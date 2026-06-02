"""Bare-prompt baseline extractor.

Control condition for measuring how much the full extraction pipeline adds
over a vanilla Claude call: no system prompt, no few-shot, no org/customer
context, no post-processing — just one line of instruction plus the chat text,
validated against the same ``SOExtractContractList`` schema so the output is
field-comparable with the agent's.
"""

from __future__ import annotations

import logging

from core.llm_client import call_llm
from core.models import SOExtractContractList

logger = logging.getLogger(__name__)

BASELINE_PROMPT_TEMPLATE = "Create a sales order from this:\n\n"


def run_baseline(text: str, model_key: str) -> dict | None:
    """Run the no-context baseline extraction.

    Returns the parsed dict on success, or ``None`` on any failure (logged as a
    warning, never raised) so a baseline miss can never fail the agent run.
    """
    prompt = BASELINE_PROMPT_TEMPLATE + text
    try:
        result = call_llm(
            prompt,
            schema=SOExtractContractList,
            model_key=model_key,
            system_prompt=None,
        )
        return result.model_dump()
    except Exception as exc:  # noqa: BLE001 - baseline must never crash the run
        logger.warning("Baseline extraction failed (model=%s, exc_type=%s): %s", model_key, type(exc).__name__, exc)
        return None
