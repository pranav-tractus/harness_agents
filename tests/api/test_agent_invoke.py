import mongomock
import pytest

from apps.api import seed
from apps.api.db import mongo
from apps.api.models import AgentDecision, AgentQuestion, SlotBelief
from apps.api.services import agent_service, chat_service
from apps.api.services.product_matcher_service import ProductMatch, ProductMatchResult
from core.models import SOExtractContractList
from tests.api._factories import make_extract, make_item


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    seed.seed_all()
    yield
    mongo.reset_client()


def _ctx(_cid):
    return {"profile_block": None, "history_block": None, "product_block": None}


def _decider(decision):
    return lambda name, messages, ctx, model_key, previous_json=None: decision


def _matcher(_customer_id=None, _window=None, _model_key=None):
    return ProductMatchResult(matches=[])


def _chat(customer_id="dummy-01"):
    return chat_service.ensure_default_chat(customer_id)


def test_clarify_writes_question_only():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "need choline")
    dec = AgentDecision(mode="clarify", message="What quantity and incoterm?",
                        questions=[AgentQuestion(slot="quantity", directed_to="customer", text="qty?")])
    out = agent_service.invoke("dummy-01", "sonnet-4-6",
                               decider=_decider(dec), context_fn=_ctx, matcher_fn=_matcher)
    assert out["summary"] is None
    assert out["messages"][-1]["kind"] == "question"
    assert mongo.summaries().count_documents({"status": "pending"}) == 0


def test_draft_upserts_pending_with_ledger():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT TG-BPPC CIF Busan")
    contract = SOExtractContractList(data=[])
    dec = AgentDecision(mode="draft", message="Draft ready", contract=contract,
                        ledger=[SlotBelief(slot="ship_term", value="CIF", source="chat",
                                           confidence="high", agreed_by=["customer"])])
    out = agent_service.invoke("dummy-01", "sonnet-4-6",
                               decider=_decider(dec), context_fn=_ctx, matcher_fn=_matcher)
    assert out["summary"]["status"] == "pending"
    assert out["summary"]["chat_id"] == ch
    assert out["summary"]["slots"][0]["slot"] == "ship_term"
    assert out["messages"][-1]["kind"] == "draft"


def test_invoke_includes_prior_agent_question_in_decider_window():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "need choline")
    chat_service.add_message("dummy-01", ch, "agent", "What quantity?", kind="question")
    seen = []

    def capture(name, messages, ctx, model_key, previous_json=None):
        seen.append(messages)
        return AgentDecision(mode="clarify", message="Still need incoterm?")

    agent_service.invoke("dummy-01", "sonnet-4-6", decider=capture, context_fn=_ctx, matcher_fn=_matcher)
    bodies = [m["body"] for m in seen[0]]
    assert "What quantity?" in bodies


def test_invoke_never_finalizes_even_when_ready():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT CIF Busan")
    dec = AgentDecision(mode="finalize", message="Both confirmed.",
                        contract=SOExtractContractList(data=[]), ready_to_finalize=True,
                        ledger=[SlotBelief(slot="ship_term", value="CIF", source="chat",
                                           confidence="high", agreed_by=["seller", "customer"])])
    out = agent_service.invoke("dummy-01", "sonnet-4-6",
                               decider=_decider(dec), context_fn=_ctx, matcher_fn=_matcher)
    assert out["messages"][-1]["kind"] == "draft"
    assert "@agent confirm" in out["messages"][-1]["body"]
    assert chat_service.get_last_contract_seq(ch) == 0
    assert mongo.summaries().count_documents({"status": "approved"}) == 0


def test_agent_messages_carry_decision_json():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "need choline")
    dec = AgentDecision(mode="clarify", message="Which product?",
                        questions=[AgentQuestion(slot="description", directed_to="seller", text="?")])
    out = agent_service.invoke("dummy-01", "sonnet-4-6",
                               decider=_decider(dec), context_fn=_ctx, matcher_fn=_matcher)
    assert '"mode": "clarify"' in out["messages"][-1]["summary_json"]


def _confident_matcher(code="TG-BPPC"):
    def _fn(_customer_id=None, _window=None, _model_key=None):
        return ProductMatchResult(matches=[ProductMatch(
            mention="thing", status="confident", resolved_code=code)])
    return _fn


def test_invoke_blocks_draft_on_ungrounded_product_code():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "buy GHOST-1")
    contract = make_extract(items=[make_item(description="GHOST-1")])
    dec = AgentDecision(mode="draft", message="draft", contract=contract, ledger=[])
    out = agent_service.invoke("dummy-01", "sonnet-4-6", decider=_decider(dec),
                               context_fn=_ctx, matcher_fn=_confident_matcher("TG-BPPC"))
    assert out["summary"] is None
    assert out["messages"][-1]["kind"] == "question"
    assert mongo.summaries().count_documents({"status": "pending"}) == 0


def test_invoke_stores_warnings_on_draft():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT TG-BPPC CIF")
    contract = make_extract(items=[make_item(
        description="TG-BPPC", quantity=10.0, unit_price=100.0, total=999.0, ship_term="CIF")])
    dec = AgentDecision(mode="draft", message="draft", contract=contract, ledger=[])
    out = agent_service.invoke("dummy-01", "sonnet-4-6", decider=_decider(dec),
                               context_fn=_ctx, matcher_fn=_confident_matcher("TG-BPPC"))
    assert out["summary"]["status"] == "pending"
    assert "total_mismatch" in [v["code"] for v in out["summary"]["violations"]]
