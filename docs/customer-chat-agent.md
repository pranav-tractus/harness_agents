# Customer-Chat Agent — Developer Guide

How the "new agent" in `apps/` works end to end: what it does, the request paths
that reach it, the services it orchestrates, the two data stores it reads/writes,
and how the result renders in the web UI.

This is the agent introduced on the `customer-chat-graphiti-simulation` branch. It
lives entirely under `apps/` and reuses the `core/` extraction library for LLM calls
and contract schemas.

---

## 1. What the agent is

The agent is a **neutral contract-drafting participant in a group chat** between a
seller ("me") and a customer. It watches the conversation, resolves which catalog
products are being discussed, tracks a per-slot ledger of the deal terms, and:

- **asks** the minimum set of clarifying questions when critical terms are unknown,
- **drafts** a structured sales-order contract once the critical terms are known,
- **finalizes** the contract into a knowledge graph once both parties have agreed,
  then starts a fresh chat "branch" for the next order.

It never auto-finalizes. A draft always waits for an explicit `@agent confirm` /
`approve` action before it is committed to the graph.

---

## 2. Where everything lives (file map)

```
apps/api/
  main.py                         # FastAPI app; wires all routers
  models.py                       # Pydantic I/O + AgentDecision, SlotBelief, readiness helpers, markdown renderer
  settings.py                     # env: mongo url, falkordb host/port, web origin

  routers/
    messages.py                   # POST a chat message; an @agent tag runs the agent  ← the only entrypoint
    chats.py                      # list/create chats, list chat messages
    customers.py, products.py, graphs.py, models_router.py

  services/
    agent_service.py              # ★ THE AGENT: invoke() / finalize() / approve()
    agent_tag.py                  # parses "@agent …" → "ask" | "approve" | None (pure, no I/O)
    product_matcher_service.py    # resolve product mentions → catalog SKUs (LLM + graph pools)
    summary_context_service.py    # assemble grounding context (profile + history + product blocks)
    chat_service.py               # Mongo chats & messages: seq numbers, windows, chat lifecycle
    chat_graph_service.py         # ★ write finalized contract into the customer knowledge graph
    graph_reader_service.py       # read customer & product graphs → {nodes, edges} for the UI
    profile_graph_service.py      # customer profile ↔ graph attributes
    product_graph_service.py      # catalog product facts → graph

  db/
    mongo.py                      # Mongo collections: customers, chats, messages, summaries, products
    falkor.py                     # FalkorDB (graph) client; per-customer graph + shared catalog graph

core/                             # reused extraction library (NOT app-specific)
  llm_client.py                   # call_llm(prompt, schema, model_key, system_prompt) via instructor
  models.py                       # SOExtractContractList / SOUpdateContractList contract schemas
  utils.py                        # MODEL_CATALOG, provider clients, model resolution

apps/web/src/
  api/client.ts                   # typed fetch client (postMessage, listMessages, …)
  components/ChatPane.tsx         # renders chat + draft/final/question cards
```

The two anchors to read first are **`apps/api/services/agent_service.py`** (the brain)
and **`apps/api/services/chat_graph_service.py`** (the graph write).

---

## 3. The two data stores

The agent reads/writes two very different stores. Keeping them straight is the key to
understanding the flow.

### MongoDB — the conversation & drafts (source of live state)
`apps/api/db/mongo.py`

| Collection  | Holds                                                                 |
|-------------|-----------------------------------------------------------------------|
| `customers` | customer record + `profile`                                           |
| `chats`     | one per conversation "session"; has `status`, `last_contract_seq`      |
| `messages`  | every message with a per-chat monotonic `seq` and a `kind` (see below)|
| `summaries` | the current draft/approved contract for a chat (`status: pending`/`approved`) |
| `products`  | catalog product docs                                                  |

Message `kind` values matter: `chat` (real seller/customer text), `question`,
`draft`, `final`, `summary`. The agent only reasons over a *window* of
`chat`/`question`/`draft`/`final` messages since the last committed contract
(`_AGENT_WINDOW_KINDS`, `agent_service.py:133`).

