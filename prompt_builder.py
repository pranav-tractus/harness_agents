import json
import logging
from pathlib import Path
from typing import Type

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from pydantic import BaseModel

from db import get_recent_success_examples

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), trim_blocks=True, lstrip_blocks=True)
_env.filters["jsonpretty"] = lambda value, indent=2: json.dumps(value, indent=indent, ensure_ascii=False)


def build_system_prompt(
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    iso_date: str | None = None,
) -> str:
    """Render the system prompt with optional vendor/counterparty context and reference date.

    Args:
        organization_info: Vendor / Team 1 metadata dict (used for interpretation only).
        customer_info: Counterparty / Team 2 metadata dict (used for interpretation only).
        iso_date: ISO 8601 reference date string (e.g. "2026-04-30").

    Returns:
        Rendered system prompt string.
    """
    try:
        template = _env.get_template("system_prompt.j2")
    except TemplateNotFound:
        raise FileNotFoundError(f"system_prompt.j2 not found in {_TEMPLATES_DIR}")

    prompt = template.render(
        organization_info=organization_info,
        customer_info=customer_info,
        iso_date=iso_date,
    )

    logger.debug("Built system prompt (chars=%d)", len(prompt))
    return prompt


def build_prompt(
    input_text: str,
    schema: Type[BaseModel],
    attempt: int = 1,
    iso_date: str | None = None,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
) -> str:
    """Build a Jinja2-rendered extraction prompt for the given schema and input text.

    Args:
        input_text: Normalized input text to extract from.
        schema: Pydantic model class describing the target structure.
        attempt: Current attempt number (1-indexed). Values > 1 inject retry hints.
        iso_date: ISO 8601 reference date string forwarded to extraction_rules.j2.
        organization_info: Vendor metadata forwarded to extraction_rules.j2 context.
        customer_info: Counterparty metadata forwarded to extraction_rules.j2 context.

    Returns:
        Rendered prompt string ready to be sent to the LLM.
    """
    try:
        template = _env.get_template("extraction.j2")
    except TemplateNotFound:
        raise FileNotFoundError(f"extraction.j2 not found in {_TEMPLATES_DIR}")

    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    recent_examples = get_recent_success_examples(limit=5, schema_name=schema.__name__)

    prompt = template.render(
        input_text=input_text.strip(),
        schema_json=schema_json,
        few_shot_examples=recent_examples,
        attempt=attempt,
        iso_date=iso_date,
        organization_info=organization_info,
        customer_info=customer_info,
    )

    logger.debug("Built prompt (attempt=%d, schema=%s, chars=%d)", attempt, schema.__name__, len(prompt))
    return prompt
