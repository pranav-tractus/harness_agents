# Graph-Grounded Summary Generation (Chat Sim)

Date: 2026-07-17

## Problem

In the chat-simulation flow, sales-order summary generation (`/create-sales-order`
and `/edit`) feeds the LLM only three things:

- the customer **name** (a plain string),
- a **flat product catalog** (`code — description` pulled straight from Mongo), and
- the **raw chat window** since the last contract.

The two Kuzu graphs the system maintains are **not** consumed during summary
generation:

- The **customer profile graph** (`graph_dbs/<cid>/profile.db`) — customer
  attributes (email, phone, business/delivery address, contact point,
  `approved_credit_term`, `approved_white_label`, `latest_packing_and_loading`)
  is never read.
- The **chat entity graph** (`graph_dbs/<cid>/chat.db`) — historical
  products/ports/terms — is *written* right before the summary (Step A of
  `command_service._create`) but its contents are never read back into the
  prompt. `graph/retrieval.get_memory_block()` already renders this graph into a
  text block, but nothing in the chat-sim wiring calls it.

There is also no product graph today; products are flat Mongo docs
(`code`, `description`, `spec`).

## Goal

Feed graph context into summary generation and revision so the LLM grounds the
sales order in what the system already knows, and **backfills fields the chat
did not explicitly state**, always preferring explicit chat values when they
conflict with graph facts.

Three sources feed the summary:

1. **Customer profile graph** (`profile.db`) — known customer attributes.
2. **Chat entity graph** (`chat.db`) — historical products/ports/terms.
3. **A new product graph** — richer than the flat catalog: product aliases +
   normalized spec attributes, so fuzzy chat mentions resolve to real catalog
   products.

## Design Decisions (settled during brainstorming)

- **Role of graph data:** grounding + gap-filling. The LLM prefers values
  explicitly stated in the chat; when a field is not stated, it may fill it from
  the profile graph, purchase history, or product catalog context. It must not
  invent values that appear in none of these sources.
- **Sources:** both Kuzu graphs **plus** a new richer product graph.
- **Product graph scope:** aliases + structured specs only (no categories,
  substitutes, or customer-affinity links — YAGNI).
- **Product graph population:** LLM-derived at sync time from each product's
  `description`/`spec`. No product schema changes, no manual curation.
- **Product graph sync trigger:** on write — product create/update re-derives and
  resyncs that product's graph node; delete removes it. Mirrors how the profile
  graph resyncs on profile change.
- **Profile block source:** read from the profile **graph** (not Mongo), to honor
  "feed the customer information graph".
- **Coverage:** both `/create-sales-order` and `/edit` receive graph context, so
  revisions stay grounded.
- **Catalog scope in prompt:** the full enriched catalog is fed (matches today's
  behavior). If the catalog grows large, filtering to likely-mentioned products
  is a future concern, not built now.

## Architecture

```
products router (create/update/delete)
        │  resync_product / remove_product   (injectable, like profile resync)
        ▼
product_graph_service ──► graph_dbs/_catalog/product.db   (single shared Kuzu DB)
        │
        │ catalog_block()
        ▼
summary_context_service ──┬── profile block  ◄── profile_graph_service.read_block()  ◄── profile.db
                          ├── history block  ◄── graph.retrieval.get_memory_block()  ◄── chat.db
                          └── product block  ◄── product_graph_service.catalog_block()
        │  assemble(customer_id) -> {profile_block, history_block, product_block}
        ▼
command_service (_create / _edit)
        │  context_fn(customer_id)   (injectable)
        ▼
summary_service.generate / revise  ──►  LLM  (gap-filling system prompt)
```

## Components

### 1. Product graph (new, global)

**Storage:** single shared Kuzu DB at `graph_dbs/_catalog/product.db` (products
are global, not per-customer).

**Schema** (profile-graph style — Attribute-like nodes):

- `Product(code STRING PK, description STRING, spec STRING)`
- `Alias(name STRING PK)` with `Product-[:HAS_ALIAS]->Alias`
- `SpecAttr(key STRING PK, value STRING)` with `Product-[:HAS_SPEC]->SpecAttr`

**Extractor:** `graph/product_extractor.py`

```python
class ProductFacts(BaseModel):
    aliases: list[str] = []          # alternate names / common references
    grade: str | None = None
    packing_size: str | None = None
    unit: str | None = None
    attributes: dict[str, str] = {}  # any other normalized spec key/values

def extract_product_facts(description: str, spec: str | None,
                          model_key: str) -> ProductFacts: ...
```

`grade`, `packing_size`, `unit` and each `attributes` entry are written as
`SpecAttr` nodes keyed by attribute name.

**Service:** `apps/api/services/product_graph_service.py`

- `resync_product(code, description, spec, model_key, *, extractor=None, db_path=None) -> None`
  — LLM-derive facts, wipe that product's existing node/edges, rewrite. Idempotent.
- `remove_product(code, *, db_path=None) -> None` — delete node + its alias/spec edges.
- `catalog_block(*, db_path=None) -> str | None` — render the whole enriched
  catalog to a prompt text block, e.g.:

  ```
  === Product Catalog ===
  - WHF25: Wheat Flour 25kg | grade: A, packing_size: 25kg, unit: MT
    aka: atta, maida, wheat flour bag
  ```

  Returns `None` when the catalog graph is empty.

