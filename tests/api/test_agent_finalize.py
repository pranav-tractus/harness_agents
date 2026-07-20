import mongomock
import pytest

from apps.api import seed
from apps.api.db import mongo
from apps.api.models import AgentDecision, SlotBelief
from apps.api.services import agent_service, chat_service
from core.models import SOExtractContractList


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    seed.seed_all()
    yield
    mongo.reset_client()


def _graph(order):
    def _fn(customer_id, chat_id, chat_title, contract, slots, source_seqs, to_seq):
        order.append(to_seq)
        return "contract-id"
    return _fn


def _chat(customer_id="dummy-01"):
    return chat_service.ensure_default_chat(customer_id)


def test_auto_finalize_advances_checkpoint_and_writes_graph():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT CIF Busan")  # seq 1
    calls = []
    dec = AgentDecision(mode="finalize", message="Both confirmed. Finalizing.",
                        contract=SOExtractContractList(data=[]), ready_to_finalize=True,
                        ledger=[SlotBelief(slot="ship_term", value="CIF", source="chat",
                                           confidence="high", agreed_by=["seller", "customer"])])
    window = chat_service.chat_messages_since(ch, 0)
    out = agent_service.finalize("dummy-01", decision=dec, window=window,
                                 model_key="sonnet-4-6", graph_fn=_graph(calls))
    assert calls == [1]
    assert chat_service.get_last_contract_seq(ch) == 1
    assert out["messages"][-1]["kind"] == "final"
    assert mongo.summaries().count_documents({"status": "approved"}) == 1


def test_approve_finalizes_pending_draft():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "x")
    mongo.summaries().insert_one({
        "customer_id": "dummy-01", "status": "pending", "model_key": "sonnet-4-6",
        "from_seq": 1, "to_seq": 1, "revision": 0,
        "content": SOExtractContractList(data=[]).model_dump(),
        "rendered_markdown": "draft", "slots": [], "created_at": "t", "approved_at": None})
    out = agent_service.approve("dummy-01", graph_fn=_graph([]))
    assert out["summary"]["status"] == "approved"
    assert chat_service.get_last_contract_seq(ch) == 1
