from pathlib import Path

import kuzu

from graph.product_extractor import ProductFacts, extract_product_facts

GRAPH_ROOT = Path("graph_dbs")

_DDL = [
    "CREATE NODE TABLE IF NOT EXISTS Product(code STRING, description STRING, spec STRING, PRIMARY KEY(code))",
    "CREATE NODE TABLE IF NOT EXISTS Alias(id STRING, code STRING, name STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS SpecAttr(id STRING, code STRING, key STRING, value STRING, PRIMARY KEY(id))",
    "CREATE REL TABLE IF NOT EXISTS HAS_ALIAS(FROM Product TO Alias)",
    "CREATE REL TABLE IF NOT EXISTS HAS_SPEC(FROM Product TO SpecAttr)",
]


def product_db_path() -> Path:
    return GRAPH_ROOT / "_catalog" / "product.db"


def _connect() -> kuzu.Connection:
    path = product_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = kuzu.Connection(kuzu.Database(str(path)))
    for ddl in _DDL:
        conn.execute(ddl)
    return conn


def _delete_product(conn: kuzu.Connection, code: str) -> None:
    conn.execute("MATCH (p:Product {code: $c})-[r:HAS_ALIAS]->() DELETE r", {"c": code})
    conn.execute("MATCH (p:Product {code: $c})-[r:HAS_SPEC]->() DELETE r", {"c": code})
    conn.execute("MATCH (a:Alias {code: $c}) DELETE a", {"c": code})
    conn.execute("MATCH (s:SpecAttr {code: $c}) DELETE s", {"c": code})
    conn.execute("MATCH (p:Product {code: $c}) DELETE p", {"c": code})


def _spec_pairs(facts: ProductFacts) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, value in (("grade", facts.grade), ("packing_size", facts.packing_size), ("unit", facts.unit)):
        if value:
            pairs.append((key, str(value)))
    for key, value in facts.attributes.items():
        if value:
            pairs.append((key, str(value)))
    return pairs


def resync_product(code, description, spec, model_key="openai:5.5", *, extractor=None) -> None:
    extractor = extractor or extract_product_facts
    facts = extractor(description, spec, model_key)
    conn = _connect()
    _delete_product(conn, code)
    conn.execute(
        "CREATE (:Product {code: $c, description: $d, spec: $s})",
        {"c": code, "d": description or "", "s": spec or ""},
    )
    for name in dict.fromkeys(a for a in facts.aliases if a):  # dedupe, preserve order
        aid = f"{code}::{name}"
        conn.execute("CREATE (:Alias {id: $id, code: $c, name: $n})", {"id": aid, "c": code, "n": name})
        conn.execute(
            "MATCH (p:Product {code: $c}), (a:Alias {id: $id}) CREATE (p)-[:HAS_ALIAS]->(a)",
            {"c": code, "id": aid},
        )
    for key, value in _spec_pairs(facts):
        sid = f"{code}::{key}"
        conn.execute(
            "CREATE (:SpecAttr {id: $id, code: $c, key: $k, value: $v})",
            {"id": sid, "c": code, "k": key, "v": value},
        )
        conn.execute(
            "MATCH (p:Product {code: $c}), (s:SpecAttr {id: $id}) CREATE (p)-[:HAS_SPEC]->(s)",
            {"c": code, "id": sid},
        )


def remove_product(code) -> None:
    if not product_db_path().exists():
        return
    _delete_product(_connect(), code)


def catalog_block() -> str | None:
    if not product_db_path().exists():
        return None
    conn = _connect()
    res = conn.execute("MATCH (p:Product) RETURN p.code, p.description ORDER BY p.code")
    products: list[tuple[str, str]] = []
    while res.has_next():
        row = res.get_next()
        products.append((row[0], row[1]))
    if not products:
        return None

    lines = ["=== Product Catalog ==="]
    for code, description in products:
        specs: list[str] = []
        sres = conn.execute(
            "MATCH (p:Product {code: $c})-[:HAS_SPEC]->(s:SpecAttr) RETURN s.key, s.value ORDER BY s.key",
            {"c": code},
        )
        while sres.has_next():
            k, v = sres.get_next()
            specs.append(f"{k}: {v}")
        aliases: list[str] = []
        ares = conn.execute(
            "MATCH (p:Product {code: $c})-[:HAS_ALIAS]->(a:Alias) RETURN a.name ORDER BY a.name",
            {"c": code},
        )
        while ares.has_next():
            aliases.append(ares.get_next()[0])

        line = f"- {code}: {description}"
        if specs:
            line += " | " + ", ".join(specs)
        lines.append(line)
        if aliases:
            lines.append(f"  aka: {', '.join(aliases)}")
    return "\n".join(lines)
