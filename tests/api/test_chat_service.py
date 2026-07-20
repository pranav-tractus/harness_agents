import mongomock
import pytest

from apps.api.db import mongo
from apps.api.services import chat_service


def _seed_customers() -> None:
    for cid in ("dummy-01", "dummy-02", "dummy-03"):
        mongo.customers().insert_one(
            {"_id": cid, "name": cid, "profile": {}, "last_contract_seq": 0, "updated_at": "now"}
        )


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    _seed_customers()
    yield
    mongo.reset_client()


def test_seq_is_monotonic_per_customer():
    a = chat_service.add_message("dummy-01", "me", "hi")
    b = chat_service.add_message("dummy-01", "customer", "hello")
    c = chat_service.add_message("dummy-02", "me", "hi")
    assert a["seq"] == 1 and b["seq"] == 2
    assert c["seq"] == 1  # independent per customer


def test_since_filters_by_kind_and_seq():
    chat_service.add_message("dummy-01", "me", "old")           # seq 1
    chat_service.add_message("dummy-01", "me", "/cmd", kind="command")  # seq 2
    chat_service.add_message("dummy-01", "customer", "new")     # seq 3
    since = chat_service.chat_messages_since("dummy-01", 1)
    bodies = [m["body"] for m in since]
    assert bodies == ["new"]  # command excluded, old excluded


def test_messages_since_accepts_kind_filter():
    chat_service.add_message("dummy-01", "seller", "hi")                    # seq 1 chat
    chat_service.add_message("dummy-01", "agent", "qty?", kind="question")  # seq 2
    chat_service.add_message("dummy-01", "me", "/cmd", kind="command")      # seq 3
    since = chat_service.messages_since("dummy-01", 0, kinds=["chat", "question"])
    assert [m["kind"] for m in since] == ["chat", "question"]


def test_checkpoint_roundtrip():
    assert chat_service.get_last_contract_seq("dummy-01") == 0
    chat_service.set_last_contract_seq("dummy-01", 7)
    assert chat_service.get_last_contract_seq("dummy-01") == 7
