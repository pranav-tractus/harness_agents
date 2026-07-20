from falkordb import FalkorDB

from apps.api.settings import get_settings

_client: FalkorDB | None = None


def get_client() -> FalkorDB:
    global _client
    if _client is None:
        s = get_settings()
        _client = FalkorDB(host=s.falkordb_host, port=s.falkordb_port)
    return _client


def reset_client() -> None:
    global _client
    _client = None


def customer_graph(customer_id: str):
    return get_client().select_graph(f"customer:{customer_id}")


def catalog_graph():
    return get_client().select_graph("catalog")


def is_available() -> bool:
    try:
        get_client().connection.ping()
        return True
    except Exception:
        return False
