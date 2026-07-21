from apps.api.models import is_ready, missing_agreement, render_summary_markdown

from tests.api._factories import make_extract, make_item, make_update


def test_summary_markdown_lists_products():
    s = make_extract(
        items=[make_item(description="TG-BPPC", quantity=10, quantity_unit="MT",
                         unit_price=100, pricing_unit="USD/MT", ship_term="FOB",
                         shipping_address="Busan")],
        payment_date="30% advance",
    )
    md = render_summary_markdown(s, "Dummy-01")
    assert "TG-BPPC" in md
    assert "Busan" in md
    assert "30% advance" in md
    assert "Dummy-01" in md


def test_summary_markdown_handles_update_schema():
    s = make_update(items=[make_item(description="TG-MGL8")], vendor_name="Tractus")
    md = render_summary_markdown(s)
    assert "TG-MGL8" in md
    assert "Tractus" in md


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
