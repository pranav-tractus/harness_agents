"""One-folder-per-run artifact pipeline.

Each bulk (or single) run lands in ``results/<run_id>/`` with four files:

- ``run.jsonl``      — append-only, one record per (agent, chat, run)
- ``aggregate.json`` — rollups by (model, strategy, fs_count, dataset, agent)
- ``report.html``    — single HTML report covering everything in the run
- ``config.json``    — full invocation config so dashboards can reload it

This module owns the writers; ``harness.runner`` owns the orchestration.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import AgentRunResult

RESULTS_DIR_DEFAULT = Path(__file__).resolve().parents[1] / "results"


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def make_run_dir(results_root: Path | None = None, run_id: str | None = None) -> tuple[Path, str]:
    rid = run_id or make_run_id()
    base = Path(results_root or RESULTS_DIR_DEFAULT).resolve()
    run_dir = base / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, rid


def record_to_row(rec: AgentRunResult) -> dict[str, Any]:
    """Flat dict representation suitable for jsonl + dashboards."""
    score = asdict(rec.score) if rec.score else {}
    return {
        "run_started_at_utc": rec.started_at_utc,
        "agent_id": rec.agent_id,
        "dataset_id": rec.dataset_id,
        "source_path": rec.source_path,
        "source_filename": Path(rec.source_path).name if rec.source_path else "",
        "success": rec.success,
        "status": rec.status,
        "attempts": rec.attempts,
        "elapsed_sec": rec.elapsed_sec,
        "error": rec.error,
        "model_key": rec.model_key,
        "model_provider": rec.model_provider,
        "few_shot_count": rec.few_shot_count,
        "few_shot_paths": rec.few_shot_paths,
        "pipeline_step": rec.pipeline_step,
        "flow_stage_ms": rec.flow_stage_ms,
        "output_json": rec.output_json,
        "score": score,
        "expected_available": score.get("expected_available", False),
        "mismatch_count": score.get("mismatch_count", 0),
        "compared_field_count": score.get("compared_field_count", 0),
        "metrics": score.get("metrics", {}),
        "mismatches": score.get("mismatches", []),
    }


def write_config(run_dir: Path, config: dict[str, Any]) -> Path:
    path = run_dir / "config.json"
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def append_record(run_dir: Path, rec: AgentRunResult) -> None:
    path = run_dir / "run.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record_to_row(rec), ensure_ascii=False) + "\n")
        fh.flush()


def aggregate(records: list[AgentRunResult]) -> dict[str, Any]:
    """Compute combo / chat / dataset / fs_count / agent summaries."""
    rows = [record_to_row(r) for r in records]

    def _safe_avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _bucket(key_fn) -> dict[tuple, list[dict[str, Any]]]:
        buckets: dict[tuple, list[dict[str, Any]]] = {}
        for r in rows:
            buckets.setdefault(key_fn(r), []).append(r)
        return buckets

    def _summarize(rows_in: list[dict[str, Any]]) -> dict[str, Any]:
        with_expected = [r for r in rows_in if r["expected_available"]]
        total_mismatch = sum(r["mismatch_count"] for r in with_expected)
        total_compared = sum(r["compared_field_count"] for r in with_expected)
        return {
            "run_count": len(rows_in),
            "success_rate": sum(1 for r in rows_in if r["success"]) / len(rows_in) if rows_in else 0.0,
            "avg_attempts": _safe_avg([r["attempts"] for r in rows_in]),
            "avg_elapsed_sec": _safe_avg([r["elapsed_sec"] for r in rows_in]),
            "avg_mismatch_per_expected_run": (
                total_mismatch / len(with_expected) if with_expected else None
            ),
            "field_match_rate": (
                1 - (total_mismatch / max(total_compared, 1))
                if with_expected else None
            ),
        }

    combo_buckets = _bucket(lambda r: (r["agent_id"], r["model_key"], r["few_shot_count"]))
    combo_summary = [
        {
            "agent_id": key[0],
            "model_key": key[1],
            "few_shot_count": key[2],
            **_summarize(rows_in),
        }
        for key, rows_in in sorted(combo_buckets.items())
    ]

    chat_buckets = _bucket(lambda r: (r["agent_id"], r["source_filename"], r["model_key"], r["few_shot_count"]))
    chat_summary = [
        {
            "agent_id": key[0],
            "chat_filename": key[1],
            "model_key": key[2],
            "few_shot_count": key[3],
            **_summarize(rows_in),
        }
        for key, rows_in in sorted(chat_buckets.items())
    ]

    dataset_buckets = _bucket(lambda r: (r["agent_id"], r["dataset_id"]))
    dataset_summary = [
        {"agent_id": key[0], "dataset_id": key[1], **_summarize(rows_in)}
        for key, rows_in in sorted(dataset_buckets.items())
    ]

    agent_buckets = _bucket(lambda r: r["agent_id"])
    agent_summary = [
        {"agent_id": key, **_summarize(rows_in)}
        for key, rows_in in sorted(agent_buckets.items())
    ]

    fs_buckets = _bucket(lambda r: (r["agent_id"], r["few_shot_count"]))
    fs_summary = [
        {"agent_id": key[0], "few_shot_count": key[1], **_summarize(rows_in)}
        for key, rows_in in sorted(fs_buckets.items())
    ]

    return {
        "totals": _summarize(rows),
        "by_combo": combo_summary,
        "by_chat": chat_summary,
        "by_dataset": dataset_summary,
        "by_agent": agent_summary,
        "by_few_shot_count": fs_summary,
    }


def write_aggregate(run_dir: Path, run_id: str, summary: dict[str, Any], config: dict[str, Any]) -> Path:
    payload = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "summary": summary,
        "artifacts": {
            "run_jsonl": str(run_dir / "run.jsonl"),
            "config_json": str(run_dir / "config.json"),
            "report_html": str(run_dir / "report.html"),
        },
    }
    path = run_dir / "aggregate.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def render_report_html(
    run_dir: Path,
    run_id: str,
    config: dict[str, Any],
    summary: dict[str, Any],
    records: list[AgentRunResult],
    *,
    generate_llm_story: bool = True,
    story_model_key: str = "sonnet-4-5",
) -> str:
    """Single-page dashboard report (see ``harness/report_dashboard_html.py``)."""
    from harness.report_dashboard_html import dashboard_generated_timestamp, render_dashboard_report_html
    from harness.report_summary import DEFAULT_VISUAL_STORY_MODEL, summarize_visual_story_safe
    from harness.results_brief import brief_from_run_dir

    mk = story_model_key or DEFAULT_VISUAL_STORY_MODEL
    brief = brief_from_run_dir(run_dir)
    story = summarize_visual_story_safe(
        brief,
        summary,
        config,
        model_key=mk,
        use_llm=generate_llm_story,
    )
    return render_dashboard_report_html(
        run_id,
        dashboard_generated_timestamp(),
        config,
        summary,
        records,
        story,
    )


def write_report(
    run_dir: Path,
    run_id: str,
    config: dict[str, Any],
    summary: dict[str, Any],
    records: list[AgentRunResult],
    *,
    generate_llm_story: bool = True,
    story_model_key: str = "sonnet-4-5",
) -> Path:
    path = run_dir / "report.html"
    path.write_text(
        render_report_html(
            run_dir,
            run_id,
            config,
            summary,
            records,
            generate_llm_story=generate_llm_story,
            story_model_key=story_model_key,
        ),
        encoding="utf-8",
    )
    return path
