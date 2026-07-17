import kuzu

from apps.api.services import profile_graph_service as pg
from apps.api.services import chat_graph_service as cg


def test_resync_writes_profile_and_leaves_chat_db_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "GRAPH_ROOT", tmp_path)
    monkeypatch.setattr(cg, "GRAPH_ROOT", tmp_path)

    # a pre-existing chat.db sentinel that must not be modified
    chat_dir = cg.chat_db_path("dummy-01").parent
    chat_dir.mkdir(parents=True, exist_ok=True)
    sentinel = chat_dir / "SENTINEL"
    sentinel.write_text("keep")

    pg.resync("dummy-01", "Dummy-01", {"email": "a@b.com", "phone": "123",
                                       "business_address": "Blr", "delivery_address": None,
                                       "contact_point": "Ravi", "approved_credit_term": "30d",
                                       "approved_white_label": "yes",
                                       "latest_packing_and_loading": "FCL"})

    db = kuzu.Database(str(pg.profile_db_path("dummy-01")))
    conn = kuzu.Connection(db)
    rows = conn.execute("MATCH (a:Attribute) RETURN a.key, a.value").get_as_pl()
    keys = set(rows["a.key"].to_list())
    assert "email" in keys and "approved_credit_term" in keys
    assert sentinel.read_text() == "keep"  # chat side untouched


def test_resync_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "GRAPH_ROOT", tmp_path)
    prof = {"email": "a@b.com"}
    pg.resync("dummy-02", "Dummy-02", prof)
    pg.resync("dummy-02", "Dummy-02", prof)
    db = kuzu.Database(str(pg.profile_db_path("dummy-02")))
    conn = kuzu.Connection(db)
    n = conn.execute("MATCH (a:Attribute) RETURN count(a) AS n").get_as_pl()["n"].to_list()[0]
    assert n == 1  # not duplicated


def test_read_block_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "GRAPH_ROOT", tmp_path)
    assert pg.read_block("no-such-customer") is None


def test_read_block_renders_attributes(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "GRAPH_ROOT", tmp_path)
    pg.resync("dummy-03", "Dummy-03", {"approved_credit_term": "Net 30", "email": "a@b.com"})
    block = pg.read_block("dummy-03")
    assert block is not None
    assert "=== Customer Profile ===" in block
    assert "approved_credit_term: Net 30" in block
    assert "email: a@b.com" in block
