"""Helper to draft new entries for an agent's ``expected_results.py``.

Runs the selected agent on a single source path (or all sources for one
dataset), prints a Python literal block ready to paste into the agent's
``expected_results.py``, and shows a diff against the existing expected
entry (if any). No file is rewritten automatically — curation stays manual.

Usage examples:

    python -m harness.seed_expected --agent so_extraction \\
        --source raw_data/customers/acme_foods/chats/realistic_acme_foods_001.json

    python -m harness.seed_expected --agent so_extraction --dataset acme_foods \\
        --model sonnet-4-6 --runs 2
"""

from __future__ import annotations

import argparse
import json
import logging
import pprint
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.base import BaseAgent, RunOptions
from agents.config import load_config
from core.utils import DEFAULT_MODEL_KEY
from harness.scoring import normalize_contract_shape

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Draft expected_results entries for an agent.")
    p.add_argument("--agent", required=True, help="Agent id (e.g. so_extraction).")
    p.add_argument("--config", default="", help="Path to agents.json.")
    p.add_argument("--source", default="", help="Single source path (chat JSON).")
    p.add_argument("--dataset", default="", help="Dataset id to enumerate (when --source is omitted).")
    p.add_argument("--model", default=DEFAULT_MODEL_KEY, help="Model key used to draft the expected output.")
    p.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per source; the most-stable run (fewest mismatches, then fastest) wins.",
    )
    p.add_argument("--few-shot", nargs="*", default=[], help="Few-shot chat paths (capped at 10).")
    p.add_argument("--db-few-shot-limit", type=int, default=0)
    p.add_argument(
        "--include-only-missing",
        action="store_true",
        help="Skip sources that already have an expected entry.",
    )
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def _resolve_paths(values: list[str], root: Path) -> list[Path]:
    out: list[Path] = []
    for value in values:
        candidate = Path(value).expanduser()
        candidate = candidate if candidate.is_absolute() else (root / candidate)
        if candidate.exists():
            out.append(candidate.resolve())
        else:
            logger.warning("Path not found, skipping: %s", value)
    return out


def _best_run(agent: BaseAgent, source_path: Path, model_key: str, fs_paths: list[Path], runs: int, db_lim: int) -> dict[str, Any] | None:
    payload = agent.load_input(source_path)
    best: dict[str, Any] | None = None
    best_score: tuple[int, float] = (10**6, 10**6)
    for run_idx in range(1, max(1, runs) + 1):
        opts = RunOptions(
            model_key=model_key,
            few_shot_paths=list(fs_paths),
            extra={"db_few_shot_limit": db_lim},
        )
        result = agent.run_one(payload, opts)
        if not result.success or result.output_json is None:
            logger.warning(
                "Run %d failed for %s: %s", run_idx, source_path.name, result.error,
            )
            continue
        candidate = (result.score.mismatch_count, result.elapsed_sec)
        if candidate < best_score:
            best_score = candidate
            best = {
                "output": normalize_contract_shape(result.output_json) or result.output_json,
                "mismatch_count": result.score.mismatch_count,
                "compared_field_count": result.score.compared_field_count,
                "elapsed_sec": result.elapsed_sec,
            }
    return best


def _diff_dict(expected: Any, actual: Any, path: str = "") -> list[str]:
    diffs: list[str] = []
    if type(expected) is not type(actual):
        diffs.append(f"  {path}: type {type(expected).__name__} -> {type(actual).__name__}")
        return diffs
    if isinstance(expected, dict):
        keys = sorted(set(expected) | set(actual))
        for k in keys:
            if k not in expected:
                diffs.append(f"  + {path}.{k} = {actual[k]!r}")
            elif k not in actual:
                diffs.append(f"  - {path}.{k} (was {expected[k]!r})")
            else:
                diffs.extend(_diff_dict(expected[k], actual[k], f"{path}.{k}" if path else k))
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            diffs.append(f"  {path}: list len {len(expected)} -> {len(actual)}")
        for i, (e, a) in enumerate(zip(expected, actual)):
            diffs.extend(_diff_dict(e, a, f"{path}[{i}]"))
    else:
        if expected != actual:
            diffs.append(f"  {path}: {expected!r} -> {actual!r}")
    return diffs


def _emit_block(filename: str, value: Any) -> str:
    body = pprint.pformat(value, indent=4, width=100, sort_dicts=False)
    body = body.replace("\n", "\n    ")
    return f"    {filename!r}: {body},"


def main() -> None:
    args = _parse_args()
    cfg = load_config(args.config or None)
    agent = cfg.get_agent(args.agent)
    repo_root = agent.repo_root

    if args.source:
        sources: list[Path] = _resolve_paths([args.source], repo_root)
    elif args.dataset:
        ds = agent.get_dataset(args.dataset)
        sources = ds.expand(repo_root)
    else:
        sources = []
        for ds in agent.datasets():
            sources.extend(ds.expand(repo_root))

    if args.include_only_missing:
        sources = [p for p in sources if agent.expected_for(p) is None]

    if not sources:
        raise SystemExit("No sources matched. Pass --source, --dataset, or ensure expected entries are missing.")

    fs_paths = _resolve_paths(args.few_shot, repo_root)[:10]

    for source in sources:
        if not args.quiet:
            print(f"\n=== {source.name} ===", flush=True)
        outcome = _best_run(agent, source, args.model, fs_paths, args.runs, args.db_few_shot_limit)
        if outcome is None:
            print(f"  (all runs failed for {source.name})")
            continue

        new_value = outcome["output"]
        current = agent.expected_for(source)
        if current is not None:
            diffs = _diff_dict(current, new_value)
            if diffs:
                print("  diff vs current expected:")
                for line in diffs:
                    print(line)
            else:
                print("  (no diff vs current expected)")
        else:
            print("  (no existing expected entry)")

        print("  paste-into expected_results.EXPECTED_BY_CHAT:")
        print(_emit_block(source.name, new_value))


if __name__ == "__main__":
    main()
