"""Unified single + bulk + pipeline runner.

Replaces ``tests/benchmark_fewshot.py`` and ``tests/run_benchmark_variants.py``.

A single CLI handles:

- one chat against one agent (``--agent <id> --chat <path>``)
- a pipeline against one chat (``--pipeline <id> --chat <path>``)
- a bulk sweep over (model x few-shot count x chat x run) (``--bulk``)

Every invocation produces one folder under ``results/<run_id>/`` containing
``run.jsonl``, ``aggregate.json``, ``report.html``, and ``config.json``.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.base import AgentRunResult, BaseAgent, Pipeline, RunOptions
from agents.config import HarnessConfig, load_config
from agents.so_extraction.agent import ChatInput
from agents.product_retrieval.agent import SummaryInput
from core.utils import DEFAULT_MODEL_KEY, MODEL_CATALOG
from harness import artifacts

logger = logging.getLogger(__name__)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)


CHECKPOINT_EVERY_N_RUNS = 10


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Unified harness runner: single or bulk runs over an agent or pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--config", type=str, default="", help="Path to agents.json (defaults to configs/agents.json).")
    p.add_argument("--agent", type=str, default="", help="Agent id to run (mutually exclusive with --pipeline).")
    p.add_argument("--pipeline", type=str, default="", help="Pipeline id to run.")
    p.add_argument("--chat", type=str, default="", help="Single source path (chat JSON for the first agent).")
    p.add_argument("--datasets", nargs="*", default=[], help="Restrict bulk runs to these dataset ids.")
    p.add_argument("--chats-glob", type=str, default="", help="Glob (relative to repo root) selecting bulk source paths.")
    p.add_argument("--bulk", action="store_true", help="Run all chats discovered via datasets/chats-glob.")
    p.add_argument("--models", nargs="*", default=[], help="Model keys; default is [sonnet-4-6].")
    p.add_argument("--runs-per-chat", type=int, default=1)
    p.add_argument("--max-workers", type=int, default=8)
    p.add_argument("--few-shot", nargs="*", default=[], help="Explicit few-shot chat paths (capped at 10).")
    p.add_argument("--few-shot-sweep", nargs="*", type=int, default=[], help="Sweep over few-shot counts (e.g. 0 1 3 5 10).")
    p.add_argument("--few-shot-seed", type=int, default=42, help="Deterministic seed for few-shot sampling during sweeps.")
    p.add_argument("--db-few-shot-limit", type=int, default=0, help="How many DB-backed few-shot examples to include per run.")
    p.add_argument("--results-root", type=str, default="", help="Override results/ root.")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--skip-without-expected", action="store_true")
    return p.parse_args()


def _resolve_paths(values: list[str], root: Path) -> list[Path]:
    out: list[Path] = []
    for value in values:
        p = Path(value).expanduser()
        candidate = p if p.is_absolute() else (root / p)
        if candidate.exists():
            out.append(candidate.resolve())
        else:
            logger.warning("Path not found, skipping: %s", value)
    return out


def _dataset_for_path(agent: BaseAgent, path: Path) -> str:
    resolved = path.resolve()
    for ds in agent.datasets():
        for candidate in ds.expand(agent.repo_root):
            if candidate == resolved:
                return ds.id
    return "default"


def _gather_source_paths(
    agent: BaseAgent,
    args: argparse.Namespace,
) -> list[tuple[str, Path]]:
    """Return ``[(dataset_id, source_path)]`` for the requested scope."""
    selected: list[tuple[str, Path]] = []

    if args.chat and not args.bulk:
        for path in _resolve_paths([args.chat], agent.repo_root):
            selected.append((_dataset_for_path(agent, path), path))
    elif args.chats_glob:
        for path in sorted(agent.repo_root.glob(args.chats_glob)):
            if path.is_file():
                selected.append((_dataset_for_path(agent, path), path.resolve()))
    else:
        for ds in agent.datasets():
            if args.datasets and ds.id not in args.datasets:
                continue
            for path in ds.expand(agent.repo_root):
                selected.append((ds.id, path))

    if args.skip_without_expected:
        selected = [(ds_id, p) for ds_id, p in selected if agent.expected_for(p) is not None]

    seen: set[Path] = set()
    deduped: list[tuple[str, Path]] = []
    for ds_id, p in selected:
        if p in seen:
            continue
        seen.add(p)
        deduped.append((ds_id, p))
    return deduped


def _models(args: argparse.Namespace) -> list[str]:
    if not args.models:
        return [DEFAULT_MODEL_KEY]
    invalid = [m for m in args.models if m not in MODEL_CATALOG]
    if invalid:
        raise SystemExit(f"Unknown model keys: {invalid}. Available: {sorted(MODEL_CATALOG.keys())}")
    return list(dict.fromkeys(args.models))


def _few_shot_plan(
    agent: BaseAgent,
    args: argparse.Namespace,
) -> list[list[Path]]:
    """Return one or more candidate few-shot path lists (cap 10 each)."""
    if args.few_shot:
        explicit = _resolve_paths(args.few_shot, agent.repo_root)[:10]
        return [explicit]
    if args.few_shot_sweep:
        pool = agent.few_shot_pool()
        if not pool:
            return [[]]
        rng = random.Random(args.few_shot_seed)
        unique_counts = sorted({max(0, min(10, c)) for c in args.few_shot_sweep})
        plans: list[list[Path]] = []
        for count in unique_counts:
            if count == 0:
                plans.append([])
                continue
            sample = pool if count >= len(pool) else rng.sample(pool, count)
            plans.append(list(sample))
        return plans
    return [[]]


def _runtime_payload_for(agent: BaseAgent, source_path: Path) -> Any:
    """Pre-load the agent's input payload (used outside the worker for caching)."""
    return agent.load_input(source_path)


