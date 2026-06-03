import json
import logging
from pathlib import Path
from typing import Type

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from pydantic import BaseModel

from core.db import DB_PATH, get_recent_success_examples, get_recent_update_examples
from core.models import SOExtractContractList, SOUpdateContractList
from core.prompt_strategy import PromptStrategy, provider_family
from core.utils import customer_info as utils_customer_info, team_info as utils_team_info

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), trim_blocks=True, lstrip_blocks=True)
_env.filters["jsonpretty"] = lambda value, indent=2: json.dumps(value, indent=indent, ensure_ascii=False)


INITIAL_SCHEMA: Type[BaseModel] = SOExtractContractList
UPDATE_SCHEMA: Type[BaseModel] = SOUpdateContractList

UPDATE_FEW_SHOT_DB_LIMIT = 5
UPDATE_FEW_SHOT_MAX_TOTAL = 18

INITIAL_FEW_SHOT_DB_LIMIT_DEFAULT = 5
INITIAL_FEW_SHOT_MAX_TOTAL = 18


def _extraction_template_name(strategy: PromptStrategy, model_key: str) -> str:
    """Return the Jinja2 template filename for the given strategy and model."""
    if strategy == PromptStrategy.XML_NEUTRAL:
        return "extraction_xml_neutral.j2"
    if strategy == PromptStrategy.SCHEMA_DRIVEN:
        return "extraction_schema_driven.j2"
    if strategy == PromptStrategy.PROVIDER_PROFILE:
        family = provider_family(model_key)
        # provider_family() maps "bedrock" -> "anthropic" already
        if family == "anthropic":
            return "extraction.j2"
        return "extraction_xml_neutral.j2"
    return "extraction.j2"  # CURRENT


def _validation_system_template_name(strategy: PromptStrategy, model_key: str) -> str:
    if strategy == PromptStrategy.CURRENT:
        return "validation_system.j2"
    if strategy == PromptStrategy.PROVIDER_PROFILE:
        family = provider_family(model_key)
        # provider_family() maps "bedrock" -> "anthropic" already
        if family == "anthropic":
            return "validation_system.j2"
        return "validation_system_xml_neutral.j2"
    return "validation_system_xml_neutral.j2"


def _validation_user_template_name(strategy: PromptStrategy, model_key: str) -> str:
    if strategy == PromptStrategy.CURRENT:
        return "validation_user.j2"
    if strategy == PromptStrategy.PROVIDER_PROFILE:
        family = provider_family(model_key)
        # provider_family() maps "bedrock" -> "anthropic" already
        if family == "anthropic":
            return "validation_user.j2"
        return "validation_user_xml_neutral.j2"
    return "validation_user_xml_neutral.j2"


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
    strategy: PromptStrategy = PromptStrategy.CURRENT,
    model_key: str = "",
) -> str:
    """Build a Jinja2-rendered initial extraction prompt.

    ``strategy`` selects the template variant; defaults to CURRENT for backward compat.
    """
    target_schema = INITIAL_SCHEMA
    template_name = _extraction_template_name(strategy, model_key)
    try:
        template = _env.get_template(template_name)
    except TemplateNotFound:
        raise FileNotFoundError(f"{template_name} not found in {_TEMPLATES_DIR}")

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
        "Built initial extraction prompt (attempt=%d, schema=%s, strategy=%s, chars=%d)",
        attempt, target_schema.__name__, strategy.value, len(prompt),
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
    """Build the human-in-the-loop update prompt (always uses CURRENT template)."""
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


def build_validation_system_prompt(
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    strategy: PromptStrategy = PromptStrategy.CURRENT,
    model_key: str = "",
) -> str:
    """System prompt for the validation / post-processing LLM layer."""
    template_name = _validation_system_template_name(strategy, model_key)
    try:
        template = _env.get_template(template_name)
    except TemplateNotFound:
        raise FileNotFoundError(f"{template_name} not found in {_TEMPLATES_DIR}")
    return template.render(
        organization_info=organization_info if organization_info is not None else utils_team_info,
        customer_info=customer_info if customer_info is not None else utils_customer_info,
    )


def build_validation_user_prompt(
    source_text: str,
    extraction_json: dict,
    strategy: PromptStrategy = PromptStrategy.CURRENT,
    model_key: str = "",
) -> str:
    """User prompt for validation LLM: chat + current extraction JSON."""
    template_name = _validation_user_template_name(strategy, model_key)
    try:
        template = _env.get_template(template_name)
    except TemplateNotFound:
        raise FileNotFoundError(f"{template_name} not found in {_TEMPLATES_DIR}")
    return template.render(
        source_text=source_text.strip(),
        extraction_json=extraction_json,
    )
