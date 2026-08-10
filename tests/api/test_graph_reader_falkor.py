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


def test_reader_emits_supersedes_edge(cid):
    _skip()
    pg.resync(cid, "T", {})
    empty = {"items": []}
    cg.write_contract(cid, "chat-1", "A", empty, [], [], to_seq=1)
    cg.write_contract(cid, "chat-1", "A", empty, [], [], to_seq=2)
    data = gr.read_customer_graph(cid)
    supersedes = [e for e in data["edges"] if e["type"] == "SUPERSEDES"]
    assert len(supersedes) == 1
    contracts = {n["id"]: n for n in data["nodes"] if n["type"] == "Contract"}
    assert supersedes[0]["source"] in contracts and supersedes[0]["target"] in contracts
    assert contracts[supersedes[0]["source"]]["properties"]["revision"] == 1
    assert contracts[supersedes[0]["target"]]["properties"]["revision"] == 0


def test_reader_emits_the_organization_node_and_edge(cid):
    _skip()
    pg.resync(cid, "T", {}, org={"id": "pym", "name": "Pym Technologies"})
    data = gr.read_customer_graph(cid)
    node = next(n for n in data["nodes"] if n["type"] == "Organization")
    assert node["id"] == "Organization::pym"
    assert node["label"] == "Pym Technologies"
    assert any(e["type"] == "BELONGS_TO" and e["target"] == "Organization::pym"
               for e in data["edges"])


def test_empty_customer_graph(cid):
    _skip()
    assert gr.read_customer_graph("no-such") == {"nodes": [], "edges": []}
