import pytest

from apps.api.db import falkor


@pytest.fixture(autouse=True)
def _reset():
    yield
    falkor.reset_client()


def _skip_if_down():
    if not falkor.is_available():
        pytest.skip("FalkorDB not reachable")


def test_customer_graph_roundtrip():
    _skip_if_down()
    g = falkor.customer_graph("test-roundtrip")
    try:
        g.query("CREATE (:Customer {id: $id, name: $n})", {"id": "test-roundtrip", "n": "T"})
        res = g.query("MATCH (c:Customer) RETURN c.name")
        assert res.result_set[0][0] == "T"
    finally:
        g.delete()
