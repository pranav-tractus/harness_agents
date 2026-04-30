"""Extraction Engine — orchestrates the full pipeline:

    normalize → build_prompt → call_bedrock (instructor) → store result

Retry logic (Tenacity) wraps the LLM call so transient validation or
parsing failures automatically re-run with a progressively clarified prompt.
"""

import json
import logging
import textwrap
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

from db import ExtractionResult, init_db, save_result
from llm_client import call_bedrock
from prompt_builder import build_prompt, build_system_prompt

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_ATTEMPTS = 3
_CHUNK_THRESHOLD = 4_000  # characters — inputs longer than this are chunked


# Input normalisation helpers

def _normalize(text: str) -> str:
    """Strip leading/trailing whitespace and collapse excessive blank lines."""
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
    """Split text into chunks of at most `max_chars`, breaking on paragraph boundaries."""
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


# Core extraction with Tenacity retry

def _extract_with_retry_tracked(
    text: str,
    schema: Type[T],
    model_key: str,
    system_prompt: str | None = None,
    iso_date: str | None = None,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
) -> tuple[T, int, str]:
    """Run prompt → LLM → validated model, retrying up to _MAX_ATTEMPTS times.

    Returns:
        (result, total_attempts_used, last_prompt) tuple.
    """
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
            "Extraction attempt %d/%d for schema=%s",
            current_attempt, _MAX_ATTEMPTS, schema.__name__,
        )
        prompt = build_prompt(
            text,
            schema,
            attempt=current_attempt,
            iso_date=iso_date,
            organization_info=organization_info,
            customer_info=customer_info,
        )
        last_prompt = prompt
        logger.debug("Prompt (attempt=%d):\n%s", current_attempt, textwrap.indent(prompt, "  "))

        result = call_bedrock(prompt, schema, model_key=model_key, system_prompt=system_prompt)

        logger.info("Attempt %d succeeded", current_attempt)
        return result

    result = _attempt()
    return result, attempts_used, last_prompt


# Public API

class ExtractionEngine:
    """Orchestrates the complete extraction pipeline for a given Pydantic schema."""

    def __init__(
        self,
        model_key: str = "default",
        organization_info: dict | None = None,
        customer_info: dict | None = None,
        iso_date: str | None = None,
    ) -> None:
        self.model_key = model_key
        self.organization_info = organization_info
        self.customer_info = customer_info
        self.iso_date = iso_date
        init_db()

    def run(self, input_text: str, schema: Type[T]) -> ExtractionResult:
        """Run the full extraction pipeline and persist the result to SQLite.

        Args:
            input_text: Raw unstructured text to extract from.
            schema: Pydantic model class describing the target structure.

        Returns:
            ExtractionResult with status, output_json, error, and attempt count.
        """
        normalized = _normalize(input_text)
        chunks = _chunk_text(normalized)

        if len(chunks) > 1:
            logger.info("Input split into %d chunks (total chars=%d)", len(chunks), len(normalized))

        # For now, extract from the first chunk (or the whole text if no splitting needed).
        # Multi-chunk merging can be added per schema requirements.
        text_to_extract = chunks[0] if chunks else normalized

        system_prompt = build_system_prompt(
            organization_info=self.organization_info,
            customer_info=self.customer_info,
            iso_date=self.iso_date,
        )

        logger.info("Starting extraction: schema=%s chars=%d", schema.__name__, len(text_to_extract))

        try:
            result_model, attempts_used, final_prompt = _extract_with_retry_tracked(
                text_to_extract,
                schema,
                self.model_key,
                system_prompt=system_prompt,
                iso_date=self.iso_date,
                organization_info=self.organization_info,
                customer_info=self.customer_info,
            )
            output_json = result_model.model_dump_json(indent=2)
            logger.info("Extraction succeeded after %d attempt(s)", attempts_used)

            db_result = ExtractionResult(
                input_text=input_text,
                prompt_text=final_prompt,
                schema_name=schema.__name__,
                output_json=output_json,
                status="success",
                error=None,
                attempts=attempts_used,
            )

        except (ValidationError, ValueError, json.JSONDecodeError, RetryError, Exception) as exc:
            error_msg = str(exc)
            logger.error("Extraction failed after %d attempt(s): %s", _MAX_ATTEMPTS, error_msg)

            db_result = ExtractionResult(
                input_text=input_text,
                prompt_text=None,
                schema_name=schema.__name__,
                output_json=None,
                status="failed",
                error=error_msg,
                attempts=_MAX_ATTEMPTS,
            )

        row_id = save_result(db_result)
        logger.info("Result persisted to DB id=%d status=%s", row_id, db_result.status)
        return db_result
