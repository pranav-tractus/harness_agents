# tests/test_token_report_html.py
"""Token report HTML generation tests."""

from __future__ import annotations

import unittest

from harness.token_report_html import render_token_report_html


def _summary(with_tokens: bool = True):
    token_fields = {}
    if with_tokens:
        token_fields = {
            "total_input_tokens": 1500,
            "total_output_tokens": 600,
            "total_cache_read_tokens": 200,
            "total_cache_write_tokens": 50,
            "total_tokens": 2100,
        }
    totals = {"run_count": 3, "success_rate": 1.0, **token_fields}
    by_combo = [
        {"model_key": "sonnet-4-6", "total_input_tokens": 1500,
         "total_output_tokens": 600, "total_tokens": 2100, "run_count": 3,
         "total_cache_read_tokens": 200, "total_cache_write_tokens": 50}
    ] if with_tokens else []
    by_chat = [
        {"chat_filename": "chat_01.json", "model_key": "sonnet-4-6",
         "few_shot_count": 0, "total_input_tokens": 500, "total_output_tokens": 200,
         "total_tokens": 700, "total_cache_read_tokens": 0, "run_count": 1}
    ] if with_tokens else []
    return {"totals": totals, "by_combo": by_combo, "by_chat": by_chat}


class TestTokenReportHtml(unittest.TestCase):
    def test_report_contains_token_totals(self):
        html = render_token_report_html("run-001", "2026-06-03T12:00:00Z", {}, _summary())
        self.assertIn("1,500", html)   # input tokens formatted
        self.assertIn("Token Usage", html)

    def test_report_contains_per_chat_table(self):
        html = render_token_report_html("run-001", "2026-06-03T12:00:00Z", {}, _summary())
        self.assertIn("chat_01.json", html)

    def test_report_no_tokens_shows_placeholder(self):
        html = render_token_report_html("run-001", "2026-06-03T12:00:00Z", {}, _summary(with_tokens=False))
        self.assertIn("No token data", html)

    def test_report_is_valid_html_structure(self):
        html = render_token_report_html("run-001", "2026-06-03T12:00:00Z", {}, _summary())
        self.assertTrue(html.strip().startswith("<!DOCTYPE html"))
        self.assertIn("</html>", html)


if __name__ == "__main__":
    unittest.main()
