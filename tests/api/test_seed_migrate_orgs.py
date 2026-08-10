import mongomock
import pytest

from apps.api import seed
from apps.api.db import mongo


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    yield
    mongo.reset_client()


def test_migrate_orgs_seeds_the_roster():
    seed.migrate_orgs()
    assert mongo.organizations().count_documents({}) == 4


def test_migrate_orgs_spreads_the_dummy_customers():
    seed.seed_all()
    seed.migrate_orgs()
    got = {c["_id"]: c["org_id"] for c in mongo.customers().find()}
    assert got == {"dummy-01": "roxxon", "dummy-02": "pym", "dummy-03": "alchemax"}


def test_migrate_orgs_sends_other_orgless_customers_to_the_catchall():
    mongo.customers().insert_one({"_id": "acme", "name": "Acme", "profile": {},
                                  "last_contract_seq": 0})
    seed.migrate_orgs()
    assert mongo.customers().find_one({"_id": "acme"})["org_id"] == "damage-control"


def test_migrate_orgs_never_overwrites_an_existing_assignment():
    mongo.customers().insert_one({"_id": "dummy-01", "name": "Dummy-01", "profile": {},
                                  "last_contract_seq": 0, "org_id": "alchemax"})
    seed.migrate_orgs()
    assert mongo.customers().find_one({"_id": "dummy-01"})["org_id"] == "alchemax"


def test_migrate_orgs_is_idempotent():
    seed.seed_all()
    seed.migrate_orgs()
    seed.migrate_orgs()
    assert mongo.organizations().count_documents({}) == 4
    assert mongo.customers().count_documents({"org_id": {"$exists": False}}) == 0


def test_seed_all_alone_leaves_no_customer_without_an_org():
    """`migrate_orgs` runs last inside `seed_all` for exactly this reason."""
    seed.seed_all()
    assert mongo.customers().count_documents({"org_id": {"$exists": False}}) == 0


def test_seed_all_gives_every_seeded_product_an_org():
    seed.seed_all()
    assert mongo.products().count_documents({"org_id": {"$exists": False}}) == 0
    assert mongo.products().count_documents({"org_id": "damage-control"}) == 0
