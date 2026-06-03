"""Layer-2 post-processing as an ordered list of explicit stages.

The public signature of :func:`run_postprocess_pipeline` is preserved so the
agent / runner / dashboard wiring is unchanged. The implementation is now a
thin runner over :data:`core.postprocess_stages.DEFAULT_STAGES`.

Diagnostics carry a per-stage report (``diagnostics["stages"]``) plus the
legacy flat keys (``deterministic_changes``, ``validation_issues``, etc.) so
existing report / dashboard code keeps working without changes.
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any

from core.postprocess_stages import (
    DEFAULT_STAGES,
    PostprocessStage,
    StageContext,
    StageResult,
    ValidationLLMStage,
)

logger = logging.getLogger(__name__)


def run_validation_llm(
    *,
    source_text: str,
    contract: dict[str, Any],
    validation_model_key: str,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Convenience wrapper around the validation stage (kept for back-compat)."""
    ctx = StageContext(
        source_text=source_text,
        reference_iso_date="",
        raw_contract=contract,
        extraction_model_key="",
        validation_model_key=validation_model_key,
        organization_info=organization_info,
        customer_info=customer_info,
    )
    result = ValidationLLMStage().run(contract, ctx)
    if result.status == "failed":
        raise RuntimeError(result.error or "validation LLM failed")
    return result.contract, result.issues, result.notes


def _stage_enabled(stage: PostprocessStage, flags: dict[str, bool]) -> bool:
    return bool(flags.get(stage.enabled_key, True))


def run_postprocess_pipeline(
    raw_contract: dict[str, Any],
    *,
    source_text: str,
    reference_iso_date: str,
    extraction_model_key: str,
    validation_model_key: str | None = None,
    enable_deterministic: bool = True,
    enable_validation_llm: bool = True,
    organization_info: dict | None = None,
    customer_info: dict | None = None,
    stages: list[PostprocessStage] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run layer-2 refinement. Returns ``(final_contract, diagnostics)``.

    ``enable_deterministic`` (legacy) toggles the unit-normalize and
    total-recompute stages together. The freeze-dates and structural-audit
    stages are always run when enabled (they are cheap and have no side
    effects beyond emitting warnings).
    """
    t0 = time.perf_counter()
    diagnostics: dict[str, Any] = {
        "extraction_model_key": extraction_model_key,
        "validation_model_key": validation_model_key,
        "stages": [],
        "warnings": [],
        "deterministic_changes": [],
        "validation_issues": [],
        "validation_notes": "",
    }

    if enable_validation_llm and not validation_model_key:
        diagnostics["warnings"].append(
            {
                "code": "validation_skipped_no_model",
                "path": "<pipeline>",
                "message": "enable_validation_llm=True but no validation_model_key provided.",
            }
        )
        logger.info("Validation LLM enabled but no validation_model_key; skipping.")

    flags = {
        "enable_normalize_units": enable_deterministic,
        "enable_validation_llm": enable_validation_llm,
        "enable_recompute_totals": enable_deterministic,
        "enable_freeze_dates": True,
        "enable_structural_audit": True,
    }
    ctx = StageContext(
        source_text=source_text,
        reference_iso_date=reference_iso_date,
        raw_contract=copy.deepcopy(raw_contract),
        extraction_model_key=extraction_model_key,
        validation_model_key=validation_model_key,
        organization_info=organization_info,
        customer_info=customer_info,
    )

    working = copy.deepcopy(raw_contract)
    for stage in stages or DEFAULT_STAGES:
        if not _stage_enabled(stage, flags):
            diagnostics["stages"].append({
                "name": stage.name,
                "status": "skipped",
                "elapsed_ms": 0.0,
                "reason": "disabled-by-flag",
            })
            continue
        result: StageResult = stage.run(working, ctx)
        diagnostics["stages"].append(result.to_diag())
        if result.status == "ok":
            working = result.contract
        elif result.status == "failed":
            diagnostics.setdefault("stage_errors", []).append({"stage": stage.name, "error": result.error})
            # Keep going — downstream stages get the unchanged working contract.

        # Mirror per-stage findings into the legacy flat lists so existing
        # reports keep rendering without a code change.
        diagnostics["warnings"].extend(result.warnings)
        if stage.name == "validation_llm" and result.status == "ok":
            diagnostics["validation_issues"] = result.issues
            diagnostics["validation_notes"] = result.notes
            if hasattr(result, "token_usage") and result.token_usage:
                diagnostics["validation_token_usage"] = result.token_usage
        if stage.name == "validation_llm" and result.status == "failed":
            diagnostics["validation_error"] = result.error
        if result.changes and stage.name in ("normalize_units", "recompute_totals"):
            diagnostics["deterministic_changes"].extend(result.changes)

    # Legacy timing keys.
    stage_ms = {s["name"]: s.get("elapsed_ms", 0.0) for s in diagnostics["stages"]}
    diagnostics["deterministic_ms"] = round(
        stage_ms.get("normalize_units", 0.0) + stage_ms.get("recompute_totals", 0.0), 3
    )
    diagnostics["llm_validate_ms"] = stage_ms.get("validation_llm", 0.0)
    diagnostics["postprocess_total_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    return working, diagnostics
