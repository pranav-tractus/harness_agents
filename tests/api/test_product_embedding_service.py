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
        "org_id": "pym",
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


# ---------------------------------------------------------------------------
# Per-org vector index tests
# ---------------------------------------------------------------------------

from apps.api.db import vectors
from apps.api.services import org_service, product_embedding_service as pes


@pytest.fixture(autouse=True)
def _fake_mongo_orgs(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    org_service.seed_roster()
    yield
    mongo.reset_client()


class _Spy:
    """Records what was written where, standing in for one S3 Vectors index."""

    def __init__(self, name):
        self.name = name
        self.put_keys: list[str] = []
        self.deleted: list[str] = []
        self.ensured = False

    def ensure(self, dimension=3072):
        self.ensured = True

    def put(self, records):
        self.put_keys += [r.key for r in records]

    def delete(self, keys):
        self.deleted += list(keys)


def _embed(texts, mode="document"):
    return [[1.0, 0.0] for _ in texts]


def _product(code="A", org_id="pym"):
    oid = mongo.products().insert_one(
        {"code": code, "org_id": org_id, "short_description": "d", "spec": "s"}
    ).inserted_id
    return mongo.products().find_one({"_id": oid})


def test_build_routes_to_the_orgs_index(monkeypatch):
    made = {}
    monkeypatch.setattr(vectors, "is_available", lambda: True)
    monkeypatch.setattr(vectors, "index_named", lambda n: made.setdefault(n, _Spy(n)))
    doc = _product(org_id="roxxon")
    pes.build_from_doc(doc, embed_fn=_embed)
    assert list(made) == [org_service.vector_index_name("roxxon")]
    assert made[org_service.vector_index_name("roxxon")].ensured is True


def test_build_persists_the_index_name_on_the_product(monkeypatch):
    monkeypatch.setattr(vectors, "is_available", lambda: True)
    monkeypatch.setattr(vectors, "index_named", lambda n: _Spy(n))
    doc = _product(org_id="roxxon")
    pes.build_from_doc(doc, embed_fn=_embed)
    stored = mongo.products().find_one({"_id": doc["_id"]})
    assert stored["vector_index"] == org_service.vector_index_name("roxxon")
    assert stored["vector_keys"]


def test_build_raises_when_the_product_has_no_org():
    doc_id = mongo.products().insert_one({"code": "Z", "short_description": "d"}).inserted_id
    doc = mongo.products().find_one({"_id": doc_id})
    with pytest.raises(org_service.MissingOrg):
        pes.build_from_doc(doc, embed_fn=_embed)


def test_status_goes_stale_when_only_the_org_changed(monkeypatch):
    monkeypatch.setattr(vectors, "is_available", lambda: True)
    monkeypatch.setattr(vectors, "index_named", lambda n: _Spy(n))
    doc = _product(org_id="pym")
    pes.build_from_doc(doc, embed_fn=_embed)
    built = mongo.products().find_one({"_id": doc["_id"]})
    assert pes.status_for_doc(built) == "built"
    assert pes.status_for_doc({**built, "org_id": "roxxon"}) == "stale"


def test_remove_product_deletes_from_the_stored_index(monkeypatch):
    made = {}
    monkeypatch.setattr(vectors, "is_available", lambda: True)
    monkeypatch.setattr(vectors, "index_named", lambda n: made.setdefault(n, _Spy(n)))
    doc = _product(org_id="pym")
    pes.build_from_doc(doc, embed_fn=_embed)
    keys = mongo.products().find_one({"_id": doc["_id"]})["vector_keys"]
    pes.remove_product(doc["_id"])
    assert made[org_service.vector_index_name("pym")].deleted == keys


def test_move_org_deletes_from_old_index_and_puts_into_new(monkeypatch):
    made = {}
    monkeypatch.setattr(vectors, "is_available", lambda: True)
    monkeypatch.setattr(vectors, "index_named", lambda n: made.setdefault(n, _Spy(n)))
    doc = _product(org_id="pym")
    pes.build_from_doc(doc, embed_fn=_embed)
    old_keys = mongo.products().find_one({"_id": doc["_id"]})["vector_keys"]

    moved = pes.move_org(mongo.products().find_one({"_id": doc["_id"]}),
                         "roxxon", embed_fn=_embed)

    old = made[org_service.vector_index_name("pym")]
    new = made[org_service.vector_index_name("roxxon")]
    assert old.deleted == old_keys
    assert new.put_keys == old_keys  # same product id, new index
    assert moved["org_id"] == "roxxon"
    assert moved["vector_index"] == org_service.vector_index_name("roxxon")


def test_move_org_to_the_same_org_is_a_no_op(monkeypatch):
    made = {}
    monkeypatch.setattr(vectors, "is_available", lambda: True)
    monkeypatch.setattr(vectors, "index_named", lambda n: made.setdefault(n, _Spy(n)))
    doc = _product(org_id="pym")
    pes.build_from_doc(doc, embed_fn=_embed)
    made[org_service.vector_index_name("pym")].deleted.clear()
    pes.move_org(mongo.products().find_one({"_id": doc["_id"]}), "pym", embed_fn=_embed)
    assert made[org_service.vector_index_name("pym")].deleted == []


def test_move_org_leaves_the_product_unbuilt_when_the_rebuild_fails(monkeypatch):
    monkeypatch.setattr(vectors, "is_available", lambda: True)
    monkeypatch.setattr(vectors, "index_named", lambda n: _Spy(n))
    doc = _product(org_id="pym")
    pes.build_from_doc(doc, embed_fn=_embed)

    def _boom(texts, mode="document"):
        raise RuntimeError("openai down")

    with pytest.raises(RuntimeError):
        pes.move_org(mongo.products().find_one({"_id": doc["_id"]}), "roxxon", embed_fn=_boom)
    after = mongo.products().find_one({"_id": doc["_id"]})
    assert after["org_id"] == "roxxon"
    assert pes.status_for_doc(after) == "not built"
