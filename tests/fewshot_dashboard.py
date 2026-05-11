"""Streamlit dashboard for few-shot benchmark artifacts.

Run:
    streamlit run tests/fewshot_dashboard.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import streamlit as st


ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


def _list_aggregate_files() -> list[Path]:
    if not ARTIFACTS_DIR.exists():
        return []
    return sorted(ARTIFACTS_DIR.glob("*_aggregate.json"), reverse=True)


def _load_records(jsonl_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _load_multi_aggregates(files: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_records: list[dict[str, Any]] = []
    loaded_aggregates: list[dict[str, Any]] = []
    for agg_path in files:
        aggregate = json.loads(agg_path.read_text(encoding="utf-8"))
        loaded_aggregates.append(aggregate)
        runs_path = Path(aggregate["artifacts"]["runs_jsonl"])
        for row in _load_records(runs_path):
            row["_aggregate_file"] = agg_path.name
            row["_run_id"] = aggregate.get("run_id")
            all_records.append(row)
    return loaded_aggregates, all_records


def _safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _safe_std(values: list[float]) -> float | None:
    return pstdev(values) if len(values) > 1 else 0.0 if len(values) == 1 else None


def _few_shot_count_from_record(record: dict[str, Any]) -> int | None:
    """Extract few-shot count from aggregate filename pattern like '_fs10'."""
    name = str(record.get("_aggregate_file", ""))
    m = re.search(r"_fs(\d+)", name)
    if not m:
        return None
    return int(m.group(1))


_REALISM_CACHE: dict[str, list[str]] = {}


def _realism_flags_for_chat(chat_path_str: str) -> list[str]:
    if chat_path_str in _REALISM_CACHE:
        return _REALISM_CACHE[chat_path_str]
    flags: list[str] = []
    try:
        data = json.loads(Path(chat_path_str).read_text(encoding="utf-8"))
        flags = sorted(set(data.get("realism_flags") or []))
    except (OSError, json.JSONDecodeError):
        flags = []
    _REALISM_CACHE[chat_path_str] = flags
    return flags


def _annotate_records_with_realism(records: list[dict[str, Any]]) -> None:
    for r in records:
        chat_path = str(r.get("chat_path") or "")
        r["_realism_flags"] = _realism_flags_for_chat(chat_path) if chat_path else []


def _summaries_from_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    combo_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in records:
        combo_groups.setdefault((r["model_key"], r["fewshot_strategy"]), []).append(r)

    combo_summary: list[dict[str, Any]] = []
    for (model, strategy), rows in sorted(combo_groups.items()):
        success_rate = sum(1 for x in rows if x.get("success")) / len(rows)
        avg_attempts = sum(float(x.get("attempts", 0)) for x in rows) / len(rows)
        avg_elapsed = sum(float(x.get("elapsed_sec", 0.0)) for x in rows) / len(rows)
        with_expected = [x for x in rows if x.get("expected_available")]
        mismatch_counts = [int(x.get("mismatch_count", 0)) for x in with_expected]
        compared_fields = [int(x.get("compared_field_count", 0)) for x in with_expected]
        total_mismatch = sum(mismatch_counts)
        total_compared = sum(compared_fields)
        combo_summary.append(
            {
                "model_key": model,
                "fewshot_strategy": strategy,
                "run_count": len(rows),
                "success_rate": success_rate,
                "avg_attempts": avg_attempts,
                "avg_elapsed_sec": avg_elapsed,
                "avg_mismatch_per_expected_run": (
                    total_mismatch / len(with_expected) if with_expected else None
                ),
                "field_match_rate": (
                    1 - (total_mismatch / max(total_compared, 1)) if with_expected else None
                ),
            }
        )

    chat_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in records:
        key = (r["chat_filename"], r["model_key"], r["fewshot_strategy"])
        chat_groups.setdefault(key, []).append(r)
    chat_summary: list[dict[str, Any]] = []
    for (chat, model, strategy), rows in sorted(chat_groups.items()):
        chat_summary.append(
            {
                "chat_filename": chat,
                "model_key": model,
                "fewshot_strategy": strategy,
                "run_count": len(rows),
                "success_rate": sum(1 for x in rows if x.get("success")) / len(rows),
                "avg_elapsed_sec": sum(float(x.get("elapsed_sec", 0.0)) for x in rows) / len(rows),
                "mismatch_counts": [
                    int(x.get("mismatch_count", 0))
                    for x in rows
                    if x.get("expected_available")
                ],
            }
        )
    return combo_summary, chat_summary


st.set_page_config(page_title="Few-shot Benchmark", layout="wide")
st.title("Few-shot Benchmark Dashboard")
st.caption("Model + strategy comparison for initial extraction in repeated parallel runs.")

agg_files = _list_aggregate_files()
if not agg_files:
    st.warning("No aggregate files found in tests/artifacts. Run benchmark first.")
    st.stop()

view_mode = st.radio(
    "View mode",
    ["Single aggregate", "Combine multiple aggregates"],
    horizontal=True,
)
if view_mode == "Single aggregate":
    selected_agg = st.selectbox("Aggregate artifact", agg_files, format_func=lambda p: p.name)
    aggregate = json.loads(selected_agg.read_text(encoding="utf-8"))
    runs_path = Path(aggregate["artifacts"]["runs_jsonl"])
    records = _load_records(runs_path)
    aggregate_list = [aggregate]
else:
    selected_aggs = st.multiselect(
        "Aggregate artifacts",
        agg_files,
        default=agg_files[: min(8, len(agg_files))],
        format_func=lambda p: p.name,
    )
    if not selected_aggs:
        st.info("Select one or more aggregate files.")
        st.stop()
    aggregate_list, records = _load_multi_aggregates(selected_aggs)
    aggregate = {
        "config": {
            "combined_aggregate_files": [p.name for p in selected_aggs],
            "combined_run_count": len(records),
        }
    }

st.subheader("Run Configuration")
st.json(aggregate["config"], expanded=False)
if aggregate.get("customer_summary"):
    st.subheader("Customer Summary")
    st.dataframe(aggregate["customer_summary"], use_container_width=True, hide_index=True)

if aggregate.get("summary"):
    combo_summary = aggregate["summary"]["combo_summary"]
    chat_summary = aggregate["summary"]["chat_summary"]
else:
    combo_summary, chat_summary = _summaries_from_records(records)

st.subheader("Model + Strategy Leaderboard")
st.dataframe(combo_summary, use_container_width=True, hide_index=True)

st.subheader("Per-chat Breakdown")
st.dataframe(chat_summary, use_container_width=True, hide_index=True)

st.subheader("Reliability, Runtime, and Variability")
_annotate_records_with_realism(records)
models = sorted({r["model_key"] for r in records})
customers = sorted({r.get("customer_id", "default") for r in records})
providers = sorted({str(r["model_key"]).split(":", 1)[0] if ":" in str(r["model_key"]) else "bedrock" for r in records})
strategies = sorted({r["fewshot_strategy"] for r in records})
chat_names = sorted({r["chat_filename"] for r in records})
realism_flag_universe = sorted({f for r in records for f in r.get("_realism_flags", [])})

col0, col1, col2, col3, col4 = st.columns(5)
selected_customers = col0.multiselect("Customers", customers, default=customers)
selected_providers = col1.multiselect("Providers", providers, default=providers)
selected_models = col2.multiselect("Models", models, default=models)
selected_strategies = col3.multiselect("Few-shot strategies", strategies, default=strategies)
selected_chats = col4.multiselect("Chats", chat_names, default=chat_names)
aggregate_names = sorted({r.get("_aggregate_file", "single") for r in records})
col_agg, col_realism, col_realism_mode = st.columns([2, 2, 1])
selected_aggregate_names = col_agg.multiselect(
    "Aggregate files (combined mode)",
    aggregate_names,
    default=aggregate_names,
)
selected_realism_flags = col_realism.multiselect(
    "Realism flags",
    realism_flag_universe,
    default=realism_flag_universe,
    help="Filter to chats containing any of these realism flags. Leave empty to include only chats with no realism flags.",
)
realism_match_mode = col_realism_mode.radio(
    "Realism match",
    ["any", "all"],
    horizontal=False,
    help="'any' = chat has at least one selected flag; 'all' = chat has every selected flag.",
)


def _passes_realism(record: dict[str, Any]) -> bool:
    flags = set(record.get("_realism_flags", []))
    if not realism_flag_universe:
        return True
    selected = set(selected_realism_flags)
    if not selected:
        return not flags
    if realism_match_mode == "all":
        return selected.issubset(flags)
    return bool(selected & flags)


filtered = [
    r
    for r in records
    if r.get("customer_id", "default") in selected_customers
    and ((str(r["model_key"]).split(":", 1)[0] if ":" in str(r["model_key"]) else "bedrock") in selected_providers)
    and r["model_key"] in selected_models
    and r["fewshot_strategy"] in selected_strategies
    and r["chat_filename"] in selected_chats
    and r.get("_aggregate_file", "single") in selected_aggregate_names
    and _passes_realism(r)
]

if not filtered:
    st.info("No runs match the current filters.")
    st.stop()

overall_success = sum(1 for r in filtered if r["success"]) / len(filtered)
elapsed = [float(r["elapsed_sec"]) for r in filtered]
mismatch = [int(r["mismatch_count"]) for r in filtered if r["expected_available"]]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Runs", len(filtered))
m2.metric("Success rate", f"{overall_success:.1%}")
m3.metric("Avg runtime (s)", f"{(_safe_mean(elapsed) or 0):.3f}")
m4.metric("Mismatch stdev", f"{(_safe_std(mismatch) or 0):.3f}")

st.subheader("Detailed Runs")
st.dataframe(
    [
        {
            "provider": str(r["model_key"]).split(":", 1)[0] if ":" in str(r["model_key"]) else "bedrock",
            "customer_id": r.get("customer_id", "default"),
            "model": r["model_key"],
            "strategy": r["fewshot_strategy"],
            "chat": r["chat_filename"],
            "realism_flags": ",".join(r.get("_realism_flags", [])),
            "aggregate_file": r.get("_aggregate_file", "single"),
            "run": r["run_index"],
            "success": r["success"],
            "attempts": r["attempts"],
            "elapsed_sec": r["elapsed_sec"],
            "mismatch_count": r["mismatch_count"],
            "compared_fields": r["compared_field_count"],
        }
        for r in filtered
    ],
    use_container_width=True,
    hide_index=True,
)

st.subheader("Realism Flag Breakdown")
realism_rows_present = any(r.get("_realism_flags") for r in filtered)
if not realism_rows_present:
    st.info(
        "No realism-flagged chats in the current selection. "
        "Run tests/generate_realistic_chats.py to add realistic scenarios."
    )
else:
    flag_buckets: dict[str, list[dict[str, Any]]] = {}
    no_flag_bucket: list[dict[str, Any]] = []
    for r in filtered:
        flags = r.get("_realism_flags") or []
        if not flags:
            no_flag_bucket.append(r)
            continue
        for flag in flags:
            flag_buckets.setdefault(flag, []).append(r)

    breakdown_rows: list[dict[str, Any]] = []
    for flag, rows in sorted(flag_buckets.items()):
        expected_rows = [x for x in rows if x.get("expected_available")]
        total_mismatch = sum(int(x.get("mismatch_count", 0)) for x in expected_rows)
        breakdown_rows.append(
            {
                "realism_flag": flag,
                "run_count": len(rows),
                "success_rate": sum(1 for x in rows if x.get("success")) / len(rows),
                "avg_attempts": sum(float(x.get("attempts", 0)) for x in rows) / len(rows),
                "avg_elapsed_sec": sum(float(x.get("elapsed_sec", 0.0)) for x in rows) / len(rows),
                "expected_run_count": len(expected_rows),
                "avg_mismatch_per_expected_run": (
                    total_mismatch / len(expected_rows) if expected_rows else None
                ),
            }
        )

    if no_flag_bucket:
        expected_rows = [x for x in no_flag_bucket if x.get("expected_available")]
        total_mismatch = sum(int(x.get("mismatch_count", 0)) for x in expected_rows)
        breakdown_rows.append(
            {
                "realism_flag": "(none)",
                "run_count": len(no_flag_bucket),
                "success_rate": sum(1 for x in no_flag_bucket if x.get("success")) / len(no_flag_bucket),
                "avg_attempts": sum(float(x.get("attempts", 0)) for x in no_flag_bucket) / len(no_flag_bucket),
                "avg_elapsed_sec": sum(float(x.get("elapsed_sec", 0.0)) for x in no_flag_bucket) / len(no_flag_bucket),
                "expected_run_count": len(expected_rows),
                "avg_mismatch_per_expected_run": (
                    total_mismatch / len(expected_rows) if expected_rows else None
                ),
            }
        )

    st.dataframe(breakdown_rows, use_container_width=True, hide_index=True)

    flag_only_rows = [x for x in breakdown_rows if x["realism_flag"] != "(none)"]
    if flag_only_rows:
        hardest = min(flag_only_rows, key=lambda x: x["success_rate"])
        easiest = max(flag_only_rows, key=lambda x: x["success_rate"])
        c1, c2 = st.columns(2)
        c1.metric(
            "Hardest realism flag (lowest success rate)",
            value=hardest["realism_flag"],
            delta=f"success_rate={hardest['success_rate']:.1%}",
        )
        c2.metric(
            "Easiest realism flag (highest success rate)",
            value=easiest["realism_flag"],
            delta=f"success_rate={easiest['success_rate']:.1%}",
        )

st.subheader("Mismatch Inspector")
mismatch_rows = [r for r in filtered if r["mismatches"]]
if not mismatch_rows:
    st.success("No mismatches found in current filtered runs.")
else:
    selected_row = st.selectbox(
        "Run with mismatches",
        mismatch_rows,
        format_func=lambda r: f"{r['model_key']} | {r['fewshot_strategy']} | {r['chat_filename']} | run {r['run_index']}",
    )
    st.json(selected_row["mismatches"])

st.subheader("Few-shot Count vs Mismatch")
fs_rows = [r for r in filtered if _few_shot_count_from_record(r) is not None]
if not fs_rows:
    st.info("Few-shot count breakdown unavailable (aggregate filenames do not include '_fsN').")
else:
    by_fs: dict[int, list[dict[str, Any]]] = {}
    for row in fs_rows:
        fs_count = _few_shot_count_from_record(row)
        if fs_count is None:
            continue
        by_fs.setdefault(fs_count, []).append(row)

    fs_summary: list[dict[str, Any]] = []
    for fs_count, rows in sorted(by_fs.items()):
        expected_rows = [x for x in rows if x.get("expected_available")]
        total_mismatch = sum(int(x.get("mismatch_count", 0)) for x in expected_rows)
        avg_mismatch = total_mismatch / len(expected_rows) if expected_rows else None
        fs_summary.append(
            {
                "fewshot_count": fs_count,
                "run_count": len(rows),
                "expected_run_count": len(expected_rows),
                "total_mismatch_count": total_mismatch,
                "avg_mismatch_per_expected_run": avg_mismatch,
            }
        )

    st.dataframe(fs_summary, use_container_width=True, hide_index=True)

    valid_rows = [x for x in fs_summary if x["expected_run_count"] > 0]
    if valid_rows:
        most = max(valid_rows, key=lambda x: x["total_mismatch_count"])
        least = min(valid_rows, key=lambda x: x["total_mismatch_count"])
        c1, c2 = st.columns(2)
        c1.metric(
            "Most mismatches (few-shot count)",
            value=str(most["fewshot_count"]),
            delta=f"total={most['total_mismatch_count']}",
        )
        c2.metric(
            "Least mismatches (few-shot count)",
            value=str(least["fewshot_count"]),
            delta=f"total={least['total_mismatch_count']}",
        )

st.subheader("Generation Flow Timeline")
flow_rows = []
for r in filtered:
    flow = r.get("flow_stage_ms") or {}
    flow_rows.append(
        {
            "customer_id": r.get("customer_id", "default"),
            "chat": r["chat_filename"],
            "model": r["model_key"],
            "strategy": r["fewshot_strategy"],
            "run": r["run_index"],
            "chat_load_ms": flow.get("chat_load_ms"),
            "fewshot_plan_ms": flow.get("fewshot_plan_ms"),
            "model_run_ms": flow.get("model_run_ms"),
            "total_case_ms": flow.get("total_case_ms"),
        }
    )
st.dataframe(flow_rows, use_container_width=True, hide_index=True)
