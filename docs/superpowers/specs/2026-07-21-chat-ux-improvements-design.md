# Chat UX Improvements — Design

**Date:** 2026-07-21
**Scope:** `apps/web` (chat UI) and `apps/api` (agent / chat / graph services)
**Status:** Approved for planning

## Summary

Six UX improvements to the customer-chat simulation:

1. Invoke the agent by tagging `@agent` in a message instead of clicking an "Ask agent" button.
2. The `@agent` message is posted and visible in the chat thread.
3. Fix agent message formatting (markdown rendering; no cramped run-on intro).
4. Attach the agent's decision JSON to every agent message.
5. The agent finalizes a contract only when a confirm message tagging it is sent, and only if the draft is ready.
6. Finalizing a contract finishes the current chat and starts a new one, rendered as a checkpoint in a continuous WhatsApp-style thread and as a linked branch in the graph.

## Key Architectural Decision

Each conversation segment between finalized contracts remains a **separate chat record** (Mongo `Chat` document), which is what maps one-to-one to a **branch in the graph**. The UI renders **all** of a customer's chats as **one continuous scroll** (WhatsApp-group metaphor) with a **checkpoint divider** wherever the stream crosses from one chat into the next. This delivers requirement #6's clean graph branching without introducing a chat-switcher view.

## Current State (baseline)

- **`MessageComposer`** (`apps/web/src/components/MessageComposer.tsx`): Seller/Customer toggle, text input, **Send**, **Ask agent**, and a conditional **Approve** button (`showApprove`).
- **`ChatPage`** (`apps/web/src/pages/ChatPage.tsx`): `handleMessage` posts a chat message; `handleAskAgent` calls `invokeAgent(..., "ask")` but **posts no visible message**; `handleApprove` calls `invokeAgent(..., "approve")`.
- **`ChatPane`** (`apps/web/src/components/ChatPane.tsx`): `draft`/`final`/`summary` cards render body in a raw `<pre className="whitespace-pre-wrap">` (no markdown). Plain agent messages already use `<Markdown>`. `summary_json` collapsible `<details>` shows on `draft`/`summary` cards.
- **`agent_service`** (`apps/api/services/agent_service.py`): `invoke` runs the LLM every call; on `mode="finalize"` with `ready_to_finalize` it **auto-finalizes** (writes the contract to the graph). `approve` finalizes an existing pending draft without an LLM call. `finalize` writes the contract card **without** `summary_json`.
- **`chat_service`** (`apps/api/services/chat_service.py`): `ensure_default_chat` returns the **oldest** chat (one chat per customer in practice). `_next_seq` is per-chat.
- **`chat_graph_service`** (`apps/api/services/chat_graph_service.py`): writes `Customer -HAS_CHAT-> Chat -HAS_CONTRACT-> Contract -HAS_LINE-> LineItem` etc.; contracts linked via `SUPERSEDES`.
- **`graph_reader_service`** (`apps/api/services/graph_reader_service.py`): reads all `HAS_CHAT` chats and their contract subgraphs.
- **`hierarchy.ts`** (`apps/web/src/components/graph/hierarchy.ts`): `CONTAINMENT_EDGE_TYPES` drives graph nesting; `SUPERSEDES` is deliberately excluded as a cross-link.
- Frontend `Message` type (`apps/web/src/api/client.ts`) does **not** currently declare `chat_id`, though the API already includes it in the message payload.

## Detailed Design

### 1. `@agent` tagging replaces the buttons (req 1, 2)

**Frontend — `MessageComposer.tsx`**
- Remove the **Ask agent** and **Approve** buttons and the `onAskAgent`, `onApprove`, `showApprove` props.
- Keep the Seller/Customer toggle, the input, and **Send**.

**Frontend — `ChatPage.tsx`**
- Rework `handleMessage(body)`:
  1. `const trimmed = body.trim();`
  2. Post the message under the current role (`api.postMessage(selectedId, role, body)`) — always, so a tagged message is visible (req 2).
  3. If `trimmed` starts with `@agent` (case-insensitive):
     - Parse the remainder after `@agent`. If the first word is a confirm keyword (`confirm` / `finalize` / `approve`), call `api.invokeAgent(selectedId, modelKey, "approve")`; otherwise call `api.invokeAgent(selectedId, modelKey, "ask")`.
  4. Reload messages.
- Remove `handleAskAgent`, `handleApprove`, `pendingSummary`/`showApprove` state and the `pendingFromMessages`/`showApprove` helpers if no longer needed for gating (gating now lives server-side; keep only what the UI still uses).
- Confirm-keyword detection helper (frontend): `const CONFIRM_WORDS = new Set(["confirm", "finalize", "approve"]);` matched against the first token after `@agent`.

