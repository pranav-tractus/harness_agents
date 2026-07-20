import hashlib

from apps.api.db import falkor
from graph.product_extractor import extract_product_facts


def _hash(description: str, spec: str | None) -> str:
    return hashlib.sha256(f"{description}\x00{spec or ''}".encode()).hexdigest()[:16]


def _delete(g, code: str) -> None:
    # Categories are MERGE-shared across products — detach edges only
    g.query("MATCH (p:Product {code:$c})-[r:IN_CATEGORY]->(:Category) DELETE r", {"c": code})
    g.query("MATCH (p:Product {code:$c})-[r]->(n) WHERE n:Alias OR n:SpecAttr OR n:Application "
            "DELETE r, n", {"c": code})
    g.query("MATCH (p:Product {code:$c}) DELETE p", {"c": code})


def build(code, description, spec, model_key="openai:5.5", *, extractor=None) -> None:
    extractor = extractor or extract_product_facts
    facts = extractor(description, spec, model_key)
    g = falkor.catalog_graph()
    _delete(g, code)
    g.query("CREATE (:Product {code:$c, description:$d, spec:$s, built_hash:$h})",
            {"c": code, "d": description or "", "s": spec or "", "h": _hash(description, spec)})
    for name in dict.fromkeys(a for a in facts.aliases if a):
        g.query("MATCH (p:Product {code:$c}) CREATE (a:Alias {name:$n}) MERGE (p)-[:HAS_ALIAS]->(a)",
                {"c": code, "n": name})
    for key, value in (("grade", facts.grade), ("packing_size", facts.packing_size), ("unit", facts.unit)):
        if value:
            g.query("MATCH (p:Product {code:$c}) CREATE (s:SpecAttr {key:$k, value:$v}) MERGE (p)-[:HAS_SPEC]->(s)",
                    {"c": code, "k": key, "v": str(value)})
    cat = facts.attributes.get("category")
    if cat:
        g.query("MATCH (p:Product {code:$c}) MERGE (cat:Category {name:$n}) MERGE (p)-[:IN_CATEGORY]->(cat)",
                {"c": code, "n": cat})
    app = facts.attributes.get("application")
    if app:
        g.query("MATCH (p:Product {code:$c}) CREATE (a:Application {name:$n}) MERGE (p)-[:USED_FOR]->(a)",
                {"c": code, "n": app})


def status(code, description, spec) -> str:
    if not falkor.is_available():
        return "not built"
    rows = falkor.catalog_graph().query(
        "MATCH (p:Product {code:$c}) RETURN p.built_hash", {"c": code}).result_set
    if not rows:
        return "not built"
    return "built" if rows[0][0] == _hash(description, spec) else "stale"


def remove_product(code) -> None:
    if falkor.is_available():
        _delete(falkor.catalog_graph(), code)


def resolve(name: str) -> list[str]:
    if not falkor.is_available():
        return []
    rows = falkor.catalog_graph().query(
        "MATCH (p:Product)-[:HAS_ALIAS]->(a:Alias) WHERE toLower(a.name) = toLower($n) "
        "RETURN p.code UNION MATCH (p:Product) WHERE toLower(p.code) = toLower($n) RETURN p.code",
        {"n": name}).result_set
    return [r[0] for r in rows]


def catalog_block() -> str | None:
    if not falkor.is_available():
        return None
    g = falkor.catalog_graph()
    prods = g.query("MATCH (p:Product) RETURN p.code, p.description ORDER BY p.code").result_set
    if not prods:
        return None
    lines = ["=== Product Catalog ==="]
    for code, desc in prods:
        aliases = [r[0] for r in g.query(
            "MATCH (p:Product {code:$c})-[:HAS_ALIAS]->(a:Alias) RETURN a.name", {"c": code}).result_set]
        line = f"- {code}: {desc}"
        lines.append(line)
        if aliases:
            lines.append(f"  aka: {', '.join(aliases)}")
    return "\n".join(lines)
