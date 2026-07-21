import mongomock
import pytest

from apps.api.db import mongo


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(mongo, "_client", client)
    yield
    mongo.reset_client()


def test_collections_are_named():
    assert mongo.customers().name == "customers"
    assert mongo.products().name == "products"
    assert mongo.messages().name == "messages"
    assert mongo.summaries().name == "summaries"


def test_insert_and_read_roundtrip():
    mongo.customers().insert_one({"_id": "dummy-01", "name": "Dummy-01"})
    doc = mongo.customers().find_one({"_id": "dummy-01"})
    assert doc["name"] == "Dummy-01"
