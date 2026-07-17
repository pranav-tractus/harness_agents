import pytest
from graph.kuzu_backend import KuzuBackend
from graph.retrieval import get_memory_block

_BASE_EPISODE = {
    "source_id": "customers/acme_foods/chats/ep1",
    "customer_id": "acme_foods",
    "timestamp": 1760200000,
    "entities": {
        "products": [
            {"name": "KNM Coffee", "quantity": 10.0, "unit": "bags",
             "price": 25.0, "price_unit": "USD/bag", "incoterm": "FOB", "port": "Singapore"},
        ],
        "ports": ["Singapore"],
        "payment_terms": "Net 30",
        "packing": "25kg PP bags",
        "loading": "1x20 FCL",
    },
}


@pytest.fixture
def populated_backend(tmp_path):
    b = KuzuBackend(db_path=tmp_path / "ret.db")
    b.write_episode(_BASE_EPISODE)
    yield b
    b.close()


def test_memory_block_contains_product(populated_backend):
    block = get_memory_block("acme_foods", populated_backend)
    assert block is not None
    assert "KNM Coffee" in block


def test_memory_block_contains_port(populated_backend):
    block = get_memory_block("acme_foods", populated_backend)
    assert "Singapore" in block


def test_memory_block_contains_terms(populated_backend):
    block = get_memory_block("acme_foods", populated_backend)
    assert "Net 30" in block
    assert "25kg PP bags" in block


def test_memory_block_none_for_unknown_customer(populated_backend):
    block = get_memory_block("no_such_customer", populated_backend)
    assert block is None


def test_memory_block_customer_isolation(tmp_path):
    b = KuzuBackend(db_path=tmp_path / "iso.db")
    ep_nova = {
        "source_id": "customers/nova_exports/chats/ep1",
        "customer_id": "nova_exports",
        "timestamp": 1000,
        "entities": {
            "products": [{"name": "Palm Oil", "quantity": 20.0, "unit": "MT",
                          "price": 800.0, "price_unit": "USD/MT",
                          "incoterm": "CIF", "port": "Busan"}],
            "ports": ["Busan"],
            "payment_terms": "100% Advance",
            "packing": "",
            "loading": "",
        },
    }
    b.write_episode(_BASE_EPISODE)
    b.write_episode(ep_nova)
    acme_block = get_memory_block("acme_foods", b)
    assert "Palm Oil" not in (acme_block or "")
    assert "KNM Coffee" in (acme_block or "")
    b.close()
