import pytest

from apps.api.db import falkor
from apps.api.services import chat_graph_service as cg
from apps.api.services import graph_reader_service as gr
from apps.api.services import profile_graph_service as pg


@pytest.fixture()
def cid():
    c = "test-reader"
    yield c
    if falkor.is_available():
        falkor.customer_graph(c).delete()


def _skip():
    if not falkor.is_available():
        pytest.skip("FalkorDB not reachable")


def test_customer_graph_reads_branch_and_tags_chat(cid):
    _skip()
    pg.resync(cid, "T", {"email": "a@b.com"})
    cg.write_contract(cid, "chat-1", "Deal A",
        {"items": [{"sr_no": 1, "description": "TG-BPPC", "quantity": 10, "quantity_unit": "MT",
                    "unit_price": 100, "pricing_unit": "USD/MT", "ship_term": "CIF",
                    "delivery_terms": "", "shipment_date": "", "shipping_address": "Busan",
                    "packing": "", "loading": "", "total": None}]},
        [], [], to_seq=1)
    data = gr.read_customer_graph(cid)
    types = {n["type"] for n in data["nodes"]}
    assert {"Customer", "Chat", "Contract", "LineItem", "Port", "Attribute"} <= types
    line = next(n for n in data["nodes"] if n["type"] == "LineItem")
    assert line["chat_id"] == "chat-1"


def test_empty_customer_graph(cid):
    _skip()
    assert gr.read_customer_graph("no-such") == {"nodes": [], "edges": []}
