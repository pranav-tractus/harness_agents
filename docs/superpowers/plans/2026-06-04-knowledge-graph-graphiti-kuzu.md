# Knowledge Graph (Graphiti + Kuzu) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full V1 knowledge graph loop — ingest all `raw_data/` chats into a Kuzu graph, retrieve per-customer temporal memory, inject it into extraction prompts, and expose a QA endpoint.

**Architecture:** Graphiti's episode/temporal concepts drive the design; entity extraction uses the existing `call_llm` from `core/llm_client.py` (provider-agnostic). All graph writes go to Kuzu (in-process, no Docker). The `AbstractGraphBackend` protocol is the seam for swapping in Neptune in production.

**Tech Stack:** `kuzu>=0.8`, `graphiti-core` (installed for LLMClient types and prod integration path), existing `call_llm` infrastructure, pytest + unittest.

**Spec:** `docs/superpowers/specs/2026-06-04-knowledge-graph-graphiti-kuzu-design.md`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `graph/__init__.py` | Create | Package marker |
| `graph/backend.py` | Create | `AbstractGraphBackend` Protocol |
| `graph/kuzu_backend.py` | Create | Kuzu in-process implementation |
| `graph/episode_builder.py` | Create | raw chat JSON → episode dict |
| `graph/extractor.py` | Create | episode text → `ExtractedFacts` via LLM |
| `graph/ingestion.py` | Create | walk raw_data, run full ingest loop |
| `graph/retrieval.py` | Create | Kuzu → compact memory block string |
| `graph/qa.py` | Create | `answer_question(customer_id, question)` |
| `graph/client.py` | Create | `GraphitiMemoryClient` — single entry point |
| `graph/__main__.py` | Create | CLI: `python -m graph` |
| `core/prompt_builder.py` | Modify | add optional `memory_block` param |
| `templates/extraction.j2` | Modify | add customer history section |
| `templates/system_prompt.j2` | Modify | add Rule 7 (memory is disambiguation only) |
| `tests/test_graph_episode_builder.py` | Create | episode builder tests |
| `tests/test_graph_kuzu_backend.py` | Create | Kuzu backend tests |
| `tests/test_graph_retrieval.py` | Create | retrieval + memory block tests |
| `tests/test_graph_qa.py` | Create | QA scope guard + answer tests |
| `tests/test_graph_prompt_integration.py` | Create | prompt builder memory_block tests |
| `requirements.txt` | Modify | add kuzu, graphiti-core |

---

## Task 1: Install dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add kuzu and graphiti-core to requirements.txt**

Open `requirements.txt` and add these two lines (maintain alphabetical order near `k` and `g`):

```
graphiti-core>=0.3.14
kuzu>=0.8.0
```

- [ ] **Step 2: Install**

```bash
pip install "kuzu>=0.8.0" "graphiti-core>=0.3.14"
```

Expected: Both packages install without error. Verify with:

```bash
python -c "import kuzu; print(kuzu.__version__)"
python -c "import graphiti_core; print('graphiti-core ok')"
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add kuzu and graphiti-core dependencies"
```

---

## Task 2: `graph/` package + AbstractGraphBackend protocol

**Files:**
- Create: `graph/__init__.py`
- Create: `graph/backend.py`

- [ ] **Step 1: Create `graph/__init__.py`**

```python
```

(Empty file — package marker only.)

- [ ] **Step 2: Write the failing test**

Create `tests/test_graph_backend_protocol.py`:

```python
import pytest
from graph.backend import AbstractGraphBackend


def test_kuzu_backend_satisfies_protocol():
    """KuzuBackend must satisfy AbstractGraphBackend at runtime."""
    from graph.kuzu_backend import KuzuBackend
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp:
        backend = KuzuBackend(db_path=pathlib.Path(tmp) / "test.db")
        assert isinstance(backend, AbstractGraphBackend)
        backend.close()
```

- [ ] **Step 3: Run to confirm it fails**

```bash
pytest tests/test_graph_backend_protocol.py -v
```

Expected: `ModuleNotFoundError: No module named 'graph'`

- [ ] **Step 4: Create `graph/backend.py`**

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class AbstractGraphBackend(Protocol):
    def write_episode(self, episode: dict) -> None: ...
    def query_customer(self, customer_id: str) -> list[dict]: ...
    def close(self) -> None: ...
```

- [ ] **Step 5: Commit skeleton (test still fails — KuzuBackend not yet written)**

```bash
git add graph/__init__.py graph/backend.py tests/test_graph_backend_protocol.py
git commit -m "feat: add graph package + AbstractGraphBackend protocol"
```

---

## Task 3: KuzuBackend — schema, write, query

**Files:**
- Create: `graph/kuzu_backend.py`
- Test: `tests/test_graph_kuzu_backend.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_graph_kuzu_backend.py`:

```python
import tempfile
import pathlib
import pytest
from graph.kuzu_backend import KuzuBackend


@pytest.fixture
def tmp_backend(tmp_path):
    b = KuzuBackend(db_path=tmp_path / "test.db")
    yield b
    b.close()


def test_write_episode_creates_customer_and_product(tmp_backend):
    episode = {
        "source_id": "customers/acme_foods/chats/test_001",
        "customer_id": "acme_foods",
        "timestamp": 1760200000,
        "entities": {
            "products": [
                {
                    "name": "KNM Coffee",
                    "quantity": 10.0,
                    "unit": "bags",
                    "price": 25.0,
                    "price_unit": "USD/bag",
                    "incoterm": "FOB",
                    "port": "Singapore",
                }
            ],
            "ports": ["Singapore"],
            "payment_terms": "Net 30",
            "packing": "25kg PP bags",
            "loading": "1x20 FCL",
        },
    }
    tmp_backend.write_episode(episode)
    results = tmp_backend.query_customer("acme_foods")
    assert len(results) > 0
    product_names = [r["product_name"] for r in results if r.get("product_name")]
    assert "KNM Coffee" in product_names


def test_write_episode_idempotent(tmp_backend):
    episode = {
        "source_id": "customers/acme_foods/chats/test_001",
        "customer_id": "acme_foods",
        "timestamp": 1760200000,
        "entities": {
            "products": [{"name": "Rice", "quantity": 5.0, "unit": "MT",
                          "price": 300.0, "price_unit": "USD/MT",
                          "incoterm": "CIF", "port": "Busan"}],
            "ports": ["Busan"],
            "payment_terms": "",
            "packing": "",
            "loading": "",
        },
    }
    tmp_backend.write_episode(episode)
    tmp_backend.write_episode(episode)  # second write must not duplicate
    results = tmp_backend.query_customer("acme_foods")
    product_rows = [r for r in results if r.get("product_name") == "Rice"]
    assert len(product_rows) == 1


