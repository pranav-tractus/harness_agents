"""Prompt strategy selection for model-neutral extraction."""

from __future__ import annotations

from enum import Enum

from core.utils import resolve_model_selection


class PromptStrategy(Enum):
    CURRENT = "current"
    XML_NEUTRAL = "xml_neutral"
    PROVIDER_PROFILE = "provider_profile"
    SCHEMA_DRIVEN = "schema_driven"

    @classmethod
    def from_str(cls, value: str | None) -> "PromptStrategy":
        if not value:
            return cls.CURRENT
        try:
            return cls(value.lower())
        except ValueError:
            return cls.CURRENT


def provider_family(model_key: str) -> str:
    """Return provider family string for a model key: 'anthropic', 'openai', 'gemini', 'bedrock'."""
    if not model_key:
        return "anthropic"
    try:
        resolved = resolve_model_selection(model_key)
        provider = resolved.get("provider", "anthropic")
        # Map bedrock to anthropic since bedrock hosts anthropic models
        if provider == "bedrock":
            return "anthropic"
        return provider
    except (ValueError, KeyError):
        return "anthropic"
