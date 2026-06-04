from core.prompt_builder import build_prompt, build_system_prompt


def test_prompt_without_memory_block_has_no_memory_section():
    prompt = build_prompt(
        "Some chat text",
        iso_date="2026-06-04",
        db_few_shot_limit=0,
    )
    assert "Customer history" not in prompt
    assert "graph memory" not in prompt


def test_prompt_with_memory_block_contains_history_section():
    memory = "=== Customer History (acme_foods) ===\n- Products: KNM Coffee"
    prompt = build_prompt(
        "Some chat text",
        iso_date="2026-06-04",
        memory_block=memory,
        db_few_shot_limit=0,
    )
    assert "Customer history (graph memory)" in prompt
    assert "KNM Coffee" in prompt


def test_prompt_memory_block_appears_before_input_text():
    memory = "=== Customer History ===\n- Products: Test Product"
    prompt = build_prompt(
        "THE_INPUT_TEXT",
        iso_date="2026-06-04",
        memory_block=memory,
        db_few_shot_limit=0,
    )
    memory_pos = prompt.find("Customer history")
    input_pos = prompt.find("THE_INPUT_TEXT")
    assert memory_pos < input_pos


def test_system_prompt_contains_memory_rule():
    system = build_system_prompt()
    assert "Memory is disambiguation only" in system or "memory" in system.lower()
