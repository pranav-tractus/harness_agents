import json
import logging
from pathlib import Path
from typing import Type

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from pydantic import BaseModel

from db import DB_PATH, get_recent_success_examples, get_recent_update_examples
from models import SOExtractContractList, SOUpdateContractList
from utils import customer_info as utils_customer_info, team_info as utils_team_info

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), trim_blocks=True, lstrip_blocks=True)
_env.filters["jsonpretty"] = lambda value, indent=2: json.dumps(value, indent=indent, ensure_ascii=False)


INITIAL_SCHEMA: Type[BaseModel] = SOExtractContractList
UPDATE_SCHEMA: Type[BaseModel] = SOUpdateContractList

UPDATE_FEW_SHOT_DB_LIMIT = 5
UPDATE_FEW_SHOT_MAX_TOTAL = 18

INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT = 5
INITIAL_FEW_SHOT_MAX_TOTAL = 18


def build_system_prompt(
    organization_info: dict | None = None,
    customer_info: dict | None = None,
) -> str:
    """Render the system prompt with optional vendor/counterparty reference context."""
    try:
        template = _env.get_template("system_prompt.j2")
    except TemplateNotFound:
        raise FileNotFoundError(f"system_prompt.j2 not found in {_TEMPLATES_DIR}")

    prompt = template.render(
        organization_info=organization_info if organization_info is not None else utils_team_info,
        customer_info=customer_info if customer_info is not None else utils_customer_info,
    )

    logger.debug("Built system prompt (chars=%d)", len(prompt))
    return prompt


def build_prompt(
    input_text: str,
    attempt: int = 1,
    *,
    iso_date: str,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    extra_few_shot_examples: list[dict] | None = None,
    db_few_shot_limit: int = INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT,
    db_path: Path = DB_PATH,
) -> str:
    """Build a Jinja2-rendered initial extraction prompt.

    The schema is locked to ``SOExtractContractList`` for the initial extraction flow.
    The ``schema`` argument is retained for backwards compatibility but is ignored
    if it does not match the locked initial schema.

    ``extra_few_shot_examples`` are merged **before** database examples (from saved
    summaries). Set ``db_few_shot_limit`` to ``0`` to use only file-based examples.
    The merged list is capped at ``INITIAL_FEW_SHOT_MAX_TOTAL``.
    """
    target_schema = INITIAL_SCHEMA
    try:
        template = _env.get_template("extraction.j2")
    except TemplateNotFound:
        raise FileNotFoundError(f"extraction.j2 not found in {_TEMPLATES_DIR}")

    schema_json = json.dumps(target_schema.model_json_schema(), indent=2)
    extra = list(extra_few_shot_examples or [])
    db_examples = (
        get_recent_success_examples(
            limit=db_few_shot_limit,
            schema_name=target_schema.__name__,
            db_path=db_path,
        )
        if db_few_shot_limit > 0
        else []
    )
    merged = extra + db_examples
    if len(merged) > INITIAL_FEW_SHOT_MAX_TOTAL:
        keep_extra = min(len(extra), INITIAL_FEW_SHOT_MAX_TOTAL)
        trimmed_extra = extra[:keep_extra]
        room = INITIAL_FEW_SHOT_MAX_TOTAL - len(trimmed_extra)
        merged = trimmed_extra + db_examples[: max(0, room)]

    prompt = template.render(
        input_text=input_text.strip(),
        schema_json=schema_json,
        few_shot_examples=merged,
        attempt=attempt,
        iso_date=iso_date,
        organization_info=organization_info,
        customer_info=customer_info,
    )

    logger.debug(
        "Built initial extraction prompt (attempt=%d, schema=%s, chars=%d)",
        attempt, target_schema.__name__, len(prompt),
    )
    return prompt


def build_update_prompt(
    previous_summary: dict,
    update_instruction: str,
    original_input_text: str | None = None,
    attempt: int = 1,
    *,
    iso_date: str,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    synthetic_few_shot_examples: list[dict] | None = None,
    db_path: Path = DB_PATH,
) -> str:
    """Build the human-in-the-loop update prompt.

    Always renders against ``SOUpdateContractList``. Few-shot examples are pulled
    from the ``summaries`` table where ``kind='update'``. Optionally prepend
    synthetic scenarios (``raw_data/chats/updates/``) when the caller passes
    ``synthetic_few_shot_examples``.
    """
    target_schema = UPDATE_SCHEMA
    try:
        template = _env.get_template("update.j2")
    except TemplateNotFound:
        raise FileNotFoundError(f"update.j2 not found in {_TEMPLATES_DIR}")

    schema_json = json.dumps(target_schema.model_json_schema(), indent=2)
    previous_summary_json = json.dumps(previous_summary, indent=2, ensure_ascii=False)
    db_examples = get_recent_update_examples(limit=UPDATE_FEW_SHOT_DB_LIMIT, db_path=db_path)
    synth = list(synthetic_few_shot_examples or [])
    few_shot_examples = synth + db_examples
    if len(few_shot_examples) > UPDATE_FEW_SHOT_MAX_TOTAL:
        few_shot_examples = few_shot_examples[:UPDATE_FEW_SHOT_MAX_TOTAL]

    prompt = template.render(
        previous_summary_json=previous_summary_json,
        update_instruction=update_instruction.strip(),
        original_input_text=(original_input_text or "").strip() or None,
        schema_json=schema_json,
        few_shot_examples=few_shot_examples,
        attempt=attempt,
        iso_date=iso_date,
        organization_info=organization_info,
        customer_info=customer_info,
    )

    logger.debug(
        "Built update prompt (attempt=%d, schema=%s, chars=%d)",
        attempt, target_schema.__name__, len(prompt),
    )
    return prompt
