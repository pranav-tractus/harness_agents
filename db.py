import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "extractions.db"

_DDL = """
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


def init_db(db_path: Path = DB_PATH) -> None:
    """Create the extractions table if it does not exist."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(_DDL)
        # Lightweight migration for existing DBs created before prompt_text existed.
        cols = conn.execute("PRAGMA table_info(extractions)").fetchall()
        col_names = {c[1] for c in cols}
        if "prompt_text" not in col_names:
            conn.execute("ALTER TABLE extractions ADD COLUMN prompt_text TEXT")
        conn.commit()
    logger.debug("DB initialised at %s", db_path)


def save_result(result: ExtractionResult, db_path: Path = DB_PATH) -> int:
    """Persist an ExtractionResult and return the new row id."""
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
    else:
        raise ValueError("Failed to save extraction result")


def get_history(limit: int = 50, db_path: Path = DB_PATH) -> list[dict]:
    """Return the most recent `limit` extraction rows as dicts, newest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM extractions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_id(row_id: int, db_path: Path = DB_PATH) -> Optional[dict]:
    """Fetch a single extraction row by primary key."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM extractions WHERE id = ?", (row_id,)
        ).fetchone()
    return dict(row) if row else None


def get_recent_success_examples(
    limit: int = 5,
    schema_name: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Return recent successful examples with input/prompt/output for few-shot context."""
    query = """
        SELECT input_text, prompt_text, output_json, schema_name, created_at
        FROM extractions
        WHERE status = 'success'
          AND output_json IS NOT NULL
          AND prompt_text IS NOT NULL
    """
    params: list[object] = []
    if schema_name:
        query += " AND schema_name = ?"
        params.append(schema_name)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(r) for r in rows]
