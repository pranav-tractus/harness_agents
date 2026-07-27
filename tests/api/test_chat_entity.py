import mongomock
import pytest

from apps.api import seed
from apps.api.db import mongo
from apps.api.services import chat_service


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    seed.seed_all()
    yield
    mongo.reset_client()


def test_seq_is_per_chat():
    ch = chat_service.ensure_default_chat("dummy-01")
    other = chat_service.create_chat("dummy-01", "Second deal")["id"]
    a = chat_service.add_message("dummy-01", ch, "seller", "hi")
    b = chat_service.add_message("dummy-01", other, "seller", "hi")
    assert a["seq"] == 1 and b["seq"] == 1       # independent per chat
    assert a["chat_id"] == ch and b["chat_id"] == other


def test_checkpoint_is_per_chat():
    ch = chat_service.ensure_default_chat("dummy-01")
    assert chat_service.get_last_contract_seq(ch) == 0
    chat_service.set_last_contract_seq(ch, 5)
    assert chat_service.get_last_contract_seq(ch) == 5


def test_since_filters_by_chat_kind_and_seq():
    ch = chat_service.ensure_default_chat("dummy-01")
    chat_service.add_message("dummy-01", ch, "seller", "old")                 # 1
    chat_service.add_message("dummy-01", ch, "agent", "qty?", kind="question")   # 2
    chat_service.add_message("dummy-01", ch, "customer", "new")               # 3
    since = chat_service.chat_messages_since(ch, 1)
    assert [m["body"] for m in since] == ["new"]
