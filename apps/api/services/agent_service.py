from datetime import datetime, timezone

from apps.api.db import mongo
from apps.api.models import AgentDecision, cap_questions, render_summary_markdown
from apps.api.services import chat_service, summary_context_service
from core.llm_client import call_llm
from core.models import SOExtractContractList

SYSTEM = (
    "You are a neutral contract agent in a group chat with a seller and a customer. "
    "Read the conversation and grounding context, then return an AgentDecision.\n"
    "Maintain a per-slot ledger over these contract slots: description (product), "
    "quantity, unit_price, ship_term (incoterm), shipping_address, packing, loading, "
    "payment_date. For each slot record value, source (chat|last_order|profile|inferred|"
    "unknown), confidence, and agreed_by (which of seller/customer explicitly agreed).\n"
    "Resolve soft slots (shipping_address, packing, loading, payment_date) silently from "
    "last orders / profile and mark them source=inferred. Only ASK about critical slots "
    "(description, quantity, unit_price, ship_term) you cannot resolve; ask at most 3, "
    "directed to the party who can answer. When all critical slots are known, set mode="
    "'draft' and fill contract. Set ready_to_finalize=true ONLY when every material slot "
    "is agreed_by both seller and customer; then set mode='finalize'. Never invent "
    "quantities, prices, or terms."
)


def _chat_block(messages: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {m['body']}" for m in messages)


def _section(label: str, block: str | None) -> str:
    return f"{label}:\n{block}\n\n" if block else ""


def build_prompt(customer_name, messages, ctx, previous_json=None) -> str:
    prompt = (
        f"Customer: {customer_name}\n\n"
        + _section("Customer profile", ctx.get("profile_block"))
        + _section("Purchase history (last orders)", ctx.get("history_block"))
        + _section("Product catalog", ctx.get("product_block"))
    )
    if previous_json:
        prompt += f"Previous draft (JSON):\n{previous_json}\n\n"
    prompt += (
        f"Conversation:\n{_chat_block(messages)}\n\n"
        "Slots to track: description, quantity, unit_price, ship_term, "
        "shipping_address, packing, loading, payment_date.\n"
        "Return the AgentDecision now."
    )
    return prompt


def decide(customer_name, messages, ctx, model_key, *, previous_json=None, llm=None) -> AgentDecision:
    llm = llm or call_llm
    prompt = build_prompt(customer_name, messages, ctx, previous_json)
    decision: AgentDecision = llm(prompt, AgentDecision, model_key, system_prompt=SYSTEM)
    decision = cap_questions(decision)
    if decision.mode == "finalize" and not decision.ready_to_finalize:
        decision.mode = "draft"
    return decision


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _customer_name(customer_id: str) -> str:
    doc = mongo.customers().find_one({"_id": customer_id}, projection={"name": 1})
    return doc["name"] if doc else customer_id


def _pending(customer_id: str) -> dict | None:
    return mongo.summaries().find_one({"customer_id": customer_id, "status": "pending"})


def _summary_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def _agent_msg(customer_id, body, kind, summary_id=None, summary_json=None):
    return chat_service.add_message(customer_id, "agent", body, kind=kind,
                                    summary_id=summary_id, summary_json=summary_json)


def invoke(customer_id, model_key, *, decider=None, context_fn=None, graph_fn=None) -> dict:
    decider = decider or decide
    context_fn = context_fn or summary_context_service.assemble

    last = chat_service.get_last_contract_seq(customer_id)
    window = chat_service.chat_messages_since(customer_id, last)
    if not window:
        return {"messages": [_agent_msg(customer_id, "No new messages since the last contract.", "chat")],
                "summary": None}

    ctx = context_fn(customer_id)
    pending = _pending(customer_id)
    previous_json = None
    if pending:
        previous_json = SOExtractContractList(**pending["content"]).model_dump_json(indent=2)
    decision = decider(_customer_name(customer_id), window, ctx, model_key,
                       previous_json=previous_json)

    if decision.mode == "clarify":
        msg = _agent_msg(customer_id, decision.message, "question")
        return {"messages": [msg], "summary": None}

    if decision.mode == "finalize":
        return finalize(customer_id, decision=decision, window=window,
                        model_key=model_key, graph_fn=graph_fn)

    # draft
    contract = decision.contract or SOExtractContractList(data=[])
    markdown = render_summary_markdown(contract, _customer_name(customer_id))
    slots = [s.model_dump() for s in decision.ledger]
    to_seq = window[-1]["seq"]
    if pending:
        mongo.summaries().update_one(
            {"_id": pending["_id"]},
            {"$set": {"content": contract.model_dump(), "rendered_markdown": markdown,
                      "slots": slots, "to_seq": to_seq, "model_key": model_key},
             "$inc": {"revision": 1}})
        doc = mongo.summaries().find_one({"_id": pending["_id"]})
    else:
        doc = {"customer_id": customer_id, "status": "pending", "model_key": model_key,
               "from_seq": window[0]["seq"], "to_seq": to_seq, "revision": 0,
               "content": contract.model_dump(), "rendered_markdown": markdown,
               "slots": slots, "created_at": _now(), "approved_at": None}
        doc["_id"] = mongo.summaries().insert_one(doc).inserted_id

    card = _agent_msg(customer_id, decision.message + "\n\n" + markdown, "draft",
                      summary_id=str(doc["_id"]), summary_json=contract.model_dump_json(indent=2))
    return {"messages": [card], "summary": _summary_out(doc)}
