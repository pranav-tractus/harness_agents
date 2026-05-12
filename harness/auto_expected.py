"""Automatically generate and write expected_results entries for an agent.

This is the "apply" counterpart to :mod:`harness.seed_expected`:

- ``seed_expected``  prints paste-ready blocks + diffs and never touches disk.
- ``auto_expected``  runs the agent, picks the most-stable output per source,
  and rewrites the agent's ``expected_results.py`` in place so the
  ``EXPECTED_BY_CHAT`` dict gains/updates the chosen entries.

The rewrite is AST-based: we identify the ``EXPECTED_BY_CHAT = {...}`` assignment,
replace exactly that assignment's source range with a deterministically
formatted literal, and leave the module docstring + helper functions untouched.

Examples::

    # Add expected entries for every chat in a dataset that doesn't have one.
    python -m harness.auto_expected --agent so_extraction \\
        --dataset acme_foods --only-missing

    # Refresh a single chat (overwriting any existing entry), 3 runs deep.
    python -m harness.auto_expected --agent so_extraction \\
        --source raw_data/chats/single_product_single_shipment_simple.json \\
        --runs 3 --overwrite-existing

    # Show what would change without writing anything.
    python -m harness.auto_expected --agent so_extraction --all --dry-run

    # Seed from an existing benchmark artifact instead of re-running the LLM.
    python -m harness.auto_expected --agent so_extraction \\
        --from-jsonl results/<run_id>/run.jsonl --only-missing
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.base import BaseAgent, RunOptions
from agents.config import load_config
from core.utils import DEFAULT_MODEL_KEY
from harness.scoring import normalize_contract_shape

logger = logging.getLogger(__name__)

EXPECTED_DICT_NAME = "EXPECTED_BY_CHAT"


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run an agent and write its outputs into expected_results.py.",
    )
    p.add_argument("--agent", required=True, help="Agent id (e.g. so_extraction).")
    p.add_argument("--config", default="", help="Path to agents.json (defaults to configs/agents.json).")

    src = p.add_argument_group("source selection (pick one)")
    src.add_argument("--source", action="append", default=[], help="One or more chat paths (repeatable).")
    src.add_argument("--dataset", action="append", default=[], help="Dataset id(s) to enumerate.")
    src.add_argument("--all", action="store_true", help="Run every source across every dataset for this agent.")
    src.add_argument(
        "--from-jsonl",
        default="",
        help="Skip the LLM and use outputs from a prior run's run.jsonl artifact.",
    )

    run = p.add_argument_group("agent run options")
    run.add_argument("--model", default=DEFAULT_MODEL_KEY, help="Model key for fresh runs.")
    run.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Best-of-N: most-stable run per source wins (fewest mismatches, then fastest).",
    )
    run.add_argument("--few-shot", nargs="*", default=[], help="Up to 10 few-shot chat paths.")
    run.add_argument("--db-few-shot-limit", type=int, default=0)

    policy = p.add_argument_group("write policy")
    policy.add_argument(
        "--only-missing",
        action="store_true",
        help="Skip sources that already have an expected entry.",
    )
    policy.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Allow rewriting entries that differ from the new output.",
    )
    policy.add_argument(
        "--sort-keys",
        action="store_true",
        help="Sort EXPECTED_BY_CHAT alphabetically by filename when writing.",
    )
    policy.add_argument("--dry-run", action="store_true", help="Print the plan without writing the file.")
    policy.add_argument(
        "--backup",
        action="store_true",
        help="Copy the original file to <name>.py.bak before overwriting.",
    )
    policy.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def _resolve_paths(values: Iterable[str], root: Path) -> list[Path]:
    out: list[Path] = []
    for value in values:
        candidate = Path(value).expanduser()
        candidate = candidate if candidate.is_absolute() else (root / candidate)
        if candidate.exists():
            out.append(candidate.resolve())
        else:
            logger.warning("Path not found, skipping: %s", value)
    return out


def _collect_sources(agent: BaseAgent, args: argparse.Namespace) -> list[Path]:
    repo_root = agent.repo_root
    selected: list[Path] = []
    if args.source:
        selected.extend(_resolve_paths(args.source, repo_root))
    if args.dataset:
        for ds_id in args.dataset:
            for path in agent.get_dataset(ds_id).expand(repo_root):
                selected.append(path)
    if args.all or (not args.source and not args.dataset and not args.from_jsonl):
        for ds in agent.datasets():
            for path in ds.expand(repo_root):
                selected.append(path)
    # de-dup, preserve order
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in selected:
        resolved = Path(path).resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


# ---------------------------------------------------------------------------
# Run-time helpers
# ---------------------------------------------------------------------------


def _best_run(
    agent: BaseAgent,
    source_path: Path,
    model_key: str,
    fs_paths: list[Path],
    runs: int,
    db_lim: int,
) -> dict[str, Any] | None:
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
            logger.warning("Run %d failed for %s: %s", run_idx, source_path.name, result.error)
            continue
        candidate = (result.score.mismatch_count, result.elapsed_sec)
        if candidate < best_score:
            best_score = candidate
            best = {
                "output": result.output_json,
                "mismatch_count": result.score.mismatch_count,
                "elapsed_sec": result.elapsed_sec,
            }
    return best


def _outputs_from_jsonl(
    agent: BaseAgent,
    jsonl_path: Path,
    sources_filter: set[str] | None,
) -> dict[str, Any]:
    """Pick the best output per source from a benchmark run.jsonl artifact.

    Uses the same "fewest mismatches, then fastest" heuristic so the result
    matches what fresh ``--runs N`` would have selected.
    """
    if not jsonl_path.exists():
        raise SystemExit(f"--from-jsonl path not found: {jsonl_path}")
    per_source: dict[str, tuple[tuple[int, float], dict[str, Any]]] = {}
    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("agent_id") != agent.id:
                continue
            if not row.get("success") or row.get("output_json") is None:
                continue
            filename = row.get("source_filename") or Path(row.get("source_path", "")).name
            if not filename:
                continue
            if sources_filter is not None and filename not in sources_filter:
                continue
            score = row.get("score") or {}
            key = (int(score.get("mismatch_count", 0)), float(row.get("elapsed_sec", 0.0)))
            if filename not in per_source or key < per_source[filename][0]:
                per_source[filename] = (key, row["output_json"])
    return {fn: payload for fn, (_, payload) in per_source.items()}


# ---------------------------------------------------------------------------
# Deterministic Python-literal formatter
# ---------------------------------------------------------------------------


_INDENT = "    "


def format_python_literal(value: Any, indent_level: int = 0) -> str:
    """Render a JSON-ish Python literal as black-style source code.

    - Strings use double quotes (via :func:`json.dumps`).
    - Dicts preserve insertion order; one key per line with trailing commas.
    - Lists likewise one element per line.
    - Floats keep their fractional form (e.g. ``25.0`` stays ``25.0``).
    """
    pad = _INDENT * indent_level
    inner = _INDENT * (indent_level + 1)

    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int) and not isinstance(value, bool):
        return repr(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        if not value:
            return "{}"
        parts = ["{"]
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"Expected string keys, got {type(k).__name__}: {k!r}")
            parts.append(f"{inner}{json.dumps(k, ensure_ascii=False)}: {format_python_literal(v, indent_level + 1)},")
        parts.append(f"{pad}}}")
        return "\n".join(parts)
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        parts = ["["]
        for item in value:
            parts.append(f"{inner}{format_python_literal(item, indent_level + 1)},")
        parts.append(f"{pad}]")
        return "\n".join(parts)
    raise TypeError(f"Unsupported value of type {type(value).__name__}: {value!r}")


# ---------------------------------------------------------------------------
# AST-based file rewrite
# ---------------------------------------------------------------------------


def _find_assignment(tree: ast.Module, name: str) -> ast.Assign | ast.AnnAssign | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name and node.value is not None:
                return node
    return None


def load_expected_dict(path: Path) -> dict[str, Any]:
    """Read ``EXPECTED_BY_CHAT`` from an agent's expected_results.py without importing it.

    Uses :func:`ast.literal_eval` against the source segment so this helper
    has no side effects and tolerates partial / in-progress edits to other
    parts of the module.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = _find_assignment(tree, EXPECTED_DICT_NAME)
    if node is None:
        raise SystemExit(f"{path} does not define a top-level '{EXPECTED_DICT_NAME}' assignment.")
    value_node = node.value if isinstance(node, ast.Assign) else node.value  # type: ignore[union-attr]
    segment = ast.get_source_segment(src, value_node)
    if segment is None:
        raise SystemExit(f"Could not extract source segment for {EXPECTED_DICT_NAME} in {path}.")
    try:
        loaded = ast.literal_eval(segment)
    except (SyntaxError, ValueError) as exc:
        raise SystemExit(f"{EXPECTED_DICT_NAME} in {path} is not a Python literal: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SystemExit(f"{EXPECTED_DICT_NAME} in {path} must be a dict; got {type(loaded).__name__}.")
    return loaded


def rewrite_expected_file(path: Path, new_value: dict[str, Any]) -> str:
    """Return the new file contents with ``EXPECTED_BY_CHAT`` replaced.

    Preserves the module docstring, imports, helper functions, and any
    comments/spacing outside the assignment itself. Does not write to disk.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = _find_assignment(tree, EXPECTED_DICT_NAME)
    if node is None:
        raise SystemExit(f"{path} does not define a top-level '{EXPECTED_DICT_NAME}' assignment.")

    formatted = format_python_literal(new_value, indent_level=0)

    if isinstance(node, ast.AnnAssign):
        annotation = ast.get_source_segment(src, node.annotation) or ""
        new_assign = f"{EXPECTED_DICT_NAME}: {annotation} = {formatted}"
    else:
        new_assign = f"{EXPECTED_DICT_NAME} = {formatted}"

    lines = src.splitlines(keepends=True)
    start_idx = node.lineno - 1  # 0-indexed first line of the assignment
    end_idx = node.end_lineno     # 0-indexed line *after* the assignment
    prefix = "".join(lines[:start_idx])
    suffix = "".join(lines[end_idx:])
    # Re-attach a trailing newline to the assignment if the rest of the file expects one
    if not new_assign.endswith("\n"):
        new_assign += "\n"
    return prefix + new_assign + suffix


# ---------------------------------------------------------------------------
# Diff helpers (lightweight; full diff lives in seed_expected.py)
# ---------------------------------------------------------------------------


def _summarize_diff(current: Any, new: Any) -> str:
    if current is None:
        return "new"
    if current == new:
        return "unchanged"
    return "changed"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _collect_new_entries(
    agent: BaseAgent,
    sources: list[Path],
    args: argparse.Namespace,
    fs_paths: list[Path],
) -> dict[str, Any]:
    new_entries: dict[str, Any] = {}
    if args.from_jsonl:
        jsonl_path = Path(args.from_jsonl).expanduser()
        if not jsonl_path.is_absolute():
            jsonl_path = (agent.repo_root / jsonl_path).resolve()
        allowed = {p.name for p in sources} if sources else None
        from_jsonl = _outputs_from_jsonl(agent, jsonl_path, allowed)
        for filename, payload in from_jsonl.items():
            normalized = normalize_contract_shape(payload) or payload
            new_entries[filename] = agent.expected_from_output(normalized)
        if not new_entries:
            print(f"No usable outputs for agent={agent.id} in {jsonl_path}.")
        return new_entries

    if not sources:
        raise SystemExit("No sources matched. Use --source, --dataset, --all, or --from-jsonl.")

    for source in sources:
        outcome = _best_run(
            agent=agent,
            source_path=source,
            model_key=args.model,
            fs_paths=fs_paths,
            runs=args.runs,
            db_lim=args.db_few_shot_limit,
        )
        if outcome is None:
            print(f"  ! all {args.runs} run(s) failed for {source.name}; skipping")
            continue
        raw = outcome["output"]
        normalized = normalize_contract_shape(raw) or raw
        new_entries[source.name] = agent.expected_from_output(normalized)
    return new_entries


def _apply_policy(
    current: dict[str, Any],
    new_entries: dict[str, Any],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    actions: list[tuple[str, str]] = []  # (filename, action) where action ∈ {new, replace, skip:*}
    merged: dict[str, Any] = dict(current)
    for filename, value in new_entries.items():
        if filename in current:
            if args.only_missing:
                actions.append((filename, "skip:only-missing"))
                continue
            if current[filename] == value:
                actions.append((filename, "skip:unchanged"))
                continue
            if not args.overwrite_existing:
                actions.append((filename, "skip:exists"))
                continue
            merged[filename] = value
            actions.append((filename, "replace"))
        else:
            merged[filename] = value
            actions.append((filename, "new"))
    if args.sort_keys:
        merged = dict(sorted(merged.items()))
    return merged, actions


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    cfg = load_config(args.config or None)
    agent = cfg.get_agent(args.agent)
    expected_path = agent.expected_results_path()
    if expected_path is None:
        raise SystemExit(
            f"Agent '{agent.id}' does not expose an expected_results.py file (override expected_results_path)."
        )

    fs_paths = _resolve_paths(args.few_shot, agent.repo_root)[:10]
    sources = _collect_sources(agent, args)

    if not args.quiet:
        print(f"Agent           : {agent.id}")
        print(f"Expected file   : {expected_path.relative_to(agent.repo_root)}")
        if args.from_jsonl:
            scope = f"all entries in {args.from_jsonl}" if not sources else f"{len(sources)} source filter(s)"
            print(f"Mode            : from-jsonl ({scope})")
        else:
            print(f"Mode            : fresh runs (best-of-{args.runs})")
            print(f"Sources matched : {len(sources)}")
        print()

    new_entries = _collect_new_entries(agent, sources, args, fs_paths)
    if not new_entries:
        print("Nothing to write.")
        return 0

    current = load_expected_dict(expected_path)
    merged, actions = _apply_policy(current, new_entries, args)

    counts: dict[str, int] = defaultdict(int)
    for _, action in actions:
        counts[action] += 1

    if not args.quiet:
        print("Planned changes:")
        for filename, action in actions:
            print(f"  [{action:>20s}] {filename}")
        print()
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"Summary: {summary or '<no-op>'}")

    will_change = counts.get("new", 0) + counts.get("replace", 0)
    if will_change == 0:
        if not args.quiet:
            print("No file changes required.")
        return 0

    if args.dry_run:
        print(f"\n(dry-run) would update {will_change} entries in {expected_path}")
        return 0

    new_src = rewrite_expected_file(expected_path, merged)

    # Sanity check: the rewritten file must still parse and round-trip.
    try:
        ast.parse(new_src)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise SystemExit(f"Refusing to write: generated file does not parse ({exc}).")

    if args.backup:
        backup = expected_path.with_suffix(".py.bak")
        shutil.copy2(expected_path, backup)
        if not args.quiet:
            print(f"Backup written  : {backup}")

    expected_path.write_text(new_src, encoding="utf-8")
    if not args.quiet:
        print(f"Wrote {will_change} entries to {expected_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
