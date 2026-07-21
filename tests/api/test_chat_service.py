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


def test_seq_is_monotonic_per_chat():
    ch = chat_service.ensure_default_chat("dummy-01")
    other = chat_service.ensure_default_chat("dummy-02")
    a = chat_service.add_message("dummy-01", ch, "me", "hi")
    b = chat_service.add_message("dummy-01", ch, "customer", "hello")
    c = chat_service.add_message("dummy-02", other, "me", "hi")
    assert a["seq"] == 1 and b["seq"] == 2
    assert c["seq"] == 1  # independent per chat


def test_since_filters_by_kind_and_seq():
    ch = chat_service.ensure_default_chat("dummy-01")
    chat_service.add_message("dummy-01", ch, "me", "old")           # seq 1
    chat_service.add_message("dummy-01", ch, "me", "/cmd", kind="command")  # seq 2
    chat_service.add_message("dummy-01", ch, "customer", "new")     # seq 3
    since = chat_service.chat_messages_since(ch, 1)
    bodies = [m["body"] for m in since]
    assert bodies == ["new"]  # command excluded, old excluded


def test_messages_since_accepts_kind_filter():
    ch = chat_service.ensure_default_chat("dummy-01")
    chat_service.add_message("dummy-01", ch, "seller", "hi")                    # seq 1 chat
    chat_service.add_message("dummy-01", ch, "agent", "qty?", kind="question")  # seq 2
    chat_service.add_message("dummy-01", ch, "me", "/cmd", kind="command")      # seq 3
    since = chat_service.messages_since(ch, 0, kinds=["chat", "question"])
    assert [m["kind"] for m in since] == ["chat", "question"]


def test_checkpoint_roundtrip():
    ch = chat_service.ensure_default_chat("dummy-01")
    assert chat_service.get_last_contract_seq(ch) == 0
    chat_service.set_last_contract_seq(ch, 7)
    assert chat_service.get_last_contract_seq(ch) == 7


def test_ensure_active_chat_reuses_then_creates_after_finish():
    a = chat_service.ensure_active_chat("dummy-01")
    assert chat_service.ensure_active_chat("dummy-01") == a  # reuse while active
    chat_service.finish_chat(a)
    b = chat_service.ensure_active_chat("dummy-01")
    assert b != a  # new chat once finished


def test_start_new_chat_numbers_titles():
    first = chat_service.ensure_active_chat("dummy-02")  # "Chat 1"
    chat_service.finish_chat(first)
    second = chat_service.start_new_chat("dummy-02")
    assert second["title"] == "Chat 2"


def test_all_messages_spans_chats_in_order_with_status():
    a = chat_service.ensure_active_chat("dummy-03")
    chat_service.add_message("dummy-03", a, "seller", "in chat 1")
    chat_service.finish_chat(a)
    b = chat_service.start_new_chat("dummy-03")["id"]
    chat_service.add_message("dummy-03", b, "seller", "in chat 2")
    rows = chat_service.all_messages("dummy-03")
    assert [r["body"] for r in rows] == ["in chat 1", "in chat 2"]
    assert rows[0]["chat_id"] == a and rows[0]["chat_status"] == "finished"
    assert rows[1]["chat_id"] == b and rows[1]["chat_status"] == "active"