**Frontend — `ChatPane.tsx` tag styling**
- When a message body (any role) starts with `@agent` (case-insensitive), split off that leading token and render it as a **mention chip**: a `<span>` with an accent color and medium weight (e.g. rounded, subtle background), followed by the remaining text. Must remain legible inside both the seller bubble (primary background / primary-foreground text) and the customer bubble (card background). Use a token that reads as a highlight in both — e.g. accent text with a translucent background overlay.

**Backend**
- No new endpoint needed: `POST /api/customers/{id}/messages` posts the visible message; `POST /api/customers/{id}/agent` with `action` `"ask"` or `"approve"` drives the agent. Posting the message **before** invoking the agent ensures it is inside the agent's read window.

### 2. Visible tagged message (req 2)

Delivered by step 1.2 above: the `@agent …` text is persisted as a normal `chat` message under the current role before the agent runs, so it appears in the thread and is included in the agent's window. The `@agent` prefix is preserved (not stripped) so the mention chip renders and the model sees the instruction as conversation.

### 3. Fix agent message formatting (req 3)

**Frontend — `ChatPane.tsx`**
- Render the `draft` / `final` / `summary` card body through the existing `<Markdown>` component instead of the raw `<pre>`. This fixes literal `**bold**`, lists, and headings.

**Backend — `agent_service.SYSTEM` prompt**
- Add an instruction: keep `message` to **one short sentence**; do **not** restate the full order inside `message` (the structured summary is rendered separately). This removes the cramped run-on paragraph seen in the screenshot.
- Card body composition is unchanged in shape (`message.strip() + "\n\n" + rendered_markdown`) but now reads cleanly because `message` is a single line and the whole thing is markdown-rendered.

### 4. JSON on every agent message (req 4)

**Backend — `agent_service.py`**
- Attach the full `AgentDecision` JSON (`decision.model_dump_json(indent=2)`) as `summary_json` on **every** agent-produced message:
  - `clarify` → `question` message: attach decision JSON.
  - `draft` → already attaches contract JSON; switch/extend to the full decision JSON (contract is inside the decision).
  - `finalize` → `final` message currently has **no** `summary_json`; attach JSON.
- For the confirm/finalize path that does not run a fresh LLM call (`approve`), attach the finalized contract JSON (`SOExtractContractList` dump) since there is no `AgentDecision`.
- The "No new messages since the last contract." `chat` message may omit JSON (nothing meaningful to show).

**Frontend — `ChatPane.tsx`**
- Render the collapsible `<details>` "Raw model response (JSON)" block, collapsed by default, on **all** agent messages that carry `summary_json` — including plain `chat`/`question` messages, not just cards.

### 5. Finalize only on tagged confirm, gated (req 5)

**Backend — `agent_service.invoke`**
- Never auto-finalize. If the model returns `mode="finalize"` / `ready_to_finalize=true`, downgrade to a **draft** card and append a hint to the card, e.g. *"Ready to finalize — send `@agent confirm` to finalize."*
- A normal `@agent …` (action `"ask"`) therefore always yields a `clarify` question or a `draft` card, never a finalized contract.

**Backend — confirm path (`action="approve"`)**
- Reuse/extend `agent_service.approve` as the gated finalize:
  - Load the pending draft for the active chat.
  - **Gate on readiness** via a single shared predicate `is_ready(slots)`: the draft is ready iff it has at least one material slot **and** every material slot is `agreed_by` both `seller` and `customer`. An empty/absent ledger is **not** ready. (This is a clean readiness definition, not the old `showApprove` button-visibility heuristic, which treated empty slots as approvable.)
  - If no pending draft, or not ready → post an agent `chat`/`question` message that **refuses** and lists what is still missing (unagreed/absent slots). Do not finalize.
  - If ready → finalize (write contract to graph, persist final summary, advance `last_contract_seq`) and trigger the chat-branch transition (req 6).
- Remove the frontend **Approve** button; `showApprove` logic moves entirely server-side.

### 6. New chat branch + checkpoint after finalize (req 6)

**Backend — `chat_service.py`**
- Add `ensure_active_chat(customer_id)`: return the **newest** chat whose `status != "finished"`; if none exists, create `Chat N` where `N = (count of the customer's chats) + 1`.
- Write paths use the active chat: `messages.post_message`, `agent_service.invoke`/`finalize`/`approve`, `command_service` (where it currently calls `ensure_default_chat`).
- Keep `ensure_default_chat` only if a caller genuinely needs the oldest chat; otherwise migrate callers to `ensure_active_chat`. Audit all `ensure_default_chat` call sites.

