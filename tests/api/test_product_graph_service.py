import kuzu

from apps.api.services import product_graph_service as pgs
from graph.product_extractor import ProductFacts


def _fake_extractor(facts_by_code):
    def _fn(description, spec, model_key):
        return facts_by_code[description]
    return _fn


def test_resync_writes_product_alias_and_spec_nodes(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    facts = ProductFacts(aliases=["atta", "maida"], grade="A", packing_size="25kg",
                         unit="MT", attributes={"origin": "India"})
    pgs.resync_product("WHF25", "Wheat Flour", "grade A", extractor=lambda d, s, m: facts)

    db = kuzu.Database(str(pgs.product_db_path()))
    conn = kuzu.Connection(db)
    aliases = conn.execute("MATCH (a:Alias) RETURN a.name").get_as_pl()["a.name"].to_list()
    spec_keys = conn.execute("MATCH (s:SpecAttr) RETURN s.key").get_as_pl()["s.key"].to_list()
    assert set(aliases) == {"atta", "maida"}
    assert "grade" in spec_keys and "unit" in spec_keys and "origin" in spec_keys


def test_resync_is_idempotent_and_scoped_per_product(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    f1 = ProductFacts(aliases=["atta"], grade="A")
    f2 = ProductFacts(aliases=["lecithin"], grade="B")
    pgs.resync_product("WHF25", "Wheat Flour", None, extractor=lambda d, s, m: f1)
    pgs.resync_product("LEC10", "Lecithin", None, extractor=lambda d, s, m: f2)
    pgs.resync_product("WHF25", "Wheat Flour", None, extractor=lambda d, s, m: f1)  # again

    db = kuzu.Database(str(pgs.product_db_path()))
    conn = kuzu.Connection(db)
    n_products = conn.execute("MATCH (p:Product) RETURN count(p) AS n").get_as_pl()["n"].to_list()[0]
    n_aliases = conn.execute("MATCH (a:Alias) RETURN count(a) AS n").get_as_pl()["n"].to_list()[0]
    assert n_products == 2       # WHF25 not duplicated
    assert n_aliases == 2        # one per product, not duplicated


def test_remove_product_deletes_only_that_product(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    pgs.resync_product("WHF25", "Wheat Flour", None,
                       extractor=lambda d, s, m: ProductFacts(aliases=["atta"]))
    pgs.resync_product("LEC10", "Lecithin", None,
                       extractor=lambda d, s, m: ProductFacts(aliases=["lecithin"]))
    pgs.remove_product("WHF25")

    db = kuzu.Database(str(pgs.product_db_path()))
    conn = kuzu.Connection(db)
    codes = conn.execute("MATCH (p:Product) RETURN p.code").get_as_pl()["p.code"].to_list()
    assert codes == ["LEC10"]


def test_catalog_block_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    assert pgs.catalog_block() is None


def test_catalog_block_renders_products(tmp_path, monkeypatch):
    monkeypatch.setattr(pgs, "GRAPH_ROOT", tmp_path)
    pgs.resync_product("WHF25", "Wheat Flour", None,
                       extractor=lambda d, s, m: ProductFacts(aliases=["atta"], grade="A", unit="MT"))
    block = pgs.catalog_block()
    assert block is not None
    assert "=== Product Catalog ===" in block
    assert "WHF25: Wheat Flour" in block
    assert "grade: A" in block and "unit: MT" in block
    assert "aka: atta" in block
