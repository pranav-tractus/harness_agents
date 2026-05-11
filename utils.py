"""Back-compat shim. New code should import from ``core.utils``."""

from core.utils import (  # noqa: F401
    AWS_REGION,
    BEDROCK_ANTHROPIC_MODELS,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_MODEL_KEY,
    GEMINI_MODELS,
    MODEL_CATALOG,
    OPENAI_API_KEY,
    OPENAI_MODELS,
    S3_BUCKET,
    _gemini_model_for_api,
    _get_gemini_client,
    _get_openai_client,
    _normalize_gemini_model,
    build_model_catalog,
    create_boto3_client,
    customer_info,
    get_gemini_response,
    resolve_model_selection,
    setup_streamlit_console_logfile,
    team_info,
)
