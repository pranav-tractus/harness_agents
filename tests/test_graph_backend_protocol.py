import pytest
from graph.backend import AbstractGraphBackend


def test_kuzu_backend_satisfies_protocol():
    """KuzuBackend must satisfy AbstractGraphBackend at runtime."""
    from graph.kuzu_backend import KuzuBackend
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp:
        backend = KuzuBackend(db_path=pathlib.Path(tmp) / "test.db")
        assert isinstance(backend, AbstractGraphBackend)
        backend.close()
