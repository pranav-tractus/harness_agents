import pytest
from unittest.mock import patch, MagicMock
from graph.extractor import ExtractedFacts, ExtractedProduct, extract_entities

SAMPLE_CHAT = """(TEAM2): Need 10 MT KNM Coffee, CIF Busan, USD 500/MT.
(TEAM1): Confirmed. Packing: 25kg PP bags. Loading: 1x20 FCL.
(TEAM2): Payment: Net 30.
(TEAM1): Done."""


def test_extracted_facts_model():
    facts = ExtractedFacts(
        products=[ExtractedProduct(name="KNM Coffee", quantity=10.0, unit="MT",
                                   price=500.0, price_unit="USD/MT",
                                   incoterm="CIF", port="Busan")],
        ports=["Busan"],
        payment_terms="Net 30",
        packing="25kg PP bags",
        loading="1x20 FCL",
    )
    assert facts.products[0].name == "KNM Coffee"
    assert facts.payment_terms == "Net 30"


def test_extract_entities_calls_llm(monkeypatch):
    fake_facts = ExtractedFacts(
        products=[ExtractedProduct(name="Rice", quantity=5.0, unit="MT",
                                   price=300.0, price_unit="USD/MT",
                                   incoterm="FOB", port="Singapore")],
        ports=["Singapore"],
        payment_terms="100% Advance",
        packing="",
        loading="",
    )
    monkeypatch.setattr("graph.extractor.call_llm", lambda *a, **kw: fake_facts)
    result = extract_entities(SAMPLE_CHAT, model_key="sonnet-4-6")
    assert result.products[0].name == "Rice"
    assert result.payment_terms == "100% Advance"


def test_extract_entities_returns_empty_on_no_data(monkeypatch):
    monkeypatch.setattr("graph.extractor.call_llm", lambda *a, **kw: ExtractedFacts())
    result = extract_entities("Just a greeting, no contract data.", model_key="sonnet-4-6")
    assert result.products == []
    assert result.payment_terms == ""


def test_extract_entities_injects_memory_block(monkeypatch):
    captured_prompt = {}

    def fake_call_llm(prompt, schema, model_key):
        captured_prompt["prompt"] = prompt
        return ExtractedFacts()

    monkeypatch.setattr("graph.extractor.call_llm", fake_call_llm)
    block = "=== Customer History (acme_foods) ===\n- Products: KNM Coffee 10 MT @ USD/bag 25"
    extract_entities("Hi, need coffee.", memory_block=block)
    assert block in captured_prompt["prompt"]


def test_extract_entities_no_memory_block_omits_section(monkeypatch):
    captured_prompt = {}

    def fake_call_llm(prompt, schema, model_key):
        captured_prompt["prompt"] = prompt
        return ExtractedFacts()

    monkeypatch.setattr("graph.extractor.call_llm", fake_call_llm)
    extract_entities("Hi, need coffee.")
    assert "Customer History" not in captured_prompt["prompt"]
