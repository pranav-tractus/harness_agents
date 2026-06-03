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


from core.prompt_builder import build_prompt, build_validation_system_prompt, build_validation_user_prompt
from core.prompt_strategy import PromptStrategy


def test_build_prompt_current_strategy_contains_extraction_rules():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.CURRENT,
    )
    assert "extraction rules" in prompt.lower() or "Extraction rules" in prompt


def test_build_prompt_xml_neutral_uses_xml_tags():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.XML_NEUTRAL,
    )
    assert "<extraction_task>" in prompt
    assert "<rules>" in prompt


def test_build_prompt_schema_driven_is_short():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.SCHEMA_DRIVEN,
    )
    assert "Three rules" in prompt
    assert len(prompt) < 9000  # schema-driven should be concise (schema JSON adds length)


def test_build_prompt_provider_profile_anthropic_uses_current():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.PROVIDER_PROFILE,
        model_key="sonnet-4-6",
    )
    assert "extraction rules" in prompt.lower() or "Extraction rules" in prompt


def test_build_prompt_provider_profile_openai_uses_xml():
    prompt = build_prompt(
        "Test chat",
        attempt=1,
        iso_date="2026-06-03",
        strategy=PromptStrategy.PROVIDER_PROFILE,
        model_key="openai:5.4",
    )
    assert "<extraction_task>" in prompt


def test_build_validation_system_xml_neutral():
    prompt = build_validation_system_prompt(strategy=PromptStrategy.XML_NEUTRAL)
    assert "<rules>" in prompt


def test_build_validation_system_current():
    prompt = build_validation_system_prompt(strategy=PromptStrategy.CURRENT)
    assert "<rules>" not in prompt or "Hard rules" in prompt


def test_build_validation_user_xml_neutral():
    prompt = build_validation_user_prompt(
        source_text="Chat here",
        extraction_json={"data": []},
        strategy=PromptStrategy.XML_NEUTRAL,
    )
    assert "<chat_transcript>" in prompt


def test_build_validation_user_current():
    prompt = build_validation_user_prompt(
        source_text="Chat here",
        extraction_json={"data": []},
        strategy=PromptStrategy.CURRENT,
    )
    assert "## Chat transcript" in prompt


from core.models import LLMExtractContractProductItem, SalesOrderExtractContractKeyDetails


def test_item_field_descriptions_are_precise():
    schema = LLMExtractContractProductItem.model_json_schema()
    props = schema.get("properties", {})
    # Confirm agreement-only rule is encoded for unit_price
    assert "agreed" in props["unit_price"]["description"].lower() or \
           "final" in props["unit_price"]["description"].lower()
    # Confirm verbatim rule is encoded for packing
    assert "verbatim" in props["packing"]["description"].lower() or \
           "exact" in props["packing"]["description"].lower()


def test_contract_field_descriptions_encode_rules():
    schema = SalesOrderExtractContractKeyDetails.model_json_schema()
    props = schema.get("properties", {})
    # payment_date must mention payment
    assert "payment" in props["payment_date"]["description"].lower()
    # vendor_name must mention null/empty
    assert "null" in props["vendor_name"]["description"].lower() or \
           "empty" in props["vendor_name"]["description"].lower()


from core.extractor import ExtractionEngine
from core.prompt_strategy import PromptStrategy


def test_extraction_engine_accepts_strategy():
    engine = ExtractionEngine(strategy=PromptStrategy.XML_NEUTRAL)
    assert engine.strategy == PromptStrategy.XML_NEUTRAL


def test_extraction_engine_default_strategy_is_current():
    engine = ExtractionEngine()
    assert engine.strategy == PromptStrategy.CURRENT
