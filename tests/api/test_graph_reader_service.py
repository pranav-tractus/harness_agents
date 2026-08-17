from pathlib import Path

import pytest

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

@pytest.mark.skip(reason="Kuzu chat graph retired; customer graph now in FalkorDB")
def test_chat_graph_empty_when_no_db():
    pass


@pytest.mark.skip(reason="Kuzu chat graph retired; customer graph now in FalkorDB")
def test_chat_graph_nodes_and_edges():
    pass


# ── profile graph ─────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="Kuzu profile graph retired; profile data now in FalkorDB")
def test_profile_graph_empty_when_no_db():
    pass


@pytest.mark.skip(reason="Kuzu profile graph retired; profile data now in FalkorDB")
def test_profile_graph_nodes_and_edges():
    pass


