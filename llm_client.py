import logging
from typing import Type, TypeVar

import instructor
from pydantic import BaseModel

from utils import BEDROCK_ANTHROPIC_MODELS, create_boto3_client

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_TOKENS = 4096


def call_bedrock(
    prompt: str,
    schema: Type[T],
    model_key: str = "default",
    system_prompt: str | None = None,
) -> T:
    """Call AWS Bedrock Claude via instructor and return a validated Pydantic model instance.

    instructor handles JSON extraction and schema validation internally; any
    ValidationError or parsing failure propagates to the caller (extractor.py)
    so Tenacity can retry.

    Args:
        prompt: Fully rendered user prompt string from prompt_builder.
        schema: Pydantic model class to extract into.
        model_key: Key into BEDROCK_ANTHROPIC_MODELS dict (default: "default").
        system_prompt: Optional rendered system prompt from prompt_builder.

    Returns:
        Validated instance of `schema`.
    """
    model_id = BEDROCK_ANTHROPIC_MODELS[model_key]
    logger.info("Calling Bedrock model=%s schema=%s", model_id, schema.__name__)

    raw_client = create_boto3_client("bedrock-runtime")
    client = instructor.from_bedrock(raw_client)

    kwargs: dict = dict(
        model=model_id,
        response_model=schema,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    if system_prompt:
        kwargs["system"] = [{"text": system_prompt}]

    result: T = client.messages.create(**kwargs)

    logger.info("Bedrock extraction succeeded, type=%s", type(result).__name__)
    return result
