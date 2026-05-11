"""Generate synthetic customer-specific chats for harness simulations.

Usage:
    python tests/generate_customer_chats.py --harness-config configs/customers.sample.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from harness_config import load_harness_config

ORDER_SCENARIOS = [
    {
        "order_type": "single_item_spot",
        "lines": [("Arabica coffee bags", 8, 24)],
        "delivery_note": "single delivery next Friday",
        "payment_terms": "Net 15",
    },
    {
        "order_type": "multi_item_purchase_order",
        "lines": [("Robusta coffee bags", 12, 21), ("Ceylon tea cartons", 20, 18)],
        "delivery_note": "single PO, split into 2 lots",
        "payment_terms": "Net 30",
    },
    {
        "order_type": "rush_order",
        "lines": [("Espresso blend bags", 6, 27)],
        "delivery_note": "urgent dispatch within 48 hours",
        "payment_terms": "Immediate transfer",
    },
    {
        "order_type": "bulk_monthly_contract",
        "lines": [("Green coffee beans sacks", 80, 16)],
        "delivery_note": "monthly schedule over 4 shipments",
        "payment_terms": "Net 45",
    },
    {
        "order_type": "trial_then_scale",
        "lines": [("Specialty sample kits", 3, 55)],
        "delivery_note": "trial batch first, full order after approval",
        "payment_terms": "50% advance",
    },
    {
        "order_type": "mixed_currency_style",
        "lines": [("Premium cocoa packs", 25, 14)],
        "delivery_note": "invoice in USD, customs in local currency",
        "payment_terms": "Net 20",
    },
    {
        "order_type": "address_change_mid_order",
        "lines": [("Assam tea cartons", 15, 19)],
        "delivery_note": "delivery address changed after confirmation",
        "payment_terms": "Net 30",
    },
    {
        "order_type": "quantity_revision",
        "lines": [("Instant coffee jars", 40, 9)],
        "delivery_note": "buyer revises quantity before dispatch",
        "payment_terms": "Net 30",
    },
    {
        "order_type": "partial_cancellation",
        "lines": [("Herbal tea boxes", 30, 11)],
        "delivery_note": "partial cancellation after first shipment",
        "payment_terms": "Net 30",
    },
    {
        "order_type": "new_product_addon",
        "lines": [("Black tea cartons", 18, 17), ("Filter paper packs", 10, 6)],
        "delivery_note": "addon item requested after initial quote",
        "payment_terms": "Net 30",
    },
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic chats per customer.")
    parser.add_argument("--harness-config", required=True, help="Path to harness JSON config.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--count-per-customer",
        type=int,
        default=10,
        help="How many chats to generate per customer.",
    )
    return parser.parse_args()


def _build_chat(
    customer_id: str,
    customer_name: str,
    idx: int,
    tier: str,
    tags: list[str],
    scenario: dict,
) -> dict:
    lines = scenario["lines"]
    item_lines = ", ".join([f"{qty} x {name} @ {price} USD" for name, qty, price in lines])
    subtotal = sum(qty * price for _, qty, price in lines)
    order_type = scenario["order_type"]
    delivery_note = scenario["delivery_note"]
    payment_terms = scenario["payment_terms"]
    shipping_address = f"{100 + idx} Market Street, Customer Hub"
    lines = [
        {
            "from_whom": "(BUYER)",
            "body": f"Hi {customer_name}, we need this {order_type} order: {item_lines}.",
            "timestamp": idx * 10 + 1,
        },
        {
            "from_whom": "(SELLER)",
            "body": f"Confirmed. Subtotal is {subtotal} USD. We'll process as {delivery_note}.",
            "timestamp": idx * 10 + 2,
        },
        {
            "from_whom": "(BUYER)",
            "body": f"Shipping address is {shipping_address}. Payment terms: {payment_terms}.",
            "timestamp": idx * 10 + 3,
        },
        {
            "from_whom": "(SELLER)",
            "body": "Noted. Sales order draft will be shared today.",
            "timestamp": idx * 10 + 4,
        },
    ]
    return {
        "customer_id": customer_id,
        "chat_name": f"{customer_id}_synthetic_{order_type}_{idx:03d}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scenario_tags": sorted(set(tags + [order_type])),
        "complexity_tier": tier,
        "order_type": order_type,
        "messages": lines,
    }


def main() -> None:
    args = _parse_args()
    cfg = load_harness_config(args.harness_config)
    root = Path(__file__).resolve().parents[1]
    generated = 0
    for customer in cfg.customers:
        configured_total = customer.synthetic_generation.chats_to_generate
        total = max(configured_total, args.count_per_customer)
        if total <= 0:
            continue
        tiers = customer.synthetic_generation.complexity_tiers or ["simple"]
        tags = customer.synthetic_generation.scenario_tags
        customer_root = (root / customer.dataset_root).resolve()
        chats_dir = customer_root / "chats"
        chats_dir.mkdir(parents=True, exist_ok=True)
        for idx in range(1, total + 1):
            tier = tiers[(idx - 1) % len(tiers)]
            scenario = ORDER_SCENARIOS[(idx - 1) % len(ORDER_SCENARIOS)]
            payload = _build_chat(customer.id, customer.name, idx, tier, tags, scenario)
            out_path = chats_dir / f"generated_{customer.id}_{idx:03d}.json"
            out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            generated += 1
    print(f"Generated chats: {generated}")


if __name__ == "__main__":
    main()
