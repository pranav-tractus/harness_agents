import pytest

from apps.api.services import profile_graph_service as pg


@pytest.mark.skip(reason="Kuzu profile graph retired; see tests/api/test_profile_graph_falkor.py")
def test_resync_writes_profile_and_leaves_chat_db_untouched():
    pass


@pytest.mark.skip(reason="Kuzu profile graph retired; see tests/api/test_profile_graph_falkor.py")
def test_resync_is_idempotent():
    pass


@pytest.mark.skip(reason="Kuzu profile graph retired; see tests/api/test_profile_graph_falkor.py")
def test_read_block_returns_none_when_missing():
    pass


@pytest.mark.skip(reason="Kuzu profile graph retired; see tests/api/test_profile_graph_falkor.py")
def test_read_block_renders_attributes():
    pass
