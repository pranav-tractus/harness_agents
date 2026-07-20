from datetime import datetime, timezone

from apps.api.db import mongo
from apps.api.models import render_summary_markdown
from apps.api.services import agent_service, chat_service
from apps.api.services import chat_graph_service, summary_context_service, summary_service
from core.models import SOExtractContractList


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pending_summary(customer_id: str) -> dict | None:
    return mongo.summaries().find_one({"customer_id": customer_id, "status": "pending"})


def _summary_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def _assistant(customer_id, chat_id, body, summary_id=None, summary_json=None) -> dict:
    return chat_service.add_message(customer_id, chat_id, "assistant", body,
                                    kind="summary" if summary_id else "chat",
                                    summary_id=summary_id, summary_json=summary_json)


def _customer_name(customer_id: str) -> str:
    doc = mongo.customers().find_one({"_id": customer_id}, projection={"name": 1})
    return doc["name"] if doc else customer_id


def _chat_title(chat_id: str) -> str:
    from bson import ObjectId
    from apps.api.db import mongo
    doc = mongo.chats().find_one({"_id": ObjectId(chat_id)}, projection={"title": 1})
    if doc and doc.get("title"):
        return doc["title"]
    return "Chat 1"


def _source_seqs(window: list[dict]) -> list[dict]:
    return [{"seq": m["seq"], "role": m["role"], "snippet": (m.get("body") or "")[:60]} for m in window]


def dispatch(customer_id, command, args, model_key,
             *, graph_fn=None, summary_gen=None, summary_revise=None, context_fn=None) -> dict:
    graph_fn = graph_fn or chat_graph_service.write_contract
    summary_gen = summary_gen or summary_service.generate
    summary_revise = summary_revise or summary_service.revise
    context_fn = context_fn or summary_context_service.assemble
    chat_id = chat_service.ensure_default_chat(customer_id)

    if command == "create-sales-order":
        return _create(customer_id, chat_id, model_key, graph_fn, summary_gen, context_fn)
    if command == "edit":
        return _edit(customer_id, chat_id, args, model_key, summary_revise, context_fn)
    if command == "approve":
        return _approve(customer_id)
    msg = _assistant(customer_id, chat_id, f"Unknown command: /{command}")
    return {"messages": [msg], "summary": None}


def _create(customer_id, chat_id, model_key, graph_fn, summary_gen, context_fn) -> dict:
    if _pending_summary(customer_id):
        msg = _assistant(customer_id, chat_id,
                         "A summary is already pending. Use /approve or /edit before creating a new one.")
        return {"messages": [msg], "summary": None}

    last = chat_service.get_last_contract_seq(chat_id)
    window = chat_service.chat_messages_since(chat_id, last)
    if not window:
        msg = _assistant(customer_id, chat_id, "No new messages since the last contract.")
        return {"messages": [msg], "summary": None}

    to_seq = window[-1]["seq"]
    # Step A — graph (must complete before Step B)
    graph_fn(customer_id, chat_id, _chat_title(chat_id), {"items": []}, [],
             _source_seqs(window), to_seq)

    # Step B — summary (grounded on assembled graph context)
    name = _customer_name(customer_id)
    ctx = context_fn(customer_id)
    summary: SOExtractContractList = summary_gen(
        name, window, ctx["product_block"], model_key,
        profile_block=ctx["profile_block"], history_block=ctx["history_block"],
    )
    markdown = render_summary_markdown(summary, name)
    summary_json = summary.model_dump_json(indent=2)
    doc = {
        "customer_id": customer_id, "status": "pending", "model_key": model_key,
        "from_seq": window[0]["seq"], "to_seq": to_seq, "revision": 0,
        "content": summary.model_dump(), "rendered_markdown": markdown,
        "created_at": _now(), "approved_at": None,
    }
    sid = mongo.summaries().insert_one(doc).inserted_id
    doc["_id"] = sid
    card = _assistant(customer_id, chat_id, markdown, summary_id=str(sid), summary_json=summary_json)
    return {"messages": [card], "summary": _summary_out(doc)}


def _edit(customer_id, chat_id, args, model_key, summary_revise, context_fn) -> dict:
    pending = _pending_summary(customer_id)
    if not pending:
        return {"messages": [_assistant(customer_id, chat_id, "No pending summary to edit.")], "summary": None}
    if not args:
        return {"messages": [_assistant(customer_id, chat_id, "Provide edit instructions: /edit <instructions>")],
                "summary": None}

    name = _customer_name(customer_id)
    window = chat_service.chat_messages_since(chat_id, pending["from_seq"] - 1)
    # Stored content shares the core contract-list layout regardless of which
    # schema produced it, so it round-trips through SOExtractContractList for the
    # prompt's "previous summary" block.
    previous = SOExtractContractList(**pending["content"])
    ctx = context_fn(customer_id)
    revised = summary_revise(
        name, previous, args, window, model_key,
        product_block=ctx["product_block"], profile_block=ctx["profile_block"],
        history_block=ctx["history_block"],
    )
    markdown = render_summary_markdown(revised, name)
    summary_json = revised.model_dump_json(indent=2)
    mongo.summaries().update_one(
        {"_id": pending["_id"]},
        {"$set": {"content": revised.model_dump(), "rendered_markdown": markdown,
                  "model_key": model_key},
         "$inc": {"revision": 1}},
    )
    updated = mongo.summaries().find_one({"_id": pending["_id"]})
    card = _assistant(customer_id, chat_id, markdown, summary_id=str(pending["_id"]), summary_json=summary_json)
    return {"messages": [card], "summary": _summary_out(updated)}


def _approve(customer_id, *, graph_fn=None) -> dict:
    return agent_service.approve(customer_id, graph_fn=graph_fn)


def invoke_agent(customer_id, model_key) -> dict:
    return agent_service.invoke(customer_id, model_key)


def approve(customer_id) -> dict:
    return agent_service.approve(customer_id)
