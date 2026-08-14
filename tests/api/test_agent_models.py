from apps.api.models import (
    AgentDecision, AgentQuestion, SlotBelief, cap_questions, is_ready, missing_agreement,
)


def _q(slot):
    return AgentQuestion(slot=slot, directed_to="customer", text=f"what {slot}?")


def test_cap_keeps_three_criticals_first():
    d = AgentDecision(
        mode="clarify", message="…",
        questions=[_q("packing"), _q("quantity"), _q("loading"),
                   _q("unit_price"), _q("ship_term")],
    )
    out = cap_questions(d)
    slots = [q.slot for q in out.questions]
    assert len(slots) == 3
    # criticals (quantity, unit_price, ship_term) win the 3 slots over soft ones
    assert set(slots) == {"quantity", "unit_price", "ship_term"}


def test_ledger_and_agreement_roundtrip():
    d = AgentDecision(
        mode="draft", message="draft ready",
        ledger=[SlotBelief(slot="ship_term", value="CIF", source="chat",
                           confidence="high", agreed_by=["seller", "customer"])],
        ready_to_finalize=False,
    )
    assert d.ledger[0].agreed_by == ["seller", "customer"]


def test_slot_belief_provenance_defaults():
    s = SlotBelief(slot="quantity", value="10", source="chat")
    assert s.source_seqs == []
    assert s.evidence is None


def test_slot_belief_carries_source_seqs_and_evidence():
    s = SlotBelief(slot="quantity", value="10", source="chat",
                   source_seqs=[42, 43], evidence="10 MT")
    assert s.source_seqs == [42, 43]
    assert s.evidence == "10 MT"


def test_slot_belief_line_defaults_none_and_roundtrips():
    assert SlotBelief(slot="quantity").line is None
    assert SlotBelief(slot="quantity", value="5", line=2).line == 2


def test_missing_agreement_flags_any_unagreed_line_entry():
    both = ["seller", "customer"]
    slots = [
        {"slot": "description", "agreed_by": both},
        {"slot": "quantity", "line": 1, "agreed_by": both},
        {"slot": "quantity", "line": 2, "agreed_by": ["seller"]},
        {"slot": "unit_price", "agreed_by": both},
        {"slot": "ship_term", "agreed_by": both},
    ]
    assert "quantity" in missing_agreement(slots)
    assert not is_ready(slots)


def test_missing_agreement_single_entry_unchanged():
    both = ["seller", "customer"]
    slots = [{"slot": s, "agreed_by": both}
             for s in ["description", "quantity", "unit_price", "ship_term"]]
    assert missing_agreement(slots) == []
    assert is_ready(slots)
