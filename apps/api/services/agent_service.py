from apps.api.models import AgentDecision, cap_questions

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
