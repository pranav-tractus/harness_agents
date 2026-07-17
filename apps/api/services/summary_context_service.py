from apps.api.services import chat_graph_service, product_graph_service, profile_graph_service
from graph.kuzu_backend import KuzuBackend
from graph.retrieval import get_memory_block


def _history_block(customer_id: str) -> str | None:
    path = chat_graph_service.chat_db_path(customer_id)
    if not path.exists():
        return None
    backend = KuzuBackend(db_path=path)
    try:
        return get_memory_block(customer_id, backend)
    finally:
        backend.close()


def assemble(customer_id, *, profile_reader=None, history_reader=None, product_reader=None) -> dict:
    profile_reader = profile_reader or profile_graph_service.read_block
    history_reader = history_reader or _history_block
    product_reader = product_reader or product_graph_service.catalog_block
    return {
        "profile_block": profile_reader(customer_id),
        "history_block": history_reader(customer_id),
        "product_block": product_reader(),
    }
