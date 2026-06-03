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


if __name__ == "__main__":
    unittest.main()
