from apps.api.db import falkor

_FIELDS = [
    "email",
    "phone",
    "business_address",
    "delivery_address",
    "contact_point",
    "approved_credit_term",
    "approved_white_label",
    "latest_packing_and_loading",
]


def resync(customer_id: str, name: str, profile: dict, org: dict | None = None) -> None:
    g = falkor.customer_graph(customer_id)
    g.query(
        "MERGE (c:Customer {id:$id}) SET c.name = $name",
        {"id": customer_id, "name": name},
    )
    g.query(
        "MATCH (c:Customer {id:$id})-[r:BELONGS_TO]->(o:Organization) DELETE r, o",
        {"id": customer_id},
    )
    if org:
        g.query(
            "MATCH (c:Customer {id:$id}) "
            "MERGE (o:Organization {id:$oid}) SET o.name = $oname "
            "MERGE (c)-[:BELONGS_TO]->(o)",
            {"id": customer_id, "oid": org["id"], "oname": org["name"]},
        )
    g.query(
        "MATCH (c:Customer {id:$id})-[r:HAS_ATTRIBUTE]->(a:Attribute) DELETE r, a",
        {"id": customer_id},
    )
    for key in _FIELDS:
        value = profile.get(key)
        if value in (None, ""):
            continue
        g.query(
            "MATCH (c:Customer {id:$id}) CREATE (a:Attribute {key:$k, value:$v}) "
            "MERGE (c)-[:HAS_ATTRIBUTE]->(a)",
            {"id": customer_id, "k": key, "v": str(value)},
        )


def read_block(customer_id: str) -> str | None:
    if not falkor.is_available():
        return None
    g = falkor.customer_graph(customer_id)
    rows = g.query(
        "MATCH (:Customer {id:$id})-[:HAS_ATTRIBUTE]->(a:Attribute) "
        "RETURN a.key, a.value",
        {"id": customer_id},
    ).result_set
    if not rows:
        return None
    return "\n".join(f"{k}: {v}" for k, v in rows)
