"""Unit tests for the bare-prompt baseline extractor."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.baseline_extractor import BASELINE_PROMPT_TEMPLATE, run_baseline
from core.models import SOExtractContractList


class TestBaselineExtractor(unittest.TestCase):
    def test_prompt_is_single_line_with_text_appended(self):
        prompt = BASELINE_PROMPT_TEMPLATE.format(text="hello world")
        self.assertTrue(prompt.startswith("Create a sales order from this:"))
        self.assertIn("hello world", prompt)

    def test_run_baseline_calls_llm_with_no_system_prompt_and_returns_dict(self):
        fake = SOExtractContractList.model_validate({"data": []})
        with patch("core.baseline_extractor.call_llm", return_value=fake) as mocked:
            out = run_baseline("some chat text", model_key="sonnet-4-6")
        self.assertEqual(out, {"data": []})
        _, kwargs = mocked.call_args
        self.assertIsNone(kwargs.get("system_prompt"))
        self.assertEqual(kwargs.get("model_key"), "sonnet-4-6")
        self.assertEqual(kwargs.get("schema"), SOExtractContractList)

    def test_run_baseline_returns_none_on_failure(self):
        with patch("core.baseline_extractor.call_llm", side_effect=RuntimeError("boom")):
            out = run_baseline("text", model_key="sonnet-4-6")
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