### FalkorDB — the knowledge graph (committed truth)
`apps/api/db/falkor.py`

- **Per-customer graph** `customer:<id>`: `Customer → HAS_CHAT → Chat → HAS_CONTRACT
  → Contract → HAS_LINE → LineItem → OF_PRODUCT → Product`, plus `HAS_TERM → Term`,
  `DERIVED_FROM → MessageRef`, `SHIP_TO → Port`, `Chat -CONTINUES-> Chat`,
  `Contract -SUPERSEDES-> Contract`, and `Customer -PREFERS-> Preference`.
- **Shared catalog graph** `catalog`: `Product` with `HAS_ALIAS`, `HAS_SPEC`,
  `IN_CATEGORY`, `USED_FOR`.

The graph is written **only at finalize/approve time** (`chat_graph_service.write_contract`).
Everything before that lives in Mongo `summaries` as a mutable draft.

`falkor.is_available()` is checked everywhere — if FalkorDB is down, graph reads
return empty and grounding blocks are `None`, so the agent degrades gracefully to
chat-only reasoning.

---

## 4. Request entry points

All traffic goes through **`apps/api/routers/messages.py`**. There is exactly one
entrypoint.

### `POST /api/customers/{id}/messages`
```json
{ "role": "seller" | "customer", "body": "…", "model_key": "…" }
```

The body is always appended as a `kind: "chat"` message. Then
`agent_tag.parse(body)` decides what happens next:

| Body                                    | Parse      | Effect                                    |
|-----------------------------------------|------------|-------------------------------------------|
| `10MT CIF please`                       | `None`     | appended, nothing else                    |
| `@agent create sales order`             | `"ask"`    | → **`agent_service.invoke`** (drafts/asks)|
| `@agent confirm` / `finalize` / `approve` | `"approve"` | → **`agent_service.approve`** (finalizes) |

The tag must start the message (`^@agent\b`, case-insensitive), and only the
*first* word after it is checked against the confirm set — `@agent please confirm`
is an `ask`. `model_key` is only read when the message is tagged, and falls back
to `core.utils.DEFAULT_MODEL_KEY`.

The response shape is uniform: `{ "messages": [...], "summary": … | null }`. An
ordinary message returns a one-element list and a null summary; a tagged one
returns the user's message followed by whatever the agent posted.

**Why the keyword check is not an LLM call:** finalizing writes the contract
subgraph, closes the chat, and branches a new one. Routing that through the model
would let a paraphrase like "@agent looks good to me" commit an order.

---

## 5. The agent draft flow (`agent_service.invoke`)

This is the core loop. `agent_service.py:172`.

```
invoke(customer_id, model_key)
 │
 ├─ 1. chat_id = ensure_active_chat(customer_id)            # chat_service.py:56
 │       (reuses the non-finished chat, or starts "Chat N")
 │
 ├─ 2. window = messages_since(last_contract_seq, kinds=_AGENT_WINDOW_KINDS)
 │       └─ nothing new? → post "No new messages…" and return.       (:188)
 │
 ├─ 3. PRODUCT MATCHING  product_matcher_service.resolve_products    (:201)
 │       • builds a candidate pool = catalog terms found in the text (catalog graph)
 │                                   + SKUs this customer ordered before (customer graph, strong prior)
 │       • LLM classifies each product mention: confident | ambiguous | no_match
 │       • _guard() drops any resolved_code not in the pool (anti-hallucination)
 │       └─ any unresolved? → post a "question" card asking which SKU, and RETURN.  (:203)
 │           (the agent will not draft until products are pinned down)
 │
 ├─ 4. GROUNDING CONTEXT  summary_context_service.assemble           (:213)
 │       • profile_block  ← profile_graph_service.read_block   (customer graph attributes)
 │       • history_block  ← Preference nodes ("typical terms, seen Nx")
 │       • product_block  ← _resolved_product_block(matches)   (overwrites with the resolved SKUs)
 │
 ├─ 5. previous draft?  load pending summary from Mongo → previous_json  (:218)
 │
 ├─ 6. DECIDE  agent_service.decide → core.llm_client.call_llm        (:224)
 │       system = SYSTEM prompt (agent_service.py:22)
 │       returns AgentDecision { mode, message, questions, contract, ledger[], ready_to_finalize }
 │       • cap_questions() → at most 3, critical slots first  (models.py:174)
 │       • mode=="finalize" but not ready → downgraded to "draft"  (:76)
 │
 └─ 7. ACT on decision.mode:
        • "clarify" → post a "question" card, no summary.            (:229)
        • else ("draft"/"finalize") →
              contract → render_summary_markdown()                    (models.py:97)
              body = message + markdown (+ "Ready to finalize…" hint if ready)
              upsert Mongo summary (status: pending, revision++, slots, product_matches)  (:247)
              post a "draft" card with summary_id + raw decision JSON.  (:282)
```

