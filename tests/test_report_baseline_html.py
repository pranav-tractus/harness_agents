# tests/test_report_baseline_html.py
"""Report adds a baseline bar only when baseline metrics exist."""

from __future__ import annotations

import unittest

from harness.report_dashboard_html import _postprocess_comparison_html


def _summary(with_baseline: bool):
    totals = {
        "run_count": 2,
        "field_match_rate_raw_llm": 0.74,
        "field_match_rate_final": 0.89,
        "field_match_rate": 0.89,
        "improvement_rate": 0.5,
        "regression_count": 0,
    }
    combo = {
        "model_key": "sonnet-4-6",
        "few_shot_count": 0,
        "field_match_rate_raw_llm": 0.74,
        "field_match_rate_final": 0.89,
        "field_match_rate": 0.89,
    }
    if with_baseline:
        totals["field_match_rate_baseline"] = 0.61
        combo["field_match_rate_baseline"] = 0.61
    return {"totals": totals, "by_combo": [combo], "by_chat": []}


class TestReportBaseline(unittest.TestCase):
    def test_baseline_bar_present_when_metric_exists(self):
        html, script = _postprocess_comparison_html(_summary(with_baseline=True))
        self.assertIn("Baseline", script)
        self.assertIn("baseline_pct", script)

    def test_no_baseline_bar_when_metric_absent(self):
        html, script = _postprocess_comparison_html(_summary(with_baseline=False))
        self.assertNotIn("baseline_pct", script)


if __name__ == "__main__":
    unittest.main()
