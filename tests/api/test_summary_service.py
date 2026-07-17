from core.models import SOExtractContractList, SOUpdateContractList

from apps.api.services import summary_service as ss
from tests.api._factories import make_extract, make_item, make_update


def _fake_llm_factory(captured, result):
    def _llm(prompt, schema, model_key, system_prompt=None):
        captured["prompt"] = prompt
        captured["model_key"] = model_key
        captured["schema"] = schema
        captured["system_prompt"] = system_prompt
        return result
    return _llm


def test_generate_embeds_all_context_blocks():
    captured = {}
    result = make_extract(items=[make_item(description="TG-BPPC", quantity=10, quantity_unit="MT")])
    msgs = [{"role": "me", "body": "10MT TG-BPPC"}, {"role": "customer", "body": "ok"}]
    out = ss.generate(
        "Dummy-01", msgs, "=== Product Catalog ===\n- TG-BPPC: Choline", "sonnet-4-6",
        profile_block="=== Customer Profile ===\n- approved_credit_term: Net 30",
        history_block="=== Customer History ===\n- Products: TG-BPPC",
        llm=_fake_llm_factory(captured, result),
    )
    assert isinstance(out, SOExtractContractList)
    assert captured["schema"] is SOExtractContractList
    assert "10MT TG-BPPC" in captured["prompt"]
    assert "TG-BPPC: Choline" in captured["prompt"]
    assert "approved_credit_term: Net 30" in captured["prompt"]
    assert "Customer History" in captured["prompt"]
    assert "Prefer values explicitly stated in the chat" in captured["system_prompt"]


def test_generate_omits_missing_blocks():
    captured = {}
    result = make_extract(items=[make_item(description="TG-BPPC")])
    out = ss.generate("Dummy-01", [{"role": "me", "body": "x"}], None, "sonnet-4-6",
                      llm=_fake_llm_factory(captured, result))
    assert isinstance(out, SOExtractContractList)
    assert "Customer profile" not in captured["prompt"]
    assert "Product catalog" not in captured["prompt"]


def test_revise_embeds_previous_and_context():
    captured = {}
    prev = make_extract(items=[make_item(description="TG-BPPC", quantity=10, quantity_unit="MT")])
    result = make_update(items=[make_item(description="TG-BPPC", quantity=20, quantity_unit="MT")])
    out = ss.revise(
        "Dummy-01", prev, "change qty to 20", [{"role": "me", "body": "x"}], "sonnet-4-6",
        product_block="=== Product Catalog ===\n- TG-BPPC: Choline",
        profile_block="=== Customer Profile ===\n- email: a@b.com",
        llm=_fake_llm_factory(captured, result),
    )
    assert isinstance(out, SOUpdateContractList)
    assert captured["schema"] is SOUpdateContractList
    assert "change qty to 20" in captured["prompt"]
    assert "TG-BPPC" in captured["prompt"]       # previous summary embedded
    assert "email: a@b.com" in captured["prompt"]
