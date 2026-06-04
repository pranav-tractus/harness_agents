from __future__ import annotations

import logging

from graph.backend import AbstractGraphBackend

logger = logging.getLogger(__name__)

_MAX_PRODUCTS = 10
_MAX_PORTS = 8
_MAX_SOURCES = 5


def get_memory_block(customer_id: str, backend: AbstractGraphBackend) -> str | None:
    rows = backend.query_customer(customer_id)
    if not rows:
        return None

    products: dict[str, dict] = {}
    ports: dict[str, str] = {}
    terms_list: list[dict] = []
    sources: list[str] = []
    _sources_seen: set[str] = set()

    for row in rows:
        src = row.get("source_id", "")
        if src and src not in _sources_seen:
            sources.append(src)
            _sources_seen.add(src)

        if row["type"] == "product":
            name = row["product_name"]
            if name and name not in products:
                products[name] = row

        elif row["type"] == "port":
            port = row["port"]
            inco = row.get("incoterm", "")
            if port:
                key = f"{inco} {port}".strip() if inco else port
                ports[port] = key

        elif row["type"] == "terms":
            terms_list.append(row)

    lines: list[str] = [f"=== Customer History ({customer_id}) ==="]

    if products:
        product_strs = []
        for name, p in list(products.items())[:_MAX_PRODUCTS]:
            qty = f"{p['quantity']} {p['unit']}" if p.get("quantity") and p.get("unit") else ""
            price = f"@ {p['price_unit']} {p['price']}" if p.get("price") and p.get("price_unit") else ""
            parts = [name, qty, price]
            product_strs.append(" ".join(pt for pt in parts if pt))
        lines.append(f"- Products: {', '.join(product_strs)}")

    if ports:
        lines.append(f"- Ports: {', '.join(list(ports.values())[:_MAX_PORTS])}")

    if terms_list:
        latest = terms_list[0]
        if latest.get("payment_terms"):
            lines.append(f"- Payment terms: {latest['payment_terms']}")
        if latest.get("packing"):
            lines.append(f"- Packing: {latest['packing']}")
        if latest.get("loading"):
            lines.append(f"- Loading: {latest['loading']}")

    if sources:
        lines.append(f"[Sources: {', '.join(sources[:_MAX_SOURCES])}]")

    return "\n".join(lines)
