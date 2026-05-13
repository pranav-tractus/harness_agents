"""Token-light briefs for harness results (dashboard + LLM summaries).

Builds headline metrics and the Agent+Model+FS leaderboard from slimmed
``run.jsonl``-shaped dicts, matching the Streamlit Results Browser math.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

# If a run has more combo rows than this, only the worst-N by mismatch are sent
# to the LLM (see ``maybe_truncate_leaderboard``).
_MAX_LEADERBOARD_ROWS = 50


def _safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _safe_std(values: list[int]) -> float | None:
    if not values:
        return None
    return pstdev(values) if len(values) > 1 else 0.0


def slim_record(r: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky fields; keep enough for metrics and leaderboard."""
    keys = (
        "agent_id",
        "model_key",
        "few_shot_count",
        "dataset_id",
        "source_filename",
        "success",
        "elapsed_sec",
        "expected_available",
        "mismatch_count",
        "compared_field_count",
        "pipeline_step",
        "_run_dir",
    )
    out: dict[str, Any] = {}
    for k in keys:
        if k in r:
            out[k] = r[k]
    if "few_shot_count" not in out:
        out["few_shot_count"] = r.get("few_shot_count", 0)
    return out


def headline_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Match Results Browser: Runs, success rate, avg elapsed, mismatch stdev."""
    if not records:
        return {
            "runs": 0,
            "success_rate": None,
            "avg_runtime_sec": None,
            "mismatch_stdev": None,
        }
    success_rate = sum(1 for r in records if r.get("success")) / len(records)
    elapsed = [float(r["elapsed_sec"]) for r in records]
    mismatches = [int(r["mismatch_count"]) for r in records if r.get("expected_available")]
    return {
        "runs": len(records),
        "success_rate": success_rate,
        "avg_runtime_sec": _safe_mean(elapsed),
        "mismatch_stdev": _safe_std(mismatches),
    }


def leaderboard_by_combo(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same aggregation as ``dashboard/app.py`` Results Browser leaderboard."""
    by_combo: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for r in records:
        key = (r["agent_id"], r["model_key"], int(r.get("few_shot_count", 0)))
        by_combo.setdefault(key, []).append(r)
    rows: list[dict[str, Any]] = []
    for (agent_id, model_key, fs_count), xs in sorted(by_combo.items()):
        with_expected = [x for x in xs if x.get("expected_available")]
        total_mismatch = sum(x["mismatch_count"] for x in with_expected)
        total_compared = sum(x["compared_field_count"] for x in with_expected)
        rows.append(
            {
                "agent": agent_id,
                "model": model_key,
                "fs_count": fs_count,
                "runs": len(xs),
                "success_rate": sum(1 for x in xs if x["success"]) / len(xs),
                "avg_elapsed_sec": _safe_mean([float(x["elapsed_sec"]) for x in xs]),
                "avg_mismatch_per_expected_run": (
                    total_mismatch / len(with_expected) if with_expected else None
                ),
                "field_match_rate": (
                    1 - (total_mismatch / max(total_compared, 1)) if with_expected else None
                ),
            }
        )
    return rows


def maybe_truncate_leaderboard(
    rows: list[dict[str, Any]],
    max_rows: int = _MAX_LEADERBOARD_ROWS,
) -> tuple[list[dict[str, Any]], bool, int]:
    """If too many combo rows, keep the worst half by mismatch for the LLM."""
    if len(rows) <= max_rows:
        return rows, False, len(rows)

    def sort_key(r: dict[str, Any]) -> float:
        m = r.get("avg_mismatch_per_expected_run")
        if m is None:
            return -1.0
        return float(m)

    worst_first = sorted(rows, key=sort_key, reverse=True)
    truncated = worst_first[:max_rows]
    return truncated, True, len(rows)


