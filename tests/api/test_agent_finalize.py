import mongomock
import pytest

from apps.api import seed
from apps.api.db import mongo
from apps.api.models import AgentDecision, CRITICAL_SLOTS_ORDER, SlotBelief
from apps.api.services import agent_service, chat_service
from core.models import SOExtractContractList
from tests.api._factories import make_extract, make_item


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


def _ready_slots():
    return [{"slot": s, "value": "x", "source": "chat", "confidence": "high",
             "agreed_by": ["seller", "customer"]} for s in CRITICAL_SLOTS_ORDER]


def _seed_pending(ch, slots):
    mongo.summaries().insert_one({
        "customer_id": "dummy-01", "chat_id": ch, "status": "pending", "model_key": "sonnet-4-6",
        "from_seq": 1, "to_seq": 1, "revision": 0,
        "content": SOExtractContractList(data=[]).model_dump(),
        "rendered_markdown": "draft", "slots": slots, "created_at": "t", "approved_at": None})


def _seed_pending_content(ch, slots, content):
    mongo.summaries().insert_one({
        "customer_id": "dummy-01", "chat_id": ch, "status": "pending",
        "model_key": "sonnet-4-6", "from_seq": 1, "to_seq": 1, "revision": 0,
        "content": content, "rendered_markdown": "draft", "slots": slots,
        "created_at": "t", "approved_at": None})


def test_approve_refuses_when_not_ready():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "x")
    _seed_pending(ch, [])  # nothing agreed
    out = agent_service.approve("dummy-01", graph_fn=_graph([]), branch_fn=lambda *a, **k: None)
    assert out["summary"] is None
    assert out["messages"][-1]["kind"] == "chat"
    assert "Not ready" in out["messages"][-1]["body"]
    assert chat_service.get_last_contract_seq(ch) == 0


def test_approve_finalizes_ready_draft_and_branches():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT CIF Busan")
    _seed_pending(ch, _ready_slots())
    out = agent_service.approve("dummy-01", graph_fn=_graph([]), branch_fn=lambda *a, **k: None)
    assert out["summary"]["status"] == "approved"
    assert out["messages"][-1]["summary_json"]  # JSON attached
    # current chat finished, a fresh active chat now exists
    from apps.api.services import chat_service as cs
    assert cs.active_chat("dummy-01")["_id"].__str__() != ch


def test_approve_blocks_on_unresolved_sku():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "buy GHOST-1")  # seq 1
    contract = make_extract(items=[make_item(description="GHOST-1")]).model_dump()
    mongo.summaries().insert_one({
        "customer_id": "dummy-01", "chat_id": ch, "status": "pending",
        "model_key": "sonnet-4-6", "from_seq": 1, "to_seq": 1, "revision": 0,
        "content": contract, "rendered_markdown": "draft", "slots": _ready_slots(),
        "product_matches": [{"mention": "tg", "status": "confident",
                             "resolved_code": "TG-BPPC", "canonical_name": "TG-BPPC"}],
        "created_at": "t", "approved_at": None})
    out = agent_service.approve("dummy-01", graph_fn=_graph([]),
                                branch_fn=lambda *a, **k: None)
    assert out["summary"] is None
    assert mongo.summaries().count_documents({"status": "approved"}) == 0
    assert "GHOST-1" in out["messages"][-1]["body"]


def test_approve_blocks_on_verification_failure():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT CIF")  # seq 1
    bad = make_extract(items=[make_item(description="TG-BPPC", ship_term="CIFF")]).model_dump()
    _seed_pending_content(ch, _ready_slots(), bad)
    out = agent_service.approve("dummy-01", graph_fn=_graph([]), branch_fn=lambda *a, **k: None)
    assert out["summary"] is None
    assert mongo.summaries().count_documents({"status": "approved"}) == 0
    assert chat_service.get_last_contract_seq(ch) == 0
    assert "finalize" in out["messages"][-1]["body"].lower()


def test_finalize_stamps_chat_id_on_approved_summary():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT CIF Busan")
    dec = AgentDecision(mode="finalize", message="Done.",
                        contract=SOExtractContractList(data=[]), ready_to_finalize=True, ledger=[])
    window = chat_service.chat_messages_since(ch, 0)
    out = agent_service.finalize("dummy-01", decision=dec, window=window,
                                 model_key="sonnet-4-6", graph_fn=_graph([]))
    assert out["summary"]["chat_id"] == ch
    assert mongo.summaries().find_one({"status": "approved"})["chat_id"] == ch
