import logging
from typing import Type, TypeVar

import instructor
from pydantic import BaseModel

from core.token_usage import TokenUsage
from core.utils import (
    _gemini_model_for_api,
    _get_gemini_client,
    _get_openai_client,
    create_boto3_client,
    resolve_model_selection,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_TOKENS = 4096


def _call_bedrock(prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None) -> T:
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


def _call_bedrock_with_usage(
    prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None
) -> tuple[T, dict]:
    logger.info("Calling Bedrock (with usage) model=%s schema=%s", model_id, schema.__name__)
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
    result, completion = client.messages.create_with_completion(**kwargs)
    raw_usage = completion.get("usage", {}) if isinstance(completion, dict) else {}
    usage = TokenUsage(
        input_tokens=int(raw_usage.get("inputTokens") or 0),
        output_tokens=int(raw_usage.get("outputTokens") or 0),
    ).to_dict()
    return result, usage


def _call_openai(prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None) -> T:
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


def _call_openai_with_usage(
    prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None
) -> tuple[T, dict]:
    logger.info("Calling OpenAI (with usage) model=%s schema=%s", model_id, schema.__name__)
    client = _get_openai_client()
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    result, completion = client.chat.completions.create_with_completion(
        model=model_id,
        response_model=schema,
        messages=messages,
    )
    raw_usage = getattr(completion, "usage", None)
    usage = TokenUsage(
        input_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(raw_usage, "completion_tokens", 0) or 0),
    ).to_dict()
    return result, usage


def _call_gemini(prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None) -> T:
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


def _call_gemini_with_usage(
    prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None
) -> tuple[T, dict]:
    logger.info("Calling Gemini (with usage) model=%s schema=%s", model_id, schema.__name__)
    instructor_model = model_id
    api_model = _gemini_model_for_api(instructor_model)
    client = _get_gemini_client(instructor_model)
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    result, completion = client.chat.completions.create_with_completion(
        model=api_model,
        response_model=schema,
        messages=messages,
    )
    raw_usage = getattr(completion, "usage", None)
    usage = TokenUsage(
        input_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(raw_usage, "completion_tokens", 0) or 0),
    ).to_dict()
    return result, usage


def _call_anthropic(prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None) -> T:
    logger.info("Calling Anthropic model=%s schema=%s", model_id, schema.__name__)
    from core.utils import _get_anthropic_client
    client = _get_anthropic_client()
    kwargs: dict = dict(
        model=model_id,
        response_model=schema,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    if system_prompt:
        kwargs["system"] = system_prompt
    result: T = client.messages.create(**kwargs)
    logger.info("Anthropic extraction succeeded, type=%s", type(result).__name__)
    return result


def _call_anthropic_with_usage(
    prompt: str, schema: Type[T], model_id: str, system_prompt: str | None = None
) -> tuple[T, dict]:
    logger.info("Calling Anthropic (with usage) model=%s schema=%s", model_id, schema.__name__)
    from core.utils import _get_anthropic_client
    client = _get_anthropic_client()
    kwargs: dict = dict(
        model=model_id,
        response_model=schema,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    if system_prompt:
        kwargs["system"] = system_prompt
    result, completion = client.messages.create_with_completion(**kwargs)
    raw_usage = getattr(completion, "usage", None)
    usage = TokenUsage(
        input_tokens=int(getattr(raw_usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(raw_usage, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(raw_usage, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(getattr(raw_usage, "cache_creation_input_tokens", 0) or 0),
    ).to_dict()
    return result, usage


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
    if provider == "anthropic":
        return _call_anthropic(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    raise ValueError(f"Unsupported provider '{provider}' for model_key='{model_key}'")


def call_llm_with_usage(
    prompt: str,
    schema: Type[T],
    model_key: str,
    system_prompt: str | None = None,
) -> tuple[T, dict]:
    """Provider-aware LLM call returning (validated_model, token_usage_dict).

    Token usage dict keys: input_tokens, output_tokens, cache_read_tokens,
    cache_write_tokens, total_tokens. All ints.
    """
    resolved = resolve_model_selection(model_key)
    provider = resolved["provider"]
    model_id = resolved["model_id"]
    if provider == "bedrock":
        return _call_bedrock_with_usage(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    if provider == "openai":
        return _call_openai_with_usage(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    if provider == "anthropic":
        return _call_anthropic_with_usage(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    if provider == "gemini":
        return _call_gemini_with_usage(prompt, schema, model_id=model_id, system_prompt=system_prompt)
    raise ValueError(f"Unsupported provider '{provider}' for model_key='{model_key}'")
