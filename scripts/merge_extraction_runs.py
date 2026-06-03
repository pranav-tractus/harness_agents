#!/usr/bin/env python3
"""Merge two harness extraction runs into one results folder.

Typical use: combine a --with-baseline run (OpenAI + Bedrock) with a run that
added Anthropic API models, injecting Bedrock opus-4-6 baseline onto Anthropic
Opus rows that were collected without --with-baseline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agents.base import AgentRunResult, ScoreResult
from harness import artifacts

DEFAULT_EXCLUDE_MODELS = frozenset({"gemini:gemini-2.5-pro"})

MERGED_MODELS = [
    "sonnet-4-6",
    "opus-4-6",
    "anthropic:opus-4-7",
    "anthropic:opus-4-8",
    "openai:5.4",
    "openai:5.2",
]

FULL_BENCHMARK_DATASETS = [
    "core",
    "downloaded",
    "acme_foods",
    "nova_exports",
    "emails",
]


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _filter_models(
    rows: list[dict[str, Any]],
    exclude: frozenset[str],
) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("model_key") not in exclude]


def _score_from_dict(d: dict[str, Any] | None) -> ScoreResult:
    s = d or {}
    return ScoreResult(
        expected_available=bool(s.get("expected_available")),
        mismatch_count=int(s.get("mismatch_count") or 0),
        compared_field_count=int(s.get("compared_field_count") or 0),
        mismatches=list(s.get("mismatches") or []),
        metrics=dict(s.get("metrics") or {}),
    )


def _row_to_result(row: dict[str, Any]) -> AgentRunResult:
    token_usage = None
    if any(row.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")):
        token_usage = {
            "input_tokens": row.get("input_tokens", 0),
            "output_tokens": row.get("output_tokens", 0),
            "cache_read_tokens": row.get("cache_read_tokens", 0),
            "cache_write_tokens": row.get("cache_write_tokens", 0),
            "total_tokens": row.get("total_tokens", 0),
        }
    return AgentRunResult(
        agent_id=row["agent_id"],
        dataset_id=row["dataset_id"],
        source_path=row["source_path"],
        success=bool(row["success"]),
        status=row["status"],
        attempts=int(row["attempts"]),
        elapsed_sec=float(row["elapsed_sec"]),
        output_json=row.get("output_json"),
        raw_llm_output_json=row.get("raw_llm_output_json"),
        error=row.get("error"),
        model_key=row.get("model_key"),
        model_provider=row.get("model_provider"),
        validation_model_key=row.get("validation_model_key"),
        score=_score_from_dict(row.get("score")),
        score_raw_llm=_score_from_dict(row.get("score_raw_llm")),
        score_baseline=_score_from_dict(row.get("score_baseline")),
        baseline_output_json=row.get("baseline_output_json"),
        token_usage=token_usage,
        extraction_diagnostics=row.get("extraction_diagnostics"),
        flow_stage_ms=dict(row.get("flow_stage_ms") or {}),
        few_shot_paths=list(row.get("few_shot_paths") or []),
        few_shot_count=int(row.get("few_shot_count") or 0),
        pipeline_step=int(row.get("pipeline_step") or 0),
        started_at_utc=row.get("run_started_at_utc") or "",
    )


def _opus46_baseline_by_source(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("model_key") == "opus-4-6" and row.get("baseline_available"):
            out[row["source_path"]] = row
    return out


def _inject_opus46_baseline(
    row: dict[str, Any],
    baseline_row: dict[str, Any],
) -> dict[str, Any]:
    """Stamp opus-4-6 baseline onto an Anthropic Opus row; return flat jsonl row."""
    patched = dict(row)
    patched["baseline_output_json"] = baseline_row.get("baseline_output_json")
    patched["score_baseline"] = dict(baseline_row.get("score_baseline") or {})
    rec = _row_to_result(patched)
    return artifacts.record_to_row(rec)


def merge_rows(
    primary_rows: list[dict[str, Any]],
    supplemental_rows: list[dict[str, Any]],
    *,
    anthropic_models: set[str],
    exclude_models: frozenset[str],
) -> list[dict[str, Any]]:
    primary_rows = _filter_models(primary_rows, exclude_models)
    supplemental_rows = _filter_models(supplemental_rows, exclude_models)
    baseline_lookup = _opus46_baseline_by_source(primary_rows)
    merged: list[dict[str, Any]] = list(primary_rows)

    for row in supplemental_rows:
        model = row.get("model_key")
        if model not in anthropic_models:
            continue
        base = baseline_lookup.get(row["source_path"])
        if base is None:
            raise KeyError(
                f"No opus-4-6 baseline for source_path={row['source_path']!r} "
                f"(model={model})"
            )
        merged.append(_inject_opus46_baseline(row, base))

    def sort_key(r: dict[str, Any]) -> tuple:
        try:
            mi = MERGED_MODELS.index(r.get("model_key", ""))
        except ValueError:
            mi = 99
        return (mi, r.get("source_filename", ""), r.get("model_key", ""))

    merged.sort(key=sort_key)
    return merged


def _merged_config(
    primary_cfg: dict[str, Any],
    *,
    run_id: str,
    results_dir: Path,
    merged_from: list[str],
) -> dict[str, Any]:
    cfg = dict(primary_cfg)
    cfg["models"] = list(MERGED_MODELS)
    cfg["datasets"] = list(FULL_BENCHMARK_DATASETS)
    cfg["with_baseline"] = True
    cfg["report_style"] = "pitch"
    cfg["results_dir"] = str(results_dir)
    cfg["merged_from"] = merged_from
    cfg["baseline_policy"] = (
        "Per-model baseline from primary run; "
        "anthropic:opus-4-7 and anthropic:opus-4-8 use opus-4-6 baseline_output_json "
        "from primary run (same source_path)."
    )
    return cfg


def run_merge(
    primary_dir: Path,
    supplemental_dir: Path,
    *,
    out_root: Path,
    anthropic_models: set[str],
    exclude_models: frozenset[str] = DEFAULT_EXCLUDE_MODELS,
    run_id: str | None = None,
) -> Path:
    primary_dir = primary_dir.resolve()
    supplemental_dir = supplemental_dir.resolve()
    rid = run_id or artifacts.make_run_id()
    run_dir = out_root.resolve() / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    primary_rows = _load_rows(primary_dir / "run.jsonl")
    supplemental_rows = _load_rows(supplemental_dir / "run.jsonl")
    merged_rows = merge_rows(
        primary_rows,
        supplemental_rows,
        anthropic_models=anthropic_models,
        exclude_models=exclude_models,
    )

    primary_cfg = json.loads((primary_dir / "config.json").read_text(encoding="utf-8"))
    config = _merged_config(
        primary_cfg,
        run_id=rid,
        results_dir=run_dir,
        merged_from=[primary_dir.name, supplemental_dir.name],
    )

    jsonl_path = run_dir / "run.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in merged_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    records = [_row_to_result(r) for r in merged_rows]
    summary = artifacts.aggregate(records)
    artifacts.write_config(run_dir, config)
    artifacts.write_aggregate(run_dir, rid, summary, config)
    artifacts.write_pitch_report(run_dir, rid, config, summary)
    artifacts.write_token_report(run_dir, rid, config, summary)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--primary",
        type=Path,
        required=True,
        help="Run dir with --with-baseline (e.g. 20260603T053802Z)",
    )
    parser.add_argument(
        "--supplemental",
        type=Path,
        required=True,
        help="Run dir with extra models (e.g. 20260603T051559Z)",
    )
    parser.add_argument(
        "--anthropic-models",
        default="anthropic:opus-4-7,anthropic:opus-4-8",
        help="Comma-separated model keys to take from supplemental run",
    )
    parser.add_argument("--out", type=Path, default=Path("results"))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    anthropic = {m.strip() for m in args.anthropic_models.split(",") if m.strip()}
    run_dir = run_merge(
        args.primary,
        args.supplemental,
        out_root=args.out,
        anthropic_models=anthropic,
        run_id=args.run_id,
    )
    n = sum(1 for _ in (run_dir / "run.jsonl").open())
    print(f"Merged run: {run_dir}")
    print(f"Records:    {n}")
    print(f"Report:     {run_dir / 'report.html'}")


if __name__ == "__main__":
    main()