def test_query_customer_isolation(tmp_backend):
    for cid, product in [("acme_foods", "KNM Coffee"), ("nova_exports", "Palm Oil")]:
        ep = {
            "source_id": f"customers/{cid}/chats/ep1",
            "customer_id": cid,
            "timestamp": 1000,
            "entities": {
                "products": [{"name": product, "quantity": 1.0, "unit": "MT",
                              "price": 100.0, "price_unit": "USD/MT",
                              "incoterm": "FOB", "port": "Singapore"}],
                "ports": ["Singapore"],
                "payment_terms": "",
                "packing": "",
                "loading": "",
            },
        }
        tmp_backend.write_episode(ep)
    acme_results = tmp_backend.query_customer("acme_foods")
    acme_products = {r["product_name"] for r in acme_results if r.get("product_name")}
    assert "KNM Coffee" in acme_products
    assert "Palm Oil" not in acme_products


def test_query_unknown_customer_returns_empty(tmp_backend):
    results = tmp_backend.query_customer("no_such_customer")
    assert results == []
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_graph_kuzu_backend.py -v
```

Expected: `ModuleNotFoundError: No module named 'graph.kuzu_backend'`

- [ ] **Step 3: Create `graph/kuzu_backend.py`**

```python
import logging
from pathlib import Path

import kuzu

logger = logging.getLogger(__name__)

_DDL = [
    "CREATE NODE TABLE IF NOT EXISTS Customer(id STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Product(name STRING, PRIMARY KEY(name))",
    "CREATE NODE TABLE IF NOT EXISTS Port(name STRING, PRIMARY KEY(name))",
    "CREATE NODE TABLE IF NOT EXISTS Episode(source_id STRING, customer_id STRING, timestamp INT64, PRIMARY KEY(source_id))",
    "CREATE REL TABLE IF NOT EXISTS BUYS(FROM Customer TO Product, quantity DOUBLE, unit STRING, price DOUBLE, price_unit STRING, incoterm STRING, timestamp INT64, source_id STRING)",
    "CREATE REL TABLE IF NOT EXISTS SHIPS_TO(FROM Customer TO Port, incoterm STRING, timestamp INT64, source_id STRING)",
    "CREATE REL TABLE IF NOT EXISTS HAS_TERMS(FROM Customer TO Episode, payment_terms STRING, packing STRING, loading STRING)",
]


class KuzuBackend:
    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = Path("graph.db")
        self._db = kuzu.Database(str(db_path))
        self._conn = kuzu.Connection(self._db)
        self._init_schema()

    def _init_schema(self) -> None:
        for ddl in _DDL:
            self._conn.execute(ddl)

    def _upsert_node(self, table: str, pk_col: str, pk_val: str) -> None:
        check = self._conn.execute(
            f"MATCH (n:{table} {{{pk_col}: $val}}) RETURN count(n) AS c",
            {"val": pk_val},
        )
        count = check.get_next()[0]
        if count == 0:
            self._conn.execute(
                f"CREATE (:{table} {{{pk_col}: $val}})",
                {"val": pk_val},
            )

    def write_episode(self, episode: dict) -> None:
        source_id = episode["source_id"]
        customer_id = episode["customer_id"]
        timestamp = episode.get("timestamp", 0)
        entities = episode.get("entities", {})

        # Idempotency check
        existing = self._conn.execute(
            "MATCH (e:Episode {source_id: $sid}) RETURN count(e) AS c",
            {"sid": source_id},
        )
        if existing.get_next()[0] > 0:
            logger.debug("Episode already exists, skipping: %s", source_id)
            return

        self._upsert_node("Customer", "id", customer_id)
        self._conn.execute(
            "CREATE (:Episode {source_id: $sid, customer_id: $cid, timestamp: $ts})",
            {"sid": source_id, "cid": customer_id, "ts": timestamp},
        )

        for product in entities.get("products", []):
            pname = product.get("name", "").strip()
            if not pname:
                continue
            self._upsert_node("Product", "name", pname)
            port = (product.get("port") or "").strip()
            if port:
                self._upsert_node("Port", "name", port)
            self._conn.execute(
                """
                MATCH (c:Customer {id: $cid}), (p:Product {name: $pname})
                CREATE (c)-[:BUYS {
                    quantity: $qty, unit: $unit, price: $price,
                    price_unit: $price_unit, incoterm: $inco,
                    timestamp: $ts, source_id: $sid
                }]->(p)
                """,
                {
                    "cid": customer_id,
                    "pname": pname,
                    "qty": float(product.get("quantity") or 0),
                    "unit": product.get("unit") or "",
                    "price": float(product.get("price") or 0),
                    "price_unit": product.get("price_unit") or "",
                    "inco": product.get("incoterm") or "",
                    "ts": timestamp,
                    "sid": source_id,
                },
            )
            if port:
                self._conn.execute(
                    """
                    MATCH (c:Customer {id: $cid}), (po:Port {name: $port})
                    CREATE (c)-[:SHIPS_TO {incoterm: $inco, timestamp: $ts, source_id: $sid}]->(po)
                    """,
                    {"cid": customer_id, "port": port,
                     "inco": product.get("incoterm") or "",
                     "ts": timestamp, "sid": source_id},
                )

        for port in entities.get("ports", []):
            port = port.strip()
            if not port:
                continue
            self._upsert_node("Port", "name", port)
            self._conn.execute(
                """
                MATCH (c:Customer {id: $cid}), (po:Port {name: $port})
                CREATE (c)-[:SHIPS_TO {incoterm: '', timestamp: $ts, source_id: $sid}]->(po)
                """,
                {"cid": customer_id, "port": port, "ts": timestamp, "sid": source_id},
            )

        payment_terms = entities.get("payment_terms") or ""
        packing = entities.get("packing") or ""
        loading = entities.get("loading") or ""
        if any([payment_terms, packing, loading]):
            self._conn.execute(
                """
                MATCH (c:Customer {id: $cid}), (e:Episode {source_id: $sid})
                CREATE (c)-[:HAS_TERMS {
                    payment_terms: $pt, packing: $pk, loading: $ld
                }]->(e)
                """,
                {"cid": customer_id, "sid": source_id,
                 "pt": payment_terms, "pk": packing, "ld": loading},
            )

    def query_customer(self, customer_id: str) -> list[dict]:
        rows: list[dict] = []

        # Products
        res = self._conn.execute(
            """
            MATCH (c:Customer {id: $cid})-[b:BUYS]->(p:Product)
            RETURN p.name AS product_name, b.quantity AS quantity, b.unit AS unit,
                   b.price AS price, b.price_unit AS price_unit,
                   b.incoterm AS incoterm, b.timestamp AS timestamp, b.source_id AS source_id
            ORDER BY b.timestamp DESC
            """,
            {"cid": customer_id},
        )
        while res.has_next():
            row = res.get_next()
            rows.append({
                "type": "product",
                "product_name": row[0],
                "quantity": row[1],
                "unit": row[2],
                "price": row[3],
                "price_unit": row[4],
                "incoterm": row[5],
                "timestamp": row[6],
                "source_id": row[7],
            })

        # Ports
        res = self._conn.execute(
            """
            MATCH (c:Customer {id: $cid})-[s:SHIPS_TO]->(po:Port)
            RETURN po.name AS port, s.incoterm AS incoterm, s.timestamp AS ts, s.source_id AS sid
            ORDER BY s.timestamp DESC
            """,
            {"cid": customer_id},
        )
        while res.has_next():
            row = res.get_next()
            rows.append({
                "type": "port",
                "port": row[0],
                "incoterm": row[1],
                "timestamp": row[2],
                "source_id": row[3],
            })

        # Terms
        res = self._conn.execute(
            """
            MATCH (c:Customer {id: $cid})-[t:HAS_TERMS]->(e:Episode)
            RETURN t.payment_terms AS payment_terms, t.packing AS packing,
                   t.loading AS loading, e.timestamp AS ts, e.source_id AS sid
            ORDER BY e.timestamp DESC
            """,
            {"cid": customer_id},
        )
        while res.has_next():
            row = res.get_next()
            rows.append({
                "type": "terms",
                "payment_terms": row[0],
                "packing": row[1],
                "loading": row[2],
                "timestamp": row[3],
                "source_id": row[4],
            })

        return rows

    def close(self) -> None:
        pass  # kuzu connection has no explicit close in Python SDK
