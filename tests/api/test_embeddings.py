import math

import pytest

from core import embeddings


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeResponse:
    def __init__(self, vectors):
        self.embeddings = [_FakeEmbedding(v) for v in vectors]


class _FakeModels:
    def __init__(self, vectors, seen):
        self._vectors = vectors
        self._seen = seen

    def embed_content(self, *, model, contents, config):
        self._seen.update(model=model, contents=list(contents), config=config)
        return _FakeResponse(self._vectors)


class _FakeClient:
    def __init__(self, vectors, seen):
        self.models = _FakeModels(vectors, seen)


@pytest.fixture()
def seen(monkeypatch):
    seen = {}
    monkeypatch.setattr(embeddings, "_client", _FakeClient([[3.0, 4.0]], seen))
    return seen


def test_embed_normalizes_vectors(seen):
    [vec] = embeddings.embed(["hello"])
    assert vec == pytest.approx([0.6, 0.8])
    assert math.isclose(sum(x * x for x in vec), 1.0, rel_tol=1e-6)


def test_document_mode_uses_retrieval_document_task(seen):
    embeddings.embed(["a"], mode="document")
    assert seen["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert seen["config"].output_dimensionality == 1536
    assert seen["model"] == "gemini-embedding-001"


def test_query_mode_uses_retrieval_query_task(seen):
    embeddings.embed(["a"], mode="query")
    assert seen["config"].task_type == "RETRIEVAL_QUERY"


def test_settings_expose_vector_config(monkeypatch):
    from apps.api import settings as settings_mod
    monkeypatch.setenv("S3_VECTOR_BUCKET", "vec-bucket")
    monkeypatch.setenv("SPECS_S3_BUCKET", "spec-bucket")
    settings_mod.get_settings.cache_clear()
    s = settings_mod.get_settings()
    assert s.vector_bucket == "vec-bucket"
    assert s.specs_s3_bucket == "spec-bucket"
    assert s.vector_index == "product-catalog"
    assert s.aws_region == "us-east-1"
    settings_mod.get_settings.cache_clear()