def _run_case(
    agent: BaseAgent,
    payload: Any,
    options: RunOptions,
    run_index: int,
) -> AgentRunResult:
    result = agent.run_one(payload, options)
    # Stamp run index onto flow stage map for downstream filtering.
    result.flow_stage_ms = {**(result.flow_stage_ms or {}), "run_index": run_index}
    return result


def _run_bulk(
    agent: BaseAgent,
    args: argparse.Namespace,
    run_dir: Path,
    run_id: str,
    config: dict[str, Any],
) -> list[AgentRunResult]:
    sources = _gather_source_paths(agent, args)
    if not sources:
        raise SystemExit("No source paths matched. Check --datasets / --chats-glob / --chat.")
    fs_plans = _few_shot_plan(agent, args)
    models = _models(args)
    total = len(sources) * len(fs_plans) * len(models) * max(1, args.runs_per_chat)
    if not args.quiet:
        print(
            f"Bulk run: agent={agent.id} sources={len(sources)} models={len(models)} "
            f"fs_plans={len(fs_plans)} runs_per_chat={args.runs_per_chat} total={total}",
            flush=True,
        )

    cached_payloads: dict[Path, Any] = {}
    records: list[AgentRunResult] = []
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
        futures = []
        for dataset_id, source_path in sources:
            payload = cached_payloads.setdefault(source_path, _runtime_payload_for(agent, source_path))
            for model_key in models:
                for fs_paths in fs_plans:
                    for run_idx in range(1, max(1, args.runs_per_chat) + 1):
                        opts = RunOptions(
                            model_key=model_key,
                            few_shot_paths=list(fs_paths),
                            dataset_id=dataset_id,
                            extra={"db_few_shot_limit": args.db_few_shot_limit},
                        )
                        futures.append(
                            ex.submit(_run_case, agent, payload, opts, run_idx)
                        )

        for fut in as_completed(futures):
            rec = fut.result()
            records.append(rec)
            artifacts.append_record(run_dir, rec)
            completed += 1
            if not args.quiet:
                pct = (completed / total) * 100 if total else 100.0
                print(
                    f"[{completed}/{total} | {pct:5.1f}%] {rec.agent_id} | "
                    f"{rec.model_key} | fs={rec.few_shot_count} | {Path(rec.source_path).name} | "
                    f"status={rec.status} | elapsed={rec.elapsed_sec:.2f}s | "
                    f"mismatches={rec.score.mismatch_count}",
                    flush=True,
                )
            if completed % CHECKPOINT_EVERY_N_RUNS == 0 or completed == total:
                summary = artifacts.aggregate(records)
                artifacts.write_aggregate(run_dir, run_id, summary, config)
                artifacts.write_report(run_dir, run_id, config, summary, records)

    return records


