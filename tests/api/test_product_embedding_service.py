import mongomock
import pytest

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


def _doc(**over):
    doc = {
        "_id": "PX-1", "code": "PX-1", "name": "Sunflower Lecithin",
        "short_description": "De-oiled sunflower lecithin powder",
        "long_description": "Free-flowing powder.",
        "spec": "AI >= 95%, moisture <= 2%",
        "metadata": {"form": "powder", "packing": "25kg bag"},
        "aliases": ["SFL powder", "PL5"],
    }
    doc.update(over)
    return doc


def test_build_writes_main_spec_and_alias_vectors():
    idx = InMemoryIndex()
    doc = _doc()
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    keys = sorted(idx._store)
    assert keys == ["PX-1#alias#0", "PX-1#alias#1", "PX-1#main", "PX-1#spec"]
    main = idx._store["PX-1#main"]
    assert main.metadata["code"] == "PX-1"
    assert main.metadata["kind"] == "main"
    assert main.metadata["name"] == "Sunflower Lecithin"
    assert main.metadata["form"] == "powder"
    assert "Sunflower Lecithin" in main.metadata["snippet"]
    assert len(main.metadata["snippet"]) <= 300


def test_build_records_hash_and_keys_in_mongo():
    idx = InMemoryIndex()
    doc = _doc()
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    saved = mongo.products().find_one({"_id": "PX-1"})
    assert saved["embedded_hash"]
    assert sorted(saved["vector_keys"]) == sorted(idx._store)


def test_rebuild_deletes_stale_alias_vectors():
    idx = InMemoryIndex()
    doc = _doc()
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    slim = mongo.products().find_one({"_id": "PX-1"})
    slim["aliases"] = ["PL5"]
    pe.build_from_doc(slim, embed_fn=_fake_embed, index=idx)
    assert "PX-1#alias#1" not in idx._store
    assert "PX-1#alias#0" in idx._store


def test_status_lifecycle():
    idx = InMemoryIndex()
    doc = _doc()
    mongo.products().insert_one(doc)
    assert pe.status_for_doc(doc) == "not built"
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    built = mongo.products().find_one({"_id": "PX-1"})
    assert pe.status_for_doc(built) == "built"
    built["short_description"] = "changed"
    assert pe.status_for_doc(built) == "stale"


def test_remove_product_deletes_vectors():
    idx = InMemoryIndex()
    doc = _doc()
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    pe.remove_product("PX-1", index=idx)
    assert idx._store == {}


def test_no_spec_vector_when_spec_and_metadata_empty():
    idx = InMemoryIndex()
    doc = _doc(spec=None, metadata={}, aliases=[])
    mongo.products().insert_one(doc)
    pe.build_from_doc(doc, embed_fn=_fake_embed, index=idx)
    assert sorted(idx._store) == ["PX-1#main"]
