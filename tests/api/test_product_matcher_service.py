import mongomock
import pytest

from apps.api.db import mongo
from apps.api.services import product_matcher_service as pm
from apps.api.services.product_matcher_service import (
    MentionList, ProductCandidate, ProductMatch, ProductMatchResult)


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    yield
    mongo.reset_client()


def _window(*bodies):
    return [{"seq": i, "role": "seller", "body": b} for i, b in enumerate(bodies)]


def _mentions(*ms):
    return lambda text: list(ms)


def _cands(*cands):
    return lambda mentions: list(cands)


def _hist(*codes):
    return lambda cid: [ProductCandidate(code=c, name=c, score=0.0) for c in codes]


def _cand(code, score=0.9, **kw):
    return ProductCandidate(code=code, name=kw.pop("name", code), score=score, **kw)


def test_confident_match_passes_through():
    mongo.products().insert_one({"code": "TG-BPPC", "name": "Bypass Choline"})
    result = ProductMatchResult(matches=[ProductMatch(
        mention="choline", status="confident", resolved_code="TG-BPPC",
        canonical_name="Bypass Choline", confidence=0.95)])
    out = pm.resolve_products("dummy-01", _window("need choline"), "m",
                              mention_fn=_mentions("choline"),
                              candidate_fn=_cands(_cand("TG-BPPC")),
                              history_fn=_hist(), llm=lambda *a, **k: result)
    assert out.resolved()[0].resolved_code == "TG-BPPC"
    assert out.unresolved() == []


def test_guard_rejects_a_pool_code_that_is_not_in_mongo():
    """A product deleted from Mongo can linger in the vector index."""
    result = ProductMatchResult(matches=[ProductMatch(
        mention="fructose", status="confident", resolved_code="15100500",
        canonical_name="FRUCTOPURE 500", confidence=0.93)])
    out = pm.resolve_products("dummy-01", _window("need fructose"), "m",
                              mention_fn=_mentions("fructose"),
                              candidate_fn=_cands(_cand("15100500")),
                              history_fn=_hist(), llm=lambda *a, **k: result)
    assert out.matches[0].status == "no_match"
    assert out.matches[0].resolved_code is None


def test_guard_accepts_a_code_that_is_in_mongo():
    mongo.products().insert_one({"code": "TG-BPPC", "name": "Bypass Choline"})
    result = ProductMatchResult(matches=[ProductMatch(
        mention="choline", status="confident", resolved_code="TG-BPPC",
        canonical_name="Bypass Choline", confidence=0.95)])
    out = pm.resolve_products("dummy-01", _window("need choline"), "m",
                              mention_fn=_mentions("choline"),
                              candidate_fn=_cands(_cand("TG-BPPC")),
                              history_fn=_hist(), llm=lambda *a, **k: result)
    assert out.resolved()[0].resolved_code == "TG-BPPC"


def test_history_pool_drops_codes_with_no_product():
    """The graph stores free-text descriptions in LineItem.product_code."""
    mongo.products().insert_one({"code": "TG-BPPC", "name": "Bypass Choline"})
    kept = pm._filter_history([
        ProductCandidate(code="TG-BPPC", name="TG-BPPC"),
        ProductCandidate(code="FRUCTOPURE TM 700", name="FRUCTOPURE TM 700"),
    ])
    assert [c.code for c in kept] == ["TG-BPPC"]


def test_guard_downgrades_hallucinated_code_to_no_match():
    result = ProductMatchResult(matches=[ProductMatch(
        mention="choline", status="confident", resolved_code="NOT-IN-POOL",
        canonical_name="???", confidence=0.99)])
    out = pm.resolve_products("dummy-01", _window("need choline"), "m",
                              mention_fn=_mentions("choline"),
                              candidate_fn=_cands(_cand("TG-BPPC")),
                              history_fn=_hist(), llm=lambda *a, **k: result)
    assert out.matches[0].status == "no_match"
    assert out.unresolved()


def test_empty_mentions_short_circuits_llm_and_candidates():
    called = {"llm": 0, "cands": 0}

    def _fake_llm(*a, **k):
        called["llm"] += 1
        return ProductMatchResult(matches=[])

    def _fake_cands(mentions):
        called["cands"] += 1
        return []

    out = pm.resolve_products("dummy-01", _window("hello there"), "m",
                              mention_fn=_mentions(), candidate_fn=_fake_cands,
                              history_fn=_hist(), llm=_fake_llm)
    assert out.matches == []
    assert called == {"llm": 0, "cands": 0}


