"""Chat file loader and normalizer.

Supports three JSON formats found in ``raw_data/``:

- ``chats/``: ``{"messages": [{"from_whom": "...", "body": "...", "timestamp": ...}]}``
- ``chats/updates/``: ``{"messages": [...], "generated_summary": {...}, "updates": [...]}``
- ``downloaded_chats/``: ``{"chats": [[{msg}, ...], ...], "field_data": {...}, ...}``

Produces a plain-text conversation string suitable for the extraction pipeline,
plus optional ``generated_summary`` / ``updates`` payloads for the human-in-the-loop
update flow.
"""

import json
from pathlib import Path
from typing import Any

SYNTH_UPDATES_FEW_SHOT_MAX_STEPS_DEFAULT = 12

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = REPO_ROOT / "raw_data"
CHATS_DIR = RAW_DATA_DIR / "chats"
UPDATES_DIR = CHATS_DIR / "updates"
DOWNLOADED_CHATS_DIR = RAW_DATA_DIR / "downloaded_chats"


def list_chat_files() -> dict[str, list[Path]]:
    """Return all available chat JSON files grouped by source folder."""
    result: dict[str, list[Path]] = {"chats": [], "updates": [], "downloaded_chats": []}
    if CHATS_DIR.exists():
        result["chats"] = sorted(p for p in CHATS_DIR.glob("*.json"))
    if UPDATES_DIR.exists():
        result["updates"] = sorted(UPDATES_DIR.glob("*.json"))
    if DOWNLOADED_CHATS_DIR.exists():
        result["downloaded_chats"] = sorted(DOWNLOADED_CHATS_DIR.glob("*.json"))
    return result


def list_chat_files_for_dataset_root(dataset_root: Path) -> dict[str, list[Path]]:
    """Return chat files under a customer dataset root.

    Expected layout:
    - ``<root>/chats/*.json``
    - ``<root>/chats/updates/*.json``
    - ``<root>/downloaded_chats/*.json``
    """
    root = Path(dataset_root).expanduser().resolve()
    chats_dir = root / "chats"
    updates_dir = chats_dir / "updates"
    downloaded_dir = root / "downloaded_chats"
    result: dict[str, list[Path]] = {"chats": [], "updates": [], "downloaded_chats": []}
    if chats_dir.exists():
        result["chats"] = sorted(chats_dir.glob("*.json"))
    if updates_dir.exists():
        result["updates"] = sorted(updates_dir.glob("*.json"))
    if downloaded_dir.exists():
        result["downloaded_chats"] = sorted(downloaded_dir.glob("*.json"))
    return result


def labeled_raw_chat_paths() -> list[tuple[str, Path]]:
    """``(label, path)`` pairs for UIs: ``[chats] foo.json``, ``[updates] bar.json``, etc."""
    out: list[tuple[str, Path]] = []
    grouped = list_chat_files()
    for folder in ("chats", "downloaded_chats", "updates"):
        for p in grouped.get(folder, []):
            out.append((f"[{folder}] {p.name}", p))
    out.sort(key=lambda x: x[0].lower())
    return out


def labeled_chat_paths_for_globs(globs: list[str], root: Path | None = None) -> list[tuple[str, Path]]:
    """``(label, path)`` pairs for arbitrary glob patterns (e.g. agent few-shot pool).

    Labels are the path relative to ``root`` (default: repo root) so the
    dashboard can group multiselect entries by sub-folder.
    """
    base = Path(root or REPO_ROOT).resolve()
    seen: set[Path] = set()
    pairs: list[tuple[str, Path]] = []
    for pattern in globs:
        for path in sorted(base.glob(pattern)):
            resolved = path.resolve()
            if resolved in seen or not resolved.is_file():
                continue
            seen.add(resolved)
            try:
                label = str(resolved.relative_to(base))
            except ValueError:
                label = str(resolved)
            pairs.append((label, resolved))
    pairs.sort(key=lambda x: x[0].lower())
    return pairs


def add_seq_numbers(messages: list[dict]) -> list[dict]:
    """Assign a ``seq`` field to each message where ``seq=0`` is the oldest."""
    return [{**msg, "seq": idx} for idx, msg in enumerate(messages)]


def _parse_chats_format(data: dict[str, Any]) -> str:
    """Parse the simple ``chats/`` format."""
    messages = add_seq_numbers(data.get("messages", []))
    lines: list[str] = []
    for msg in messages:
        speaker = msg.get("from_whom", "UNKNOWN").strip("() ")
        body = (msg.get("body") or "").strip()
        if body:
            lines.append(f"[seq={msg['seq']}] {speaker}: {body}")
    return "\n".join(lines)


def _parse_downloaded_chats_format(data: dict[str, Any]) -> str:
    """Parse the ``downloaded_chats/`` format (real WhatsApp exports)."""
    chat_groups: list[list[dict]] = data.get("chats", [])
    chat_name = data.get("chat_name", "")

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


