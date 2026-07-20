from datetime import datetime, timezone

from apps.api.db import mongo


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_seq(customer_id: str) -> int:
    last = mongo.messages().find_one(
        {"customer_id": customer_id}, sort=[("seq", -1)], projection={"seq": 1}
    )
    return (last["seq"] + 1) if last else 1


def _to_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def add_message(customer_id: str, role: str, body: str,
                kind: str = "chat", summary_id: str | None = None,
                summary_json: str | None = None) -> dict:
    doc = {
        "customer_id": customer_id,
        "seq": _next_seq(customer_id),
        "role": role,
        "kind": kind,
        "body": body,
        "summary_id": summary_id,
        "summary_json": summary_json,
        "created_at": _now(),
    }
    res = mongo.messages().insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_out(doc)


def list_messages(customer_id: str) -> list[dict]:
    cur = mongo.messages().find({"customer_id": customer_id}).sort("seq", 1)
    return [_to_out(d) for d in cur]


def messages_since(customer_id: str, seq: int, kinds: list[str] | None = None) -> list[dict]:
    filt: dict = {"customer_id": customer_id, "seq": {"$gt": seq}}
    if kinds is not None:
        filt["kind"] = {"$in": kinds}
    cur = mongo.messages().find(filt).sort("seq", 1)
    return [_to_out(d) for d in cur]


def chat_messages_since(customer_id: str, seq: int) -> list[dict]:
    return messages_since(customer_id, seq, kinds=["chat"])


def get_last_contract_seq(customer_id: str) -> int:
    doc = mongo.customers().find_one({"_id": customer_id}, projection={"last_contract_seq": 1})
    return int(doc["last_contract_seq"]) if doc else 0


def set_last_contract_seq(customer_id: str, seq: int) -> None:
    mongo.customers().update_one(
        {"_id": customer_id}, {"$set": {"last_contract_seq": seq, "updated_at": _now()}}
    )
