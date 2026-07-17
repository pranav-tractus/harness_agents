from pathlib import Path
from typing import Any

import kuzu

GRAPH_ROOT = Path("graph_dbs")


def _empty() -> dict[str, list]:
    return {"nodes": [], "edges": []}


def _node(node_id: str, label: str, node_type: str, props: dict[str, Any]) -> dict:
    return {"id": node_id, "label": label, "type": node_type, "properties": props}


def _edge(source: str, target: str, edge_type: str, props: dict[str, Any], seen: set[str]) -> dict:
    base = f"{source}__{edge_type}__{target}"
    eid, n = base, 1
    while eid in seen:
        eid = f"{base}__{n}"
        n += 1
    seen.add(eid)
    return {"id": eid, "source": source, "target": target, "type": edge_type, "properties": props}


def read_chat_graph(customer_id: str) -> dict:
    path = GRAPH_ROOT / customer_id / "chat.db"
    if not path.exists():
        return _empty()

    conn = kuzu.Connection(kuzu.Database(str(path)))
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    res = conn.execute("MATCH (c:Customer) RETURN c.id")
    while res.has_next():
        cid = res.get_next()[0]
        nodes.append(_node(f"Customer::{cid}", cid, "Customer", {"id": cid}))

    res = conn.execute("MATCH (p:Product) RETURN p.name")
    while res.has_next():
        name = res.get_next()[0]
        nodes.append(_node(f"Product::{name}", name, "Product", {"name": name}))

    res = conn.execute("MATCH (po:Port) RETURN po.name")
    while res.has_next():
        name = res.get_next()[0]
        nodes.append(_node(f"Port::{name}", name, "Port", {"name": name}))

    res = conn.execute(
        "MATCH (e:Episode) RETURN e.source_id, e.customer_id, e.timestamp"
    )
    while res.has_next():
        sid, cid, ts = res.get_next()
        nodes.append(_node(
            f"Episode::{sid}", sid, "Episode",
            {"source_id": sid, "customer_id": cid, "timestamp": ts},
        ))

    res = conn.execute(
        "MATCH (c:Customer)-[b:BUYS]->(p:Product) "
        "RETURN c.id, p.name, b.quantity, b.unit, b.price, b.price_unit, "
        "b.incoterm, b.timestamp, b.source_id"
    )
    while res.has_next():
        row = res.get_next()
        edges.append(_edge(
            f"Customer::{row[0]}", f"Product::{row[1]}", "BUYS",
            {"quantity": row[2], "unit": row[3], "price": row[4],
             "price_unit": row[5], "incoterm": row[6],
             "timestamp": row[7], "source_id": row[8]},
            seen,
        ))

    res = conn.execute(
        "MATCH (c:Customer)-[s:SHIPS_TO]->(po:Port) "
        "RETURN c.id, po.name, s.incoterm, s.timestamp, s.source_id"
    )
    while res.has_next():
        row = res.get_next()
        edges.append(_edge(
            f"Customer::{row[0]}", f"Port::{row[1]}", "SHIPS_TO",
            {"incoterm": row[2], "timestamp": row[3], "source_id": row[4]},
            seen,
        ))

    res = conn.execute(
        "MATCH (c:Customer)-[t:HAS_TERMS]->(e:Episode) "
        "RETURN c.id, e.source_id, t.payment_terms, t.packing, t.loading"
    )
    while res.has_next():
        row = res.get_next()
        edges.append(_edge(
            f"Customer::{row[0]}", f"Episode::{row[1]}", "HAS_TERMS",
            {"payment_terms": row[2], "packing": row[3], "loading": row[4]},
            seen,
        ))

    return {"nodes": nodes, "edges": edges}


def read_profile_graph(customer_id: str) -> dict:
    path = GRAPH_ROOT / customer_id / "profile.db"
    if not path.exists():
        return _empty()

    conn = kuzu.Connection(kuzu.Database(str(path)))
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    res = conn.execute("MATCH (c:Customer) RETURN c.id, c.name")
    while res.has_next():
        cid, name = res.get_next()
        nodes.append(_node(f"Customer::{cid}", name, "Customer", {"id": cid, "name": name}))

    res = conn.execute("MATCH (a:Attribute) RETURN a.key, a.value")
    while res.has_next():
        key, value = res.get_next()
        nodes.append(_node(f"Attribute::{key}", key, "Attribute", {"key": key, "value": value}))

    res = conn.execute(
        "MATCH (c:Customer)-[:HAS_ATTRIBUTE]->(a:Attribute) RETURN c.id, a.key"
    )
    while res.has_next():
        cid, key = res.get_next()
        edges.append(_edge(
            f"Customer::{cid}", f"Attribute::{key}", "HAS_ATTRIBUTE", {}, seen,
        ))

    return {"nodes": nodes, "edges": edges}


def read_product_graph() -> dict:
    path = GRAPH_ROOT / "_catalog" / "product.db"
    if not path.exists():
        return _empty()

    conn = kuzu.Connection(kuzu.Database(str(path)))
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    res = conn.execute("MATCH (p:Product) RETURN p.code, p.description, p.spec")
    while res.has_next():
        code, desc, spec = res.get_next()
        nodes.append(_node(
            f"Product::{code}", code, "Product",
            {"code": code, "description": desc, "spec": spec},
        ))

    res = conn.execute("MATCH (a:Alias) RETURN a.id, a.code, a.name")
    while res.has_next():
        aid, code, name = res.get_next()
        nodes.append(_node(
            f"Alias::{aid}", name, "Alias",
            {"id": aid, "code": code, "name": name},
        ))

    res = conn.execute("MATCH (s:SpecAttr) RETURN s.id, s.code, s.key, s.value")
    while res.has_next():
        sid, code, key, value = res.get_next()
        nodes.append(_node(
            f"SpecAttr::{sid}", f"{key}: {value}", "SpecAttr",
            {"id": sid, "code": code, "key": key, "value": value},
        ))

    res = conn.execute(
        "MATCH (p:Product)-[:HAS_ALIAS]->(a:Alias) RETURN p.code, a.id"
    )
    while res.has_next():
        code, aid = res.get_next()
        edges.append(_edge(f"Product::{code}", f"Alias::{aid}", "HAS_ALIAS", {}, seen))

    res = conn.execute(
        "MATCH (p:Product)-[:HAS_SPEC]->(s:SpecAttr) RETURN p.code, s.id"
    )
    while res.has_next():
        code, sid = res.get_next()
        edges.append(_edge(f"Product::{code}", f"SpecAttr::{sid}", "HAS_SPEC", {}, seen))

    return {"nodes": nodes, "edges": edges}
