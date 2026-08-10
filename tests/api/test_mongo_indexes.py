import mongomock
import pytest
from pymongo.errors import DuplicateKeyError

from apps.api.db import mongo


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    yield
    mongo.reset_client()


def test_code_is_unique():
    mongo.ensure_indexes()
    mongo.products().insert_one({"code": "A", "source_pdf_hash": "h1"})
    with pytest.raises(DuplicateKeyError):
        mongo.products().insert_one({"code": "A", "source_pdf_hash": "h2"})


def test_source_pdf_hash_is_unique():
    mongo.ensure_indexes()
    mongo.products().insert_one({"code": "A", "source_pdf_hash": "h1"})
    with pytest.raises(DuplicateKeyError):
        mongo.products().insert_one({"code": "B", "source_pdf_hash": "h1"})


def test_source_pdf_hash_index_is_sparse():
    """Seeded products carry no hash; many of them must coexist."""
    mongo.ensure_indexes()
    mongo.products().insert_one({"code": "A"})
    mongo.products().insert_one({"code": "B"})
    assert mongo.products().count_documents({}) == 2


def test_ensure_indexes_is_idempotent():
    mongo.ensure_indexes()
    mongo.ensure_indexes()
    mongo.products().insert_one({"code": "A"})
    assert mongo.products().count_documents({}) == 1


def test_ensure_indexes_creates_org_id_indexes():
    mongo.ensure_indexes()
    product_keys = [k for ix in mongo.products().index_information().values()
                    for k, _ in ix["key"]]
    customer_keys = [k for ix in mongo.customers().index_information().values()
                     for k, _ in ix["key"]]
    assert "org_id" in product_keys
    assert "org_id" in customer_keys
