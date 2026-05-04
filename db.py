import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "extractions.db"

_DDL_EXTRACTIONS = """
CREATE TABLE IF NOT EXISTS extractions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    input_text  TEXT    NOT NULL,
    prompt_text TEXT,
    schema_name TEXT    NOT NULL,
    output_json TEXT,
    status      TEXT    NOT NULL CHECK(status IN ('success', 'failed')),
    error       TEXT,
    attempts    INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL
);
"""

_DDL_SUMMARIES = """
CREATE TABLE IF NOT EXISTS summaries (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_summary_id  INTEGER NULL REFERENCES summaries(id),
    kind               TEXT    NOT NULL CHECK(kind IN ('initial', 'update')),
    schema_name        TEXT    NOT NULL,
    source_chat        TEXT,
    input_text         TEXT    NOT NULL,
    prompt_text        TEXT,
    update_instruction TEXT,
    output_json        TEXT    NOT NULL,
    attempts           INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT    NOT NULL
);
"""


@dataclass
class ExtractionResult:
    input_text: str
    prompt_text: Optional[str]
    schema_name: str
    status: str
    attempts: int
    output_json: Optional[str] = None
    error: Optional[str] = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()


@dataclass
class SavedSummary:
    """A user-saved summary row (initial extraction or human-in-the-loop update).

    ``parent_summary_id`` chains updates back to the initial summary (and to any
    intermediate update revisions).
    """

    kind: str  # 'initial' | 'update'
    schema_name: str
    input_text: str
    output_json: str
    parent_summary_id: Optional[int] = None
    source_chat: Optional[str] = None
    prompt_text: Optional[str] = None
    update_instruction: Optional[str] = None
    attempts: int = 1
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        if self.kind not in ("initial", "update"):
            raise ValueError(f"Invalid kind: {self.kind!r}")


def init_db(db_path: Path = DB_PATH) -> None:
    """Create the tables if they do not already exist (additive migrations only)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(_DDL_EXTRACTIONS)
        cols = conn.execute("PRAGMA table_info(extractions)").fetchall()
        col_names = {c[1] for c in cols}
        if "prompt_text" not in col_names:
            conn.execute("ALTER TABLE extractions ADD COLUMN prompt_text TEXT")

        conn.execute(_DDL_SUMMARIES)
        conn.commit()
    logger.debug("DB initialised at %s", db_path)


def save_result(result: ExtractionResult, db_path: Path = DB_PATH) -> int:
    """Persist a raw ExtractionResult to the legacy extractions table.

    Note: the new HITL flow does NOT call this. Use :func:`save_summary` instead.
    Retained for backwards compatibility with any existing scripts/tests.
    """
    row = asdict(result)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO extractions (input_text, prompt_text, schema_name, output_json, status, error, attempts, created_at)
            VALUES (:input_text, :prompt_text, :schema_name, :output_json, :status, :error, :attempts, :created_at)
            """,
            row,
        )
        conn.commit()
    logger.debug("Saved extraction id=%d status=%s", cur.lastrowid, result.status)
    if cur.lastrowid:
        return cur.lastrowid
    raise ValueError("Failed to save extraction result")


def save_summary(summary: SavedSummary, db_path: Path = DB_PATH) -> int:
    """Persist a SavedSummary row and return its primary key."""
    row = asdict(summary)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO summaries (
                parent_summary_id, kind, schema_name, source_chat, input_text,
                prompt_text, update_instruction, output_json, attempts, created_at
            ) VALUES (
                :parent_summary_id, :kind, :schema_name, :source_chat, :input_text,
                :prompt_text, :update_instruction, :output_json, :attempts, :created_at
            )
            """,
            row,
        )
        conn.commit()
    if cur.lastrowid is None:
        raise ValueError("Failed to save summary")
    logger.info(
        "Saved summary id=%d kind=%s parent=%s schema=%s",
        cur.lastrowid, summary.kind, summary.parent_summary_id, summary.schema_name,
    )
    return cur.lastrowid


def get_history(limit: int = 50, db_path: Path = DB_PATH) -> list[dict]:
    """Return the most recent saved summaries (newest first)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM summaries ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_id(row_id: int, db_path: Path = DB_PATH) -> Optional[dict]:
    """Fetch a single summary row by primary key."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM summaries WHERE id = ?", (row_id,)
        ).fetchone()
    return dict(row) if row else None


def get_summary_chain(root_id: int, db_path: Path = DB_PATH) -> list[dict]:
    """Return the initial summary plus all update revisions, oldest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            WITH RECURSIVE chain(id) AS (
                SELECT id FROM summaries WHERE id = ?
                UNION ALL
                SELECT s.id FROM summaries s JOIN chain c ON s.parent_summary_id = c.id
            )
            SELECT s.* FROM summaries s
            JOIN chain c ON s.id = c.id
            ORDER BY s.id ASC
            """,
            (root_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_success_examples(
    limit: int = 5,
    schema_name: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Return recent saved initial summaries for few-shot context.

    Reads from the ``summaries`` table (kind='initial'). Falls back to the legacy
    ``extractions`` table when no saved summaries exist for the schema yet.
    """
    examples: list[dict] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        query = """
            SELECT input_text, prompt_text, output_json, schema_name, created_at
            FROM summaries
            WHERE kind = 'initial' AND output_json IS NOT NULL AND prompt_text IS NOT NULL
        """
        params: list[object] = []
        if schema_name:
            query += " AND schema_name = ?"
            params.append(schema_name)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        examples = [dict(r) for r in conn.execute(query, tuple(params)).fetchall()]

        if not examples:
            legacy_q = """
                SELECT input_text, prompt_text, output_json, schema_name, created_at
                FROM extractions
                WHERE status = 'success' AND output_json IS NOT NULL AND prompt_text IS NOT NULL
            """
            legacy_params: list[object] = []
            if schema_name:
                legacy_q += " AND schema_name = ?"
                legacy_params.append(schema_name)
            legacy_q += " ORDER BY id DESC LIMIT ?"
            legacy_params.append(limit)
            examples = [dict(r) for r in conn.execute(legacy_q, tuple(legacy_params)).fetchall()]

    return examples


def get_recent_update_examples(limit: int = 5, db_path: Path = DB_PATH) -> list[dict]:
    """Return recent saved update revisions plus their parent summary as few-shot examples.

    Each returned dict has keys ``previous_summary_json``, ``update_instruction``,
    and ``updated_summary_json`` so they slot directly into ``update.j2``.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT child.update_instruction AS update_instruction,
                   child.output_json        AS updated_summary_json,
                   parent.output_json       AS previous_summary_json,
                   child.input_text         AS recent_chat_messages,
                   child.created_at         AS created_at
            FROM summaries child
            JOIN summaries parent ON child.parent_summary_id = parent.id
            WHERE child.kind = 'update' AND parent.output_json IS NOT NULL
            ORDER BY child.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
