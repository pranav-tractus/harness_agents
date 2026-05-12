"""Extraction Engine — orchestrates the full pipeline:

    normalize -> build_prompt -> call_llm (instructor) -> return result

Schemas are locked:
- initial extraction always uses ``SOExtractContractList``
- summary updates always use ``SOUpdateContractList``

The engine does not write to the database. Persistence is the caller's
responsibility (typically the Streamlit UI's "Save" button via
:func:`core.db.save_summary`).

Retry logic (Tenacity) wraps the LLM call so transient validation or parsing
failures automatically re-run with a progressively clarified prompt.
"""

import json
import logging
import textwrap
from datetime import date
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from core.chat_loader import load_synthetic_update_few_shot_examples
from core.db import DB_PATH, ExtractionResult, init_db
from core.llm_client import call_llm
from core.models import SOExtractContractList, SOUpdateContractList
from core.prompt_builder import (
    INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT,
    build_prompt,
    build_system_prompt,
    build_update_prompt,
)
from core.utils import DEFAULT_MODEL_KEY, resolve_model_selection

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_ATTEMPTS = 3
_CHUNK_THRESHOLD = 4_000


def _normalize(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        stripped = line.strip()
        if stripped == "":
            blank_run += 1
            if blank_run <= 1:
                cleaned.append("")
        else:
            blank_run = 0
            cleaned.append(stripped)
    return "\n".join(cleaned).strip()


def _chunk_text(text: str, max_chars: int = _CHUNK_THRESHOLD) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _call_with_retry(
    schema: Type[T],
    model_key: str,
    prompt_factory,
    system_prompt: str | None,
) -> tuple[T, int, str]:
    """Run prompt -> LLM -> validated model, retrying up to ``_MAX_ATTEMPTS`` times."""
    attempts_used = 0
    last_prompt = ""

    @retry(
        retry=retry_if_exception_type((ValidationError, ValueError, json.JSONDecodeError)),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_fixed(1),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _attempt() -> T:
        nonlocal attempts_used, last_prompt
        attempts_used += 1
        current_attempt = attempts_used

        logger.info(
            "LLM attempt %d/%d for schema=%s",
            current_attempt, _MAX_ATTEMPTS, schema.__name__,
        )
        prompt = prompt_factory(current_attempt)
        last_prompt = prompt
        logger.debug("Prompt (attempt=%d):\n%s", current_attempt, textwrap.indent(prompt, "  "))

        result = call_llm(prompt, schema, model_key=model_key, system_prompt=system_prompt)

        logger.info("Attempt %d succeeded", current_attempt)
        return result

    result = _attempt()
    return result, attempts_used, last_prompt


class ExtractionEngine:
    """Orchestrates the locked initial-extraction and summary-update flows.

    Schema selection is fixed:
    - :meth:`run` -> ``SOExtractContractList``
    - :meth:`update` -> ``SOUpdateContractList``
    """

    INITIAL_SCHEMA: Type[BaseModel] = SOExtractContractList
    UPDATE_SCHEMA: Type[BaseModel] = SOUpdateContractList

    def __init__(
        self,
        model_key: str = DEFAULT_MODEL_KEY,
        organization_info: dict | None = None,
        customer_info: dict | None = None,
        iso_date: str | None = None,
        db_path: Path = DB_PATH,
    ) -> None:
        self.model_key = model_key
        resolved = resolve_model_selection(model_key)
        self.model_provider = resolved["provider"]
        self.organization_info = organization_info
        self.customer_info = customer_info
        self.iso_date = iso_date if iso_date is not None else date.today().isoformat()
        self.db_path = Path(db_path).expanduser().resolve()
        init_db(self.db_path)

    def run(
        self,
        input_text: str,
        schema: Type[BaseModel] | None = None,
        *,
        extra_few_shot_examples: list[dict] | None = None,
        db_few_shot_limit: int = INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT,
    ) -> ExtractionResult:
        """Run the initial extraction pipeline and return the (un-persisted) result."""
        target_schema = self.INITIAL_SCHEMA
        normalized = _normalize(input_text)
        chunks = _chunk_text(normalized)

        if len(chunks) > 1:
            logger.info("Input split into %d chunks (total chars=%d)", len(chunks), len(normalized))

        text_to_extract = chunks[0] if chunks else normalized

        system_prompt = build_system_prompt(
            organization_info=self.organization_info,
            customer_info=self.customer_info,
        )

        logger.info(
            "Starting initial extraction: schema=%s chars=%d",
            target_schema.__name__, len(text_to_extract),
        )

        def _factory(attempt: int) -> str:
            return build_prompt(
                text_to_extract,
                attempt=attempt,
                iso_date=self.iso_date,
                organization_info=self.organization_info,
                customer_info=self.customer_info,
                extra_few_shot_examples=extra_few_shot_examples,
                db_few_shot_limit=db_few_shot_limit,
                db_path=self.db_path,
            )

        try:
            result_model, attempts_used, final_prompt = _call_with_retry(
                target_schema, self.model_key, _factory, system_prompt,
            )
            output_json = result_model.model_dump_json(indent=2)
            logger.info("Initial extraction succeeded after %d attempt(s)", attempts_used)
            return ExtractionResult(
                input_text=input_text,
                prompt_text=final_prompt,
                schema_name=target_schema.__name__,
                output_json=output_json,
                status="success",
                error=None,
                attempts=attempts_used,
                model_key=self.model_key,
                model_provider=self.model_provider,
            )

        except (ValidationError, ValueError, json.JSONDecodeError, RetryError, Exception) as exc:
            error_msg = str(exc)
            logger.error("Initial extraction failed after %d attempt(s): %s", _MAX_ATTEMPTS, error_msg)
            return ExtractionResult(
                input_text=input_text,
                prompt_text=None,
                schema_name=target_schema.__name__,
                output_json=None,
                status="failed",
                error=error_msg,
                attempts=_MAX_ATTEMPTS,
                model_key=self.model_key,
                model_provider=self.model_provider,
            )

    def update(
        self,
        previous_summary: dict,
        update_instruction: str,
        original_input_text: str | None = None,
        *,
        include_synthetic_update_few_shot: bool = False,
        synthetic_update_few_shot_paths: list[Path] | None = None,
    ) -> ExtractionResult:
        """Apply a human update instruction to an existing summary."""
        target_schema = self.UPDATE_SCHEMA

        system_prompt = build_system_prompt(
            organization_info=self.organization_info,
            customer_info=self.customer_info,
        )

        normalized_chat = _normalize(original_input_text) if original_input_text else None

        logger.info(
            "Starting summary update: schema=%s previous_keys=%d instruction_chars=%d synthetic_few_shot=%s",
            target_schema.__name__,
            len(previous_summary or {}),
            len(update_instruction or ""),
            include_synthetic_update_few_shot,
        )

        synthetic_examples = (
            load_synthetic_update_few_shot_examples(paths=synthetic_update_few_shot_paths)
            if include_synthetic_update_few_shot
            else None
        )

        def _factory(attempt: int) -> str:
            return build_update_prompt(
                previous_summary=previous_summary,
                update_instruction=update_instruction,
                original_input_text=normalized_chat,
                attempt=attempt,
                iso_date=self.iso_date,
                organization_info=self.organization_info,
                customer_info=self.customer_info,
                synthetic_few_shot_examples=synthetic_examples,
                db_path=self.db_path,
            )

        try:
            result_model, attempts_used, final_prompt = _call_with_retry(
                target_schema, self.model_key, _factory, system_prompt,
            )
            output_json = result_model.model_dump_json(indent=2)
            logger.info("Summary update succeeded after %d attempt(s)", attempts_used)
            return ExtractionResult(
                input_text=original_input_text or "",
                prompt_text=final_prompt,
                schema_name=target_schema.__name__,
                output_json=output_json,
                status="success",
                error=None,
                attempts=attempts_used,
                model_key=self.model_key,
                model_provider=self.model_provider,
            )

        except (ValidationError, ValueError, json.JSONDecodeError, RetryError, Exception) as exc:
            error_msg = str(exc)
            logger.error("Summary update failed after %d attempt(s): %s", _MAX_ATTEMPTS, error_msg)
            return ExtractionResult(
                input_text=original_input_text or "",
                prompt_text=None,
                schema_name=target_schema.__name__,
                output_json=None,
                status="failed",
                error=error_msg,
                attempts=_MAX_ATTEMPTS,
                model_key=self.model_key,
                model_provider=self.model_provider,
            )
