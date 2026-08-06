import json

import mongomock
import pytest
from bson import ObjectId

from apps.api.db import mongo
from apps.api.db.vectors import InMemoryIndex
from apps.api.services import product_embedding_service as pe


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    yield
    mongo.reset_client()


def _fake_embed(texts, *, mode="document"):
    # Deterministic 2-dim "embeddings": length of text encodes identity.
    return [[float(len(t)), 1.0] for t in texts]


_PID = ObjectId("000000000000000000000001")


def _doc(**over):
    doc = {
        "_id": _PID, "code": "PX-1", "name": "Sunflower Lecithin",
        "short_description": "De-oiled sunflower lecithin powder",
        "long_description": "Free-flowing powder.",
        "spec": "AI >= 95%, moisture <= 2%",
        "metadata": {"form": "powder", "packing": "25kg bag"},
    }
    doc.update(over)
    return doc


def test_build_writes_main_and_spec_vectors_only():
    idx = InMemoryIndex()
    doc = _doc()
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    assert sorted(idx._store) == [f"{_PID}#main", f"{_PID}#spec"]
    main = idx._store[f"{_PID}#main"]
    assert main.metadata["code"] == "PX-1"
    assert main.metadata["kind"] == "main"
    assert main.metadata["name"] == "Sunflower Lecithin"
    attrs = json.loads(main.metadata["attrs"])
    assert attrs["form"] == "powder"
    assert "Sunflower Lecithin" in main.metadata["snippet"]
    assert len(main.metadata["snippet"]) <= 300


def test_build_records_hash_and_keys_in_mongo():
    idx = InMemoryIndex()
    doc = _doc()
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    saved = mongo.products().find_one({"_id": _PID})
    assert saved["embedded_hash"]
    assert sorted(saved["vector_keys"]) == sorted(idx._store)


def test_status_lifecycle():
    idx = InMemoryIndex()
    doc = _doc()
    mongo.products().insert_one(doc)
    assert pe.status_for_doc(doc) == "not built"
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    built = mongo.products().find_one({"_id": _PID})
    assert pe.status_for_doc(built) == "built"
    built["short_description"] = "changed"
    assert pe.status_for_doc(built) == "stale"


def test_remove_product_deletes_vectors_by_object_id():
    idx = InMemoryIndex()
    doc = _doc()
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    pe.remove_product(_PID, index=idx)
    assert idx._store == {}


def test_no_spec_vector_when_spec_and_metadata_empty():
    idx = InMemoryIndex()
    doc = _doc(spec=None, metadata={})
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    assert sorted(idx._store) == [f"{_PID}#main"]


def test_aliases_on_a_document_produce_no_vectors():
    idx = InMemoryIndex()
    doc = _doc(aliases=["SFL powder", "PL5", "lecithin"])
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    assert not any("#alias" in k for k in idx._store)