def _run_pipeline(
    cfg: HarnessConfig,
    args: argparse.Namespace,
    run_dir: Path,
    run_id: str,
    config: dict[str, Any],
) -> list[AgentRunResult]:
    pipeline = cfg.build_pipeline(args.pipeline)
    primary = pipeline.agents[0]
    sources = _gather_source_paths(primary, args)
    if not sources:
        raise SystemExit("No source paths matched for pipeline.")
    fs_plans = _few_shot_plan(primary, args)
    models = _models(args)

    records: list[AgentRunResult] = []
    for dataset_id, source_path in sources:
        for model_key in models:
            for fs_paths in fs_plans:
                opts_per_step: list[RunOptions] = []
                for step_idx, agent in enumerate(pipeline.agents):
                    step_opts = RunOptions(
                        model_key=model_key,
                        few_shot_paths=list(fs_paths) if step_idx == 0 else [],
                        dataset_id=dataset_id if step_idx == 0 else None,
                        extra={"db_few_shot_limit": args.db_few_shot_limit if step_idx == 0 else 0},
                    )
                    opts_per_step.append(step_opts)
                step_results = pipeline.run(source_path, opts_per_step)
                for step_idx, rec in enumerate(step_results):
                    if step_idx > 0 and not rec.source_path:
                        rec.source_path = str(source_path)
                    records.append(rec)
                    artifacts.append_record(run_dir, rec)
                    if not args.quiet:
                        print(
                            f"[pipeline] step={step_idx} agent={rec.agent_id} "
                            f"status={rec.status} mismatches={rec.score.mismatch_count}",
                            flush=True,
                        )

    summary = artifacts.aggregate(records)
    artifacts.write_aggregate(run_dir, run_id, summary, config)
    artifacts.write_report(run_dir, run_id, config, summary, records)
    return records


def main() -> None:
    args = _parse_args()
    if not args.agent and not args.pipeline:
        raise SystemExit("Pass --agent <id> or --pipeline <id>.")
    if args.agent and args.pipeline:
        raise SystemExit("Pass either --agent or --pipeline, not both.")

    cfg = load_config(args.config or None)
    run_dir, run_id = artifacts.make_run_dir(
        results_root=Path(args.results_root).resolve() if args.results_root else None,
    )
    config_payload: dict[str, Any] = {
        "agent": args.agent or None,
        "pipeline": args.pipeline or None,
        "models": _models(args),
        "datasets": args.datasets,
        "chat": args.chat or None,
        "chats_glob": args.chats_glob or None,
        "bulk": bool(args.bulk),
        "runs_per_chat": args.runs_per_chat,
        "max_workers": args.max_workers,
        "few_shot_explicit": args.few_shot,
        "few_shot_sweep": args.few_shot_sweep,
        "few_shot_seed": args.few_shot_seed,
        "db_few_shot_limit": args.db_few_shot_limit,
        "skip_without_expected": bool(args.skip_without_expected),
        "results_dir": str(run_dir),
        "config_file": args.config or "configs/agents.json",
    }
    artifacts.write_config(run_dir, config_payload)

    if args.pipeline:
        records = _run_pipeline(cfg, args, run_dir, run_id, config_payload)
    else:
        agent = cfg.get_agent(args.agent)
        records = _run_bulk(agent, args, run_dir, run_id, config_payload)

    summary = artifacts.aggregate(records)
    artifacts.write_aggregate(run_dir, run_id, summary, config_payload)
    artifacts.write_report(run_dir, run_id, config_payload, summary, records)

    print(f"Run dir       : {run_dir}")
    print(f"Run JSONL     : {run_dir / 'run.jsonl'}")
    print(f"Aggregate JSON: {run_dir / 'aggregate.json'}")
    print(f"HTML report   : {run_dir / 'report.html'}")


__all__ = ["main", "_run_bulk", "_run_pipeline", "_few_shot_plan", "ChatInput", "SummaryInput"]


if __name__ == "__main__":
    main()
