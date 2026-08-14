from datetime import datetime, timezone

from bson import ObjectId

from apps.api.db import mongo


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chat_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def create_chat(customer_id: str, title: str, channel: str = "whatsapp") -> dict:
    doc = {
        "customer_id": customer_id,
        "title": title,
        "status": "active",
        "channel": channel,
        "created_at": _now(),
        "last_activity": _now(),
        "last_contract_seq": 0,
    }
    doc["_id"] = mongo.chats().insert_one(doc).inserted_id
    return _chat_out(doc)


def ensure_default_chat(customer_id: str) -> str:
    existing = mongo.chats().find_one(
        {"customer_id": customer_id}, sort=[("created_at", 1)]
    )
    if existing:
        return str(existing["_id"])
    return create_chat(customer_id, "Chat 1")["id"]


def _chat_count(customer_id: str) -> int:
    return mongo.chats().count_documents({"customer_id": customer_id})


def active_chat(customer_id: str) -> dict | None:
    return mongo.chats().find_one(
        {"customer_id": customer_id, "status": {"$ne": "finished"}},
        sort=[("created_at", -1)],
    )


def start_new_chat(customer_id: str) -> dict:
    return create_chat(customer_id, f"Chat {_chat_count(customer_id) + 1}")


def ensure_active_chat(customer_id: str) -> str:
    doc = active_chat(customer_id)
    return str(doc["_id"]) if doc else start_new_chat(customer_id)["id"]


def finish_chat(chat_id: str) -> None:
    mongo.chats().update_one(
        {"_id": ObjectId(chat_id)},
        {"$set": {"status": "finished", "last_activity": _now()}},
    )


def all_messages(customer_id: str) -> list[dict]:
    chats = list(mongo.chats().find({"customer_id": customer_id}).sort("created_at", 1))
    order = {str(c["_id"]): i for i, c in enumerate(chats)}
    status = {str(c["_id"]): c.get("status", "active") for c in chats}
    msgs = list(mongo.messages().find({"customer_id": customer_id}))
    msgs.sort(key=lambda m: (order.get(m["chat_id"], len(order)), m["seq"]))
    out = []
    for m in msgs:
        d = _to_out(m)
        d["chat_status"] = status.get(m["chat_id"], "active")
        out.append(d)
    return out


def _next_seq(chat_id: str) -> int:
    last = mongo.messages().find_one(
        {"chat_id": chat_id}, sort=[("seq", -1)], projection={"seq": 1}
    )
    return (last["seq"] + 1) if last else 1


def _to_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def add_message(
    customer_id, chat_id, role, body, kind="chat", summary_id=None, summary_json=None
) -> dict:
    doc = {
        "customer_id": customer_id,
        "chat_id": chat_id,
        "seq": _next_seq(chat_id),
        "role": role,
        "kind": kind,
        "body": body,
        "summary_id": summary_id,
        "summary_json": summary_json,
        "created_at": _now(),
    }
    doc["_id"] = mongo.messages().insert_one(doc).inserted_id
    mongo.chats().update_one(
        {"_id": ObjectId(chat_id)}, {"$set": {"last_activity": _now()}}
    )
    return _to_out(doc)


def messages_since(chat_id, seq, kinds=None) -> list[dict]:
    filt: dict = {"chat_id": chat_id, "seq": {"$gt": seq}}
    if kinds is not None:
        filt["kind"] = {"$in": kinds}
    cur = mongo.messages().find(filt).sort("seq", 1)
    return [_to_out(d) for d in cur]


def chat_messages_since(chat_id, seq) -> list[dict]:
    return messages_since(chat_id, seq, kinds=["chat"])


def get_last_contract_seq(chat_id) -> int:
    doc = mongo.chats().find_one(
        {"_id": ObjectId(chat_id)}, projection={"last_contract_seq": 1}
    )
    return int(doc["last_contract_seq"]) if doc else 0


def set_last_contract_seq(chat_id, seq) -> None:
    mongo.chats().update_one(
        {"_id": ObjectId(chat_id)},
        {"$set": {"last_contract_seq": seq, "last_activity": _now()}},
    )
