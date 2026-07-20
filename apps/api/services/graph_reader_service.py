from typing import Any

from apps.api.db import falkor


def _empty():
    return {"nodes": [], "edges": []}


def _node(node_id, label, node_type, props, chat_id=None):
    n = {"id": node_id, "label": label, "type": node_type, "properties": props}
    if chat_id is not None:
        n["chat_id"] = chat_id
    return n


def _edge(edges, source, target, etype):
    edges.append({"id": f"{source}__{etype}__{target}", "source": source,
                  "target": target, "type": etype, "properties": {}})


def read_customer_graph(customer_id: str) -> dict:
    if not falkor.is_available():
        return _empty()
    g = falkor.customer_graph(customer_id)
    nodes, edges = [], []

    cust = g.query("MATCH (c:Customer {id:$id}) RETURN c.id, c.name", {"id": customer_id}).result_set
    if not cust:
        return _empty()
    cid, cname = cust[0]
    nodes.append(_node(f"Customer::{cid}", cname or cid, "Customer", {"id": cid, "name": cname}))

    for key, value in g.query("MATCH (:Customer {id:$id})-[:HAS_ATTRIBUTE]->(a:Attribute) "
                              "RETURN a.key, a.value", {"id": customer_id}).result_set:
        nodes.append(_node(f"Attribute::{key}", key, "Attribute", {"key": key, "value": value}))
        _edge(edges, f"Customer::{cid}", f"Attribute::{key}", "HAS_ATTRIBUTE")

    for slot, val, sup in g.query("MATCH (:Customer {id:$id})-[:PREFERS]->(pr:Preference) "
                                  "RETURN pr.slot, pr.value, pr.support", {"id": customer_id}).result_set:
        nodes.append(_node(f"Preference::{slot}", f"{slot}={val}", "Preference",
                           {"slot": slot, "value": val, "support": sup}))
        _edge(edges, f"Customer::{cid}", f"Preference::{slot}", "PREFERS")

    for chat_id, title, status in g.query(
            "MATCH (:Customer {id:$id})-[:HAS_CHAT]->(ch:Chat) RETURN ch.id, ch.title, ch.status",
            {"id": customer_id}).result_set:
        nodes.append(_node(f"Chat::{chat_id}", title or chat_id, "Chat",
                           {"id": chat_id, "status": status}, chat_id=chat_id))
        _edge(edges, f"Customer::{cid}", f"Chat::{chat_id}", "HAS_CHAT")

        for (con_id, rev, cstatus) in g.query(
                "MATCH (ch:Chat {id:$ch})-[:HAS_CONTRACT]->(ct:Contract) "
                "RETURN ct.id, ct.revision, ct.status", {"ch": chat_id}).result_set:
            nodes.append(_node(f"Contract::{con_id}", f"Contract rev{rev}", "Contract",
                               {"id": con_id, "revision": rev, "status": cstatus}, chat_id=chat_id))
            _edge(edges, f"Chat::{chat_id}", f"Contract::{con_id}", "HAS_CONTRACT")

            for (old_id,) in g.query(
                    "MATCH (ct:Contract {id:$c})-[:SUPERSEDES]->(old:Contract) RETURN old.id",
                    {"c": con_id}).result_set:
                _edge(edges, f"Contract::{con_id}", f"Contract::{old_id}", "SUPERSEDES")

            for (li, code, qty, unit, price, punit, inco, agreed) in g.query(
                    "MATCH (ct:Contract {id:$c})-[:HAS_LINE]->(li:LineItem) "
                    "RETURN li.id, li.product_code, li.quantity, li.unit, li.price, li.price_unit, "
                    "li.incoterm, li.agreed_by", {"c": con_id}).result_set:
                label = f"{code} · {qty or '?'} {unit or ''} · {inco or ''}".strip()
                nodes.append(_node(f"LineItem::{li}", label, "LineItem",
                    {"product_code": code, "quantity": qty, "unit": unit, "price": price,
                     "price_unit": punit, "incoterm": inco, "agreed_by": agreed}, chat_id=chat_id))
                _edge(edges, f"Contract::{con_id}", f"LineItem::{li}", "HAS_LINE")
                if code:
                    nid = f"Product::{code}"
                    if not any(n["id"] == nid for n in nodes):
                        nodes.append(_node(nid, code, "Product", {"code": code}, chat_id=chat_id))
                    _edge(edges, f"LineItem::{li}", nid, "OF_PRODUCT")
                for (pname,) in g.query("MATCH (li:LineItem {id:$li})-[:SHIP_TO]->(po:Port) RETURN po.name",
                                        {"li": li}).result_set:
                    pid = f"Port::{pname}"
                    if not any(n["id"] == pid for n in nodes):
                        nodes.append(_node(pid, pname, "Port", {"name": pname}, chat_id=chat_id))
                    _edge(edges, f"LineItem::{li}", pid, "SHIP_TO")

            for i, (kind, value, agreed) in enumerate(g.query(
                    "MATCH (ct:Contract {id:$c})-[:HAS_TERM]->(t:Term) RETURN t.kind, t.value, t.agreed_by",
                    {"c": con_id}).result_set):
                tid = f"Term::{con_id}::{kind}::{i}"
                nodes.append(_node(tid, f"{kind}: {value}", "Term",
                                   {"kind": kind, "value": value, "agreed_by": agreed}, chat_id=chat_id))
                _edge(edges, f"Contract::{con_id}", tid, "HAS_TERM")

            for i, (seq, role, snip) in enumerate(g.query(
                    "MATCH (ct:Contract {id:$c})-[:DERIVED_FROM]->(m:MessageRef) "
                    "RETURN m.seq, m.role, m.snippet", {"c": con_id}).result_set):
                mid = f"MessageRef::{con_id}::{i}"
                nodes.append(_node(mid, f"#{seq} {role}", "MessageRef",
                                   {"seq": seq, "role": role, "snippet": snip}, chat_id=chat_id))
                _edge(edges, f"Contract::{con_id}", mid, "DERIVED_FROM")

    return {"nodes": nodes, "edges": edges}


def read_product_graph() -> dict:
    if not falkor.is_available():
        return _empty()
    g = falkor.catalog_graph()
    nodes, edges = [], []
    prods = g.query("MATCH (p:Product) RETURN p.code, p.description, p.spec").result_set
    if not prods:
        return _empty()
    for code, desc, spec in prods:
        nodes.append(_node(f"Product::{code}", code, "Product", {"code": code, "description": desc, "spec": spec}))
    for (rel, ntype, label_cypher) in (
        ("HAS_ALIAS", "Alias", "a.name"), ("HAS_SPEC", "SpecAttr", "a.key + ': ' + a.value"),
        ("IN_CATEGORY", "Category", "a.name"), ("USED_FOR", "Application", "a.name")):
        rows = g.query(f"MATCH (p:Product)-[:{rel}]->(a:{ntype}) RETURN p.code, id(a), {label_cypher}").result_set
        for code, aid, label in rows:
            nid = f"{ntype}::{aid}"
            nodes.append(_node(nid, label, ntype, {"label": label}))
            _edge(edges, f"Product::{code}", nid, rel)
    return {"nodes": nodes, "edges": edges}
