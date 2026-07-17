# Knowledge Graph: Graphiti + Kuzu (V1 Design)

**Date:** 2026-06-04
**Status:** Approved for implementation

## Summary

Add a temporal customer knowledge graph to the dakar extraction harness as a prototype of the production Graphiti + Kuzu/Neptune design. Graphiti handles LLM-based entity extraction and temporal fact synthesis. Kuzu runs in-process as the graph backend (no Docker). The graph feeds a compact memory block into extraction prompts to improve disambiguation of products, ports, packing/loading terms, and recurring commercial patterns.

This experiment validates the full V1 loop — ingestion, retrieval, prompt injection, and QA — before wiring into the production Postgres/Hasura/Neptune system.

---

## Architecture

```
raw_data/ (all chats)
       │
       ▼
graph/ingestion.py
  Walk raw_data → episode_builder → Graphiti LLM extraction → KuzuBackend
       │
       ▼
graph/backend.py (AbstractGraphBackend protocol)
  └── graph/kuzu_backend.py (in-process Kuzu DB)
       │
       ├──► graph/retrieval.py → memory_block: str
       │         │
       │         ▼
       │    core/prompt_builder.py (build_prompt + memory_block)
       │         │
       │         ▼
       │    templates/extraction.j2 (memory block injected before input_text)
       │
       └──► graph/qa.py → answer_question(customer_id, question) → str
```

The existing `core/` code is touched in exactly two places: `prompt_builder.py` (one new optional `memory_block` param) and `templates/extraction.j2` (one new optional section). Everything else is additive.

---

## Module: `graph/`

```
graph/
├── __init__.py
├── backend.py          # AbstractGraphBackend Protocol
├── kuzu_backend.py     # Kuzu in-process implementation
├── episode_builder.py  # raw chat JSON → episode dict
├── ingestion.py        # walk raw_data, ingest all chats
├── retrieval.py        # query Kuzu → compact memory block string
├── qa.py               # answer_question(customer_id, question)
└── client.py           # GraphitiMemoryClient — single entry point
```

### `backend.py` — AbstractGraphBackend

A `typing.Protocol` with three methods:

```python
class AbstractGraphBackend(Protocol):
    def write_episode(self, episode: dict) -> None: ...
    def query_customer(self, customer_id: str) -> list[dict]: ...
    def close(self) -> None: ...
```

KuzuBackend implements this. Neptune backend will implement the same interface in prod with no changes to callers.

### `kuzu_backend.py` — KuzuBackend

Kuzu runs in-process (embedded, like SQLite). DB file location is configurable via `KUZU_DB_PATH` env var, defaulting to `graph.db` in the project root.

**Node tables:**
```
Customer(id STRING PRIMARY KEY, name STRING)
Product(name STRING PRIMARY KEY, canonical_name STRING)
Port(name STRING PRIMARY KEY, country STRING)
```

**Edge tables:**
```
Buys(Customer→Product)
  quantity FLOAT, unit STRING, price FLOAT, price_unit STRING,
  incoterm STRING, timestamp INT64, source_id STRING

ShipsTo(Customer→Port)
  incoterm STRING, timestamp INT64, source_id STRING

UsedTerms(Customer→Episode)
  payment_terms STRING, packing STRING, loading STRING,
  timestamp INT64, source_id STRING

Episode(source_id STRING PRIMARY KEY, customer_id STRING, timestamp INT64)
```

Writes are idempotent: `MERGE` on `source_id` before inserting edges; skip if already present.

### `episode_builder.py` — Episode Builder

Converts a raw chat JSON file to a structured episode dict.

**Customer ID inference:**
- `raw_data/customers/<id>/chats/*.json` → `customer_id = <id>`
- `raw_data/downloaded_chats/<N>__<date>__<thread_id>__<uuid>.json` → `customer_id = <thread_id>` (stable across files for the same thread)
- `raw_data/chats/*.json` and `raw_data/emails/*.json` → `customer_id = "generic"`

**Episode structure:**
```json
{
  "source_id": "customers/acme_foods/chats/fs_acme_simple",
  "customer_id": "acme_foods",
  "timestamp": 1760200000,
  "content": "<full concatenated chat text>",
  "field_data": { ... }
}
```

`source_id` is the path relative to `raw_data/` without extension. `timestamp` is the first message timestamp if present, else file mtime. `field_data` is included when present (customer chats have it; generic chats may not).

### `ingestion.py` — Ingestion Pipeline

1. Walk all `raw_data/**/*.json` files.
2. Build episode via `episode_builder.py`.
3. Call Graphiti's `add_episode()` with the episode content — Graphiti LLM extracts entities (products, ports, incoterms, payment terms, packing/loading) and temporal facts.
4. Write extracted entities and relationships to KuzuBackend.
5. Skip if `source_id` already exists in Kuzu (idempotent).

