import mongomock
import pytest
from fastapi.testclient import TestClient

from apps.api.db import mongo
from apps.api.services import command_service
from tests.api._factories import make_extract, make_item


_CUSTOMERS = [("dummy-01", "Dummy-01"), ("dummy-02", "Dummy-02"), ("dummy-03", "Dummy-03")]
_PRODUCTS = [
    ("TG-BPPC", "Rumen bypass Phosphotidyl Choline"),
    ("TG-MGL8", "Lecithin activated Fat Powder"),
    ("GIIOFINE-UP-SF", "De-Oiled Sunflower Lecithin Powder"),
    ("GIIOFINE-L-nGM", "Liquid Soyabean Lecithin"),
]


def _seed_fixture_data() -> None:
    for cid, name in _CUSTOMERS:
        mongo.customers().insert_one(
            {"_id": cid, "name": name, "profile": {}, "last_contract_seq": 0, "updated_at": "now"}
        )
    for code, desc in _PRODUCTS:
        mongo.products().insert_one({"_id": code, "code": code, "description": desc, "spec": None})


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    monkeypatch.setattr("apps.api.routers.customers.profile_graph_service.resync",
                        lambda *a, **k: None)
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.build",
                        lambda *a, **k: None)
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.remove_product",
                        lambda *a, **k: None)
    _seed_fixture_data()
    monkeypatch.setattr("apps.api.services.agent_service.chat_graph_service.write_contract",
                        lambda *a, **k: "contract-id")
    monkeypatch.setattr(command_service.summary_service, "generate",
                        lambda *a, **k: make_extract(items=[make_item(description="TG-BPPC")]))
    monkeypatch.setattr(command_service.summary_context_service, "assemble",
                        lambda *a, **k: {"profile_block": None, "history_block": None,
                                         "product_block": None})
    from apps.api.main import create_app
    with TestClient(create_app()) as c:
        yield c


def test_list_customers(client):
    r = client.get("/api/customers")
    assert r.status_code == 200
    assert {c["id"] for c in r.json()} == {"dummy-01", "dummy-02", "dummy-03"}


def test_products(client):
    r = client.get("/api/products")
    assert len(r.json()) == 4


def test_edit_product(client):
    r = client.put("/api/products/TG-BPPC", json={"description": "Updated choline", "spec": "v2"})
    assert r.status_code == 200
    assert r.json()["description"] == "Updated choline"
    assert r.json()["spec"] == "v2"


def test_delete_product(client):
    r = client.delete("/api/products/TG-MGL8")
    assert r.status_code == 204
    assert client.get("/api/products/TG-MGL8").status_code == 404
    assert len(client.get("/api/products").json()) == 3


def test_models(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    rows = r.json()
    assert all({"key", "display_name", "provider"} <= set(m) for m in rows)
    assert any(m["key"] == "sonnet-4-6" for m in rows)


def test_post_message_then_create_order(client):
    client.post("/api/customers/dummy-01/messages", json={"role": "me", "body": "10MT TG-BPPC"})
    r = client.post("/api/customers/dummy-01/commands",
                    json={"command": "create-sales-order", "model_key": "sonnet-4-6"})
    assert r.status_code == 200
    assert r.json()["summary"]["status"] == "pending"


def test_put_profile_updates_and_returns(client, monkeypatch):
    monkeypatch.setattr("apps.api.routers.customers.profile_graph_service.resync", lambda *a, **k: None)
    r = client.put("/api/customers/dummy-01", json={"profile": {"email": "a@b.com"}})
    assert r.status_code == 200
    assert r.json()["profile"]["email"] == "a@b.com"


def test_create_customer_generates_slug_id(client):
    r = client.post("/api/customers", json={"name": "Acme Corp"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "acme-corp"
    assert body["name"] == "Acme Corp"
    assert body["last_contract_seq"] == 0
    assert client.get("/api/customers/acme-corp").status_code == 200


def test_create_customer_slug_collision(client):
    first = client.post("/api/customers", json={"name": "Dummy 01"}).json()
    assert first["id"] == "dummy-01-2"


def test_delete_customer_cascades(client):
    client.post("/api/customers/dummy-01/messages", json={"role": "me", "body": "hi"})
    assert mongo.messages().count_documents({"customer_id": "dummy-01"}) == 1
    assert mongo.chats().count_documents({"customer_id": "dummy-01"}) >= 1
    r = client.delete("/api/customers/dummy-01")
    assert r.status_code == 204
    assert client.get("/api/customers/dummy-01").status_code == 404
    assert mongo.messages().count_documents({"customer_id": "dummy-01"}) == 0
    assert mongo.summaries().count_documents({"customer_id": "dummy-01"}) == 0
    assert mongo.chats().count_documents({"customer_id": "dummy-01"}) == 0


def test_delete_missing_customer_404(client):
    assert client.delete("/api/customers/nope").status_code == 404


def test_create_product(client):
    r = client.post("/api/products", json={"code": "NEW-1", "description": "New product", "spec": "s1"})
    assert r.status_code == 201
    assert r.json()["id"] == "NEW-1"
    assert len(client.get("/api/products").json()) == 5


def test_create_product_conflict(client):
    r = client.post("/api/products", json={"code": "TG-BPPC", "description": "dup"})
    assert r.status_code == 409


def test_create_product_does_not_sync_graph(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.build",
                        lambda code, description, spec, *a, **k: calls.append((code, description, spec)))
    r = client.post("/api/products", json={"code": "NEW-2", "description": "New", "spec": "s"})
    assert r.status_code == 201
    assert calls == []


def test_build_product_syncs_graph(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.build",
                        lambda code, description, spec, *a, **k: calls.append((code, description, spec)))
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.status",
                        lambda *a, **k: "built")
    r = client.post("/api/products/TG-BPPC/build")
    assert r.status_code == 200
    assert ("TG-BPPC", "Rumen bypass Phosphotidyl Choline", None) in calls


def test_update_product_does_not_sync_graph(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.build",
                        lambda code, description, spec, *a, **k: calls.append((code, description, spec)))
    r = client.put("/api/products/TG-BPPC", json={"description": "Updated", "spec": "v2"})
    assert r.status_code == 200
    assert calls == []


def test_delete_product_removes_from_graph(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_graph_service.remove_product",
                        lambda code, *a, **k: calls.append(code))
    r = client.delete("/api/products/TG-MGL8")
    assert r.status_code == 204
    assert "TG-MGL8" in calls


def test_delete_product_succeeds_when_graph_sync_fails(client, monkeypatch):
    def raise_remove_error(*args, **kwargs):
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr("apps.api.routers.products.product_graph_service.remove_product", raise_remove_error)
    r = client.delete("/api/products/TG-MGL8")
    assert r.status_code == 204
