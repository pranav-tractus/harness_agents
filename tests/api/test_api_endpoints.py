import mongomock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.db import mongo
from apps.api.models import AgentDecision
from apps.api.services import agent_service, org_service
from apps.api.services.product_matcher_service import ProductMatchResult
from tests.api._factories import make_extract, make_item


_CUSTOMERS = [("dummy-01", "Dummy-01"), ("dummy-02", "Dummy-02"), ("dummy-03", "Dummy-03")]
_PRODUCTS = [
    ("TG-BPPC", "Rumen bypass Phosphotidyl Choline"),
    ("TG-MGL8", "Lecithin activated Fat Powder"),
    ("GIIOFINE-UP-SF", "De-Oiled Sunflower Lecithin Powder"),
    ("GIIOFINE-L-nGM", "Liquid Soyabean Lecithin"),
]


def _seed_fixture_data() -> None:
    org_service.seed_roster()
    for cid, name in _CUSTOMERS:
        mongo.customers().insert_one(
            {"_id": cid, "name": name, "profile": {}, "last_contract_seq": 0,
             "updated_at": "now", "org_id": "pym"}
        )
    for code, desc in _PRODUCTS:
        mongo.products().insert_one({"code": code, "description": desc, "spec": None, "org_id": "pym"})


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    monkeypatch.setattr("apps.api.routers.customers.profile_graph_service.resync",
                        lambda *a, **k: None)
    monkeypatch.setattr("apps.api.routers.products.product_embedding_service.build_from_doc",
                        lambda *a, **k: None)
    monkeypatch.setattr("apps.api.routers.products.product_embedding_service.remove_product",
                        lambda *a, **k: None)
    _seed_fixture_data()
    monkeypatch.setattr("apps.api.services.agent_service.chat_graph_service.write_contract",
                        lambda *a, **k: "contract-id")
    monkeypatch.setattr(agent_service, "decide",
                        lambda *a, **k: AgentDecision(
                            mode="draft",
                            message="Draft ready.",
                            contract=make_extract(items=[make_item(description="TG-BPPC")]),
                        ))
    monkeypatch.setattr(agent_service.product_matcher_service, "resolve_products",
                        lambda *a, **k: ProductMatchResult(matches=[]))
    monkeypatch.setattr(agent_service.summary_context_service, "assemble",
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


def _product_id(client, code):
    return next(p["id"] for p in client.get("/api/products").json() if p["code"] == code)


def test_edit_product(client):
    pid = _product_id(client, "TG-BPPC")
    r = client.put(f"/api/products/{pid}", json={"short_description": "Updated choline", "spec": "v2"})
    assert r.status_code == 200
    assert r.json()["short_description"] == "Updated choline"
    assert r.json()["spec"] == "v2"
    assert r.json()["code"] == "TG-BPPC"


def test_delete_product(client):
    pid = _product_id(client, "TG-MGL8")
    r = client.delete(f"/api/products/{pid}")
    assert r.status_code == 204
    assert client.get(f"/api/products/{pid}").status_code == 404
    assert len(client.get("/api/products").json()) == 3


def test_delete_removes_vectors_before_the_document(client, monkeypatch):
    """remove_product reads vector_keys off the document, so it must run first."""
    seen = {}

    def _record(product_id, **kwargs):
        seen["doc_existed"] = mongo.products().find_one({"_id": product_id}) is not None

    monkeypatch.setattr("apps.api.routers.products.product_embedding_service.remove_product", _record)
    pid = _product_id(client, "TG-MGL8")
    assert client.delete(f"/api/products/{pid}").status_code == 204
    assert seen["doc_existed"] is True


def test_get_product_with_a_malformed_id_is_404(client):
    assert client.get("/api/products/not-an-object-id").status_code == 404


def test_models(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    rows = r.json()
    assert all({"key", "display_name", "provider"} <= set(m) for m in rows)
    assert any(m["key"] == "sonnet-4-6" for m in rows)


def test_post_message_then_tag_agent_creates_pending_draft(client):
    client.post("/api/customers/dummy-01/messages", json={"role": "me", "body": "10MT TG-BPPC"})
    r = client.post("/api/customers/dummy-01/messages",
                    json={"role": "me", "body": "@agent create sales order",
                          "model_key": "sonnet-4-6"})
    assert r.status_code == 200
    assert r.json()["summary"]["status"] == "pending"


def test_put_profile_updates_and_returns(client, monkeypatch):
    monkeypatch.setattr("apps.api.routers.customers.profile_graph_service.resync", lambda *a, **k: None)
    r = client.put("/api/customers/dummy-01", json={"profile": {"email": "a@b.com"}})
    assert r.status_code == 200
    assert r.json()["profile"]["email"] == "a@b.com"


def test_create_customer_generates_slug_id(client):
    r = client.post("/api/customers", json={"name": "Acme Corp", "org_id": "pym"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "acme-corp"
    assert body["name"] == "Acme Corp"
    assert body["last_contract_seq"] == 0
    assert client.get("/api/customers/acme-corp").status_code == 200


def test_create_customer_slug_collision(client):
    first = client.post("/api/customers", json={"name": "Dummy 01", "org_id": "pym"}).json()
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
    r = client.post("/api/products", json={"code": "NEW-1", "short_description": "New product", "spec": "s1", "org_id": "pym"})
    assert r.status_code == 201
    assert r.json()["code"] == "NEW-1"
    assert r.json()["id"] != "NEW-1"


def test_create_product_conflict(client):
    r = client.post("/api/products", json={"code": "TG-BPPC", "short_description": "dup", "org_id": "pym"})
    assert r.status_code == 409


def test_create_product_does_not_sync_embeddings(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_embedding_service.build_from_doc",
                        lambda doc, **k: calls.append(doc["code"]))
    r = client.post("/api/products", json={"code": "NEW-2", "short_description": "New", "spec": "s", "org_id": "pym"})
    assert r.status_code == 201
    assert calls == []


def test_build_product_syncs_embeddings(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_embedding_service.build_from_doc",
                        lambda doc, **k: calls.append(doc["code"]))
    monkeypatch.setattr("apps.api.routers.products.product_embedding_service.status_for_doc",
                        lambda doc: "built")
    pid = _product_id(client, "TG-BPPC")
    r = client.post(f"/api/products/{pid}/build")
    assert r.status_code == 200
    assert "TG-BPPC" in calls


def test_update_product_does_not_sync_embeddings(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_embedding_service.build_from_doc",
                        lambda doc, **k: calls.append(doc["code"]))
    pid = _product_id(client, "TG-BPPC")
    r = client.put(f"/api/products/{pid}", json={"short_description": "Updated", "spec": "v2"})
    assert r.status_code == 200
    assert calls == []


def test_delete_product_removes_from_vector_index(client, monkeypatch):
    calls = []
    monkeypatch.setattr("apps.api.routers.products.product_embedding_service.remove_product",
                        lambda product_id, *a, **k: calls.append(product_id))
    pid = _product_id(client, "TG-MGL8")
    r = client.delete(f"/api/products/{pid}")
    assert r.status_code == 204
    assert len(calls) == 1
    assert str(calls[0]) == pid


def test_delete_product_succeeds_when_embedding_sync_fails(client, monkeypatch):
    def raise_remove_error(*args, **kwargs):
        raise RuntimeError("vector index unavailable")

    monkeypatch.setattr("apps.api.routers.products.product_embedding_service.remove_product", raise_remove_error)
    pid = _product_id(client, "TG-MGL8")
    r = client.delete(f"/api/products/{pid}")
    assert r.status_code == 204


def test_messages_include_chat_id_and_status(client):
    client.post("/api/customers/dummy-01/messages", json={"role": "seller", "body": "hello"})
    rows = client.get("/api/customers/dummy-01/messages").json()
    assert rows[-1]["chat_id"]
    assert rows[-1]["chat_status"] == "active"


def test_create_customer_requires_a_known_org(client):
    from apps.api.models import CustomerCreate
    from apps.api.routers import customers as customers_router
    with pytest.raises(HTTPException) as exc:
        customers_router.create_customer(CustomerCreate(name="Acme", org_id="hydra"))
    assert exc.value.status_code == 422


def test_create_customer_stores_and_returns_the_org(client):
    from apps.api.models import CustomerCreate
    from apps.api.routers import customers as customers_router
    out = customers_router.create_customer(CustomerCreate(name="Acme", org_id="pym"))
    assert out.org_id == "pym"
