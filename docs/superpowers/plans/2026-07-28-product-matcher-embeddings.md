# Product Matcher Embeddings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the FalkorDB product catalog graph with an embedding pipeline: Textract-scanned spec PDFs → LLM-extracted product records in Mongo → gemini-embedding-001 vectors in Amazon S3 Vectors → vector-search-powered product matcher with score/snippet disambiguation questions.

**Architecture:** An offline CLI ingests `prod_specs/*.pdf` (S3 upload → async Textract with TABLES → LLM extraction → Mongo upsert → embed → S3 Vectors). At runtime the matcher extracts mention phrases with a small LLM call, embeds them (query mode), queries top-5 per mention, and feeds candidates (score, snippet, structured metadata) into the existing resolution LLM. The catalog graph, its build endpoints, and its UI are removed; customer/chat graphs stay.

**Tech Stack:** Python/FastAPI, MongoDB (mongomock in tests), boto3 1.43.0 (`textract`, `s3`, `s3vectors`), google-genai (`gemini-embedding-001`), instructor via existing `core.llm_client.call_llm`, React/Vite web app.

**Spec:** `docs/superpowers/specs/2026-07-28-product-matcher-embeddings-design.md`

## Global Constraints

- Embedding model: `gemini-embedding-001`, `output_dimensionality=1536`, vectors L2-normalized in code (Gemini only auto-normalizes at 3072 dims).
- Vector keys: `{code}#main`, `{code}#spec`, `{code}#alias#{n}`. Metadata keys: `code`, `name`, `kind`, flattened product metadata (all filterable), `snippet` (non-filterable, ≤300 chars).
- S3 Vectors index: cosine metric, dimension 1536, region from settings (default `us-east-1`).
- New env vars: `SPECS_S3_BUCKET` (no default), `S3_VECTOR_BUCKET` (no default), `S3_VECTOR_INDEX` (default `product-catalog`), `AWS_REGION` (default `us-east-1`).
- Default extraction model key: `"openai:5.5"` (matches the old `product_graph_service` default).
- Python tests: run `python -m pytest <file> -v` from the repo root. Web tests: `npx vitest run <file>` from `apps/web/`.
- Runtime matcher errors must degrade (fallback substring scan over Mongo), never raise into the chat flow.
- Keep the existing code style: module-level functions, injectable dependencies as keyword args for tests, `mongomock` + `monkeypatch` fixtures.
- Customer/chat/profile graphs and `falkor.customer_graph` are untouched. Only the catalog graph is removed.

---

### Task 1: Settings + `core/embeddings.py`

**Files:**
- Modify: `apps/api/settings.py`
- Create: `core/embeddings.py`
- Test: `tests/api/test_embeddings.py`

**Interfaces:**
- Consumes: `apps.api.settings.get_settings()` (existing).
- Produces: `Settings` gains `specs_s3_bucket: str`, `vector_bucket: str`, `vector_index: str`, `aws_region: str`. `core.embeddings.embed(texts: list[str], *, mode: str = "document") -> list[list[float]]` (1536-dim, unit-norm). `core.embeddings.DIMENSION = 1536`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_embeddings.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.embeddings'`

- [ ] **Step 3: Implement settings + embeddings**

In `apps/api/settings.py`, add four fields to the dataclass and factory:

```python
@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    mongo_db_name: str
    web_origin: str
    falkordb_host: str
    falkordb_port: int
    specs_s3_bucket: str
    vector_bucket: str
    vector_index: str
    aws_region: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        mongodb_uri=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"),
        mongo_db_name=os.environ.get("MONGO_DB_NAME", "chat_sim"),
        web_origin=os.environ.get("WEB_ORIGIN", "http://localhost:5173"),
        falkordb_host=os.environ.get("FALKORDB_HOST", "localhost"),
        falkordb_port=int(os.environ.get("FALKORDB_PORT", "6379")),
        specs_s3_bucket=os.environ.get("SPECS_S3_BUCKET", ""),
        vector_bucket=os.environ.get("S3_VECTOR_BUCKET", ""),
        vector_index=os.environ.get("S3_VECTOR_INDEX", "product-catalog"),
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
    )
```

Create `core/embeddings.py`:

```python
import numpy as np

MODEL = "gemini-embedding-001"
DIMENSION = 1536

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai  # reads GEMINI_API_KEY / GOOGLE_API_KEY

        _client = genai.Client()
    return _client


def _normalize(values: list[float]) -> list[float]:
    arr = np.asarray(values, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    return (arr / norm).tolist() if norm else arr.tolist()


def embed(texts: list[str], *, mode: str = "document") -> list[list[float]]:
    """Embed texts with gemini-embedding-001 at 1536 dims, L2-normalized.

    Gemini only returns unit-norm vectors at 3072 dims; at 1536 we must
    normalize ourselves for cosine distance to be meaningful.
    """
    from google.genai import types

    task = "RETRIEVAL_DOCUMENT" if mode == "document" else "RETRIEVAL_QUERY"
    resp = _get_client().models.embed_content(
        model=MODEL,
        contents=list(texts),
        config=types.EmbedContentConfig(
            task_type=task, output_dimensionality=DIMENSION
        ),
    )
    return [_normalize(e.values) for e in resp.embeddings]
```

Note the fixture monkeypatches `embeddings._client` directly, so `_get_client` is bypassed in tests and no API key is needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_embeddings.py -v`
Expected: 4 PASS

- [ ] **Step 5: Run the full API suite to check nothing broke**

Run: `python -m pytest tests/api -v`
Expected: all PASS (settings change is additive)

- [ ] **Step 6: Commit**

```bash
git add apps/api/settings.py core/embeddings.py tests/api/test_embeddings.py
git commit -m "feat: add vector settings and gemini embedding client"
```

---

### Task 2: `apps/api/db/vectors.py` — vector index abstraction

**Files:**
- Create: `apps/api/db/vectors.py`
- Test: `tests/api/test_vectors.py`

**Interfaces:**
- Consumes: `core.utils.create_boto3_client(name, region)`, `apps.api.settings.get_settings()`, `core.embeddings.DIMENSION`.
- Produces:
  - `VectorRecord(key: str, embedding: list[float], metadata: dict)` (dataclass)
  - `VectorHit(key: str, score: float, metadata: dict)` (dataclass)
  - `InMemoryIndex()` with `.put(records)`, `.query(embedding, top_k=5) -> list[VectorHit]`, `.delete(keys)`
  - `S3VectorsIndex(bucket, index, *, client=None)` with same methods plus `.ensure(dimension=DIMENSION)`
  - `default_index() -> S3VectorsIndex` built from settings
  - `is_available() -> bool` (True when `settings.vector_bucket` is set)

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_vectors.py
import pytest

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
    assert kw["dimension"] == 1536
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_vectors.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError`

- [ ] **Step 3: Implement `apps/api/db/vectors.py`**

