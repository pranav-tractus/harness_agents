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
    facts = pe.extract_product_facts(
        name="Wheat Flour",
        short_description="Wheat Flour 25kg",
        long_description="Stone-ground whole wheat atta, milled in India.",
        spec="grade A, 25kg PP bag",
        metadata={"density": "0.55 g/cm3"},
        model_key="sonnet-4-6",
    )

    assert facts.aliases == ["atta", "wheat flour bag"]
    assert facts.grade == "A"
    assert captured["schema"] is pe.ProductFacts
    assert captured["model_key"] == "sonnet-4-6"
    # richer inputs all reach the prompt
    for token in ("Wheat Flour", "stone-ground", "grade A, 25kg PP bag", "density", "0.55 g/cm3"):
        assert token.lower() in captured["prompt"].lower()
