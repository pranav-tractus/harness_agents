import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from models import SOUpdateContractList, SOExtractContractList
from openai import OpenAI

import boto3
import instructor

AWS_REGION = "us-east-1"
S3_BUCKET = "tractuslabs-data-sources"

BEDROCK_ANTHROPIC_MODELS = {
    "sonnet-4-5": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "sonnet-4-6": "us.anthropic.claude-sonnet-4-6",
    "opus-4-5": "us.anthropic.claude-opus-4-5-20251101-v1:0",
    "opus-4-6": "us.anthropic.claude-opus-4-6-v1",
    # "opus-4-7": "us.anthropic.claude-opus-4-7",
}

# OpenAI model shorthands and full names
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODELS = {
    "4.1": "gpt-4.1-2025-04-14",
    "5.2": "gpt-5.2-2025-12-11",
    "5-mini": "gpt-5-mini-2025-08-07",
    "5.4": "gpt-5.4-2026-03-05",
}

GEMINI_MODELS = {
    "gemini-2.5-pro": "google/gemini-2.5-pro",
    "gemini-2.5-flash": "google/gemini-2.5-flash",
}

DEFAULT_MODEL_KEY = "sonnet-4-6"
DEFAULT_GEMINI_MODEL = GEMINI_MODELS["gemini-2.5-pro"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

team_info = {
    "name": "Van Beethoven",
    "email": "van@beethonven.com",
    "phone": "+000000000000",
    "address": "123 Main St, Anytown, USA",
}
customer_info = {
    "name": "Leonardo da Vinci",
    "email": "da@vinci.com",
    "id": "432eef62-3867-46b7-abf0-cdb2a09183d6",
}


def create_boto3_client(name: str, region: str = AWS_REGION):
    if os.getenv("IS_LOCAL", "") == "true":
        if name == "dynamodb":
            return boto3.resource(
                name,
                region_name=region,
                aws_access_key_id=os.getenv("ACCESS_KEY"),
                aws_secret_access_key=os.getenv("SECRET_KEY"),
            )
        return boto3.client(
            name,
            region_name=region,
            aws_access_key_id=os.getenv("ACCESS_KEY"),
            aws_secret_access_key=os.getenv("SECRET_KEY"),
        )
    else:
        return boto3.client(name, region_name=region)


def setup_streamlit_console_logfile() -> Path:
    """Mirror console output to a timestamped logfile once per server process."""
    root_logger = logging.getLogger()
    if getattr(root_logger, "_streamlit_logfile_initialized", False):
        return getattr(root_logger, "_streamlit_logfile_path")

    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logfile = logs_dir / f"streamlit-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

    class _TeeStream:
        def __init__(self, *streams):
            self._streams = streams
            self._ansi_re = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

        def write(self, data):
            for stream in self._streams:
                if getattr(stream, "_strip_ansi", False):
                    stream.write(self._ansi_re.sub("", data))
                else:
                    stream.write(data)
                stream.flush()
            return len(data)

        def flush(self):
            for stream in self._streams:
                stream.flush()

        def isatty(self):
            return False

    log_file_handle = logfile.open("a", encoding="utf-8", buffering=1)
    log_file_handle._strip_ansi = True
    sys.stdout = _TeeStream(sys.__stdout__, log_file_handle)
    sys.stderr = _TeeStream(sys.__stderr__, log_file_handle)

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    root_logger._streamlit_logfile_initialized = True
    root_logger._streamlit_logfile_path = logfile
    root_logger.info("Console logging initialized. Writing to %s", logfile.resolve())
    return logfile


def _normalize_gemini_model(name: str) -> str:
    """Ensure model is in form 'google/gemini-*' for instructor."""
    name = (name or "").strip()
    if not name:
        return DEFAULT_GEMINI_MODEL
    if not name.startswith("google/"):
        return f"google/{name}"
    return name


def _gemini_model_for_api(instructor_model: str) -> str:
    """Return model id for google-genai API. SDK builds path as models/{model} - no 'google/' prefix."""
    if not instructor_model:
        return DEFAULT_GEMINI_MODEL.split("/", 1)[-1]
    return (
        instructor_model.split("/", 1)[-1]
        if "/" in instructor_model
        else instructor_model
    )


def _get_gemini_client(model: str):
    """Model must be 'google/gemini-*' for instructor.from_provider."""
    return instructor.from_provider(model)


def get_gemini_response(
    prompt: str | None = None,
    messages: list[dict] | None = None,
    is_update: bool = False,
    model: str | None = None,
) -> SOExtractContractList | SOUpdateContractList:
    model = _normalize_gemini_model(model or DEFAULT_GEMINI_MODEL)
    api_model = _gemini_model_for_api(model)
    gemini_api = _get_gemini_client(model)
    if messages is None:
        messages = [{"role": "user", "content": prompt or ""}]
    try:
        logger.info(
            "get_gemini_response::0:: Sending messages (count=%s), model=%s",
            len(messages),
            api_model,
        )
        response = gemini_api.chat.completions.create(
            model=api_model,
            response_model=SOExtractContractList
            if not is_update
            else SOUpdateContractList,
            messages=messages,
        )
        return response
    except Exception as e:
        logger.exception(
            "get_gemini_response::3:: Error during Gemini processing %s", e
        )
        raise ValueError(e) from e


def _get_openai_client():
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set")
    return instructor.from_openai(OpenAI(api_key=OPENAI_API_KEY))


def build_model_catalog() -> dict[str, dict[str, str]]:
    """Builds a provider-aware model catalog with stable CLI/UI keys."""
    catalog: dict[str, dict[str, str]] = {}
    for key, model_id in BEDROCK_ANTHROPIC_MODELS.items():
        catalog[key] = {
            "provider": "bedrock",
            "model_id": model_id,
            "display_name": f"Bedrock · {key}",
        }
    for key, model_id in OPENAI_MODELS.items():
        full_key = f"openai:{key}"
        catalog[full_key] = {
            "provider": "openai",
            "model_id": model_id,
            "display_name": f"OpenAI · {key}",
        }
    for key, model_id in GEMINI_MODELS.items():
        full_key = f"gemini:{key}"
        catalog[full_key] = {
            "provider": "gemini",
            "model_id": model_id,
            "display_name": f"Gemini · {key}",
        }
    return catalog


MODEL_CATALOG = build_model_catalog()


def resolve_model_selection(model_key: str | None) -> dict[str, Any]:
    """Resolve model key into provider/model metadata.

    Supports:
    - bare Bedrock keys, e.g. "sonnet-4-6"
    - explicit provider keys, e.g. "openai:4.1", "gemini:gemini-2.5-pro"
    """
    key = (model_key or DEFAULT_MODEL_KEY).strip()
    if key in MODEL_CATALOG:
        resolved = dict(MODEL_CATALOG[key])
        resolved["model_key"] = key
        return resolved

    if key in BEDROCK_ANTHROPIC_MODELS:
        return {
            "provider": "bedrock",
            "model_id": BEDROCK_ANTHROPIC_MODELS[key],
            "display_name": f"Bedrock · {key}",
            "model_key": key,
        }

    if key.startswith("openai:"):
        short = key.split(":", 1)[1]
        if short in OPENAI_MODELS:
            return {
                "provider": "openai",
                "model_id": OPENAI_MODELS[short],
                "display_name": f"OpenAI · {short}",
                "model_key": key,
            }

    if key.startswith("gemini:"):
        short = key.split(":", 1)[1]
        if short in GEMINI_MODELS:
            return {
                "provider": "gemini",
                "model_id": GEMINI_MODELS[short],
                "display_name": f"Gemini · {short}",
                "model_key": key,
            }

    valid = ", ".join(sorted(MODEL_CATALOG.keys()))
    raise ValueError(f"Unknown model key '{key}'. Valid keys: {valid}")