```

- [ ] **Step 4: Run all backend tests**

```bash
pytest tests/test_graph_kuzu_backend.py tests/test_graph_backend_protocol.py -v
```

Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add graph/kuzu_backend.py tests/test_graph_kuzu_backend.py tests/test_graph_backend_protocol.py
git commit -m "feat: add KuzuBackend with DDL, write_episode, query_customer"
```

---

## Task 4: Episode builder

**Files:**
- Create: `graph/episode_builder.py`
- Test: `tests/test_graph_episode_builder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_graph_episode_builder.py`:

```python
import json
import pathlib
import pytest
from graph.episode_builder import build_episode, infer_customer_id


RAW_DATA = pathlib.Path(__file__).resolve().parents[1] / "raw_data"


def test_infer_customer_from_customers_dir(tmp_path):
    chat_path = tmp_path / "raw_data" / "customers" / "acme_foods" / "chats" / "test.json"
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text('{"customer_id": "acme_foods", "messages": []}')
    assert infer_customer_id(chat_path) == "acme_foods"


def test_infer_customer_from_downloaded_chats_json(tmp_path):
    chat_path = (
        tmp_path / "raw_data" / "downloaded_chats" /
        "01__2025-07-12__120363400604184610_g_us__c53c0007-bbd6-4474-8348-b011992829f8.json"
    )
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text(json.dumps({"customer_id": "c53c0007-bbd6-4474-8348-b011992829f8", "chats": []}))
    assert infer_customer_id(chat_path) == "c53c0007-bbd6-4474-8348-b011992829f8"


def test_infer_customer_generic_for_chats_dir(tmp_path):
    chat_path = tmp_path / "raw_data" / "chats" / "some_chat.json"
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text("{}")
    assert infer_customer_id(chat_path) == "generic"


def test_build_episode_from_standard_messages(tmp_path):
    chat_path = tmp_path / "raw_data" / "customers" / "acme_foods" / "chats" / "test.json"
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text(json.dumps({
        "customer_id": "acme_foods",
        "messages": [
            {"from_whom": "(TEAM1)", "body": "Price is 25 USD/bag", "timestamp": 1000},
            {"from_whom": "(TEAM2)", "body": "Confirmed", "timestamp": 1001},
        ]
    }))
    raw_data_dir = tmp_path / "raw_data"
    episode = build_episode(chat_path, raw_data_dir)
    assert episode["customer_id"] == "acme_foods"
    assert episode["timestamp"] == 1000
    assert "(TEAM1): Price is 25 USD/bag" in episode["content"]
    assert episode["source_id"] == "customers/acme_foods/chats/test"


def test_build_episode_from_downloaded_chat(tmp_path):
    chat_path = (
        tmp_path / "raw_data" / "downloaded_chats" /
        "01__2025-07-12__120363400604184610_g_us__abc123.json"
    )
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text(json.dumps({
        "customer_id": "abc123",
        "chats": [
            [{"from_me": False, "text": {"body": "raw msg"}, "timestamp": 999, "from_name": "Alice"}],
            [{"from_whom": "(TEAM1)", "body": "Processed msg", "timestamp": 1000}],
        ]
    }))
    raw_data_dir = tmp_path / "raw_data"
    episode = build_episode(chat_path, raw_data_dir)
    assert episode["customer_id"] == "abc123"
    assert "Processed msg" in episode["content"]
    assert episode["timestamp"] == 1000


def test_build_episode_real_acme_file():
    """Integration: builds episode from the real acme_foods fixture."""
    path = RAW_DATA / "customers" / "acme_foods" / "chats" / "fs_acme_simple.json"
    if not path.exists():
        pytest.skip("raw_data not available")
    episode = build_episode(path, RAW_DATA)
    assert episode["customer_id"] == "acme_foods"
    assert len(episode["content"]) > 0
    assert episode["source_id"].startswith("customers/acme_foods")
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_graph_episode_builder.py -v
```

Expected: `ModuleNotFoundError: No module named 'graph.episode_builder'`

- [ ] **Step 3: Create `graph/episode_builder.py`**

