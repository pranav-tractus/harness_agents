"""Tests for Anthropic direct API model catalog entries."""

from __future__ import annotations

import unittest

from core.utils import MODEL_CATALOG, resolve_model_selection


class TestAnthropicDirectCatalog(unittest.TestCase):
    def test_anthropic_keys_present_in_catalog(self):
        for key in ("anthropic:sonnet-4-6", "anthropic:opus-4-8"):
            self.assertIn(key, MODEL_CATALOG, f"{key} not in MODEL_CATALOG")

    def test_anthropic_provider_field(self):
        entry = MODEL_CATALOG["anthropic:sonnet-4-6"]
        self.assertEqual(entry["provider"], "anthropic")
        self.assertEqual(entry["model_id"], "claude-sonnet-4-6")

    def test_resolve_model_selection_anthropic(self):
        resolved = resolve_model_selection("anthropic:opus-4-8")
        self.assertEqual(resolved["provider"], "anthropic")
        self.assertEqual(resolved["model_id"], "claude-opus-4-8")
        self.assertEqual(resolved["model_key"], "anthropic:opus-4-8")

    def test_bedrock_key_still_resolves_to_bedrock(self):
        resolved = resolve_model_selection("sonnet-4-6")
        self.assertEqual(resolved["provider"], "bedrock")

    def test_unknown_anthropic_key_raises(self):
        with self.assertRaises(ValueError):
            resolve_model_selection("anthropic:nonexistent-model")


class TestAnthropicDirectCaller(unittest.TestCase):
    def test_call_llm_dispatches_to_anthropic_provider(self):
        from unittest.mock import patch

        from core.llm_client import call_llm
        from core.models import SOExtractContractList

        fake_result = SOExtractContractList.model_validate({"data": []})

        with patch("core.llm_client._call_anthropic", return_value=fake_result) as mocked:
            result = call_llm(
                "test prompt",
                SOExtractContractList,
                model_key="anthropic:sonnet-4-6",
                system_prompt="sys",
            )

        mocked.assert_called_once()
        self.assertEqual(result, fake_result)

    def test_call_anthropic_no_system_when_none(self):
        from unittest.mock import MagicMock, patch

        from core.llm_client import _call_anthropic
        from core.models import SOExtractContractList

        fake_client = MagicMock()
        fake_client.messages.create.return_value = SOExtractContractList.model_validate({"data": []})

        with patch("core.llm_client.instructor") as mock_instructor, \
                patch("core.llm_client.anthropic_sdk") as mock_sdk:
            mock_sdk.Anthropic.return_value = MagicMock()
            mock_instructor.from_anthropic.return_value = fake_client
            _call_anthropic(
                "hello",
                SOExtractContractList,
                model_id="claude-sonnet-4-6",
                system_prompt=None,
            )

        call_kwargs = fake_client.messages.create.call_args.kwargs
        self.assertNotIn("system", call_kwargs)


if __name__ == "__main__":
    unittest.main()