```python
from dataclasses import dataclass, field

import numpy as np

from apps.api.settings import get_settings
from core.embeddings import DIMENSION


@dataclass
class VectorRecord:
    key: str
    embedding: list[float]
    metadata: dict = field(default_factory=dict)


@dataclass
class VectorHit:
    key: str
    score: float
    metadata: dict = field(default_factory=dict)


class InMemoryIndex:
    """Numpy cosine index for tests and offline dev."""

    def __init__(self):
        self._store: dict[str, VectorRecord] = {}

    def ensure(self, dimension: int = DIMENSION) -> None:
        pass

    def put(self, records: list[VectorRecord]) -> None:
        for r in records:
            self._store[r.key] = r

    def delete(self, keys: list[str]) -> None:
        for k in keys:
            self._store.pop(k, None)

    def query(self, embedding: list[float], top_k: int = 5) -> list[VectorHit]:
        q = np.asarray(embedding, dtype=np.float32)
        hits = []
        for r in self._store.values():
            v = np.asarray(r.embedding, dtype=np.float32)
            denom = float(np.linalg.norm(q) * np.linalg.norm(v))
            score = float(q @ v) / denom if denom else 0.0
            hits.append(VectorHit(key=r.key, score=score, metadata=dict(r.metadata)))
        return sorted(hits, key=lambda h: -h.score)[:top_k]


class S3VectorsIndex:
    def __init__(self, bucket: str, index: str, *, client=None):
        self._bucket = bucket
        self._index = index
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from core.utils import create_boto3_client

            self._client = create_boto3_client("s3vectors", region=get_settings().aws_region)
        return self._client

    def ensure(self, dimension: int = DIMENSION) -> None:
        try:
            self.client.get_index(vectorBucketName=self._bucket, indexName=self._index)
            return
        except self.client.exceptions.NotFoundException:
            pass
        try:
            self.client.create_vector_bucket(vectorBucketName=self._bucket)
        except self.client.exceptions.ConflictException:
            pass
        self.client.create_index(
            vectorBucketName=self._bucket,
            indexName=self._index,
            dataType="float32",
            dimension=dimension,
            distanceMetric="cosine",
            metadataConfiguration={"nonFilterableMetadataKeys": ["snippet"]},
        )

    def put(self, records: list[VectorRecord]) -> None:
        self.client.put_vectors(
            vectorBucketName=self._bucket,
            indexName=self._index,
            vectors=[
                {
                    "key": r.key,
                    "data": {"float32": [float(x) for x in r.embedding]},
                    "metadata": r.metadata,
                }
                for r in records
            ],
        )

    def delete(self, keys: list[str]) -> None:
        if not keys:
            return
        self.client.delete_vectors(
            vectorBucketName=self._bucket, indexName=self._index, keys=list(keys)
        )

    def query(self, embedding: list[float], top_k: int = 5) -> list[VectorHit]:
        resp = self.client.query_vectors(
            vectorBucketName=self._bucket,
            indexName=self._index,
            topK=top_k,
            queryVector={"float32": [float(x) for x in embedding]},
            returnMetadata=True,
            returnDistance=True,
        )
        return [
            VectorHit(
                key=v["key"],
                score=1.0 - float(v.get("distance") or 0.0),
                metadata=v.get("metadata") or {},
            )
            for v in resp.get("vectors", [])
        ]


def default_index() -> S3VectorsIndex:
    s = get_settings()
    return S3VectorsIndex(s.vector_bucket, s.vector_index)


def is_available() -> bool:
    return bool(get_settings().vector_bucket)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_vectors.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/db/vectors.py tests/api/test_vectors.py
git commit -m "feat: add S3 Vectors index wrapper with in-memory fallback"
```

---

### Task 3: `product_embedding_service` — build / status / remove

**Files:**
- Create: `apps/api/services/product_embedding_service.py`
- Test: `tests/api/test_product_embedding_service.py`

**Interfaces:**
- Consumes: `apps.api.db.vectors` (`VectorRecord`, `default_index`, `is_available`), `core.embeddings.embed`, `apps.api.db.mongo.products()`.
- Produces (mirrors the old `product_graph_service` names so the router swap in Task 6 is mechanical):
  - `build_from_doc(doc: dict, *, embed_fn=None, index=None) -> None`
  - `status_for_doc(doc: dict) -> str` — `"built" | "stale" | "not built"`
  - `remove_product(code: str, *, index=None) -> None`
  - `_payloads(doc) -> list[tuple[str, str, dict]]` — `(key, text, metadata)`; used by the ingest tests too.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_product_embedding_service.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_product_embedding_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

```python
# apps/api/services/product_embedding_service.py
import hashlib
import json

from apps.api.db import mongo, vectors
from core import embeddings

_SNIPPET_LEN = 300


def _meta_text(metadata: dict) -> str:
    return " · ".join(f"{k}: {v}" for k, v in sorted((metadata or {}).items()))


def _render_main(doc: dict) -> str:
    parts = [
        doc.get("name") or doc["code"],
        doc.get("short_description") or doc.get("description") or "",
        doc.get("long_description") or "",
        _meta_text(doc.get("metadata") or {}),
    ]
    return "\n".join(p for p in parts if p)


def _render_spec(doc: dict) -> str:
    parts = [doc.get("spec") or "", _meta_text(doc.get("metadata") or {})]
    return "\n".join(p for p in parts if p)


def _payloads(doc: dict) -> list[tuple[str, str, dict]]:
    """(key, text-to-embed, metadata) for every vector this product owns."""
    code = doc["code"]
    flat = {k: str(v) for k, v in (doc.get("metadata") or {}).items()}
    base = {"code": code, "name": doc.get("name") or code, **flat}
    out = [(f"{code}#main", _render_main(doc), {**base, "kind": "main"})]
    spec_text = _render_spec(doc)
    if spec_text:
        out.append((f"{code}#spec", spec_text, {**base, "kind": "spec"}))
    aliases = [a for a in dict.fromkeys(doc.get("aliases") or []) if a]
    for i, alias in enumerate(aliases):
        text = f"{alias} — {doc.get('name') or code}"
        out.append((f"{code}#alias#{i}", text, {**base, "kind": "alias"}))
    return out


def _hash(payloads: list[tuple[str, str, dict]]) -> str:
    blob = json.dumps([(k, t) for k, t, _ in payloads], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def build_from_doc(doc: dict, *, embed_fn=None, index=None) -> None:
    embed_fn = embed_fn or embeddings.embed
    index = index or vectors.default_index()
    payloads = _payloads(doc)
    vecs = embed_fn([text for _, text, _ in payloads], mode="document")
    records = [
        vectors.VectorRecord(
            key=key, embedding=vec, metadata={**meta, "snippet": text[:_SNIPPET_LEN]}
        )
        for (key, text, meta), vec in zip(payloads, vecs)
    ]
    new_keys = [r.key for r in records]
    stale = [k for k in (doc.get("vector_keys") or []) if k not in set(new_keys)]
    if stale:
        index.delete(stale)
    index.put(records)
    mongo.products().update_one(
        {"_id": doc["code"]},
        {"$set": {"embedded_hash": _hash(payloads), "vector_keys": new_keys}},
    )


def status_for_doc(doc: dict) -> str:
    if not doc.get("embedded_hash"):
        return "not built"
    return "built" if doc["embedded_hash"] == _hash(_payloads(doc)) else "stale"


def remove_product(code: str, *, index=None) -> None:
    doc = mongo.products().find_one({"_id": code}) or {}
    keys = doc.get("vector_keys") or []
    if not keys:
        return
    if index is None:
        if not vectors.is_available():
            return
        index = vectors.default_index()
    index.delete(keys)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_product_embedding_service.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/product_embedding_service.py tests/api/test_product_embedding_service.py
git commit -m "feat: add product embedding build/status/remove service"
```

---

### Task 4: Matcher rewrite — mention extraction + vector candidates

**Files:**
- Modify: `apps/api/services/product_matcher_service.py`
- Rewrite: `tests/api/test_product_matcher_service.py`

**Interfaces:**
- Consumes: `apps.api.db.vectors` (`is_available`, `default_index`), `core.embeddings.embed`, `apps.api.db.mongo.products()`, `apps.api.db.falkor` (history pool, unchanged).
- Produces:
  - `ProductCandidate` gains `snippet: str = ""` and `metadata: dict[str, str] = {}`.
  - `MentionList(BaseModel)` with `mentions: list[str]`.
  - `resolve_products(customer_id, window, model_key, *, mention_fn=None, candidate_fn=None, history_fn=None, llm=None) -> ProductMatchResult` — **signature change**: `catalog_pool_fn(text)` is replaced by `candidate_fn(mentions: list[str])` and the new `mention_fn(text) -> list[str]`.
  - `ProductMatch`, `ProductMatchResult`, `.resolved()`, `.unresolved()`, `_guard` unchanged.
  - Task 5/6 rely on `ProductCandidate.snippet` and `.score` for question rendering.

- [ ] **Step 1: Rewrite the test file (failing)**

Replace `tests/api/test_product_matcher_service.py` entirely:

