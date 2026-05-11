"""Back-compat shim. New code should import from ``core.db``."""

from core.db import (  # noqa: F401
    DB_PATH,
    ExtractionResult,
    SavedSummary,
    get_by_id,
    get_history,
    get_recent_success_examples,
    get_recent_update_examples,
    get_summary_chain,
    init_db,
    save_result,
    save_summary,
)
