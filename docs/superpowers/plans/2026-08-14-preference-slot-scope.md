# Preference Slot Scope (Cursor I3-remainder) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop deriving customer `Preference` nodes from per-line, per-order-varying slots (`quantity`, `description`) so the learning-loop grounding stays meaningful and no longer collapses multi-line values to last-write-wins.

**Architecture:** Introduce a pure `is_preferable_slot()` predicate naming the slots that make sense as a *customer default* (recurring terms), and gate `chat_graph_service.write_contract`'s `Preference` derivation on it. No schema change.

**Tech Stack:** Python 3, Pydantic v2, pytest, FalkorDB (integration test skips when unreachable).

**Spec:** Resolves the `Preference` half of Cursor review finding **I3** on PR #9 ("`LineItem.agreed_by` / `Preference` still key only by slot name … `Preference {slot: quantity}` keeps the last line's value"). The `agreed_by` half was already fixed in `53e9852`. Context: [`docs/contract-agent-harness.md`](../../contract-agent-harness.md) (the "Preferences are the feedback loop" grounding), `apps/api/services/summary_context_service.py::_history_block` (how Preferences are read back as "Typical terms").

## Global Constraints

- **No new dependencies; no schema change.** `Preference` nodes keep their shape.
- **Design decision (baked in): preferable slots = `ship_term`, `packing`, `loading`, `payment_date`.** These are recurring "typical terms" a customer tends to repeat. `quantity` and `description` vary every order and are excluded. Confirm this set with the reviewer/owner before shipping if unsure — it's the one judgment call in this plan.
- **Backward-compatible.** Existing `Preference {slot: quantity}` / `{slot: description}` nodes already in a graph are left untouched (not deleted); they simply stop being reinforced. A follow-up migration could prune them, out of scope here.
- **Run `pytest tests/api -q` before each commit.**

## Design Rationale

`write_contract` currently does `for s in slots: if agreed_by ⊇ {seller,customer} and value: MERGE (Preference {slot})` — one preference per both-agreed slot (`apps/api/services/chat_graph_service.py:176`). Those nodes are read back verbatim by `summary_context_service._history_block` as `"Typical terms:\n- <slot>: <value> (seen Nx)"` and fed into the next draft's grounding. A "typical term" of `quantity: 10` is noise, and with per-line ledgers two `quantity` entries `MERGE` onto one `Preference {slot:"quantity"}` (last-write-wins). Restricting derivation to genuinely-recurring term slots fixes both the noise and the collapse.

---

### Task 1: `is_preferable_slot` predicate

**Files:**
- Modify: `apps/api/models.py:156-157` (near `CRITICAL_SLOTS`)
- Test: `tests/api/test_agent_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `PREFERABLE_SLOTS: set[str]` and `def is_preferable_slot(slot: str) -> bool`.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_agent_models.py` and extend its import on line 1 to include the new names:

```python
from apps.api.models import (
    AgentDecision, AgentQuestion, SlotBelief, cap_questions, is_ready,
    missing_agreement, is_preferable_slot,
)
```

Then append:

```python
def test_preferable_slots_are_recurring_terms_only():
    assert is_preferable_slot("ship_term")
    assert is_preferable_slot("payment_date")
    assert is_preferable_slot("packing")
    assert is_preferable_slot("loading")
    # per-order-varying slots are NOT customer defaults
    assert not is_preferable_slot("quantity")
    assert not is_preferable_slot("description")
    assert not is_preferable_slot("unit_price")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/api/test_agent_models.py::test_preferable_slots_are_recurring_terms_only -q`
Expected: FAIL — `ImportError: cannot import name 'is_preferable_slot'`.

- [ ] **Step 3: Add the predicate**

In `apps/api/models.py`, right after the `CRITICAL_SLOTS` definition (line 157), add:

```python
# Slots worth remembering as a customer default (recurring "typical terms").
# Deliberately excludes quantity / description / unit_price, which vary per order.
PREFERABLE_SLOTS = {"ship_term", "packing", "loading", "payment_date"}


def is_preferable_slot(slot: str) -> bool:
    return slot in PREFERABLE_SLOTS
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/api/test_agent_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/models.py tests/api/test_agent_models.py
git commit -m "feat(models): add is_preferable_slot predicate (recurring terms only)"
```

---

### Task 2: Gate `Preference` derivation on the predicate