```python
import mongomock
import pytest

from apps.api.db import mongo
from apps.api.services import product_matcher_service as pm
from apps.api.services.product_matcher_service import (
    MentionList, ProductCandidate, ProductMatch, ProductMatchResult)


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    yield
    mongo.reset_client()


def _window(*bodies):
    return [{"seq": i, "role": "seller", "body": b} for i, b in enumerate(bodies)]


def _mentions(*ms):
    return lambda text: list(ms)


def _cands(*cands):
    return lambda mentions: list(cands)


def _hist(*codes):
    return lambda cid: [ProductCandidate(code=c, name=c, score=0.0) for c in codes]


def _cand(code, score=0.9, **kw):
    return ProductCandidate(code=code, name=kw.pop("name", code), score=score, **kw)


def test_confident_match_passes_through():
    result = ProductMatchResult(matches=[ProductMatch(
        mention="choline", status="confident", resolved_code="TG-BPPC",
        canonical_name="Bypass Choline", confidence=0.95)])
    out = pm.resolve_products("dummy-01", _window("need choline"), "m",
                              mention_fn=_mentions("choline"),
                              candidate_fn=_cands(_cand("TG-BPPC")),
                              history_fn=_hist(), llm=lambda *a, **k: result)
    assert out.resolved()[0].resolved_code == "TG-BPPC"
    assert out.unresolved() == []


def test_guard_downgrades_hallucinated_code_to_no_match():
    result = ProductMatchResult(matches=[ProductMatch(
        mention="choline", status="confident", resolved_code="NOT-IN-POOL",
        canonical_name="???", confidence=0.99)])
    out = pm.resolve_products("dummy-01", _window("need choline"), "m",
                              mention_fn=_mentions("choline"),
                              candidate_fn=_cands(_cand("TG-BPPC")),
                              history_fn=_hist(), llm=lambda *a, **k: result)
    assert out.matches[0].status == "no_match"
    assert out.unresolved()


def test_empty_mentions_short_circuits_llm_and_candidates():
    called = {"llm": 0, "cands": 0}

    def _fake_llm(*a, **k):
        called["llm"] += 1
        return ProductMatchResult(matches=[])

    def _fake_cands(mentions):
        called["cands"] += 1
        return []

    out = pm.resolve_products("dummy-01", _window("hello there"), "m",
                              mention_fn=_mentions(), candidate_fn=_fake_cands,
                              history_fn=_hist(), llm=_fake_llm)
    assert out.matches == []
    assert called == {"llm": 0, "cands": 0}


def test_mentions_without_candidates_return_no_match_questions():
    def _fake_llm(*a, **k):
        raise AssertionError("llm must not be called with an empty pool")

    out = pm.resolve_products("dummy-01", _window("need unobtainium"), "m",
                              mention_fn=_mentions("unobtainium"),
                              candidate_fn=_cands(), history_fn=_hist(), llm=_fake_llm)
    assert len(out.matches) == 1
    assert out.matches[0].status == "no_match"
    assert "unobtainium" in out.matches[0].question


def test_prompt_carries_scores_metadata_snippets_and_history():
    seen = {}

    def _fake_llm(prompt, schema, model_key, system_prompt=None):
        seen["prompt"] = prompt
        return ProductMatchResult(matches=[])

    pm.resolve_products(
        "dummy-01", _window("the usual lecithin"), "m",
        mention_fn=_mentions("lecithin"),
        candidate_fn=_cands(_cand("GIIOFINE-UP-SF", score=0.87,
                                  name="Sunflower Lecithin Powder",
                                  snippet="de-oiled sunflower lecithin",
                                  metadata={"form": "powder"})),
        history_fn=_hist("TG-BPPC"), llm=_fake_llm)
    p = seen["prompt"]
    assert "similarity 0.87" in p
    assert "form: powder" in p
    assert "de-oiled sunflower lecithin" in p
    assert "TG-BPPC" in p


def test_default_mention_fn_uses_llm_with_mention_schema():
    def _fake_llm(prompt, schema, model_key, system_prompt=None):
        if schema is MentionList:
            return MentionList(mentions=["lecithin"])
        return ProductMatchResult(matches=[])

    out = pm.resolve_products("dummy-01", _window("send lecithin"), "m",
                              candidate_fn=_cands(_cand("A")),
                              history_fn=_hist(), llm=_fake_llm)
    assert out.matches == []  # resolution result from fake; wiring exercised


def test_dedup_keeps_best_score_and_fills_snippet():
    merged = pm._dedup([
        ProductCandidate(code="A", name="", score=0.9, snippet="best"),
        ProductCandidate(code="A", name="Alpha", score=0.5, snippet="worse",
                         metadata={"form": "powder"}),
    ])
    assert len(merged) == 1
    c = merged[0]
    assert c.score == 0.9
    assert c.snippet == "best"
    assert c.name == "Alpha"          # filled from the other candidate
    assert c.metadata == {"form": "powder"}


def test_fallback_candidates_substring_scan(monkeypatch):
    mongo.products().insert_one({
        "_id": "PL5", "code": "PL5", "name": "Feed Lecithin",
        "aliases": ["GIIOFEED PL5"], "metadata": {"form": "liquid"}})
    monkeypatch.setattr(pm.vectors, "is_available", lambda: False)
    cands = pm._vector_candidates(["need the giiofeed pl5 drums"])
    assert [c.code for c in cands] == ["PL5"]
    assert cands[0].metadata == {"form": "liquid"}


def test_vector_error_falls_back(monkeypatch):
    mongo.products().insert_one({"_id": "PL5", "code": "PL5", "name": "Feed Lecithin"})
    monkeypatch.setattr(pm.vectors, "is_available", lambda: True)

    def _boom(*a, **k):
        raise RuntimeError("aws down")

    monkeypatch.setattr(pm.embeddings, "embed", _boom)
    cands = pm._vector_candidates(["pl5 please"])
    assert [c.code for c in cands] == ["PL5"]


def test_system_prompt_carries_hard_rules():
    assert "Only ever use codes from the provided pool" in pm._SYSTEM
    assert "Empty is a valid answer" in pm._SYSTEM
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_product_matcher_service.py -v`
Expected: FAIL (`MentionList` import error)

- [ ] **Step 3: Rewrite the matcher**

In `apps/api/services/product_matcher_service.py`:

Replace the imports and `ProductCandidate`, add `MentionList` and logging:

```python
import logging

from pydantic import BaseModel, Field

from apps.api.db import falkor, mongo, vectors
from core import embeddings
from core.llm_client import call_llm

logger = logging.getLogger(__name__)


class ProductCandidate(BaseModel):
    code: str
    name: str = ""
    score: float = 0.0
    snippet: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class MentionList(BaseModel):
    mentions: list[str] = Field(default_factory=list)
```

(`ProductMatch` / `ProductMatchResult` stay exactly as they are.)

Append to `_SYSTEM` (keep existing rules 1–5 verbatim, add):

```python
    "\n6. **Candidates come from vector search.** `similarity` is the cosine "
    "similarity between the mention and the product's spec text; `matched` "
    "shows the text that matched. Metadata key/values are authoritative — "
    "use them to apply attribute constraints from the chat (non-GMO, "
    "packing, form, origin) exactly, and cite the differing attribute in "
    "clarifying questions."
```

Add mention extraction:

```python
_MENTION_SYSTEM = (
    "You list distinct product mentions from a B2B commodity sales chat.\n"
    "1. Empty is a valid answer — if no product is being discussed, return "
    "an empty list. Never invent a mention.\n"
    "2. Keep attribute qualifiers attached to the mention (e.g. 'non-GMO "
    "soy lecithin in 25kg bags', not 'soy lecithin').\n"
    "3. One entry per distinct product; do not split one product's "
    "qualifiers into separate mentions.\n"
    "4. Copy the chat's wording; do not normalize or expand abbreviations."
)


def _extract_mentions(text: str, model_key, llm) -> list[str]:
    result = llm(
        "## Conversation\n" + text + "\n\n---\n\n"
        "List the distinct product mentions. Return the MentionList as "
        "valid JSON conforming to the schema. No text before or after "
        "the JSON.",
        MentionList,
        model_key,
        system_prompt=_MENTION_SYSTEM,
    )
    return [m.strip() for m in result.mentions if m and m.strip()]
```

Replace `_catalog_pool` with vector candidates + fallback:

