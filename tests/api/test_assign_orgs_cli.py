import mongomock
import pytest

from apps.api.db import mongo
from apps.api.services import org_service
from scripts import assign_orgs


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    org_service.seed_roster()
    yield
    mongo.reset_client()


def _boom_llm(*a, **k):
    raise AssertionError("no LLM call expected")


def test_assign_places_products_by_rule():
    mongo.products().insert_many([
        {"code": "L-1", "name": "Soy Lecithin Powder", "short_description": "lecithin"},
        {"code": "A-1", "name": "L-Threonine", "short_description": "amino acid",
         "metadata": {"category": "Amino acids"}},
    ])
    rows = assign_orgs.assign(llm=_boom_llm)
    assert sorted(rows) == [("A-1", "pym", "rule"), ("L-1", "roxxon", "rule")]
    assert mongo.products().find_one({"code": "L-1"})["org_id"] == "roxxon"


def test_dry_run_writes_nothing():
    mongo.products().insert_one({"code": "L-1", "name": "Soy Lecithin", "short_description": "x"})
    assign_orgs.assign(dry_run=True, llm=_boom_llm)
    assert mongo.products().find_one({"code": "L-1"}).get("org_id") is None


def test_only_unassigned_skips_products_that_already_have_an_org():
    mongo.products().insert_one({"code": "L-1", "name": "Soy Lecithin",
                                 "short_description": "x", "org_id": "alchemax"})
    assert assign_orgs.assign(llm=_boom_llm) == []
    assert mongo.products().find_one({"code": "L-1"})["org_id"] == "alchemax"


def test_all_reclassifies_products_that_already_have_an_org():
    mongo.products().insert_one({"code": "L-1", "name": "Soy Lecithin",
                                 "short_description": "x", "org_id": "alchemax"})
    assign_orgs.assign(only_unassigned=False, llm=_boom_llm)
    assert mongo.products().find_one({"code": "L-1"})["org_id"] == "roxxon"


def test_rebuild_embeds_each_assigned_product():
    built = []
    mongo.products().insert_one({"code": "L-1", "name": "Soy Lecithin", "short_description": "x"})
    assign_orgs.assign(rebuild=True, llm=_boom_llm, build_fn=lambda d: built.append(d["code"]))
    assert built == ["L-1"]


def test_main_returns_zero(capsys):
    mongo.products().insert_one({"code": "L-1", "name": "Soy Lecithin", "short_description": "x"})
    assert assign_orgs.main(["--dry-run"]) == 0
    assert "L-1" in capsys.readouterr().out
