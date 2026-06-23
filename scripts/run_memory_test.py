#!/usr/bin/env python3
"""Run memory-assisted extraction on synthetic chats, producing harness-style reports.

For each chat in tests/synthetic_chats/:
  Pass 1 (baseline): extract WITHOUT memory block  → score_baseline
  Pass 2 (memory):   extract WITH mock_memory_block → score (final)

This maps directly onto the harness's existing "with_baseline" infrastructure:
  field_match_rate_baseline = accuracy without memory
  field_match_rate_final    = accuracy with memory
  improvement_rate          = fraction of chats where memory helped

Produces results/<run_id>/ with the same files as a normal harness run:
  run.jsonl, aggregate.json, config.json, report.html, token_report.html

Usage:
  python scripts/run_memory_test.py
  python scripts/run_memory_test.py --model-key sonnet-4-6 --category memory_required
  python scripts/run_memory_test.py --chat-type multiple_shipments --no-html
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.base import AgentRunResult, ScoreResult
from graph.extractor import ExtractedFacts, ExtractedProduct, extract_entities
from harness import artifacts

CHATS_DIR = ROOT / "tests" / "synthetic_chats"
DEFAULT_MODEL = "sonnet-4-6"
AGENT_ID = "memory_extraction_test"
DEFAULT_MAX_WORKERS = 8


# ── Scoring ───────────────────────────────────────────────────────────────────

def _find_and_consume(name: str, remaining: list[ExtractedProduct]) -> ExtractedProduct | None:
    needle = name.strip().lower()
    for i, p in enumerate(remaining):
        if p.name.strip().lower() == needle:
            return remaining.pop(i)
    return None


def _score_product(
    expected: dict,
    actual: ExtractedProduct | None,
) -> tuple[int, int, list[dict]]:
    """Returns (matched_fields, total_fields, mismatches)."""
    fields = ["name", "quantity", "unit", "price", "price_unit", "incoterm", "port"]
    matched = total = 0
    mismatches: list[dict] = []

    for f in fields:
        ev = expected.get(f)
        if ev is None or ev == "":
            continue
        total += 1
        av = getattr(actual, f, None) if actual else None
        if isinstance(ev, str) and isinstance(av, str):
            hit = ev.strip().lower() == av.strip().lower()
        else:
            hit = ev == av
        if hit:
            matched += 1
        else:
            mismatches.append({"path": f"product.{f}", "expected": ev, "actual": av})

    return matched, total, mismatches


def score_facts(expected: dict, actual: ExtractedFacts) -> ScoreResult:
    """Field-by-field comparison of expected_facts dict vs ExtractedFacts.

    Uses consumed-match so duplicate product names each require a distinct actual.
    """
    total = matched = 0
    mismatches: list[dict] = []

    remaining = list(actual.products)
    for ep in expected.get("products", []):
        ap = _find_and_consume(ep.get("name", ""), remaining)
        m, t, mm = _score_product(ep, ap)
        matched += m
        total += t
        mismatches.extend(mm)

    for key, av in [
        ("payment_terms", actual.payment_terms),
        ("packing", actual.packing),
        ("loading", actual.loading),
    ]:
        ev = expected.get(key, "")
        if not ev:
            continue
        total += 1
        hit = (
            ev.strip().lower() == av.strip().lower()
            if isinstance(ev, str) and isinstance(av, str)
            else ev == av
        )
        if hit:
            matched += 1
        else:
            mismatches.append({"path": key, "expected": ev, "actual": av})

    act_ports_lower = [p.strip().lower() for p in actual.ports]
    for ep in (p.strip().lower() for p in expected.get("ports", []) if p):
        total += 1
        if ep in act_ports_lower:
            matched += 1
        else:
            mismatches.append({"path": "ports", "expected": ep, "actual": actual.ports})

    return ScoreResult(
        expected_available=total > 0,
        compared_field_count=total,
        mismatch_count=total - matched,
        mismatches=mismatches,
    )


# ── Per-chat runner ───────────────────────────────────────────────────────────

_BEDROCK_MODELS = {"sonnet-4-6", "opus-4-6", "opus-4-7", "opus-4-8"}


def run_one(chat_file: Path, model_key: str) -> AgentRunResult:
    data = json.loads(chat_file.read_text())
    chat_text: str = data["chat_text"]
    memory_block: str | None = data.get("mock_memory_block")
    expected: dict = data["expected_facts"]
    dataset_id = f"synthetic_{data['category']}"
    started = datetime.now(timezone.utc).isoformat()

    # Pass 1: baseline (no memory block)
    t0 = time.perf_counter()
    baseline_facts = extract_entities(chat_text, model_key=model_key)
    baseline_ms = (time.perf_counter() - t0) * 1000

    # Pass 2: memory-assisted
    t1 = time.perf_counter()
    memory_facts = extract_entities(chat_text, model_key=model_key, memory_block=memory_block)
    memory_ms = (time.perf_counter() - t1) * 1000

    elapsed = time.perf_counter() - t0
    provider = "bedrock" if model_key in _BEDROCK_MODELS else "unknown"

    return AgentRunResult(
        agent_id=AGENT_ID,
        dataset_id=dataset_id,
        source_path=str(chat_file),
        success=True,
        status="success",
        attempts=1,
        elapsed_sec=round(elapsed, 4),
        model_key=model_key,
        model_provider=provider,
        validation_model_key=None,
        # memory-assisted output is the "final" result
        output_json=memory_facts.model_dump(),
        raw_llm_output_json=baseline_facts.model_dump(),
        # no-memory output is the "baseline" — maps to both score_raw_llm and score_baseline
        # so that improvement_rate = fraction of chats where memory helped
        baseline_output_json=baseline_facts.model_dump(),
        score=score_facts(expected, memory_facts),
        score_raw_llm=score_facts(expected, baseline_facts),
        score_baseline=score_facts(expected, baseline_facts),
        flow_stage_ms={
            "baseline_extract_ms": round(baseline_ms, 3),
            "memory_extract_ms": round(memory_ms, 3),
            "total_case_ms": round(elapsed * 1000, 3),
        },
        extraction_diagnostics={
            "chat_id": data["chat_id"],
            "category": data["category"],
            "chat_type": data["chat_type"],
            "customer_id": data["customer_id"],
            "memory_block_present": memory_block is not None,
        },
        started_at_utc=started,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def _load_meta(path: Path) -> dict:
    """Read only the metadata fields from a chat JSON (avoids re-parsing in filter)."""
    d = json.loads(path.read_text())
    return {"path": path, "category": d.get("category"), "chat_type": d.get("chat_type")}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Memory extraction benchmark — produces harness-style reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--model-key", default=DEFAULT_MODEL, help=f"Model to use (default: {DEFAULT_MODEL})")
    ap.add_argument("--chats-dir", type=Path, default=CHATS_DIR, help="Directory of synthetic chat JSONs")
    ap.add_argument("--results-dir", type=Path, default=ROOT / "results", help="Where to write results")
    ap.add_argument(
        "--category",
        choices=["memory_required", "memory_boost", "all"],
        default="all",
        help="Filter by chat category",
    )
    ap.add_argument(
        "--chat-type",
        choices=["single_product", "multiple_products", "multiple_shipments", "all"],
        default="all",
        help="Filter by chat type",
    )
    ap.add_argument("--workers", type=int, default=DEFAULT_MAX_WORKERS, help="Parallel workers")
    ap.add_argument("--no-html", action="store_true", help="Skip HTML report generation")
    args = ap.parse_args()

    # Collect + filter chat files
    all_files = sorted(args.chats_dir.glob("*.json"))
    metas = [_load_meta(f) for f in all_files]
    selected = [
        m["path"] for m in metas
        if (args.category == "all" or m["category"] == args.category)
        and (args.chat_type == "all" or m["chat_type"] == args.chat_type)
    ]

    if not selected:
        print("No chat files matched the given filters.", file=sys.stderr)
        sys.exit(1)

    print(f"Memory extraction benchmark")
    print(f"  Model:      {args.model_key}")
    print(f"  Chats:      {len(selected)} (category={args.category}, type={args.chat_type})")
    print()

    run_dir, run_id = artifacts.make_run_dir(args.results_dir)
    config = {
        "agent": AGENT_ID,
        "model_key": args.model_key,
        "chats_dir": str(args.chats_dir),
        "category_filter": args.category,
        "chat_type_filter": args.chat_type,
        "chat_count": len(selected),
        "max_workers": args.workers,
        "description": (
            "Memory-assisted extraction benchmark: "
            "baseline (no memory block) vs memory-assisted (mock_memory_block injected). "
            "field_match_rate_baseline = without memory; field_match_rate_final = with memory."
        ),
    }
    artifacts.write_config(run_dir, config)

    records: list[AgentRunResult] = []
    errors: list[tuple[Path, Exception]] = []
    completed = 0

    # Workers only do LLM calls — all file I/O and list mutations stay on the main thread
    def _run_chat(chat_file: Path) -> AgentRunResult | Exception:
        try:
            return run_one(chat_file, args.model_key)
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_run_chat, f): f for f in selected}
        for future in as_completed(futures):
            chat_file = futures[future]
            completed += 1
            result = future.result()
            if isinstance(result, Exception):
                print(f"  [{completed:3d}/{len(selected)}] {chat_file.stem:<20} ERROR: {result}")
                errors.append((chat_file, result))
            else:
                # File write and list append both happen on the main thread — no races
                artifacts.append_record(run_dir, result)
                records.append(result)
                b = result.score_baseline.field_match_rate() or 0.0
                m = result.score.field_match_rate() or 0.0
                print(
                    f"  [{completed:3d}/{len(selected)}] {chat_file.stem:<20} "
                    f"baseline={b:.2f}  memory={m:.2f}  delta={m - b:+.2f}"
                )

    # Sort records to match file order for deterministic reports
    order = {str(f): i for i, f in enumerate(selected)}
    records.sort(key=lambda r: order.get(r.source_path, 9999))

    # Write aggregate + reports
    print()
    summary = artifacts.aggregate(records)
    artifacts.write_aggregate(run_dir, run_id, summary, config)

    if not args.no_html:
        try:
            artifacts.write_report(
                run_dir, run_id, config, summary, records,
                generate_llm_story=False,
            )
            print(f"  report.html written")
        except Exception as exc:
            print(f"  Warning: report.html failed: {exc}", file=sys.stderr)
        try:
            artifacts.write_token_report(run_dir, run_id, config, summary)
            print(f"  token_report.html written")
        except Exception as exc:
            print(f"  Warning: token_report.html failed: {exc}", file=sys.stderr)

    # Summary
    totals = summary["totals"]
    fmr_base = totals.get("field_match_rate_baseline")
    fmr_mem = totals.get("field_match_rate_final")
    imp = totals.get("improvement_rate")

    print()
    print(f"Results: {run_dir}")
    print(f"  Chats run:               {totals['run_count']}")
    print(f"  Baseline field-match:    {fmr_base:.3f}" if fmr_base is not None else "  Baseline field-match:    n/a")
    print(f"  Memory   field-match:    {fmr_mem:.3f}" if fmr_mem is not None else "  Memory   field-match:    n/a")
    if fmr_base is not None and fmr_mem is not None:
        print(f"  Delta (memory - base):   {fmr_mem - fmr_base:+.3f}")
    print(f"  Improvement rate:        {imp:.1%}" if imp is not None else "  Improvement rate:        n/a")

    if errors:
        print(f"\n  {len(errors)} chat(s) failed:", file=sys.stderr)
        for f, e in errors:
            print(f"    {f.stem}: {e}", file=sys.stderr)

    # Per-category breakdown
    categories = {}
    for row in summary.get("by_dataset", []):
        dsid = row.get("dataset_id", "")
        cat = dsid.replace("synthetic_", "")
        categories[cat] = row

    if len(categories) > 1:
        print()
        print("  By category:")
        for cat, row in sorted(categories.items()):
            b = row.get("field_match_rate_baseline")
            m_ = row.get("field_match_rate_final")
            d = (m_ - b) if b is not None and m_ is not None else None
            b_str = f"{b:.3f}" if b is not None else "n/a"
            m_str = f"{m_:.3f}" if m_ is not None else "n/a"
            d_str = f"{d:+.3f}" if d is not None else "n/a"
            print(f"    {cat:<20} baseline={b_str}  memory={m_str}  delta={d_str}")


if __name__ == "__main__":
    main()