```python
def _fallback_candidates(mentions: list[str]) -> list[ProductCandidate]:
    """Substring scan over Mongo products; keeps the app working offline."""
    lows = [m.lower() for m in mentions]
    out = []
    for doc in mongo.products().find():
        terms = [doc.get("code") or "", doc.get("name") or ""]
        terms += list(doc.get("aliases") or [])
        if any(t and (t.lower() in m or m in t.lower()) for t in terms for m in lows):
            out.append(ProductCandidate(
                code=doc["code"], name=doc.get("name") or "",
                metadata={k: str(v) for k, v in (doc.get("metadata") or {}).items()},
            ))
    return out


def _vector_candidates(mentions: list[str]) -> list[ProductCandidate]:
    if not vectors.is_available():
        return _fallback_candidates(mentions)
    try:
        index = vectors.default_index()
        out = []
        for emb in embeddings.embed(mentions, mode="query"):
            for hit in index.query(emb, top_k=5):
                md = dict(hit.metadata)
                code = md.pop("code", hit.key.split("#")[0])
                name = md.pop("name", "")
                snippet = md.pop("snippet", "")
                md.pop("kind", None)
                out.append(ProductCandidate(
                    code=code, name=name, score=hit.score, snippet=snippet,
                    metadata={k: str(v) for k, v in md.items()},
                ))
        return out
    except Exception:
        logger.warning("vector search failed; using substring fallback", exc_info=True)
        return _fallback_candidates(mentions)
```

Replace `_dedup` (best score wins, gaps filled from the loser):

```python
def _dedup(cands: list[ProductCandidate]) -> list[ProductCandidate]:
    by_code: dict[str, ProductCandidate] = {}
    for c in cands:
        cur = by_code.get(c.code)
        if cur is None:
            by_code[c.code] = c
            continue
        best, other = (c, cur) if c.score > cur.score else (cur, c)
        by_code[c.code] = ProductCandidate(
            code=best.code,
            name=best.name or other.name,
            score=best.score,
            snippet=best.snippet or other.snippet,
            metadata=best.metadata or other.metadata,
        )
    return list(by_code.values())
```

Update `_history_pool` score to `0.0` (real similarities must outrank history markers in `_dedup`):

```python
    return [ProductCandidate(code=r[0], name=r[0], score=0.0) for r in rows if r[0]]
```

Replace `_prompt`'s candidate lines:

```python
def _candidate_lines(pool: list[ProductCandidate]) -> str:
    lines = []
    for c in sorted(pool, key=lambda c: -c.score):
        line = f"- {c.code}: {c.name}"
        if c.score:
            line += f" (similarity {c.score:.2f})"
        if c.metadata:
            line += "\n  {" + ", ".join(
                f"{k}: {v}" for k, v in sorted(c.metadata.items())) + "}"
        if c.snippet:
            line += f'\n  matched: "{c.snippet}"'
        lines.append(line)
    return "\n".join(lines)


def _prompt(text: str, pool: list[ProductCandidate], history_codes: list[str]) -> str:
    return (
        "## Candidate SKUs\n"
        + _candidate_lines(pool)
        + "\n\n## Previously ordered by this customer\n"
        + (", ".join(history_codes) if history_codes else "(none)")
        + "\n\n## Conversation\n"
        + text
        + "\n\n---\n\n"
        "Resolve each distinct product mention to a candidate SKU. "
        "Return the ProductMatchResult as valid JSON conforming to the "
        "schema. No text before or after the JSON."
    )
```

Replace `resolve_products`:

```python
def resolve_products(
    customer_id, window, model_key, *,
    mention_fn=None, candidate_fn=None, history_fn=None, llm=None,
) -> ProductMatchResult:
    llm = llm or call_llm
    mention_fn = mention_fn or (lambda text: _extract_mentions(text, model_key, llm))
    candidate_fn = candidate_fn or _vector_candidates
    history_fn = history_fn or _history_pool
    text = _window_text(window)
    mentions = mention_fn(text)
    if not mentions:
        return ProductMatchResult(matches=[])
    history = history_fn(customer_id)
    pool = _dedup(candidate_fn(mentions) + history)
    if not pool:
        return ProductMatchResult(matches=[
            ProductMatch(
                mention=m, status="no_match",
                question=f'I couldn\'t match "{m}" to the catalog. Which product is it?',
            )
            for m in mentions
        ])
    result = llm(
        _prompt(text, pool, [c.code for c in history]),
        ProductMatchResult,
        model_key,
        system_prompt=_SYSTEM,
    )
    return _guard(result, {c.code for c in pool})
```

Delete the old `_catalog_pool`. `_window_text`, `_guard`, `_history_pool` (except the score change) stay.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_product_matcher_service.py -v`
Expected: 11 PASS

- [ ] **Step 5: Run the agent-invoke suite (matcher consumers)**

Run: `python -m pytest tests/api/test_agent_matcher_invoke.py tests/api -v`
Expected: all PASS (`agent_service.invoke` injects `matcher_fn`, so the signature change is invisible to it)

- [ ] **Step 6: Commit**

```bash
git add apps/api/services/product_matcher_service.py tests/api/test_product_matcher_service.py
git commit -m "feat: rewrite product matcher on mention extraction + vector search"
```

---

### Task 5: Disambiguation questions show score + snippet

**Files:**
- Modify: `apps/api/services/agent_service.py` (`_match_question`, around line 193)
- Test: `tests/api/test_agent_matcher_invoke.py` (append)

**Interfaces:**
- Consumes: `ProductCandidate.score` / `.snippet` from Task 4.
- Produces: `_match_question(unresolved) -> str` rendering `Name (CODE, 0.87 — "snippet")` per candidate. No signature change.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_agent_matcher_invoke.py`:

```python
def test_match_question_renders_scores_and_snippets():
    from apps.api.services.agent_service import _match_question
    from apps.api.services.product_matcher_service import ProductCandidate, ProductMatch
    m = ProductMatch(mention="lecithin", status="ambiguous", candidates=[
        ProductCandidate(code="GIIOFINE-UP-SF", name="Sunflower Lecithin Powder",
                         score=0.87, snippet="de-oiled sunflower lecithin powder"),
        ProductCandidate(code="GIIOFINE_L_SF", name="Sunflower Lecithin Liquid",
                         score=0.84),
    ])
    q = _match_question([m])
    assert "(GIIOFINE-UP-SF, 0.87" in q
    assert 'de-oiled sunflower lecithin powder' in q
    assert "(GIIOFINE_L_SF, 0.84)" in q


def test_match_question_without_scores_stays_clean():
    from apps.api.services.agent_service import _match_question
    from apps.api.services.product_matcher_service import ProductCandidate, ProductMatch
    m = ProductMatch(mention="x", status="ambiguous", candidates=[
        ProductCandidate(code="A", name="Alpha")])
    q = _match_question([m])
    assert "(A)" in q and "0.00" not in q
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_agent_matcher_invoke.py -v`
Expected: the two new tests FAIL (no score/snippet in output)

- [ ] **Step 3: Implement rendering**

In `apps/api/services/agent_service.py`, replace `_match_question` with:

```python
def _cand_label(c) -> str:
    label = f"{c.name} ({c.code}"
    if c.score:
        label += f", {c.score:.2f}"
    label += ")"
    if c.snippet:
        label += f' — "{c.snippet[:100]}"'
    return label


def _match_question(unresolved) -> str:
    parts = ["I need to pin down the product before drafting:"]
    for m in unresolved:
        if m.question:
            parts.append(f"- {m.question}")
            if m.candidates:
                for c in m.candidates:
                    parts.append(f"  - {_cand_label(c)}")
        elif m.candidates:
            opts = " or ".join(_cand_label(c) for c in m.candidates)
            parts.append(f'- For "{m.mention}": did you mean {opts}?')
        else:
            parts.append(
                f'- I couldn\'t match "{m.mention}" to the catalog. Which product is it?'
            )
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_agent_matcher_invoke.py -v`
Expected: all PASS (existing tests assert on substrings like "lecithin" and still hold)

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/agent_service.py tests/api/test_agent_matcher_invoke.py
git commit -m "feat: show similarity scores and snippets in product questions"
```

---

### Task 6: Products router + ProductsPage use the embedding service

**Files:**
- Modify: `apps/api/routers/products.py`
- Modify: `apps/web/src/pages/ProductsPage.tsx` (lines ~163–228)
- Modify: `tests/api/test_product_build_endpoint.py`

**Interfaces:**
- Consumes: `product_embedding_service.build_from_doc / status_for_doc / remove_product` (Task 3 — names intentionally identical to the old graph service).
- Produces: `POST /api/products/{id}/build`, `POST /api/products/build-all`, and `build_status` now mean *embedding* build. No API shape change — `ProductOut` is untouched.

- [ ] **Step 1: Update the endpoint test (failing)**

In `tests/api/test_product_build_endpoint.py`, replace the graph-service monkeypatches:

```python
import mongomock
import pytest
from fastapi.testclient import TestClient

