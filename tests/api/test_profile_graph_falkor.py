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
