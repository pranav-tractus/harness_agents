"""Back-compat shim. New code should import from ``core.llm_client``."""

from core.llm_client import call_llm  # noqa: F401
