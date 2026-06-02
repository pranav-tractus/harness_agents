"""Unit tests for the bare-prompt baseline extractor."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.baseline_extractor import BASELINE_PROMPT_TEMPLATE, run_baseline
from core.models import SOExtractContractList


class TestBaselineExtractor(unittest.TestCase):
    def test_prompt_is_single_line_with_text_appended(self):
        prompt = BASELINE_PROMPT_TEMPLATE + "hello world"
        self.assertTrue(prompt.startswith("Create a sales order from this:"))
        self.assertIn("hello world", prompt)

    def test_run_baseline_calls_llm_with_no_system_prompt_and_returns_dict(self):
        fake = SOExtractContractList.model_validate({"data": []})
        with patch("core.baseline_extractor.call_llm", return_value=fake) as mocked:
            out = run_baseline("some chat text", model_key="sonnet-4-6")
        self.assertEqual(out, {"data": []})
        mocked.assert_called_once_with(
            "Create a sales order from this:\n\nsome chat text",
            schema=SOExtractContractList,
            model_key="sonnet-4-6",
            system_prompt=None,
        )

    def test_run_baseline_returns_none_on_failure(self):
        with patch("core.baseline_extractor.call_llm", side_effect=RuntimeError("boom")):
            out = run_baseline("text", model_key="sonnet-4-6")
        self.assertIsNone(out)


class TestAgentBaselineWiring(unittest.TestCase):
    def test_run_one_populates_baseline_when_requested(self):
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from agents.base import RunOptions
        from agents.so_extraction.agent import ChatInput, SOExtractionAgent

        agent = SOExtractionAgent(
            id="so_extraction",
            display_name="SO Extraction",
            datasets=[],
            repo_root=Path(__file__).resolve().parents[1],
        )
        payload = ChatInput(source_path=Path("raw_data/chats/x.json"), text="buy 10 bags", meta={})
        opts = RunOptions(model_key="sonnet-4-6", extra={"run_baseline": True})

        engine = MagicMock()
        engine.run.return_value = MagicMock(
            status="success",
            output_json='{"data": []}',
            attempts=1,
            error=None,
            model_key="sonnet-4-6",
            model_provider="bedrock",
            chunk_count=1,
            chunk_truncated=False,
            input_chars=10,
        )
        engine.iso_date = "2026-06-01"

        with patch("agents.so_extraction.agent.ExtractionEngine", return_value=engine), \
                patch("agents.so_extraction.agent.run_postprocess_pipeline", return_value=({"data": []}, {})), \
                patch("agents.so_extraction.agent.run_baseline", return_value={"data": []}) as mocked_base, \
                patch.object(agent, "expected_for", return_value=None):
            result = agent.run_one(payload, opts)

        mocked_base.assert_called_once()
        self.assertEqual(result.baseline_output_json, {"data": []})

    def test_run_one_skips_baseline_by_default(self):
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from agents.base import RunOptions
        from agents.so_extraction.agent import ChatInput, SOExtractionAgent

        agent = SOExtractionAgent(
            id="so_extraction",
            display_name="SO Extraction",
            datasets=[],
            repo_root=Path(__file__).resolve().parents[1],
        )
        payload = ChatInput(source_path=Path("raw_data/chats/x.json"), text="buy 10 bags", meta={})
        opts = RunOptions(model_key="sonnet-4-6", extra={})

        engine = MagicMock()
        engine.run.return_value = MagicMock(
            status="success",
            output_json='{"data": []}',
            attempts=1,
            error=None,
            model_key="sonnet-4-6",
            model_provider="bedrock",
            chunk_count=1,
            chunk_truncated=False,
            input_chars=10,
        )
        engine.iso_date = "2026-06-01"

        with patch("agents.so_extraction.agent.ExtractionEngine", return_value=engine), \
                patch("agents.so_extraction.agent.run_postprocess_pipeline", return_value=({"data": []}, {})), \
                patch("agents.so_extraction.agent.run_baseline") as mocked_base, \
                patch.object(agent, "expected_for", return_value=None):
            result = agent.run_one(payload, opts)

        mocked_base.assert_not_called()
        self.assertIsNone(result.baseline_output_json)


if __name__ == "__main__":
    unittest.main()
