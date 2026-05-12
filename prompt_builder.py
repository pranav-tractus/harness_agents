"""Back-compat shim. New code should import from ``core.prompt_builder``."""

from core.prompt_builder import (  # noqa: F401
    INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT,
    INITIAL_FEW_SHOT_MAX_TOTAL,
    INITIAL_SCHEMA,
    UPDATE_FEW_SHOT_DB_LIMIT,
    UPDATE_FEW_SHOT_MAX_TOTAL,
    UPDATE_SCHEMA,
    build_prompt,
    build_system_prompt,
    build_update_prompt,
)
