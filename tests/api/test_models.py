from apps.api.models import render_summary_markdown

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
