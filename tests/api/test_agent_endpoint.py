import mongomock
import pytest
from fastapi.testclient import TestClient

from apps.api import seed
from apps.api.db import mongo
from apps.api.models import AgentDecision, AgentQuestion
from apps.api.services import agent_service, chat_service


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    seed.seed_all()
    dec = AgentDecision(mode="clarify", message="What quantity?",
                        questions=[AgentQuestion(slot="quantity", directed_to="customer", text="qty?")])
    monkeypatch.setattr(agent_service, "decide", lambda *a, **k: dec)
    from apps.api.main import create_app
    with TestClient(create_app()) as c:
        yield c


def _post(client, body, **extra):
    return client.post("/api/customers/dummy-01/messages",
                       json={"role": "seller", "body": body, **extra})


def test_untagged_message_does_not_invoke_the_agent(client):
    r = _post(client, "need choline")
    assert r.status_code == 200
    data = r.json()
    assert len(data["messages"]) == 1
    assert data["messages"][0]["kind"] == "chat"
    assert data["summary"] is None


def test_tagged_message_appends_then_asks(client):
    _post(client, "need choline")
    r = _post(client, "@agent create sales order", model_key="sonnet-4-6")
    assert r.status_code == 200
    data = r.json()
    assert data["messages"][0]["body"] == "@agent create sales order"
    assert data["messages"][-1]["kind"] == "question"


def test_tagged_message_without_model_key_still_runs(client):
    _post(client, "need choline")
    r = _post(client, "@agent create sales order")
    assert r.status_code == 200
    assert r.json()["messages"][-1]["kind"] == "question"


def test_confirm_tag_finalizes_the_pending_draft(client, monkeypatch):
    from apps.api.services import chat_graph_service
    from core.models import SOExtractContractList

    _post(client, "10MT CIF")
    ch = chat_service.ensure_default_chat("dummy-01")
    monkeypatch.setattr(chat_graph_service, "write_contract", lambda *a, **k: "contract-id")
    sid = mongo.summaries().insert_one({
        "customer_id": "dummy-01", "chat_id": ch, "status": "pending", "model_key": "sonnet-4-6",
        "from_seq": 1, "to_seq": 1, "revision": 0,
        "content": SOExtractContractList(data=[]).model_dump(),
        "rendered_markdown": "draft",
        "slots": [{"slot": s, "value": "x", "source": "chat", "confidence": "high",
                   "agreed_by": ["seller", "customer"], "source_seqs": [1]}
                  for s in ["description", "quantity", "unit_price", "ship_term"]],
        "created_at": "t", "approved_at": None,
    }).inserted_id
    chat_service.add_message("dummy-01", ch, "agent", "draft card", kind="draft",
                             summary_id=str(sid))
    r = _post(client, "@agent confirm", model_key="sonnet-4-6")
    assert r.status_code == 200
    data = r.json()
    assert data["messages"][-1]["kind"] == "final"
    assert data["summary"]["status"] == "approved"
