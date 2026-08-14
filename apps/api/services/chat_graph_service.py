import uuid
from datetime import datetime, timezone

from apps.api.db import falkor

# Term kind "payment" is backed by the ledger slot "payment_date"
_TERM_KIND_TO_SLOT = {
    "payment": "payment_date",
    "packing": "packing",
    "loading": "loading",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_chat(g, customer_id, chat_id, chat_title):
    g.query("MERGE (c:Customer {id: $id})", {"id": customer_id})
    g.query(
        "MATCH (c:Customer {id: $id}) "
        "MERGE (ch:Chat {id: $chat}) "
        "SET ch.title = $title, ch.status = 'active' "
        "MERGE (c)-[:HAS_CHAT]->(ch)",
        {"id": customer_id, "chat": chat_id, "title": chat_title},
    )


def write_contract(
    customer_id, chat_id, chat_title, contract, slots, source_seqs, to_seq
) -> str:
    g = falkor.customer_graph(customer_id)
    _ensure_chat(g, customer_id, chat_id, chat_title)

    contract_id = uuid.uuid4().hex
    # revision = count of all prior contracts in this chat (not LIMIT 1)
    count_rows = g.query(
        "MATCH (ch:Chat {id: $chat})-[:HAS_CONTRACT]->(pc:Contract) RETURN count(pc)",
        {"chat": chat_id},
    ).result_set
    revision = int(count_rows[0][0]) if count_rows else 0
    prev = g.query(
        "MATCH (ch:Chat {id: $chat})-[:HAS_CONTRACT]->(pc:Contract) "
        "RETURN pc.id ORDER BY pc.created_at DESC LIMIT 1",
        {"chat": chat_id},
    ).result_set
    g.query(
        "MATCH (ch:Chat {id: $chat}) "
        "CREATE (ct:Contract {id: $cid, status: 'finalized', revision: $rev, "
        "created_at: $now, finalized_at: $now}) "
        "MERGE (ch)-[:HAS_CONTRACT]->(ct)",
        {"chat": chat_id, "cid": contract_id, "rev": revision, "now": _now()},
    )
    if prev:
        g.query(
            "MATCH (a:Contract {id:$new}),(b:Contract {id:$old}) MERGE (a)-[:SUPERSEDES]->(b)",
            {"new": contract_id, "old": prev[0][0]},
        )

    agreed = {s["slot"]: s.get("agreed_by", []) for s in slots}
    slot_seqs = {s["slot"]: [int(q) for q in (s.get("source_seqs") or [])] for s in slots}
    slot_evidence = {s["slot"]: s.get("evidence") for s in slots}

    def _link(node_var: str, node_id: str, slot_key: str) -> None:
        ev = slot_evidence.get(slot_key)
        for seq in slot_seqs.get(slot_key, []):
            g.query(
                f"MATCH (n:{node_var} {{id:$nid}}) "
                "MERGE (m:MessageRef {contract_id:$cid, seq:$seq}) "
                "SET m.evidence = coalesce($ev, m.evidence) "
                "MERGE (n)-[:DERIVED_FROM]->(m)",
                {"nid": node_id, "cid": contract_id, "seq": seq, "ev": ev},
            )

    for it in contract.get("items", []):
        li = uuid.uuid4().hex
        g.query(
            "MATCH (ct:Contract {id: $cid}) "
            "CREATE (li:LineItem {id: $li, product_code: $code, quantity: $qty, unit: $unit, "
            "price: $price, price_unit: $punit, incoterm: $inco, agreed_by: $agreed}) "
            "MERGE (ct)-[:HAS_LINE]->(li)",
            {
                "cid": contract_id,
                "li": li,
                "code": it.get("description", ""),
                "qty": it.get("quantity"),
                "unit": it.get("quantity_unit", ""),
                "price": it.get("unit_price"),
                "punit": it.get("pricing_unit", ""),
                "inco": it.get("ship_term", ""),
                "agreed": agreed.get("description", []),
            },
        )
        code = it.get("description", "")
        if code:
            g.query(
                "MATCH (li:LineItem {id:$li}) MERGE (p:Product {code:$code}) MERGE (li)-[:OF_PRODUCT]->(p)",
                {"li": li, "code": code},
            )
        port = it.get("shipping_address", "")
        if port:
            g.query(
                "MATCH (li:LineItem {id:$li}) MERGE (po:Port {name:$name}) MERGE (li)-[:SHIP_TO]->(po)",
                {"li": li, "name": port},
            )
        for slot_key in ("description", "quantity", "unit_price", "ship_term"):
            _link("LineItem", li, slot_key)

    for kind, value in (
        ("payment", contract.get("payment_date")),
        ("packing", (contract.get("items") or [{}])[0].get("packing")),
        ("loading", (contract.get("items") or [{}])[0].get("loading")),
    ):
        if value:
            slot_key = _TERM_KIND_TO_SLOT.get(kind, kind)
            tid = uuid.uuid4().hex
            g.query(
                "MATCH (ct:Contract {id:$cid}) "
                "CREATE (t:Term {id:$tid, kind:$kind, value:$value, agreed_by:$agreed}) "
                "MERGE (ct)-[:HAS_TERM]->(t)",
                {
                    "cid": contract_id,
                    "tid": tid,
                    "kind": kind,
                    "value": str(value),
                    "agreed": agreed.get(slot_key, []),
                },
            )
            _link("Term", tid, slot_key)

    for ref in source_seqs:
        g.query(
            "MATCH (ct:Contract {id:$cid}) "
            "MERGE (m:MessageRef {contract_id:$cid, seq:$seq}) "
            "SET m.role=$role, m.snippet=$snip "
            "MERGE (ct)-[:DERIVED_FROM]->(m)",
            {
                "cid": contract_id,
                "seq": ref["seq"],
                "role": ref.get("role", ""),
                "snip": ref.get("snippet", ""),
            },
        )

    # derived preferences: one per slot agreed by both parties
    for s in slots:
        if set(s.get("agreed_by", [])) >= {"seller", "customer"} and s.get("value"):
            g.query(
                "MATCH (c:Customer {id:$id}) "
                "MERGE (pr:Preference {slot:$slot}) "
                "SET pr.value = $value, pr.last_seen = $now, "
                "pr.support = coalesce(pr.support, 0) + 1 "
                "MERGE (c)-[:PREFERS]->(pr)",
                {
                    "id": customer_id,
                    "slot": s["slot"],
                    "value": s["value"],
                    "now": _now(),
                },
            )
    return contract_id


def open_branch(customer_id, new_chat_id, new_chat_title, prev_chat_id) -> None:
    if not falkor.is_available():
        return
    g = falkor.customer_graph(customer_id)
    _ensure_chat(g, customer_id, new_chat_id, new_chat_title)
    g.query(
        "MATCH (a:Chat {id:$new}),(b:Chat {id:$old}) MERGE (a)-[:CONTINUES]->(b)",
        {"new": new_chat_id, "old": prev_chat_id},
    )
