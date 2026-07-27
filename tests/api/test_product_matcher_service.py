from apps.api.services import product_matcher_service as pm
from apps.api.services.product_matcher_service import (
    ProductCandidate, ProductMatch, ProductMatchResult)


def _window(*bodies):
    return [{"seq": i, "role": "seller", "body": b} for i, b in enumerate(bodies)]


def _pool(*codes):
    return lambda text: [ProductCandidate(code=c, name=c, score=1.0) for c in codes]


def _hist(*codes):
    return lambda cid: [ProductCandidate(code=c, name=c, score=2.0) for c in codes]


def test_confident_match_passes_through():
    result = ProductMatchResult(matches=[ProductMatch(
        mention="choline", status="confident", resolved_code="TG-BPPC",
        canonical_name="Bypass Choline", confidence=0.95)])
    out = pm.resolve_products("dummy-01", _window("need choline"), "m",
                              catalog_pool_fn=_pool("TG-BPPC"), history_fn=_hist(),
                              llm=lambda *a, **k: result)
    assert out.resolved()[0].resolved_code == "TG-BPPC"
    assert out.unresolved() == []


def test_guard_downgrades_hallucinated_code_to_no_match():
    result = ProductMatchResult(matches=[ProductMatch(
        mention="choline", status="confident", resolved_code="NOT-IN-POOL",
        canonical_name="???", confidence=0.99)])
    out = pm.resolve_products("dummy-01", _window("need choline"), "m",
                              catalog_pool_fn=_pool("TG-BPPC"), history_fn=_hist(),
                              llm=lambda *a, **k: result)
    assert out.matches[0].status == "no_match"
    assert out.unresolved()


def test_ambiguous_is_unresolved():
    result = ProductMatchResult(matches=[ProductMatch(
        mention="lecithin", status="ambiguous", confidence=0.4,
        candidates=[ProductCandidate(code="A", name="A"), ProductCandidate(code="B", name="B")],
        question="Did you mean A or B?")])
    out = pm.resolve_products("dummy-01", _window("send lecithin"), "m",
                              catalog_pool_fn=_pool("A", "B"), history_fn=_hist(),
                              llm=lambda *a, **k: result)
    assert len(out.unresolved()) == 1


def test_history_candidates_reach_the_llm_prompt():
    seen = {}

    def _fake_llm(prompt, schema, model_key, system_prompt=None):
        seen["prompt"] = prompt
        return ProductMatchResult(matches=[])

    pm.resolve_products("dummy-01", _window("the usual"), "m",
                        catalog_pool_fn=_pool(), history_fn=_hist("TG-BPPC"), llm=_fake_llm)
    assert "TG-BPPC" in seen["prompt"]


def test_empty_pool_skips_llm_and_returns_no_matches():
    called = {"n": 0}

    def _fake_llm(*a, **k):
        called["n"] += 1
        return ProductMatchResult(matches=[])

    out = pm.resolve_products("dummy-01", _window("hello"), "m",
                              catalog_pool_fn=_pool(), history_fn=_hist(), llm=_fake_llm)
    assert out.matches == []
    assert called["n"] == 0


def test_system_prompt_carries_hard_rules():
    from apps.api.services import product_matcher_service
    system = product_matcher_service._SYSTEM
    assert "Only ever use codes from the provided pool" in system
    assert "Empty is a valid answer" in system
