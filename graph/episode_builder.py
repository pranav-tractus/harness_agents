import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def infer_customer_id(path: Path) -> str:
    parts = path.parts
    if "customers" in parts:
        idx = parts.index("customers")
        return parts[idx + 1]
    if "downloaded_chats" in parts:
        try:
            data = json.loads(path.read_text())
            if "customer_id" in data:
                return str(data["customer_id"])
        except Exception:
            pass
        stem = path.stem
        chunks = stem.split("__")
        if len(chunks) >= 4:
            return chunks[-1]
    return "generic"


def _extract_chat_text(data: dict) -> tuple[str, int]:
    lines: list[str] = []
    timestamp = 0

    if "messages" in data:
        for msg in data["messages"]:
            speaker = msg.get("from_whom", "UNKNOWN")
            body = msg.get("body", "")
            lines.append(f"{speaker}: {body}")
            if not timestamp and msg.get("timestamp"):
                timestamp = int(msg["timestamp"])

    elif "chats" in data:
        arrays = data["chats"]
        target = arrays[1] if len(arrays) > 1 else arrays[0] if arrays else []
        for msg in target:
            if "body" in msg:
                speaker = msg.get("from_whom", "UNKNOWN")
                lines.append(f"{speaker}: {msg['body']}")
            elif "text" in msg and isinstance(msg["text"], dict):
                speaker = msg.get("from_name", "UNKNOWN")
                lines.append(f"{speaker}: {msg['text'].get('body', '')}")
            if not timestamp and msg.get("timestamp"):
                timestamp = int(msg["timestamp"])

    return "\n".join(lines), timestamp


def build_episode(path: Path, raw_data_dir: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    customer_id = infer_customer_id(path)

    # downloaded_chats: override with the customer_id field in JSON
    if "downloaded_chats" in path.parts and "customer_id" in data:
        customer_id = str(data["customer_id"])

    content, timestamp = _extract_chat_text(data)
    if not timestamp:
        timestamp = int(path.stat().st_mtime)

    source_id = str(path.relative_to(raw_data_dir).with_suffix(""))

    return {
        "source_id": source_id,
        "customer_id": customer_id,
        "timestamp": timestamp,
        "content": content,
    }
