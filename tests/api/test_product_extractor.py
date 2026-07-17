from graph import product_extractor as pe


def test_extract_product_facts_builds_prompt_and_returns_facts():
    captured = {}

    def _fake_llm(prompt, schema, model_key, system_prompt=None):
        captured["prompt"] = prompt
        captured["schema"] = schema
        captured["model_key"] = model_key
        return schema(
            aliases=["atta", "wheat flour bag"],
            grade="A",
            packing_size="25kg",
            unit="MT",
            attributes={"origin": "India"},
        )

    pe.call_llm = _fake_llm  # monkeypatch module ref
    facts = pe.extract_product_facts("Wheat Flour 25kg", "grade A, 25kg PP bag", "sonnet-4-6")

    assert facts.aliases == ["atta", "wheat flour bag"]
    assert facts.grade == "A"
    assert facts.packing_size == "25kg"
    assert facts.attributes["origin"] == "India"
    assert captured["schema"] is pe.ProductFacts
    assert captured["model_key"] == "sonnet-4-6"
    assert "Wheat Flour 25kg" in captured["prompt"]
    assert "grade A, 25kg PP bag" in captured["prompt"]
