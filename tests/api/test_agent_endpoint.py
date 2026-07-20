import mongomock
import pytest
from fastapi.testclient import TestClient

from apps.api import seed
from apps.api.db import mongo
from apps.api.models import AgentDecision, AgentQuestion
from apps.api.services import agent_service


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