def _load_jsonl_slim(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.is_file():
        return out
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(slim_record(json.loads(line)))
    return out


def _aggregate_row_to_leaderboard_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": r["agent_id"],
        "model": r["model_key"],
        "fs_count": int(r.get("few_shot_count", 0)),
        "runs": int(r["run_count"]),
        "success_rate": float(r["success_rate"]),
        "avg_elapsed_sec": float(r["avg_elapsed_sec"]) if r.get("avg_elapsed_sec") is not None else None,
        "avg_mismatch_per_expected_run": (
            float(r["avg_mismatch_per_expected_run"])
            if r.get("avg_mismatch_per_expected_run") is not None
            else None
        ),
        "field_match_rate": (
            float(r["field_match_rate"]) if r.get("field_match_rate") is not None else None
        ),
    }


def brief_from_run_dir(run_dir: Path) -> dict[str, Any]:
    """Full-run brief: totals from aggregate, stdev from slim jsonl, leaderboard from aggregate."""
    run_dir = run_dir.resolve()
    agg_path = run_dir / "aggregate.json"
    if not agg_path.is_file():
        raise FileNotFoundError(f"No aggregate.json in {run_dir}")

    aggregate = json.loads(agg_path.read_text(encoding="utf-8"))
    summary = aggregate.get("summary") or {}
    totals = summary.get("totals") or {}

    slim_rows = _load_jsonl_slim(run_dir / "run.jsonl")
    stdev_metrics = headline_metrics(slim_rows)

    raw_leaderboard = [
        _aggregate_row_to_leaderboard_row(r) for r in summary.get("by_combo") or []
    ]
    lb, truncated, total_combos = maybe_truncate_leaderboard(raw_leaderboard)

    return {
        "kind": "single_run_dir",
        "run_id": aggregate.get("run_id"),
        "run_dir": str(run_dir),
        "config_excerpt": _config_excerpt(aggregate.get("config") or {}),
        "totals_from_aggregate": {
            "run_count": totals.get("run_count"),
            "success_rate": totals.get("success_rate"),
            "avg_elapsed_sec": totals.get("avg_elapsed_sec"),
            "avg_mismatch_per_expected_run": totals.get("avg_mismatch_per_expected_run"),
            "field_match_rate": totals.get("field_match_rate"),
        },
        "headlines_from_jsonl": {
            "runs": stdev_metrics["runs"],
            "success_rate": stdev_metrics["success_rate"],
            "avg_runtime_sec": stdev_metrics["avg_runtime_sec"],
            "mismatch_stdev": stdev_metrics["mismatch_stdev"],
            "note": (
                "Mismatch stdev is population stdev of per-run mismatch_count over rows "
                "with expected_available=true (same as Results Browser)."
            ),
        },
        "leaderboard_agent_model_fs": lb,
        "leaderboard_truncated": truncated,
        "leaderboard_total_combos": total_combos,
    }


def _config_excerpt(cfg: dict[str, Any]) -> dict[str, Any]:
    """Small config slice for LLM context (avoid huge paths)."""
    keys = (
        "agent",
        "pipeline",
        "models",
        "datasets",
        "bulk",
        "runs_per_chat",
        "max_workers",
        "skip_without_expected",
    )
    return {k: cfg[k] for k in keys if k in cfg}


def brief_from_slim_records(
    records: list[dict[str, Any]],
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dashboard filtered selection: same tables as the UI."""
    slim = [slim_record(r) for r in records]
    headlines = headline_metrics(slim)
    raw_lb = leaderboard_by_combo(slim)
    lb, truncated, total_combos = maybe_truncate_leaderboard(raw_lb)
    return {
        "kind": "filtered_records",
        "meta": meta or {},
        "headlines": headlines,
        "leaderboard_agent_model_fs": lb,
        "leaderboard_truncated": truncated,
        "leaderboard_total_combos": total_combos,
    }


__all__ = [
    "slim_record",
    "headline_metrics",
    "leaderboard_by_combo",
    "maybe_truncate_leaderboard",
    "brief_from_run_dir",
    "brief_from_slim_records",
]
