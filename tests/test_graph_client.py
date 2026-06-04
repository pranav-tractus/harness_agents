import pytest
from graph.client import GraphitiMemoryClient


def test_get_memory_block_returns_none_when_no_history(tmp_path, monkeypatch):
    monkeypatch.setenv("KUZU_DB_PATH", str(tmp_path / "client_test.db"))
    client = GraphitiMemoryClient()
    block = client.get_memory_block("unknown_customer")
    assert block is None


def test_get_memory_block_returns_string_after_ingest(tmp_path, monkeypatch):
    monkeypatch.setenv("KUZU_DB_PATH", str(tmp_path / "client_test2.db"))
    client = GraphitiMemoryClient()
    client._backend.write_episode({
        "source_id": "test/ep1",
        "customer_id": "acme_foods",
        "timestamp": 1000,
        "entities": {
            "products": [{"name": "KNM Coffee", "quantity": 5.0, "unit": "MT",
                          "price": 100.0, "price_unit": "USD/MT",
                          "incoterm": "FOB", "port": "Singapore"}],
            "ports": ["Singapore"],
            "payment_terms": "Net 30",
            "packing": "",
            "loading": "",
        },
    })
    block = client.get_memory_block("acme_foods")
    assert block is not None
    assert "KNM Coffee" in block