**Files:**
- Modify: `apps/api/services/chat_graph_service.py:176-178` (the derived-preferences loop)
- Test: `tests/api/test_chat_graph_falkor.py`

**Interfaces:**
- Consumes: `is_preferable_slot` from `apps/api/models.py` (Task 1).
- Produces: `write_contract` only `MERGE`s a `Preference` for slots where `is_preferable_slot(slot)` is true.

- [ ] **Step 1: Write the failing test (skips when FalkorDB is down)**

Append to `tests/api/test_chat_graph_falkor.py`:

```python
def test_preferences_only_for_recurring_terms(graph_name):
    _skip_if_down()
    contract = {"items": [{"sr_no": 1, "description": "TG-BPPC", "quantity": 10,
        "quantity_unit": "MT", "unit_price": 100, "pricing_unit": "USD/MT",
        "ship_term": "CIF", "delivery_terms": "", "shipment_date": "",
        "shipping_address": "", "packing": "25kg", "loading": "", "total": 1000}],
        "vendor_name": "", "payment_date": "Net 30"}
    both = ["seller", "customer"]
    slots = [
        {"slot": "ship_term", "value": "CIF", "agreed_by": both, "source_seqs": [1]},
        {"slot": "payment_date", "value": "Net 30", "agreed_by": both, "source_seqs": [1]},
        {"slot": "quantity", "value": "10", "agreed_by": both, "source_seqs": [1]},
        {"slot": "description", "value": "TG-BPPC", "agreed_by": both, "source_seqs": [1]},
    ]
    cg.write_contract(graph_name, "chat-1", "Deal", contract, slots, [], to_seq=1)
    g = falkor.customer_graph(graph_name)
    pref_slots = {r[0] for r in g.query(
        "MATCH (:Customer)-[:PREFERS]->(pr:Preference) RETURN pr.slot").result_set}
    assert "ship_term" in pref_slots
    assert "payment_date" in pref_slots
    assert "quantity" not in pref_slots
    assert "description" not in pref_slots
```

- [ ] **Step 2: Run the test to verify it fails (or skips if FalkorDB is unavailable)**

Run: `pytest tests/api/test_chat_graph_falkor.py::test_preferences_only_for_recurring_terms -v`
Expected: FAIL — `quantity` and `description` currently become Preferences, so the `not in` assertions fail. If it prints `SKIPPED (FalkorDB not reachable)`, start FalkorDB (`docker compose up -d falkordb`).

- [ ] **Step 3: Gate the derivation**

In `apps/api/services/chat_graph_service.py`, add the import at the top (it currently imports only `falkor`):

```python
from apps.api.models import is_preferable_slot
```

Then change the derived-preferences loop (currently line 176-178) from:

```python
    # derived preferences: one per slot agreed by both parties
    for s in slots:
        if set(s.get("agreed_by", [])) >= {"seller", "customer"} and s.get("value"):
```

to:

```python
    # derived preferences: one per recurring-term slot agreed by both parties.
    # quantity / description vary per order, so they are never customer defaults.
    for s in slots:
        if (is_preferable_slot(s["slot"])
                and set(s.get("agreed_by", [])) >= {"seller", "customer"}
                and s.get("value")):
```

- [ ] **Step 4: Run the graph tests to verify the new test passes and existing ones still pass**

Run: `pytest tests/api/test_chat_graph_falkor.py -v`
Expected: PASS — the new test passes; `test_write_contract_creates_branch` still passes because its assertion `["ship_term", "CIF"] in prefs` targets a preferable slot.

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/chat_graph_service.py tests/api/test_chat_graph_falkor.py
git commit -m "fix(graph): derive Preferences only for recurring-term slots (drop quantity/description)"
```

---

## Self-Review

**Spec coverage:** I3-`Preference` half → Task 1 (predicate) + Task 2 (gate). The `agreed_by` half was already fixed (`53e9852`), so this plan closes the finding. ✅
**Placeholder scan:** real code + real assertions in every step. ✅
**Type consistency:** `is_preferable_slot(slot: str) -> bool` defined in Task 1, imported and called identically in Task 2. `PREFERABLE_SLOTS` set matches the values asserted in the Task 1 test. ✅
**Deferred/out of scope:** pruning pre-existing `Preference {slot: quantity|description}` nodes already in graphs (a one-off migration); whether `ship_term` on a multi-item order with two different incoterms should keep one preference (acceptable — a customer's "typical incoterm" is a single value).
