import pytest

from apps.api.services import chat_graph_service as cg


@pytest.mark.skip(reason="Kuzu build_and_write retired; see tests/api/test_chat_graph_falkor.py")
def test_build_and_write_retired():
    assert hasattr(cg, "write_contract")
