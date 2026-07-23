from datetime import date

from core.llm_client import call_llm
from core.models import SOExtractContractList, SOUpdateContractList

_SYSTEM_BASE = (
    "You extract a structured sales order from a customer chat, matching the "
    "provided JSON schema exactly. Prefer values explicitly stated in the chat. "
    "When a field is not stated in the chat, you may fill it from the provided "
    "customer profile, purchase history, or product catalog context, preferring "
    "the chat when they conflict. Only use products from the provided catalog. "
    "Group line items into one contract per distinct purchase order. Leave string "
    "fields empty and numeric fields null when a value appears in none of these "
    "sources. Do not invent quantities, prices, or terms. "
    "Normalize all dates to ISO 8601 (YYYY-MM-DD). For partial months use the "
    "last day of that month. Today is {today}."
)


def _system() -> str:
    return _SYSTEM_BASE.format(today=date.today().isoformat())


def _chat_block(messages: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {m['body']}" for m in messages)


def _section(label: str, block: str | None) -> str:
    return f"{label}:\n{block}\n\n" if block else ""


def generate(
    customer_name,
    messages,
    product_block,
    model_key,
    *,
    profile_block=None,
    history_block=None,
    llm=None,
) -> SOExtractContractList:
    llm = llm or call_llm
    prompt = (
        f"Customer: {customer_name}\n\n"
        + _section("Customer profile", profile_block)
        + _section("Purchase history", history_block)
        + _section("Product catalog", product_block)
        + f"Chat since last contract:\n{_chat_block(messages)}\n\n"
        "Produce the sales order contract list."
    )
    return llm(prompt, SOExtractContractList, model_key, system_prompt=_system())


def revise(
    customer_name,
    previous,
    instructions,
    messages,
    model_key,
    *,
    product_block=None,
    profile_block=None,
    history_block=None,
    llm=None,
) -> SOUpdateContractList:
    llm = llm or call_llm
    prompt = (
        f"Customer: {customer_name}\n\n"
        + _section("Customer profile", profile_block)
        + _section("Purchase history", history_block)
        + _section("Product catalog", product_block)
        + f"Previous summary (JSON):\n{previous.model_dump_json(indent=2)}\n\n"
        + f"Chat since last contract:\n{_chat_block(messages)}\n\n"
        + f"Apply these edit instructions and return the corrected contract list:\n{instructions}"
    )
    return llm(prompt, SOUpdateContractList, model_key, system_prompt=_system())
