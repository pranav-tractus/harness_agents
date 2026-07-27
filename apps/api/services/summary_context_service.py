from apps.api.db import falkor
from apps.api.services import profile_graph_service


def _history_block(customer_id: str) -> str | None:
    if not falkor.is_available():
        return None
    g = falkor.customer_graph(customer_id)
    rows = g.query(
        "MATCH (:Customer {id:$id})-[:PREFERS]->(pr:Preference) "
        "RETURN pr.slot, pr.value, pr.support",
        {"id": customer_id},
    ).result_set
    if not rows:
        return None
    return "Typical terms:\n" + "\n".join(f"- {s}: {v} (seen {n}x)" for s, v, n in rows)


def assemble(
    customer_id, *, profile_reader=None, history_reader=None, product_reader=None
) -> dict:
    profile_reader = profile_reader or profile_graph_service.read_block
    history_reader = history_reader or _history_block
    return {
        "profile_block": profile_reader(customer_id),
        "history_block": history_reader(customer_id),
        "product_block": product_reader() if product_reader else None,
    }
