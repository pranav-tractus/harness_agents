import pytest

from apps.api.db import falkor
from apps.api.services import chat_graph_service as cg


@pytest.fixture()
def graph_name():
    cid = "test-chatgraph"
    yield cid
    if falkor.is_available():
        falkor.customer_graph(cid).delete()


def _skip_if_down():
    if not falkor.is_available():
        pytest.skip("FalkorDB not reachable")


def test_write_contract_creates_branch(graph_name):
    _skip_if_down()
    contract = {"items": [{"sr_no": 1, "description": "TG-BPPC", "quantity": 10,
        "quantity_unit": "MT", "unit_price": 100, "pricing_unit": "USD/MT",
        "ship_term": "CIF", "delivery_terms": "CIF Busan", "shipment_date": "",
        "shipping_address": "Busan", "packing": "25kg", "loading": "", "total": 1000}],
        "vendor_name": "TG", "payment_date": "30% advance"}
    slots = [{"slot": "ship_term", "value": "CIF", "source": "chat",
              "confidence": "high", "agreed_by": ["seller", "customer"]}]
    cid = cg.write_contract(graph_name, "chat-1", "Deal A", contract, slots,
                            [{"seq": 42, "role": "customer", "snippet": "CIF Busan"}], to_seq=42)
    g = falkor.customer_graph(graph_name)
    lines = g.query("MATCH (:Contract)-[:HAS_LINE]->(li:LineItem) RETURN li.product_code").result_set
    assert lines[0][0] == "TG-BPPC"
    ports = g.query("MATCH (:LineItem)-[:SHIP_TO]->(p:Port) RETURN p.name").result_set
    assert ports[0][0] == "Busan"
    prefs = g.query("MATCH (:Customer)-[:PREFERS]->(pr:Preference) RETURN pr.slot, pr.value").result_set
    assert ["ship_term", "CIF"] in [list(r) for r in prefs]
    assert isinstance(cid, str)
