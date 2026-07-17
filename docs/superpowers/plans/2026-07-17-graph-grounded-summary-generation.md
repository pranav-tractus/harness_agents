# Graph-Grounded Summary Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed the customer profile graph, chat entity history, and a new LLM-derived product graph into sales-order summary generation and revision so the LLM grounds the order and backfills fields the chat did not state.

**Architecture:** A new global product graph (`graph_dbs/_catalog/product.db`) is kept in sync on product create/update/delete via an LLM extractor. A new `summary_context_service` assembles three text blocks (profile graph, chat history graph, product graph) that `command_service` passes into `summary_service.generate`/`revise`. The summary system prompt is updated to allow gap-filling from those blocks while preferring explicit chat values.

**Tech Stack:** Python, FastAPI, Kuzu (embedded graph DB), pydantic + instructor via `core.llm_client.call_llm`, pytest, mongomock.

## Global Constraints

- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- All new services expose injectable dependencies (extractor / reader / db_path / graph functions) so tests never hit a real LLM or a real shared filesystem DB, mirroring existing `profile_graph_service`, `chat_graph_service`, and `command_service` patterns.
- Kuzu graph DBs live under `GRAPH_ROOT = Path("graph_dbs")`; tests monkeypatch `GRAPH_ROOT` to `tmp_path`.
- Prefer values explicitly stated in the chat; graph data is only for gap-filling. Do not invent values absent from all sources.
- Products are global (not per-customer): the product graph is a single shared DB at `graph_dbs/_catalog/product.db`.
- Run the full API test suite with `pytest tests/api -v` (or `pytest tests -v` where noted).

---

### Task 1: Product facts extractor

**Files:**
- Create: `graph/product_extractor.py`
- Test: `tests/api/test_product_extractor.py`

**Interfaces:**
- Consumes: `core.llm_client.call_llm(prompt, schema, model_key, system_prompt=None)`.
- Produces:
  - `class ProductFacts(BaseModel)` with fields `aliases: list[str]`, `grade: str | None`, `packing_size: str | None`, `unit: str | None`, `attributes: dict[str, str]`.
  - `extract_product_facts(description: str, spec: str | None, model_key: str = "openai:5.5") -> ProductFacts`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_product_extractor.py
from graph import product_extractor as pe


