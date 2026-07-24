from datetime import date, datetime, timezone

from bson import ObjectId

from apps.api.db import mongo
from apps.api.models import (
    AgentDecision,
    cap_questions,
    is_ready,
    missing_agreement,
    render_summary_markdown,
)
from apps.api.services import (
    chat_graph_service,
    chat_service,
    product_matcher_service,
    summary_context_service,
)
from core.llm_client import call_llm
from core.models import SOExtractContractList


_SYSTEM_BASE = (
    "You are a neutral contract agent sitting in a group chat with a seller "
    "and a customer. Read the conversation and the grounding context, then "
    "return an AgentDecision.\n\n"
    "## Hard rules (apply to every field, every decision)\n"
    "1. **Chat is the only source of truth.** Reference blocks (customer "
    "profile, purchase history, product catalog) are for interpretation "
    "only — never copy their values into contract fields unless the chat "
    "explicitly confirms them.\n"
    "2. **Empty is a valid answer.** If a slot is not explicitly stated in "
    "the chat, leave it unresolved and record `source='unknown'`. Never "
    "guess, never infer.\n"
    "3. **Proposals are not agreements.** Counter-offers, asks, and "
    "unanswered messages are not `agreed_by` values. Only mark a slot "
    "`agreed_by` a party after an explicit acceptance signal from that "
    "party (\"confirmed\", \"ok\", \"agreed\", \"deal\", \"let's go\", or "
    "explicit acceptance of a counter-offer).\n"
    "4. **Verbatim strings.** Copy `packing`, `loading`, `shipping_method`, "
    "`shipping_address`, `description`, `ship_term` with the chat's exact "
    "spacing, casing, punctuation, and word order — no paraphrasing.\n"
    "5. **Dates are ISO 8601 (YYYY-MM-DD) or empty.** Never paraphrase a "
    "date as prose. For partial months use the last day of that month. "
    "For omitted years, use the current year unless the chat says "
    "otherwise. If unresolvable, leave empty.\n"
    "6. **Preserve units and currencies exactly.** No conversion (MT↔KG, "
    "USD↔INR, etc.). If the chat says \"USD 3.5 per KG\", record "
    "`unit_price=3.5, pricing_unit=\"USD/KG\"`.\n"
    "7. **`payment_date` is a date or an explicit payment-term phrase "
    "only** (e.g. \"Net 30 from delivery\", \"2026-03-15\"). Never copy "
    "shipping or document-handling notes into this field.\n\n"
    "## Agent-specific behavior (slot ledger + mode)\n"
    "- Maintain a per-slot ledger over: `description`, `quantity`, "
    "`unit_price`, `ship_term`, `shipping_address`, `packing`, `loading`, "
    "`payment_date`. For each slot record value, source "
    "(`chat|last_order|profile|inferred|unknown`), confidence, and "
    "`agreed_by` (which of seller/customer explicitly agreed).\n"
    "- Resolve soft slots (`shipping_address`, `packing`, `loading`, "
    "`payment_date`) silently from last orders / profile and mark them "
    "`source='inferred'`. Only ASK about critical slots (`description`, "
    "`quantity`, `unit_price`, `ship_term`) you cannot resolve; ask at "
    "most 3, directed to the party who can answer.\n"
    "- When all critical slots are known, set `mode='draft'` and fill "
    "`contract`. Set `ready_to_finalize=true` ONLY when every material "
    "slot is `agreed_by` both seller and customer; then set "
    "`mode='finalize'`. Never invent quantities, prices, or terms.\n"
    "- Keep the `message` field to one short sentence; never restate the "
    "full order details in `message` (the structured summary is rendered "
    "separately).\n\n"
    "IMPORTANT: Today is {today}. Resolve every relative date "
    "(\"next Friday\", \"end of month\", \"in two weeks\") against this "
    "date. Never emit a year different from the current year unless that "
    "year appears verbatim in the chat."
)

SYSTEM = _SYSTEM_BASE.format(today=date.today().isoformat())


