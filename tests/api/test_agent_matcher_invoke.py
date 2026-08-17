import mongomock
import pytest

from apps.api import seed
from apps.api.db import mongo
from apps.api.models import AgentDecision, SlotBelief
from apps.api.services import agent_service, chat_service
from apps.api.services.product_matcher_service import (
    ProductMatch, ProductMatchResult)
from core.models import SOExtractContractList


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    seed.seed_all()
    mongo.customers().update_one({"_id": "dummy-01"}, {"$set": {"org_id": "pym"}})
    yield
    mongo.reset_client()


def _ctx(_cid):
    return {"profile_block": None, "history_block": None, "product_block": None}


def _decider(decision):
    return lambda name, messages, ctx, model_key, previous_json=None: decision


def _matcher(result):
    return lambda customer_id, window, model_key: result


def _chat():
    return chat_service.ensure_default_chat("dummy-01")


def test_unresolved_match_short_circuits_with_question_and_no_draft():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "send lecithin")
    result = ProductMatchResult(matches=[ProductMatch(
        mention="lecithin", status="ambiguous", question="Sunflower or Soy lecithin?")])
    dec = AgentDecision(mode="draft", message="should not run",
                        contract=SOExtractContractList(data=[]))
    out = agent_service.invoke("dummy-01", "m", decider=_decider(dec), context_fn=_ctx,
                               matcher_fn=_matcher(result))
    assert out["summary"] is None
    assert out["messages"][-1]["kind"] == "question"
    assert "lecithin" in out["messages"][-1]["body"].lower()
    assert mongo.summaries().count_documents({"status": "pending"}) == 0


def test_confident_match_drafts_and_records_provenance():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT choline CIF Busan")
    result = ProductMatchResult(matches=[ProductMatch(
        mention="choline", status="confident", resolved_code="TG-BPPC",
        canonical_name="Bypass Choline", confidence=0.95)])
    dec = AgentDecision(mode="draft", message="Draft ready",
                        contract=SOExtractContractList(data=[]),
                        ledger=[SlotBelief(slot="ship_term", value="CIF", source="chat",
                                           confidence="high", agreed_by=["customer"],
                                           source_seqs=[1])])
    out = agent_service.invoke("dummy-01", "m", decider=_decider(dec), context_fn=_ctx,
                               matcher_fn=_matcher(result))
    assert out["messages"][-1]["kind"] == "draft"
    doc = mongo.summaries().find_one({"_id": mongo.summaries().find_one()["_id"]})
    assert doc["product_matches"][0]["resolved_code"] == "TG-BPPC"


def test_no_product_mention_drafts_normally():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "hello there")
    dec = AgentDecision(mode="draft", message="Draft", contract=SOExtractContractList(data=[]))
    out = agent_service.invoke("dummy-01", "m", decider=_decider(dec), context_fn=_ctx,
                               matcher_fn=_matcher(ProductMatchResult(matches=[])))
    assert out["messages"][-1]["kind"] == "draft"


def test_confident_match_narrows_product_block_for_decider():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT choline")
    seen = {}

    def _capture(name, messages, ctx, model_key, previous_json=None):
        seen["product_block"] = ctx.get("product_block")
        return AgentDecision(mode="draft", message="d", contract=SOExtractContractList(data=[]))

    result = ProductMatchResult(matches=[ProductMatch(
        mention="choline", status="confident", resolved_code="TG-BPPC",
        canonical_name="Bypass Choline", confidence=0.95)])
    agent_service.invoke("dummy-01", "m", decider=_capture, context_fn=_ctx,
                         matcher_fn=_matcher(result))
    assert "TG-BPPC" in (seen["product_block"] or "")


def test_match_question_renders_scores_and_snippets():
    from apps.api.services.agent_service import _match_question
    from apps.api.services.product_matcher_service import ProductCandidate, ProductMatch
    m = ProductMatch(mention="lecithin", status="ambiguous", candidates=[
        ProductCandidate(code="GIIOFINE-UP-SF", name="Sunflower Lecithin Powder",
                         score=0.87, snippet="de-oiled sunflower lecithin powder"),
        ProductCandidate(code="GIIOFINE_L_SF", name="Sunflower Lecithin Liquid",
                         score=0.84),
    ])
    q = _match_question([m])
    assert "(GIIOFINE-UP-SF, 0.87" in q
    assert 'de-oiled sunflower lecithin powder' in q
    assert "(GIIOFINE_L_SF, 0.84)" in q


def test_match_question_without_scores_stays_clean():
    from apps.api.services.agent_service import _match_question
    from apps.api.services.product_matcher_service import ProductCandidate, ProductMatch
    m = ProductMatch(mention="x", status="ambiguous", candidates=[
        ProductCandidate(code="A", name="Alpha")])
    q = _match_question([m])
    assert "(A)" in q and "0.00" not in q


def test_invoke_explains_when_the_customer_has_no_organization():
    from apps.api.services import agent_service, org_service
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "need choline")
    mongo.customers().update_one({"_id": "dummy-01"}, {"$unset": {"org_id": ""}})

    def _matcher(*a, **k):
        raise org_service.MissingOrg("no org")

    out = agent_service.invoke("dummy-01", "m", matcher_fn=_matcher)
    assert out["summary"] is None
    assert "organization" in out["messages"][0]["body"].lower()
