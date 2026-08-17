import pytest
from graph.kuzu_backend import KuzuBackend


@pytest.fixture
def tmp_backend(tmp_path):
    b = KuzuBackend(db_path=tmp_path / "test.db")
    yield b
    b.close()


def test_write_episode_creates_customer_and_product(tmp_backend):
    episode = {
        "source_id": "customers/acme_foods/chats/test_001",
        "customer_id": "acme_foods",
        "timestamp": 1760200000,
        "entities": {
            "products": [
                {
                    "name": "KNM Coffee",
                    "quantity": 10.0,
                    "unit": "bags",
                    "price": 25.0,
                    "price_unit": "USD/bag",
                    "incoterm": "FOB",
                    "port": "Singapore",
                }
            ],
            "ports": ["Singapore"],
            "payment_terms": "Net 30",
            "packing": "25kg PP bags",
            "loading": "1x20 FCL",
        },
    }
    tmp_backend.write_episode(episode)
    results = tmp_backend.query_customer("acme_foods")
    assert len(results) > 0
    product_names = [r["product_name"] for r in results if r.get("product_name")]
    assert "KNM Coffee" in product_names


def test_write_episode_idempotent(tmp_backend):
    episode = {
        "source_id": "customers/acme_foods/chats/test_001",
        "customer_id": "acme_foods",
        "timestamp": 1760200000,
        "entities": {
            "products": [{"name": "Rice", "quantity": 5.0, "unit": "MT",
                          "price": 300.0, "price_unit": "USD/MT",
                          "incoterm": "CIF", "port": "Busan"}],
            "ports": ["Busan"],
            "payment_terms": "",
            "packing": "",
            "loading": "",
        },
    }
    tmp_backend.write_episode(episode)
    tmp_backend.write_episode(episode)  # second write must not duplicate
    results = tmp_backend.query_customer("acme_foods")
    product_rows = [r for r in results if r.get("product_name") == "Rice"]
    assert len(product_rows) == 1


def test_query_customer_isolation(tmp_backend):
    for cid, product in [("acme_foods", "KNM Coffee"), ("nova_exports", "Palm Oil")]:
        ep = {
            "source_id": f"customers/{cid}/chats/ep1",
            "customer_id": cid,
            "timestamp": 1000,
            "entities": {
                "products": [{"name": product, "quantity": 1.0, "unit": "MT",
                              "price": 100.0, "price_unit": "USD/MT",
                              "incoterm": "FOB", "port": "Singapore"}],
                "ports": ["Singapore"],
                "payment_terms": "",
                "packing": "",
                "loading": "",
            },
        }
        tmp_backend.write_episode(ep)
    acme_results = tmp_backend.query_customer("acme_foods")
    acme_products = {r["product_name"] for r in acme_results if r.get("product_name")}
    assert "KNM Coffee" in acme_products
    assert "Palm Oil" not in acme_products


def test_query_unknown_customer_returns_empty(tmp_backend):
    results = tmp_backend.query_customer("no_such_customer")
    assert results == []