def _chat_block(messages: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {m['body']}" for m in messages)


def _section(label: str, block: str | None) -> str:
    return f"## {label}\n{block}\n\n" if block else ""


def build_prompt(customer_name, messages, ctx, previous_json=None) -> str:
    prompt = (
        f"Customer: {customer_name}\n\n"
        + _section("Customer profile", ctx.get("profile_block"))
        + _section("Purchase history (last orders)", ctx.get("history_block"))
        + _section("Product catalog", ctx.get("product_block"))
    )
    if previous_json:
        prompt += f"## Previous draft (JSON)\n{previous_json}\n\n"
    prompt += (
        f"## Conversation\n{_chat_block(messages)}\n\n"
        "---\n\n"
        "Slots to track: description, quantity, unit_price, ship_term, "
        "shipping_address, packing, loading, payment_date.\n"
        "Return the AgentDecision as valid JSON conforming to the schema. "
        "No text before or after the JSON."
    )
    return prompt


def decide(
    customer_name, messages, ctx, model_key, *, previous_json=None, llm=None
) -> AgentDecision:
    llm = llm or call_llm
    prompt = build_prompt(customer_name, messages, ctx, previous_json)
    decision: AgentDecision = llm(
        prompt, AgentDecision, model_key, system_prompt=SYSTEM
    )
    decision = cap_questions(decision)
    if decision.mode == "finalize" and not decision.ready_to_finalize:
        decision.mode = "draft"
    return decision


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chat_title(chat_id: str) -> str:
    doc = mongo.chats().find_one({"_id": ObjectId(chat_id)}, projection={"title": 1})
    if doc and doc.get("title"):
        return doc["title"]
    return "Chat 1"


def _source_seqs(window: list[dict]) -> list[dict]:
    return [
        {"seq": m["seq"], "role": m["role"], "snippet": (m.get("body") or "")[:60]}
        for m in window
    ]


def _contract_dict(contract: SOExtractContractList) -> dict:
    return contract.model_dump()["data"][0] if contract.data else {"items": []}


def _customer_name(customer_id: str) -> str:
    doc = mongo.customers().find_one({"_id": customer_id}, projection={"name": 1})
    return doc["name"] if doc else customer_id


def _pending(customer_id: str, chat_id: str | None = None) -> dict | None:
    chat_id = chat_id or chat_service.ensure_active_chat(customer_id)
    return mongo.summaries().find_one(
        {"customer_id": customer_id, "chat_id": chat_id, "status": "pending"}
    )


def _summary_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def _agent_msg(customer_id, chat_id, body, kind, summary_id=None, summary_json=None):
    return chat_service.add_message(
        customer_id,
        chat_id,
        "agent",
        body,
        kind=kind,
        summary_id=summary_id,
        summary_json=summary_json,
    )


_AGENT_WINDOW_KINDS = ("chat", "question", "draft", "final")


def _resolved_product_block(matches) -> str:
    lines = []
    for m in matches:
        doc = mongo.products().find_one({"_id": m.resolved_code}) or {}
        name = m.canonical_name or doc.get("name") or m.resolved_code
        short = doc.get("short_description") or doc.get("description") or ""
        meta = doc.get("metadata") or {}
        line = f"- {m.resolved_code}: {name}"
        if short:
            line += f" — {short}"
        if meta:
            line += " [" + ", ".join(f"{k}={v}" for k, v in sorted(meta.items())) + "]"
        lines.append(line)
    return "Resolved products for this order:\n" + "\n".join(lines) if lines else ""


def _match_question(unresolved) -> str:
    parts = ["I need to pin down the product before drafting:"]
    for m in unresolved:
        if m.question:
            parts.append(f"- {m.question}")
        elif m.candidates:
            opts = " or ".join(f"{c.name} ({c.code})" for c in m.candidates)
            parts.append(f'- For "{m.mention}": did you mean {opts}?')
        else:
            parts.append(
                f'- I couldn\'t match "{m.mention}" to the catalog. Which product is it?'
            )
    return "\n".join(parts)


def _draft_to_seq(window: list[dict]) -> int:
    chat_seqs = [m["seq"] for m in window if m["kind"] == "chat"]
    return chat_seqs[-1] if chat_seqs else window[-1]["seq"]


def invoke(
    customer_id,
    model_key,
    *,
    decider=None,
    context_fn=None,
    graph_fn=None,
    matcher_fn=None,
) -> dict:
    decider = decider or decide
    context_fn = context_fn or summary_context_service.assemble
    matcher_fn = matcher_fn or product_matcher_service.resolve_products
    chat_id = chat_service.ensure_active_chat(customer_id)

    last = chat_service.get_last_contract_seq(chat_id)
    window = chat_service.messages_since(chat_id, last, kinds=list(_AGENT_WINDOW_KINDS))
    if not window:
        return {
            "messages": [
                _agent_msg(
                    customer_id,
                    chat_id,
                    "No new messages since the last contract.",
                    "chat",
                )
            ],
            "summary": None,
        }

    match_result = matcher_fn(customer_id, window, model_key)
    unresolved = match_result.unresolved()
    if unresolved:
        msg = _agent_msg(
            customer_id,
            chat_id,
            _match_question(unresolved),
            "question",
            summary_json=match_result.model_dump_json(indent=2),
        )
        return {"messages": [msg], "summary": None}

    ctx = context_fn(customer_id)
    resolved_block = _resolved_product_block(match_result.resolved())
    if resolved_block:
        ctx["product_block"] = resolved_block
    _match_docs = [m.model_dump() for m in match_result.matches]
    pending = _pending(customer_id, chat_id)
    previous_json = None
    if pending:
        previous_json = SOExtractContractList(**pending["content"]).model_dump_json(
            indent=2
        )
    decision = decider(
        _customer_name(customer_id), window, ctx, model_key, previous_json=previous_json
    )
    decision_json = decision.model_dump_json(indent=2)

    if decision.mode == "clarify":
        msg = _agent_msg(
            customer_id,
            chat_id,
            decision.message,
            "question",
            summary_json=decision_json,
        )
        return {"messages": [msg], "summary": None}

    # draft — the agent NEVER auto-finalizes; a ready decision still drafts.
    contract = decision.contract or SOExtractContractList(data=[])
    markdown = render_summary_markdown(contract, _customer_name(customer_id))
    body = decision.message.strip() + "\n\n" + markdown
    if decision.ready_to_finalize or decision.mode == "finalize":
        body += "\n\n_Ready to finalize — send `@agent confirm` to finalize._"
    slots = [s.model_dump() for s in decision.ledger]
    to_seq = _draft_to_seq(window)
    if pending:
        mongo.summaries().update_one(
            {"_id": pending["_id"]},
            {
                "$set": {
                    "content": contract.model_dump(),
                    "rendered_markdown": markdown,
                    "slots": slots,
                    "to_seq": to_seq,
                    "model_key": model_key,
                    "chat_id": chat_id,
                    "product_matches": _match_docs,
                },
                "$inc": {"revision": 1},
            },
        )
        doc = mongo.summaries().find_one({"_id": pending["_id"]})
    else:
        doc = {
            "customer_id": customer_id,
            "chat_id": chat_id,
            "status": "pending",
            "model_key": model_key,
            "from_seq": window[0]["seq"],
            "to_seq": to_seq,
            "revision": 0,
            "content": contract.model_dump(),
            "rendered_markdown": markdown,
            "slots": slots,
            "product_matches": _match_docs,
            "created_at": _now(),
            "approved_at": None,
        }
        doc["_id"] = mongo.summaries().insert_one(doc).inserted_id

    card = _agent_msg(
        customer_id,
        chat_id,
        body,
        "draft",
        summary_id=str(doc["_id"]),
        summary_json=decision_json,
    )
    return {"messages": [card], "summary": _summary_out(doc)}


def _persist_final(
    customer_id, chat_id, contract, slots, from_seq, to_seq, model_key
) -> dict:
    markdown = render_summary_markdown(contract, _customer_name(customer_id))
    doc = {
        "customer_id": customer_id,
        "chat_id": chat_id,
        "status": "approved",
        "model_key": model_key,
        "from_seq": from_seq,
        "to_seq": to_seq,
        "revision": 0,
        "content": contract.model_dump(),
        "rendered_markdown": markdown,
        "slots": slots,
        "created_at": _now(),
        "approved_at": _now(),
    }
    doc["_id"] = mongo.summaries().insert_one(doc).inserted_id
    return doc


def _finish_and_branch(
    customer_id: str, finished_chat_id: str, *, branch_fn=None
) -> dict:
    branch_fn = branch_fn or chat_graph_service.open_branch
    chat_service.finish_chat(finished_chat_id)
    new_chat = chat_service.start_new_chat(customer_id)
    branch_fn(customer_id, new_chat["id"], new_chat["title"], finished_chat_id)
    return new_chat


def finalize(
    customer_id,
    *,
    decision=None,
    window=None,
    model_key="",
    graph_fn=None,
    branch_fn=None,
) -> dict:
    graph_fn = graph_fn or chat_graph_service.write_contract
    chat_id = chat_service.ensure_active_chat(customer_id)
    window = window or chat_service.chat_messages_since(
        chat_id, chat_service.get_last_contract_seq(chat_id)
    )
    to_seq = (
        window[-1]["seq"] if window else chat_service.get_last_contract_seq(chat_id)
    )
    contract = (decision.contract if decision else None) or SOExtractContractList(
        data=[]
    )
    slots = [s.model_dump() for s in decision.ledger] if decision else []

    graph_fn(
        customer_id,
        chat_id,
        _chat_title(chat_id),
        _contract_dict(contract),
        slots,
        _source_seqs(window),
        to_seq,
    )
    doc = _persist_final(
        customer_id,
        chat_id,
        contract,
        slots,
        from_seq=(window[0]["seq"] if window else to_seq),
        to_seq=to_seq,
        model_key=model_key,
    )
    chat_service.set_last_contract_seq(chat_id, to_seq)
    mongo.summaries().delete_many(
        {"customer_id": customer_id, "chat_id": chat_id, "status": "pending"}
    )
    decision_json = (
        decision.model_dump_json(indent=2)
        if decision
        else contract.model_dump_json(indent=2)
    )
    msg = _agent_msg(
        customer_id,
        chat_id,
        (decision.message if decision else "Finalized.")
        + "\n\n"
        + doc["rendered_markdown"],
        "final",
        summary_id=str(doc["_id"]),
        summary_json=decision_json,
    )
    _finish_and_branch(customer_id, chat_id, branch_fn=branch_fn)
    return {"messages": [msg], "summary": _summary_out(doc)}


def approve(customer_id, *, graph_fn=None, branch_fn=None) -> dict:
    chat_id = chat_service.ensure_active_chat(customer_id)
    pending = _pending(customer_id, chat_id)
    if not pending:
        return {
            "messages": [
                _agent_msg(
                    customer_id,
                    chat_id,
                    "There's no draft to finalize yet. Send `@agent create sales order` first.",
                    "chat",
                )
            ],
            "summary": None,
        }
    if not is_ready(pending.get("slots", [])):
        missing = missing_agreement(pending.get("slots", []))
        body = (
            "Not ready to finalize. Still need both parties to agree on: "
            + ", ".join(missing)
            + "."
        )
        return {
            "messages": [_agent_msg(customer_id, chat_id, body, "chat")],
            "summary": None,
        }

    graph_fn = graph_fn or chat_graph_service.write_contract
    window = chat_service.chat_messages_since(chat_id, pending["from_seq"] - 1)
    contract = SOExtractContractList(**pending["content"])
    slots = pending.get("slots", [])
    graph_fn(
        customer_id,
        chat_id,
        _chat_title(chat_id),
        _contract_dict(contract),
        slots,
        _source_seqs(window),
        pending["to_seq"],
    )
    mongo.summaries().update_one(
        {"_id": pending["_id"]},
        {"$set": {"status": "approved", "approved_at": _now(), "chat_id": chat_id}},
    )
    chat_service.set_last_contract_seq(chat_id, pending["to_seq"])
    approved = mongo.summaries().find_one({"_id": pending["_id"]})
    msg = _agent_msg(
        customer_id,
        chat_id,
        "Approved and finalized.\n\n" + approved["rendered_markdown"],
        "final",
        summary_id=str(approved["_id"]),
        summary_json=contract.model_dump_json(indent=2),
    )
    _finish_and_branch(customer_id, chat_id, branch_fn=branch_fn)
    return {"messages": [msg], "summary": _summary_out(approved)}