def test_extract_product_facts_builds_prompt_and_returns_facts():
    captured = {}

    def _fake_llm(prompt, schema, model_key, system_prompt=None):
        captured["prompt"] = prompt
        captured["schema"] = schema
        captured["model_key"] = model_key
        return schema(
            aliases=["atta", "wheat flour bag"],
            grade="A",
            packing_size="25kg",
            unit="MT",
            attributes={"origin": "India"},
        )

    pe.call_llm = _fake_llm  # monkeypatch module ref
    facts = pe.extract_product_facts("Wheat Flour 25kg", "grade A, 25kg PP bag", "sonnet-4-6")

    assert facts.aliases == ["atta", "wheat flour bag"]
    assert facts.grade == "A"
    assert facts.packing_size == "25kg"
    assert facts.attributes["origin"] == "India"
    assert captured["schema"] is pe.ProductFacts
    assert captured["model_key"] == "sonnet-4-6"
    assert "Wheat Flour 25kg" in captured["prompt"]
    assert "grade A, 25kg PP bag" in captured["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_product_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph.product_extractor'`.

- [ ] **Step 3: Write minimal implementation**

```python
# graph/product_extractor.py
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from core.llm_client import call_llm

_PROMPT = """\
You normalize a product catalog entry for a commodity trading system.
Given the product description and spec, extract:
- aliases: common alternate names / how a customer might refer to it in chat
- grade, packing_size, unit: normalized spec attributes when present
- attributes: any other normalized spec key/value pairs

Return empty lists, empty objects, or null when a field is not determinable.

Product description: {description}
Product spec: {spec}
"""


class ProductFacts(BaseModel):
    aliases: list[str] = Field(default_factory=list, description="Alternate names / common references")
    grade: Optional[str] = Field(default=None, description="Product grade if stated")
    packing_size: Optional[str] = Field(default=None, description="Packing size, e.g. 25kg")
    unit: Optional[str] = Field(default=None, description="Trading unit, e.g. MT, KG")
    attributes: dict[str, str] = Field(default_factory=dict, description="Other normalized spec key/values")


def extract_product_facts(description: str, spec: str | None, model_key: str = "openai:5.5") -> ProductFacts:
    prompt = _PROMPT.format(description=description, spec=spec or "")
    return call_llm(prompt, ProductFacts, model_key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_product_extractor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add graph/product_extractor.py tests/api/test_product_extractor.py
git commit -m "feat(graph): product facts extractor (aliases + normalized specs)"
```

---

### Task 2: Product graph service

**Files:**
- Create: `apps/api/services/product_graph_service.py`
- Test: `tests/api/test_product_graph_service.py`

**Interfaces:**
- Consumes: `graph.product_extractor.extract_product_facts` and `ProductFacts` (Task 1); `kuzu`.
- Produces:
  - `GRAPH_ROOT: Path` (monkeypatchable, default `Path("graph_dbs")`).
  - `product_db_path() -> Path` → `GRAPH_ROOT / "_catalog" / "product.db"`.
  - `resync_product(code: str, description: str, spec: str | None, model_key: str = "openai:5.5", *, extractor=None) -> None` — LLM-derive facts, wipe this product's node/edges, rewrite. Idempotent per code; never touches other products.
  - `remove_product(code: str) -> None` — delete this product's node + alias/spec nodes and edges (no-op if DB missing).
  - `catalog_block() -> str | None` — render whole enriched catalog to a prompt text block; `None` when the DB is missing or empty.

Notes for the implementer:
- Alias/SpecAttr primary keys are **code-scoped** to avoid cross-product collisions: `Alias.id = f"{code}::{name}"`, `SpecAttr.id = f"{code}::{key}"`. Each also stores a `code` property so per-product deletion is a simple match on `code`.
- Spec attributes written per product: `grade`, `packing_size`, `unit` (skipped when `None`), plus every entry in `attributes`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_product_graph_service.py
import kuzu

from apps.api.services import product_graph_service as pgs
from graph.product_extractor import ProductFacts


def _fake_extractor(facts_by_code):
    def _fn(description, spec, model_key):
        return facts_by_code[description]
    return _fn


def test_resync_writes_product_alias_and_spec_nodes(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    facts = ProductFacts(aliases=["atta", "maida"], grade="A", packing_size="25kg",
                         unit="MT", attributes={"origin": "India"})
    pgs.resync_product("WHF25", "Wheat Flour", "grade A", extractor=lambda d, s, m: facts)

    db = kuzu.Database(str(pgs.product_db_path()))
    conn = kuzu.Connection(db)
    aliases = conn.execute("MATCH (a:Alias) RETURN a.name").get_as_pl()["a.name"].to_list()
    spec_keys = conn.execute("MATCH (s:SpecAttr) RETURN s.key").get_as_pl()["s.key"].to_list()
    assert set(aliases) == {"atta", "maida"}
    assert "grade" in spec_keys and "unit" in spec_keys and "origin" in spec_keys


def test_resync_is_idempotent_and_scoped_per_product(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    f1 = ProductFacts(aliases=["atta"], grade="A")
    f2 = ProductFacts(aliases=["lecithin"], grade="B")
    pgs.resync_product("WHF25", "Wheat Flour", None, extractor=lambda d, s, m: f1)
    pgs.resync_product("LEC10", "Lecithin", None, extractor=lambda d, s, m: f2)
    pgs.resync_product("WHF25", "Wheat Flour", None, extractor=lambda d, s, m: f1)  # again

    db = kuzu.Database(str(pgs.product_db_path()))
    conn = kuzu.Connection(db)
    n_products = conn.execute("MATCH (p:Product) RETURN count(p) AS n").get_as_pl()["n"].to_list()[0]
    n_aliases = conn.execute("MATCH (a:Alias) RETURN count(a) AS n").get_as_pl()["n"].to_list()[0]
    assert n_products == 2       # WHF25 not duplicated
    assert n_aliases == 2        # one per product, not duplicated


def test_remove_product_deletes_only_that_product(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    pgs.resync_product("WHF25", "Wheat Flour", None,
                       extractor=lambda d, s, m: ProductFacts(aliases=["atta"]))
    pgs.resync_product("LEC10", "Lecithin", None,
                       extractor=lambda d, s, m: ProductFacts(aliases=["lecithin"]))
    pgs.remove_product("WHF25")

    db = kuzu.Database(str(pgs.product_db_path()))
    conn = kuzu.Connection(db)
    codes = conn.execute("MATCH (p:Product) RETURN p.code").get_as_pl()["p.code"].to_list()
    assert codes == ["LEC10"]


def test_catalog_block_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    assert pgs.catalog_block() is None


def test_catalog_block_renders_products(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    pgs.resync_product("WHF25", "Wheat Flour", None,
                       extractor=lambda d, s, m: ProductFacts(aliases=["atta"], grade="A", unit="MT"))
    block = pgs.catalog_block()
    assert block is not None
    assert "=== Product Catalog ===" in block
    assert "WHF25: Wheat Flour" in block
    assert "grade: A" in block and "unit: MT" in block
    assert "aka: atta" in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_product_graph_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.api.services.product_graph_service'`.

- [ ] **Step 3: Write minimal implementation**

```python
# apps/api/services/product_graph_service.py
from pathlib import Path

import kuzu

from graph.product_extractor import ProductFacts, extract_product_facts

GRAPH_ROOT = Path("graph_dbs")

_DDL = [
    "CREATE NODE TABLE IF NOT EXISTS Product(code STRING, description STRING, spec STRING, PRIMARY KEY(code))",
    "CREATE NODE TABLE IF NOT EXISTS Alias(id STRING, code STRING, name STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS SpecAttr(id STRING, code STRING, key STRING, value STRING, PRIMARY KEY(id))",
    "CREATE REL TABLE IF NOT EXISTS HAS_ALIAS(FROM Product TO Alias)",
    "CREATE REL TABLE IF NOT EXISTS HAS_SPEC(FROM Product TO SpecAttr)",
]


def product_db_path() -> Path:
    return GRAPH_ROOT / "_catalog" / "product.db"


def _connect() -> kuzu.Connection:
    path = product_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = kuzu.Connection(kuzu.Database(str(path)))
    for ddl in _DDL:
        conn.execute(ddl)
    return conn


def _delete_product(conn: kuzu.Connection, code: str) -> None:
    conn.execute("MATCH (p:Product {code: $c})-[r:HAS_ALIAS]->() DELETE r", {"c": code})
    conn.execute("MATCH (p:Product {code: $c})-[r:HAS_SPEC]->() DELETE r", {"c": code})
    conn.execute("MATCH (a:Alias {code: $c}) DELETE a", {"c": code})
    conn.execute("MATCH (s:SpecAttr {code: $c}) DELETE s", {"c": code})
    conn.execute("MATCH (p:Product {code: $c}) DELETE p", {"c": code})


def _spec_pairs(facts: ProductFacts) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, value in (("grade", facts.grade), ("packing_size", facts.packing_size), ("unit", facts.unit)):
        if value:
            pairs.append((key, str(value)))
    for key, value in facts.attributes.items():
        if value:
            pairs.append((key, str(value)))
    return pairs


def resync_product(code, description, spec, model_key="openai:5.5", *, extractor=None) -> None:
    extractor = extractor or extract_product_facts
    facts = extractor(description, spec, model_key)
    conn = _connect()
    _delete_product(conn, code)
    conn.execute(
        "CREATE (:Product {code: $c, description: $d, spec: $s})",
        {"c": code, "d": description or "", "s": spec or ""},
    )
    for name in dict.fromkeys(a for a in facts.aliases if a):  # dedupe, preserve order
        aid = f"{code}::{name}"
        conn.execute("CREATE (:Alias {id: $id, code: $c, name: $n})", {"id": aid, "c": code, "n": name})
        conn.execute(
            "MATCH (p:Product {code: $c}), (a:Alias {id: $id}) CREATE (p)-[:HAS_ALIAS]->(a)",
            {"c": code, "id": aid},
        )
    for key, value in _spec_pairs(facts):
        sid = f"{code}::{key}"
        conn.execute(
            "CREATE (:SpecAttr {id: $id, code: $c, key: $k, value: $v})",
            {"id": sid, "c": code, "k": key, "v": value},
        )
        conn.execute(
            "MATCH (p:Product {code: $c}), (s:SpecAttr {id: $id}) CREATE (p)-[:HAS_SPEC]->(s)",
            {"c": code, "id": sid},
        )


def remove_product(code) -> None:
    if not product_db_path().exists():
        return
    _delete_product(_connect(), code)


def catalog_block() -> str | None:
    if not product_db_path().exists():
        return None
    conn = _connect()
    res = conn.execute("MATCH (p:Product) RETURN p.code, p.description ORDER BY p.code")
    products: list[tuple[str, str]] = []
    while res.has_next():
        row = res.get_next()
        products.append((row[0], row[1]))
    if not products:
        return None

    lines = ["=== Product Catalog ==="]
    for code, description in products:
        specs: list[str] = []
        sres = conn.execute("MATCH (p:Product {code: $c})-[:HAS_SPEC]->(s:SpecAttr) RETURN s.key, s.value", {"c": code})
        while sres.has_next():
            k, v = sres.get_next()
            specs.append(f"{k}: {v}")
        aliases: list[str] = []
        ares = conn.execute("MATCH (p:Product {code: $c})-[:HAS_ALIAS]->(a:Alias) RETURN a.name", {"c": code})
        while ares.has_next():
            aliases.append(ares.get_next()[0])

        line = f"- {code}: {description}"
        if specs:
            line += " | " + ", ".join(specs)
        lines.append(line)
        if aliases:
            lines.append(f"  aka: {', '.join(aliases)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_product_graph_service.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/product_graph_service.py tests/api/test_product_graph_service.py
git commit -m "feat(api): product graph service (global kuzu db, per-product resync)"
```

---

### Task 3: Wire product graph sync into products router

**Files:**
- Modify: `apps/api/routers/products.py`
- Modify: `tests/api/test_api_endpoints.py` (fixture + product endpoint tests)

**Interfaces:**
- Consumes: `product_graph_service.resync_product(code, description, spec)` and `product_graph_service.remove_product(code)` (Task 2).
- Produces: no new symbols; create/update trigger `resync_product`, delete triggers `remove_product`.

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_api_endpoints.py`. First extend the `client` fixture to stub the product-graph sync (so tests never build a real graph), then add assertions.

```python
# in the client fixture, alongside the existing monkeypatches:
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.resync_product",
                        lambda *a, **k: None)
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.remove_product",
                        lambda *a, **k: None)
```

```python
def test_create_product_syncs_graph(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.resync_product",
                        lambda code, description, spec, *a, **k: calls.append(("resync", code)))
    r = client.post("/api/products", json={"code": "NEW-2", "description": "New", "spec": "s"})
    assert r.status_code == 201
    assert ("resync", "NEW-2") in calls


def test_update_product_syncs_graph(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.resync_product",
                        lambda code, description, spec, *a, **k: calls.append(("resync", code)))
    r = client.put("/api/products/TG-BPPC", json={"description": "Updated", "spec": "v2"})
    assert r.status_code == 200
    assert ("resync", "TG-BPPC") in calls


def test_delete_product_removes_from_graph(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.remove_product",
                        lambda code, *a, **k: calls.append(("remove", code)))
    r = client.delete("/api/products/TG-MGL8")
    assert r.status_code == 204
    assert ("remove", "TG-MGL8") in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_api_endpoints.py -k product -v`
Expected: FAIL — `AttributeError` on `apps.api.routers.products.product_graph_service` (not imported yet) / new tests error.

- [ ] **Step 3: Write minimal implementation**

Modify `apps/api/routers/products.py`:

```python
from fastapi import APIRouter, HTTPException, Response

from apps.api.db import mongo
from apps.api.models import ProductCreate, ProductOut, ProductUpdate
from apps.api.services import product_graph_service

router = APIRouter(prefix="/api/products", tags=["products"])
```

In `create_product`, after `mongo.products().insert_one(doc)`:

```python
    mongo.products().insert_one(doc)
    product_graph_service.resync_product(code, body.description, body.spec)
    return _out(mongo.products().find_one({"_id": code}))
```

In `update_product`, after the `$set` update block, re-read the (updated) doc and resync:

```python
    if changes:
        mongo.products().update_one({"_id": product_id}, {"$set": changes})
    updated = mongo.products().find_one({"_id": product_id})
    product_graph_service.resync_product(updated["code"], updated["description"], updated.get("spec"))
    return _out(updated)
```

In `delete_product`, after a successful delete:

```python
    res = mongo.products().delete_one({"_id": product_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "product not found")
    product_graph_service.remove_product(product_id)
    return Response(status_code=204)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_api_endpoints.py -v`
Expected: PASS (all endpoint tests, including new sync assertions).

- [ ] **Step 5: Commit**

```bash
git add apps/api/routers/products.py tests/api/test_api_endpoints.py
git commit -m "feat(api): sync product graph on product create/update/delete"
```

---

### Task 4: Profile graph read block

**Files:**
- Modify: `apps/api/services/profile_graph_service.py`
- Modify: `tests/api/test_profile_graph_service.py`

**Interfaces:**
- Consumes: existing `profile_graph_service.resync`, `profile_db_path`, `_DDL`.
- Produces: `read_block(customer_id: str) -> str | None` — renders the profile graph's `Attribute` nodes to a text block; `None` when the DB is missing or has no attributes.

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_profile_graph_service.py`:

```python
def test_read_block_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "GRAPH_ROOT", tmp_path)
    assert pg.read_block("no-such-customer") is None


def test_read_block_renders_attributes(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "GRAPH_ROOT", tmp_path)
    pg.resync("dummy-03", "Dummy-03", {"approved_credit_term": "Net 30", "email": "a@b.com"})
    block = pg.read_block("dummy-03")
    assert block is not None
    assert "=== Customer Profile ===" in block
    assert "approved_credit_term: Net 30" in block
    assert "email: a@b.com" in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_profile_graph_service.py -k read_block -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'read_block'`.

- [ ] **Step 3: Write minimal implementation**

Append to `apps/api/services/profile_graph_service.py`:

```python
def read_block(customer_id: str) -> str | None:
    path = profile_db_path(customer_id)
    if not path.exists():
        return None
    conn = kuzu.Connection(kuzu.Database(str(path)))
    for ddl in _DDL:
        conn.execute(ddl)
    res = conn.execute("MATCH (a:Attribute) RETURN a.key, a.value")
    rows: list[tuple[str, str]] = []
    while res.has_next():
        row = res.get_next()
        rows.append((row[0], row[1]))
    if not rows:
        return None
    lines = ["=== Customer Profile ==="]
    for key, value in rows:
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_profile_graph_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/profile_graph_service.py tests/api/test_profile_graph_service.py
git commit -m "feat(api): read profile graph into a prompt text block"
```

---

### Task 5: Summary context assembly service

**Files:**
- Create: `apps/api/services/summary_context_service.py`
- Test: `tests/api/test_summary_context_service.py`

**Interfaces:**
- Consumes: `profile_graph_service.read_block(customer_id)` (Task 4); `product_graph_service.catalog_block()` (Task 2); `chat_graph_service.chat_db_path(customer_id)`; `graph.kuzu_backend.KuzuBackend`; `graph.retrieval.get_memory_block(customer_id, backend)`.
- Produces: `assemble(customer_id: str, *, profile_reader=None, history_reader=None, product_reader=None) -> dict` returning keys `profile_block`, `history_block`, `product_block` (each `str | None`). `profile_reader` and `history_reader` take `customer_id`; `product_reader` takes no args.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_summary_context_service.py
from apps.api.services import summary_context_service as scs


def test_assemble_composes_three_blocks_from_injected_readers():
    out = scs.assemble(
        "dummy-01",
        profile_reader=lambda cid: f"profile:{cid}",
        history_reader=lambda cid: f"history:{cid}",
        product_reader=lambda: "products",
    )
    assert out == {
        "profile_block": "profile:dummy-01",
        "history_block": "history:dummy-01",
        "product_block": "products",
    }


def test_assemble_passes_through_none_blocks():
    out = scs.assemble(
        "dummy-01",
        profile_reader=lambda cid: None,
        history_reader=lambda cid: None,
        product_reader=lambda: None,
    )
    assert out == {"profile_block": None, "history_block": None, "product_block": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_summary_context_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.api.services.summary_context_service'`.

- [ ] **Step 3: Write minimal implementation**

```python
# apps/api/services/summary_context_service.py
from apps.api.services import chat_graph_service, product_graph_service, profile_graph_service
from graph.kuzu_backend import KuzuBackend
from graph.retrieval import get_memory_block


def _history_block(customer_id: str) -> str | None:
    path = chat_graph_service.chat_db_path(customer_id)
    if not path.exists():
        return None
    backend = KuzuBackend(db_path=path)
    try:
        return get_memory_block(customer_id, backend)
    finally:
        backend.close()


def assemble(customer_id, *, profile_reader=None, history_reader=None, product_reader=None) -> dict:
    profile_reader = profile_reader or profile_graph_service.read_block
    history_reader = history_reader or _history_block
    product_reader = product_reader or product_graph_service.catalog_block
    return {
        "profile_block": profile_reader(customer_id),
        "history_block": history_reader(customer_id),
        "product_block": product_reader(),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_summary_context_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/summary_context_service.py tests/api/test_summary_context_service.py
git commit -m "feat(api): assemble profile/history/product context blocks for summaries"
```

---

### Task 6: Summary service — graph context + gap-filling prompt

**Files:**
- Modify: `apps/api/services/summary_service.py`
- Modify: `tests/api/test_summary_service.py`

**Interfaces:**
- Consumes: `core.models.SOExtractContractList`, `SOUpdateContractList`; `core.llm_client.call_llm`.
- Produces:
  - `generate(customer_name, messages, product_block, model_key, *, profile_block=None, history_block=None, llm=None) -> SOExtractContractList` (the old `product_catalog` list param becomes the enriched `product_block` string).
  - `revise(customer_name, previous, instructions, messages, model_key, *, product_block=None, profile_block=None, history_block=None, llm=None) -> SOUpdateContractList`.
  - Updated `_SYSTEM` gap-filling string.

- [ ] **Step 1: Write the failing test**

Replace the two existing tests in `tests/api/test_summary_service.py` with the versions below (the `generate` call signature and prompt content change):

```python
from core.models import SOExtractContractList, SOUpdateContractList

from apps.api.services import summary_service as ss
from tests.api._factories import make_extract, make_item, make_update


def _fake_llm_factory(captured, result):
    def _llm(prompt, schema, model_key, system_prompt=None):
        captured["prompt"] = prompt
        captured["model_key"] = model_key
        captured["schema"] = schema
        captured["system_prompt"] = system_prompt
        return result
    return _llm


def test_generate_embeds_all_context_blocks():
    captured = {}
    result = make_extract(items=[make_item(description="TG-BPPC", quantity=10, quantity_unit="MT")])
    msgs = [{"role": "me", "body": "10MT TG-BPPC"}, {"role": "customer", "body": "ok"}]
    out = ss.generate(
        "Dummy-01", msgs, "=== Product Catalog ===\n- TG-BPPC: Choline", "sonnet-4-6",
        profile_block="=== Customer Profile ===\n- approved_credit_term: Net 30",
        history_block="=== Customer History ===\n- Products: TG-BPPC",
        llm=_fake_llm_factory(captured, result),
    )
    assert isinstance(out, SOExtractContractList)
    assert captured["schema"] is SOExtractContractList
    assert "10MT TG-BPPC" in captured["prompt"]
    assert "TG-BPPC: Choline" in captured["prompt"]
    assert "approved_credit_term: Net 30" in captured["prompt"]
    assert "Customer History" in captured["prompt"]
    assert "Prefer values explicitly stated in the chat" in captured["system_prompt"]


def test_generate_omits_missing_blocks():
    captured = {}
    result = make_extract(items=[make_item(description="TG-BPPC")])
    out = ss.generate("Dummy-01", [{"role": "me", "body": "x"}], None, "sonnet-4-6",
                      llm=_fake_llm_factory(captured, result))
    assert isinstance(out, SOExtractContractList)
    assert "Customer profile" not in captured["prompt"]
    assert "Product catalog" not in captured["prompt"]


def test_revise_embeds_previous_and_context():
    captured = {}
    prev = make_extract(items=[make_item(description="TG-BPPC", quantity=10, quantity_unit="MT")])
    result = make_update(items=[make_item(description="TG-BPPC", quantity=20, quantity_unit="MT")])
    out = ss.revise(
        "Dummy-01", prev, "change qty to 20", [{"role": "me", "body": "x"}], "sonnet-4-6",
        product_block="=== Product Catalog ===\n- TG-BPPC: Choline",
        profile_block="=== Customer Profile ===\n- email: a@b.com",
        llm=_fake_llm_factory(captured, result),
    )
    assert isinstance(out, SOUpdateContractList)
    assert captured["schema"] is SOUpdateContractList
    assert "change qty to 20" in captured["prompt"]
    assert "TG-BPPC" in captured["prompt"]       # previous summary embedded
    assert "email: a@b.com" in captured["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_summary_service.py -v`
Expected: FAIL — `generate` still expects a `product_catalog` list / lacks `profile_block`/`history_block`; `_SYSTEM` lacks the new phrasing.

- [ ] **Step 3: Write minimal implementation**

Replace `apps/api/services/summary_service.py` with:

```python
from core.llm_client import call_llm
from core.models import SOExtractContractList, SOUpdateContractList

_SYSTEM = (
    "You extract a structured sales order from a customer chat, matching the "
    "provided JSON schema exactly. Prefer values explicitly stated in the chat. "
    "When a field is not stated in the chat, you may fill it from the provided "
    "customer profile, purchase history, or product catalog context, preferring "
    "the chat when they conflict. Only use products from the provided catalog. "
    "Group line items into one contract per distinct purchase order. Leave string "
    "fields empty and numeric fields null when a value appears in none of these "
    "sources. Do not invent quantities, prices, or terms."
)


def _chat_block(messages: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {m['body']}" for m in messages)


def _section(label: str, block: str | None) -> str:
    return f"{label}:\n{block}\n\n" if block else ""


def generate(customer_name, messages, product_block, model_key,
             *, profile_block=None, history_block=None, llm=None) -> SOExtractContractList:
    llm = llm or call_llm
    prompt = (
        f"Customer: {customer_name}\n\n"
        + _section("Customer profile", profile_block)
        + _section("Purchase history", history_block)
        + _section("Product catalog", product_block)
        + f"Chat since last contract:\n{_chat_block(messages)}\n\n"
        "Produce the sales order contract list."
    )
    return llm(prompt, SOExtractContractList, model_key, system_prompt=_SYSTEM)


def revise(customer_name, previous, instructions, messages, model_key,
           *, product_block=None, profile_block=None, history_block=None, llm=None) -> SOUpdateContractList:
    llm = llm or call_llm
    prompt = (
        f"Customer: {customer_name}\n\n"
        + _section("Customer profile", profile_block)
        + _section("Purchase history", history_block)
        + _section("Product catalog", product_block)
        + f"Previous summary (JSON):\n{previous.model_dump_json(indent=2)}\n\n"
        + f"Chat since last contract:\n{_chat_block(messages)}\n\n"
        + f"Apply these edit instructions and return the corrected contract list:\n{instructions}"
    )
    return llm(prompt, SOUpdateContractList, model_key, system_prompt=_SYSTEM)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_summary_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/summary_service.py tests/api/test_summary_service.py
git commit -m "feat(api): summary generation consumes graph context with gap-filling"
```

---

### Task 7: Wire context assembly into command_service

**Files:**
- Modify: `apps/api/services/command_service.py`
- Modify: `tests/api/test_command_service.py`
- Modify: `tests/api/test_api_endpoints.py` (fixture: stub `summary_context_service.assemble`)

**Interfaces:**
- Consumes: `summary_context_service.assemble(customer_id)` (Task 5); `summary_service.generate`/`revise` new signatures (Task 6).
- Produces: `dispatch(customer_id, command, args, model_key, *, graph_fn=None, summary_gen=None, summary_revise=None, context_fn=None) -> dict` — new injectable `context_fn`; `_create`/`_edit` now pass graph context blocks into the summary generator/reviser. The old `_product_catalog()` helper is removed.

- [ ] **Step 1: Write the failing test**

Update `tests/api/test_command_service.py`: add a shared context stub and assert `_create`/`_edit` forward blocks. Replace the create/edit tests as shown and add a forwarding test.

```python
def _ctx(*a, **k):
    return {"profile_block": "PROFILE", "history_block": "HISTORY", "product_block": "CATALOG"}


def test_create_forwards_context_blocks_to_summary_gen():
    captured = {}
    chat_service.add_message("dummy-01", "me", "need 10MT TG-BPPC")

    def _gen(name, window, product_block, model_key, *, profile_block=None, history_block=None, **k):
        captured.update(product_block=product_block, profile_block=profile_block,
                        history_block=history_block)
        return _fake_summary()

    command_service.dispatch("dummy-01", "create-sales-order", None, "sonnet-4-6",
                             graph_fn=_record_graph([]), summary_gen=_gen, context_fn=_ctx)
    assert captured == {"product_block": "CATALOG", "profile_block": "PROFILE",
                        "history_block": "HISTORY"}


def test_edit_forwards_context_blocks_to_summary_revise():
    captured = {}
    chat_service.add_message("dummy-01", "me", "x")
    command_service.dispatch("dummy-01", "create-sales-order", None, "sonnet-4-6",
                             graph_fn=_record_graph([]), summary_gen=_fake_summary, context_fn=_ctx)

    def _rev(name, previous, instructions, window, model_key, *, product_block=None,
             profile_block=None, history_block=None, **k):
        captured.update(product_block=product_block, profile_block=profile_block,
                        history_block=history_block)
        return _fake_revision()

    command_service.dispatch("dummy-01", "edit", "qty 20", "sonnet-4-6",
                             summary_revise=_rev, context_fn=_ctx)
    assert captured == {"product_block": "CATALOG", "profile_block": "PROFILE",
                        "history_block": "HISTORY"}
```

Also update the three existing tests that call `dispatch(... "create-sales-order" ...)` / `"edit"` (`test_create_runs_graph_before_summary_and_posts_pending`, `test_create_blocked_when_pending_exists`, `test_approve_advances_checkpoint_and_persists`, `test_edit_requires_pending_and_bumps_revision`) to pass `context_fn=_ctx` so they never hit the filesystem-backed default assembler.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_command_service.py -v`
Expected: FAIL — `dispatch` has no `context_fn` kwarg; blocks not forwarded.

- [ ] **Step 3: Write minimal implementation**

Modify `apps/api/services/command_service.py`:

Update imports (add `summary_context_service`) and remove `_product_catalog`:

```python
from apps.api.services import chat_service
from apps.api.services import chat_graph_service, summary_context_service, summary_service
```

Delete the `_product_catalog()` function.

Update `dispatch`:

```python
def dispatch(customer_id, command, args, model_key,
             *, graph_fn=None, summary_gen=None, summary_revise=None, context_fn=None) -> dict:
    graph_fn = graph_fn or chat_graph_service.build_and_write
    summary_gen = summary_gen or summary_service.generate
    summary_revise = summary_revise or summary_service.revise
    context_fn = context_fn or summary_context_service.assemble

    if command == "create-sales-order":
        return _create(customer_id, model_key, graph_fn, summary_gen, context_fn)
    if command == "edit":
        return _edit(customer_id, args, model_key, summary_revise, context_fn)
    if command == "approve":
        return _approve(customer_id)
    msg = _assistant(customer_id, f"Unknown command: /{command}")
    return {"messages": [msg], "summary": None}
```

Update `_create` signature and Step B:

```python
def _create(customer_id, model_key, graph_fn, summary_gen, context_fn) -> dict:
    if _pending_summary(customer_id):
        msg = _assistant(customer_id,
                         "A summary is already pending. Use /approve or /edit before creating a new one.")
        return {"messages": [msg], "summary": None}

    last = chat_service.get_last_contract_seq(customer_id)
    window = chat_service.chat_messages_since(customer_id, last)
    if not window:
        msg = _assistant(customer_id, "No new messages since the last contract.")
        return {"messages": [msg], "summary": None}

    to_seq = window[-1]["seq"]
    # Step A — graph (must complete before Step B)
    graph_fn(customer_id, window, to_seq, model_key)

    # Step B — summary (grounded on assembled graph context)
    name = _customer_name(customer_id)
    ctx = context_fn(customer_id)
    summary: SOExtractContractList = summary_gen(
        name, window, ctx["product_block"], model_key,
        profile_block=ctx["profile_block"], history_block=ctx["history_block"],
    )
    markdown = render_summary_markdown(summary, name)
    summary_json = summary.model_dump_json(indent=2)
    doc = {
        "customer_id": customer_id, "status": "pending", "model_key": model_key,
        "from_seq": window[0]["seq"], "to_seq": to_seq, "revision": 0,
        "content": summary.model_dump(), "rendered_markdown": markdown,
        "created_at": _now(), "approved_at": None,
    }
    sid = mongo.summaries().insert_one(doc).inserted_id
    doc["_id"] = sid
    card = _assistant(customer_id, markdown, summary_id=str(sid), summary_json=summary_json)
    return {"messages": [card], "summary": _summary_out(doc)}
```

Update `_edit` signature and revise call:

```python
def _edit(customer_id, args, model_key, summary_revise, context_fn) -> dict:
    pending = _pending_summary(customer_id)
    if not pending:
        return {"messages": [_assistant(customer_id, "No pending summary to edit.")], "summary": None}
    if not args:
        return {"messages": [_assistant(customer_id, "Provide edit instructions: /edit <instructions>")],
                "summary": None}

    name = _customer_name(customer_id)
    window = chat_service.chat_messages_since(customer_id, pending["from_seq"] - 1)
    previous = SOExtractContractList(**pending["content"])
    ctx = context_fn(customer_id)
    revised = summary_revise(
        name, previous, args, window, model_key,
        product_block=ctx["product_block"], profile_block=ctx["profile_block"],
        history_block=ctx["history_block"],
    )
    markdown = render_summary_markdown(revised, name)
    summary_json = revised.model_dump_json(indent=2)
    mongo.summaries().update_one(
        {"_id": pending["_id"]},
        {"$set": {"content": revised.model_dump(), "rendered_markdown": markdown,
                  "model_key": model_key},
         "$inc": {"revision": 1}},
    )
    updated = mongo.summaries().find_one({"_id": pending["_id"]})
    card = _assistant(customer_id, markdown, summary_id=str(pending["_id"]), summary_json=summary_json)
    return {"messages": [card], "summary": _summary_out(updated)}
```

Then update the `client` fixture in `tests/api/test_api_endpoints.py` to stub the assembler so the end-to-end command test stays hermetic:

```python
    monkeypatch.setattr(command_service.summary_context_service, "assemble",
                        lambda *a, **k: {"profile_block": None, "history_block": None,
                                         "product_block": None})
```

- [ ] **Step 4: Run the full API suite**

Run: `pytest tests/api -v`
Expected: PASS (all tests, including updated command_service and endpoint tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/command_service.py tests/api/test_command_service.py tests/api/test_api_endpoints.py
git commit -m "feat(api): ground sales-order summaries in assembled graph context"
```

---

### Task 8: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire test suite**

Run: `pytest tests -v`
Expected: PASS. If `tests/test_graph_*` (non-`api`) require external setup, at minimum `pytest tests/api -v` must be fully green.

- [ ] **Step 2: Sanity-check the new module imports**

Run: `python -c "from apps.api.services import summary_context_service, product_graph_service; from graph.product_extractor import extract_product_facts; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit (only if verification produced fixes)**

```bash
git add -A
git commit -m "test: verify graph-grounded summary generation end to end"
```

---

## Self-Review

**Spec coverage:**
- Product graph (global, LLM-derived, aliases + specs) → Tasks 1–2. ✓
- Product graph sync on write → Task 3. ✓
- Profile block read from profile graph → Task 4. ✓
- Context assembly (profile + history + product) → Task 5. ✓
- Summary generate/revise consume context + gap-filling prompt → Task 6. ✓
- command_service wiring for create + edit → Task 7. ✓
- Testing across product graph, context, summary, command, endpoints → Tasks 1–8. ✓
- Out-of-scope items (categories/substitutes/affinity, manual curation, catalog filtering, frontend) are not introduced. ✓

**Type/name consistency:**
- `resync_product(code, description, spec, model_key="openai:5.5", *, extractor=None)` / `remove_product(code)` / `catalog_block()` used identically in Tasks 2, 3, 5. ✓
- `read_block(customer_id)` used in Tasks 4, 5. ✓
- `assemble(customer_id, *, profile_reader, history_reader, product_reader) -> {profile_block, history_block, product_block}` produced in Task 5, consumed in Task 7. ✓
- `generate(..., product_block, ..., *, profile_block, history_block)` and `revise(..., *, product_block, profile_block, history_block)` defined in Task 6, called in Task 7. ✓
- `ProductFacts` fields (`aliases`, `grade`, `packing_size`, `unit`, `attributes`) defined in Task 1, consumed by `_spec_pairs` in Task 2. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step contains full code. ✓
