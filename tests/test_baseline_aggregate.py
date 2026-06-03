# tests/test_baseline_aggregate.py
"""Baseline metric flows through record_to_row and aggregate()."""

from __future__ import annotations

import unittest

from agents.base import AgentRunResult, ScoreResult
from harness.artifacts import aggregate, record_to_row


def _rec_with_scores(*, baseline_mm, raw_mm, final_mm, compared=10):
    return AgentRunResult(
        agent_id="so_extraction",
        dataset_id="default",
        source_path="raw_data/chats/x.json",
        success=True,
        status="success",
        attempts=1,
        elapsed_sec=1.0,
        model_key="sonnet-4-6",
        score=ScoreResult(expected_available=True, mismatch_count=final_mm, compared_field_count=compared),
        score_raw_llm=ScoreResult(expected_available=True, mismatch_count=raw_mm, compared_field_count=compared),
        score_baseline=ScoreResult(expected_available=True, mismatch_count=baseline_mm, compared_field_count=compared),
    )


class TestBaselineAggregate(unittest.TestCase):
    def test_record_row_exposes_baseline_rate(self):
        row = record_to_row(_rec_with_scores(baseline_mm=4, raw_mm=2, final_mm=1))
        self.assertEqual(row["mismatch_count_baseline"], 4)
        self.assertTrue(row["baseline_available"])
        self.assertAlmostEqual(row["field_match_rate_baseline"], 0.6)

    def test_aggregate_rolls_up_baseline_rate(self):
        recs = [
            _rec_with_scores(baseline_mm=4, raw_mm=2, final_mm=1),
            _rec_with_scores(baseline_mm=6, raw_mm=3, final_mm=1),
        ]
        summary = aggregate(recs)
        totals = summary["totals"]
        # baseline: (4+6) mismatches over (10+10) compared -> 1 - 0.5 = 0.5
        self.assertAlmostEqual(totals["field_match_rate_baseline"], 0.5)
        # baseline metric also present per combo
        self.assertIn("field_match_rate_baseline", summary["by_combo"][0])

    def test_aggregate_baseline_rate_none_when_no_baseline(self):
        rec = AgentRunResult(
            agent_id="so_extraction", dataset_id="default", source_path="raw_data/chats/x.json",
            success=True, status="success", attempts=1, elapsed_sec=1.0, model_key="sonnet-4-6",
            score=ScoreResult(expected_available=True, mismatch_count=1, compared_field_count=10),
            score_raw_llm=ScoreResult(expected_available=True, mismatch_count=2, compared_field_count=10),
        )
        summary = aggregate([rec])
        self.assertIsNone(summary["totals"]["field_match_rate_baseline"])


if __name__ == "__main__":
    unittest.main()
