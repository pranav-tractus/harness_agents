import pytest

from apps.api.db import falkor
from apps.api.services import product_graph_service as pg
from graph.product_extractor import ProductFacts


@pytest.fixture(autouse=True)
def _clean():
    yield
    if falkor.is_available():
        falkor.catalog_graph().delete()


def _skip():
    if not falkor.is_available():
        pytest.skip("FalkorDB not reachable")


def _fake_extractor(name, short_description, long_description, spec, metadata, model_key):
    return ProductFacts(aliases=["choline"], grade="feed", packing_size="25kg",
                        unit="MT", attributes={"category": "Dairy nutrition",
                                               "application": "dairy cattle"})


def _kw(**over):
    base = dict(name="Bypass Choline", short_description="Rumen bypass choline",
                long_description=None, spec="grade feed", metadata={"density": "0.5 g/cm3"})
    base.update(over)
    return base


def test_build_creates_enriched_nodes_and_status(_clean=None):
    _skip()
    pg.build("TG-BPPC", extractor=_fake_extractor, **_kw())
    g = falkor.catalog_graph()
    aliases = {r[0] for r in g.query("MATCH (:Product)-[:HAS_ALIAS]->(a:Alias) RETURN a.name").result_set}
    assert "choline" in aliases
    # metadata materialized as a queryable SpecAttr
    spec_keys = {r[0] for r in g.query("MATCH (:Product)-[:HAS_SPEC]->(s:SpecAttr) RETURN s.key").result_set}
    assert "density" in spec_keys
    assert pg.status("TG-BPPC", **_kw()) == "built"
    assert pg.status("TG-BPPC", **_kw(short_description="changed")) == "stale"
    assert pg.resolve("choline") == ["TG-BPPC"]


def test_metadata_change_marks_stale(_clean=None):
    _skip()
    pg.build("TG-BPPC", extractor=_fake_extractor, **_kw())
    assert pg.status("TG-BPPC", **_kw(metadata={"density": "0.9 g/cm3"})) == "stale"


def test_delete_keeps_shared_category(_clean=None):
    _skip()
    pg.build("P1", extractor=_fake_extractor, **_kw())
    pg.build("P2", extractor=_fake_extractor, **_kw())
    g = falkor.catalog_graph()
    cats_before = g.query("MATCH (c:Category) RETURN c.name").result_set
    assert any(r[0] == "Dairy nutrition" for r in cats_before)
    pg.remove_product("P1")
    linked = g.query(
        "MATCH (:Product {code:'P2'})-[:IN_CATEGORY]->(c:Category) RETURN c.name").result_set
    assert linked and linked[0][0] == "Dairy nutrition"
    assert not g.query("MATCH (p:Product {code:'P1'}) RETURN p").result_set
