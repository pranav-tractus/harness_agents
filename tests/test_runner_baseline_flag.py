"""--with-baseline flips run_baseline in RunOptions.extra."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from harness.runner import _run_extra


class TestRunnerBaselineFlag(unittest.TestCase):
    def test_run_extra_sets_run_baseline_true(self):
        args = SimpleNamespace(validation_model="", db_few_shot_limit=0, with_baseline=True)
        extra = _run_extra(args, "sonnet-4-6")
        self.assertTrue(extra["run_baseline"])

    def test_run_extra_run_baseline_defaults_false(self):
        args = SimpleNamespace(validation_model="", db_few_shot_limit=0, with_baseline=False)
        extra = _run_extra(args, "sonnet-4-6")
        self.assertFalse(extra["run_baseline"])


if __name__ == "__main__":
    unittest.main()
