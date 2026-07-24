from apps.api.services import agent_service


def test_prompt_includes_chat_context_and_slot_guidance():
    ctx = {"profile_block": "email: a@b.com", "history_block": "last: CIF Busan",
           "product_block": "- TG-BPPC: choline"}
    msgs = [{"role": "seller", "body": "10MT TG-BPPC"},
            {"role": "customer", "body": "ok CIF Busan"}]
    prompt = agent_service.build_prompt("Dummy-01", msgs, ctx)
    assert "seller: 10MT TG-BPPC" in prompt
    assert "email: a@b.com" in prompt
    assert "last: CIF Busan" in prompt
    assert "TG-BPPC: choline" in prompt
    # slot guidance names the critical slots so the model knows what to ask for
    for slot in ("quantity", "unit_price", "ship_term"):
        assert slot in prompt


def test_prompt_embeds_previous_when_revising():
    prompt = agent_service.build_prompt("Dummy-01", [], {"profile_block": None,
        "history_block": None, "product_block": None}, previous_json='{"data": []}')
    assert '"data": []' in prompt


def test_system_prompt_carries_hard_rules_and_date_pin():
    from apps.api.services import agent_service
    system = agent_service.SYSTEM
    assert "Chat is the only source of truth" in system
    assert "Empty is a valid answer" in system
    assert "Today is" in system
