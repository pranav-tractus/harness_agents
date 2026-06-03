# tests/test_prompt_strategy.py
import pytest
from core.prompt_strategy import PromptStrategy, provider_family


def test_enum_values():
    assert PromptStrategy.CURRENT.value == "current"
    assert PromptStrategy.XML_NEUTRAL.value == "xml_neutral"
    assert PromptStrategy.PROVIDER_PROFILE.value == "provider_profile"
    assert PromptStrategy.SCHEMA_DRIVEN.value == "schema_driven"


def test_from_string_valid():
    assert PromptStrategy.from_str("xml_neutral") == PromptStrategy.XML_NEUTRAL
    assert PromptStrategy.from_str("CURRENT") == PromptStrategy.CURRENT
    assert PromptStrategy.from_str("schema_driven") == PromptStrategy.SCHEMA_DRIVEN


def test_from_string_invalid_returns_current():
    assert PromptStrategy.from_str("unknown") == PromptStrategy.CURRENT
    assert PromptStrategy.from_str("") == PromptStrategy.CURRENT
    assert PromptStrategy.from_str(None) == PromptStrategy.CURRENT


def test_provider_family_anthropic():
    assert provider_family("sonnet-4-6") == "anthropic"
    assert provider_family("opus-4-6") == "anthropic"
    assert provider_family("anthropic:opus-4-7") == "anthropic"


def test_provider_family_openai():
    assert provider_family("openai:5.4") == "openai"
    assert provider_family("openai:5.2") == "openai"


def test_provider_family_gemini():
    assert provider_family("gemini:gemini-2.5-pro") == "gemini"


def test_provider_family_unknown():
    assert provider_family("") == "anthropic"
