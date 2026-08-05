import mongomock
import pytest

from apps.api import seed
from apps.api.db import mongo
from apps.api.routers import products as products_router


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    # No embedded_hash on fresh docs; status_for_doc returns "not built"
    yield
    mongo.reset_client()


def test_create_and_get_roundtrips_new_fields():
    from apps.api.models import ProductCreate
    products_router.create_product(ProductCreate(
        code="PX-1", name="Sunflower Lecithin", short_description="De-oiled sunflower lecithin powder",
        long_description="Free-flowing de-oiled powder for emulsification.",
        spec="food grade", metadata={"density": "0.5 g/cm3", "form": "powder"}))
    out = products_router.get_product("PX-1")
    assert out.name == "Sunflower Lecithin"
    assert out.short_description == "De-oiled sunflower lecithin powder"
    assert out.long_description.startswith("Free-flowing")
    assert out.metadata["density"] == "0.5 g/cm3"


def test_update_patches_metadata_and_long_description():
    from apps.api.models import ProductCreate, ProductUpdate
    products_router.create_product(ProductCreate(code="PX-2", short_description="d"))
    products_router.update_product("PX-2", ProductUpdate(
        long_description="now with detail", metadata={"moisture": "1%"}))
    out = products_router.get_product("PX-2")
    assert out.long_description == "now with detail"
    assert out.metadata == {"moisture": "1%"}


def test_out_falls_back_to_legacy_description_field():
    # Simulate a pre-migration doc that only has `description`
    mongo.products().insert_one({"_id": "OLD-1", "code": "OLD-1", "description": "legacy text", "spec": None})
    out = products_router.get_product("OLD-1")
    assert out.short_description == "legacy text"
    assert out.name is None
    assert out.metadata == {}


def test_migrate_products_renames_description_and_defaults_fields():
    mongo.products().insert_one({"_id": "OLD-2", "code": "OLD-2", "description": "legacy", "spec": "s"})
    seed.migrate_products()
    doc = mongo.products().find_one({"_id": "OLD-2"})
    assert doc["short_description"] == "legacy"
    assert "description" not in doc
    assert doc["name"] is None and doc["long_description"] is None and doc["metadata"] == {}
    # idempotent: a second run does not clobber
    seed.migrate_products()
    assert mongo.products().find_one({"_id": "OLD-2"})["short_description"] == "legacy"


def test_out_exposes_source_label():
    mongo.products().insert_one({
        "_id": "SL-1", "code": "SL-1", "short_description": "d", "source_label": "Test Files"})
    out = products_router.get_product("SL-1")
    assert out.source_label == "Test Files"


def test_out_defaults_source_label_to_none_when_absent():
    mongo.products().insert_one({"_id": "SL-2", "code": "SL-2", "short_description": "d"})
    out = products_router.get_product("SL-2")
    assert out.source_label is None
