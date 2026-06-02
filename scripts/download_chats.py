"""Download WhatsApp chat JSON from S3 into raw_data/downloaded_chats/.

Default input is ``Public Contracts May 29 2026.json``. For each contract row,
finds S3 message JSON whose key or LastModified date matches the contract
``created_at`` date, validates customer/group identifiers, and writes wrapped
files named:

    {NN}__{YYYY-MM-DD}__{sanitized_group_id}__{customer_id}.json

Run:

    export IS_LOCAL=true
    export ACCESS_KEY=...
    export SECRET_KEY=...
    python scripts/download_chats.py --fresh
    python scripts/download_chats.py --fresh --llm-msg-only
    python scripts/download_chats.py --fresh --folder-matched-only
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.utils import S3_BUCKET, create_boto3_client

logger = logging.getLogger(__name__)

MESSAGES_PREFIX = "messages/"
DATE_BASENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})$")
LLM_MSG_BASENAME = "llm_msg.json"
SKIP_BASENAMES = frozenset({LLM_MSG_BASENAME})
DEFAULT_CONTRACTS_PATH = ROOT_DIR / "Public Contracts May 29 2026.json"


@dataclass
class ContractRow:
    whatsapp_group_id: str
    customer_id: str
    organization_id: str
    created_at: str
    field_data: dict[str, Any] | None
    po_ref_no: str
    contract_id: str
    status: str


@dataclass
class ChatPair:
    whatsapp_group_id: str
    organization_id: str


@dataclass
class DownloadStats:
    rows_processed: int = 0
    groups_scanned: int = 0
    s3_json_found: int = 0
    downloaded: int = 0
    matched: int = 0
    no_match: int = 0
    skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)
    output_paths: list[str] = field(default_factory=list)

    def record_skip(self, reason: str) -> None:
        self.skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1


def parse_contracts_json(path: Path, *, signed_only: bool = True) -> list[ContractRow]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}")

    rows: list[ContractRow] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", ""))
        if signed_only and status != "SIGNED":
            continue

        raw_customer_id = item.get("customer_id")
        organization_id = str(item.get("organization_id") or "")
        filename_id = (
            str(raw_customer_id)
            if raw_customer_id not in (None, "")
            else organization_id
        )
        if not filename_id:
            logger.warning(
                "Skipping contract %s: missing customer_id and organization_id",
                item.get("id", "<unknown>"),
            )
            continue

        raw_field_data = item.get("field_data")
        field_data = raw_field_data if isinstance(raw_field_data, dict) and raw_field_data else None

        rows.append(
            ContractRow(
                whatsapp_group_id=str(item["whatsapp_group_id"]),
                customer_id=filename_id,
                organization_id=organization_id,
                created_at=str(item["created_at"]),
                field_data=field_data,
                po_ref_no=str(item.get("po_ref_no") or ""),
                contract_id=str(item.get("id") or ""),
                status=status,
            )
        )
    return rows


def unique_groups_from_contracts(rows: list[ContractRow]) -> list[ChatPair]:
    seen: set[str] = set()
    pairs: list[ChatPair] = []
    for row in rows:
        if row.whatsapp_group_id in seen:
            continue
        seen.add(row.whatsapp_group_id)
        pairs.append(ChatPair(row.whatsapp_group_id, row.organization_id))
    return pairs


def created_date_from_contract(created_at: str) -> str:
    return created_at.split("T")[0].split(" ")[0]


def deep_contains(value: Any, needle: str) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        return any(deep_contains(v, needle) for v in value.values())
    if isinstance(value, list):
        return any(deep_contains(v, needle) for v in value)
    return False


def _looks_like_message(msg: Any) -> bool:
    if not isinstance(msg, dict):
        return False
    if msg.get("type") in {"text", "image", "document", "audio", "video", "sticker"}:
        return True
    if "timestamp" in msg and ("text" in msg or "body" in msg or "from" in msg):
        return True
    if "from_whom" in msg and "body" in msg:
        return True
    return False


def extract_messages(raw: Any) -> list[dict] | None:
    """Return message list from supported S3 JSON shapes, or None if invalid."""
    if isinstance(raw, list):
        messages = [m for m in raw if isinstance(m, dict) and _looks_like_message(m)]
        return messages or None

    if not isinstance(raw, dict):
        return None

    if isinstance(raw.get("messages"), list):
        messages = [m for m in raw["messages"] if isinstance(m, dict) and _looks_like_message(m)]
        return messages or None

    chats = raw.get("chats")
    if isinstance(chats, list) and chats:
        first = chats[0]
        if isinstance(first, list):
            messages = [m for m in first if isinstance(m, dict) and _looks_like_message(m)]
            return messages or None

    return None


def sanitize_group_id(whatsapp_group_id: str) -> str:
    return re.sub(r"[@.]", "_", whatsapp_group_id)


def created_date_from_key(key: str, last_modified: datetime | None) -> str:
    basename = Path(key).stem
    match = DATE_BASENAME_RE.match(basename)
    if match:
        return match.group(1)
    if last_modified is not None:
        return last_modified.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_filename(
    row_index: int,
    created_date: str,
    whatsapp_group_id: str,
    customer_id: str,
    suffix: str = "",
) -> str:
    safe_group = sanitize_group_id(whatsapp_group_id)
    stem = f"{row_index:02d}__{created_date}__{safe_group}__{customer_id}"
    if suffix:
        stem = f"{stem}__{suffix}"
    return f"{stem}.json"


def list_objects_with_prefix(s3_client: Any, prefix: str) -> list[dict[str, Any]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        objects.extend(page.get("Contents") or [])
    return objects


def select_keys_for_row(
    objects: list[dict[str, Any]],
    group_id: str,
    row_date: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for obj in objects:
        key = obj["Key"]
        if not key.lower().endswith(".json"):
            continue
        key_date_match = row_date in key
        last_modified = obj.get("LastModified")
        modified_date_match = (
            isinstance(last_modified, datetime)
            and last_modified.astimezone(timezone.utc).strftime("%Y-%m-%d") == row_date
        )
        group_match = group_id in key
        if (key_date_match or modified_date_match) and group_match:
            selected.append(obj)
    return selected


def identifier_match(
    key: str,
    payload: Any,
    *,
    customer_id: str,
    group_id: str,
    organization_id: str = "",
    po_ref_no: str = "",
) -> bool:
    needles = [n for n in (customer_id, group_id, organization_id, po_ref_no) if n]
    if any(needle in key or deep_contains(payload, needle) for needle in needles):
        return True
    # Signed contracts without customer_id still match group-scoped date files.
    return not customer_id and group_id in key


def _relative_parts(group_prefix: str, key: str) -> list[str] | None:
    if not key.startswith(group_prefix):
        return None
    relative = key[len(group_prefix) :]
    if not relative:
        return None
    return relative.split("/")


def list_message_json_keys(
    s3_client: Any,
    whatsapp_group_id: str,
    *,
    llm_msg_only: bool = False,
    folder_matched_only: bool = False,
) -> list[dict[str, Any]]:
    prefix = f"{MESSAGES_PREFIX}{whatsapp_group_id}/"
    paginator = s3_client.get_paginator("list_objects_v2")
    json_objects: list[dict[str, Any]] = []
    subfolder_names: set[str] = set()

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            parts = _relative_parts(prefix, key)
            if not parts:
                continue
            if len(parts) > 1 and parts[0]:
                subfolder_names.add(parts[0])
            if not key.lower().endswith(".json"):
                continue
            json_objects.append(obj)

    if llm_msg_only:
        objects = [obj for obj in json_objects if Path(obj["Key"]).name == LLM_MSG_BASENAME]
        if len(objects) > 1:
            direct_key = f"{prefix}{LLM_MSG_BASENAME}"
            direct = [obj for obj in objects if obj["Key"] == direct_key]
            if direct:
                return direct
            return [min(objects, key=lambda o: o["Key"].count("/"))]
        return objects

    if folder_matched_only:
        objects: list[dict[str, Any]] = []
        for obj in json_objects:
            key = obj["Key"]
            parts = _relative_parts(prefix, key)
            if not parts or len(parts) != 1:
                continue
            basename = parts[0]
            if basename in SKIP_BASENAMES:
                continue
            if Path(basename).stem in subfolder_names:
                objects.append(obj)
        return sorted(objects, key=lambda o: o["Key"])

    return [
        obj
        for obj in json_objects
        if Path(obj["Key"]).name not in SKIP_BASENAMES
    ]


def download_object_body(s3_client: Any, key: str) -> bytes:
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    return response["Body"].read()


def build_s3_match(s3_object: dict[str, Any]) -> dict[str, Any]:
    key = s3_object["Key"]
    last_modified = s3_object.get("LastModified")
    if isinstance(last_modified, datetime):
        last_modified_str = last_modified.astimezone(timezone.utc).isoformat()
    else:
        last_modified_str = datetime.now(timezone.utc).isoformat()
    return {
        "bucket": S3_BUCKET,
        "key": key,
        "last_modified": last_modified_str,
        "size": s3_object.get("Size", 0),
    }


def build_contract_wrapped_output(
    *,
    row_index: int,
    row: ContractRow,
    s3_matches: list[dict[str, Any]],
    chat_groups: list[list[dict]],
) -> dict[str, Any]:
    row_date = created_date_from_contract(row.created_at)
    wrapped: dict[str, Any] = {
        "row_index": row_index,
        "whatsapp_group_id": row.whatsapp_group_id,
        "customer_id": row.customer_id,
        "organization_id": row.organization_id,
        "contract_id": row.contract_id,
        "po_ref_no": row.po_ref_no,
        "status": row.status,
        "created_at": row.created_at,
        "created_date": row_date,
        "s3_matches": s3_matches,
        "chats": chat_groups,
    }
    if row.field_data is not None:
        wrapped["field_data"] = row.field_data
    return wrapped


def build_wrapped_output(
    *,
    row_index: int,
    whatsapp_group_id: str,
    customer_id: str,
    messages: list[dict],
    s3_object: dict[str, Any],
) -> dict[str, Any]:
    key = s3_object["Key"]
    last_modified = s3_object.get("LastModified")
    if isinstance(last_modified, datetime):
        created_at = last_modified.astimezone(timezone.utc).isoformat()
    else:
        created_at = datetime.now(timezone.utc).isoformat()

    created_date = created_date_from_key(key, last_modified if isinstance(last_modified, datetime) else None)

    return {
        "row_index": row_index,
        "whatsapp_group_id": whatsapp_group_id,
        "customer_id": customer_id,
        "created_at": created_at,
        "created_date": created_date,
        "s3_matches": [build_s3_match(s3_object)],
        "chats": [messages],
    }


def clear_output_dir(output_dir: Path) -> int:
    removed = 0
    for path in output_dir.glob("*.json"):
        path.unlink()
        removed += 1
    return removed


def download_contract_rows(
    rows: list[ContractRow],
    output_dir: Path,
    *,
    dry_run: bool = False,
) -> DownloadStats:
    stats = DownloadStats()
    s3_client = create_boto3_client("s3")
    output_dir.mkdir(parents=True, exist_ok=True)
    list_cache: dict[str, list[dict[str, Any]]] = {}

    for idx, row in enumerate(rows, start=1):
        stats.rows_processed += 1
        group_id = row.whatsapp_group_id
        row_date = created_date_from_contract(row.created_at)
        logger.info(
            "Row %02d: %s customer=%s date=%s",
            idx,
            group_id,
            row.customer_id,
            row_date,
        )

        try:
            if group_id not in list_cache:
                prefix = f"{MESSAGES_PREFIX}{group_id}/"
                candidate_objects = list_objects_with_prefix(s3_client, prefix)
                if not candidate_objects:
                    candidate_objects = list_objects_with_prefix(s3_client, MESSAGES_PREFIX)
                list_cache[group_id] = candidate_objects

            selected_objects = select_keys_for_row(list_cache[group_id], group_id, row_date)
            stats.s3_json_found += len(selected_objects)

            s3_matches: list[dict[str, Any]] = []
            chat_groups: list[list[dict]] = []

            for obj in selected_objects:
                key = obj["Key"]
                logger.info("  candidate: %s", key)

                if dry_run:
                    s3_matches.append(build_s3_match(obj))
                    chat_groups.append([])
                    continue

                try:
                    raw = json.loads(download_object_body(s3_client, key))
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid JSON: %s", key)
                    stats.record_skip("invalid_json")
                    continue
                except Exception as exc:
                    logger.warning("Failed to download %s: %s", key, exc)
                    stats.record_skip("download_error")
                    continue

                if not identifier_match(
                    key,
                    raw,
                    customer_id=row.customer_id,
                    group_id=group_id,
                    organization_id=row.organization_id,
                    po_ref_no=row.po_ref_no,
                ):
                    logger.info("  skipped (identifier mismatch): %s", key)
                    stats.record_skip("identifier_mismatch")
                    continue

                messages = extract_messages(raw)
                if not messages:
                    logger.warning("Skipping non-message JSON: %s", key)
                    stats.record_skip("no_messages")
                    continue

                s3_matches.append(build_s3_match(obj))
                chat_groups.append(messages)
                logger.info("  matched %s (%d messages)", key, len(messages))

            filename = build_filename(idx, row_date, group_id, row.customer_id)
            out_path = output_dir / filename

            if dry_run:
                stats.downloaded += 1
                if chat_groups or s3_matches:
                    stats.matched += 1
                else:
                    stats.no_match += 1
                stats.output_paths.append(f"(dry-run) {out_path.name} chats={len(chat_groups)}")
                continue

            wrapped = build_contract_wrapped_output(
                row_index=idx,
                row=row,
                s3_matches=s3_matches,
                chat_groups=chat_groups,
            )
            out_path.write_text(
                json.dumps(wrapped, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            stats.downloaded += 1
            stats.output_paths.append(str(out_path))
            if chat_groups:
                stats.matched += 1
            else:
                stats.no_match += 1
            logger.info("  wrote %s chats=%d", out_path.name, len(chat_groups))

        except Exception as exc:
            logger.exception("Row %02d failed: %s", idx, exc)
            stats.record_skip("row_error")
            if not dry_run:
                error_payload = build_contract_wrapped_output(
                    row_index=idx,
                    row=row,
                    s3_matches=[],
                    chat_groups=[],
                )
                error_payload["error"] = str(exc)
                out_path = output_dir / build_filename(idx, row_date, group_id, row.customer_id)
                out_path.write_text(
                    json.dumps(error_payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

    return stats


def download_chats(
    pairs: list[ChatPair],
    output_dir: Path,
    *,
    dry_run: bool = False,
    llm_msg_only: bool = False,
    folder_matched_only: bool = False,
) -> DownloadStats:
    stats = DownloadStats()
    s3_client = create_boto3_client("s3")
    output_dir.mkdir(parents=True, exist_ok=True)

    row_index = 0
    used_filenames: set[str] = set()

    for pair in pairs:
        stats.groups_scanned += 1
        logger.info("Scanning %s (org=%s)", pair.whatsapp_group_id, pair.organization_id)

        try:
            objects = list_message_json_keys(
                s3_client,
                pair.whatsapp_group_id,
                llm_msg_only=llm_msg_only,
                folder_matched_only=folder_matched_only,
            )
        except Exception as exc:
            logger.exception("Failed to list S3 prefix for %s: %s", pair.whatsapp_group_id, exc)
            stats.record_skip("s3_list_error")
            continue

        stats.s3_json_found += len(objects)
        if not objects:
            logger.warning("No JSON files found for %s", pair.whatsapp_group_id)
            stats.record_skip("no_json_found")
            continue

        for s3_object in sorted(objects, key=lambda o: o["Key"]):
            key = s3_object["Key"]
            logger.info("  candidate: %s", key)

            if dry_run:
                stats.downloaded += 1
                stats.output_paths.append(f"(dry-run) {key}")
                continue

            try:
                raw_bytes = download_object_body(s3_client, key)
                raw = json.loads(raw_bytes)
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON: %s", key)
                stats.record_skip("invalid_json")
                continue
            except Exception as exc:
                logger.warning("Failed to download %s: %s", key, exc)
                stats.record_skip("download_error")
                continue

            messages = extract_messages(raw)
            if not messages:
                logger.warning("Skipping non-message JSON: %s", key)
                stats.record_skip("no_messages")
                continue

            row_index += 1
            last_modified = s3_object.get("LastModified")
            created_date = created_date_from_key(
                key,
                last_modified if isinstance(last_modified, datetime) else None,
            )
            filename = build_filename(
                row_index,
                created_date,
                pair.whatsapp_group_id,
                pair.organization_id,
            )

            if filename in used_filenames:
                suffix = Path(key).stem.replace(".", "-")
                filename = build_filename(
                    row_index,
                    created_date,
                    pair.whatsapp_group_id,
                    pair.organization_id,
                    suffix=suffix,
                )
                logger.warning("Filename collision; using %s for key %s", filename, key)

            used_filenames.add(filename)
            wrapped = build_wrapped_output(
                row_index=row_index,
                whatsapp_group_id=pair.whatsapp_group_id,
                customer_id=pair.organization_id,
                messages=messages,
                s3_object=s3_object,
            )

            out_path = output_dir / filename
            out_path.write_text(
                json.dumps(wrapped, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            stats.downloaded += 1
            stats.output_paths.append(str(out_path))
            logger.info("  wrote %s (%d messages)", out_path.name, len(messages))

    return stats


def print_summary(stats: DownloadStats, *, contract_mode: bool) -> None:
    print("\n=== Download summary ===")
    if contract_mode:
        print(f"Rows processed:  {stats.rows_processed}")
        print(f"Rows matched:    {stats.matched}")
        print(f"Rows no match:   {stats.no_match}")
    else:
        print(f"Groups scanned:  {stats.groups_scanned}")
    print(f"S3 JSON found:   {stats.s3_json_found}")
    print(f"Downloaded:      {stats.downloaded}")
    print(f"Skipped:         {stats.skipped}")
    if stats.skip_reasons:
        print("Skip reasons:")
        for reason, count in sorted(stats.skip_reasons.items()):
            print(f"  {reason}: {count}")
    if stats.output_paths:
        print("Output files:")
        for path in stats.output_paths:
            print(f"  {path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download WhatsApp chats from S3.")
    parser.add_argument(
        "--contracts",
        type=Path,
        default=DEFAULT_CONTRACTS_PATH,
        help="Contract rows JSON (default: Public Contracts May 29 2026.json).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "raw_data" / "downloaded_chats",
        help="Directory for wrapped downloaded chat JSON files.",
    )
    parser.add_argument(
        "--fresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delete existing *.json in output dir before downloading (default: true).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List S3 candidates without downloading or writing files.",
    )
    parser.add_argument(
        "--llm-msg-only",
        action="store_true",
        help="Bulk mode: download only llm_msg.json from each unique group in contracts.",
    )
    parser.add_argument(
        "--folder-matched-only",
        action="store_true",
        help=(
            "Bulk mode: download only root-level JSON files whose basename matches a "
            "subfolder name in the same WhatsApp group."
        ),
    )
    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    args = build_arg_parser().parse_args()
    contracts_path = args.contracts.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    if not contracts_path.is_file():
        logger.error("Contracts file not found: %s", contracts_path)
        return 1

    if args.llm_msg_only and args.folder_matched_only:
        logger.error("Use only one of --llm-msg-only and --folder-matched-only")
        return 1

    try:
        rows = parse_contracts_json(contracts_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse contracts file: %s", exc)
        return 1

    if not rows:
        logger.error("No contract rows found in %s", contracts_path)
        return 1

    contract_mode = not args.llm_msg_only and not args.folder_matched_only
    logger.info(
        "Loaded %d signed contract row(s) from %s",
        len(rows),
        contracts_path,
    )

    if args.llm_msg_only:
        logger.info("Mode: llm_msg.json only (one file per unique WhatsApp group)")
    elif args.folder_matched_only:
        logger.info("Mode: folder-matched JSON only (basename must match a subfolder name)")
    else:
        logger.info("Mode: contract row matching (date + customer/group identifiers)")

    if args.fresh and not args.dry_run:
        removed = clear_output_dir(output_dir)
        if removed:
            logger.info("Removed %d existing file(s) from %s", removed, output_dir)

    if contract_mode:
        stats = download_contract_rows(rows, output_dir, dry_run=args.dry_run)
    else:
        pairs = unique_groups_from_contracts(rows)
        stats = download_chats(
            pairs,
            output_dir,
            dry_run=args.dry_run,
            llm_msg_only=args.llm_msg_only,
            folder_matched_only=args.folder_matched_only,
        )

    print_summary(stats, contract_mode=contract_mode)
    return 0 if stats.downloaded > 0 or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