def test_mentions_without_candidates_return_no_match_questions():
    def _fake_llm(*a, **k):
        raise AssertionError("llm must not be called with an empty pool")

    out = pm.resolve_products("dummy-01", _window("need unobtainium"), "m",
                              mention_fn=_mentions("unobtainium"),
                              candidate_fn=_cands(), history_fn=_hist(), llm=_fake_llm)
    assert len(out.matches) == 1
    assert out.matches[0].status == "no_match"
    assert "unobtainium" in out.matches[0].question


def test_prompt_carries_scores_metadata_snippets_and_history():
    mongo.products().insert_one({"code": "TG-BPPC", "name": "Bypass Choline"})
    seen = {}

    def _fake_llm(prompt, schema, model_key, system_prompt=None):
        seen["prompt"] = prompt
        return ProductMatchResult(matches=[])

    pm.resolve_products(
        "dummy-01", _window("the usual lecithin"), "m",
        mention_fn=_mentions("lecithin"),
        candidate_fn=_cands(_cand("GIIOFINE-UP-SF", score=0.87,
                                  name="Sunflower Lecithin Powder",
                                  snippet="de-oiled sunflower lecithin",
                                  metadata={"form": "powder"})),
        history_fn=_hist("TG-BPPC"), llm=_fake_llm)
    p = seen["prompt"]
    assert "similarity 0.87" in p
    assert "form: powder" in p
    assert "de-oiled sunflower lecithin" in p
    assert "TG-BPPC" in p


def test_default_mention_fn_uses_llm_with_mention_schema():
    def _fake_llm(prompt, schema, model_key, system_prompt=None):
        if schema is MentionList:
            return MentionList(mentions=["lecithin"])
        return ProductMatchResult(matches=[])

    out = pm.resolve_products("dummy-01", _window("send lecithin"), "m",
                              candidate_fn=_cands(_cand("A")),
                              history_fn=_hist(), llm=_fake_llm)
    assert out.matches == []  # resolution result from fake; wiring exercised


def test_dedup_keeps_best_score_and_fills_snippet():
    merged = pm._dedup([
        ProductCandidate(code="A", name="", score=0.9, snippet="best"),
        ProductCandidate(code="A", name="Alpha", score=0.5, snippet="worse",
                         metadata={"form": "powder"}),
    ])
    assert len(merged) == 1
    c = merged[0]
    assert c.score == 0.9
    assert c.snippet == "best"
    assert c.name == "Alpha"          # filled from the other candidate
    assert c.metadata == {"form": "powder"}


def test_fallback_candidates_substring_scan(monkeypatch):
    mongo.products().insert_one({
        "_id": "PL5", "code": "PL5", "name": "Feed Lecithin",
        "metadata": {"form": "liquid"}})
    monkeypatch.setattr(pm.vectors, "is_available", lambda: False)
    cands = pm._vector_candidates(["need the giiofeed pl5 drums"])
    assert [c.code for c in cands] == ["PL5"]
    assert cands[0].metadata == {"form": "liquid"}


def test_vector_error_falls_back(monkeypatch):
    mongo.products().insert_one({"_id": "PL5", "code": "PL5", "name": "Feed Lecithin"})
    monkeypatch.setattr(pm.vectors, "is_available", lambda: True)

    def _boom(*a, **k):
        raise RuntimeError("aws down")

    monkeypatch.setattr(pm.embeddings, "embed", _boom)
    cands = pm._vector_candidates(["pl5 please"])
    assert [c.code for c in cands] == ["PL5"]


def test_vector_candidate_without_code_metadata_is_skipped(monkeypatch):
    from apps.api.db.vectors import VectorHit

    class _Idx:
        def query(self, embedding, top_k=5):
            return [
                VectorHit(key="000000000000000000000009#main", score=0.9,
                          metadata={"name": "Nameless"}),
                VectorHit(key="000000000000000000000009#spec", score=0.8,
                          metadata={"code": "PL5", "name": "Feed Lecithin"}),
            ]

    monkeypatch.setattr(pm.vectors, "is_available", lambda: True)
    monkeypatch.setattr(pm.vectors, "default_index", lambda: _Idx())
    monkeypatch.setattr(pm.embeddings, "embed", lambda texts, mode="query": [[1.0, 0.0]])
    cands = pm._vector_candidates(["lecithin"])
    assert [c.code for c in cands] == ["PL5"]


def test_system_prompt_carries_hard_rules():
    assert "Only ever use codes from the provided pool" in pm._SYSTEM
    assert "Empty is a valid answer" in pm._SYSTEM
