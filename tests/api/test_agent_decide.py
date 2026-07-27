from apps.api.models import AgentDecision, AgentQuestion
from apps.api.services import agent_service


def _llm(decision):
    return lambda prompt, schema, model_key, system_prompt=None: decision


def test_decide_caps_questions():
    raw = AgentDecision(mode="clarify", message="…",
        questions=[AgentQuestion(slot=s, directed_to="customer", text="?")
                   for s in ("packing", "quantity", "loading", "unit_price", "ship_term")])
    out = agent_service.decide("D", [], {}, "sonnet-4-6", llm=_llm(raw))
    assert len(out.questions) == 3
    assert set(q.slot for q in out.questions) == {"quantity", "unit_price", "ship_term"}


def test_decide_downgrades_premature_finalize():
    raw = AgentDecision(mode="finalize", message="done", ready_to_finalize=False)
    out = agent_service.decide("D", [], {}, "sonnet-4-6", llm=_llm(raw))
    assert out.mode == "draft"