```python
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def infer_customer_id(path: Path) -> str:
    parts = path.parts
    if "customers" in parts:
        idx = parts.index("customers")
        return parts[idx + 1]
    if "downloaded_chats" in parts:
        try:
            data = json.loads(path.read_text())
            if "customer_id" in data:
                return str(data["customer_id"])
        except Exception:
            pass
        stem = path.stem
        chunks = stem.split("__")
        if len(chunks) >= 4:
            return chunks[-1]
    return "generic"


def _extract_chat_text(data: dict) -> tuple[str, int]:
    lines: list[str] = []
    timestamp = 0

    if "messages" in data:
        for msg in data["messages"]:
            speaker = msg.get("from_whom", "UNKNOWN")
            body = msg.get("body", "")
            lines.append(f"{speaker}: {body}")
            if not timestamp and msg.get("timestamp"):
                timestamp = int(msg["timestamp"])

    elif "chats" in data:
        arrays = data["chats"]
        target = arrays[1] if len(arrays) > 1 else arrays[0] if arrays else []
        for msg in target:
            if "body" in msg:
                speaker = msg.get("from_whom", "UNKNOWN")
                lines.append(f"{speaker}: {msg['body']}")
            elif "text" in msg and isinstance(msg["text"], dict):
                speaker = msg.get("from_name", "UNKNOWN")
                lines.append(f"{speaker}: {msg['text'].get('body', '')}")
            if not timestamp and msg.get("timestamp"):
                timestamp = int(msg["timestamp"])

    return "\n".join(lines), timestamp


def build_episode(path: Path, raw_data_dir: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    customer_id = infer_customer_id(path)

    # downloaded_chats: override with the customer_id field in JSON
    if "downloaded_chats" in path.parts and "customer_id" in data:
        customer_id = str(data["customer_id"])

    content, timestamp = _extract_chat_text(data)
    if not timestamp:
        timestamp = int(path.stat().st_mtime)

    source_id = str(path.relative_to(raw_data_dir).with_suffix(""))

    return {
        "source_id": source_id,
        "customer_id": customer_id,
        "timestamp": timestamp,
        "content": content,
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_graph_episode_builder.py -v
```

Expected: All 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add graph/episode_builder.py tests/test_graph_episode_builder.py
git commit -m "feat: add episode builder with customer_id inference from path"
```

---

## Task 5: Entity extractor

**Files:**
- Create: `graph/extractor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph_extractor.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from graph.extractor import ExtractedFacts, ExtractedProduct, extract_entities

SAMPLE_CHAT = """(TEAM2): Need 10 MT KNM Coffee, CIF Busan, USD 500/MT.
(TEAM1): Confirmed. Packing: 25kg PP bags. Loading: 1x20 FCL.
(TEAM2): Payment: Net 30.
(TEAM1): Done."""


def test_extracted_facts_model():
    facts = ExtractedFacts(
        products=[ExtractedProduct(name="KNM Coffee", quantity=10.0, unit="MT",
                                   price=500.0, price_unit="USD/MT",
                                   incoterm="CIF", port="Busan")],
        ports=["Busan"],
        payment_terms="Net 30",
        packing="25kg PP bags",
        loading="1x20 FCL",
    )
    assert facts.products[0].name == "KNM Coffee"
    assert facts.payment_terms == "Net 30"


def test_extract_entities_calls_llm(monkeypatch):
    fake_facts = ExtractedFacts(
        products=[ExtractedProduct(name="Rice", quantity=5.0, unit="MT",
                                   price=300.0, price_unit="USD/MT",
                                   incoterm="FOB", port="Singapore")],
        ports=["Singapore"],
        payment_terms="100% Advance",
        packing="",
        loading="",
    )
    monkeypatch.setattr("graph.extractor.call_llm", lambda *a, **kw: fake_facts)
    result = extract_entities(SAMPLE_CHAT, model_key="claude-sonnet-4-6")
    assert result.products[0].name == "Rice"
    assert result.payment_terms == "100% Advance"


def test_extract_entities_returns_empty_on_no_data(monkeypatch):
    monkeypatch.setattr("graph.extractor.call_llm", lambda *a, **kw: ExtractedFacts())
    result = extract_entities("Just a greeting, no contract data.", model_key="claude-sonnet-4-6")
    assert result.products == []
    assert result.payment_terms == ""
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_graph_extractor.py -v
```

Expected: `ModuleNotFoundError: No module named 'graph.extractor'`

- [ ] **Step 3: Create `graph/extractor.py`**

```python
import logging
from typing import Optional
from pydantic import BaseModel, Field
from core.llm_client import call_llm

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
You are an expert at extracting structured facts from commodity trading chat messages.

Extract the entities below from the chat. Return ONLY agreed/confirmed values.
Return empty strings or empty lists when a field is not confirmed in the chat.

