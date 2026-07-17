from pathlib import Path

import kuzu

GRAPH_ROOT = Path("graph_dbs")

_DDL = [
    "CREATE NODE TABLE IF NOT EXISTS Customer(id STRING, name STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Attribute(key STRING, value STRING, PRIMARY KEY(key))",
    "CREATE REL TABLE IF NOT EXISTS HAS_ATTRIBUTE(FROM Customer TO Attribute)",
]

# profile fields persisted as Attribute nodes
_FIELDS = [
    "email", "phone", "business_address", "delivery_address", "contact_point",
    "approved_credit_term", "approved_white_label", "latest_packing_and_loading",
]


def profile_db_path(customer_id: str) -> Path:
    return GRAPH_ROOT / customer_id / "profile.db"


def resync(customer_id: str, name: str, profile: dict) -> None:
    path = profile_db_path(customer_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(path))
    conn = kuzu.Connection(db)
    for ddl in _DDL:
        conn.execute(ddl)
    # full wipe of this customer's profile graph, then rebuild
    conn.execute("MATCH (c:Customer)-[r:HAS_ATTRIBUTE]->(a:Attribute) DELETE r")
    conn.execute("MATCH (a:Attribute) DELETE a")
    conn.execute("MATCH (c:Customer) DELETE c")
    conn.execute("CREATE (c:Customer {id: $id, name: $name})", {"id": customer_id, "name": name})
    for key in _FIELDS:
        value = profile.get(key)
        if value is None:
            continue
        conn.execute("CREATE (a:Attribute {key: $k, value: $v})", {"k": key, "v": str(value)})
        conn.execute(
            "MATCH (c:Customer {id: $id}), (a:Attribute {key: $k}) CREATE (c)-[:HAS_ATTRIBUTE]->(a)",
            {"id": customer_id, "k": key},
        )


def read_block(customer_id: str) -> str | None:
    path = profile_db_path(customer_id)
    if not path.exists():
        return None
    conn = kuzu.Connection(kuzu.Database(str(path)))
    for ddl in _DDL:
        conn.execute(ddl)
    res = conn.execute("MATCH (a:Attribute) RETURN a.key, a.value")
    rows: list[tuple[str, str]] = []
    while res.has_next():
        row = res.get_next()
        rows.append((row[0], row[1]))
    if not rows:
        return None
    lines = ["=== Customer Profile ==="]
    for key, value in rows:
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)
