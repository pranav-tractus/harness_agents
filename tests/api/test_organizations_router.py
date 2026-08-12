import mongomock
import pytest
from fastapi import HTTPException

from apps.api.db import mongo
from apps.api.models import OrgCreate, OrgUpdate
from apps.api.routers import organizations as router
from apps.api.services import org_service


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    org_service.seed_roster()
    yield
    mongo.reset_client()


def test_list_returns_the_roster_with_counts():
    mongo.products().insert_many([
        {"code": "A", "org_id": "pym", "short_description": "a"},
        {"code": "B", "org_id": "pym", "short_description": "b", "embedded_hash": "x"},
    ])
    mongo.customers().insert_one({"_id": "c1", "name": "Acme", "org_id": "pym"})
    pym = next(o for o in router.list_organizations() if o.id == "pym")
    assert pym.product_count == 2
    assert pym.customer_count == 1
    assert pym.unbuilt_count == 2  # "B"'s hash does not match its payload


def test_create_derives_a_slug_and_a_vector_index():
    out = router.create_organization(OrgCreate(name="Stark Industries", tagline="Arc tech"))
    assert out.id == "stark-industries"
    assert out.is_catchall is False
    assert org_service.get_org("stark-industries")["vector_index"].endswith("-stark-industries")


def test_update_changes_name_and_tagline_but_not_the_slug():
    out = router.update_organization("pym", OrgUpdate(name="Pym Particles", tagline="Small"))
    assert out.id == "pym"
    assert out.name == "Pym Particles"
    assert out.tagline == "Small"


def test_delete_empty_org_succeeds():
    router.create_organization(OrgCreate(name="Stark Industries"))
    router.delete_organization("stark-industries")
    assert org_service.get_org("stark-industries") is None


def test_delete_is_blocked_while_products_are_attached():
    mongo.products().insert_one({"code": "A", "org_id": "pym", "short_description": "a"})
    with pytest.raises(HTTPException) as exc:
        router.delete_organization("pym")
    assert exc.value.status_code == 409
    assert exc.value.detail["product_count"] == 1
    assert exc.value.detail["customer_count"] == 0


def test_delete_is_blocked_while_customers_are_attached():
    mongo.customers().insert_one({"_id": "c1", "name": "Acme", "org_id": "alchemax"})
    with pytest.raises(HTTPException) as exc:
        router.delete_organization("alchemax")
    assert exc.value.status_code == 409
    assert exc.value.detail["customer_count"] == 1


def test_catchall_cannot_be_deleted_even_when_empty():
    with pytest.raises(HTTPException) as exc:
        router.delete_organization("damage-control")
    assert exc.value.status_code == 409


def test_unknown_org_404s():
    with pytest.raises(HTTPException) as exc:
        router.get_organization("hydra")
    assert exc.value.status_code == 404


def test_create_rejects_a_blank_name():
    with pytest.raises(HTTPException) as exc:
        router.create_organization(OrgCreate(name="   "))
    assert exc.value.status_code == 422


def test_build_embeds_every_product_in_the_org(monkeypatch):
    built = []
    monkeypatch.setattr(router.product_embedding_service, "build_from_doc",
                        lambda doc, **k: built.append(doc["code"]))
    mongo.products().insert_many([
        {"code": "A", "org_id": "pym", "short_description": "a"},
        {"code": "B", "org_id": "roxxon", "short_description": "b"},
    ])
    router.build_organization("pym")
    assert built == ["A"]
