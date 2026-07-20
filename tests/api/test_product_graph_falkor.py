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


def _fake_extractor(desc, spec, model_key):
    return ProductFacts(aliases=["choline"], grade="feed", packing_size="25kg",
                        unit="MT", attributes={"category": "Dairy nutrition",
                                               "application": "dairy cattle"})


def test_build_creates_enriched_nodes_and_status(_clean=None):
    _skip()
    pg.build("TG-BPPC", "Rumen bypass choline", "grade feed", extractor=_fake_extractor)
    g = falkor.catalog_graph()
    aliases = {r[0] for r in g.query("MATCH (:Product)-[:HAS_ALIAS]->(a:Alias) RETURN a.name").result_set}
    assert "choline" in aliases
    assert pg.status("TG-BPPC", "Rumen bypass choline", "grade feed") == "built"
    assert pg.status("TG-BPPC", "changed desc", "grade feed") == "stale"
    assert pg.resolve("choline") == ["TG-BPPC"]


def test_delete_keeps_shared_category(_clean=None):
    _skip()
    pg.build("P1", "Product one", None, extractor=_fake_extractor)
    pg.build("P2", "Product two", None, extractor=_fake_extractor)
    g = falkor.catalog_graph()
    cats_before = g.query("MATCH (c:Category) RETURN c.name").result_set
    assert any(r[0] == "Dairy nutrition" for r in cats_before)
    pg.remove_product("P1")
    cats_after = g.query("MATCH (c:Category) RETURN c.name").result_set
    assert any(r[0] == "Dairy nutrition" for r in cats_after)
    # P2 still linked
    linked = g.query(
        "MATCH (:Product {code:'P2'})-[:IN_CATEGORY]->(c:Category) RETURN c.name").result_set
    assert linked and linked[0][0] == "Dairy nutrition"
    # P1 gone
    assert not g.query("MATCH (p:Product {code:'P1'}) RETURN p").result_set
