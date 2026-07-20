import mongomock
import pytest
from fastapi.testclient import TestClient

from apps.api import seed
from apps.api.db import mongo


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    seed.seed_all()
    from apps.api.main import create_app
    with TestClient(create_app()) as c:
        yield c


def test_create_and_list_chats(client):
    r = client.post("/api/customers/dummy-01/chats", json={"title": "Deal A"})
    assert r.status_code == 201
    chat_id = r.json()["id"]
    rows = client.get("/api/customers/dummy-01/chats").json()
    assert any(c["id"] == chat_id for c in rows)


def test_post_message_to_chat(client):
    chat_id = client.post("/api/customers/dummy-01/chats", json={"title": "A"}).json()["id"]
    m = client.post(f"/api/customers/dummy-01/chats/{chat_id}/messages",
                    json={"role": "seller", "body": "hi"}).json()
    assert m["chat_id"] == chat_id and m["seq"] == 1
