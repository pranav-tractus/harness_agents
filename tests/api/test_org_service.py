import mongomock
import pytest

from apps.api import orgs
from apps.api.db import mongo
from apps.api.services import org_service


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    yield
    mongo.reset_client()


def test_seed_roster_inserts_every_org():
    org_service.seed_roster()
    ids = {o["_id"] for o in org_service.list_orgs()}
    assert ids == {"roxxon", "pym", "alchemax", "damage-control"}


def test_seed_roster_is_idempotent_and_preserves_renames():
    org_service.seed_roster()
    mongo.organizations().update_one({"_id": "pym"}, {"$set": {"name": "Pym Particles Ltd"}})
    org_service.seed_roster()
    assert org_service.get_org("pym")["name"] == "Pym Particles Ltd"
    assert mongo.organizations().count_documents({}) == 4


def test_exactly_one_catchall_and_it_is_damage_control():
    org_service.seed_roster()
    catchalls = [o["_id"] for o in org_service.list_orgs() if o["is_catchall"]]
    assert catchalls == [orgs.CATCHALL_ID] == ["damage-control"]


def test_seeded_orgs_get_a_per_org_vector_index_name():
    org_service.seed_roster()
    assert org_service.get_org("roxxon")["vector_index"].endswith("-roxxon")
    assert org_service.vector_index_name("roxxon") == org_service.index_name_for("roxxon")


def test_vector_index_name_falls_back_to_derived_when_org_doc_missing():
    assert org_service.vector_index_name("ghost") == org_service.index_name_for("ghost")


def test_slugify_lowercases_and_hyphenates():
    assert org_service.slugify("Stark Industries!") == "stark-industries"


def test_slugify_disambiguates_against_existing_orgs():
    mongo.organizations().insert_one({"_id": "stark-industries", "name": "Stark"})
    assert org_service.slugify("Stark Industries") == "stark-industries-2"


def test_org_id_for_customer_reads_the_customer_doc():
    mongo.customers().insert_one({"_id": "c1", "name": "Acme", "org_id": "pym"})
    assert org_service.org_id_for_customer("c1") == "pym"


def test_org_id_for_customer_raises_when_unset():
    mongo.customers().insert_one({"_id": "c2", "name": "Beta"})
    with pytest.raises(org_service.MissingOrg):
        org_service.org_id_for_customer("c2")


def test_org_id_for_customer_raises_for_unknown_customer():
    with pytest.raises(org_service.MissingOrg):
        org_service.org_id_for_customer("nobody")