from apps.api import seed
from apps.api.db import mongo
from apps.api.services import product_embedding_service


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    seed.seed_all()
    calls = []
    monkeypatch.setattr(product_embedding_service, "build_from_doc",
                        lambda doc, **k: calls.append(doc["code"]))
    monkeypatch.setattr(product_embedding_service, "status_for_doc",
                        lambda doc: "not built")
    from apps.api.main import create_app
    with TestClient(create_app()) as c:
        c.calls = calls
        yield c


def test_build_single(client):
    r = client.post("/api/products/TG-BPPC/build")
    assert r.status_code == 200
    assert "TG-BPPC" in client.calls


def test_create_does_not_autosync(client):
    client.post("/api/products", json={"code": "NEW-1", "short_description": "x", "spec": None})
    assert "NEW-1" not in client.calls   # build only happens on explicit request
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/api/test_product_build_endpoint.py -v`
Expected: FAIL — the router still calls `product_graph_service`, so `calls` stays empty (and the real graph service would need Falkor)

- [ ] **Step 3: Swap the router**

In `apps/api/routers/products.py`: change the import and the five call sites —

```python
from apps.api.services import product_embedding_service
```

- `_out(...)`: `build_status=product_embedding_service.status_for_doc(doc)`
- `build_all()` and `build_product()`: `product_embedding_service.build_from_doc(doc)`
- `delete_product()`: `product_embedding_service.remove_product(product_id)` (keep the existing try/except + warning log)

Remove the now-unused `product_graph_service` import.

- [ ] **Step 4: Run API tests**

Run: `python -m pytest tests/api/test_product_build_endpoint.py tests/api/test_products_api.py -v`
Expected: PASS. In `tests/api/test_products_api.py`, `status_for_doc` now runs for real against mongomock docs with no `embedded_hash` → returns `"not built"` with no Falkor dependency; update the stale fixture comment (`# FalkorDB is not available under mongomock...`) to `# No embedded_hash on fresh docs; status_for_doc returns "not built"`.

- [ ] **Step 5: Relabel the ProductsPage button and column**

In `apps/web/src/pages/ProductsPage.tsx`:
- Rename `buildGraph` → `buildEmbeddings` (and its call site `onClick={() => buildEmbeddings(product)}`).
- Toast: `"Failed to build embeddings"` instead of `"Failed to build graph"`.
- Column header `<TableHead>Graph</TableHead>` → `<TableHead>Embeddings</TableHead>`.
- Button label ternary: `"Build Graph"` → `"Build Embeddings"` (keep `"Rebuild"` / `"Building…"`).

- [ ] **Step 6: Web build check**

Run: `cd apps/web && npx tsc -b && npx vitest run`
Expected: compile clean, tests PASS

- [ ] **Step 7: Commit**

```bash
git add apps/api/routers/products.py tests/api/test_product_build_endpoint.py tests/api/test_products_api.py apps/web/src/pages/ProductsPage.tsx
git commit -m "feat: product build endpoints drive embeddings instead of graphs"
```

---

### Task 7: Textract extraction — `textract_text` + `render_blocks`

**Files:**
- Create: `apps/api/services/spec_ingest_service.py` (first half)
- Test: `tests/api/test_spec_ingest_textract.py`

**Interfaces:**
- Consumes: `core.utils.create_boto3_client`, `apps.api.settings.get_settings()`.
- Produces:
  - `render_blocks(blocks: list[dict]) -> str` — LINE text, then `## Tables` with ` | `-joined grid rows.
  - `textract_text(bucket: str, key: str, *, client=None, poll_interval=2.0, timeout=300) -> str` — async `start_document_analysis` (TABLES) + polling + pagination.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_spec_ingest_textract.py
import pytest

from apps.api.services import spec_ingest_service as si


def _line(text):
    return {"Id": f"line-{text}", "BlockType": "LINE", "Text": text}


def _word(wid, text):
    return {"Id": wid, "BlockType": "WORD", "Text": text}


def _cell(cid, row, col, word_ids):
    return {"Id": cid, "BlockType": "CELL", "RowIndex": row, "ColumnIndex": col,
            "Relationships": [{"Type": "CHILD", "Ids": word_ids}]}


def _table(cell_ids):
    return {"Id": "t1", "BlockType": "TABLE",
            "Relationships": [{"Type": "CHILD", "Ids": cell_ids}]}


def test_render_blocks_lines_and_table_grid():
    blocks = [
        _line("Sunflower Lecithin Powder"),
        _line("Product Data Sheet"),
        _table(["c1", "c2", "c3", "c4"]),
        _cell("c1", 1, 1, ["w1"]), _cell("c2", 1, 2, ["w2"]),
        _cell("c3", 2, 1, ["w3"]), _cell("c4", 2, 2, ["w4", "w5"]),
        _word("w1", "Moisture"), _word("w2", "≤2%"),
        _word("w3", "Acetone"), _word("w4", "insoluble"), _word("w5", "≥95%"),
    ]
    text = si.render_blocks(blocks)
    assert "Sunflower Lecithin Powder\nProduct Data Sheet" in text
    assert "## Tables" in text
    assert "Moisture | ≤2%" in text
    assert "Acetone | insoluble ≥95%" in text


def test_render_blocks_without_tables_has_no_tables_header():
    assert "## Tables" not in si.render_blocks([_line("hello")])


class FakeTextract:
    def __init__(self):
        self.pages = [
            {"JobStatus": "IN_PROGRESS"},
            {"JobStatus": "SUCCEEDED", "Blocks": [_line("page one")], "NextToken": "tok"},
            {"JobStatus": "SUCCEEDED", "Blocks": [_line("page two")]},
        ]
        self.start_kwargs = None
        self.get_calls = []

    def start_document_analysis(self, **kw):
        self.start_kwargs = kw
        return {"JobId": "job-1"}

    def get_document_analysis(self, **kw):
        self.get_calls.append(kw)
        return self.pages.pop(0)


def test_textract_text_polls_and_paginates():
    client = FakeTextract()
    text = si.textract_text("bkt", "specs/x.pdf", client=client, poll_interval=0)
    assert "page one" in text and "page two" in text
    assert client.start_kwargs == {
        "DocumentLocation": {"S3Object": {"Bucket": "bkt", "Name": "specs/x.pdf"}},
        "FeatureTypes": ["TABLES"],
    }
    assert client.get_calls[-1]["NextToken"] == "tok"


