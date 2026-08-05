import pytest

from core import embeddings


class _FakeEmbeddingObj:
    def __init__(self, values):
        self.embedding = values


class _FakeResponse:
    def __init__(self, vectors):
        self.data = [_FakeEmbeddingObj(v) for v in vectors]


class _FakeEmbeddings:
    def __init__(self, vectors, seen):
        self._vectors = vectors
        self._seen = seen

    def create(self, *, model, input, dimensions):
        self._seen.update(model=model, input=list(input), dimensions=dimensions)
        return _FakeResponse(self._vectors)


class _FakeClient:
    def __init__(self, vectors, seen):
        self.embeddings = _FakeEmbeddings(vectors, seen)


@pytest.fixture()
def seen(monkeypatch):
    seen = {}
    monkeypatch.setattr(embeddings, "_client", _FakeClient([[0.6, 0.8]], seen))
    return seen


def test_embed_returns_vectors_unmodified(seen):
    [vec] = embeddings.embed(["hello"])
    assert vec == [0.6, 0.8]


def test_embed_uses_model_and_dimension(seen):
    embeddings.embed(["a"])
    assert seen["model"] == "text-embedding-3-large"
    assert seen["dimensions"] == 3072
    assert seen["input"] == ["a"]


def test_mode_does_not_affect_the_request(seen):
    embeddings.embed(["a"], mode="document")
    doc_call = dict(seen)
    embeddings.embed(["a"], mode="query")
    assert doc_call["model"] == seen["model"]
    assert doc_call["dimensions"] == seen["dimensions"]


def test_settings_expose_vector_config(monkeypatch):
    from apps.api import settings as settings_mod
    monkeypatch.setenv("S3_VECTOR_BUCKET", "vec-bucket")
    monkeypatch.setenv("SPECS_S3_BUCKET", "spec-bucket")
    settings_mod.get_settings.cache_clear()
    s = settings_mod.get_settings()
    assert s.vector_bucket == "vec-bucket"
    assert s.specs_s3_bucket == "spec-bucket"
    assert s.vector_index == "product-catalog-openai"
    assert s.aws_region == "us-east-1"
    settings_mod.get_settings.cache_clear()
