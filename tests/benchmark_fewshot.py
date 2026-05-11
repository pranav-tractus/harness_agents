"""Bulk benchmark runner for initial extraction few-shot strategies.

Usage:
    python tests/benchmark_fewshot.py --runs-per-chat 3 --max-workers 8
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import html
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from chat_loader import (
    build_extraction_few_shot_from_paths,
    labeled_raw_chat_paths,
    list_chat_files,
    load_chat_file,
)
from extractor import ExtractionEngine
from models import SOExtractContractList
from raw_data.expected_results import EXPECTED_BY_CHAT
from utils import MODEL_CATALOG
from harness_config import get_customer_context, load_harness_config


ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
DEFAULT_RUNS_PER_CHAT = 3
DEFAULT_MAX_WORKERS = 15
DEFAULT_OUTPUT_PREFIX = "multi_customer_fewshot_benchmark"
CHECKPOINT_EVERY_N_RUNS = 10
SCALAR_TYPES = (str, int, float, bool, type(None))

# Benchmark defaults that can be edited directly in this script.
# - FEW_SHOT_METHODS_IN_TEST controls which few-shot strategies run by default.
# - CHAT_FILES_FOR_TESTING controls which chat files are benchmarked by default.
#   Use raw chat filenames like "single_product_single_shipment_simple.json".
#   Keep this empty to include all discovered chats.
# - FEW_SHOT_EXAMPLE_LABELS controls which raw chat files are used for file-based few-shot.
#   Use labels from labeled_raw_chat_paths() like "[chats] foo.json".
#   Keep this empty to include all discovered raw few-shot files.
FEW_SHOT_METHODS_IN_TEST: list[str] = [
    # "db_only",
    "raw_only",
    # "db_plus_raw",
    "zero_shot",
]
CHAT_FILES_FOR_TESTING: list[str] = [
    # "01__2026-02-24__120363421131250401_g_us__e05574ec-b110-4554-9fc3-3abb4f9011a8.json",
    # "02__2026-02-09__120363426578757754_g_us__12a4f3a7-d506-4d32-ae06-3f76508c6abd.json",
    # "03__2026-01-30__120363403074656566_g_us__8f477a8f-2a60-4e0a-bf0e-8cc3cdf1dc9f.json",
    # "04__2026-01-29__120363408498669191_g_us__4b9c2faa-94dd-4236-abcc-398807051f21.json",
    # "05__2026-01-20__120363407382355715_g_us__12a4f3a7-d506-4d32-ae06-3f76508c6abd.json",
    # "06__2026-01-06__120363421131250401_g_us__e05574ec-b110-4554-9fc3-3abb4f9011a8.json",
    # "07__2025-12-23__120363403074656566_g_us__8f477a8f-2a60-4e0a-bf0e-8cc3cdf1dc9f.json",
    # "08__2025-09-29__120363403592950429_g_us__d586d853-694c-42f9-93be-bc7ba5b2110c.json",
    # "09__2025-09-29__120363403592950429_g_us__d586d853-694c-42f9-93be-bc7ba5b2110c.json",
    # "multiple_product_multiple_shipment_complex.json",
    "multiple_product_multiple_shipment_medium.json",
    "multiple_product_multiple_shipment_simple.json",
    "real_world_msgs_test_v1.json",
    "real_world_msgs_test_v2.json",
    "real_world_msgs_test_v3.json",
    "single_product_multiple_shipment_complex.json",
    "single_product_multiple_shipment_medium.json",
    "single_product_multiple_shipment_simple.json",
    "single_product_single_shipment_complex.json",
    "single_product_single_shipment_medium.json",
    # "single_product_single_shipment_simple.json",
]
FEW_SHOT_EXAMPLE_LABELS: list[str] = [
    "[chats] multiple_product_multiple_shipment_complex.json",
    # "[chats] multiple_product_multiple_shipment_medium.json",
    # "[chats] multiple_product_multiple_shipment_simple.json",
    # "[chats] real_world_msgs_test_v1.json",
    # "[chats] real_world_msgs_test_v2.json",
    # "[chats] real_world_msgs_test_v3.json",
    "[chats] single_product_multiple_shipment_complex.json",
    # "[chats] single_product_multiple_shipment_medium.json",
    # "[chats] single_product_multiple_shipment_simple.json",
    "[chats] single_product_single_shipment_complex.json",
    # "[chats] single_product_single_shipment_medium.json",
    # "[chats] single_product_single_shipment_simple.json",
    # "[downloaded_chats] 01__2026-02-24__120363421131250401_g_us__e05574ec-b110-4554-9fc3-3abb4f9011a8.json",
    # "[downloaded_chats] 02__2026-02-09__120363426578757754_g_us__12a4f3a7-d506-4d32-ae06-3f76508c6abd.json",
    # "[downloaded_chats] 03__2026-01-30__120363403074656566_g_us__8f477a8f-2a60-4e0a-bf0e-8cc3cdf1dc9f.json",
    # "[downloaded_chats] 04__2026-01-29__120363408498669191_g_us__4b9c2faa-94dd-4236-abcc-398807051f21.json",
    # "[downloaded_chats] 05__2026-01-20__120363407382355715_g_us__12a4f3a7-d506-4d32-ae06-3f76508c6abd.json",
    # "[downloaded_chats] 06__2026-01-06__120363421131250401_g_us__e05574ec-b110-4554-9fc3-3abb4f9011a8.json",
    # "[downloaded_chats] 07__2025-12-23__120363403074656566_g_us__8f477a8f-2a60-4e0a-bf0e-8cc3cdf1dc9f.json",
    # "[downloaded_chats] 08__2025-09-29__120363403592950429_g_us__d586d853-694c-42f9-93be-bc7ba5b2110c.json",
    # "[downloaded_chats] 09__2025-09-29__120363403592950429_g_us__d586d853-694c-42f9-93be-bc7ba5b2110c.json",
    # "[updates] update_add_shipping_address.json",
    # "[updates] update_change_payment_terms.json",
    "[updates] update_change_quantity.json",
    "[updates] update_change_unit_price.json",
    # "[updates] update_iterative_two_steps.json",
]


@dataclass
class BenchmarkRunRecord:
    run_id: str
    timestamp_utc: str
    model_key: str
    fewshot_strategy: str
    chat_filename: str
    chat_path: str
    run_index: int
    success: bool
    status: str
    attempts: int
    elapsed_sec: float
    expected_available: bool
    mismatch_count: int
    compared_field_count: int
    error: str | None
    output_json: dict[str, Any] | None
    mismatches: list[dict[str, Any]]
    customer_id: str = "default"
    flow_stage_ms: dict[str, float] | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark initial extraction few-shot strategies in bulk."
    )
    parser.add_argument("--runs-per-chat", type=int, default=DEFAULT_RUNS_PER_CHAT)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument(
        "--models",
        nargs="*",
        default=[],
        help="Optional subset of model keys from utils.MODEL_CATALOG",
    )
    parser.add_argument(
        "--fewshot-strategies",
        nargs="*",
        default=FEW_SHOT_METHODS_IN_TEST,
    )
    parser.add_argument(
        "--chat-names",
        nargs="*",
        default=CHAT_FILES_FOR_TESTING,
        help="Optional subset of chat JSON filenames.",
    )
    parser.add_argument(
        "--chat-glob",
        default="*.json",
        help="Filename glob filter applied after chat discovery.",
    )
    parser.add_argument(
        "--output-prefix",
        default=DEFAULT_OUTPUT_PREFIX,
        help="Artifact filename prefix under tests/artifacts.",
    )
    parser.add_argument(
        "--raw-fewshot-names",
        nargs="*",
        default=FEW_SHOT_EXAMPLE_LABELS,
        help="Optional subset of few-shot raw file labels from labeled_raw_chat_paths().",
    )
    parser.add_argument(
        "--skip-without-expected",
        action="store_true",
        help="Only run chats that exist in raw_data.expected_results.EXPECTED_BY_CHAT.",
    )
    parser.add_argument(
        "--update-expected",
        action="store_true",
        help="Rewrite expected_results.py entries for selected chats from benchmark outputs.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce live per-run logs; keep only final artifact paths.",
    )
    parser.add_argument(
        "--harness-config",
        type=str,
        default="",
        help="Optional JSON config for multi-customer benchmark mode.",
    )
    parser.add_argument(
        "--customers",
        nargs="*",
        default=[],
        help="Optional subset of customer ids from harness config.",
    )
    return parser.parse_args()


def _normalize_contract_shape(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("data"), list):
        return value
    if isinstance(value.get("items"), list):
        return {"data": [value]}
    return None


def _is_scalar_list(values: list[Any]) -> bool:
    return all(isinstance(x, SCALAR_TYPES) for x in values)


def _compare_recursive(
    expected: Any,
    actual: Any,
    path: str,
    mismatches: list[dict[str, Any]],
) -> int:
    compared_fields = 0
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            mismatches.append({"path": path, "expected": expected, "actual": actual})
            return 1
        for key, expected_val in expected.items():
            compared_fields += _compare_recursive(
                expected_val,
                actual.get(key),
                f"{path}.{key}" if path else key,
                mismatches,
            )
        return compared_fields

    if isinstance(expected, list):
        if _is_scalar_list(expected):
            compared_fields += 1
            if actual not in expected:
                mismatches.append(
                    {"path": path, "expected": expected, "actual": actual}
                )
            return compared_fields

        if not isinstance(actual, list):
            mismatches.append({"path": path, "expected": expected, "actual": actual})
            return compared_fields + 1

        compared_fields += 1
        if len(actual) != len(expected):
            mismatches.append(
                {
                    "path": path,
                    "expected_len": len(expected),
                    "actual_len": len(actual),
                }
            )
        loop_count = min(len(expected), len(actual))
        for idx in range(loop_count):
            compared_fields += _compare_recursive(
                expected[idx],
                actual[idx],
                f"{path}[{idx}]",
                mismatches,
            )
        return compared_fields

    compared_fields += 1
    if expected != actual:
        mismatches.append({"path": path, "expected": expected, "actual": actual})
    return compared_fields


def _score_against_expected(
    chat_filename: str,
    actual_output: dict[str, Any] | None,
) -> tuple[bool, int, int, list[dict[str, Any]]]:
    expected = EXPECTED_BY_CHAT.get(chat_filename)
    if expected is None:
        return False, 0, 0, []
    normalized_actual = (
        _normalize_contract_shape(actual_output) if actual_output else None
    )
    mismatches: list[dict[str, Any]] = []
    compared_fields = _compare_recursive(expected, normalized_actual, "", mismatches)
    return True, compared_fields, len(mismatches), mismatches


def _discover_chat_paths(args: argparse.Namespace, base_paths: list[Path] | None = None) -> list[Path]:
    chats = list(base_paths or [])
    if not chats:
        grouped = list_chat_files()
        chats = grouped.get("chats", []) + grouped.get("downloaded_chats", [])
    selected: list[Path] = []
    names_filter = set(args.chat_names or [])
    for path in chats:
        if not path.match(args.chat_glob):
            continue
        if names_filter and path.name not in names_filter:
            continue
        if args.skip_without_expected and path.name not in EXPECTED_BY_CHAT:
            continue
        selected.append(path)
    return sorted(selected)


def _resolve_raw_fewshot_paths(args: argparse.Namespace) -> list[Path]:
    label_map = dict(labeled_raw_chat_paths())
    if not args.raw_fewshot_names:
        return [label_map[label] for label in sorted(label_map.keys())]
    resolved: list[Path] = []
    for label in args.raw_fewshot_names:
        if label in label_map:
            resolved.append(label_map[label])
    return resolved


def _get_models(args: argparse.Namespace) -> list[str]:
    available = sorted(MODEL_CATALOG.keys())
    if not args.models:
        return available
    valid = [m for m in args.models if m in MODEL_CATALOG]
    if not valid:
        raise ValueError("No valid models selected.")
    return sorted(set(valid))


def _plan_strategy_context(
    strategy: str,
    raw_examples: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, int]:
    if strategy == "db_only":
        return None, 5
    if strategy == "raw_only":
        return raw_examples or None, 0
    if strategy == "db_plus_raw":
        return raw_examples or None, 5
    if strategy == "zero_shot":
        return None, 0
    raise ValueError(f"Unsupported strategy: {strategy}")


def _run_single_case(
    run_id: str,
    model_key: str,
    strategy: str,
    chat_path: Path,
    run_index: int,
    raw_examples: list[dict[str, Any]],
    customer_id: str = "default",
    db_path: Path | None = None,
) -> BenchmarkRunRecord:
    t0 = time.perf_counter()
    loaded = load_chat_file(chat_path)
    t_load = time.perf_counter()
    text = (loaded.get("text") or "").strip()
    engine = ExtractionEngine(model_key=model_key, db_path=db_path) if db_path else ExtractionEngine(model_key=model_key)
    extra_fs, db_lim = _plan_strategy_context(strategy, raw_examples)
    t_setup = time.perf_counter()

    started = time.perf_counter()
    result = engine.run(
        text, extra_few_shot_examples=extra_fs, db_few_shot_limit=db_lim
    )
    elapsed = time.perf_counter() - started
    t_done = time.perf_counter()

    output_json: dict[str, Any] | None = None
    if result.status == "success" and result.output_json:
        try:
            output_json = json.loads(result.output_json)
        except json.JSONDecodeError:
            output_json = None

    expected_available, compared_field_count, mismatch_count, mismatches = (
        _score_against_expected(
            chat_path.name,
            output_json,
        )
    )
    if not result.status == "success" and expected_available:
        mismatch_count += 1

    return BenchmarkRunRecord(
        run_id=run_id,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        model_key=model_key,
        fewshot_strategy=strategy,
        chat_filename=chat_path.name,
        chat_path=str(chat_path),
        run_index=run_index,
        success=result.status == "success",
        status=result.status,
        attempts=result.attempts,
        elapsed_sec=round(elapsed, 4),
        expected_available=expected_available,
        mismatch_count=mismatch_count,
        compared_field_count=compared_field_count,
        error=result.error,
        output_json=output_json,
        mismatches=mismatches,
        customer_id=customer_id,
        flow_stage_ms={
            "chat_load_ms": round((t_load - t0) * 1000, 3),
            "fewshot_plan_ms": round((t_setup - t_load) * 1000, 3),
            "model_run_ms": round((t_done - started) * 1000, 3),
            "total_case_ms": round((t_done - t0) * 1000, 3),
        },
    )


def _aggregate(records: list[BenchmarkRunRecord]) -> dict[str, Any]:
    combos: dict[tuple[str, str], list[BenchmarkRunRecord]] = {}
    for rec in records:
        combos.setdefault((rec.model_key, rec.fewshot_strategy), []).append(rec)

    combo_summary: list[dict[str, Any]] = []
    chat_summary: list[dict[str, Any]] = []

    for (model_key, strategy), rows in sorted(combos.items()):
        success_count = sum(1 for r in rows if r.success)
        with_expected = [r for r in rows if r.expected_available]
        total_mismatch = sum(r.mismatch_count for r in with_expected)
        total_compared = sum(r.compared_field_count for r in with_expected)
        combo_summary.append(
            {
                "model_key": model_key,
                "fewshot_strategy": strategy,
                "run_count": len(rows),
                "success_rate": success_count / len(rows) if rows else 0.0,
                "avg_attempts": sum(r.attempts for r in rows) / len(rows)
                if rows
                else 0.0,
                "avg_elapsed_sec": sum(r.elapsed_sec for r in rows) / len(rows)
                if rows
                else 0.0,
                "avg_mismatch_per_expected_run": (
                    total_mismatch / len(with_expected) if with_expected else None
                ),
                "field_match_rate": (
                    1 - (total_mismatch / max(total_compared, 1))
                    if with_expected
                    else None
                ),
            }
        )

    chat_groups: dict[tuple[str, str, str], list[BenchmarkRunRecord]] = {}
    for rec in records:
        key = (rec.chat_filename, rec.model_key, rec.fewshot_strategy)
        chat_groups.setdefault(key, []).append(rec)
    for key, rows in sorted(chat_groups.items()):
        chat_summary.append(
            {
                "chat_filename": key[0],
                "model_key": key[1],
                "fewshot_strategy": key[2],
                "run_count": len(rows),
                "success_rate": sum(r.success for r in rows) / len(rows),
                "avg_elapsed_sec": sum(r.elapsed_sec for r in rows) / len(rows),
                "mismatch_counts": [
                    r.mismatch_count for r in rows if r.expected_available
                ],
            }
        )

    return {"combo_summary": combo_summary, "chat_summary": chat_summary}


def _aggregate_by_customer(records: list[BenchmarkRunRecord]) -> list[dict[str, Any]]:
    buckets: dict[str, list[BenchmarkRunRecord]] = {}
    for rec in records:
        buckets.setdefault(rec.customer_id, []).append(rec)
    rows: list[dict[str, Any]] = []
    for customer_id, recs in sorted(buckets.items()):
        success_count = sum(1 for r in recs if r.success)
        mismatches = [r.mismatch_count for r in recs if r.expected_available]
        rows.append(
            {
                "customer_id": customer_id,
                "run_count": len(recs),
                "success_rate": success_count / len(recs) if recs else 0.0,
                "avg_elapsed_sec": (
                    sum(r.elapsed_sec for r in recs) / len(recs) if recs else 0.0
                ),
                "avg_mismatch_count": (
                    sum(mismatches) / len(mismatches) if mismatches else None
                ),
            }
        )
    return rows


def _rewrite_expected_results(selected_updates: dict[str, dict[str, Any]]) -> Path:
    out_path = Path(__file__).resolve().parents[1] / "raw_data" / "expected_results.py"
    from raw_data.expected_results import EXPECTED_BY_CHAT as existing

    merged = dict(existing)
    merged.update(selected_updates)
    content = (
        '"""\n'
        "Expected contract extraction results per chat file.\n"
        "Auto-updated by tests/benchmark_fewshot.py --update-expected.\n"
        '"""\n\n'
        f"EXPECTED_BY_CHAT = {json.dumps(merged, indent=4, ensure_ascii=False)}\n\n"
        "def get_expected_for_chat(chat_filename: str) -> dict | None:\n"
        '    """Return expected contract data for a chat file, or None if not defined."""\n'
        '    name = chat_filename if chat_filename.endswith(".json") else f"{chat_filename}.json"\n'
        "    return EXPECTED_BY_CHAT.get(name)\n"
    )
    out_path.write_text(content, encoding="utf-8")
    return out_path