Key invariant (`agent_service.py:239`): **a "ready" decision still only drafts.** The
agent surfaces "Ready to finalize — send `@agent confirm`…" but never writes the graph
itself.

### The slot ledger
The `SYSTEM` prompt tells the model to maintain a ledger over these slots:
`description, quantity, unit_price, ship_term, shipping_address, packing, loading,
payment_date`. Each `SlotBelief` (`models.py:151`) carries `value, source
(chat|last_order|profile|inferred|unknown), confidence, agreed_by ⊆ {seller,
customer}`.

- **Critical slots** = `description, quantity, unit_price, ship_term`
  (`CRITICAL_SLOTS`, `models.py:134`). These must be *known* to draft.
- **Soft slots** (address, packing, loading, payment_date) are resolved silently from
  history/profile and marked `source=inferred`.
- **Readiness** (`is_ready` / `missing_agreement`, `models.py:142`): a draft is
  finalizable only when *every critical slot is `agreed_by` both seller and customer*.

---

## 6. Finalize / approve flow

Two entry points converge on the graph write.

### `agent_service.approve` (`:388`) — approve a pending draft
1. Load the `pending` summary for the active chat. None? → "no draft" message.
2. **Readiness gate**: `is_ready(pending.slots)`. Not ready → reply listing the
   `missing_agreement` critical slots and stop. *This is the hard commit gate.*
3. `chat_graph_service.write_contract(...)` → writes the Contract subgraph.
4. Flip the summary to `status: approved`, set `chat.last_contract_seq = to_seq`.
5. Post a `final` card, then **`_finish_and_branch`**.

### `agent_service.finalize` (`:325`) — finalize directly from a decision
Same graph write + persist, used when a decision object is passed in rather than a
stored pending draft.

### `_finish_and_branch` (`:315`)
1. `chat_service.finish_chat(chat_id)` → old chat `status: finished`.
2. `chat_service.start_new_chat` → "Chat N+1".
3. `chat_graph_service.open_branch` → `newChat -CONTINUES-> oldChat` edge.

So each finalized order closes its chat and opens a linked successor. In the UI this is
the "✓ Contract finalized · new chat started" checkpoint divider
(`ChatPane.tsx:60`).

### What `write_contract` puts in the graph (`chat_graph_service.py:29`)
- Ensures `Customer` and `Chat` nodes (`MERGE`).
- Creates a `Contract` node with `revision` = count of prior contracts in the chat;
  links `SUPERSEDES` to the previous contract.
- One `LineItem` per contract item (`product_code, quantity, price, incoterm,
  agreed_by`), with `OF_PRODUCT → Product` and optional `SHIP_TO → Port`.
- `Term` nodes for payment/packing/loading.
- `MessageRef` nodes (`DERIVED_FROM`) recording the source message seqs/snippets —
  the provenance trail back to the chat.
- **Derived preferences**: for every slot agreed by *both* parties, `MERGE` a
  `Preference {slot}` and bump its `support` count. These feed back into the
  `history_block` grounding on future drafts — the "learning" loop.

Contracts render through `render_summary_markdown` (`models.py:97`), which handles
either `SOExtractContractList` or `SOUpdateContractList` since they share a field
layout.

---

## 7. LLM plumbing

