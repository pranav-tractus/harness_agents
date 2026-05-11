import logging
from typing import Type, TypeVar

import instructor
from pydantic import BaseModel

from utils import (
    _gemini_model_for_api,
    _get_gemini_client,
    _get_openai_client,
    create_boto3_client,
    resolve_model_selection,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_TOKENS = 4096


def _call_bedrock(
    prompt: str,
    schema: Type[T],
    model_id: str,
    system_prompt: str | None = None,
) -> T:
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


def _call_openai(
    prompt: str,
    schema: Type[T],
    model_id: str,
    system_prompt: str | None = None,
) -> T:
    logger.info("Calling OpenAI model=%s schema=%s", model_id, schema.__name__)
    client = _get_openai_client()
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    result: T = client.chat.completions.create(
        model=model_id,
        response_model=schema,
        messages=messages,
    )
    logger.info("OpenAI extraction succeeded, type=%s", type(result).__name__)
    return result


def _call_gemini(
    prompt: str,
    schema: Type[T],
    model_id: str,
    system_prompt: str | None = None,
) -> T:
    logger.info("Calling Gemini model=%s schema=%s", model_id, schema.__name__)
    instructor_model = model_id
    api_model = _gemini_model_for_api(instructor_model)
    client = _get_gemini_client(instructor_model)
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    result: T = client.chat.completions.create(
        model=api_model,
        response_model=schema,
        messages=messages,
    )
    logger.info("Gemini extraction succeeded, type=%s", type(result).__name__)
    return result


def call_llm(
    prompt: str,
    schema: Type[T],
    model_key: str,
    system_prompt: str | None = None,
) -> T:
    """Provider-aware LLM call and schema validation via instructor."""
    resolved = resolve_model_selection(model_key)
    provider = resolved["provider"]
    model_id = resolved["model_id"]
    if provider == "bedrock":
        return _call_bedrock(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    if provider == "openai":
        return _call_openai(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    if provider == "gemini":
        return _call_gemini(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    raise ValueError(f"Unsupported provider '{provider}' for model_key='{model_key}'")
