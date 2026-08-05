import pytest

from core.embeddings import DIMENSION

from apps.api.db import vectors
from apps.api.db.vectors import InMemoryIndex, S3VectorsIndex, VectorRecord


def _rec(key, emb, **meta):
    return VectorRecord(key=key, embedding=emb, metadata=meta)


def test_in_memory_query_ranks_by_cosine():
    idx = InMemoryIndex()
    idx.put([_rec("A#main", [1.0, 0.0], code="A"), _rec("B#main", [0.0, 1.0], code="B")])
    hits = idx.query([1.0, 0.0], top_k=2)
    assert [h.key for h in hits] == ["A#main", "B#main"]
    assert hits[0].score == pytest.approx(1.0)
    assert hits[0].metadata["code"] == "A"


def test_in_memory_delete_and_top_k():
    idx = InMemoryIndex()
    idx.put([_rec("A#main", [1.0, 0.0]), _rec("B#main", [0.9, 0.1]), _rec("C#main", [0.0, 1.0])])
    idx.delete(["B#main"])
    hits = idx.query([1.0, 0.0], top_k=1)
    assert [h.key for h in hits] == ["A#main"]


class _NotFound(Exception):
    pass


class _Conflict(Exception):
    pass


class _Exceptions:
    NotFoundException = _NotFound
    ConflictException = _Conflict


class FakeS3VectorsClient:
    def __init__(self, index_exists=False):
        self.exceptions = _Exceptions()
        self.calls = []
        self._index_exists = index_exists

    def get_index(self, **kw):
        self.calls.append(("get_index", kw))
        if not self._index_exists:
            raise _NotFound()
        return {}

    def create_vector_bucket(self, **kw):
        self.calls.append(("create_vector_bucket", kw))

    def create_index(self, **kw):
        self.calls.append(("create_index", kw))

    def put_vectors(self, **kw):
        self.calls.append(("put_vectors", kw))

    def query_vectors(self, **kw):
        self.calls.append(("query_vectors", kw))
        return {"vectors": [
            {"key": "A#main", "distance": 0.1, "metadata": {"code": "A", "snippet": "s"}},
        ]}

    def delete_vectors(self, **kw):
        self.calls.append(("delete_vectors", kw))


def test_s3_ensure_creates_bucket_and_index_when_missing():
    client = FakeS3VectorsClient(index_exists=False)
    S3VectorsIndex("vb", "idx", client=client).ensure()
    names = [c[0] for c in client.calls]
    assert names == ["get_index", "create_vector_bucket", "create_index"]
    _, kw = client.calls[-1]
    assert kw["dimension"] == DIMENSION
    assert kw["distanceMetric"] == "cosine"
    assert kw["metadataConfiguration"] == {"nonFilterableMetadataKeys": ["snippet"]}


def test_s3_ensure_noop_when_index_exists():
    client = FakeS3VectorsClient(index_exists=True)
    S3VectorsIndex("vb", "idx", client=client).ensure()
    assert [c[0] for c in client.calls] == ["get_index"]


def test_s3_put_query_delete_shapes():
    client = FakeS3VectorsClient(index_exists=True)
    idx = S3VectorsIndex("vb", "idx", client=client)
    idx.put([_rec("A#main", [0.5, 0.5], code="A")])
    hits = idx.query([1.0, 0.0], top_k=3)
    idx.delete(["A#main"])

    _, put_kw = client.calls[0]
    assert put_kw["vectorBucketName"] == "vb" and put_kw["indexName"] == "idx"
    assert put_kw["vectors"] == [
        {"key": "A#main", "data": {"float32": [0.5, 0.5]}, "metadata": {"code": "A"}}
    ]
    _, q_kw = client.calls[1]
    assert q_kw["topK"] == 3 and q_kw["returnMetadata"] is True and q_kw["returnDistance"] is True
    assert hits[0].key == "A#main"
    assert hits[0].score == pytest.approx(0.9)  # 1 - distance
    _, d_kw = client.calls[2]
    assert d_kw["keys"] == ["A#main"]


def test_delete_with_no_keys_is_noop():
    client = FakeS3VectorsClient(index_exists=True)
    S3VectorsIndex("vb", "idx", client=client).delete([])
    assert client.calls == []


def test_is_available_tracks_settings(monkeypatch):
    from apps.api import settings as settings_mod
    monkeypatch.delenv("S3_VECTOR_BUCKET", raising=False)
    settings_mod.get_settings.cache_clear()
    assert vectors.is_available() is False
    monkeypatch.setenv("S3_VECTOR_BUCKET", "vb")
    settings_mod.get_settings.cache_clear()
    assert vectors.is_available() is True
    settings_mod.get_settings.cache_clear()
