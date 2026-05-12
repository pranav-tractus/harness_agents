"""Generate operationally-realistic customer chats.

Adds realism the simple synthetic generator does not cover:

- ``long_thread``        : 20+ messages with off-topic banter and status checks
- ``noisy_text``         : typos, emojis, voice-to-text artifacts, partial duplicates
- ``missing_prices``     : vague price phrasing ("usual rate", "same as last time")
- ``contradictory``      : buyer flips quantity / price / address mid-thread
- ``multilingual``       : Spanish / Hindi / French / Mandarin snippets mixed in

Each generated chat carries top-level ``realism_flags`` so dashboards and
filters can segment by realism type without re-parsing message bodies.

Usage:
    python -m agents.so_extraction.data_gen.generate_realistic_chats \\
        --config configs/agents.json --count-per-customer 10
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.config import load_config


BASE_ITEMS = [
    ("Arabica coffee bags", 8, 24),
    ("Robusta coffee bags", 12, 21),
    ("Ceylon tea cartons", 20, 18),
    ("Assam tea cartons", 15, 19),
    ("Espresso blend bags", 6, 27),
    ("Green coffee beans sacks", 80, 16),
    ("Premium cocoa packs", 25, 14),
    ("Black tea cartons", 18, 17),
    ("Specialty sample kits", 3, 55),
    ("Filter paper packs", 10, 6),
]

ADDRESSES = [
    "101 Market Street, Customer Hub",
    "212 Riverside Drive, Old Town",
    "9 Harbor Plaza, Pier 4",
    "55 Spice Lane, Warehouse District",
    "300 Innovation Park, Block C",
]

PAYMENT_TERMS = ["Net 15", "Net 30", "Net 45", "50% advance", "Immediate transfer"]


def _flavor_long_thread(rng: random.Random, base_msgs: list[dict]) -> list[dict]:
    extras: list[dict] = []
    fillers = [
        ("(BUYER)", "By the way, how was the trade fair last week?"),
        ("(SELLER)", "It was good, picked up a few new SKUs to share next call."),
        ("(BUYER)", "Quick check - is the warehouse still closed Sundays?"),
        ("(SELLER)", "Yes Sundays closed, Saturdays half day until 1pm."),
        ("(BUYER)", "Noted. Also, did you receive the previous invoice copy?"),
        ("(SELLER)", "Yes received, accounts team is processing it."),
        ("(BUYER)", "Great. One more thing - any new arrivals on Robusta?"),
        ("(SELLER)", "Yes a fresh lot landed Tuesday, will share photos."),
        ("(BUYER)", "Please share. We may add it to next month's order."),
        ("(SELLER)", "Will do later today after the inspection."),
        ("(BUYER)", "Thanks. Also confirm the GST number we have on file."),
        ("(SELLER)", "GST is unchanged, same as last invoice."),
        ("(BUYER)", "Good. Forward the dispatch ETA once available."),
        ("(SELLER)", "Sure, expecting confirmation from logistics in an hour."),
        ("(BUYER)", "Perfect."),
        ("(SELLER)", "Update - logistics confirmed dispatch slot."),
        ("(BUYER)", "Send the AWB once generated."),
        ("(SELLER)", "Will share by EOD."),
        ("(BUYER)", "Also, share the test report for the new lot when ready."),
        ("(SELLER)", "Yes, lab results due by Friday."),
        ("(BUYER)", "OK, talk soon."),
        ("(SELLER)", "Talk soon."),
    ]
    base_ts = max(m["timestamp"] for m in base_msgs)
    rng.shuffle(fillers)
    for offset, (who, text) in enumerate(fillers, start=1):
        extras.append({"from_whom": who, "body": text, "timestamp": base_ts + offset})
    return extras


def _flavor_noisy_text(rng: random.Random, base_msgs: list[dict]) -> list[dict]:
    emoji_pool = ["😅", "👍", "🙏", "🚚", "📦", "✅", "❗", "..."]
    typo_map = {
        "the": "teh",
        "please": "pls",
        "thanks": "thx",
        "address": "addr",
        "tomorrow": "tmrw",
        "shipment": "shipmnt",
        "payment": "paymnt",
        "delivery": "delvery",
    }
    new_msgs: list[dict] = []
    for msg in base_msgs:
        body = msg["body"]
        for k, v in typo_map.items():
            if rng.random() < 0.45 and k in body.lower():
                body = body.replace(k, v).replace(k.capitalize(), v.capitalize())
        if rng.random() < 0.6:
            body = body + " " + rng.choice(emoji_pool)
        new_msgs.append({**msg, "body": body})
        if rng.random() < 0.25:
            new_msgs.append({"from_whom": msg["from_whom"], "body": "(typing...)", "timestamp": msg["timestamp"] + 1})
        if rng.random() < 0.2:
            new_msgs.append({"from_whom": msg["from_whom"], "body": body[: max(5, len(body) // 2)] + "—", "timestamp": msg["timestamp"] + 2})
    return new_msgs


def _flavor_missing_prices(rng: random.Random, base_msgs: list[dict]) -> list[dict]:
    replacements = [
        "usual rate",
        "same as last time",
        "you know our standard pricing",
        "let's go with last month's rate",
        "price as previously agreed",
    ]
    new_msgs: list[dict] = []
    for msg in base_msgs:
        body = msg["body"]
        if "USD" in body or "$" in body or "@ " in body:
            body = body.split("@")[0].strip() + " @ " + rng.choice(replacements) + "."
        new_msgs.append({**msg, "body": body})
    new_msgs.append(
        {
            "from_whom": "(SELLER)",
            "body": "Will use the rate we discussed last cycle unless you confirm otherwise.",
            "timestamp": max(m["timestamp"] for m in base_msgs) + 1,
        }
    )
    return new_msgs


def _flavor_contradictory(rng: random.Random, base_msgs: list[dict]) -> list[dict]:
    base_ts = max(m["timestamp"] for m in base_msgs)
    flips = [
        ("(BUYER)", "Actually scratch that, double the quantity on the first line item."),
        ("(BUYER)", "Wait sorry - keep original qty but change unit price down by 2 USD."),
        ("(BUYER)", "Hmm, on second thought, ship to 9 Harbor Plaza instead of the address I gave."),
        ("(SELLER)", "Just to confirm - which version is final?"),
        ("(BUYER)", "Final: original qty, original price, deliver to 9 Harbor Plaza."),
        ("(BUYER)", "Actually one more change - split the delivery into two equal shipments."),
    ]
    return [
        {"from_whom": who, "body": text, "timestamp": base_ts + offset}
        for offset, (who, text) in enumerate(flips, start=1)
    ]


def _flavor_multilingual(rng: random.Random, base_msgs: list[dict]) -> list[dict]:
    pool = [
        ("(BUYER)", "Hola, mismo pedido por favor confirmar el total."),
        ("(SELLER)", "Bonjour, je vous envoie la confirmation tout de suite."),
        ("(BUYER)", "Bhai ek minute, total kitna ban raha hai exactly?"),
        ("(SELLER)", "Ji bilkul, abhi calculate karke share karta hu."),
        ("(BUYER)", "请问什么时候发货？"),
        ("(SELLER)", "明天上午发货，单号稍后发您。"),
        ("(BUYER)", "Obrigado, qualquer atualização me avise."),
    ]
    base_ts = max(m["timestamp"] for m in base_msgs)
    rng.shuffle(pool)
    return [
        {"from_whom": who, "body": text, "timestamp": base_ts + offset}
        for offset, (who, text) in enumerate(pool[:5], start=1)
    ]


FLAVOR_REGISTRY: dict[str, Callable[[random.Random, list[dict]], list[dict]]] = {
    "long_thread": _flavor_long_thread,
    "noisy_text": _flavor_noisy_text,
    "missing_prices": _flavor_missing_prices,
    "contradictory": _flavor_contradictory,
    "multilingual": _flavor_multilingual,
}


def _build_base_messages(rng: random.Random, customer_name: str, idx: int) -> tuple[list[dict], dict]:
    item = rng.choice(BASE_ITEMS)
    name, qty, price = item
    address = rng.choice(ADDRESSES)
    payment = rng.choice(PAYMENT_TERMS)
    subtotal = qty * price
    messages = [
        {
            "from_whom": "(BUYER)",
            "body": f"Hi {customer_name}, please raise an SO for {qty} x {name} @ {price} USD. Thanks.",
            "timestamp": idx * 100 + 1,
        },
        {
            "from_whom": "(SELLER)",
            "body": f"Got it - subtotal {subtotal} USD. Confirm address and payment terms?",
            "timestamp": idx * 100 + 2,
        },
        {
            "from_whom": "(BUYER)",
            "body": f"Address: {address}. Payment: {payment}.",
            "timestamp": idx * 100 + 3,
        },
        {
            "from_whom": "(SELLER)",
            "body": "Noted, sending SO draft today.",
            "timestamp": idx * 100 + 4,
        },
    ]
    meta = {
        "item_name": name,
        "quantity": qty,
        "unit_price": price,
        "currency": "USD",
        "address": address,
        "payment_terms": payment,
    }
    return messages, meta


def _apply_flavors(rng: random.Random, base_msgs: list[dict], flavors: list[str]) -> list[dict]:
    msgs = list(base_msgs)
    for flavor in flavors:
        fn = FLAVOR_REGISTRY[flavor]
        result = fn(rng, msgs)
        if flavor in ("noisy_text", "missing_prices"):
            msgs = result
        else:
            msgs.extend(result)
    msgs.sort(key=lambda m: m["timestamp"])
    return msgs


def _choose_flavors(rng: random.Random, allowed: list[str]) -> list[str]:
    pick_count = rng.choice([1, 1, 2, 2, 3])
    return rng.sample(allowed, k=min(pick_count, len(allowed)))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate realistic customer chats for harness testing.")
    p.add_argument("--config", default="", help="Path to agents.json (default: configs/agents.json).")
    p.add_argument("--agent", default="so_extraction")
    p.add_argument("--count-per-customer", type=int, default=10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--flavors",
        nargs="*",
        default=list(FLAVOR_REGISTRY.keys()),
        choices=list(FLAVOR_REGISTRY.keys()),
    )
    p.add_argument("--prefix", default="realistic")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = load_config(args.config or None)
    agent = cfg.get_agent(args.agent)
    customer_like = [
        ds for ds in agent.datasets()
        if ds.id not in {"core", "downloaded"} and ds.customer_info
    ]
    if not customer_like:
        raise SystemExit("No customer-style datasets found in this agent's config.")

    generated = 0
    summary: dict[str, int] = {flavor: 0 for flavor in args.flavors}

    for ds in customer_like:
        customer_name = ds.customer_info.get("name") if ds.customer_info else ds.id
        customer_id = ds.id
        chats_dir = (agent.repo_root / f"raw_data/customers/{customer_id}/chats").resolve()
        chats_dir.mkdir(parents=True, exist_ok=True)

        customer_seed = args.seed + sum(ord(c) for c in customer_id)
        for idx in range(1, args.count_per_customer + 1):
            rng = random.Random(customer_seed + idx)
            base_msgs, meta = _build_base_messages(rng, customer_name, idx)
            flavors = _choose_flavors(rng, args.flavors)
            messages = _apply_flavors(rng, base_msgs, flavors)
            for flavor in flavors:
                summary[flavor] += 1

            payload = {
                "customer_id": customer_id,
                "chat_name": f"{customer_id}_{args.prefix}_{idx:03d}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "realism_flags": sorted(flavors),
                "complexity_tier": "realistic",
                "ground_truth_meta": meta,
                "messages": messages,
            }
            out_path = chats_dir / f"{args.prefix}_{customer_id}_{idx:03d}.json"
            out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            generated += 1

    print(f"Generated realistic chats: {generated}")
    for flavor, count in sorted(summary.items()):
        print(f"  flavor={flavor:<18} used_in_chats={count}")


if __name__ == "__main__":
    main()
