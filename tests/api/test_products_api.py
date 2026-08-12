import mongomock
import pytest
from bson import ObjectId
from fastapi import HTTPException

from apps.api import seed
from apps.api.db import mongo
from apps.api.routers import products as products_router
from apps.api.services import org_service


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    # No embedded_hash on fresh docs; status_for_doc returns "not built"
    org_service.seed_roster()
    yield
    mongo.reset_client()


def test_create_and_get_roundtrips_new_fields():
    from apps.api.models import ProductCreate
    created = products_router.create_product(ProductCreate(
        code="PX-1", name="Sunflower Lecithin", short_description="De-oiled sunflower lecithin powder",
        long_description="Free-flowing de-oiled powder for emulsification.",
        spec="food grade", metadata={"density": "0.5 g/cm3", "form": "powder"}, org_id="pym"))
    out = products_router.get_product(created.id)
    assert out.name == "Sunflower Lecithin"
    assert out.short_description == "De-oiled sunflower lecithin powder"
    assert out.long_description.startswith("Free-flowing")
    assert out.metadata["density"] == "0.5 g/cm3"
    assert out.id != "PX-1"


def test_update_patches_metadata_and_long_description():
    from apps.api.models import ProductCreate, ProductUpdate
    created = products_router.create_product(ProductCreate(code="PX-2", short_description="d", org_id="pym"))
    products_router.update_product(created.id, ProductUpdate(
        long_description="now with detail", metadata={"moisture": "1%"}))
    out = products_router.get_product(created.id)
    assert out.long_description == "now with detail"
    assert out.metadata == {"moisture": "1%"}


def test_out_falls_back_to_legacy_description_field():
    # Simulate a pre-migration doc that only has `description`
    oid = ObjectId()
    mongo.products().insert_one({"_id": oid, "code": "OLD-1", "description": "legacy text", "spec": None})
    out = products_router.get_product(str(oid))
    assert out.short_description == "legacy text"
    assert out.name is None
    assert out.metadata == {}


def test_migrate_products_renames_description_and_defaults_fields():
    oid = ObjectId()
    mongo.products().insert_one({"_id": oid, "code": "OLD-2", "description": "legacy", "spec": "s"})
    seed.migrate_products()
    doc = mongo.products().find_one({"_id": oid})
    assert doc["short_description"] == "legacy"
    assert "description" not in doc
    assert doc["name"] is None and doc["long_description"] is None and doc["metadata"] == {}
    # idempotent: a second run does not clobber
    seed.migrate_products()
    assert mongo.products().find_one({"_id": oid})["short_description"] == "legacy"


def test_out_exposes_source_label():
    oid = ObjectId()
    mongo.products().insert_one({
        "_id": oid, "code": "SL-1", "short_description": "d", "source_label": "Test Files"})
    out = products_router.get_product(str(oid))
    assert out.source_label == "Test Files"


def test_out_defaults_source_label_to_none_when_absent():
    oid = ObjectId()
    mongo.products().insert_one({"_id": oid, "code": "SL-2", "short_description": "d"})
    out = products_router.get_product(str(oid))
    assert out.source_label is None


def test_create_requires_a_known_org():
    from apps.api.models import ProductCreate
    with pytest.raises(HTTPException) as exc:
        products_router.create_product(ProductCreate(
            code="PX-9", short_description="d", org_id="hydra"))
    assert exc.value.status_code == 422


def test_list_filters_by_org():
    from apps.api.models import ProductCreate
    products_router.create_product(ProductCreate(code="R-1", short_description="d", org_id="roxxon"))
    products_router.create_product(ProductCreate(code="P-1", short_description="d", org_id="pym"))
    assert [p.code for p in products_router.list_products(org_id="roxxon")] == ["R-1"]
    assert len(products_router.list_products()) == 2


def test_update_to_a_new_org_moves_the_vectors(monkeypatch):
    from apps.api.models import ProductCreate, ProductUpdate
    moved = {}
    monkeypatch.setattr(products_router.product_embedding_service, "move_org",
                        lambda doc, new: moved.setdefault("to", new) or
                        mongo.products().find_one({"_id": doc["_id"]}))
    created = products_router.create_product(ProductCreate(
        code="PX-8", short_description="d", org_id="pym"))
    products_router.update_product(created.id, ProductUpdate(org_id="roxxon"))
    assert moved["to"] == "roxxon"


def test_update_to_an_unknown_org_422s():
    from apps.api.models import ProductCreate, ProductUpdate
    created = products_router.create_product(ProductCreate(
        code="PX-7", short_description="d", org_id="pym"))
    with pytest.raises(HTTPException) as exc:
        products_router.update_product(created.id, ProductUpdate(org_id="hydra"))
    assert exc.value.status_code == 422


def test_build_all_skips_products_with_no_org(monkeypatch):
    built = []
    monkeypatch.setattr(products_router.product_embedding_service, "build_from_doc",
                        lambda doc, **k: built.append(doc["code"]))
    mongo.products().insert_many([
        {"code": "HAS", "short_description": "d", "org_id": "pym"},
        {"code": "NONE", "short_description": "d"},
    ])
    products_router.build_all()
    assert built == ["HAS"]
