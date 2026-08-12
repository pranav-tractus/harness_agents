import mongomock
import pytest

from apps.api.db import mongo
from apps.api.services import org_classifier_service as oc
from apps.api.services import org_service


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    org_service.seed_roster()
    yield
    mongo.reset_client()


def _boom_llm(*a, **k):
    raise AssertionError("the LLM must not be called when a rule matches")


def test_category_rule_places_amino_acids_in_pym():
    doc = {"code": "TG-RPMT", "name": "Rumen Protected Methionine",
           "short_description": "Rumen-protected DL-Methionine",
           "metadata": {"category": "Amino acids"}}
    assert oc.classify(doc, llm=_boom_llm) == oc.Classification("pym", "rule")


def test_keyword_rule_places_uncategorised_lecithin_in_roxxon():
    doc = {"code": "GIIOFINE-UP-SF", "name": "Sunflower Lecithin Powder",
           "short_description": "De-Oiled Sunflower Lecithin Powder", "metadata": {}}
    assert oc.classify(doc, llm=_boom_llm) == oc.Classification("roxxon", "rule")


def test_category_pass_beats_keyword_pass_across_rules():
    """TG-BETAINE's long description mentions choline and DL-methionine.

    A single-pass first-hit-wins loop would file this Vitamins product under
    Roxxon (choline) or Pym (methionine).
    """
    doc = {"code": "TG-BETAINE", "name": "Betaine Anhydrous 98%",
           "short_description": "Betaine anhydrous 98% feed grade",
           "long_description": "Partially replaces DL-methionine and choline chloride.",
           "metadata": {"category": "Vitamins"}}
    assert oc.classify(doc, llm=_boom_llm) == oc.Classification("alchemax", "rule")


def test_keyword_pass_ignores_long_description():
    doc = {"code": "X-1", "name": "Mystery Additive", "short_description": "unknown blend",
           "long_description": "contains lecithin and phytase", "metadata": {}}
    result = oc.classify(doc, llm=lambda *a, **k: oc.OrgChoice(org_id="alchemax"))
    assert result == oc.Classification("alchemax", "llm")


def test_llm_runs_only_when_no_rule_matched():
    doc = {"code": "X-2", "name": "Widget", "short_description": "a widget", "metadata": {}}
    seen = {}

    def _llm(prompt, schema, model_key, system_prompt=None):
        seen["prompt"] = prompt
        return oc.OrgChoice(org_id="pym", reason="closest fit")

    assert oc.classify(doc, llm=_llm) == oc.Classification("pym", "llm")
    assert "Pym Technologies" in seen["prompt"]
    assert "Widget" in seen["prompt"]


def test_llm_answer_outside_the_roster_falls_back_to_catchall():
    doc = {"code": "X-3", "name": "Widget", "short_description": "a widget", "metadata": {}}
    result = oc.classify(doc, llm=lambda *a, **k: oc.OrgChoice(org_id="hydra"))
    assert result == oc.Classification("damage-control", "catchall")


def test_llm_exception_falls_back_to_catchall():
    doc = {"code": "X-4", "name": "Widget", "short_description": "a widget", "metadata": {}}

    def _llm(*a, **k):
        raise RuntimeError("provider down")

    assert oc.classify(doc, llm=_llm) == oc.Classification("damage-control", "catchall")


def test_every_seeded_product_is_placed_by_a_rule():
    from apps.api.seed import _PRODUCTS
    for p in _PRODUCTS:
        result = oc.classify(p, llm=_boom_llm)
        assert result.via == "rule", f"{p['code']} fell through to the LLM"