def _build_expected_updates(
    records: list[BenchmarkRunRecord],
) -> dict[str, dict[str, Any]]:
    updates: dict[str, dict[str, Any]] = {}
    by_chat: dict[str, list[BenchmarkRunRecord]] = {}
    for rec in records:
        if rec.success and rec.output_json:
            by_chat.setdefault(rec.chat_filename, []).append(rec)
    for chat_name, rows in by_chat.items():
        best = sorted(
            rows, key=lambda r: (r.mismatch_count, r.elapsed_sec, r.run_index)
        )[0]
        normalized = _normalize_contract_shape(best.output_json)
        if normalized:
            schema_safe = SOExtractContractList.model_validate(normalized).model_dump(
                mode="python"
            )
            updates[chat_name] = schema_safe
    return updates


def _render_html_report(
    aggregate_payload: dict[str, Any], records: list[BenchmarkRunRecord]
) -> str:
    combo_rows = aggregate_payload["summary"]["combo_summary"]
    chat_rows = aggregate_payload["summary"]["chat_summary"]
    config = aggregate_payload["config"]
    run_id = aggregate_payload["run_id"]
    generated_at = aggregate_payload["generated_at_utc"]

    def _fmt(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    combo_table_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(row['model_key'])}</td>"
            f"<td>{html.escape(row['fewshot_strategy'])}</td>"
            f"<td>{row['run_count']}</td>"
            f"<td>{_fmt(row['success_rate'])}</td>"
            f"<td>{_fmt(row['avg_attempts'])}</td>"
            f"<td>{_fmt(row['avg_elapsed_sec'])}</td>"
            f"<td>{_fmt(row['avg_mismatch_per_expected_run'])}</td>"
            f"<td>{_fmt(row['field_match_rate'])}</td>"
            "</tr>"
        )
        for row in combo_rows
    )

    chat_table_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(row['chat_filename'])}</td>"
            f"<td>{html.escape(row['model_key'])}</td>"
            f"<td>{html.escape(row['fewshot_strategy'])}</td>"
            f"<td>{row['run_count']}</td>"
            f"<td>{_fmt(row['success_rate'])}</td>"
            f"<td>{_fmt(row['avg_elapsed_sec'])}</td>"
            f"<td>{html.escape(json.dumps(row['mismatch_counts']))}</td>"
            "</tr>"
        )
        for row in chat_rows
    )

    mismatched = [r for r in records if r.mismatch_count > 0]
    mismatch_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(r.chat_filename)}</td>"
            f"<td>{html.escape(r.model_key)}</td>"
            f"<td>{html.escape(r.fewshot_strategy)}</td>"
            f"<td>{r.run_index}</td>"
            f"<td>{r.mismatch_count}</td>"
            f"<td><pre>{html.escape(json.dumps(r.mismatches[:5], indent=2, ensure_ascii=False))}</pre></td>"
            "</tr>"
        )
        for r in sorted(
            mismatched,
            key=lambda x: (
                x.mismatch_count,
                x.chat_filename,
                x.model_key,
                x.fewshot_strategy,
            ),
            reverse=True,
        )[:100]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Few-shot Benchmark Report {html.escape(run_id)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; color: #1f2937; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .meta {{ margin-bottom: 16px; color: #4b5563; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; font-size: 13px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; text-align: left; }}
    th {{ background: #f3f4f6; }}
    pre {{ margin: 0; white-space: pre-wrap; }}
    .card {{ background: #f9fafb; border: 1px solid #e5e7eb; padding: 10px; margin-bottom: 16px; }}
  </style>
</head>
<body>
  <h1>Few-shot Benchmark Report</h1>
  <div class="meta">Run ID: <code>{html.escape(run_id)}</code> | Generated UTC: <code>{html.escape(generated_at)}</code></div>

  <div class="card">
    <h2>Configuration</h2>
    <pre>{html.escape(json.dumps(config, indent=2, ensure_ascii=False))}</pre>
  </div>

  <h2>Model + Strategy Summary</h2>
  <table>
    <thead>
      <tr>
        <th>Model</th><th>Strategy</th><th>Runs</th><th>Success rate</th><th>Avg attempts</th>
        <th>Avg elapsed (s)</th><th>Avg mismatch/expected run</th><th>Field match rate</th>
      </tr>
    </thead>
    <tbody>
      {combo_table_rows}
    </tbody>
  </table>

  <h2>Per-chat Breakdown</h2>
  <table>
    <thead>
      <tr>
        <th>Chat</th><th>Model</th><th>Strategy</th><th>Runs</th>
        <th>Success rate</th><th>Avg elapsed (s)</th><th>Mismatch counts</th>
      </tr>
    </thead>
    <tbody>
      {chat_table_rows}
    </tbody>
  </table>

  <h2>Top Mismatches (up to 100 runs)</h2>
  <table>
    <thead>
      <tr>
        <th>Chat</th><th>Model</th><th>Strategy</th><th>Run</th><th>Mismatch count</th><th>Sample mismatches</th>
      </tr>
    </thead>
    <tbody>
      {mismatch_rows}
    </tbody>
  </table>
</body>
</html>
"""


def _build_aggregate_payload(
    run_id: str,
    runs_path: Path,
    models: list[str],
    strategies: list[str],
    chats: list[Path],
    args: argparse.Namespace,
    raw_paths: list[Path],
    records: list[BenchmarkRunRecord],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "models": models,
            "fewshot_strategies": strategies,
            "chat_count": len(chats),
            "runs_per_chat": args.runs_per_chat,
            "max_workers": args.max_workers,
            "raw_fewshot_count": len(raw_paths),
            "raw_fewshot_labels_filter": args.raw_fewshot_names,
        },
        "artifacts": {"runs_jsonl": str(runs_path)},
        "summary": _aggregate(records),
        "customer_summary": _aggregate_by_customer(records),
    }


def _write_checkpoint_artifacts(
    aggregate_path: Path,
    html_path: Path,
    aggregate_payload: dict[str, Any],
    records: list[BenchmarkRunRecord],
) -> None:
    aggregate_path.write_text(
        json.dumps(aggregate_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    html_path.write_text(
        _render_html_report(aggregate_payload, records),
        encoding="utf-8",
    )


def main() -> None:
    args = _parse_args()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    models = _get_models(args)
    strategies = sorted(set(args.fewshot_strategies))
    customer_cases: list[dict[str, Any]] = []
    if args.harness_config:
        cfg = load_harness_config(args.harness_config)
        ids = set(args.customers or [c.id for c in cfg.customers])
        for customer in cfg.customers:
            if customer.id not in ids:
                continue
            ctx = get_customer_context(cfg, ROOT_DIR, customer.id)
            chat_paths = _discover_chat_paths(args, base_paths=ctx.expand_globs())
            if not chat_paths:
                continue
            raw_paths = [ROOT_DIR / p for p in customer.few_shot.paths if not Path(p).is_absolute()]
            raw_paths += [Path(p) for p in customer.few_shot.paths if Path(p).is_absolute()]
            raw_examples = build_extraction_few_shot_from_paths(raw_paths)
            customer_cases.append(
                {
                    "customer_id": customer.id,
                    "db_path": ctx.db_path,
                    "chats": chat_paths,
                    "raw_paths": raw_paths,
                    "raw_examples": raw_examples,
                }
            )
    else:
        chats = _discover_chat_paths(args)
        raw_paths = _resolve_raw_fewshot_paths(args)
        raw_examples = build_extraction_few_shot_from_paths(raw_paths)
        customer_cases.append(
            {
                "customer_id": "default",
                "db_path": None,
                "chats": chats,
                "raw_paths": raw_paths,
                "raw_examples": raw_examples,
            }
        )

    if not customer_cases:
        raise SystemExit("No chat files matched filters.")
    if args.runs_per_chat <= 0:
        raise SystemExit("--runs-per-chat must be >= 1")

    total_chat_count = sum(len(c["chats"]) for c in customer_cases)
    total_cases = len(models) * len(strategies) * total_chat_count * args.runs_per_chat
    if not args.quiet:
        print(
            "Starting benchmark: "
            f"models={len(models)} strategies={len(strategies)} chats={total_chat_count} "
            f"runs_per_chat={args.runs_per_chat} total_cases={total_cases} "
            f"max_workers={args.max_workers}",
            flush=True,
        )

    records: list[BenchmarkRunRecord] = []
    futures = []
    completed = 0
    runs_path = ARTIFACTS_DIR / f"{args.output_prefix}_{run_id}_runs.jsonl"
    aggregate_path = ARTIFACTS_DIR / f"{args.output_prefix}_{run_id}_aggregate.json"
    html_path = RESULTS_DIR / f"{args.output_prefix}_{run_id}.html"

    # Initialize run-level artifact immediately so consumers can tail it while running.
    runs_path.write_text("", encoding="utf-8")

    def _checkpoint() -> None:
        payload = _build_aggregate_payload(
            run_id=run_id,
            runs_path=runs_path,
            models=models,
            strategies=strategies,
            chats=[p for c in customer_cases for p in c["chats"]],
            args=args,
            raw_paths=[p for c in customer_cases for p in c["raw_paths"]],
            records=records,
        )
        _write_checkpoint_artifacts(aggregate_path, html_path, payload, records)

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        for customer_case in customer_cases:
            for model in models:
                for strategy in strategies:
                    for chat_path in customer_case["chats"]:
                        for run_idx in range(1, args.runs_per_chat + 1):
                            futures.append(
                                executor.submit(
                                    _run_single_case,
                                    run_id,
                                    model,
                                    strategy,
                                    chat_path,
                                    run_idx,
                                    customer_case["raw_examples"],
                                    customer_case["customer_id"],
                                    customer_case["db_path"],
                                )
                            )
        with runs_path.open("a", encoding="utf-8") as runs_fh:
            for fut in as_completed(futures):
                rec = fut.result()
                records.append(rec)
                runs_fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
                runs_fh.flush()

                completed += 1
                if not args.quiet:
                    pct = (completed / total_cases) * 100 if total_cases else 100.0
                    print(
                        f"[{completed}/{total_cases} | {pct:5.1f}%] "
                        f"{rec.customer_id} | {rec.model_key} | {rec.fewshot_strategy} | {rec.chat_filename} | "
                        f"run={rec.run_index} | status={rec.status} | "
                        f"attempts={rec.attempts} | elapsed={rec.elapsed_sec:.3f}s | "
                        f"mismatches={rec.mismatch_count}",
                        flush=True,
                    )
                if completed % CHECKPOINT_EVERY_N_RUNS == 0 or completed == total_cases:
                    _checkpoint()
                    if not args.quiet:
                        print(
                            f"Checkpoint artifacts refreshed at {completed}/{total_cases}",
                            flush=True,
                        )

    aggregate_payload = _build_aggregate_payload(
        run_id=run_id,
        runs_path=runs_path,
        models=models,
        strategies=strategies,
        chats=[p for c in customer_cases for p in c["chats"]],
        args=args,
        raw_paths=[p for c in customer_cases for p in c["raw_paths"]],
        records=records,
    )
    _write_checkpoint_artifacts(aggregate_path, html_path, aggregate_payload, records)

    if args.update_expected:
        updates = _build_expected_updates(records)
        updated_path = _rewrite_expected_results(updates)
        print(f"Updated expected results file: {updated_path}")

    print(f"Runs artifact: {runs_path}")
    print(f"Aggregate artifact: {aggregate_path}")
    print(f"HTML report: {html_path}")


if __name__ == "__main__":
    main()
