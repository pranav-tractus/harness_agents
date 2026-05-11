"""Run benchmark_fewshot.py in multiple variants with customer few-shot data.

This wrapper enforces:
- extraction chats from ``raw_data/chats/*.json``
- few-shot examples from customer-specific chat files (configurable count range)

Usage:
    python tests/run_benchmark_variants.py \
      --harness-config configs/customers.sample.json \
      --variants raw_only zero_shot db_plus_raw \
      --runs-per-chat 2 \
      --max-workers 8
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from harness_config import load_harness_config


DEFAULT_VARIANTS = ["raw_only", "zero_shot", "db_only", "db_plus_raw"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run tests/benchmark_fewshot.py across strategy variants while using "
            "customer-specific few-shot examples and raw_data/chats for extraction."
        )
    )
    parser.add_argument(
        "--harness-config",
        required=True,
        help="Path to harness JSON config containing customers and few_shot.paths.",
    )
    parser.add_argument(
        "--variants",
        nargs="*",
        default=DEFAULT_VARIANTS,
        help=f"Few-shot strategy variants. Default: {', '.join(DEFAULT_VARIANTS)}",
    )
    parser.add_argument("--models", nargs="*", default=["sonnet-4-6"])
    parser.add_argument("--customers", nargs="*", default=[])
    parser.add_argument("--runs-per-chat", type=int, default=1)
    parser.add_argument("--max-workers", type=int, default=15)
    parser.add_argument(
        "--min-few-shot-per-customer",
        type=int,
        default=1,
        help="Minimum number of customer-specific few-shot chats to use.",
    )
    parser.add_argument(
        "--max-few-shot-per-customer",
        type=int,
        default=0,
        help="Maximum number of customer-specific few-shot chats to use (0 means all available).",
    )
    parser.add_argument(
        "--few-shot-counts",
        nargs="*",
        type=int,
        default=[],
        help="Optional explicit few-shot counts (overrides min/max range).",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--output-prefix",
        default="fewshot_benchmark_customer_variants",
        help="Prefix for benchmark artifact files.",
    )
    return parser.parse_args()


def _customer_chat_candidates(customer_payload: dict) -> list[Path]:
    dataset_root = (ROOT_DIR / customer_payload["dataset_root"]).resolve()
    return sorted((dataset_root / "chats").glob("*.json"))


def _build_override_config(
    config_path: Path,
    few_shot_count_per_customer: int,
    selected_customers: set[str] | None = None,
) -> Path:
    """Create temp config forcing extract chats to raw_data/chats and few-shot count."""
    cfg = load_harness_config(config_path)
    payload = cfg.model_dump(mode="python")
    for customer in payload.get("customers", []):
        if selected_customers and customer["id"] not in selected_customers:
            continue
        customer["chat_globs"] = ["../../chats/*.json"]
        candidates = _customer_chat_candidates(customer)
        if not candidates:
            continue
        count = min(few_shot_count_per_customer, len(candidates))
        customer.setdefault("few_shot", {})
        customer["few_shot"]["paths"] = [
            str(path.relative_to(ROOT_DIR)) for path in candidates[:count]
        ]

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="benchmark_variants_",
        delete=False,
        encoding="utf-8",
    )
    with tmp:
        tmp.write(json.dumps(payload, indent=2, ensure_ascii=False))
    return Path(tmp.name)


def _run_variant(
    args: argparse.Namespace,
    override_cfg: Path,
    variant: str,
    few_shot_count: int,
) -> int:
    cmd = [
        sys.executable,
        str(ROOT_DIR / "tests" / "benchmark_fewshot.py"),
        "--harness-config",
        str(override_cfg),
        "--fewshot-strategies",
        variant,
        "--runs-per-chat",
        str(args.runs_per_chat),
        "--max-workers",
        str(args.max_workers),
        "--output-prefix",
        f"{args.output_prefix}_{variant}_fs{few_shot_count}",
    ]
    if args.models:
        cmd.extend(["--models", *args.models])
    if args.customers:
        cmd.extend(["--customers", *args.customers])
    if args.quiet:
        cmd.append("--quiet")

    print(
        f"\n=== Running variant: {variant} | few-shot-per-customer={few_shot_count} ===",
        flush=True,
    )
    print(" ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=str(ROOT_DIR))
    return completed.returncode


def main() -> None:
    args = _parse_args()
    config_path = Path(args.harness_config).expanduser().resolve()
    cfg = load_harness_config(config_path)
    requested_customers = set(args.customers) if args.customers else {
        c.id for c in cfg.customers
    }

    available_counts: list[int] = []
    for customer in cfg.customers:
        if customer.id not in requested_customers:
            continue
        chat_count = len(_customer_chat_candidates(customer.model_dump(mode="python")))
        if chat_count > 0:
            available_counts.append(chat_count)
    if not available_counts:
        raise SystemExit("No customer chat candidates found under customer dataset roots.")

    max_possible = min(available_counts)
    if args.few_shot_counts:
        counts = sorted({c for c in args.few_shot_counts if 1 <= c <= max_possible})
    else:
        max_count = (
            max_possible
            if args.max_few_shot_per_customer <= 0
            else min(args.max_few_shot_per_customer, max_possible)
        )
        min_count = max(1, args.min_few_shot_per_customer)
        if min_count > max_count:
            raise SystemExit(
                f"Invalid few-shot range: min={min_count} max={max_count} "
                f"(max_possible={max_possible})"
            )
        counts = list(range(min_count, max_count + 1))
    if not counts:
        raise SystemExit("No valid few-shot counts to run.")

    print("Extract chats source forced to: raw_data/chats/*.json", flush=True)
    print("Few-shot source per customer: customer dataset_root/chats/*.json", flush=True)
    print(f"Few-shot counts to run: {counts}", flush=True)

    failed: list[str] = []
    for few_shot_count in counts:
        override_cfg = _build_override_config(
            config_path,
            few_shot_count_per_customer=few_shot_count,
            selected_customers=requested_customers,
        )
        print(f"Using temporary override config: {override_cfg}", flush=True)
        for variant in args.variants:
            code = _run_variant(args, override_cfg, variant, few_shot_count)
            if code != 0:
                failed.append(f"{variant}:fs{few_shot_count}")

    if failed:
        raise SystemExit(f"Failed variants: {', '.join(failed)}")
    print("\nAll requested variants completed successfully.")


if __name__ == "__main__":
    main()
