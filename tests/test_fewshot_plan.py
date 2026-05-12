"""Tests for the bulk-run few-shot planning helpers.

Covers:
- nested sampling (count=2 paths ⊂ count=5 ⊂ count=10)
- deterministic seed
- 0-count and over-cap behaviour
- explicit-paths override path
- source-under-test self-exclusion
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.base import BaseAgent, Dataset
from harness.fewshot import (
    plan_few_shot_variants,
    resolve_fewshot_for_source,
    summarize_fewshot_variants,
)


class _StubAgent(BaseAgent):
    """Minimal agent whose few-shot pool is a fixed list of paths."""

    input_type = object
    output_type = object

    def __init__(self, pool: list[Path]) -> None:
        super().__init__(
            id="stub",
            display_name="stub",
            datasets=[Dataset(id="default", globs=())],
            few_shot_globs=(),
            repo_root=Path("."),
        )
        self._pool = list(pool)

    def few_shot_pool(self) -> list[Path]:
        return list(self._pool)

    def load_input(self, source_path):  # type: ignore[override]
        return source_path

    def run_one(self, input_payload, options):  # type: ignore[override]
        raise NotImplementedError

    def expected_for(self, source_path):  # type: ignore[override]
        return None

    def score(self, expected, actual):  # type: ignore[override]
        from agents.base import ScoreResult
        return ScoreResult()


def _pool(n: int, tmp: Path) -> list[Path]:
    return [tmp / f"chat_{i:03d}.json" for i in range(n)]


class PlanFewShotVariantsTests(unittest.TestCase):
    def test_nested_prefix_property(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent = _StubAgent(_pool(20, tmp))
            variants = plan_few_shot_variants(agent, sweep_counts=[2, 5, 10], seed=42)
            labels = [label for label, _, _ in variants]
            self.assertEqual(labels, ["fs2", "fs5", "fs10"])
            samples = {label: paths for label, _, paths in variants}
            self.assertEqual(len(samples["fs2"]), 2)
            self.assertEqual(len(samples["fs5"]), 5)
            self.assertEqual(len(samples["fs10"]), 10)
            # Nested: smaller-count list must be a prefix of larger-count list.
            self.assertEqual(samples["fs5"][: 2], samples["fs2"])
            self.assertEqual(samples["fs10"][: 5], samples["fs5"])

    def test_seed_is_deterministic(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent = _StubAgent(_pool(20, tmp))
            a = plan_few_shot_variants(agent, sweep_counts=[3], seed=7)
            b = plan_few_shot_variants(agent, sweep_counts=[3], seed=7)
            c = plan_few_shot_variants(agent, sweep_counts=[3], seed=99)
            self.assertEqual([p.name for _, _, paths in a for p in paths],
                             [p.name for _, _, paths in b for p in paths])
            self.assertNotEqual([p.name for _, _, paths in a for p in paths],
                                [p.name for _, _, paths in c for p in paths])

    def test_zero_count_is_empty_variant(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent = _StubAgent(_pool(5, tmp))
            variants = plan_few_shot_variants(agent, sweep_counts=[0, 2], seed=1)
            self.assertEqual(variants[0][2], [])
            self.assertEqual(len(variants[1][2]), 2)

    def test_count_clamped_to_pool_size_and_cap(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent = _StubAgent(_pool(3, tmp))
            variants = plan_few_shot_variants(agent, sweep_counts=[10], seed=1)
            label, count, paths = variants[0]
            self.assertEqual(label, "fs10")
            self.assertEqual(count, 10)
            # Pool only has 3 items, so the actual paths cap at 3.
            self.assertEqual(len(paths), 3)

    def test_explicit_paths_override_sweep(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            existing = tmp / "real.json"
            existing.write_text("{}", encoding="utf-8")
            agent = _StubAgent(_pool(5, tmp))
            variants = plan_few_shot_variants(
                agent,
                explicit_paths=[str(existing)],
                sweep_counts=[3],
                seed=1,
            )
            self.assertEqual(len(variants), 1)
            label, count, paths = variants[0]
            self.assertEqual(label, "explicit")
            self.assertEqual(count, 1)
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].name, "real.json")

    def test_empty_pool_returns_empty_variants(self) -> None:
        agent = _StubAgent([])
        variants = plan_few_shot_variants(agent, sweep_counts=[1, 5], seed=1)
        labels = [label for label, *_ in variants]
        self.assertEqual(labels, ["fs1", "fs5"])
        for _, _, paths in variants:
            self.assertEqual(paths, [])

    def test_no_sweep_no_explicit_returns_none_variant(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent = _StubAgent(_pool(5, tmp))
            variants = plan_few_shot_variants(agent)
            self.assertEqual(len(variants), 1)
            label, count, paths = variants[0]
            self.assertEqual((label, count, paths), ("none", 0, []))

    def test_pool_override_replaces_agent_pool(self) -> None:
        """When the caller passes a curated pool, the agent's default pool is ignored."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent_pool = _pool(20, tmp)
            agent = _StubAgent(agent_pool)
            # Curated subset that does NOT overlap by index range with the agent's pool order.
            curated = [tmp / "curated_a.json", tmp / "curated_b.json", tmp / "curated_c.json"]
            variants = plan_few_shot_variants(
                agent,
                sweep_counts=[1, 2, 3],
                seed=42,
                pool_override=curated,
            )
            sampled_names: set[str] = set()
            for _label, _count, paths in variants:
                for p in paths:
                    sampled_names.add(p.name)
            # All sampled names must come from the curated list, none from the agent's pool.
            self.assertTrue(sampled_names.issubset({"curated_a.json", "curated_b.json", "curated_c.json"}))
            self.assertEqual(sampled_names, {p.name for p in curated})

    def test_pool_override_preserves_nested_prefix_property(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent = _StubAgent(_pool(0, tmp))  # agent pool is empty; only override is used
            curated = [tmp / f"x_{i}.json" for i in range(8)]
            variants = plan_few_shot_variants(
                agent,
                sweep_counts=[2, 4, 6],
                seed=7,
                pool_override=curated,
            )
            sets = {label: paths for label, _, paths in variants}
            self.assertEqual(sets["fs4"][:2], sets["fs2"])
            self.assertEqual(sets["fs6"][:4], sets["fs4"])

    def test_pool_override_shorter_than_count_caps_to_pool(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent = _StubAgent(_pool(50, tmp))
            curated = [tmp / "only_a.json", tmp / "only_b.json"]
            variants = plan_few_shot_variants(
                agent,
                sweep_counts=[5],
                seed=42,
                pool_override=curated,
            )
            label, requested, paths = variants[0]
            self.assertEqual(label, "fs5")
            self.assertEqual(requested, 5)
            # Effective sample capped at the curated pool size (2).
            self.assertEqual(len(paths), 2)
            self.assertEqual({p.name for p in paths}, {"only_a.json", "only_b.json"})

    def test_pool_override_dedupes_while_preserving_order(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent = _StubAgent(_pool(5, tmp))
            duplicate = tmp / "dup.json"
            curated = [duplicate, duplicate, tmp / "other.json", duplicate]
            variants = plan_few_shot_variants(
                agent,
                sweep_counts=[10],
                seed=42,
                pool_override=curated,
            )
            _, _, paths = variants[0]
            self.assertEqual(len(paths), 2)
            self.assertEqual({p.name for p in paths}, {"dup.json", "other.json"})


class ResolveFewShotForSourceTests(unittest.TestCase):
    def test_excludes_source_under_test(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            a = tmp / "a.json"
            b = tmp / "b.json"
            c = tmp / "c.json"
            for p in (a, b, c):
                p.write_text("{}", encoding="utf-8")
            filtered = resolve_fewshot_for_source([a, b, c], source_path=b, allow_self=False)
            self.assertEqual([p.name for p in filtered], ["a.json", "c.json"])

    def test_allow_self_keeps_it(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            a = tmp / "a.json"
            b = tmp / "b.json"
            for p in (a, b):
                p.write_text("{}", encoding="utf-8")
            filtered = resolve_fewshot_for_source([a, b], source_path=b, allow_self=True)
            self.assertEqual([p.name for p in filtered], ["a.json", "b.json"])


class SummarizeFewShotVariantsTests(unittest.TestCase):
    def test_paths_made_relative_to_repo(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            paths = [tmp / "a.json", tmp / "sub" / "b.json"]
            (tmp / "sub").mkdir(exist_ok=True)
            variants = [("explicit", 2, paths)]
            summary = summarize_fewshot_variants(variants, repo_root=tmp)
            self.assertEqual(summary, [
                {"label": "explicit", "count": 2, "paths": ["a.json", "sub/b.json"]},
            ])


class WalkPathsTests(unittest.TestCase):
    """The deterministic 0..N walk over user-picked chats."""

    def _make_files(self, tmp: Path, n: int) -> list[Path]:
        files = []
        for i in range(n):
            p = tmp / f"pick_{i:02d}.json"
            p.write_text("{}", encoding="utf-8")
            files.append(p)
        return files

    def test_walk_produces_fs0_through_fsN_in_order(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            files = self._make_files(tmp, 3)
            agent = _StubAgent(_pool(20, tmp))
            variants = plan_few_shot_variants(agent, walk_paths=files)
            labels = [label for label, _, _ in variants]
            self.assertEqual(labels, ["fs0", "fs1", "fs2", "fs3"])
            self.assertEqual(variants[0][2], [])
            self.assertEqual([p.name for p in variants[1][2]], ["pick_00.json"])
            self.assertEqual([p.name for p in variants[2][2]], ["pick_00.json", "pick_01.json"])
            self.assertEqual(
                [p.name for p in variants[3][2]],
                ["pick_00.json", "pick_01.json", "pick_02.json"],
            )

    def test_walk_preserves_user_order_exactly(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            files = self._make_files(tmp, 5)
            # User-picked order on purpose: reversed.
            picked = list(reversed(files))
            agent = _StubAgent(_pool(20, tmp))
            variants = plan_few_shot_variants(agent, walk_paths=picked)
            self.assertEqual(
                [p.name for p in variants[-1][2]],
                ["pick_04.json", "pick_03.json", "pick_02.json", "pick_01.json", "pick_00.json"],
            )

    def test_walk_is_capped_at_10_paths(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            files = self._make_files(tmp, 15)
            agent = _StubAgent(_pool(0, tmp))
            variants = plan_few_shot_variants(agent, walk_paths=files)
            labels = [label for label, _, _ in variants]
            self.assertEqual(labels, [f"fs{i}" for i in range(11)])
            self.assertEqual(len(variants[-1][2]), 10)

    def test_walk_ignores_sweep_and_pool_override(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            files = self._make_files(tmp, 2)
            agent = _StubAgent(_pool(20, tmp))
            variants = plan_few_shot_variants(
                agent,
                walk_paths=files,
                sweep_counts=[3, 7],
                pool_override=[tmp / "decoy.json"],
                seed=0,
            )
            labels = [label for label, _, _ in variants]
            self.assertEqual(labels, ["fs0", "fs1", "fs2"])
            self.assertEqual([p.name for p in variants[-1][2]], ["pick_00.json", "pick_01.json"])

    def test_walk_explicit_wins_over_walk(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            files = self._make_files(tmp, 2)
            explicit_file = tmp / "explicit.json"
            explicit_file.write_text("{}", encoding="utf-8")
            agent = _StubAgent(_pool(0, tmp))
            agent._repo_root = tmp
            variants = plan_few_shot_variants(
                agent,
                explicit_paths=[str(explicit_file)],
                walk_paths=files,
            )
            self.assertEqual(len(variants), 1)
            self.assertEqual(variants[0][0], "explicit")
            self.assertEqual([p.name for p in variants[0][2]], ["explicit.json"])

    def test_walk_deduplicates_picks(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            files = self._make_files(tmp, 2)
            agent = _StubAgent(_pool(0, tmp))
            variants = plan_few_shot_variants(agent, walk_paths=[files[0], files[1], files[0]])
            # The duplicate is silently dropped: only 3 variants (fs0, fs1, fs2).
            labels = [label for label, _, _ in variants]
            self.assertEqual(labels, ["fs0", "fs1", "fs2"])

    def test_walk_warns_and_skips_missing_paths(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            real = tmp / "real.json"
            real.write_text("{}", encoding="utf-8")
            agent = _StubAgent(_pool(0, tmp))
            agent._repo_root = tmp
            variants = plan_few_shot_variants(
                agent,
                walk_paths=[str(real), str(tmp / "missing.json")],
            )
            # Only the real file makes it in → fs0, fs1.
            labels = [label for label, _, _ in variants]
            self.assertEqual(labels, ["fs0", "fs1"])
            self.assertEqual([p.name for p in variants[-1][2]], ["real.json"])

    def test_walk_empty_list_falls_through_to_none(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            agent = _StubAgent(_pool(5, tmp))
            # An empty walk_paths is falsy → planner falls through to the next branch.
            variants = plan_few_shot_variants(agent, walk_paths=[])
            self.assertEqual(len(variants), 1)
            self.assertEqual(variants[0][0], "none")


if __name__ == "__main__":
    unittest.main()
