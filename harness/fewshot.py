"""Few-shot planning helpers shared by the bulk runner and the dashboard.

These helpers intentionally avoid importing anything from the agents' runtime
backends (LLM clients, retry libraries, etc.) so the dashboard and unit tests
can use them with a minimal dependency footprint.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from agents.base import BaseAgent


def resolve_path_list(values: list[str], root: Path) -> list[Path]:
    """Resolve a list of (optionally relative) path strings, dropping missing ones.

    Missing paths emit a warning via the module logger and are silently skipped
    (mirrors the runner's ``_resolve_paths`` behaviour and keeps the
    dependency footprint of this module tiny).
    """
    import logging
    log = logging.getLogger(__name__)
    out: list[Path] = []
    for value in values:
        p = Path(value).expanduser()
        candidate = p if p.is_absolute() else (root / p)
        if candidate.exists():
            out.append(candidate.resolve())
        else:
            log.warning("Few-shot path not found, skipping: %s", value)
    return out


# Backwards-compatible alias for older internal callers.
_resolve_paths = resolve_path_list


def plan_few_shot_variants(
    agent: BaseAgent,
    *,
    explicit_paths: list[str] | None = None,
    walk_paths: list[str] | list[Path] | None = None,
    sweep_counts: list[int] | None = None,
    seed: int = 42,
    pool_override: list[Path] | None = None,
) -> list[tuple[str, int, list[Path]]]:
    """Return ``[(label, count, paths)]`` few-shot variants for a bulk run.

    Precedence (first match wins):

    1. ``explicit_paths``: a single ``("explicit", n, paths)`` variant
       capped at 10 entries.
    2. ``walk_paths``: a **deterministic walk** in user-picked order. If you
       pass ``[A, B, C]`` you get variants ``fs0=[]``, ``fs1=[A]``, ``fs2=[A,B]``,
       ``fs3=[A,B,C]``. No shuffling, no sampling — use this when you want to
       hand-pick which examples each variant uses and see how each one shifts
       the result. Capped at 10 paths (so at most ``fs0..fs10``).
    3. ``sweep_counts``: nested random sampling from the pool. The pool is
       shuffled once with ``seed``, then each count takes a *prefix* of that
       shuffled order. ``pool_override`` (optional) replaces the agent's pool.
    4. Otherwise: a single empty variant.

    The variants do not yet account for source-under-test self-exclusion; that
    happens at scheduling time in :func:`resolve_fewshot_for_source`.
    """
    if explicit_paths:
        explicit = resolve_path_list(explicit_paths, agent.repo_root)[:10]
        return [("explicit", len(explicit), explicit)]

    if walk_paths:
        resolved_walk: list[Path] = []
        seen_walk: set[Path] = set()
        for p in walk_paths:
            if isinstance(p, Path):
                if not p.exists():
                    import logging
                    logging.getLogger(__name__).warning("Walk path not found, skipping: %s", p)
                    continue
                resolved = p.resolve()
            else:
                # Reuse the same warn-and-skip logic as the rest of the module.
                rp = resolve_path_list([str(p)], agent.repo_root)
                if not rp:
                    continue
                resolved = rp[0]
            if resolved in seen_walk:
                continue
            seen_walk.add(resolved)
            resolved_walk.append(resolved)
        ordered = resolved_walk[:10]
        variants: list[tuple[str, int, list[Path]]] = []
        for count in range(len(ordered) + 1):
            variants.append((f"fs{count}", count, list(ordered[:count])))
        return variants

    if not sweep_counts:
        return [("none", 0, [])]

    pool: list[Path]
    if pool_override is not None:
        # Honour exactly what the caller curated; only de-dup while preserving order.
        seen: set[Path] = set()
        pool = []
        for p in pool_override:
            resolved = Path(p).resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            pool.append(resolved)
    else:
        pool = list(agent.few_shot_pool())
    unique_counts = sorted({max(0, min(10, c)) for c in sweep_counts})

    if not pool:
        return [(f"fs{c}", 0, []) for c in unique_counts]

    rng = random.Random(seed)
    shuffled = list(pool)
    rng.shuffle(shuffled)

    variants = []
    for count in unique_counts:
        effective = min(count, len(shuffled))
        variants.append((f"fs{count}", count, list(shuffled[:effective])))
    return variants


def resolve_fewshot_for_source(
    variant_paths: list[Path],
    source_path: Path,
    allow_self: bool,
) -> list[Path]:
    """Drop the source-under-test from a variant's path list unless allowed."""
    if allow_self:
        return list(variant_paths)
    resolved_source = source_path.resolve()
    return [p for p in variant_paths if p.resolve() != resolved_source]


def summarize_fewshot_variants(
    variants: list[tuple[str, int, list[Path]]],
    repo_root: Path,
) -> list[dict[str, Any]]:
    """Serializable description of every few-shot variant for config.json / stdout."""
    out: list[dict[str, Any]] = []
    for label, count, paths in variants:
        rel_paths: list[str] = []
        for p in paths:
            try:
                rel_paths.append(str(p.relative_to(repo_root)))
            except ValueError:
                rel_paths.append(str(p))
        out.append({"label": label, "count": count, "paths": rel_paths})
    return out


__all__ = [
    "plan_few_shot_variants",
    "resolve_fewshot_for_source",
    "summarize_fewshot_variants",
]