**Backend — finalize transition (shared helper)**
- Factor the branch transition into one helper called by the finalization path. After this change the finalizing path is the confirm/`approve` path (since `invoke` no longer finalizes); route any remaining `agent_service.finalize` callers through the same helper so the transition happens exactly once wherever a contract is actually finalized.
- After writing the contract, persisting the final summary, and calling `set_last_contract_seq`:
  1. Mark the current chat `status = "finished"`.
  2. Create a new active chat via `chat_service.create_chat`.
  3. In the graph: create the new `Chat` node, `Customer -HAS_CHAT-> newChat`, and `newChat -CONTINUES-> previousChat` (single link to the immediately-previous chat). This makes the new branch appear immediately, even before it has a contract.

**Backend — messages endpoint (`apps/api/routers/messages.py` + `chat_service.list_messages`)**
- `GET /api/customers/{id}/messages` returns **all** of the customer's chats' messages ordered by (chat `created_at`, message `seq`). Each message already carries `chat_id` (and its chat status can be included if useful for the divider). Implementation: query messages for all of the customer's chat ids, sorted by chat order then seq. `post_message` targets the active chat.

**Backend — graph read (`graph_reader_service.py`)**
- Emit `CONTINUES` edges: `MATCH (ch:Chat)-[:CONTINUES]->(prev:Chat)` → add an edge between the two chat nodes.

**Frontend — `Message` type (`apps/web/src/api/client.ts`)**
- Add `chat_id: string` to the `Message` type (already present in the payload).

**Frontend — `ChatPane.tsx` checkpoint divider**
- While mapping messages, when `messages[i].chat_id !== messages[i-1].chat_id`, render a centered checkpoint pill before `messages[i]`: `✓ Contract finalized · new chat started` (muted, centered, small). This appears right after the finalized-contract card.

**Frontend — graph (`hierarchy.ts`, `GraphCanvas.tsx`)**
- Treat `CONTINUES` as a **cross-link** like `SUPERSEDES`: exclude it from `CONTAINMENT_EDGE_TYPES` so it does not nest chats under each other.
- `GraphCanvas` renders `CONTINUES` as an edge between branch (Chat) nodes so the `Chat 1 ← Chat 2 ← Chat 3` lineage is visible.

## Data Model Changes

- `Chat.status`: values extend to include `"finished"` (in addition to `"active"`).
- New graph relationship: `(:Chat)-[:CONTINUES]->(:Chat)` (new → immediately-previous).
- Frontend `Message` type gains `chat_id: string`.
- No change to `Message`/`Contract`/`LineItem`/`Term` shapes.

## Testing (TDD)

Update existing tests and add coverage:

**Frontend**
- `MessageComposer.test.tsx`: buttons removed; Send still works; no `onAskAgent`/`onApprove`/`showApprove`.
- `ChatPane.test.tsx`:
  - `@agent`-prefixed message renders the mention chip.
  - `draft`/`final`/`summary` cards render markdown (`**bold**` → `<strong>`, not literal asterisks).
  - `summary_json` `<details>` appears on all agent messages that carry it, collapsed.
  - Checkpoint divider renders when `chat_id` changes between adjacent messages.
- `client.test.ts`: `Message` type includes `chat_id`; agent invoke `"ask"`/`"approve"` routing.
- `ChatPage` behavior: `@agent create sales order` posts a visible message then calls `invokeAgent(..., "ask")`; `@agent confirm` posts then calls `"approve"`.

**Backend**
- Tag routing / confirm keywords resolve to `"ask"` vs `"approve"` correctly (frontend unit-level, but assert the backend `action` handling).
- `invoke` never finalizes even when the model returns `mode="finalize"` — downgrades to draft with the finalize hint.
- Confirm gating: not-ready draft → refusal message listing missing slots, no graph write; ready draft → finalize.
- Every agent message carries `summary_json` (question/draft/final).
- `ensure_active_chat` returns newest non-finished chat, creates one when all are finished.
- On finalize: current chat marked `finished`, new active chat created, graph has `CONTINUES` new→previous.
- `list_messages` aggregates all of a customer's chats in order and includes `chat_id`.
- `graph_reader_service` emits `CONTINUES` edges.

## Out of Scope

- A chat-switcher / multi-pane view (explicitly replaced by the continuous-thread + checkpoint approach).
- Carrying conversation context forward into the new chat beyond what the existing profile/purchase-history/graph context already provides.
- Linking a new chat to more than the immediately-previous chat.
