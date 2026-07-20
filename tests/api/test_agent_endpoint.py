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
    monkeypatch.setattr(agent_service, "decide",
                        lambda *a, **k: dec)
    from apps.api.main import create_app
    with TestClient(create_app()) as c:
        yield c


def test_agent_ask_returns_question(client):
    client.post("/api/customers/dummy-01/messages", json={"role": "seller", "body": "need choline"})
    r = client.post("/api/customers/dummy-01/agent", json={"model_key": "sonnet-4-6", "action": "ask"})
    assert r.status_code == 200
    assert r.json()["messages"][-1]["kind"] == "question"


def test_agent_approve_returns_final(client, monkeypatch):
    from apps.api.services import chat_graph_service
    from core.models import SOExtractContractList

    client.post("/api/customers/dummy-01/messages", json={"role": "seller", "body": "10MT CIF"})
    ch = chat_service.ensure_default_chat("dummy-01")
    monkeypatch.setattr(chat_graph_service, "build_and_write",
                        lambda *a, **k: {"written": True})
    sid = mongo.summaries().insert_one({
        "customer_id": "dummy-01", "status": "pending", "model_key": "sonnet-4-6",
        "from_seq": 1, "to_seq": 1, "revision": 0,
        "content": SOExtractContractList(data=[]).model_dump(),
        "rendered_markdown": "draft", "slots": [], "created_at": "t", "approved_at": None,
    }).inserted_id
    chat_service.add_message("dummy-01", ch, "agent", "draft card", kind="draft",
                             summary_id=str(sid))
    r = client.post("/api/customers/dummy-01/agent", json={"model_key": "sonnet-4-6", "action": "approve"})
    assert r.status_code == 200
    data = r.json()
    assert data["messages"][-1]["kind"] == "final"
    assert data["summary"]["status"] == "approved"
