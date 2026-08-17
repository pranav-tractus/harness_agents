# Per-Item Ledger Coverage (Cursor I4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For a contract with two or more line items, require every item to carry its own `line`-scoped ledger entry for each critical slot, so agreement and provenance can no longer silently fall back to a single shared order-level value.

**Architecture:** Add a coverage check to the deterministic `verify()` gate (which, unlike `is_ready`, has the contract's item list). When there are ≥2 items, any missing `(sr_no, slot)` critical entry blocks with `missing_line_coverage`. Combined with the already-strict `missing_agreement` (every entry must be agreed) this makes multi-item readiness require per-line agreement.

**Tech Stack:** Python 3, Pydantic v2, pytest.

**Spec:** Resolves Cursor review finding **I4** on PR #9 ("`is_ready` / `verify()` do not require per-item ledger coverage or `line`. A two-item contract with one order-level agreed quantity is ready, and omitted `line` falls back to shared `flat_prov` — the original multi-item provenance bug, one skipped field away."). Builds on `SlotBelief.line` and the per-line provenance/`agreed_by` already shipped (`5e80bd1`, `53e9852`), and the prompt that already asks the model to set `line`. Context: [`docs/contract-agent-harness.md`](../../contract-agent-harness.md).

## Global Constraints

- **No new dependencies; no schema change.**
- **Coverage is enforced in `verify()`, not `is_ready()`.** `is_ready(slots)` has no contract and cannot know how many items exist; it stays slot-only (already strict: every entry must be agreed). `verify()` has the contract item list and owns coverage. Both run at `approve()`.
- **Only multi-item contracts (≥2 items) are affected.** A single-item contract may keep an order-level (line-less) ledger, preserving backward compatibility with existing single-item drafts. New drafts get `line` from the prompt regardless.
- **Interacts with I1 (already shipped):** each covered per-line critical entry must still be `source="chat"` with a citation, or the existing `critical_not_chat_sourced` / `missing_provenance` blocks fire independently. Coverage only checks presence.
- **Run `pytest tests/api -q` before each commit.**

## Design Rationale

`missing_agreement` already requires *every* ledger entry for a critical slot to be agreed by both parties. The remaining gap is that a 2-item contract can satisfy it with a *single* order-level `quantity` entry — no per-item entries at all — and `write_contract` then shares that entry's provenance/`agreed_by` across both `LineItem`s (the `flat_prov` fallback). Enforcing that each item has its own `(sr_no, slot)` entry closes the gap at its source. `verify()` already computes `items = contract.data[0].items`, so the check is local.

---

### Task 1: `missing_line_coverage` check in `verify()`

**Files:**
- Modify: `apps/api/verification.py` (imports + a block before `return out`)
- Test: `tests/api/test_verification.py`
- Docs: `apps/web/src/architecture/spec.ts`, `docs/contract-agent-harness.md` (then regenerate `docs/architecture.md`)

**Interfaces:**
- Consumes: `CRITICAL_SLOTS_ORDER` from `apps/api/models.py`; each contract item's `sr_no`; ledger dicts with optional `line`.
- Produces: a `missing_line_coverage` (severity `block`) `Violation` for each `(item.sr_no, critical_slot)` with no line-scoped ledger entry, emitted only when the contract has ≥2 items.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_verification.py`:

```python
def _line_slots(sr):
    return [{"slot": s, "value": "x", "source": "chat", "line": sr, "source_seqs": [1]}
            for s in ["description", "quantity", "unit_price", "ship_term"]]


def test_multi_item_full_line_coverage_passes():
    contract = make_extract(items=[
        make_item(sr_no=1, description="A", ship_term="CIF"),
        make_item(sr_no=2, description="B", ship_term="FOB")])
    slots = _line_slots(1) + _line_slots(2)
    v = verify(contract, slots, resolved_codes={"A", "B"}, window_seqs={1})
    assert not any(x.code == "missing_line_coverage" for x in v)


def test_multi_item_missing_line_coverage_blocks():
    contract = make_extract(items=[
        make_item(sr_no=1, description="A", ship_term="CIF"),
        make_item(sr_no=2, description="B", ship_term="FOB")])
    # a single order-level quantity, no per-line entries — the I4 bug
    slots = [{"slot": "quantity", "value": "10", "source": "chat", "source_seqs": [1]}]
    v = verify(contract, slots, resolved_codes={"A", "B"}, window_seqs={1})
    assert any(x.code == "missing_line_coverage" and x.severity == "block" for x in v)


def test_single_item_order_level_ledger_is_allowed():
    contract = make_extract(items=[make_item(description="A", ship_term="CIF")])
    slots = [{"slot": s, "value": "x", "source": "chat", "source_seqs": [1]}
             for s in ["description", "quantity", "unit_price", "ship_term"]]
    v = verify(contract, slots, resolved_codes={"A"}, window_seqs={1})
    assert not any(x.code == "missing_line_coverage" for x in v)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/api/test_verification.py -k "line_coverage or order_level" -q`
Expected: FAIL — `test_multi_item_missing_line_coverage_blocks` finds no `missing_line_coverage` violation (the check doesn't exist yet). The other two pass trivially (also no such code), so run them again after Step 3 to confirm they stay green.

- [ ] **Step 3: Add the coverage check**

In `apps/api/verification.py`, extend the models import (currently `from apps.api.models import CRITICAL_SLOTS`):

```python
from apps.api.models import CRITICAL_SLOTS, CRITICAL_SLOTS_ORDER
```

Then, immediately before `return out` at the end of `verify()`, add:

```python
    # Per-item ledger coverage. Only meaningful with >=2 line items: there an
    # order-level (line-less) critical slot is shared/ambiguous across items, and
    # an omitted per-line entry silently falls back to that single shared value.
    if len(items) >= 2:
        covered = {
            (int(s["line"]), s["slot"])
            for s in slots
            if s.get("line") is not None and s.get("value") is not None
        }
        for it in items:
            for slot in CRITICAL_SLOTS_ORDER:
                if (it.sr_no, slot) not in covered:
                    out.append(Violation(
                        code="missing_line_coverage", slot=slot, severity="block",
                        message=(f"Line item sr_no={it.sr_no} has no ledger entry "
                                 f"for critical slot '{slot}'."),
                    ))

    return out
```

(Remove the old bare `return out` so there is exactly one at the end.)

- [ ] **Step 4: Run the verifier tests and the full API suite**

Run: `pytest tests/api/test_verification.py -q && pytest tests/api -q`
Expected: PASS. Existing single-item verify tests and all invoke/approve/endpoint tests are unaffected because their contracts have 0 or 1 item (`len(items) < 2`).

- [ ] **Step 5: Update the docs**

In `apps/web/src/architecture/spec.ts`, add `missing_line_coverage` to the `agent.verify` node's blocking-codes invariant (the string listing `unknown_product_code, missing_ship_term, …, missing_provenance`).

In `docs/contract-agent-harness.md`, add a bullet to the verify checklist (the "**Harness — deterministic verification:**" list in the draft-time verify step):

```markdown
  - **per-item coverage** — in a contract with 2+ line items, each item must
    carry its own `line`-scoped ledger entry for every critical slot
    (blocking `missing_line_coverage`), so agreement and provenance are never
    shared across items;
```

Then regenerate the architecture doc:

```bash
cd apps/web && npm run gen:arch
```

- [ ] **Step 6: Commit**

```bash
git add apps/api/verification.py tests/api/test_verification.py \
        apps/web/src/architecture/spec.ts docs/architecture.md docs/contract-agent-harness.md
git commit -m "feat(verification): require per-line-item ledger coverage on multi-item contracts"
```

---

## Self-Review

**Spec coverage:** I4 → Task 1 blocks a multi-item contract whose critical slots aren't per-line-covered. The companion "reject order-level critical when N≥2" is subsumed: an order-level entry has `line=None`, so it never appears in `covered`, so every item reports `missing_line_coverage` for that slot. Per-line *agreement* is then enforced by the existing strict `missing_agreement`. ✅
**Placeholder scan:** real code + real assertions throughout; the one prose step (docs) gives the exact strings to add. ✅
**Type consistency:** `missing_line_coverage` code string matches between the implementation and the test; `covered` is a `set[tuple[int, str]]` keyed the same way it's queried (`(it.sr_no, slot)`); `CRITICAL_SLOTS_ORDER` is the imported list. ✅
**Deferred/out of scope:** requiring `line` on single-item contracts (legacy line-less ledgers stay valid); a draft-time UX that asks per-item clarifying questions when coverage is missing (today a missing-coverage draft simply blocks → the agent posts the verifier's messages as a question, which is acceptable).
