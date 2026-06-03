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


if __name__ == "__main__":
    unittest.main()
