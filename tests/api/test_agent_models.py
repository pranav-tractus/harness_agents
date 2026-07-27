from apps.api.models import AgentDecision, AgentQuestion, SlotBelief, cap_questions


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
