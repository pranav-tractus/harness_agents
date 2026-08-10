import pytest

from apps.api.db import falkor
from apps.api.services import chat_graph_service as cg
from apps.api.services import profile_graph_service as pg


@pytest.fixture()
def cid():
    c = "test-profile"
    yield c
    if falkor.is_available():
        falkor.customer_graph(c).delete()


def _skip():
    if not falkor.is_available():
        pytest.skip("FalkorDB not reachable")


def test_resync_writes_the_organization_node(cid):
    _skip()
    pg.resync(cid, "T", {}, org={"id": "pym", "name": "Pym Technologies"})
    g = falkor.customer_graph(cid)
    rows = g.query(
        "MATCH (:Customer)-[:BELONGS_TO]->(o:Organization) RETURN o.id, o.name"
    ).result_set
    assert rows == [["pym", "Pym Technologies"]]


def test_resync_replaces_a_previous_organization(cid):
    _skip()
    pg.resync(cid, "T", {}, org={"id": "pym", "name": "Pym Technologies"})
    pg.resync(cid, "T", {}, org={"id": "roxxon", "name": "Roxxon Energy Corporation"})
    g = falkor.customer_graph(cid)
    rows = g.query(
        "MATCH (:Customer)-[:BELONGS_TO]->(o:Organization) RETURN o.id"
    ).result_set
    assert rows == [["roxxon"]]


def test_resync_without_an_org_leaves_no_organization_node(cid):
    _skip()
    pg.resync(cid, "T", {"email": "a@b.com"})
    g = falkor.customer_graph(cid)
    assert g.query("MATCH (o:Organization) RETURN o.id").result_set == []


def test_resync_preserves_attributes_alongside_the_org(cid):
    _skip()
    pg.resync(cid, "T", {"email": "a@b.com"}, org={"id": "pym", "name": "Pym"})
    g = falkor.customer_graph(cid)
    keys = {r[0] for r in g.query(
        "MATCH (:Customer)-[:HAS_ATTRIBUTE]->(a:Attribute) RETURN a.key").result_set}
    assert "email" in keys


def test_resync_writes_attrs_and_preserves_branches(cid):
    _skip()
    cg.write_contract(cid, "chat-1", "A", {"items": []}, [], [], to_seq=1)  # a branch exists
    pg.resync(cid, "T", {"email": "a@b.com", "approved_credit_term": "Net 30"})
    g = falkor.customer_graph(cid)
    keys = {r[0] for r in g.query("MATCH (:Customer)-[:HAS_ATTRIBUTE]->(a:Attribute) RETURN a.key").result_set}
    assert {"email", "approved_credit_term"} <= keys
    # the chat branch survived the profile resync
    chats = g.query("MATCH (:Customer)-[:HAS_CHAT]->(ch:Chat) RETURN ch.id").result_set
    assert chats and chats[0][0] == "chat-1"
