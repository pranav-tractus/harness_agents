import pytest

from apps.api.services import chat_graph_service as cg


@pytest.mark.skip(reason="Kuzu build_and_write retired; see tests/api/test_chat_graph_falkor.py")
def test_build_and_write_retired():
    assert hasattr(cg, "write_contract")


def test_slot_index_and_lookup_scope_by_line():
    idx = cg._slot_index([
        {"slot": "quantity", "line": 1, "source_seqs": [11], "agreed_by": ["seller"]},
        {"slot": "quantity", "line": 2, "source_seqs": [22],
         "agreed_by": ["seller", "customer"]},
        {"slot": "ship_term", "source_seqs": [9]},  # order-level (no line)
    ])
    # each line reads its own entry — no cross-line leakage (the regression)
    assert cg._lookup(idx, "quantity", 1)["source_seqs"] == [11]
    assert cg._lookup(idx, "quantity", 2)["agreed_by"] == ["seller", "customer"]
    # a line-scoped slot has no order-level fallback for an unknown line
    assert cg._lookup(idx, "quantity", 3) is None
    # an order-level slot resolves for any line (and for None)
    assert cg._lookup(idx, "ship_term", 1)["source_seqs"] == [9]
    assert cg._lookup(idx, "ship_term", None)["source_seqs"] == [9]