def test_textract_text_raises_on_failed_job():
    class FailTextract(FakeTextract):
        def __init__(self):
            self.pages = [{"JobStatus": "FAILED", "StatusMessage": "bad pdf"}]
            self.get_calls = []

    with pytest.raises(RuntimeError, match="bad pdf"):
        si.textract_text("bkt", "specs/x.pdf", client=FailTextract(), poll_interval=0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_spec_ingest_textract.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the Textract half of the service**

Create `apps/api/services/spec_ingest_service.py`:

```python
import time

from apps.api.settings import get_settings


def render_blocks(blocks: list[dict]) -> str:
    """Textract blocks → plain text: LINEs in order, then tables as grids."""
    by_id = {b["Id"]: b for b in blocks}
    lines = [b["Text"] for b in blocks if b["BlockType"] == "LINE" and b.get("Text")]
    tables = []
    for table in (b for b in blocks if b["BlockType"] == "TABLE"):
        cells: dict[tuple[int, int], str] = {}
        for rel in table.get("Relationships", []):
            if rel["Type"] != "CHILD":
                continue
            for cid in rel["Ids"]:
                cell = by_id.get(cid)
                if not cell or cell["BlockType"] != "CELL":
                    continue
                words = []
                for crel in cell.get("Relationships", []):
                    if crel["Type"] != "CHILD":
                        continue
                    for wid in crel["Ids"]:
                        w = by_id.get(wid)
                        if w and w["BlockType"] == "WORD":
                            words.append(w["Text"])
                        elif w and w["BlockType"] == "SELECTION_ELEMENT":
                            words.append(
                                "[x]" if w.get("SelectionStatus") == "SELECTED" else "[ ]"
                            )
                cells[(cell["RowIndex"], cell["ColumnIndex"])] = " ".join(words)
        if not cells:
            continue
        n_rows = max(r for r, _ in cells)
        n_cols = max(c for _, c in cells)
        tables.append("\n".join(
            " | ".join(cells.get((r, c), "") for c in range(1, n_cols + 1)).rstrip()
            for r in range(1, n_rows + 1)
        ))
    out = "\n".join(lines)
    if tables:
        out += "\n\n## Tables\n" + "\n\n".join(tables)
    return out


def textract_text(
    bucket: str, key: str, *, client=None, poll_interval: float = 2.0, timeout: float = 300
) -> str:
    if client is None:
        from core.utils import create_boto3_client

        client = create_boto3_client("textract", region=get_settings().aws_region)
    job_id = client.start_document_analysis(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
        FeatureTypes=["TABLES"],
    )["JobId"]
    deadline = time.time() + timeout
    while True:
        resp = client.get_document_analysis(JobId=job_id, MaxResults=1000)
        status = resp["JobStatus"]
        if status == "SUCCEEDED":
            break
        if status == "FAILED":
            raise RuntimeError(
                f"Textract job failed for {key}: {resp.get('StatusMessage', '')}"
            )
        if time.time() > deadline:
            raise TimeoutError(f"Textract job timed out for {key}")
        time.sleep(poll_interval)
    blocks = list(resp.get("Blocks", []))
    while resp.get("NextToken"):
        resp = client.get_document_analysis(
            JobId=job_id, MaxResults=1000, NextToken=resp["NextToken"]
        )
        blocks.extend(resp.get("Blocks", []))
    return render_blocks(blocks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_spec_ingest_textract.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/spec_ingest_service.py tests/api/test_spec_ingest_textract.py
git commit -m "feat: add Textract text extraction with table rendering"
```

---

### Task 8: Spec extraction, upsert, and `ingest_pdf` / `ingest_folder`

**Files:**
- Modify: `apps/api/services/spec_ingest_service.py` (second half)
- Test: `tests/api/test_spec_ingest_service.py`

**Interfaces:**
- Consumes: `textract_text` (Task 7), `core.llm_client.call_llm`, `apps.api.db.mongo.products()`, `product_embedding_service.build_from_doc` (Task 3), `apps.api.db.vectors` (Task 2).
- Produces:
  - `ProductSpec(BaseModel)`: `code, name, short_description, long_description, spec, aliases, metadata` (`spec` is the condensed spec string — it fills the existing Mongo `spec` field that the `#spec` vector embeds).
  - `IngestReport(BaseModel)`: `file, code, name, status, aliases, error` where `status ∈ ingested|skipped|dry-run|failed`.
  - `extract_spec(text, filename, model_key="openai:5.5", llm=None) -> ProductSpec`
  - `upsert_product(spec: ProductSpec, *, source_pdf: str, pdf_hash: str) -> dict`
  - `ingest_pdf(path, *, model_key="openai:5.5", force=False, dry_run=False, upload_fn=None, textract_fn=None, llm=None, embed_fn=None, index=None) -> IngestReport`
  - `ingest_folder(folder, **same kwargs) -> list[IngestReport]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_spec_ingest_service.py
import mongomock
import pytest

from apps.api.db import mongo
from apps.api.db.vectors import InMemoryIndex
from apps.api.services import spec_ingest_service as si
from apps.api.services.spec_ingest_service import ProductSpec


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    monkeypatch.setenv("SPECS_S3_BUCKET", "spec-bucket")
    from apps.api import settings as settings_mod
    settings_mod.get_settings.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()
    mongo.reset_client()


_SPEC = ProductSpec(
    code="GIIOFEED-PL5", name="Feed Lecithin PL5",
    short_description="Soy lecithin for animal feed",
    long_description="Liquid soy lecithin for feed mills.",
    spec="AI >= 60%", aliases=["PL5"], metadata={"form": "liquid"})


def _fake_llm(spec=_SPEC):
    return lambda prompt, schema, model_key, system_prompt=None: spec


def _fake_embed(texts, *, mode="document"):
    return [[1.0, 0.0] for _ in texts]


def _deps(tmp_path, **over):
    pdf = tmp_path / "GIIOFEED PL5.pdf"
    pdf.write_bytes(b"%PDF fake")
    deps = dict(
        upload_fn=lambda path, bucket, key: None,
        textract_fn=lambda bucket, key: "GIIOFEED PL5 spec text",
        llm=_fake_llm(),
        embed_fn=_fake_embed,
        index=InMemoryIndex(),
    )
    deps.update(over)
    return pdf, deps


def test_extract_spec_falls_back_to_filename_slug():
    spec = si.extract_spec("text", "GIIOFINE_L_SF .pdf", llm=_fake_llm(
        ProductSpec(name="Sunflower Lecithin Liquid", short_description="x")))
    assert spec.code == "GIIOFINE-L-SF"


def test_ingest_writes_product_and_vectors(tmp_path):
    pdf, deps = _deps(tmp_path)
    report = si.ingest_pdf(pdf, **deps)
    assert report.status == "ingested"
    assert report.code == "GIIOFEED-PL5"
    doc = mongo.products().find_one({"_id": "GIIOFEED-PL5"})
    assert doc["name"] == "Feed Lecithin PL5"
    assert doc["aliases"] == ["PL5"]
    assert doc["source_pdf"] == "specs/GIIOFEED PL5.pdf"
    assert doc["source_pdf_hash"]
    assert doc["embedded_hash"]
    assert any(k.endswith("#alias#0") for k in deps["index"]._store)


def test_ingest_skips_unchanged_pdf(tmp_path):
    pdf, deps = _deps(tmp_path)
    si.ingest_pdf(pdf, **deps)
    called = {"n": 0}

    def _counting_textract(bucket, key):
        called["n"] += 1
        return "text"

    report = si.ingest_pdf(pdf, **{**deps, "textract_fn": _counting_textract})
    assert report.status == "skipped"
    assert called["n"] == 0


def test_force_reingests_unchanged_pdf(tmp_path):
    pdf, deps = _deps(tmp_path)
    si.ingest_pdf(pdf, **deps)
    report = si.ingest_pdf(pdf, force=True, **deps)
    assert report.status == "ingested"


def test_dry_run_extracts_but_writes_nothing(tmp_path):
    pdf, deps = _deps(tmp_path)
    report = si.ingest_pdf(pdf, dry_run=True, **deps)
    assert report.status == "dry-run"
    assert report.code == "GIIOFEED-PL5"
    assert mongo.products().count_documents({}) == 0
    assert deps["index"]._store == {}


def test_failure_is_reported_not_raised(tmp_path):
    def _boom(bucket, key):
        raise RuntimeError("textract exploded")

    pdf, deps = _deps(tmp_path, textract_fn=_boom)
    report = si.ingest_pdf(pdf, **deps)
    assert report.status == "failed"
    assert "textract exploded" in report.error


def test_ingest_folder_sweeps_and_continues(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"%PDF a")
    (tmp_path / "b.pdf").write_bytes(b"%PDF b")
    calls = []

    def _llm_by_file(prompt, schema, model_key, system_prompt=None):
        calls.append(1)
        n = len(calls)
        return ProductSpec(code=f"P-{n}", name=f"Prod {n}", short_description="s")

    reports = si.ingest_folder(
        tmp_path,
        upload_fn=lambda path, bucket, key: None,
        textract_fn=lambda bucket, key: "text",
        llm=_llm_by_file, embed_fn=_fake_embed, index=InMemoryIndex())
    assert [r.status for r in reports] == ["ingested", "ingested"]
    assert mongo.products().count_documents({}) == 2


def test_upsert_preserves_embedding_bookkeeping():
    mongo.products().insert_one({
        "_id": "GIIOFEED-PL5", "code": "GIIOFEED-PL5",
        "short_description": "old", "embedded_hash": "h", "vector_keys": ["k"]})
    si.upsert_product(_SPEC, source_pdf="specs/x.pdf", pdf_hash="ph")
    doc = mongo.products().find_one({"_id": "GIIOFEED-PL5"})
    assert doc["short_description"] == "Soy lecithin for animal feed"
    assert doc["embedded_hash"] == "h" and doc["vector_keys"] == ["k"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_spec_ingest_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'ProductSpec'`

- [ ] **Step 3: Implement the ingestion half**

Append to `apps/api/services/spec_ingest_service.py` (place the new `import`
lines at the top of the file, merged with the existing ones):

```python
import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, Field

from apps.api.db import mongo, vectors
from apps.api.services import product_embedding_service
from core.llm_client import call_llm


class ProductSpec(BaseModel):
    code: str = ""
    name: str = ""
    short_description: str = ""
    long_description: str = ""
    spec: str = ""
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class IngestReport(BaseModel):
    file: str = ""
    code: str = ""
    name: str = ""
    status: str = ""  # ingested | skipped | dry-run | failed
    aliases: int = 0
    error: str = ""


_EXTRACT_SYSTEM = (
    "You read raw text extracted from a product specification PDF for a B2B "
    "commodity catalog and return a ProductSpec.\n"
    "1. `code`: the manufacturer product code / SKU exactly as printed in "
    "the document. If no code is printed, return an empty string.\n"
    "2. `name`: the commercial product name.\n"
    "3. `short_description`: one sentence, what the product is.\n"
    "4. `long_description`: 2-4 sentences covering composition, key "
    "properties, and applications.\n"
    "5. `spec`: a condensed one-line spec string of the key technical "
    "attributes (e.g. 'AI >= 95%, moisture <= 2%').\n"
    "6. `aliases`: alternate names a customer might use in chat (trade "
    "names, abbreviations, line codes). Do not repeat `code` or `name`.\n"
    "7. `metadata`: normalized key/values with lowercase snake_case keys "
    "(form, packing, storage, density, origin, category, application, "
    "shelf_life, ...). Values verbatim from the document.\n"
    "Never invent values not present in the document."
)


def _slug(filename: str) -> str:
    stem = Path(filename).stem
    return re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9]+", "-", stem)).strip("-").upper()


def extract_spec(text: str, filename: str, model_key: str = "openai:5.5", llm=None) -> ProductSpec:
    llm = llm or call_llm
    spec = llm(
        f"## Document: {filename}\n\n{text}\n\n---\n\n"
        "Return the ProductSpec as valid JSON conforming to the schema. "
        "No text before or after the JSON.",
        ProductSpec,
        model_key,
        system_prompt=_EXTRACT_SYSTEM,
    )
    if not spec.code.strip():
        spec.code = _slug(filename)
    else:
        spec.code = spec.code.strip()
    return spec


def upsert_product(spec: ProductSpec, *, source_pdf: str, pdf_hash: str) -> dict:
    fields = {
        "code": spec.code,
        "name": spec.name or None,
        "short_description": spec.short_description,
        "long_description": spec.long_description or None,
        "spec": spec.spec or None,
        "metadata": spec.metadata,
        "aliases": spec.aliases,
        "source_pdf": source_pdf,
        "source_pdf_hash": pdf_hash,
    }
    mongo.products().update_one({"_id": spec.code}, {"$set": fields}, upsert=True)
    return mongo.products().find_one({"_id": spec.code})


def _default_upload(path: Path, bucket: str, key: str) -> None:
    from core.utils import create_boto3_client

    client = create_boto3_client("s3", region=get_settings().aws_region)
    client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())


def ingest_pdf(
    path: Path, *, model_key: str = "openai:5.5", force: bool = False,
    dry_run: bool = False, upload_fn=None, textract_fn=None, llm=None,
    embed_fn=None, index=None,
) -> IngestReport:
    path = Path(path)
    report = IngestReport(file=path.name)
    try:
        pdf_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        bucket = get_settings().specs_s3_bucket
        key = f"specs/{path.name}"
        existing = mongo.products().find_one({"source_pdf": key})
        if existing and existing.get("source_pdf_hash") == pdf_hash and not force:
            report.code = existing["code"]
            report.name = existing.get("name") or ""
            report.status = "skipped"
            return report
        (upload_fn or _default_upload)(path, bucket, key)
        text = (textract_fn or textract_text)(bucket, key)
        spec = extract_spec(text, path.name, model_key, llm=llm)
        report.code, report.name, report.aliases = spec.code, spec.name, len(spec.aliases)
        if dry_run:
            report.status = "dry-run"
            return report
        doc = upsert_product(spec, source_pdf=key, pdf_hash=pdf_hash)
        product_embedding_service.build_from_doc(doc, embed_fn=embed_fn, index=index)
        report.status = "ingested"
        return report
    except Exception as exc:  # per-file isolation: the sweep must continue
        report.status = "failed"
        report.error = str(exc)
        return report


def ingest_folder(folder, **kwargs) -> list[IngestReport]:
    folder = Path(folder)
    if not kwargs.get("dry_run") and kwargs.get("index") is None and vectors.is_available():
        idx = vectors.default_index()
        idx.ensure()
        kwargs["index"] = idx
    return [ingest_pdf(pdf, **kwargs) for pdf in sorted(folder.glob("*.pdf"))]
```

(`get_settings` is already imported at the top of the module from Task 7.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_spec_ingest_service.py tests/api/test_spec_ingest_textract.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/spec_ingest_service.py tests/api/test_spec_ingest_service.py
git commit -m "feat: add PDF spec ingestion with LLM extraction and upsert"
```

---

### Task 9: CLI — `scripts/ingest_specs.py`

**Files:**
- Create: `scripts/ingest_specs.py`
- Test: `tests/api/test_ingest_specs_cli.py`

**Interfaces:**
- Consumes: `spec_ingest_service.ingest_folder`, `IngestReport` (Task 8).
- Produces: `python -m scripts.ingest_specs prod_specs/ [--model openai:5.5] [--dry-run] [--force]`; `main(argv) -> int` (0 clean, 1 if any file failed).

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_ingest_specs_cli.py
from apps.api.services.spec_ingest_service import IngestReport
from scripts import ingest_specs


def _run(monkeypatch, reports, argv):
    seen = {}

    def _fake_folder(folder, **kwargs):
        seen["folder"] = str(folder)
        seen["kwargs"] = kwargs
        return reports

    monkeypatch.setattr(ingest_specs.spec_ingest_service, "ingest_folder", _fake_folder)
    code = ingest_specs.main(argv)
    return code, seen


def test_main_prints_table_and_returns_zero(monkeypatch, capsys):
    reports = [
        IngestReport(file="a.pdf", code="A-1", name="Alpha", status="ingested", aliases=2),
        IngestReport(file="b.pdf", code="B-1", name="Beta", status="skipped"),
    ]
    code, seen = _run(monkeypatch, reports, ["prod_specs"])
    out = capsys.readouterr().out
    assert code == 0
    assert seen["folder"] == "prod_specs"
    assert seen["kwargs"]["dry_run"] is False
    assert "a.pdf" in out and "A-1" in out and "ingested" in out
    assert "1 ingested" in out and "1 skipped" in out


def test_main_flags_are_forwarded(monkeypatch, capsys):
    code, seen = _run(monkeypatch, [], ["prod_specs", "--dry-run", "--force", "--model", "sonnet-4-6"])
    assert code == 0
    assert seen["kwargs"]["dry_run"] is True
    assert seen["kwargs"]["force"] is True
    assert seen["kwargs"]["model_key"] == "sonnet-4-6"


def test_main_returns_one_on_failure(monkeypatch, capsys):
    reports = [IngestReport(file="bad.pdf", status="failed", error="boom")]
    code, _ = _run(monkeypatch, reports, ["prod_specs"])
    out = capsys.readouterr().out
    assert code == 1
    assert "boom" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_ingest_specs_cli.py -v`
Expected: FAIL with `ModuleNotFoundError` (check `scripts/__init__.py` exists; create an empty one if not)

- [ ] **Step 3: Implement the CLI**

```python
# scripts/ingest_specs.py
"""Sweep a folder of product spec PDFs into Mongo + the vector index.

Usage:
    python -m scripts.ingest_specs prod_specs/ [--model openai:5.5] [--dry-run] [--force]
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from apps.api.services import spec_ingest_service


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder containing *.pdf spec sheets")
    parser.add_argument("--model", default="openai:5.5", help="model_key for extraction")
    parser.add_argument("--dry-run", action="store_true",
                        help="extract and print, write nothing to Mongo/vectors")
    parser.add_argument("--force", action="store_true", help="re-ingest unchanged PDFs")
    args = parser.parse_args(argv)

    reports = spec_ingest_service.ingest_folder(
        args.folder, model_key=args.model, dry_run=args.dry_run, force=args.force
    )

    widths = (36, 22, 28, 8)
    print(f"{'file':<{widths[0]}} {'code':<{widths[1]}} {'name':<{widths[2]}} status")
    for r in reports:
        line = (f"{r.file:<{widths[0]}} {r.code:<{widths[1]}} "
                f"{r.name:<{widths[2]}} {r.status}")
        if r.error:
            line += f"  ({r.error})"
        print(line)
    counts = Counter(r.status for r in reports)
    print("\n" + ", ".join(f"{n} {status}" for status, n in sorted(counts.items())))
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_ingest_specs_cli.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ingest_specs.py scripts/__init__.py tests/api/test_ingest_specs_cli.py
git commit -m "feat: add ingest_specs CLI for PDF sweep"
```

---

### Task 10: Remove the product catalog graph

**Files:**
- Delete: `apps/api/services/product_graph_service.py`, `graph/product_extractor.py`
- Delete: `tests/api/test_product_graph_service.py`, `tests/api/test_product_graph_falkor.py`, `tests/api/test_product_extractor.py`
- Modify: `apps/api/routers/graphs.py`, `apps/api/main.py`, `apps/api/services/graph_reader_service.py`, `apps/api/db/falkor.py`, `tests/api/test_graph_reader_service.py`
- Modify (web): `apps/web/src/api/client.ts`, `apps/web/src/pages/GraphsPage.tsx`, `apps/web/src/components/GraphLegend.tsx`, `apps/web/src/components/GraphDetailPanel.tsx`, `apps/web/src/components/GraphLegend.test.tsx`, `apps/web/src/components/GraphDetailPanel.test.tsx`

Nothing else imports these modules after Task 6 (verify in Step 1). Customer/chat/profile graph code is untouched.

- [ ] **Step 1: Verify no remaining consumers**

Run: `grep -rn "product_graph_service\|product_extractor\|catalog_graph\|read_product_graph\|getGraphProducts" --include="*.py" --include="*.ts" --include="*.tsx" apps core graph scripts tests`
Expected: hits only in the files listed above (the deletion targets and the modify targets). If anything else shows up, update that consumer first.

- [ ] **Step 2: Backend removal**

- `git rm apps/api/services/product_graph_service.py graph/product_extractor.py tests/api/test_product_graph_service.py tests/api/test_product_graph_falkor.py tests/api/test_product_extractor.py`
- `apps/api/routers/graphs.py`: delete `catalog_router = APIRouter(...)` and the `get_product_graph` endpoint, leaving:

```python
from fastapi import APIRouter

from apps.api.services import graph_reader_service

customer_router = APIRouter(prefix="/api/customers/{customer_id}", tags=["graphs"])


@customer_router.get("/graph")
def get_customer_graph(customer_id: str) -> dict:
    return graph_reader_service.read_customer_graph(customer_id)
```

- `apps/api/main.py`: delete the line `app.include_router(graphs.catalog_router)`.
- `apps/api/services/graph_reader_service.py`: delete the whole `read_product_graph()` function (keep `_node`/`_edge`/`_empty` — the customer reader uses them).
- `apps/api/db/falkor.py`: delete the `catalog_graph()` function.
- `tests/api/test_graph_reader_service.py`: delete the test functions that import `ProductFacts` / `product_graph_service` / call `read_product_graph` (keep the customer-graph tests).

- [ ] **Step 3: Run the Python suite**

Run: `python -m pytest tests -v`
Expected: all PASS, no import errors

- [ ] **Step 4: Web removal**

- `apps/web/src/api/client.ts`: delete the `getGraphProducts` entry.
- `apps/web/src/pages/GraphsPage.tsx`:
  - Delete `type GraphView`, the `view` state, `EMPTY_SUBTITLES`, the `Tabs` block, `handleRebuild`, and the `rebuilding` state.
  - `loadGraph` keeps only the customer branch:

```tsx
const loadGraph = useCallback(async (customerId: string) => {
  try {
    const data = await api.getCustomerGraph(customerId);
    setGraphData(data);
    setSelected(null);
    setExpanded(new Set());
    setChatFilter("all");
  } catch {
    toast.error("Failed to load graph");
    setGraphData(EMPTY_GRAPH);
  }
}, []);
```

  - The load effect and `handleRefresh` become `if (selectedCustomerId) loadGraph(selectedCustomerId);`.
  - `displayedGraph` drops the `view !== "customer"` condition (filter applies whenever `chatFilter !== "all"`).
  - `GraphCanvas` gets `emptySubtitle="Run the sales-order agent in the chat to build this graph"`; `<GraphLegend />` loses the `view` prop; `GraphDetailPanel` loses `onRebuild`/`rebuilding`.
- `apps/web/src/components/GraphLegend.tsx`: remove the `view` prop, `PRODUCT_TYPES`, and the `view === "products"` build-status legend block; always render `CUSTOMER_TYPES`.
- `apps/web/src/components/GraphDetailPanel.tsx`: remove the `onRebuild`/`rebuilding` props, the `buildStatus`/`productCode` derivation, and the BuildBadge/Rebuild block (`BuildBadge` stays exported from `graph/nodes/parts` — ProductsPage still uses it).
- Update `GraphLegend.test.tsx` and `GraphDetailPanel.test.tsx`: delete tests exercising the products view / rebuild button; fix render calls that passed the removed props.

- [ ] **Step 5: Web verification**

Run: `cd apps/web && npx tsc -b && npx vitest run`
Expected: compile clean, tests PASS (any remaining reference to removed props is a compile error — fix it)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat!: remove product catalog graph in favor of embeddings"
```

---

### Task 11: Full verification + live smoke run

**Files:** none created — verification only.

- [ ] **Step 1: Full test suites**

Run: `python -m pytest tests -v` and `cd apps/web && npx tsc -b && npx vitest run`
Expected: all PASS

- [ ] **Step 2: Grep for leftovers**

Run: `grep -rn "product_graph\|catalog_graph\|HAS_ALIAS\|SpecAttr" --include="*.py" --include="*.ts" --include="*.tsx" apps core graph scripts | grep -v node_modules`
Expected: no hits (or only comments/docs — remove them)

- [ ] **Step 3: Live smoke run (requires AWS + Gemini credentials in `.env`)**

```bash
export SPECS_S3_BUCKET=<pdf-bucket> S3_VECTOR_BUCKET=<vector-bucket>
python -m scripts.ingest_specs prod_specs/ --dry-run   # review codes/names table
python -m scripts.ingest_specs prod_specs/             # real run: 27 PDFs
```

Expected: dry-run table shows sensible codes (e.g. `GIIOFINE-UP-SF` from its PDF); real run ends `N ingested` with exit 0.

- [ ] **Step 4: End-to-end matcher check**

Start the API and web app, open a customer chat, send `@agent` a message like "need 2 MT of the non-GMO soy lecithin", and confirm: (a) a confident match resolves to `GIIOFINE-L-nGM`-style SKU, and (b) an ambiguous message like "send lecithin" produces a question listing candidates with similarity scores and snippets. Check `/api/products` shows `build_status: "built"` for ingested products.

- [ ] **Step 5: Report results**

Summarize test counts, live-run output, and any deviations from the spec for review. Do not merge/PR without user sign-off.