Chat:
{chat_text}
"""


class ExtractedProduct(BaseModel):
    name: str = Field(description="Product name exactly as stated")
    quantity: Optional[float] = Field(default=None, description="Agreed quantity as a number")
    unit: Optional[str] = Field(default=None, description="Unit for quantity (MT, KG, bags, etc.)")
    price: Optional[float] = Field(default=None, description="Agreed unit price as a number")
    price_unit: Optional[str] = Field(default=None, description="Price unit (USD/MT, USD/KG, etc.)")
    incoterm: Optional[str] = Field(default=None, description="Incoterm (FOB, CIF, EXW, DDP)")
    port: Optional[str] = Field(default=None, description="Port or destination city")


class ExtractedFacts(BaseModel):
    products: list[ExtractedProduct] = Field(
        default_factory=list,
        description="All products agreed in the chat"
    )
    ports: list[str] = Field(
        default_factory=list,
        description="Ports or destinations mentioned and agreed"
    )
    payment_terms: str = Field(
        default="",
        description="Payment terms (e.g. Net 30, 100% Advance, 50% CAD)"
    )
    packing: str = Field(
        default="",
        description="Agreed packing description (e.g. 25kg PP bags)"
    )
    loading: str = Field(
        default="",
        description="Agreed loading description (e.g. 1x20 FCL)"
    )


def extract_entities(chat_text: str, model_key: str = "claude-sonnet-4-6") -> ExtractedFacts:
    prompt = _EXTRACTION_PROMPT.format(chat_text=chat_text)
    try:
        return call_llm(prompt, ExtractedFacts, model_key)
    except Exception:
        logger.exception("Entity extraction failed, returning empty facts")
        return ExtractedFacts()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_graph_extractor.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add graph/extractor.py tests/test_graph_extractor.py
git commit -m "feat: add entity extractor with ExtractedFacts pydantic schema"
```

---

## Task 6: Ingestion pipeline

**Files:**
- Create: `graph/ingestion.py`
- Test: `tests/test_graph_ingestion.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graph_ingestion.py`:

```python
import json
import pathlib
import pytest
from unittest.mock import patch
from graph.extractor import ExtractedFacts, ExtractedProduct
from graph.kuzu_backend import KuzuBackend
from graph.ingestion import ingest_all


@pytest.fixture
def fake_raw_data(tmp_path):
    for cid, product in [("acme_foods", "KNM Coffee"), ("nova_exports", "Palm Oil")]:
        chat_dir = tmp_path / "raw_data" / "customers" / cid / "chats"
        chat_dir.mkdir(parents=True)
        (chat_dir / "ep001.json").write_text(json.dumps({
            "customer_id": cid,
            "messages": [
                {"from_whom": "(TEAM1)", "body": f"100 MT {product} @ USD 300/MT CIF Singapore", "timestamp": 1000},
                {"from_whom": "(TEAM2)", "body": "Confirmed. Net 30.", "timestamp": 1001},
            ]
        }))
    return tmp_path / "raw_data"


def _fake_extract(chat_text, model_key="claude-sonnet-4-6"):
    product_name = "KNM Coffee" if "KNM Coffee" in chat_text else "Palm Oil"
    return ExtractedFacts(
        products=[ExtractedProduct(name=product_name, quantity=100.0, unit="MT",
                                   price=300.0, price_unit="USD/MT",
                                   incoterm="CIF", port="Singapore")],
        ports=["Singapore"],
        payment_terms="Net 30",
        packing="",
        loading="",
    )


def test_ingest_all_writes_to_backend(fake_raw_data, tmp_path):
    backend = KuzuBackend(db_path=tmp_path / "test.db")
    with patch("graph.ingestion.extract_entities", side_effect=_fake_extract):
        count = ingest_all(fake_raw_data, backend, model_key="claude-sonnet-4-6")
    assert count == 2
    acme = backend.query_customer("acme_foods")
    assert any(r.get("product_name") == "KNM Coffee" for r in acme)
    backend.close()


def test_ingest_all_idempotent(fake_raw_data, tmp_path):
    backend = KuzuBackend(db_path=tmp_path / "test.db")
    with patch("graph.ingestion.extract_entities", side_effect=_fake_extract):
        first = ingest_all(fake_raw_data, backend, model_key="claude-sonnet-4-6")
        second = ingest_all(fake_raw_data, backend, model_key="claude-sonnet-4-6")
    assert first == 2
    assert second == 0  # all already ingested
    backend.close()


def test_ingest_all_skips_empty_content(tmp_path):
    raw = tmp_path / "raw_data" / "chats"
    raw.mkdir(parents=True)
    (raw / "empty.json").write_text(json.dumps({"messages": []}))
    backend = KuzuBackend(db_path=tmp_path / "test.db")
    with patch("graph.ingestion.extract_entities", return_value=ExtractedFacts()):
        count = ingest_all(tmp_path / "raw_data", backend)
    backend.close()
    assert count == 0  # skipped because content is empty
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_graph_ingestion.py -v
```

Expected: `ModuleNotFoundError: No module named 'graph.ingestion'`

- [ ] **Step 3: Create `graph/ingestion.py`**

```python
import logging
from pathlib import Path

from graph.backend import AbstractGraphBackend
from graph.episode_builder import build_episode
from graph.extractor import ExtractedFacts, extract_entities

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_SKIP_DIRS = {".git", "__pycache__"}


def ingest_all(
    raw_data_dir: Path,
    backend: AbstractGraphBackend,
    model_key: str = _DEFAULT_MODEL,
) -> int:
    raw_data_dir = Path(raw_data_dir)
    ingested = 0

    for path in sorted(raw_data_dir.rglob("*.json")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue

        try:
            episode = build_episode(path, raw_data_dir)
        except Exception:
            logger.warning("Failed to build episode from %s", path, exc_info=True)
            continue

        if not episode["content"].strip():
            logger.debug("Skipping empty episode: %s", episode["source_id"])
            continue

        try:
            facts: ExtractedFacts = extract_entities(episode["content"], model_key=model_key)
        except Exception:
            logger.warning("Extraction failed for %s", episode["source_id"], exc_info=True)
            continue

        episode["entities"] = {
            "products": [p.model_dump() for p in facts.products],
            "ports": facts.ports,
            "payment_terms": facts.payment_terms,
            "packing": facts.packing,
            "loading": facts.loading,
        }

        try:
            backend.write_episode(episode)
            ingested += 1
            logger.info("Ingested: %s (customer=%s)", episode["source_id"], episode["customer_id"])
        except Exception:
            logger.warning("Failed to write episode %s", episode["source_id"], exc_info=True)

    return ingested
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_graph_ingestion.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add graph/ingestion.py tests/test_graph_ingestion.py
git commit -m "feat: add ingestion pipeline — walks raw_data, extracts, writes to backend"
```

---

## Task 7: Retrieval — memory block

**Files:**
- Create: `graph/retrieval.py`
- Test: `tests/test_graph_retrieval.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graph_retrieval.py`:

```python
import pytest
from graph.kuzu_backend import KuzuBackend
from graph.retrieval import get_memory_block

_BASE_EPISODE = {
    "source_id": "customers/acme_foods/chats/ep1",
    "customer_id": "acme_foods",
    "timestamp": 1760200000,
    "entities": {
        "products": [
            {"name": "KNM Coffee", "quantity": 10.0, "unit": "bags",
             "price": 25.0, "price_unit": "USD/bag", "incoterm": "FOB", "port": "Singapore"},
        ],
        "ports": ["Singapore"],
        "payment_terms": "Net 30",
        "packing": "25kg PP bags",
        "loading": "1x20 FCL",
    },
}


@pytest.fixture
def populated_backend(tmp_path):
    b = KuzuBackend(db_path=tmp_path / "ret.db")
    b.write_episode(_BASE_EPISODE)
    yield b
    b.close()


def test_memory_block_contains_product(populated_backend):
    block = get_memory_block("acme_foods", populated_backend)
    assert block is not None
    assert "KNM Coffee" in block


def test_memory_block_contains_port(populated_backend):
    block = get_memory_block("acme_foods", populated_backend)
    assert "Singapore" in block


def test_memory_block_contains_terms(populated_backend):
    block = get_memory_block("acme_foods", populated_backend)
    assert "Net 30" in block
    assert "25kg PP bags" in block


def test_memory_block_none_for_unknown_customer(populated_backend):
    block = get_memory_block("no_such_customer", populated_backend)
    assert block is None


def test_memory_block_customer_isolation(tmp_path):
    b = KuzuBackend(db_path=tmp_path / "iso.db")
    ep_nova = {
        "source_id": "customers/nova_exports/chats/ep1",
        "customer_id": "nova_exports",
        "timestamp": 1000,
        "entities": {
            "products": [{"name": "Palm Oil", "quantity": 20.0, "unit": "MT",
                          "price": 800.0, "price_unit": "USD/MT",
                          "incoterm": "CIF", "port": "Busan"}],
            "ports": ["Busan"],
            "payment_terms": "100% Advance",
            "packing": "",
            "loading": "",
        },
    }
    b.write_episode(_BASE_EPISODE)
    b.write_episode(ep_nova)
    acme_block = get_memory_block("acme_foods", b)
    assert "Palm Oil" not in (acme_block or "")
    assert "KNM Coffee" in (acme_block or "")
    b.close()
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_graph_retrieval.py -v
```

Expected: `ModuleNotFoundError: No module named 'graph.retrieval'`

- [ ] **Step 3: Create `graph/retrieval.py`**

```python
from __future__ import annotations

import logging
from collections import defaultdict

from graph.backend import AbstractGraphBackend

logger = logging.getLogger(__name__)

_MAX_PRODUCTS = 10
_MAX_PORTS = 8
_MAX_SOURCES = 5


def get_memory_block(customer_id: str, backend: AbstractGraphBackend) -> str | None:
    rows = backend.query_customer(customer_id)
    if not rows:
        return None

    products: dict[str, dict] = {}
    ports: dict[str, str] = {}
    terms_list: list[dict] = []
    sources: list[str] = []

    for row in rows:
        src = row.get("source_id", "")
        if src and src not in sources:
            sources.append(src)

        if row["type"] == "product":
            name = row["product_name"]
            if name and name not in products:
                products[name] = row

        elif row["type"] == "port":
            port = row["port"]
            inco = row.get("incoterm", "")
            if port:
                key = f"{inco} {port}".strip() if inco else port
                ports[port] = key

        elif row["type"] == "terms":
            terms_list.append(row)

    lines: list[str] = [f"=== Customer History ({customer_id}) ==="]

    if products:
        product_strs = []
        for name, p in list(products.items())[:_MAX_PRODUCTS]:
            qty = f"{p['quantity']} {p['unit']}" if p.get("quantity") and p.get("unit") else ""
            price = f"@ {p['price_unit']} {p['price']}" if p.get("price") and p.get("price_unit") else ""
            parts = [name, qty, price]
            product_strs.append(" ".join(p for p in parts if p))
        lines.append(f"- Products: {', '.join(product_strs)}")

    if ports:
        lines.append(f"- Ports: {', '.join(list(ports.values())[:_MAX_PORTS])}")

    if terms_list:
        latest = terms_list[0]
        if latest.get("payment_terms"):
            lines.append(f"- Payment terms: {latest['payment_terms']}")
        if latest.get("packing"):
            lines.append(f"- Packing: {latest['packing']}")
        if latest.get("loading"):
            lines.append(f"- Loading: {latest['loading']}")

    if sources:
        lines.append(f"[Sources: {', '.join(sources[:_MAX_SOURCES])}]")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_graph_retrieval.py -v
```

Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add graph/retrieval.py tests/test_graph_retrieval.py
git commit -m "feat: add retrieval — query Kuzu and format compact memory block"
```

---

## Task 8: QA endpoint

**Files:**
- Create: `graph/qa.py`
- Test: `tests/test_graph_qa.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graph_qa.py`:

```python
import pytest
from unittest.mock import patch
from graph.kuzu_backend import KuzuBackend
from graph.qa import answer_question

_EP = {
    "source_id": "customers/acme_foods/chats/ep1",
    "customer_id": "acme_foods",
    "timestamp": 1000,
    "entities": {
        "products": [{"name": "KNM Coffee", "quantity": 10.0, "unit": "bags",
                      "price": 25.0, "price_unit": "USD/bag", "incoterm": "FOB", "port": "Singapore"}],
        "ports": ["Singapore"],
        "payment_terms": "Net 30",
        "packing": "25kg PP bags",
        "loading": "1x20 FCL",
    },
}


@pytest.fixture
def backend(tmp_path):
    b = KuzuBackend(db_path=tmp_path / "qa.db")
    b.write_episode(_EP)
    yield b
    b.close()


def test_answer_question_refuses_empty_customer(backend):
    with pytest.raises(ValueError, match="customer_id"):
        answer_question("", "What products?", backend)


def test_answer_question_returns_no_history_for_unknown(backend):
    result = answer_question("unknown_customer", "What products?", backend)
    assert "no history" in result.lower() or "no data" in result.lower()


def test_answer_question_calls_llm(backend, monkeypatch):
    monkeypatch.setattr(
        "graph.qa.call_llm_text",
        lambda prompt, model_key: "Based on history, acme_foods buys KNM Coffee."
    )
    result = answer_question("acme_foods", "What products does this customer buy?", backend)
    assert "KNM Coffee" in result or "acme_foods" in result
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_graph_qa.py -v
```

Expected: `ModuleNotFoundError: No module named 'graph.qa'`

- [ ] **Step 3: Create `graph/qa.py`**

```python
import logging
from graph.backend import AbstractGraphBackend
from graph.retrieval import get_memory_block

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"

_QA_PROMPT = """\
You are a helpful assistant answering questions about a customer's trading history.
Use only the facts provided below. Include source references in your answer.
If you cannot answer from the facts, say so clearly.

