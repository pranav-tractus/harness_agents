import mongomock
import pytest

from apps.api import seed
from apps.api.db import mongo
from apps.api.models import AgentDecision, AgentQuestion, SlotBelief
from apps.api.services import agent_service, chat_service
from core.models import SOExtractContractList


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


def test_clarify_writes_question_only():
    chat_service.add_message("dummy-01", "seller", "need choline")
    dec = AgentDecision(mode="clarify", message="What quantity and incoterm?",
                        questions=[AgentQuestion(slot="quantity", directed_to="customer", text="qty?")])
    out = agent_service.invoke("dummy-01", "sonnet-4-6",
                               decider=_decider(dec), context_fn=_ctx)
    assert out["summary"] is None
    assert out["messages"][-1]["kind"] == "question"
    assert mongo.summaries().count_documents({"status": "pending"}) == 0


def test_draft_upserts_pending_with_ledger():
    chat_service.add_message("dummy-01", "seller", "10MT TG-BPPC CIF Busan")
    contract = SOExtractContractList(data=[])
    dec = AgentDecision(mode="draft", message="Draft ready", contract=contract,
                        ledger=[SlotBelief(slot="ship_term", value="CIF", source="chat",
                                           confidence="high", agreed_by=["customer"])])
    out = agent_service.invoke("dummy-01", "sonnet-4-6",
                               decider=_decider(dec), context_fn=_ctx)
    assert out["summary"]["status"] == "pending"
    assert out["summary"]["slots"][0]["slot"] == "ship_term"
    assert out["messages"][-1]["kind"] == "draft"


def test_invoke_includes_prior_agent_question_in_decider_window():
    chat_service.add_message("dummy-01", "seller", "need choline")
    chat_service.add_message("dummy-01", "agent", "What quantity?", kind="question")
    seen = []

    def capture(name, messages, ctx, model_key, previous_json=None):
        seen.append(messages)
        return AgentDecision(mode="clarify", message="Still need incoterm?")

    agent_service.invoke("dummy-01", "sonnet-4-6", decider=capture, context_fn=_ctx)
    bodies = [m["body"] for m in seen[0]]
    assert "What quantity?" in bodies


def test_invoke_auto_finalizes_when_ready():
    chat_service.add_message("dummy-01", "seller", "10MT CIF Busan")
    calls = []
    dec = AgentDecision(mode="finalize", message="Both confirmed. Finalizing.",
                        contract=SOExtractContractList(data=[]), ready_to_finalize=True,
                        ledger=[SlotBelief(slot="ship_term", value="CIF", source="chat",
                                           confidence="high", agreed_by=["seller", "customer"])])

    def _graph(customer_id, messages, to_seq, model_key):
        calls.append(to_seq)

    out = agent_service.invoke("dummy-01", "sonnet-4-6",
                               decider=_decider(dec), context_fn=_ctx, graph_fn=_graph)
    assert calls == [1]
    assert chat_service.get_last_contract_seq("dummy-01") == 1
    assert out["messages"][-1]["kind"] == "final"
    assert mongo.summaries().count_documents({"status": "approved"}) == 1