Exposed as a CLI: `python -m graph.ingestion --data-dir raw_data/ [--reset]`.

### `retrieval.py` — Memory Retrieval

`get_memory_block(customer_id: str, backend: AbstractGraphBackend) -> str | None`

Queries Kuzu for all facts associated with `customer_id`. Returns `None` if no history exists (prompt is sent without memory block — no hallucination risk).

**Memory block format:**
```
=== Customer History (acme_foods) ===
- Products: KNM Coffee (10 bags @ USD 25/bag), Rice Bran Oil
- Ports: FOB Singapore, CIF Busan
- Payment terms: Net 30, 100% Advance
- Packing: 25kg PP bags | Loading: 1x20 FCL
[Sources: customers/acme_foods/chats/fs_acme_simple, ...]
```

Capped at ~400 tokens. Most-recent facts appear first (temporal ordering from timestamps).

### `qa.py` — QA Endpoint

`answer_question(customer_id: str, question: str, backend: AbstractGraphBackend) -> str`

1. Validate `customer_id` is non-empty (scope guard — no cross-customer queries).
2. Retrieve all customer facts from Kuzu via `retrieval.py`.
3. Build a QA prompt with the facts and the question.
4. Call the LLM (uses existing `core/llm_client.py`).
5. Return the answer string with inline source references.

Supports questions like:
- "What products does this customer usually buy?"
- "What ports have we shipped to?"
- "What payment terms have we used?"

Refuses questions that lack a `customer_id`.

### `client.py` — GraphitiMemoryClient

Single entry point for callers:

```python
client = GraphitiMemoryClient()          # reads KUZU_DB_PATH from env
block = client.get_memory_block("acme_foods")   # → str | None
answer = client.answer_question("acme_foods", "What products?")  # → str
```

---

## Template Changes

### `templates/extraction.j2`

Add one optional section immediately before `## Input text`:

```jinja2
{% if memory_block %}
## Customer history (graph memory)
The following is a summary of this customer's past contracts. Use it only to
disambiguate products, ports, packing/loading terms, and units mentioned in
the chat below. Do not populate fields from memory unless the current chat
explicitly confirms the value.

{{ memory_block }}

{% endif %}
```

### `templates/system_prompt.j2`

Add Rule 7 to the existing hard rules list:

```
7. **Memory is disambiguation only.** Customer history under "Customer history
   (graph memory)" helps interpret abbreviations and recurring patterns. Never
   copy values from it into output fields unless the current chat explicitly
   states or agrees to that value.
```

### `core/prompt_builder.py`

`build_prompt()` gains one new optional keyword argument:

```python
def build_prompt(
    input_text: str,
    attempt: int = 1,
    *,
    iso_date: str,
    memory_block: str | None = None,   # NEW
    ...
) -> str:
```

Passed through to the Jinja2 template context. Defaults to `None` so all existing callers are unaffected.

---

## Backend Switching (prod path)

The `AbstractGraphBackend` protocol is the only seam between the application and the graph database. Prod will implement a `NeptuneBackend` that satisfies the same protocol and is selected by env var:

```
GRAPH_BACKEND=kuzu   # default / local / dakar
GRAPH_BACKEND=neptune
KUZU_DB_PATH=./graph.db
NEPTUNE_ENDPOINT=wss://...
```

No business logic changes when switching backends.

---

## Testing

1. **Ingestion idempotency** — run ingestion twice, assert Kuzu node/edge counts are identical.
2. **Customer isolation** — query `nova_exports` memory, assert no `acme_foods` facts appear.
3. **Missing memory** — query an unknown `customer_id`, assert `get_memory_block` returns `None` and prompt is built without the memory section.
4. **Memory block in prompt** — assert prompt with `memory_block` contains the "Customer history" section; assert prompt without it does not.
5. **QA scoping** — `answer_question` with empty `customer_id` raises `ValueError`.
6. **QA content** — `answer_question("acme_foods", "What products?")` mentions "KNM Coffee".

---

## Assumptions

- Graphiti's `add_episode()` API is used for LLM extraction only; graph writes go through the KuzuBackend adapter, not Graphiti's built-in Neo4j writer.
- `raw_data/chats/` and `raw_data/emails/` files without a customer_id are bucketed under `"generic"` and ingested but will rarely surface in retrieval (no customer scopes them).
- `downloaded_chats/` thread IDs are stable customer proxies for the experiment; in prod these map to real `customer_id` values from Postgres.
- Kuzu version ≥ 0.8 for stable Python SDK.
- Graphiti version pinned in `requirements.txt`; Neptune support deferred to prod implementation.
