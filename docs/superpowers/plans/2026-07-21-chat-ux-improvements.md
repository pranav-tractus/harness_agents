# Chat UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "Ask agent" button with `@agent` message tagging, make tagged messages visible, fix agent-message markdown formatting, attach the agent's decision JSON to every agent message, gate finalization behind a tagged confirm, and start a new linked chat branch each time a contract is finalized.

**Architecture:** The React chat UI (`apps/web`) posts every message (tagged or not) and, when a message starts with `@agent`, additionally invokes the FastAPI agent endpoint (`apps/api`) with `ask` or `approve`. Each conversation segment between finalized contracts stays a separate Mongo `Chat` record — one per graph branch — but the UI shows all of a customer's chats as one continuous thread with a checkpoint divider at each `chat_id` boundary. The agent never auto-finalizes; a tagged confirm finalizes only a ready draft and then finishes the chat and opens the next branch (`(:Chat)-[:CONTINUES]->(:Chat)` in FalkorDB).

**Tech Stack:** React 19 + Vite + Vitest + Testing Library (frontend); FastAPI + Pydantic + MongoDB (mongomock in tests) + FalkorDB (Cypher) + pytest (backend); `react-markdown` + `remark-gfm` for rendering.

## Global Constraints

- Agent tag: a message triggers the agent iff its trimmed body starts with `@agent` (case-insensitive). Copy verbatim in UI: `@agent`.
- Confirm keywords (first word after `@agent`, case-insensitive): `confirm`, `finalize`, `approve` → action `"approve"`; anything else → action `"ask"`.
- Tagged messages post under the currently selected role (`seller` | `customer`) and remain visible in the thread; the `@agent` prefix is preserved (not stripped).
- The agent never auto-finalizes. A normal `@agent …` always yields a `clarify` question or a `draft` card.
- Finalize is gated: `is_ready(slots)` = ledger has ≥1 slot AND every critical slot (`description`, `quantity`, `unit_price`, `ship_term`) is `agreed_by` both `seller` and `customer`.
- Ready-draft hint copy (verbatim): `_Ready to finalize — send `@agent confirm` to finalize._`
- Checkpoint divider copy (verbatim): `✓ Contract finalized · new chat started`.
- New chat title format: `Chat N` where `N = (customer's chat count) + 1`.
- Graph lineage edge: `(:Chat)-[:CONTINUES]->(:Chat)`, direction new → immediately-previous chat. `CONTINUES` is a cross-link, never a containment edge.
- Frontend test runner (run from `apps/web`): `npm test -- <path>` (i.e. `vitest run <path>`). Type check: `npm run build`.
- Backend test runner (run from repo root, venv active): `python -m pytest <path> -v`.

---

## File Structure

**Frontend (`apps/web/src`)**
- Create `lib/agentTag.ts` — pure tag parsing/splitting helpers.
- Create `lib/agentTag.test.ts` — unit tests for the helpers.
- Modify `components/MessageComposer.tsx` — remove Ask-agent/Approve buttons and their props.
- Modify `components/MessageComposer.test.tsx` — reflect the new prop shape.
- Modify `pages/ChatPage.tsx` — tag-routing in `handleMessage`; drop ask/approve/pending state.
- Create `pages/ChatPage.test.tsx` — assert post-then-invoke routing.
- Modify `api/client.ts` — add `chat_id` and `chat_status` to the `Message` type.
- Modify `components/ChatPane.tsx` — markdown cards, JSON `<details>` on all agent messages, `@agent` mention chip, checkpoint divider.
- Modify `components/ChatPane.test.tsx` — new fixtures/fields and behavior tests.
- Modify `components/GraphCanvas.tsx` — export `edgeStroke`, style `CONTINUES`.
- Create `components/GraphCanvas.test.ts` — test `edgeStroke`.
- Modify `components/graph/hierarchy.test.ts` — lock `CONTINUES` as a non-containment cross-link.

**Backend (`apps/api`)**
- Modify `models.py` — `CRITICAL_SLOTS_ORDER`, `is_ready`, `missing_agreement`; one-line-`message` instruction in the agent SYSTEM prompt (SYSTEM lives in `agent_service.py`).
- Modify `services/chat_service.py` — `active_chat`, `ensure_active_chat`, `start_new_chat`, `finish_chat`, `all_messages`.
- Modify `services/agent_service.py` — `invoke` never finalizes + decision JSON on every message; `_finish_and_branch`; gated `approve`; JSON on `finalize`.
- Modify `services/chat_graph_service.py` — `open_branch` (new Chat node + `CONTINUES`).
- Modify `services/graph_reader_service.py` — emit `CONTINUES` edges.
- Modify `routers/messages.py` — GET returns `all_messages`; POST uses active chat.
- Modify `services/command_service.py` — migrate `ensure_default_chat` → `ensure_active_chat`.

**Tests (backend, `tests/api`)**
- Modify `test_agent_invoke.py`, `test_agent_finalize.py`, `test_agent_endpoint.py`, `test_chat_service.py`, `test_models.py`.
- Create `test_chat_branch.py` (mongo branch transition) and add `CONTINUES` cases to `test_chat_graph_falkor.py` / `test_graph_reader_falkor.py`.

---

## Task 1: `agentTag` pure helpers (frontend)

**Files:**
- Create: `apps/web/src/lib/agentTag.ts`
- Test: `apps/web/src/lib/agentTag.test.ts`

**Interfaces:**
- Produces:
  - `type AgentAction = "ask" | "approve"`
  - `parseAgentTag(body: string): { isAgent: boolean; action: AgentAction }`
  - `splitAgentMention(body: string): { mention: string | null; rest: string }`

- [ ] **Step 1: Write the failing test**

```ts
// apps/web/src/lib/agentTag.test.ts
import { describe, expect, it } from "vitest";
import { parseAgentTag, splitAgentMention } from "./agentTag";

describe("parseAgentTag", () => {
  it("flags non-tagged messages as not-agent", () => {
    expect(parseAgentTag("hello there")).toEqual({ isAgent: false, action: "ask" });
  });
  it("routes a plain @agent message to ask", () => {
    expect(parseAgentTag("@agent create sales order")).toEqual({ isAgent: true, action: "ask" });
  });
  it("routes confirm keywords to approve (case-insensitive)", () => {
    for (const w of ["confirm", "Finalize", "APPROVE"]) {
      expect(parseAgentTag(`@agent ${w}`)).toEqual({ isAgent: true, action: "approve" });
    }
  });
  it("treats @agent with no verb as ask", () => {
    expect(parseAgentTag("@agent")).toEqual({ isAgent: true, action: "ask" });
  });
});

describe("splitAgentMention", () => {
  it("splits the leading @agent token from the rest", () => {
    expect(splitAgentMention("@agent create sales order")).toEqual({
      mention: "@agent",
      rest: " create sales order",
    });
  });
  it("returns null mention when not tagged", () => {
    expect(splitAgentMention("hello")).toEqual({ mention: null, rest: "hello" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `apps/web`): `npm test -- src/lib/agentTag.test.ts`
Expected: FAIL — cannot resolve `./agentTag`.

- [ ] **Step 3: Write the implementation**

```ts
// apps/web/src/lib/agentTag.ts
export type AgentAction = "ask" | "approve";

const AGENT_TAG = /^@agent\b/i;
const CONFIRM_WORDS = new Set(["confirm", "finalize", "approve"]);

