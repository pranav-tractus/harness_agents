#!/usr/bin/env python3
"""Generate synthetic test chats for memory-assisted extraction evaluation.

Writes 60 JSON files to tests/synthetic_chats/:
  - 30 memory_required (MR): extraction only possible with memory block
  - 30 memory_boost (MB): extraction possible without memory, measures if memory helps

Run: python scripts/generate_test_chats.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "tests" / "synthetic_chats"


# ── Customer fixtures ────────────────────────────────────────────────────────
# Encodes what each customer's graph memory block would contain.
# Used to: (a) build mock_memory_block strings, (b) fill expected_facts
# in memory_required chats where chat text is intentionally vague.

CUSTOMER_FIXTURES: dict[str, dict] = {
    "18965853-110b-40a3-9a9c-f6c29582e7b6": {
        "label": "C-18965853",
        "products": {
            "GIIOFEED PL-5": {
                "quantity": 2.0, "unit": "MT",
                "price": 1420.0, "price_unit": "USD/MT",
                "incoterm": "CIF", "port": "Busan",
            }
        },
        "ports": ["Busan"],
        "payment_terms": "",
        "packing": "25kg PP bags",
        "loading": "1x20 FCL",
    },
    "f081da35-3b14-4328-86f6-0f569bc63b43": {
        "label": "C-f081da35",
        "products": {
            "GIIOFEED PL-5": {
                "quantity": 2.0, "unit": "MT",
                "price": 1420.0, "price_unit": "USD/MT",
                "incoterm": "CIF", "port": "Busan",
            },
            "GIIOFINE - L - SF": {
                "quantity": 1.1, "unit": "MT",
                "price": 2980.0, "price_unit": "USD/MT",
                "incoterm": "CIF", "port": "Busan",
            },
        },
        "ports": ["Busan"],
        "payment_terms": "COD",
        "packing": "IBC",
        "loading": "1x20 FCL",
    },
    "12a4f3a7-d506-4d32-ae06-3f76508c6abd": {
        "label": "C-12a4f3a7",
        "products": {
            "GIIOFINE-P-S": {
                "quantity": 13.0, "unit": "MT",
                "price": 2850.0, "price_unit": "USD/MT",
                "incoterm": "CIF", "port": "Busan",
            }
        },
        "ports": ["Busan"],
        "payment_terms": "",
        "packing": "25kg PP bags",
        "loading": "2x20 FCL",
    },
    "d586d853-694c-42f9-93be-bc7ba5b2110c": {
        "label": "C-d586d853",
        "products": {
            "BP102": {
                "quantity": 23.0, "unit": "MT",
                "price": 1425.0, "price_unit": "USD/MT",
                "incoterm": "CIF", "port": "Busan",
            }
        },
        "ports": ["Busan"],
        "payment_terms": "",
        "packing": "25kg printed paper bag",
        "loading": "23MT / 40' FCL",
    },
    "8f477a8f-2a60-4e0a-bf0e-8cc3cdf1dc9f": {
        "label": "C-8f477a8f",
        "products": {
            "Bergapur": {
                "quantity": 10.5, "unit": "MT",
                "price": 3100.0, "price_unit": "USD/MT",
                "incoterm": "EXW", "port": "",
            }
        },
        "ports": [],
        "payment_terms": "",
        "packing": "25kg bags",
        "loading": "40' FCL",
    },
    "acme_foods": {
        "label": "Acme Foods",
        "products": {
            "KISAN Coffee": {
                "quantity": 10.0, "unit": "bags",
                "price": 25.0, "price_unit": "USD/bag",
                "incoterm": "FOB", "port": "Singapore",
            }
        },
        "ports": ["Singapore"],
        "payment_terms": "Net 15",
        "packing": "standard bags",
        "loading": "",
    },
}


def _memory_block(cid: str) -> str:
    """Build mock_memory_block string matching graph/retrieval.py format."""
    fx = CUSTOMER_FIXTURES[cid]
    lines = [f"=== Customer History ({cid}) ==="]
    product_strs = []
    for name, p in fx["products"].items():
        qty = f"{p['quantity']} {p['unit']}"
        price = f"@ {p['price_unit']} {p['price']}"
        product_strs.append(f"{name} {qty} {price}")
    lines.append(f"- Products: {', '.join(product_strs)}")
    if fx["ports"]:
        port_entries = []
        for name, p in fx["products"].items():
            inco = p.get("incoterm", "")
            port = p.get("port", "")
            if port:
                port_entries.append(f"{inco} {port}".strip() if inco else port)
        all_ports = list(dict.fromkeys(port_entries + fx["ports"]))
        lines.append(f"- Ports: {', '.join(all_ports)}")
    if fx["payment_terms"]:
        lines.append(f"- Payment terms: {fx['payment_terms']}")
    if fx["packing"]:
        lines.append(f"- Packing: {fx['packing']}")
    if fx["loading"]:
        lines.append(f"- Loading: {fx['loading']}")
    return "\n".join(lines)


def _prod(cid: str, name: str, **overrides) -> dict:
    """Return expected_facts product dict from fixture, with optional overrides."""
    base = dict(CUSTOMER_FIXTURES[cid]["products"][name])
    base["name"] = name
    base.update(overrides)
    return base


def _facts(products: list[dict], ports: list[str], payment_terms: str = "",
           packing: str = "", loading: str = "") -> dict:
    return {
        "products": products,
        "ports": ports,
        "payment_terms": payment_terms,
        "packing": packing,
        "loading": loading,
    }


# ── Chat spec definitions ─────────────────────────────────────────────────────
# Each entry produces one JSON file. 'messages' use timestamp=1,2,3,...

C1 = "18965853-110b-40a3-9a9c-f6c29582e7b6"
C2 = "f081da35-3b14-4328-86f6-0f569bc63b43"
C3 = "12a4f3a7-d506-4d32-ae06-3f76508c6abd"
C4 = "d586d853-694c-42f9-93be-bc7ba5b2110c"
C5 = "8f477a8f-2a60-4e0a-bf0e-8cc3cdf1dc9f"
C6 = "acme_foods"

CHAT_SPECS: list[dict] = [

    # ── Memory-Required / Single Product (mr_sp_001 – mr_sp_010) ──────────────
    {
        "chat_id": "mr_sp_001", "customer_id": C1,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Hi, we need GIIOFEED PL-5 — same quantity and price as last time."},
            {"from_whom": "(SELLER)", "body": "Confirmed. I'll book it for next week's dispatch."},
            {"from_whom": "(BUYER)", "body": "CIF Busan as usual. Thanks."},
        ],
        "expected_facts": _facts(
            products=[_prod(C1, "GIIOFEED PL-5")],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mr_sp_002", "customer_id": C1,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Please send the usual qty of PL-5, standard packing."},
            {"from_whom": "(SELLER)", "body": "Sure, will process at our standard rate."},
            {"from_whom": "(BUYER)", "body": "Same destination as before."},
        ],
        "expected_facts": _facts(
            products=[_prod(C1, "GIIOFEED PL-5")],
            ports=["Busan"],
            packing="25kg PP bags",
            loading="1x20 FCL",
        ),
    },
    {
        "chat_id": "mr_sp_003", "customer_id": C2,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Standard order of GIIOFINE - L - SF please, same terms as last shipment."},
            {"from_whom": "(SELLER)", "body": "Got it, will book the IBC."},
            {"from_whom": "(BUYER)", "body": "Payment COD as agreed."},
        ],
        "expected_facts": _facts(
            products=[_prod(C2, "GIIOFINE - L - SF")],
            ports=["Busan"],
            payment_terms="COD",
            packing="IBC",
        ),
    },
    {
        "chat_id": "mr_sp_004", "customer_id": C4,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Another order of BP102 please, 23 MT. Usual terms apply."},
            {"from_whom": "(SELLER)", "body": "Noted. Same price and packing as before?"},
            {"from_whom": "(BUYER)", "body": "Yes exactly. CIF Busan."},
        ],
        "expected_facts": _facts(
            products=[_prod(C4, "BP102")],
            ports=["Busan"],
            packing="25kg printed paper bag",
            loading="23MT / 40' FCL",
        ),
    },
    {
        "chat_id": "mr_sp_005", "customer_id": C5,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10.5 MT Bergapur for March dispatch, same pricing as January."},
            {"from_whom": "(SELLER)", "body": "Confirmed for March, EXW."},
            {"from_whom": "(BUYER)", "body": "Standard packing, 25kg bags."},
        ],
        "expected_facts": _facts(
            products=[_prod(C5, "Bergapur")],
            ports=[],
            packing="25kg bags",
            loading="40' FCL",
        ),
    },
    {
        "chat_id": "mr_sp_006", "customer_id": C6,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Hi, need the same KISAN Coffee order as usual."},
            {"from_whom": "(SELLER)", "body": "Confirmed, will ship FOB Singapore."},
            {"from_whom": "(BUYER)", "body": "Same payment terms as before — Net 15."},
        ],
        "expected_facts": _facts(
            products=[_prod(C6, "KISAN Coffee")],
            ports=["Singapore"],
            payment_terms="Net 15",
        ),
    },
    {
        "chat_id": "mr_sp_007", "customer_id": C3,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Another 13MT of GIIOFINE-P-S, usual port and price."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 25kg PP bags."},
            {"from_whom": "(BUYER)", "body": "Great, same FCL arrangement."},
        ],
        "expected_facts": _facts(
            products=[_prod(C3, "GIIOFINE-P-S")],
            ports=["Busan"],
            packing="25kg PP bags",
            loading="2x20 FCL",
        ),
    },
    {
        "chat_id": "mr_sp_008", "customer_id": C1,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Need 1 MT of PL-5 this time, same price per MT as usual."},
            {"from_whom": "(SELLER)", "body": "Done. Destination Busan, CIF."},
        ],
        "expected_facts": _facts(
            products=[_prod(C1, "GIIOFEED PL-5", quantity=1.0)],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mr_sp_009", "customer_id": C4,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "20 MT BP102, CIF Busan, usual packing and loading please."},
            {"from_whom": "(SELLER)", "body": "Confirmed at standard rate."},
        ],
        "expected_facts": _facts(
            products=[_prod(C4, "BP102", quantity=20.0)],
            ports=["Busan"],
            packing="25kg printed paper bag",
            loading="23MT / 40' FCL",
        ),
    },
    {
        "chat_id": "mr_sp_010", "customer_id": C5,
        "category": "memory_required", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Usual Bergapur qty for March dispatch, EXW, standard bag."},
            {"from_whom": "(SELLER)", "body": "Confirmed, same price as January contract."},
        ],
        "expected_facts": _facts(
            products=[_prod(C5, "Bergapur")],
            ports=[],
            packing="25kg bags",
            loading="40' FCL",
        ),
    },

    # ── Memory-Required / Multiple Products (mr_mp_001 – mr_mp_010) ───────────
    {
        "chat_id": "mr_mp_001", "customer_id": C2,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Please process GIIOFEED PL-5 as usual, plus 1 IBC of GIIOFINE - L - SF."},
            {"from_whom": "(SELLER)", "body": "Confirmed both. Same pricing applies."},
            {"from_whom": "(BUYER)", "body": "CIF Busan, COD payment."},
        ],
        "expected_facts": _facts(
            products=[_prod(C2, "GIIOFEED PL-5"), _prod(C2, "GIIOFINE - L - SF")],
            ports=["Busan"],
            payment_terms="COD",
            packing="IBC",
        ),
    },
    {
        "chat_id": "mr_mp_002", "customer_id": C1,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Need 2 MT PL-5 at the usual rate, plus a 500kg sample at same price."},
            {"from_whom": "(SELLER)", "body": "Confirmed. CIF Busan for both."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C1, "GIIOFEED PL-5"),
                _prod(C1, "GIIOFEED PL-5", quantity=0.5, unit="MT"),
            ],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mr_mp_003", "customer_id": C3,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Confirming 2 FCL GIIOFINE-P-S at standard price. Usual arrangement."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 25kg PP bags, CIF Busan."},
        ],
        "expected_facts": _facts(
            products=[_prod(C3, "GIIOFINE-P-S", quantity=26.0)],
            ports=["Busan"],
            packing="25kg PP bags",
            loading="2x20 FCL",
        ),
    },
    {
        "chat_id": "mr_mp_004", "customer_id": C4,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "20 MT BP102 for October. Same price as before. Add 3 MT BP102 trial at same rate."},
            {"from_whom": "(SELLER)", "body": "Confirmed all. Same destination and packing."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C4, "BP102", quantity=20.0),
                _prod(C4, "BP102", quantity=3.0),
            ],
            ports=["Busan"],
            packing="25kg printed paper bag",
        ),
    },
    {
        "chat_id": "mr_mp_005", "customer_id": C5,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10.5 MT Bergapur + 6.3 MT additional Bergapur, January pricing."},
            {"from_whom": "(SELLER)", "body": "Confirmed. EXW, 25kg bags."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C5, "Bergapur"),
                _prod(C5, "Bergapur", quantity=6.3),
            ],
            ports=[],
            packing="25kg bags",
        ),
    },
    {
        "chat_id": "mr_mp_006", "customer_id": C6,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "The usual KISAN Coffee order. Also add 5 cartons of Arabica at same per-bag price."},
            {"from_whom": "(SELLER)", "body": "Done, FOB Singapore. Net 15 payment."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C6, "KISAN Coffee"),
                {"name": "Arabica", "quantity": 5.0, "unit": "cartons",
                 "price": 25.0, "price_unit": "USD/bag", "incoterm": "FOB", "port": "Singapore"},
            ],
            ports=["Singapore"],
            payment_terms="Net 15",
        ),
    },
    {
        "chat_id": "mr_mp_007", "customer_id": C2,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Same combo as last time: PL-5 plus the SF liquid."},
            {"from_whom": "(SELLER)", "body": "Confirmed. CIF Busan, COD."},
        ],
        "expected_facts": _facts(
            products=[_prod(C2, "GIIOFEED PL-5"), _prod(C2, "GIIOFINE - L - SF")],
            ports=["Busan"],
            payment_terms="COD",
        ),
    },
    {
        "chat_id": "mr_mp_008", "customer_id": C3,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "39 MT soya lecithin powder in usual packing plus 2 extra MT, same terms."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 25kg PP bags, CIF Busan."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C3, "GIIOFINE-P-S", quantity=39.0),
                _prod(C3, "GIIOFINE-P-S", quantity=2.0),
            ],
            ports=["Busan"],
            packing="25kg PP bags",
        ),
    },
    {
        "chat_id": "mr_mp_009", "customer_id": C4,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Standard BP102 order. Also 2 MT BP102 trial sample, standard terms."},
            {"from_whom": "(SELLER)", "body": "All confirmed. Packing and loading as usual."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C4, "BP102"),
                _prod(C4, "BP102", quantity=2.0),
            ],
            ports=["Busan"],
            packing="25kg printed paper bag",
            loading="23MT / 40' FCL",
        ),
    },
    {
        "chat_id": "mr_mp_010", "customer_id": C5,
        "category": "memory_required", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "March and April Bergapur splits, standard pricing. 10.5 MT each."},
            {"from_whom": "(SELLER)", "body": "Confirmed. EXW, same packing."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C5, "Bergapur"),
                _prod(C5, "Bergapur"),
            ],
            ports=[],
            packing="25kg bags",
        ),
    },

    # ── Memory-Required / Multiple Shipments (mr_ms_001 – mr_ms_010) ─────────
    {
        "chat_id": "mr_ms_001", "customer_id": C4,
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "BP102: split usual order — half in November, half in January. Usual packing and price."},
            {"from_whom": "(SELLER)", "body": "Confirmed. CIF Busan both shipments."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C4, "BP102", quantity=11.5),
                _prod(C4, "BP102", quantity=11.5),
            ],
            ports=["Busan"],
            packing="25kg printed paper bag",
        ),
    },
    {
        "chat_id": "mr_ms_002", "customer_id": C1,
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "2 MT July + 2 MT August PL-5. Same price per MT as always."},
            {"from_whom": "(SELLER)", "body": "CIF Busan confirmed for both."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C1, "GIIOFEED PL-5"),
                _prod(C1, "GIIOFEED PL-5"),
            ],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mr_ms_003", "customer_id": C2,
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "GIIOFEED PL-5 split over 2 containers, standard terms, same pricing."},
            {"from_whom": "(SELLER)", "body": "Noted. COD, CIF Busan, July and August."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C2, "GIIOFEED PL-5"),
                _prod(C2, "GIIOFEED PL-5"),
            ],
            ports=["Busan"],
            payment_terms="COD",
        ),
    },
    {
        "chat_id": "mr_ms_004", "customer_id": "fc1a5131-1287-4c0b-98c6-40d0d5012d72",
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Two batches of MGL8: 8 MT by November, remaining in January. Usual 25kg stitch paper bag."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 10 MT total, split as requested."},
        ],
        "expected_facts": _facts(
            products=[
                {"name": "MGL8", "quantity": 8.0, "unit": "MT",
                 "price": None, "price_unit": None, "incoterm": None, "port": None},
                {"name": "MGL8", "quantity": 2.0, "unit": "MT",
                 "price": None, "price_unit": None, "incoterm": None, "port": None},
            ],
            ports=[],
            packing="25kg stitch paper bag",
        ),
    },
    {
        "chat_id": "mr_ms_005", "customer_id": C5,
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10.5 MT March + 6.3 MT late March + 4.2 MT April Bergapur. Standard January price."},
            {"from_whom": "(SELLER)", "body": "Confirmed all three. EXW, 25kg bags."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C5, "Bergapur"),
                _prod(C5, "Bergapur", quantity=6.3),
                _prod(C5, "Bergapur", quantity=4.2),
            ],
            ports=[],
            packing="25kg bags",
        ),
    },
    {
        "chat_id": "mr_ms_006", "customer_id": C3,
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "2 × 20' FCL GIIOFINE-P-S, usual arrangement. June and July."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 25kg PP bags, CIF Busan."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C3, "GIIOFINE-P-S"),
                _prod(C3, "GIIOFINE-P-S"),
            ],
            ports=["Busan"],
            packing="25kg PP bags",
            loading="2x20 FCL",
        ),
    },
    {
        "chat_id": "mr_ms_007", "customer_id": C4,
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "23 MT BP102 this month + additional 23 MT next month. Same everything."},
            {"from_whom": "(SELLER)", "body": "Both confirmed. CIF Busan, standard packing."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C4, "BP102"),
                _prod(C4, "BP102"),
            ],
            ports=["Busan"],
            packing="25kg printed paper bag",
            loading="23MT / 40' FCL",
        ),
    },
    {
        "chat_id": "mr_ms_008", "customer_id": C6,
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10 bags KISAN Coffee now + 10 bags next quarter. Same price as always."},
            {"from_whom": "(SELLER)", "body": "Confirmed. FOB Singapore, Net 15."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C6, "KISAN Coffee"),
                _prod(C6, "KISAN Coffee"),
            ],
            ports=["Singapore"],
            payment_terms="Net 15",
        ),
    },
    {
        "chat_id": "mr_ms_009", "customer_id": C1,
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "First 1 MT July, then 1 MT August PL-5. Standard terms and port."},
            {"from_whom": "(SELLER)", "body": "Confirmed at usual rate, CIF Busan."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C1, "GIIOFEED PL-5", quantity=1.0),
                _prod(C1, "GIIOFEED PL-5", quantity=1.0),
            ],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mr_ms_010", "customer_id": C5,
        "category": "memory_required", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "January and February Bergapur shipments. Usual quantity each month."},
            {"from_whom": "(SELLER)", "body": "Confirmed. EXW, 25kg bags, same pricing."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C5, "Bergapur"),
                _prod(C5, "Bergapur"),
            ],
            ports=[],
            packing="25kg bags",
        ),
    },

    # ── Memory-Boost / Single Product (mb_sp_001 – mb_sp_010) ─────────────────
    {
        "chat_id": "mb_sp_001", "customer_id": C1,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "We need 2 MT of GIIOFEED PL-5 at USD 1420/MT, CIF Busan."},
            {"from_whom": "(SELLER)", "body": "Confirmed. Will process the order."},
        ],
        "expected_facts": _facts(
            products=[_prod(C1, "GIIOFEED PL-5")],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mb_sp_002", "customer_id": C1,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "Order 3 MT GIIOFEED PL-5 at USD 1420/MT, CIF Busan, July dispatch."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 25kg PP bags, 1x20 FCL."},
        ],
        "expected_facts": _facts(
            products=[_prod(C1, "GIIOFEED PL-5", quantity=3.0)],
            ports=["Busan"],
            packing="25kg PP bags",
            loading="1x20 FCL",
        ),
    },
    {
        "chat_id": "mb_sp_003", "customer_id": C4,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "23 MT BP102 at USD 1425/MT, CIF Busan, 25kg printed paper bag, 23MT / 40' FCL."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[_prod(C4, "BP102")],
            ports=["Busan"],
            packing="25kg printed paper bag",
            loading="23MT / 40' FCL",
        ),
    },
    {
        "chat_id": "mb_sp_004", "customer_id": C5,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10.5 MT Bergapur at USD 3100/MT, EXW, 25kg bags, 40' FCL."},
            {"from_whom": "(SELLER)", "body": "Confirmed for March dispatch."},
        ],
        "expected_facts": _facts(
            products=[_prod(C5, "Bergapur")],
            ports=[],
            packing="25kg bags",
            loading="40' FCL",
        ),
    },
    {
        "chat_id": "mb_sp_005", "customer_id": C3,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "13 MT GIIOFINE-P-S at USD 2850/MT, CIF Busan, 25kg PP bags."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 2x20 FCL."},
        ],
        "expected_facts": _facts(
            products=[_prod(C3, "GIIOFINE-P-S")],
            ports=["Busan"],
            packing="25kg PP bags",
            loading="2x20 FCL",
        ),
    },
    {
        "chat_id": "mb_sp_006", "customer_id": C2,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "1 IBC GIIOFINE - L - SF (liquid) at USD 2980/MT, CIF Busan."},
            {"from_whom": "(SELLER)", "body": "Confirmed. COD payment."},
        ],
        "expected_facts": _facts(
            products=[_prod(C2, "GIIOFINE - L - SF")],
            ports=["Busan"],
            payment_terms="COD",
            packing="IBC",
        ),
    },
    {
        "chat_id": "mb_sp_007", "customer_id": C6,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10 bags KISAN Coffee at USD 25/bag, FOB Singapore, Net 15."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[_prod(C6, "KISAN Coffee")],
            ports=["Singapore"],
            payment_terms="Net 15",
        ),
    },
    {
        "chat_id": "mb_sp_008", "customer_id": C1,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "1 MT GIIOFEED PL-5 at USD 1420/MT, CIF Busan, July."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[_prod(C1, "GIIOFEED PL-5", quantity=1.0)],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mb_sp_009", "customer_id": C4,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "12 MT BP102 at USD 1425/MT, CIF Busan, 20' FCL."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 25kg printed paper bag."},
        ],
        "expected_facts": _facts(
            products=[_prod(C4, "BP102", quantity=12.0)],
            ports=["Busan"],
            packing="25kg printed paper bag",
        ),
    },
    {
        "chat_id": "mb_sp_010", "customer_id": C5,
        "category": "memory_boost", "chat_type": "single_product",
        "messages": [
            {"from_whom": "(BUYER)", "body": "6.3 MT Bergapur at USD 3.05/kg, EXW, 25kg bags."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[{"name": "Bergapur", "quantity": 6.3, "unit": "MT",
                       "price": 3.05, "price_unit": "USD/kg", "incoterm": "EXW", "port": ""}],
            ports=[],
            packing="25kg bags",
        ),
    },

    # ── Memory-Boost / Multiple Products (mb_mp_001 – mb_mp_010) ─────────────
    {
        "chat_id": "mb_mp_001", "customer_id": C2,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "2 MT GIIOFEED PL-5 at USD 1420/MT + 1 IBC GIIOFINE - L - SF at USD 2980/MT. CIF Busan."},
            {"from_whom": "(SELLER)", "body": "Confirmed both. COD."},
        ],
        "expected_facts": _facts(
            products=[_prod(C2, "GIIOFEED PL-5"), _prod(C2, "GIIOFINE - L - SF")],
            ports=["Busan"],
            payment_terms="COD",
        ),
    },
    {
        "chat_id": "mb_mp_002", "customer_id": C3,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "13 MT GIIOFINE-P-S at USD 2850/MT + 5 MT soya powder at USD 2500/MT. CIF Busan, 25kg PP bags."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C3, "GIIOFINE-P-S"),
                {"name": "soya powder", "quantity": 5.0, "unit": "MT",
                 "price": 2500.0, "price_unit": "USD/MT", "incoterm": "CIF", "port": "Busan"},
            ],
            ports=["Busan"],
            packing="25kg PP bags",
        ),
    },
    {
        "chat_id": "mb_mp_003", "customer_id": C4,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "20 MT BP102 at USD 1425/MT + 5 MT MGL8 at USD 12000/MT. CIF Busan, 25kg printed paper bag."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C4, "BP102", quantity=20.0),
                {"name": "MGL8", "quantity": 5.0, "unit": "MT",
                 "price": 12000.0, "price_unit": "USD/MT", "incoterm": "CIF", "port": "Busan"},
            ],
            ports=["Busan"],
            packing="25kg printed paper bag",
        ),
    },
    {
        "chat_id": "mb_mp_004", "customer_id": C5,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10.5 MT Bergapur at USD 3100/MT + 5 MT extra at USD 3050/MT. EXW, 25kg bags."},
            {"from_whom": "(SELLER)", "body": "Confirmed both. 40' FCL."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C5, "Bergapur"),
                {"name": "Bergapur", "quantity": 5.0, "unit": "MT",
                 "price": 3050.0, "price_unit": "USD/MT", "incoterm": "EXW", "port": ""},
            ],
            ports=[],
            packing="25kg bags",
        ),
    },
    {
        "chat_id": "mb_mp_005", "customer_id": C6,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10 bags KISAN Coffee at USD 25/bag + 5 cartons Ceylon tea at USD 18/carton. FOB Singapore."},
            {"from_whom": "(SELLER)", "body": "Confirmed. Net 15."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C6, "KISAN Coffee"),
                {"name": "Ceylon tea", "quantity": 5.0, "unit": "cartons",
                 "price": 18.0, "price_unit": "USD/carton", "incoterm": "FOB", "port": "Singapore"},
            ],
            ports=["Singapore"],
            payment_terms="Net 15",
        ),
    },
    {
        "chat_id": "mb_mp_006", "customer_id": C1,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "2 MT GIIOFEED PL-5 at USD 1420/MT + 500kg sample at USD 1500/MT. CIF Busan."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C1, "GIIOFEED PL-5"),
                {"name": "GIIOFEED PL-5", "quantity": 0.5, "unit": "MT",
                 "price": 1500.0, "price_unit": "USD/MT", "incoterm": "CIF", "port": "Busan"},
            ],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mb_mp_007", "customer_id": C3,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "39 MT GIIOFINE-P-S at USD 2850/MT, 25kg PP bags, CIF Busan. Plus 2 MT extra at same price."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C3, "GIIOFINE-P-S", quantity=39.0),
                _prod(C3, "GIIOFINE-P-S", quantity=2.0),
            ],
            ports=["Busan"],
            packing="25kg PP bags",
        ),
    },
    {
        "chat_id": "mb_mp_008", "customer_id": C4,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "23 MT BP102 at USD 1425/MT + 2 MT trial BP102 at USD 1450/MT. CIF Busan."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 25kg printed paper bag."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C4, "BP102"),
                {"name": "BP102", "quantity": 2.0, "unit": "MT",
                 "price": 1450.0, "price_unit": "USD/MT", "incoterm": "CIF", "port": "Busan"},
            ],
            ports=["Busan"],
            packing="25kg printed paper bag",
        ),
    },
    {
        "chat_id": "mb_mp_009", "customer_id": C5,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10.5 MT + 6.3 MT + 4.2 MT Bergapur, all at USD 3.05/kg. EXW, 25kg bags."},
            {"from_whom": "(SELLER)", "body": "Confirmed all three lots. 40' FCL."},
        ],
        "expected_facts": _facts(
            products=[
                {"name": "Bergapur", "quantity": 10.5, "unit": "MT",
                 "price": 3.05, "price_unit": "USD/kg", "incoterm": "EXW", "port": ""},
                {"name": "Bergapur", "quantity": 6.3, "unit": "MT",
                 "price": 3.05, "price_unit": "USD/kg", "incoterm": "EXW", "port": ""},
                {"name": "Bergapur", "quantity": 4.2, "unit": "MT",
                 "price": 3.05, "price_unit": "USD/kg", "incoterm": "EXW", "port": ""},
            ],
            ports=[],
            packing="25kg bags",
        ),
    },
    {
        "chat_id": "mb_mp_010", "customer_id": C2,
        "category": "memory_boost", "chat_type": "multiple_products",
        "messages": [
            {"from_whom": "(BUYER)", "body": "GIIOFEED PL-5 2MT at USD 1420/MT and GIIOFINE - L - SF 1.1MT at USD 2980/MT. CIF Busan, COD."},
            {"from_whom": "(SELLER)", "body": "Confirmed both items."},
        ],
        "expected_facts": _facts(
            products=[_prod(C2, "GIIOFEED PL-5"), _prod(C2, "GIIOFINE - L - SF")],
            ports=["Busan"],
            payment_terms="COD",
        ),
    },

    # ── Memory-Boost / Multiple Shipments (mb_ms_001 – mb_ms_010) ────────────
    {
        "chat_id": "mb_ms_001", "customer_id": C4,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "8 MT BP102 in November at USD 1425/MT + 15 MT in January at USD 1425/MT. CIF Busan, 25kg printed paper bag."},
            {"from_whom": "(SELLER)", "body": "Confirmed both shipments."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C4, "BP102", quantity=8.0),
                _prod(C4, "BP102", quantity=15.0),
            ],
            ports=["Busan"],
            packing="25kg printed paper bag",
        ),
    },
    {
        "chat_id": "mb_ms_002", "customer_id": C1,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "1 MT GIIOFEED PL-5 July at USD 1420/MT + 1 MT August at USD 1420/MT. CIF Busan."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C1, "GIIOFEED PL-5", quantity=1.0),
                _prod(C1, "GIIOFEED PL-5", quantity=1.0),
            ],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mb_ms_003", "customer_id": C5,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10.5 MT Bergapur March at USD 3.05/kg + 6.3 MT late March at USD 3.05/kg. EXW, 25kg bags."},
            {"from_whom": "(SELLER)", "body": "Confirmed both."},
        ],
        "expected_facts": _facts(
            products=[
                {"name": "Bergapur", "quantity": 10.5, "unit": "MT",
                 "price": 3.05, "price_unit": "USD/kg", "incoterm": "EXW", "port": ""},
                {"name": "Bergapur", "quantity": 6.3, "unit": "MT",
                 "price": 3.05, "price_unit": "USD/kg", "incoterm": "EXW", "port": ""},
            ],
            ports=[],
            packing="25kg bags",
        ),
    },
    {
        "chat_id": "mb_ms_004", "customer_id": C3,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "26 MT GIIOFINE-P-S: 13 MT in June + 13 MT in July. USD 2850/MT, CIF Busan, 25kg PP bags."},
            {"from_whom": "(SELLER)", "body": "Confirmed. 2x20 FCL each."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C3, "GIIOFINE-P-S"),
                _prod(C3, "GIIOFINE-P-S"),
            ],
            ports=["Busan"],
            packing="25kg PP bags",
            loading="2x20 FCL",
        ),
    },
    {
        "chat_id": "mb_ms_005", "customer_id": C2,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "2 MT GIIOFEED PL-5 July at USD 1420/MT + 2 MT August at USD 1420/MT. CIF Busan, COD."},
            {"from_whom": "(SELLER)", "body": "Confirmed."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C2, "GIIOFEED PL-5"),
                _prod(C2, "GIIOFEED PL-5"),
            ],
            ports=["Busan"],
            payment_terms="COD",
        ),
    },
    {
        "chat_id": "mb_ms_006", "customer_id": C6,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "10 bags KISAN Coffee in May + 10 bags in June. USD 25/bag, FOB Singapore, Net 15."},
            {"from_whom": "(SELLER)", "body": "Confirmed both shipments."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C6, "KISAN Coffee"),
                _prod(C6, "KISAN Coffee"),
            ],
            ports=["Singapore"],
            payment_terms="Net 15",
        ),
    },
    {
        "chat_id": "mb_ms_007", "customer_id": C4,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "20 MT BP102 October + 23 MT November. USD 1425/MT, CIF Busan, 25kg printed paper bag."},
            {"from_whom": "(SELLER)", "body": "Confirmed both."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C4, "BP102", quantity=20.0),
                _prod(C4, "BP102"),
            ],
            ports=["Busan"],
            packing="25kg printed paper bag",
        ),
    },
    {
        "chat_id": "mb_ms_008", "customer_id": C1,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "3 shipments: 1 MT July + 2 MT August + 1 MT September GIIOFEED PL-5 at USD 1420/MT. CIF Busan."},
            {"from_whom": "(SELLER)", "body": "All three confirmed."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C1, "GIIOFEED PL-5", quantity=1.0),
                _prod(C1, "GIIOFEED PL-5", quantity=2.0),
                _prod(C1, "GIIOFEED PL-5", quantity=1.0),
            ],
            ports=["Busan"],
        ),
    },
    {
        "chat_id": "mb_ms_009", "customer_id": C5,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "January 10.5 MT Bergapur + February 6.3 MT Bergapur. USD 3.05/kg, EXW, 25kg bags."},
            {"from_whom": "(SELLER)", "body": "Confirmed both."},
        ],
        "expected_facts": _facts(
            products=[
                {"name": "Bergapur", "quantity": 10.5, "unit": "MT",
                 "price": 3.05, "price_unit": "USD/kg", "incoterm": "EXW", "port": ""},
                {"name": "Bergapur", "quantity": 6.3, "unit": "MT",
                 "price": 3.05, "price_unit": "USD/kg", "incoterm": "EXW", "port": ""},
            ],
            ports=[],
            packing="25kg bags",
        ),
    },
    {
        "chat_id": "mb_ms_010", "customer_id": C3,
        "category": "memory_boost", "chat_type": "multiple_shipments",
        "messages": [
            {"from_whom": "(BUYER)", "body": "3 × 13MT GIIOFINE-P-S: July + August + September. USD 2850/MT, CIF Busan, 25kg PP bags."},
            {"from_whom": "(SELLER)", "body": "Confirmed all three. 2x20 FCL each."},
        ],
        "expected_facts": _facts(
            products=[
                _prod(C3, "GIIOFINE-P-S"),
                _prod(C3, "GIIOFINE-P-S"),
                _prod(C3, "GIIOFINE-P-S"),
            ],
            ports=["Busan"],
            packing="25kg PP bags",
            loading="2x20 FCL",
        ),
    },
]


# ── Generator ────────────────────────────────────────────────────────────────

def _build_chat_text(messages: list[dict]) -> str:
    return "\n".join(
        f"{m['from_whom']}: {m['body']}" for m in messages
    )


def generate_all(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for spec in CHAT_SPECS:
        cid = spec["customer_id"]
        # Add timestamps
        messages = [
            {**m, "timestamp": i + 1}
            for i, m in enumerate(spec["messages"])
        ]
        # Build mock_memory_block only for customers in CUSTOMER_FIXTURES
        mock_block: str | None = None
        if cid in CUSTOMER_FIXTURES:
            mock_block = _memory_block(cid)

        record = {
            "chat_id": spec["chat_id"],
            "customer_id": cid,
            "category": spec["category"],
            "chat_type": spec["chat_type"],
            "chat_text": _build_chat_text(messages),
            "messages": messages,
            "mock_memory_block": mock_block,
            "expected_facts": spec["expected_facts"],
        }
        out_path = out_dir / f"{spec['chat_id']}.json"
        out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        print(f"  wrote {out_path.relative_to(Path.cwd())}")

    print(f"\nGenerated {len(CHAT_SPECS)} synthetic chats → {out_dir}")


if __name__ == "__main__":
    generate_all(OUT_DIR)
