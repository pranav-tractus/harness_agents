# tests/test_token_usage.py
"""Unit tests for TokenUsage dataclass and call_llm_with_usage."""

from __future__ import annotations

import unittest

from core.token_usage import TokenUsage


class TestTokenUsage(unittest.TestCase):
    def test_defaults_are_zero(self):
        u = TokenUsage()
        self.assertEqual(u.input_tokens, 0)
        self.assertEqual(u.output_tokens, 0)
        self.assertEqual(u.cache_read_tokens, 0)
        self.assertEqual(u.cache_write_tokens, 0)

    def test_total_tokens(self):
        u = TokenUsage(input_tokens=100, output_tokens=50)
        self.assertEqual(u.total_tokens(), 150)

    def test_addition(self):
        a = TokenUsage(input_tokens=10, output_tokens=5, cache_read_tokens=3, cache_write_tokens=1)
        b = TokenUsage(input_tokens=20, output_tokens=8, cache_read_tokens=0, cache_write_tokens=2)
        c = a + b
        self.assertEqual(c.input_tokens, 30)
        self.assertEqual(c.output_tokens, 13)
        self.assertEqual(c.cache_read_tokens, 3)
        self.assertEqual(c.cache_write_tokens, 3)

    def test_to_dict(self):
        u = TokenUsage(input_tokens=100, output_tokens=50, cache_read_tokens=20, cache_write_tokens=5)
        d = u.to_dict()
        self.assertEqual(d["input_tokens"], 100)
        self.assertEqual(d["output_tokens"], 50)
        self.assertEqual(d["cache_read_tokens"], 20)
        self.assertEqual(d["cache_write_tokens"], 5)
        self.assertEqual(d["total_tokens"], 150)

    def test_from_dict(self):
        d = {"input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 2, "cache_write_tokens": 1}
        u = TokenUsage.from_dict(d)
        self.assertEqual(u.input_tokens, 10)
        self.assertEqual(u.total_tokens(), 15)

    def test_from_dict_handles_missing_keys(self):
        u = TokenUsage.from_dict({"input_tokens": 7})
        self.assertEqual(u.input_tokens, 7)
        self.assertEqual(u.output_tokens, 0)


class TestCallLlmWithUsage(unittest.TestCase):
    def test_returns_tuple_of_model_and_usage(self):
        from unittest.mock import MagicMock, patch

        from core.llm_client import call_llm_with_usage
        from core.models import SOExtractContractList

        fake_result = SOExtractContractList.model_validate({"data": []})
        fake_usage = {
            "input_tokens": 100, "output_tokens": 50,
            "cache_read_tokens": 0, "cache_write_tokens": 0, "total_tokens": 150,
        }

        with patch("core.llm_client._call_bedrock_with_usage", return_value=(fake_result, fake_usage)):
            model, usage = call_llm_with_usage(
                "prompt",
                SOExtractContractList,
                model_key="sonnet-4-6",
            )

        self.assertIsInstance(model, SOExtractContractList)
        self.assertEqual(usage["input_tokens"], 100)
        self.assertEqual(usage["output_tokens"], 50)

    def test_call_llm_unchanged_returns_model_only(self):
        from unittest.mock import patch

        from core.llm_client import call_llm
        from core.models import SOExtractContractList

        fake_result = SOExtractContractList.model_validate({"data": []})

        with patch("core.llm_client._call_bedrock", return_value=fake_result):
            result = call_llm("prompt", SOExtractContractList, model_key="sonnet-4-6")

        self.assertIsInstance(result, SOExtractContractList)


class TestExtractorTokenPropagation(unittest.TestCase):
    def test_extraction_engine_run_stores_token_usage(self):
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from core.extractor import ExtractionEngine
        from core.models import SOExtractContractList

        fake_model = SOExtractContractList.model_validate({"data": []})
        fake_usage = {
            "input_tokens": 200, "output_tokens": 80,
            "cache_read_tokens": 0, "cache_write_tokens": 0, "total_tokens": 280,
        }

        with patch("core.extractor.call_llm_with_usage", return_value=(fake_model, fake_usage)), \
                patch("core.extractor.init_db"), \
                patch("core.extractor.build_prompt", return_value="fake prompt"), \
                patch("core.extractor.build_system_prompt", return_value="fake system"):
            engine = ExtractionEngine(model_key="sonnet-4-6", db_path=Path("/tmp/test.db"))
            result = engine.run("some chat text")

        self.assertEqual(result.status, "success")
        self.assertIsNotNone(result.token_usage)
        self.assertEqual(result.token_usage["input_tokens"], 200)
        self.assertEqual(result.token_usage["total_tokens"], 280)


class TestAgentTokenWiring(unittest.TestCase):
    def test_run_one_stores_token_usage_from_engine(self):
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
        payload = ChatInput(
            source_path=Path("raw_data/chats/x.json"),
            text="buy 10 bags",
            meta={},
        )
        opts = RunOptions(model_key="sonnet-4-6", extra={})

        engine = MagicMock()
        engine.iso_date = "2026-06-01"
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
            token_usage={"input_tokens": 150, "output_tokens": 60, "cache_read_tokens": 0,
                         "cache_write_tokens": 0, "total_tokens": 210},
        )

        with patch("agents.so_extraction.agent.ExtractionEngine", return_value=engine), \
                patch("agents.so_extraction.agent.run_postprocess_pipeline",
                      return_value=({"data": []}, {"llm_validate_ms": 0, "postprocess_total_ms": 0,
                                                    "deterministic_ms": 0})), \
                patch.object(agent, "expected_for", return_value=None):
            result = agent.run_one(payload, opts)

        self.assertIsNotNone(result.token_usage)
        self.assertEqual(result.token_usage["input_tokens"], 150)


if __name__ == "__main__":
    unittest.main()