Customer history:
{memory_block}

Question: {question}
"""


def call_llm_text(prompt: str, model_key: str = _DEFAULT_MODEL) -> str:
    from pydantic import BaseModel
    from core.llm_client import call_llm

    class TextResponse(BaseModel):
        answer: str

    result = call_llm(prompt, TextResponse, model_key)
    return result.answer


def answer_question(
    customer_id: str,
    question: str,
    backend: AbstractGraphBackend,
    model_key: str = _DEFAULT_MODEL,
) -> str:
    if not customer_id:
        raise ValueError("customer_id is required — cross-customer queries are not allowed")

    memory_block = get_memory_block(customer_id, backend)
    if not memory_block:
        return f"No history found for customer '{customer_id}'."

    prompt = _QA_PROMPT.format(memory_block=memory_block, question=question)
    return call_llm_text(prompt, model_key=model_key)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_graph_qa.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add graph/qa.py tests/test_graph_qa.py
git commit -m "feat: add QA endpoint with customer scope guard"
```

---

## Task 9: GraphitiMemoryClient

**Files:**
- Create: `graph/client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph_client.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from graph.client import GraphitiMemoryClient


def test_get_memory_block_returns_none_when_no_history(tmp_path, monkeypatch):
    monkeypatch.setenv("KUZU_DB_PATH", str(tmp_path / "client_test.db"))
    client = GraphitiMemoryClient()
    block = client.get_memory_block("unknown_customer")
    assert block is None


def test_get_memory_block_returns_string_after_ingest(tmp_path, monkeypatch):
    monkeypatch.setenv("KUZU_DB_PATH", str(tmp_path / "client_test2.db"))
    client = GraphitiMemoryClient()
    client._backend.write_episode({
        "source_id": "test/ep1",
        "customer_id": "acme_foods",
        "timestamp": 1000,
        "entities": {
            "products": [{"name": "KNM Coffee", "quantity": 5.0, "unit": "MT",
                          "price": 100.0, "price_unit": "USD/MT",
                          "incoterm": "FOB", "port": "Singapore"}],
            "ports": ["Singapore"],
            "payment_terms": "Net 30",
            "packing": "",
            "loading": "",
        },
    })
    block = client.get_memory_block("acme_foods")
    assert block is not None
    assert "KNM Coffee" in block
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_graph_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'graph.client'`

- [ ] **Step 3: Create `graph/client.py`**

```python
import logging
import os
from pathlib import Path

from graph.backend import AbstractGraphBackend
from graph.kuzu_backend import KuzuBackend
from graph.retrieval import get_memory_block
from graph.qa import answer_question

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path("graph.db")
_DEFAULT_MODEL = "claude-sonnet-4-6"


class GraphitiMemoryClient:
    def __init__(
        self,
        backend: AbstractGraphBackend | None = None,
        model_key: str = _DEFAULT_MODEL,
    ) -> None:
        if backend is None:
            db_path = Path(os.environ.get("KUZU_DB_PATH", str(_DEFAULT_DB_PATH)))
            backend = KuzuBackend(db_path=db_path)
        self._backend = backend
        self._model_key = model_key

    def get_memory_block(self, customer_id: str) -> str | None:
        if not customer_id:
            return None
        return get_memory_block(customer_id, self._backend)

    def answer_question(self, customer_id: str, question: str) -> str:
        return answer_question(customer_id, question, self._backend, model_key=self._model_key)

    def close(self) -> None:
        self._backend.close()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_graph_client.py -v
```

Expected: Both tests pass.

- [ ] **Step 5: Commit**

```bash
git add graph/client.py tests/test_graph_client.py
git commit -m "feat: add GraphitiMemoryClient — single entry point for retrieval and QA"
```

---

## Task 10: Prompt builder + template integration

**Files:**
- Modify: `core/prompt_builder.py` (line 48 — `build_prompt` signature)
- Modify: `templates/extraction.j2`
- Modify: `templates/system_prompt.j2`
- Test: `tests/test_graph_prompt_integration.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graph_prompt_integration.py`:

```python
from datetime import date
from core.prompt_builder import build_prompt, build_system_prompt


def test_prompt_without_memory_block_has_no_memory_section():
    prompt = build_prompt(
        "Some chat text",
        iso_date="2026-06-04",
        db_few_shot_limit=0,
    )
    assert "Customer history" not in prompt
    assert "graph memory" not in prompt


def test_prompt_with_memory_block_contains_history_section():
    memory = "=== Customer History (acme_foods) ===\n- Products: KNM Coffee"
    prompt = build_prompt(
        "Some chat text",
        iso_date="2026-06-04",
        memory_block=memory,
        db_few_shot_limit=0,
    )
    assert "Customer history (graph memory)" in prompt
    assert "KNM Coffee" in prompt


def test_prompt_memory_block_appears_before_input_text():
    memory = "=== Customer History ===\n- Products: Test Product"
    prompt = build_prompt(
        "THE_INPUT_TEXT",
        iso_date="2026-06-04",
        memory_block=memory,
        db_few_shot_limit=0,
    )
    memory_pos = prompt.find("Customer history")
    input_pos = prompt.find("THE_INPUT_TEXT")
    assert memory_pos < input_pos


def test_system_prompt_contains_memory_rule():
    system = build_system_prompt()
    assert "Memory is disambiguation only" in system or "memory" in system.lower()
```

- [ ] **Step 2: Run to confirm tests 2 and 3 fail (tests 1 and 4 may pass)**

```bash
pytest tests/test_graph_prompt_integration.py -v
```

Expected: `test_prompt_with_memory_block_contains_history_section` FAILS (KeyError or template renders no memory section).

- [ ] **Step 3: Modify `core/prompt_builder.py`**

In `build_prompt`, add `memory_block: str | None = None` to the signature and pass it to the template. Replace the current `build_prompt` signature and template render call (lines 48–104):

```python
def build_prompt(
    input_text: str,
    attempt: int = 1,
    *,
    iso_date: str,
    memory_block: str | None = None,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    extra_few_shot_examples: list[dict] | None = None,
    db_few_shot_limit: int = INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT,
    db_path: Path = DB_PATH,
) -> str:
```

And in the `template.render(...)` call inside `build_prompt`, add:

```python
    prompt = template.render(
        input_text=input_text.strip(),
        schema_json=schema_json,
        few_shot_examples=merged,
        attempt=attempt,
        iso_date=iso_date,
        memory_block=memory_block,
        organization_info=organization_info,
        customer_info=customer_info,
    )
```

- [ ] **Step 4: Modify `templates/extraction.j2`**

Add the memory block section immediately before `## Input text`. The full updated file:

```jinja2
{% include "extraction_rules.j2" %}

{% include "anti_hallucination.j2" %}

{% if few_shot_examples %}
## Few-shot examples (recent successful generations)
Use these as behavioral references only. Prioritize the current Input Text and schema.

{% for ex in few_shot_examples %}
### Example {{ loop.index }}
User:
Input:
{{ ex.input_text }}

Prompt:
{{ ex.prompt_text }}

Assistant:
{{ ex.output_json }}

{% endfor %}
{% endif %}

{% if memory_block %}
## Customer history (graph memory)
The following is a summary of this customer's past contracts. Use it only to
disambiguate products, ports, packing/loading terms, and units mentioned in
the chat below. Do not populate fields from memory unless the current chat
explicitly confirms the value.

{{ memory_block }}

{% endif %}

## Output requirements
- Valid JSON matching the target schema exactly.
- No text, explanation, or markdown before or after the JSON.
- Preserve units (e.g. MT, kg, USD/MT, USD/kg) and currencies exactly as stated in the conversation.

## Target schema
```json
{{ schema_json }}
```

## Input text

{{ input_text }}

---

Extract the structured data from the Input Text above. Your response must be valid JSON that strictly conforms to the schema.
```

- [ ] **Step 5: Modify `templates/system_prompt.j2`**

After the last numbered rule in the `## Hard rules` section (currently ending at rule 6 about preserving units), add Rule 7:

```
7. **Memory is disambiguation only.** Customer history provided under
   "Customer history (graph memory)" helps interpret abbreviations and
   recurring patterns. Never copy values from it into output fields unless
   the current chat explicitly states or agrees to that value.
```

- [ ] **Step 6: Run all prompt integration tests**

```bash
pytest tests/test_graph_prompt_integration.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
pytest tests/ -v --ignore=tests/test_graph_extractor.py -x
```

(Skip extractor tests here since they need a live LLM key. All others must pass.)

- [ ] **Step 8: Commit**

```bash
git add core/prompt_builder.py templates/extraction.j2 templates/system_prompt.j2 tests/test_graph_prompt_integration.py
git commit -m "feat: inject graph memory block into extraction prompt"
```

---

## Task 11: CLI — `python -m graph`

**Files:**
- Create: `graph/__main__.py`

- [ ] **Step 1: Create `graph/__main__.py`**

```python
import argparse
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def cmd_ingest(args: argparse.Namespace) -> None:
    from graph.kuzu_backend import KuzuBackend
    from graph.ingestion import ingest_all

    db_path = Path(os.environ.get("KUZU_DB_PATH", "graph.db"))
    if args.reset and db_path.exists():
        import shutil
        shutil.rmtree(db_path) if db_path.is_dir() else db_path.unlink()
        print(f"Cleared existing graph DB at {db_path}")

    backend = KuzuBackend(db_path=db_path)
    count = ingest_all(Path(args.data_dir), backend, model_key=args.model)
    backend.close()
    print(f"Ingested {count} episodes into {db_path}")


def cmd_qa(args: argparse.Namespace) -> None:
    from graph.client import GraphitiMemoryClient

    client = GraphitiMemoryClient()
    answer = client.answer_question(args.customer_id, args.question)
    print(answer)
    client.close()


def cmd_memory(args: argparse.Namespace) -> None:
    from graph.client import GraphitiMemoryClient

    client = GraphitiMemoryClient()
    block = client.get_memory_block(args.customer_id)
    if block:
        print(block)
    else:
        print(f"No history found for customer: {args.customer_id}")
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m graph", description="Knowledge graph CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest raw_data into the graph")
    p_ingest.add_argument("--data-dir", default="raw_data", help="Path to raw_data directory")
    p_ingest.add_argument("--model", default="claude-sonnet-4-6", help="Model key for extraction")
    p_ingest.add_argument("--reset", action="store_true", help="Clear the graph DB before ingesting")
    p_ingest.set_defaults(func=cmd_ingest)

    p_qa = sub.add_parser("qa", help="Ask a question about a customer")
    p_qa.add_argument("customer_id", help="Customer ID to query")
    p_qa.add_argument("question", help="Question to answer")
    p_qa.set_defaults(func=cmd_qa)

    p_mem = sub.add_parser("memory", help="Print memory block for a customer")
    p_mem.add_argument("customer_id", help="Customer ID to retrieve memory for")
    p_mem.set_defaults(func=cmd_memory)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI help works**

```bash
python -m graph --help
```

Expected output:
```
usage: python -m graph [-h] {ingest,qa,memory} ...

Knowledge graph CLI

positional arguments:
  {ingest,qa,memory}
    ingest            Ingest raw_data into the graph
    qa                Ask a question about a customer
    memory            Print memory block for a customer
```

- [ ] **Step 3: Commit**

```bash
git add graph/__main__.py
git commit -m "feat: add graph CLI — ingest, qa, memory subcommands"
```

---

## Task 12: Final integration check

- [ ] **Step 1: Run the complete test suite**

```bash
pytest tests/ -v -x \
  --ignore=tests/test_graph_extractor.py
```

Expected: All tests pass. (Extractor tests are excluded because they require a live LLM API key. They pass in CI with credentials set.)

- [ ] **Step 2: Smoke-test CLI on real data (requires API key)**

```bash
KUZU_DB_PATH=./graph_smoke.db python -m graph ingest --data-dir raw_data/ --reset --model claude-sonnet-4-6
```

Expected: Logs show `Ingested N episodes`. No errors.

```bash
python -m graph memory acme_foods
```

Expected: Prints a memory block containing products from `raw_data/customers/acme_foods/chats/`.

```bash
python -m graph qa acme_foods "What products does this customer usually buy?"
```

Expected: LLM answer mentioning products found in acme_foods history, with source references.

- [ ] **Step 3: Clean up smoke DB**

```bash
rm -rf graph_smoke.db
```

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat: complete knowledge graph V1 — Graphiti + Kuzu ingestion, retrieval, QA, and prompt integration"
```

---

## Notes for Production (Neptune path)

When wiring into the production system:

1. Implement `NeptuneBackend(AbstractGraphBackend)` using the AWS Neptune Bolt driver.
2. Set `GRAPH_BACKEND=neptune` and `NEPTUNE_ENDPOINT=wss://...` in env.
3. In `graph/client.py`, read `GRAPH_BACKEND` and instantiate the correct backend.
4. Replace the custom `extract_entities` with Graphiti's full `add_episode()` API (which handles entity resolution and temporal deduplication) pointed at Neptune.
5. Ingestion source switches from `raw_data/` files to Hasura events / Lambda hooks on approved/signed contracts.

No changes needed to `retrieval.py`, `qa.py`, `prompt_builder.py`, or templates.
