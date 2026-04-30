"""Chat file loader and normalizer.

Supports two JSON formats found in raw_data/:
  - chats/: {"messages": [{"from_whom": "...", "body": "...", "timestamp": ...}]}
  - downloaded_chats/: {"chats": [[{msg}, ...], ...], "field_data": {...}, ...}

Produces a plain-text conversation string suitable for the extraction pipeline.
"""

import json
from pathlib import Path
from typing import Any

RAW_DATA_DIR = Path(__file__).parent / "raw_data"
CHATS_DIR = RAW_DATA_DIR / "chats"
DOWNLOADED_CHATS_DIR = RAW_DATA_DIR / "downloaded_chats"


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def list_chat_files() -> dict[str, list[Path]]:
    """Return all available chat JSON files grouped by source folder."""
    result: dict[str, list[Path]] = {"chats": [], "downloaded_chats": []}
    if CHATS_DIR.exists():
        result["chats"] = sorted(CHATS_DIR.glob("*.json"))
    if DOWNLOADED_CHATS_DIR.exists():
        result["downloaded_chats"] = sorted(DOWNLOADED_CHATS_DIR.glob("*.json"))
    return result


# ---------------------------------------------------------------------------
# Sequence numbering
# ---------------------------------------------------------------------------

def add_seq_numbers(messages: list[dict]) -> list[dict]:
    """Assign a `seq` field to each message where seq=0 is the oldest.

    Assumes the input list is already in chronological order (oldest first),
    as stored in the raw JSON exports.
    """
    return [{**msg, "seq": idx} for idx, msg in enumerate(messages)]


# ---------------------------------------------------------------------------
# Format-specific parsers
# ---------------------------------------------------------------------------

def _parse_chats_format(data: dict[str, Any]) -> str:
    """Parse the simple chats/ format.

    Input shape:
        {"messages": [{"from_whom": "(TEAM1)", "body": "...", "timestamp": 123}]}
    """
    messages = add_seq_numbers(data.get("messages", []))
    lines: list[str] = []
    for msg in messages:
        speaker = msg.get("from_whom", "UNKNOWN").strip("() ")
        body = (msg.get("body") or "").strip()
        if body:
            lines.append(f"[seq={msg['seq']}] {speaker}: {body}")
    return "\n".join(lines)


def _parse_downloaded_chats_format(data: dict[str, Any]) -> str:
    """Parse the downloaded_chats/ format (real WhatsApp exports).

    Input shape:
        {
          "chat_name": "...",
          "chats": [[{msg}, ...], ...],   # grouped by date
          "field_data": {...}             # existing extraction (ignored here)
        }
    """
    chat_groups: list[list[dict]] = data.get("chats", [])
    chat_name = data.get("chat_name", "")

    # Flatten all groups into a single chronological list before sequencing
    flat: list[dict] = []
    for group in chat_groups:
        if not isinstance(group, list):
            continue
        for msg in group:
            if isinstance(msg, dict) and msg.get("type") == "text":
                body = (msg.get("text") or {}).get("body", "").strip()
                if body:
                    flat.append(msg)

    sequenced = add_seq_numbers(flat)

    lines: list[str] = []
    if chat_name:
        lines.append(f"Chat: {chat_name}")
        lines.append("")

    for msg in sequenced:
        body: str = (msg.get("text") or {}).get("body", "").strip()
        from_name: str = msg.get("from_name", "")
        from_me: bool = msg.get("from_me", False)

        if from_name:
            speaker = from_name
        elif from_me:
            speaker = "ME"
        else:
            speaker = msg.get("from", "") or "UNKNOWN"

        lines.append(f"[seq={msg['seq']}] {speaker}: {body}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_chat_file(path: Path) -> dict[str, Any]:
    """Load a chat JSON file and return a dict with:

    - ``text``: normalized plain-text conversation string
    - ``format``: detected format ("chats" or "downloaded_chats")
    - ``raw``: original parsed JSON dict
    - ``field_data``: pre-existing extraction output if present, else None
    - ``meta``: dict of metadata (filename, chat_name, created_at, etc.)
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    # Detect format
    if "messages" in data and isinstance(data["messages"], list):
        fmt = "chats"
        text = _parse_chats_format(data)
    elif "chats" in data and isinstance(data["chats"], list):
        fmt = "downloaded_chats"
        text = _parse_downloaded_chats_format(data)
    else:
        # Fallback: dump the whole thing as text
        fmt = "unknown"
        text = json.dumps(data, indent=2)

    field_data = data.get("field_data")

    meta: dict[str, Any] = {
        "filename": path.name,
        "format": fmt,
        "chat_name": data.get("chat_name", ""),
        "created_at": data.get("created_at", ""),
        "customer_id": data.get("customer_id", ""),
        "whatsapp_group_id": data.get("whatsapp_group_id", ""),
    }

    return {
        "text": text,
        "format": fmt,
        "raw": data,
        "field_data": field_data,
        "meta": meta,
    }
