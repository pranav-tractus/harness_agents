from datetime import date

from core.llm_client import call_llm
from core.models import SOExtractContractList, SOUpdateContractList

_SYSTEM_BASE = (
    "You are a specialized Contract Data Extraction Agent with 20+ years of "
    "experience converting unstructured business chat logs (WhatsApp, email, "
    "messenger) into a single, precise, structured JSON contract object.\n\n"
    "## Your role\n"
    "- Act as a neutral analyst: extract only terms both sides have explicitly "
    "agreed to.\n"
    "- Output valid JSON only. No commentary, no markdown wrappers, no extra "
    "fields.\n"
    "- Preserve units, currencies, and numeric precision exactly as stated in "
    "the conversation.\n\n"
    "## Hard rules (apply to every field, every time)\n"
    "1. **Chat is the only source of truth.** Reference blocks (customer "
    "profile, purchase history, product catalog) are for interpretation only "
    "— never copy their values into output fields unless the chat explicitly "
    "confirms them.\n"
    "2. **Empty is a valid answer.** If a field is not explicitly stated in "
    "the chat, return `null` or an empty string per the schema. Never guess, "
    "never infer from context. A partial but accurate extraction is strictly "
    "preferred over a complete but invented one.\n"
    "3. **Proposals are not agreements.** Counter-offers, asks, and unanswered "
    "messages are not extractable. Only the final, mutually accepted value. "
    "Confirmation signals: \"confirmed\", \"ok\", \"agreed\", \"deal\", "
    "\"let's go\", or explicit acceptance of a counter-offer.\n"
    "4. **Verbatim strings.** Copy `packing`, `loading`, `shipping_method`, "
    "`delivery_terms`, `billing_address`, `shipping_address`, `description`, "
    "`vendor_name`, `ship_term` with the chat's exact spacing, casing, "
    "punctuation, and word order — no paraphrasing.\n"
    "5. **Dates are ISO 8601 (YYYY-MM-DD) or empty.** Never paraphrase a date "
    "as prose. For partial months (e.g. \"November 2026\") use the last day "
    "of the named month (2026-11-30). For omitted years, use the current year "
    "unless the chat says otherwise. If unresolvable, leave empty.\n"
    "6. **Preserve units and currencies exactly.** No conversion (MT↔KG, "
    "gallon↔litre, USD↔INR, etc.). If the chat says \"USD 3.5 per KG\", "
    "write `unit_price=3.5, pricing_unit=\"USD/KG\"`.\n"
    "7. **`payment_date` is a date or an explicit payment-term phrase only** "
    "(e.g. \"Net 30 from delivery\", \"2026-03-15\"). Never copy boilerplate "
    "like \"Against scan copies of documents\" or document-handling notes "
    "into this field. If unsure, leave empty.\n"
    "8. **No inference from context.** Do not deduce values from common "
    "knowledge, industry defaults, or by combining unrelated statements. If "
    "the chat does not say it, do not write it.\n\n"
    "IMPORTANT: Today is {today}. Resolve every relative date "
    "(\"next Friday\", \"end of month\", \"in two weeks\") against this "
    "date. Never emit a year different from the current year unless that "
    "year appears verbatim in the chat."
)


def _system() -> str:
    return _SYSTEM_BASE.format(today=date.today().isoformat())


def _chat_block(messages: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {m['body']}" for m in messages)


def _section(label: str, block: str | None) -> str:
    return f"## {label}\n{block}\n\n" if block else ""


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
        + f"## Chat since last contract\n{_chat_block(messages)}\n\n"
        "---\n\n"
        "Produce the sales order contract list from the chat above. "
        "Return only valid JSON matching the SOExtractContractList schema. "
        "No text, explanation, or markdown before or after the JSON."
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
        + f"## Previous summary (JSON)\n{previous.model_dump_json(indent=2)}\n\n"
        + f"## Chat since last contract\n{_chat_block(messages)}\n\n"
        + f"## Update instruction (from human reviewer)\n{instructions}\n\n"
        "---\n\n"
        "Apply the human's update instruction to the Previous summary and "
        "return the complete updated JSON conforming to the "
        "SOUpdateContractList schema. Preserve every unchanged field "
        "byte-for-byte. Only modify the specific fields the instruction "
        "explicitly names. Never invent items or fields. "
        "No text before or after the JSON."
    )
    return llm(prompt, SOUpdateContractList, model_key, system_prompt=_system())