def load_chat_file(path: Path) -> dict[str, Any]:
    """Load a chat JSON file and return a normalized dict.

    Keys returned:
    - ``text``: normalized plain-text conversation string
    - ``format``: detected format (``chats``, ``updates``, ``downloaded_chats``, ``unknown``)
    - ``raw``: original parsed JSON dict
    - ``field_data``: pre-existing extraction output if present, else ``None``
    - ``generated_summary``: pre-baked summary (only for ``updates`` format), else ``None``
    - ``updates``: list of ``{instruction, expected_summary}`` entries, else ``[]``
    - ``meta``: dict of metadata (filename, chat_name, created_at, etc.)
    """
    path = Path(path).expanduser().resolve()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    upd_root = UPDATES_DIR.resolve()
    is_updates_dir = upd_root in path.parents or path.parent == upd_root
    has_messages = isinstance(data.get("messages"), list)
    has_chats = isinstance(data.get("chats"), list)

    if is_updates_dir and has_messages:
        fmt = "updates"
        text = _parse_chats_format(data)
    elif has_messages:
        fmt = "chats"
        text = _parse_chats_format(data)
    elif has_chats:
        fmt = "downloaded_chats"
        text = _parse_downloaded_chats_format(data)
    else:
        fmt = "unknown"
        text = json.dumps(data, indent=2)

    field_data = data.get("field_data")
    generated_summary = data.get("generated_summary") if fmt == "updates" else None
    updates = data.get("updates", []) if fmt == "updates" else []

    meta: dict[str, Any] = {
        "filename": path.name,
        "format": fmt,
        "chat_name": data.get("chat_name", ""),
        "created_at": data.get("created_at", ""),
        "customer_id": data.get("customer_id", ""),
        "whatsapp_group_id": data.get("whatsapp_group_id", ""),
        "source_chat": data.get("source_chat", "") if fmt == "updates" else "",
        "description": data.get("description", "") if fmt == "updates" else "",
        "realism_flags": data.get("realism_flags", []),
        "complexity_tier": data.get("complexity_tier", ""),
    }

    return {
        "text": text,
        "format": fmt,
        "raw": data,
        "field_data": field_data,
        "generated_summary": generated_summary,
        "updates": updates,
        "meta": meta,
    }


def _normalize_to_extract_list_shape(gold: dict[str, Any]) -> dict[str, Any]:
    """Wrap legacy ``field_data`` (single contract) as ``SOExtractContractList`` JSON."""
    if isinstance(gold.get("data"), list):
        return gold
    if isinstance(gold.get("items"), list):
        return {"data": [gold]}
    return gold


def _gold_dict_for_extraction_few_shot(loaded: dict[str, Any]) -> dict[str, Any] | None:
    fd = loaded.get("field_data")
    if isinstance(fd, dict) and fd:
        return _normalize_to_extract_list_shape(fd)
    if loaded.get("format") == "updates":
        gs = loaded.get("generated_summary")
        if isinstance(gs, dict) and gs:
            return _normalize_to_extract_list_shape(gs)
    return None


def _short_repo_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def build_extraction_few_shot_from_paths(paths: list[Path]) -> list[dict[str, Any]]:
    """Build rows for ``extraction.j2`` from JSON chat files.

    Skips files without usable gold output (``field_data`` or, for ``updates/``,
    ``generated_summary``). Downloaded exports often store a single contract in
    ``field_data``; it is wrapped as ``{"data": [contract]}`` when needed.
    """
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            loaded = load_chat_file(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        gold = _gold_dict_for_extraction_few_shot(loaded)
        if gold is None:
            continue
        text = (loaded.get("text") or "").strip()
        if not text:
            continue
        label = _short_repo_path(path)
        rows.append(
            {
                "input_text": text,
                "prompt_text": (
                    f"Few-shot reference from {label} "
                    "(assistant JSON from field_data or generated_summary; not a stored LLM prompt)."
                ),
                "output_json": json.dumps(gold, indent=2, ensure_ascii=False),
            }
        )
    return rows


def load_synthetic_update_few_shot_examples(
    max_steps: int = SYNTH_UPDATES_FEW_SHOT_MAX_STEPS_DEFAULT,
    paths: list[Path] | None = None,
) -> list[dict[str, Any]]:
    """Turn ``raw_data/chats/updates/*.json`` scenarios into update few-shot rows."""
    examples: list[dict[str, Any]] = []
    if max_steps <= 0:
        return examples
    if paths is not None:
        file_iter = list(paths)
    elif UPDATES_DIR.exists():
        file_iter = sorted(UPDATES_DIR.glob("*.json"))
    else:
        return examples

    for path in sorted(file_iter, key=lambda p: str(p)):
        loaded = load_chat_file(path)
        if loaded["format"] != "updates":
            continue
        generated = loaded.get("generated_summary")
        if not isinstance(generated, dict):
            continue
        chat_text = (loaded.get("text") or "").strip()
        prev: dict[str, Any] = generated

        for upd in loaded.get("updates") or []:
            if len(examples) >= max_steps:
                return examples
            if not isinstance(upd, dict):
                continue
            instruction = (upd.get("instruction") or "").strip()
            expected = upd.get("expected_summary")
            if expected is None or not isinstance(expected, dict):
                continue
            examples.append(
                {
                    "previous_summary_json": json.dumps(prev, indent=2, ensure_ascii=False),
                    "update_instruction": instruction,
                    "updated_summary_json": json.dumps(expected, indent=2, ensure_ascii=False),
                    "recent_chat_messages": chat_text or None,
                }
            )
            prev = expected

    return examples