Every model call funnels through **`core.llm_client.call_llm(prompt, schema,
model_key, system_prompt=…)`** which uses `instructor` to coerce the response into the
given Pydantic schema across providers (Bedrock / Anthropic / OpenAI / Gemini). The
`model_key` comes from the request body and maps through `core.utils.MODEL_CATALOG`
(exposed to the UI via `GET /api/models`, `models_router.py`).

Schemas used:
- `AgentDecision` (`models.py:165`) — the agent's structured output.
- `ProductMatchResult` (`product_matcher_service.py:23`) — product resolution.
- `SOExtractContractList` / `SOUpdateContractList` (`core/models.py`) — the contract.

All three services accept an injectable `llm=`/`decider=`/`*_fn=` parameter, so tests
stub the LLM and graph without network/DB (see `*_service` signatures — e.g.
`agent_service.invoke(..., decider=None, context_fn=None, graph_fn=None,
matcher_fn=None)`).

---

## 8. Frontend rendering (`apps/web`)

- `api/client.ts` — `postMessage(id, role, body, model_key)` is the only write;
  the browser does no tag parsing. `listMessages` polls the merged, chat-ordered
  message list (`chat_service.all_messages`).
- `ChatPane.tsx` renders by message `kind`:
  - `summary` / `draft` / `final` → a `Card` with badge ("AI Summary" / "Draft
    contract" / "Finalized contract"), the markdown body, and a collapsible **"Raw
    model response (JSON)"** (`summary_json` = the pretty-printed decision).
  - `question` → a left-bordered "needs answer" callout.
  - `chat` → normal seller (right) / customer (left) / agent (full-width) bubbles;
    `@agent` mentions get a highlight chip (`splitAgentMention`, cosmetic only).
  - Between a `finished` chat and the next, the **checkpoint divider** is drawn.

---

## 9. End-to-end sequence (happy path)

```
Seller & customer exchange messages  ── POST /messages ──▶ Mongo messages (kind=chat)

Seller: "@agent create sales order"  ── POST /messages ─▶ agent_tag → agent_service.invoke
   │
   ├─ product_matcher: all mentions confident
   ├─ context assembled (profile + prefs + resolved products)
   ├─ decide(): critical slots known but not both-agreed → mode="draft"
   └─ upsert pending summary + post DRAFT card ("Ready to finalize…" once agreed)

… more negotiation, seller re-invokes @agent → draft revised (revision++) …

Seller: "@agent confirm"             ── POST /messages ─▶ agent_tag → agent_service.approve
   │
   ├─ is_ready(slots)? ── no ──▶ "Still need both parties to agree on: …"  (stop)
   └─ yes:
        chat_graph_service.write_contract → Contract/LineItem/Term/MessageRef/Preference
        summary → approved, chat.last_contract_seq = to_seq
        post FINAL card
        _finish_and_branch → old chat finished, "Chat N+1" opened, CONTINUES edge

UI: draft/final cards render in ChatPane; graph view reads via
    graph_reader_service.read_customer_graph → GraphCanvas.
```

---

## 10. Gotchas & invariants

- **The `@agent` tag is the only trigger.** There is no command endpoint. The
  ask/approve split is a deterministic keyword check in `agent_tag.parse`, never
  a model decision.
- **The agent never commits on its own.** Drafting and finalizing are separate calls;
  finalize is gated on both-party agreement of all critical slots.
- **`last_contract_seq` is the watermark.** Everything the agent reasons over is
  `messages_since(last_contract_seq)`; after finalize it advances, so the next order
  starts from a clean window.
- **Product codes are never invented.** `product_matcher._guard` and the summary
  system prompts constrain the model to the provided catalog pool; unmatched mentions
  become questions.
- **Graph writes are idempotent-ish via `MERGE`** for Customer/Chat/Product/Port/
  Preference, but `Contract`/`LineItem`/`Term`/`MessageRef` are `CREATE`d fresh each
  finalize (new revision, `SUPERSEDES` the old).
- **Preferences are the feedback loop.** Both-agreed slots become `Preference` nodes
  that reappear as `history_block` grounding on the next draft.
- **Everything degrades if FalkorDB is down** (`falkor.is_available()` guards): no
  grounding, empty graph views, but chat + drafting still work off Mongo.