`extractor` and `db_path` are injectable for tests (default: real
`extract_product_facts` + `graph_dbs/_catalog/product.db`).

**Router wiring** (`apps/api/routers/products.py`):

- `create_product` → `product_graph_service.resync_product(code, description, spec, DEFAULT_MODEL)`
- `update_product` → `resync_product(...)` after the Mongo update
- `delete_product` → `product_graph_service.remove_product(code)`

Wired so tests can monkeypatch these (same pattern as
`customers.profile_graph_service.resync`).

### 2. Profile graph read (extend existing)

`apps/api/services/profile_graph_service.py` gains:

- `read_block(customer_id, *, db_path=None) -> str | None` — query the
  `Customer-[:HAS_ATTRIBUTE]->Attribute` edges from `profile.db` and render:

  ```
  === Customer Profile ===
  - approved_credit_term: Net 30
  - delivery_address: ...
  - latest_packing_and_loading: 25kg PP bags, 1x20 FCL
  ```

  Returns `None` when there are no attributes.

Existing `resync` is unchanged.

### 3. Context assembly (new)

`apps/api/services/summary_context_service.py`:

```python
def assemble(customer_id: str, *, profile_reader=None,
             history_reader=None, product_reader=None) -> dict:
    return {
        "profile_block": ...,   # profile_graph_service.read_block(customer_id)
        "history_block": ...,   # get_memory_block(customer_id, KuzuBackend(chat.db))
        "product_block": ...,   # product_graph_service.catalog_block()
    }
```

Each reader is injectable for tests. Any block may be `None`; the summary service
omits `None` blocks from the prompt.

The history reader constructs a `KuzuBackend` on the customer's `chat.db`
(`chat_graph_service.chat_db_path`) and calls `graph.retrieval.get_memory_block`,
closing the backend afterward.

### 4. Summary service + prompt (modify)

`apps/api/services/summary_service.py`:

- `generate(customer_name, messages, product_block, model_key, *,
   profile_block=None, history_block=None, llm=None)` — the enriched
  `product_block` replaces the old flat `product_catalog` list; profile/history
  blocks are new, optional.
- `revise(customer_name, previous, instructions, messages, model_key, *,
   product_block=None, profile_block=None, history_block=None, llm=None)` — same
  context added.
- Prompt includes the non-`None` blocks under clear headers (Customer profile /
  Purchase history / Product catalog) plus the chat window.
- `_SYSTEM` updated:

  > "You extract a structured sales order from a customer chat, matching the
  > provided JSON schema exactly. Prefer values explicitly stated in the chat.
  > When a field is not stated in the chat, you may fill it from the provided
  > customer profile, purchase history, or product catalog context, preferring
  > the chat when they conflict. Only use products from the provided catalog.
  > Group line items into one contract per distinct purchase order. Do not invent
  > values that appear in none of these sources."

### 5. command_service wiring (modify)

`apps/api/services/command_service.py`:

- Add injectable `context_fn=summary_context_service.assemble` to `dispatch`.
- `_create`: after Step A (graph build), call `ctx = context_fn(customer_id)` and
  pass `ctx["product_block"]`, `ctx["profile_block"]`, `ctx["history_block"]` into
  `summary_gen`.
- `_edit`: call `context_fn(customer_id)` and pass the same blocks into
  `summary_revise`.
- The old `_product_catalog()` flat-list helper is removed (its role is replaced
  by the enriched product block).

## Data Flow (create-sales-order)

1. Router logs the `/create-sales-order` command message.
2. `command_service._create` guards on pending summary + non-empty window.
3. **Step A:** `chat_graph_service.build_and_write` writes the window's entities
   to `chat.db` (unchanged).
4. **Context:** `summary_context_service.assemble(customer_id)` reads profile
   graph, chat graph (now including Step A's write), and product graph.
5. **Step B:** `summary_service.generate(name, window, product_block, model_key,
   profile_block=..., history_block=...)` → `SOExtractContractList`.
6. Persist pending summary + render card (unchanged).

`/edit` mirrors this: assemble context, then `summary_service.revise(...)` with
the blocks.

## Testing

- `tests/api/test_product_graph_service.py` — `resync_product` writes
  product/alias/spec nodes (fake extractor, tmp DB); idempotent resync; `remove_product`
  deletes; `catalog_block` renders expected text and returns `None` when empty.
- `tests/api/test_summary_context_service.py` — `assemble` composes three blocks
  from injected readers; `None` blocks handled.
- `tests/api/test_summary_service.py` — updated for new signature; prompt contains
  profile/history/product blocks when provided and omits them when `None`; new
  gap-filling `_SYSTEM` string asserted.
- `tests/api/test_command_service.py` — `_create`/`_edit` call `context_fn` and
  forward blocks into the (stubbed) summary generator/reviser.
- `tests/api/test_api_endpoints.py` — product create/update/delete monkeypatch the
  new product-graph sync functions (as the profile resync is already stubbed);
  assert they are invoked.
- Profile graph `read_block` covered in `tests/api/test_profile_graph_service.py`.

## Out of Scope

- Product categories, substitutes, or customer-affinity links.
- Manual curation of aliases/specs.
- Filtering the fed catalog to likely-mentioned products (future, if catalog grows).
- Any frontend changes.
