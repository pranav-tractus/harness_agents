from pathlib import Path

import pytest

from apps.api.services import graph_reader_service
from graph.kuzu_backend import KuzuBackend


# ── helpers ──────────────────────────────────────────────────────────────────

def _seed_chat(tmp_path: Path, customer_id: str) -> None:
    db_path = tmp_path / customer_id / "chat.db"
    db_path.parent.mkdir(parents=True)
    backend = KuzuBackend(db_path=db_path)
    backend.write_episode({
        "source_id": f"{customer_id}/order-1",
        "customer_id": customer_id,
        "timestamp": 1000,
        "entities": {
            "products": [
                {
                    "name": "TG-BPPC",
                    "quantity": 100,
                    "unit": "mt",
                    "price": 500.0,
                    "price_unit": "USD/mt",
                    "incoterm": "FOB",
                    "port": "Shanghai",
                }
            ],
            "ports": [],
            "payment_terms": "30 days",
            "packing": "25kg bags",
            "loading": "bulk",
        },
    })
    backend.close()


# ── chat graph ────────────────────────────────────────────────────────────────

def test_chat_graph_empty_when_no_db(tmp_path, monkeypatch):
    monkeypatch.setattr(graph_reader_service, "GRAPH_ROOT", tmp_path)
    result = graph_reader_service.read_chat_graph("cust-1")
    assert result == {"nodes": [], "edges": []}


def test_chat_graph_nodes_and_edges(tmp_path, monkeypatch):
    monkeypatch.setattr(graph_reader_service, "GRAPH_ROOT", tmp_path)
    _seed_chat(tmp_path, "cust-1")

    result = graph_reader_service.read_chat_graph("cust-1")

    node_types = {n["type"] for n in result["nodes"]}
    assert "Customer" in node_types
    assert "Product" in node_types
    assert "Port" in node_types
    assert "Episode" in node_types

    edge_types = {e["type"] for e in result["edges"]}
    assert "BUYS" in edge_types
    assert "SHIPS_TO" in edge_types
    assert "HAS_TERMS" in edge_types

    buys = next(e for e in result["edges"] if e["type"] == "BUYS")
    assert buys["properties"]["quantity"] == 100.0
    assert buys["properties"]["incoterm"] == "FOB"
    assert buys["source"].startswith("Customer::")
    assert buys["target"].startswith("Product::")


# ── profile graph ─────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="Kuzu profile graph retired; profile data now in FalkorDB")
def test_profile_graph_empty_when_no_db():
    pass


@pytest.mark.skip(reason="Kuzu profile graph retired; profile data now in FalkorDB")
def test_profile_graph_nodes_and_edges():
    pass


# ── product catalog graph ─────────────────────────────────────────────────────

@pytest.mark.skip(reason="Kuzu product catalog retired; product graph now in FalkorDB")
def test_product_graph_empty_when_no_db(tmp_path, monkeypatch):
    monkeypatch.setattr(graph_reader_service, "GRAPH_ROOT", tmp_path)
    result = graph_reader_service.read_product_graph()
    assert result == {"nodes": [], "edges": []}


@pytest.mark.skip(reason="Kuzu product catalog retired; product graph now in FalkorDB")
def test_product_graph_nodes_and_edges(tmp_path, monkeypatch):
    from graph.product_extractor import ProductFacts
    from apps.api.services import product_graph_service

    monkeypatch.setattr(graph_reader_service, "GRAPH_ROOT", tmp_path)
    monkeypatch.setattr(product_graph_service, "GRAPH_ROOT", tmp_path)

    def fake_extractor(description, spec, model_key):
        return ProductFacts(
            aliases=["TG-BPPC-alt"],
            grade="food",
            packing_size="25kg",
            unit="bag",
            attributes={"color": "white"},
        )

    product_graph_service.resync_product(
        "TG-BPPC", "Test product", "spec text", extractor=fake_extractor
    )

    result = graph_reader_service.read_product_graph()

    node_types = {n["type"] for n in result["nodes"]}
    assert "Product" in node_types
    assert "Alias" in node_types
    assert "SpecAttr" in node_types

    edge_types = {e["type"] for e in result["edges"]}
    assert "HAS_ALIAS" in edge_types
    assert "HAS_SPEC" in edge_types

    product_node = next(n for n in result["nodes"] if n["type"] == "Product")
    assert product_node["label"] == "TG-BPPC"
    assert product_node["id"] == "Product::TG-BPPC"