export function parseAgentTag(body: string): { isAgent: boolean; action: AgentAction } {
  const trimmed = body.trim();
  if (!AGENT_TAG.test(trimmed)) return { isAgent: false, action: "ask" };
  const rest = trimmed.replace(AGENT_TAG, "").trim();
  const first = (rest.split(/\s+/)[0] ?? "").toLowerCase();
  return { isAgent: true, action: CONFIRM_WORDS.has(first) ? "approve" : "ask" };
}

export function splitAgentMention(body: string): { mention: string | null; rest: string } {
  const m = body.match(/^(@agent)\b(.*)$/i);
  if (!m) return { mention: null, rest: body };
  return { mention: m[1], rest: m[2] };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `apps/web`): `npm test -- src/lib/agentTag.test.ts`
Expected: PASS (6 assertions across 6 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/agentTag.ts apps/web/src/lib/agentTag.test.ts
git commit -m "feat(web): add @agent tag parsing helpers"
```

---

## Task 2: Simplify `MessageComposer` (remove agent buttons)

**Files:**
- Modify: `apps/web/src/components/MessageComposer.tsx`
- Test: `apps/web/src/components/MessageComposer.test.tsx`

**Interfaces:**
- Produces: `MessageComposer` props are now `{ role: "seller" | "customer"; onRoleChange: (r) => void; onMessage: (body: string) => void }`.

- [ ] **Step 1: Rewrite the failing test**

```tsx
// apps/web/src/components/MessageComposer.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageComposer } from "./MessageComposer";

describe("MessageComposer", () => {
  it("submits trimmed text via onMessage and exposes roles", () => {
    const onMessage = vi.fn();
    render(<MessageComposer role="seller" onRoleChange={() => {}} onMessage={onMessage} />);
    fireEvent.change(screen.getByPlaceholderText("Message…"), { target: { value: "  hi  " } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(onMessage).toHaveBeenCalledWith("hi");
    expect(screen.getByText("Seller")).toBeTruthy();
  });

  it("no longer renders Ask agent or Approve buttons", () => {
    render(<MessageComposer role="seller" onRoleChange={() => {}} onMessage={() => {}} />);
    expect(screen.queryByRole("button", { name: /ask agent/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `apps/web`): `npm test -- src/components/MessageComposer.test.tsx`
Expected: FAIL — TypeScript/prop errors and the current file still renders the buttons.

- [ ] **Step 3: Rewrite the component**

```tsx
// apps/web/src/components/MessageComposer.tsx
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

type Props = {
  role: "seller" | "customer";
  onRoleChange: (r: "seller" | "customer") => void;
  onMessage: (body: string) => void;
};

export function MessageComposer({ role, onRoleChange, onMessage }: Props) {
  const [text, setText] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    onMessage(value);
    setText("");
  }

  return (
    <form data-testid="composer-form" onSubmit={submit}
      className="flex items-center gap-2 border-t bg-card px-4 py-3">
      <ToggleGroup value={[role]} onValueChange={(v) => { const n = v[0]; if (n) onRoleChange(n as "seller" | "customer"); }}>
        <ToggleGroupItem value="seller" className="text-xs font-medium">Seller</ToggleGroupItem>
        <ToggleGroupItem value="customer" className="text-xs font-medium">Customer</ToggleGroupItem>
      </ToggleGroup>
      <Input value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Message…" className="flex-1" />
      <Button type="submit" size="sm" variant="secondary">Send</Button>
    </form>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `apps/web`): `npm test -- src/components/MessageComposer.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/MessageComposer.tsx apps/web/src/components/MessageComposer.test.tsx
git commit -m "feat(web): drop Ask-agent/Approve buttons from composer"
```

---

## Task 3: Readiness helpers + one-line intro prompt (backend `models.py` / `agent_service.py`)

**Files:**
- Modify: `apps/api/models.py`
- Modify: `apps/api/services/agent_service.py` (SYSTEM prompt only in this task)
- Test: `tests/api/test_models.py`

**Interfaces:**
- Produces:
  - `CRITICAL_SLOTS_ORDER: list[str] = ["description", "quantity", "unit_price", "ship_term"]`
  - `CRITICAL_SLOTS = set(CRITICAL_SLOTS_ORDER)`
  - `is_ready(slots: list[dict]) -> bool`
  - `missing_agreement(slots: list[dict]) -> list[str]`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_models.py`:

```python
from apps.api.models import is_ready, missing_agreement


def _slot(slot, agreed):
    return {"slot": slot, "value": "x", "source": "chat", "confidence": "high", "agreed_by": agreed}


def test_is_ready_true_when_all_critical_agreed_by_both():
    slots = [_slot(s, ["seller", "customer"]) for s in
             ["description", "quantity", "unit_price", "ship_term"]]
    assert is_ready(slots) is True
    assert missing_agreement(slots) == []


def test_is_ready_false_when_a_critical_slot_unagreed():
    slots = [_slot("description", ["seller", "customer"]),
             _slot("quantity", ["seller"]),
             _slot("unit_price", ["seller", "customer"]),
             _slot("ship_term", ["seller", "customer"])]
    assert is_ready(slots) is False
    assert missing_agreement(slots) == ["quantity"]


def test_is_ready_false_when_empty():
    assert is_ready([]) is False
    assert missing_agreement([]) == ["description", "quantity", "unit_price", "ship_term"]
```

- [ ] **Step 2: Run test to verify it fails**

Run (repo root): `python -m pytest tests/api/test_models.py -v -k is_ready`
Expected: FAIL — `ImportError: cannot import name 'is_ready'`.

- [ ] **Step 3: Add the helpers to `models.py`**

Replace the existing `CRITICAL_SLOTS = {...}` line (around line 125) with:

```python
CRITICAL_SLOTS_ORDER = ["description", "quantity", "unit_price", "ship_term"]
CRITICAL_SLOTS = set(CRITICAL_SLOTS_ORDER)


def _agreed_by_both(slots: list[dict]) -> dict[str, set[str]]:
    return {s["slot"]: set(s.get("agreed_by", [])) for s in slots}


def missing_agreement(slots: list[dict]) -> list[str]:
    by_slot = _agreed_by_both(slots)
    return [s for s in CRITICAL_SLOTS_ORDER if not {"seller", "customer"} <= by_slot.get(s, set())]


def is_ready(slots: list[dict]) -> bool:
    return bool(slots) and missing_agreement(slots) == []
```

- [ ] **Step 4: Run test to verify it passes**

Run (repo root): `python -m pytest tests/api/test_models.py -v -k is_ready`
Expected: PASS (3 tests).

- [ ] **Step 5: Tighten the agent intro instruction**

In `apps/api/services/agent_service.py`, append this sentence to the end of the `SYSTEM` string (inside the closing quote, after "…terms."):

```python
    " Keep the `message` field to one short sentence; never restate the full "
    "order details in `message` (the structured summary is rendered separately)."
```

- [ ] **Step 6: Run backend suite to confirm no regressions**

Run (repo root): `python -m pytest tests/api/test_models.py tests/api/test_agent_prompt.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/models.py apps/api/services/agent_service.py tests/api/test_models.py
git commit -m "feat(api): add draft-readiness helpers and one-line agent intro"
```

---

## Task 4: Active-chat lifecycle + all-chats message stream (`chat_service`)

**Files:**
- Modify: `apps/api/services/chat_service.py`
- Test: `tests/api/test_chat_service.py`

**Interfaces:**
- Consumes: `create_chat(customer_id, title)`, `add_message(...)`, `_now`, `_to_out` (existing in this module).
- Produces:
  - `active_chat(customer_id) -> dict | None` (raw Mongo doc, newest non-finished)
  - `ensure_active_chat(customer_id) -> str` (chat id)
  - `start_new_chat(customer_id) -> dict` (via `_chat_out`)
  - `finish_chat(chat_id) -> None`
  - `all_messages(customer_id) -> list[dict]` — every chat's messages ordered by (chat `created_at`, `seq`), each stamped with `chat_id` and `chat_status`.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_chat_service.py`:

```python
def test_ensure_active_chat_reuses_then_creates_after_finish():
    a = chat_service.ensure_active_chat("dummy-01")
    assert chat_service.ensure_active_chat("dummy-01") == a  # reuse while active
    chat_service.finish_chat(a)
    b = chat_service.ensure_active_chat("dummy-01")
    assert b != a  # new chat once finished


def test_start_new_chat_numbers_titles():
    first = chat_service.ensure_active_chat("dummy-02")  # "Chat 1"
    chat_service.finish_chat(first)
    second = chat_service.start_new_chat("dummy-02")
    assert second["title"] == "Chat 2"


def test_all_messages_spans_chats_in_order_with_status():
    a = chat_service.ensure_active_chat("dummy-03")
    chat_service.add_message("dummy-03", a, "seller", "in chat 1")
    chat_service.finish_chat(a)
    b = chat_service.start_new_chat("dummy-03")
    chat_service.add_message("dummy-03", b, "seller", "in chat 2")
    rows = chat_service.all_messages("dummy-03")
    assert [r["body"] for r in rows] == ["in chat 1", "in chat 2"]
    assert rows[0]["chat_id"] == a and rows[0]["chat_status"] == "finished"
    assert rows[1]["chat_id"] == b and rows[1]["chat_status"] == "active"
```

- [ ] **Step 2: Run test to verify it fails**

Run (repo root): `python -m pytest tests/api/test_chat_service.py -v -k "active_chat or all_messages or numbers_titles"`
Expected: FAIL — `AttributeError: module ... has no attribute 'ensure_active_chat'`.

- [ ] **Step 3: Add the functions to `chat_service.py`**

Add after `ensure_default_chat` (keep `ensure_default_chat` as-is for backward compatibility):

```python
def _chat_count(customer_id: str) -> int:
    return mongo.chats().count_documents({"customer_id": customer_id})


def active_chat(customer_id: str) -> dict | None:
    return mongo.chats().find_one(
        {"customer_id": customer_id, "status": {"$ne": "finished"}},
        sort=[("created_at", -1)])


def start_new_chat(customer_id: str) -> dict:
    return create_chat(customer_id, f"Chat {_chat_count(customer_id) + 1}")


def ensure_active_chat(customer_id: str) -> str:
    doc = active_chat(customer_id)
    return str(doc["_id"]) if doc else start_new_chat(customer_id)["id"]


def finish_chat(chat_id: str) -> None:
    mongo.chats().update_one({"_id": ObjectId(chat_id)},
        {"$set": {"status": "finished", "last_activity": _now()}})


def all_messages(customer_id: str) -> list[dict]:
    chats = list(mongo.chats().find({"customer_id": customer_id}).sort("created_at", 1))
    order = {str(c["_id"]): i for i, c in enumerate(chats)}
    status = {str(c["_id"]): c.get("status", "active") for c in chats}
    msgs = list(mongo.messages().find({"customer_id": customer_id}))
    msgs.sort(key=lambda m: (order.get(m["chat_id"], len(order)), m["seq"]))
    out = []
    for m in msgs:
        d = _to_out(m)
        d["chat_status"] = status.get(m["chat_id"], "active")
        out.append(d)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run (repo root): `python -m pytest tests/api/test_chat_service.py -v`
Expected: PASS (all, including the three new tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/chat_service.py tests/api/test_chat_service.py
git commit -m "feat(api): add active-chat lifecycle and all-chats message stream"
```

---

## Task 5: `invoke` never finalizes + decision JSON on every message

**Files:**
- Modify: `apps/api/services/agent_service.py` (`invoke`, `_pending`)
- Test: `tests/api/test_agent_invoke.py`

**Interfaces:**
- Consumes: `chat_service.ensure_active_chat`, `models.render_summary_markdown`.
- Produces: `invoke(...)` returns `{"messages": [...], "summary": ...}` where every agent message carries `summary_json` = `decision.model_dump_json(indent=2)`; a ready decision produces a `draft` (not `final`) with the finalize hint appended.

- [ ] **Step 1: Replace the auto-finalize test with the new behavior**

In `tests/api/test_agent_invoke.py`, delete `test_invoke_auto_finalizes_when_ready` and add:

```python
def test_invoke_never_finalizes_even_when_ready():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT CIF Busan")
    dec = AgentDecision(mode="finalize", message="Both confirmed.",
                        contract=SOExtractContractList(data=[]), ready_to_finalize=True,
                        ledger=[SlotBelief(slot="ship_term", value="CIF", source="chat",
                                           confidence="high", agreed_by=["seller", "customer"])])
    out = agent_service.invoke("dummy-01", "sonnet-4-6",
                               decider=_decider(dec), context_fn=_ctx)
    assert out["messages"][-1]["kind"] == "draft"
    assert "@agent confirm" in out["messages"][-1]["body"]
    assert chat_service.get_last_contract_seq(ch) == 0
    assert mongo.summaries().count_documents({"status": "approved"}) == 0


def test_agent_messages_carry_decision_json():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "need choline")
    dec = AgentDecision(mode="clarify", message="Which product?",
                        questions=[AgentQuestion(slot="description", directed_to="seller", text="?")])
    out = agent_service.invoke("dummy-01", "sonnet-4-6",
                               decider=_decider(dec), context_fn=_ctx)
    assert '"mode": "clarify"' in out["messages"][-1]["summary_json"]
```

- [ ] **Step 2: Run test to verify it fails**

Run (repo root): `python -m pytest tests/api/test_agent_invoke.py -v -k "never_finalizes or decision_json"`
Expected: FAIL — invoke still finalizes / question has no `summary_json`.

- [ ] **Step 3: Update `invoke` and `_pending`**

In `agent_service.py`, change `_pending` to use the active chat:

```python
def _pending(customer_id: str, chat_id: str | None = None) -> dict | None:
    chat_id = chat_id or chat_service.ensure_active_chat(customer_id)
    return mongo.summaries().find_one(
        {"customer_id": customer_id, "chat_id": chat_id, "status": "pending"})
```

Replace the body of `invoke` from the `chat_id = ...` line through the end of the function with:

```python
    chat_id = chat_service.ensure_active_chat(customer_id)

    last = chat_service.get_last_contract_seq(chat_id)
    window = chat_service.messages_since(chat_id, last, kinds=list(_AGENT_WINDOW_KINDS))
    if not window:
        return {"messages": [_agent_msg(customer_id, chat_id,
                "No new messages since the last contract.", "chat")], "summary": None}

    ctx = context_fn(customer_id)
    pending = _pending(customer_id, chat_id)
    previous_json = None
    if pending:
        previous_json = SOExtractContractList(**pending["content"]).model_dump_json(indent=2)
    decision = decider(_customer_name(customer_id), window, ctx, model_key,
                       previous_json=previous_json)
    decision_json = decision.model_dump_json(indent=2)

    if decision.mode == "clarify":
        msg = _agent_msg(customer_id, chat_id, decision.message, "question",
                         summary_json=decision_json)
        return {"messages": [msg], "summary": None}

    # draft — the agent NEVER auto-finalizes; a ready decision still drafts.
    contract = decision.contract or SOExtractContractList(data=[])
    markdown = render_summary_markdown(contract, _customer_name(customer_id))
    body = decision.message.strip() + "\n\n" + markdown
    if decision.ready_to_finalize or decision.mode == "finalize":
        body += "\n\n_Ready to finalize — send `@agent confirm` to finalize._"
    slots = [s.model_dump() for s in decision.ledger]
    to_seq = _draft_to_seq(window)
    if pending:
        mongo.summaries().update_one(
            {"_id": pending["_id"]},
            {"$set": {"content": contract.model_dump(), "rendered_markdown": markdown,
                      "slots": slots, "to_seq": to_seq, "model_key": model_key, "chat_id": chat_id},
             "$inc": {"revision": 1}})
        doc = mongo.summaries().find_one({"_id": pending["_id"]})
    else:
        doc = {"customer_id": customer_id, "chat_id": chat_id, "status": "pending",
               "model_key": model_key, "from_seq": window[0]["seq"], "to_seq": to_seq, "revision": 0,
               "content": contract.model_dump(), "rendered_markdown": markdown,
               "slots": slots, "created_at": _now(), "approved_at": None}
        doc["_id"] = mongo.summaries().insert_one(doc).inserted_id

    card = _agent_msg(customer_id, chat_id, body, "draft",
                      summary_id=str(doc["_id"]), summary_json=decision_json)
    return {"messages": [card], "summary": _summary_out(doc)}
```

Also remove the now-dead `if decision.mode == "finalize": return finalize(...)` branch (it is replaced by the code above). Keep the `finalize` function itself — it is updated in Task 7.

- [ ] **Step 4: Run test to verify it passes**

Run (repo root): `python -m pytest tests/api/test_agent_invoke.py -v`
Expected: PASS (existing clarify/draft/window tests plus the two new ones).

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/agent_service.py tests/api/test_agent_invoke.py
git commit -m "feat(api): stop agent auto-finalizing and attach decision JSON to every message"
```

---

## Task 6: `open_branch` — new Chat node + `CONTINUES` edge (graph write)

**Files:**
- Modify: `apps/api/services/chat_graph_service.py`
- Test: `tests/api/test_chat_graph_falkor.py`

**Interfaces:**
- Consumes: `falkor.customer_graph`, `falkor.is_available`, `_ensure_chat` (existing in this module).
- Produces: `open_branch(customer_id: str, new_chat_id: str, new_chat_title: str, prev_chat_id: str) -> None` — no-op when FalkorDB is unavailable; otherwise MERGEs the new `Chat` node (+ `HAS_CHAT`) and MERGEs `(new)-[:CONTINUES]->(prev)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_chat_graph_falkor.py`:

```python
def test_open_branch_links_continues(graph_name):
    _skip_if_down()
    cg.write_contract(graph_name, "chat-1", "Chat 1", {"items": []}, [], [], to_seq=1)
    cg.open_branch(graph_name, "chat-2", "Chat 2", "chat-1")
    g = falkor.customer_graph(graph_name)
    rows = g.query(
        "MATCH (a:Chat)-[:CONTINUES]->(b:Chat) RETURN a.id, b.id").result_set
    assert [list(r) for r in rows] == [["chat-2", "chat-1"]]
    chats = {r[0] for r in g.query("MATCH (:Customer)-[:HAS_CHAT]->(ch:Chat) RETURN ch.id").result_set}
    assert {"chat-1", "chat-2"} <= chats
```

- [ ] **Step 2: Run test to verify it fails**

Run (repo root): `python -m pytest tests/api/test_chat_graph_falkor.py -v -k open_branch`
Expected: FAIL — `AttributeError: ... 'open_branch'` (or SKIP if FalkorDB is not running; start it via `docker-compose up -d` first).

- [ ] **Step 3: Add `open_branch` to `chat_graph_service.py`**

```python
def open_branch(customer_id, new_chat_id, new_chat_title, prev_chat_id) -> None:
    if not falkor.is_available():
        return
    g = falkor.customer_graph(customer_id)
    _ensure_chat(g, customer_id, new_chat_id, new_chat_title)
    g.query(
        "MATCH (a:Chat {id:$new}),(b:Chat {id:$old}) MERGE (a)-[:CONTINUES]->(b)",
        {"new": new_chat_id, "old": prev_chat_id})
```

- [ ] **Step 4: Run test to verify it passes**

Run (repo root): `python -m pytest tests/api/test_chat_graph_falkor.py -v -k open_branch`
Expected: PASS (or SKIP if FalkorDB down — acceptable; re-run with the DB up before merging).

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/chat_graph_service.py tests/api/test_chat_graph_falkor.py
git commit -m "feat(api): open a new chat branch with a CONTINUES link on finalize"
```

---

## Task 7: Gated confirm-to-finalize + branch transition (`approve`, `finalize`)

**Files:**
- Modify: `apps/api/services/agent_service.py` (`finalize`, `approve`, add `_finish_and_branch`)
- Test: `tests/api/test_agent_finalize.py`, `tests/api/test_agent_endpoint.py`

**Interfaces:**
- Consumes: `models.is_ready`, `models.missing_agreement`, `chat_service.finish_chat`, `chat_service.start_new_chat`, `chat_graph_service.open_branch`.
- Produces:
  - `_finish_and_branch(customer_id: str, finished_chat_id: str, *, branch_fn=None) -> dict` (returns the new chat doc).
  - `finalize(..., branch_fn=None)` — final message carries `summary_json`; finishes the chat and opens the next branch.
  - `approve(customer_id, *, graph_fn=None, branch_fn=None)` — refuses when there is no draft or the draft is not ready; otherwise finalizes, stamps `summary_json`, and branches.

- [ ] **Step 1: Update the finalize/approve tests**

In `tests/api/test_agent_finalize.py`, add the `is_ready` import and a ready-ledger helper, replace `test_approve_finalizes_pending_draft`, and add gating + branch tests:

```python
from apps.api.models import CRITICAL_SLOTS_ORDER


def _ready_slots():
    return [{"slot": s, "value": "x", "source": "chat", "confidence": "high",
             "agreed_by": ["seller", "customer"]} for s in CRITICAL_SLOTS_ORDER]


def _seed_pending(ch, slots):
    from core.models import SOExtractContractList
    mongo.summaries().insert_one({
        "customer_id": "dummy-01", "chat_id": ch, "status": "pending", "model_key": "sonnet-4-6",
        "from_seq": 1, "to_seq": 1, "revision": 0,
        "content": SOExtractContractList(data=[]).model_dump(),
        "rendered_markdown": "draft", "slots": slots, "created_at": "t", "approved_at": None})


def test_approve_refuses_when_not_ready():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "x")
    _seed_pending(ch, [])  # nothing agreed
    out = agent_service.approve("dummy-01", graph_fn=_graph([]), branch_fn=lambda *a, **k: None)
    assert out["summary"] is None
    assert out["messages"][-1]["kind"] == "chat"
    assert "Not ready" in out["messages"][-1]["body"]
    assert chat_service.get_last_contract_seq(ch) == 0


def test_approve_finalizes_ready_draft_and_branches():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "seller", "10MT CIF Busan")
    _seed_pending(ch, _ready_slots())
    out = agent_service.approve("dummy-01", graph_fn=_graph([]), branch_fn=lambda *a, **k: None)
    assert out["summary"]["status"] == "approved"
    assert out["messages"][-1]["summary_json"]  # JSON attached
    # current chat finished, a fresh active chat now exists
    from apps.api.services import chat_service as cs
    assert cs.active_chat("dummy-01")["_id"].__str__() != ch
```

In `tests/api/test_agent_endpoint.py`, make `test_agent_approve_returns_final` seed a ready ledger. Replace the summary-insert block's `"slots": []` with:

```python
        "slots": [{"slot": s, "value": "x", "source": "chat", "confidence": "high",
                   "agreed_by": ["seller", "customer"]}
                  for s in ["description", "quantity", "unit_price", "ship_term"]],
```

- [ ] **Step 2: Run tests to verify they fail**

Run (repo root): `python -m pytest tests/api/test_agent_finalize.py tests/api/test_agent_endpoint.py -v`
Expected: FAIL — `approve` doesn't gate/branch yet and `_seed_pending` with `[]` currently finalizes.

- [ ] **Step 3: Add `_finish_and_branch`, gate `approve`, update `finalize`**

In `agent_service.py`, **replace the existing** `from apps.api.models import AgentDecision, cap_questions, render_summary_markdown` line (around line 6) with:

```python
from apps.api.models import (AgentDecision, cap_questions, is_ready,
                             missing_agreement, render_summary_markdown)
```

Add the shared helper:

```python
def _finish_and_branch(customer_id: str, finished_chat_id: str, *, branch_fn=None) -> dict:
    branch_fn = branch_fn or chat_graph_service.open_branch
    chat_service.finish_chat(finished_chat_id)
    new_chat = chat_service.start_new_chat(customer_id)
    branch_fn(customer_id, new_chat["id"], new_chat["title"], finished_chat_id)
    return new_chat
```

Replace `finalize`'s final-message line and add the transition. Change the `finalize` signature and its tail:

```python
def finalize(customer_id, *, decision=None, window=None, model_key="", graph_fn=None, branch_fn=None) -> dict:
    graph_fn = graph_fn or chat_graph_service.write_contract
    chat_id = chat_service.ensure_active_chat(customer_id)
    window = window or chat_service.chat_messages_since(chat_id, chat_service.get_last_contract_seq(chat_id))
    to_seq = window[-1]["seq"] if window else chat_service.get_last_contract_seq(chat_id)
    contract = (decision.contract if decision else None) or SOExtractContractList(data=[])
    slots = [s.model_dump() for s in decision.ledger] if decision else []

    graph_fn(customer_id, chat_id, _chat_title(chat_id), _contract_dict(contract), slots,
             _source_seqs(window), to_seq)
    doc = _persist_final(customer_id, chat_id, contract, slots,
                         from_seq=(window[0]["seq"] if window else to_seq),
                         to_seq=to_seq, model_key=model_key)
    chat_service.set_last_contract_seq(chat_id, to_seq)
    mongo.summaries().delete_many(
        {"customer_id": customer_id, "chat_id": chat_id, "status": "pending"})
    decision_json = (decision.model_dump_json(indent=2) if decision
                     else contract.model_dump_json(indent=2))
    msg = _agent_msg(customer_id, chat_id, (decision.message if decision else "Finalized.") + "\n\n"
                     + doc["rendered_markdown"], "final", summary_id=str(doc["_id"]),
                     summary_json=decision_json)
    _finish_and_branch(customer_id, chat_id, branch_fn=branch_fn)
    return {"messages": [msg], "summary": _summary_out(doc)}
```

Replace `approve` with the gated version:

```python
def approve(customer_id, *, graph_fn=None, branch_fn=None) -> dict:
    chat_id = chat_service.ensure_active_chat(customer_id)
    pending = _pending(customer_id, chat_id)
    if not pending:
        return {"messages": [_agent_msg(customer_id, chat_id,
                "There's no draft to finalize yet. Send `@agent create sales order` first.",
                "chat")], "summary": None}
    if not is_ready(pending.get("slots", [])):
        missing = missing_agreement(pending.get("slots", []))
        body = ("Not ready to finalize. Still need both parties to agree on: "
                + ", ".join(missing) + ".")
        return {"messages": [_agent_msg(customer_id, chat_id, body, "chat")], "summary": None}

    graph_fn = graph_fn or chat_graph_service.write_contract
    window = chat_service.chat_messages_since(chat_id, pending["from_seq"] - 1)
    contract = SOExtractContractList(**pending["content"])
    slots = pending.get("slots", [])
    graph_fn(customer_id, chat_id, _chat_title(chat_id), _contract_dict(contract), slots,
             _source_seqs(window), pending["to_seq"])
    mongo.summaries().update_one({"_id": pending["_id"]},
        {"$set": {"status": "approved", "approved_at": _now(), "chat_id": chat_id}})
    chat_service.set_last_contract_seq(chat_id, pending["to_seq"])
    approved = mongo.summaries().find_one({"_id": pending["_id"]})
    msg = _agent_msg(customer_id, chat_id, "Approved and finalized.\n\n" + approved["rendered_markdown"],
                     "final", summary_id=str(approved["_id"]),
                     summary_json=contract.model_dump_json(indent=2))
    _finish_and_branch(customer_id, chat_id, branch_fn=branch_fn)
    return {"messages": [msg], "summary": _summary_out(approved)}
```

Note: `command_service._approve` calls `agent_service.approve(customer_id, graph_fn=graph_fn)` — that still type-checks (`branch_fn` defaults to `None`).

- [ ] **Step 4: Run tests to verify they pass**

Run (repo root): `python -m pytest tests/api/test_agent_finalize.py tests/api/test_agent_endpoint.py -v`
Expected: PASS. (`test_auto_finalize_advances_checkpoint_and_writes_graph` still passes: `finalize` writes the graph via the stub and the default `branch_fn`/`open_branch` no-ops because FalkorDB is down in unit tests.)

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/agent_service.py tests/api/test_agent_finalize.py tests/api/test_agent_endpoint.py
git commit -m "feat(api): gate finalize behind a ready draft and branch to a new chat"
```

---

## Task 8: `CONTINUES` edges in the graph reader

**Files:**
- Modify: `apps/api/services/graph_reader_service.py`
- Test: `tests/api/test_chat_graph_falkor.py`

**Interfaces:**
- Consumes: `read_customer_graph` internals (`_edge`, node id format `Chat::{id}`).
- Produces: `read_customer_graph` output `edges` now include `{type: "CONTINUES"}` between two `Chat::` nodes.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_chat_graph_falkor.py`:

```python
def test_reader_emits_continues_edges(graph_name):
    _skip_if_down()
    from apps.api.services import graph_reader_service
    cg.write_contract(graph_name, "chat-1", "Chat 1", {"items": []}, [], [], to_seq=1)
    cg.open_branch(graph_name, "chat-2", "Chat 2", "chat-1")
    g = graph_reader_service.read_customer_graph(graph_name)
    cont = [(e["source"], e["target"]) for e in g["edges"] if e["type"] == "CONTINUES"]
    assert ("Chat::chat-2", "Chat::chat-1") in cont
```

Note: `read_customer_graph` needs a `Customer` node to return non-empty. `write_contract` MERGEs the `Customer` via `_ensure_chat`, so the graph is populated.

- [ ] **Step 2: Run test to verify it fails**

Run (repo root): `python -m pytest tests/api/test_chat_graph_falkor.py -v -k continues_edges`
Expected: FAIL — no `CONTINUES` edge emitted (or SKIP if DB down).

- [ ] **Step 3: Emit `CONTINUES` edges in `read_customer_graph`**

In `graph_reader_service.py`, immediately before the final `return {"nodes": nodes, "edges": edges}`, add:

```python
    for new_id, old_id in g.query(
            "MATCH (:Customer {id:$id})-[:HAS_CHAT]->(a:Chat)-[:CONTINUES]->(b:Chat) "
            "RETURN a.id, b.id", {"id": customer_id}).result_set:
        _edge(edges, f"Chat::{new_id}", f"Chat::{old_id}", "CONTINUES")
```

- [ ] **Step 4: Run test to verify it passes**

Run (repo root): `python -m pytest tests/api/test_chat_graph_falkor.py -v -k "continues_edges or open_branch"`
Expected: PASS (or SKIP if DB down).

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/graph_reader_service.py tests/api/test_chat_graph_falkor.py
git commit -m "feat(api): expose CONTINUES chat-lineage edges from the graph reader"
```

---

## Task 9: Messages router + command_service use the active chat

**Files:**
- Modify: `apps/api/routers/messages.py`
- Modify: `apps/api/services/command_service.py`
- Test: `tests/api/test_api_endpoints.py`

**Interfaces:**
- Consumes: `chat_service.all_messages`, `chat_service.ensure_active_chat`.
- Produces: `GET /api/customers/{id}/messages` returns every chat's messages (each with `chat_id`, `chat_status`); `POST` appends to the active chat.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_api_endpoints.py` (follow the file's existing `client` fixture; if it seeds `dummy-01`, reuse it — otherwise mirror the fixture in `test_agent_endpoint.py`):

```python
def test_messages_include_chat_id_and_status(client):
    client.post("/api/customers/dummy-01/messages", json={"role": "seller", "body": "hello"})
    rows = client.get("/api/customers/dummy-01/messages").json()
    assert rows[-1]["chat_id"]
    assert rows[-1]["chat_status"] == "active"
```

- [ ] **Step 2: Run test to verify it fails**

Run (repo root): `python -m pytest tests/api/test_api_endpoints.py -v -k chat_id_and_status`
Expected: FAIL — response rows lack `chat_status` (GET still returns single-chat list).

- [ ] **Step 3: Update the router**

Rewrite `apps/api/routers/messages.py`:

```python
from fastapi import APIRouter

from apps.api.models import MessageIn
from apps.api.services import chat_service

router = APIRouter(prefix="/api/customers/{customer_id}/messages", tags=["messages"])


@router.get("")
def list_messages(customer_id: str) -> list[dict]:
    return chat_service.all_messages(customer_id)


@router.post("")
def post_message(customer_id: str, body: MessageIn) -> dict:
    chat_id = chat_service.ensure_active_chat(customer_id)
    return chat_service.add_message(customer_id, chat_id, body.role, body.body)
```

- [ ] **Step 4: Migrate `command_service` to the active chat**

In `apps/api/services/command_service.py`, replace every `chat_service.ensure_default_chat(` with `chat_service.ensure_active_chat(` (in `_pending_summary` and `dispatch`). This keeps the `/commands` path consistent with the agent path.

- [ ] **Step 5: Run tests to verify they pass**

Run (repo root): `python -m pytest tests/api/test_api_endpoints.py tests/api/test_command_service.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/routers/messages.py apps/api/services/command_service.py tests/api/test_api_endpoints.py
git commit -m "feat(api): serve all-chat message stream and write to the active chat"
```

---

## Task 10: `Message` type + `ChatPage` tag routing (frontend)

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/pages/ChatPage.tsx`
- Create: `apps/web/src/pages/ChatPage.test.tsx`

**Interfaces:**
- Consumes: `parseAgentTag` (Task 1), `api.postMessage`, `api.invokeAgent`.
- Produces: `Message` type gains `chat_id: string` and `chat_status: string`; `ChatPage.handleMessage` posts the message, then invokes the agent with the parsed action when tagged.

- [ ] **Step 1: Extend the `Message` type**

In `apps/web/src/api/client.ts`, add two fields to the `Message` type:

```ts
export type Message = {
  id: string;
  customer_id: string;
  chat_id: string;
  chat_status: string;
  seq: number;
  role: string;
  kind: string;
  body: string;
  summary_id: string | null;
  summary_json: string | null;
  created_at: string;
};
```

- [ ] **Step 2: Write the failing ChatPage test**

```tsx
// apps/web/src/pages/ChatPage.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/client", () => {
  const customers = [{ id: "c1", name: "Acme", profile: {}, last_contract_seq: 0 }];
  return {
    api: {
      listCustomers: vi.fn(async () => customers),
      listMessages: vi.fn(async () => []),
      listModels: vi.fn(async () => [{ key: "sonnet-4-6", display_name: "Sonnet", provider: "anthropic" }]),
      postMessage: vi.fn(async () => ({})),
      invokeAgent: vi.fn(async () => ({ messages: [], summary: null })),
      getCustomer: vi.fn(async () => customers[0]),
    },
  };
});

import { api } from "@/api/client";
import { ChatPage } from "./ChatPage";

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  vi.clearAllMocks();
});

async function type(text: string) {
  render(<ChatPage />);
  await waitFor(() => expect(api.listCustomers).toHaveBeenCalled());
  fireEvent.change(screen.getByPlaceholderText("Message…"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /send/i }));
}

describe("ChatPage @agent routing", () => {
  it("posts a normal message without invoking the agent", async () => {
    await type("just chatting");
    await waitFor(() => expect(api.postMessage).toHaveBeenCalledWith("c1", "seller", "just chatting"));
    expect(api.invokeAgent).not.toHaveBeenCalled();
  });

  it("posts then asks the agent when tagged", async () => {
    await type("@agent create sales order");
    await waitFor(() => expect(api.invokeAgent).toHaveBeenCalledWith("c1", "sonnet-4-6", "ask"));
    expect(api.postMessage).toHaveBeenCalledWith("c1", "seller", "@agent create sales order");
  });

  it("routes @agent confirm to approve", async () => {
    await type("@agent confirm");
    await waitFor(() => expect(api.invokeAgent).toHaveBeenCalledWith("c1", "sonnet-4-6", "approve"));
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `apps/web`): `npm test -- src/pages/ChatPage.test.tsx`
Expected: FAIL — `handleMessage` doesn't invoke the agent (Ask-agent flow still separate) and `MessageComposer` props mismatch.

- [ ] **Step 4: Rework `ChatPage`**

Edit `apps/web/src/pages/ChatPage.tsx`:

1. Add the import: `import { parseAgentTag } from "@/lib/agentTag";`
2. Replace `handleMessage` with:

```tsx
  async function handleMessage(body: string) {
    if (!selectedId) return;
    try {
      await api.postMessage(selectedId, role, body);
      const { isAgent, action } = parseAgentTag(body);
      if (isAgent) {
        await api.invokeAgent(selectedId, modelKey, action);
      }
      await loadMessages(selectedId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to send message");
    }
  }
```

3. Delete `handleAskAgent`, `handleApprove`, the `pendingSummary` state, the `showApprove` helper usage, `pendingFromMessages`, and `showApprove` — plus the `Slot`/`PendingSummary` bits only used by them. Keep `loadMessages` setting messages (drop its `setPendingSummary(...)` call).
4. Update the `MessageComposer` usage to the new props:

```tsx
        <MessageComposer role={role} onRoleChange={setRole} onMessage={handleMessage} />
```

- [ ] **Step 5: Run test + typecheck to verify pass**

Run (from `apps/web`): `npm test -- src/pages/ChatPage.test.tsx src/api/client.test.ts`
Then: `npm run build`
Expected: tests PASS; `tsc` reports no errors (no dangling references to removed helpers/props).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/api/client.ts apps/web/src/pages/ChatPage.tsx apps/web/src/pages/ChatPage.test.tsx
git commit -m "feat(web): invoke the agent from @agent-tagged messages"
```

---

## Task 11: Markdown card bodies + JSON on every agent message (`ChatPane`)

**Files:**
- Modify: `apps/web/src/components/ChatPane.tsx`
- Test: `apps/web/src/components/ChatPane.test.tsx`

**Interfaces:**
- Consumes: `Message` type (`chat_id`, `chat_status`, `summary_json`), `Markdown` component.
- Produces: `draft`/`final`/`summary` cards render via `<Markdown>`; a collapsible JSON `<details>` renders on **any** agent message with `summary_json`.

- [ ] **Step 1: Update the test fixture and add tests**

In `apps/web/src/components/ChatPane.test.tsx`, extend the `msg` helper to include the new fields and (optionally) accept overrides:

```tsx
function msg(seq: number, role: string, body: string, extra: Partial<Message> = {}): Message {
  return {
    id: `m${seq}`,
    customer_id: "c1",
    chat_id: "chat-1",
    chat_status: "active",
    seq,
    role,
    kind: "message",
    body,
    summary_id: null,
    summary_json: null,
    created_at: "2026-07-20T00:00:00Z",
    ...extra,
  };
}
```

Add a new describe block:

```tsx
describe("ChatPane agent rendering", () => {
  it("renders final card body as markdown (bold, not literal asterisks)", () => {
    const { container } = render(
      <ChatPane messages={[msg(1, "agent", "Done.\n\n- **tea** — qty 18 MT", { kind: "final" })]} />,
    );
    expect(container.querySelector("strong")?.textContent).toBe("tea");
    expect(container.textContent).not.toContain("**tea**");
  });

  it("shows a collapsible JSON block on a plain agent question", () => {
    render(
      <ChatPane messages={[msg(1, "agent", "Which product?",
        { kind: "question", summary_json: '{"mode":"clarify"}' })]} />,
    );
    expect(screen.getByText(/Raw model response \(JSON\)/i)).toBeTruthy();
    expect(screen.getByText(/"mode":"clarify"/)).toBeTruthy();
  });
});
```

Add `import { screen } from "@testing-library/react";` if not already imported.

- [ ] **Step 2: Run test to verify it fails**

Run (from `apps/web`): `npm test -- src/components/ChatPane.test.tsx`
Expected: FAIL — the card renders `<pre>` (literal `**tea**`, no `<strong>`) and question messages have no JSON block.

- [ ] **Step 3: Refactor `ChatPane` rendering**

In `apps/web/src/components/ChatPane.tsx`:

1. Add a small JSON sub-component near the top of the file (after imports):

```tsx
function JsonDetails({ json }: { json: string }) {
  return (
    <details className="text-xs">
      <summary className="cursor-pointer select-none text-muted-foreground hover:text-foreground">
        Raw model response (JSON)
      </summary>
      <pre className="mt-2 max-h-80 overflow-auto rounded-md bg-muted p-3 font-mono text-[11px] leading-relaxed">
        {json}
      </pre>
    </details>
  );
}
```

2. In the card branch (`["summary", "draft", "final"].includes(message.kind)`), replace the `<pre className="whitespace-pre-wrap text-sm">{message.body}</pre>` line with `<Markdown>{message.body}</Markdown>`, and replace the inline `{message.summary_json && (<details>…</details>)}` block with `{message.summary_json && <JsonDetails json={message.summary_json} />}`.

3. In the trailing agent/seller/customer branch, after the `{isAgentRole(message.role) ? <Markdown>… : <div>…</div>}` block, append (inside the same wrapper `div`, before its closing tag):

```tsx
            {isAgentRole(message.role) && message.summary_json && (
              <div className="mt-2">
                <JsonDetails json={message.summary_json} />
              </div>
            )}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `apps/web`): `npm test -- src/components/ChatPane.test.tsx`
Expected: PASS (existing provenance tests plus the two new ones).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/ChatPane.tsx apps/web/src/components/ChatPane.test.tsx
git commit -m "feat(web): render agent cards as markdown and show JSON on every agent message"
```

---

## Task 12: `@agent` mention chip in the thread (`ChatPane`)

**Files:**
- Modify: `apps/web/src/components/ChatPane.tsx`
- Test: `apps/web/src/components/ChatPane.test.tsx`

**Interfaces:**
- Consumes: `splitAgentMention` (Task 1).
- Produces: seller/customer plain-text bubbles render a leading `@agent` token as a styled mention chip.

- [ ] **Step 1: Write the failing test**

Add to the `ChatPane agent rendering` describe block:

```tsx
  it("highlights the @agent mention in a seller message", () => {
    const { container } = render(
      <ChatPane messages={[msg(1, "seller", "@agent create sales order")]} />,
    );
    const chip = container.querySelector('[data-testid="agent-mention"]');
    expect(chip?.textContent).toBe("@agent");
    expect(container.textContent).toContain("create sales order");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `apps/web`): `npm test -- src/components/ChatPane.test.tsx`
Expected: FAIL — no `[data-testid="agent-mention"]` node.

- [ ] **Step 3: Render the chip**

In `apps/web/src/components/ChatPane.tsx`:

1. Add the import: `import { splitAgentMention } from "@/lib/agentTag";`
2. Add a helper component:

```tsx
function MessageText({ body }: { body: string }) {
  const { mention, rest } = splitAgentMention(body);
  if (!mention) return <div className="whitespace-pre-wrap leading-relaxed">{body}</div>;
  return (
    <div className="whitespace-pre-wrap leading-relaxed">
      <span
        data-testid="agent-mention"
        className="rounded bg-indigo-500/15 px-1 font-medium text-indigo-600 dark:text-indigo-300"
      >
        {mention}
      </span>
      {rest}
    </div>
  );
}
```

3. In the trailing branch, replace the non-agent render `<div className="whitespace-pre-wrap leading-relaxed">{message.body}</div>` with `<MessageText body={message.body} />`.

- [ ] **Step 4: Run test to verify it passes**

Run (from `apps/web`): `npm test -- src/components/ChatPane.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/ChatPane.tsx apps/web/src/components/ChatPane.test.tsx
git commit -m "feat(web): highlight the @agent mention in chat messages"
```

---

## Task 13: Checkpoint divider at finished-chat boundaries (`ChatPane`)

**Files:**
- Modify: `apps/web/src/components/ChatPane.tsx`
- Test: `apps/web/src/components/ChatPane.test.tsx`

**Interfaces:**
- Consumes: `Message.chat_id`, `Message.chat_status`.
- Produces: a centered checkpoint divider renders after the last message of any chat whose `chat_status === "finished"`.

- [ ] **Step 1: Write the failing test**

Add to the `ChatPane agent rendering` describe block:

```tsx
  it("renders a checkpoint divider after a finished chat's last message", () => {
    const { getByText, queryByText } = render(
      <ChatPane
        messages={[
          msg(1, "agent", "Approved.", { kind: "final", chat_id: "chat-1", chat_status: "finished" }),
          msg(1, "seller", "next deal", { id: "m2", chat_id: "chat-2", chat_status: "active" }),
        ]}
      />,
    );
    expect(getByText(/Contract finalized · new chat started/)).toBeTruthy();
    // active chat's messages do not get a trailing divider
    const dividers = document.querySelectorAll('[data-testid="chat-checkpoint"]');
    expect(dividers.length).toBe(1);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `apps/web`): `npm test -- src/components/ChatPane.test.tsx`
Expected: FAIL — no checkpoint element.

- [ ] **Step 3: Add the divider to the map**

In `apps/web/src/components/ChatPane.tsx`:

1. Add `Fragment` to the React import: `import { Fragment, useEffect, useRef } from "react";`
2. Add a divider component:

```tsx
function CheckpointDivider() {
  return (
    <div data-testid="chat-checkpoint" className="flex items-center gap-3 py-2">
      <div className="h-px flex-1 bg-border" />
      <span className="rounded-full bg-muted px-3 py-0.5 text-[11px] font-medium text-muted-foreground">
        ✓ Contract finalized · new chat started
      </span>
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}
```

3. Extract the current per-message JSX into a local `renderMessage(message)` function (move the whole body of the existing `messages.map((message) => { … })` callback into it, returning the same JSX). Then change the map to wrap each item and conditionally append the divider:

```tsx
      {messages.map((message, i) => {
        const next = messages[i + 1];
        const isChatEnd = !next || next.chat_id !== message.chat_id;
        const showCheckpoint = isChatEnd && message.chat_status === "finished";
        return (
          <Fragment key={message.id}>
            {renderMessage(message)}
            {showCheckpoint && <CheckpointDivider />}
          </Fragment>
        );
      })}
```

Note: `renderMessage` must no longer set its own `key` on the returned root (the `Fragment` now carries the key); leave the inner `key` off or harmless. Keep the `data-seq` attributes.

- [ ] **Step 4: Run test + full ChatPane suite to verify pass**

Run (from `apps/web`): `npm test -- src/components/ChatPane.test.tsx`
Expected: PASS (all checkpoint + earlier tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/ChatPane.tsx apps/web/src/components/ChatPane.test.tsx
git commit -m "feat(web): show a checkpoint divider between finished and new chats"
```

---

## Task 14: `CONTINUES` edge styling + cross-link lock (graph FE)

**Files:**
- Modify: `apps/web/src/components/GraphCanvas.tsx`
- Create: `apps/web/src/components/GraphCanvas.test.ts`
- Modify: `apps/web/src/components/graph/hierarchy.test.ts`

**Interfaces:**
- Produces: `edgeStroke(type: string): string` (exported) — `SUPERSEDES` → rose, `CONTINUES` → indigo, else slate.

- [ ] **Step 1: Write the failing tests**

Create `apps/web/src/components/GraphCanvas.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { edgeStroke } from "./GraphCanvas";

describe("edgeStroke", () => {
  it("colors CONTINUES distinctly from SUPERSEDES and default", () => {
    expect(edgeStroke("SUPERSEDES")).toBe("#f43f5e");
    expect(edgeStroke("CONTINUES")).toBe("#6366f1");
    expect(edgeStroke("HAS_CHAT")).toBe("#cbd5e1");
  });
});
```

Add to `apps/web/src/components/graph/hierarchy.test.ts`:

```ts
import { CONTAINMENT_EDGE_TYPES, childrenMap } from "./hierarchy";

it("treats CONTINUES as a cross-link, not containment", () => {
  expect(CONTAINMENT_EDGE_TYPES.has("CONTINUES")).toBe(false);
  const kids = childrenMap([
    { id: "e", source: "Chat::b", target: "Chat::a", type: "CONTINUES", properties: {} },
  ]);
  expect(kids.size).toBe(0); // CONTINUES does not create parent→child nesting
});
```

(If `hierarchy.test.ts` already imports `CONTAINMENT_EDGE_TYPES`/`childrenMap`, reuse the existing import instead of duplicating it.)

- [ ] **Step 2: Run tests to verify they fail**

Run (from `apps/web`): `npm test -- src/components/GraphCanvas.test.ts src/components/graph/hierarchy.test.ts`
Expected: FAIL — `edgeStroke` is not exported.

- [ ] **Step 3: Export `edgeStroke` and use it**

In `apps/web/src/components/GraphCanvas.tsx`, add above `toFlowEdges`:

```tsx
export function edgeStroke(type: string): string {
  if (type === "SUPERSEDES") return "#f43f5e";
  if (type === "CONTINUES") return "#6366f1";
  return "#cbd5e1";
}
```

Then in `toFlowEdges`, replace `style: { stroke: e.type === "SUPERSEDES" ? "#f43f5e" : "#cbd5e1" },` with `style: { stroke: edgeStroke(e.type) },`.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `apps/web`): `npm test -- src/components/GraphCanvas.test.ts src/components/graph/hierarchy.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/GraphCanvas.tsx apps/web/src/components/GraphCanvas.test.ts apps/web/src/components/graph/hierarchy.test.ts
git commit -m "feat(web): style CONTINUES chat-lineage edges in the graph"
```

---

## Task 15: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole backend suite**

Run (repo root): `python -m pytest tests/api -v`
Expected: PASS (FalkorDB-gated tests may SKIP if the DB is down; start `docker-compose up -d` and re-run the `test_chat_graph_falkor.py` cases to confirm `open_branch` / `CONTINUES` pass live).

- [ ] **Step 2: Run the whole frontend suite + typecheck**

Run (from `apps/web`): `npm test`
Then: `npm run build`
Expected: all vitest files PASS; `tsc -b` clean.

- [ ] **Step 3: Manual smoke (optional but recommended)**

With API + web + Mongo + FalkorDB running: type `@agent create sales order` as Seller (draft appears, JSON collapsible, markdown clean), exchange messages until both agree, send `@agent confirm` (contract finalizes, checkpoint divider appears, new chat begins), and confirm the Graphs page shows a `CONTINUES`-linked new branch.

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "test: verify chat UX improvements end-to-end"
```

---

## Self-Review Notes (spec coverage)

- Req 1 (`@agent` replaces button): Tasks 1, 2, 10.
- Req 2 (tagged message visible): Task 10 (post before invoke) + Task 12 (mention chip).
- Req 3 (formatting): Task 3 (one-line intro) + Task 11 (markdown cards).
- Req 4 (JSON on every agent message): Tasks 5, 7 (backend attach) + Task 11 (render on all).
- Req 5 (finalize only on tagged confirm, gated): Tasks 3, 5, 7, 10.
- Req 6 (new chat branch + checkpoint): Tasks 4, 6, 7, 8, 9, 13, 14.
