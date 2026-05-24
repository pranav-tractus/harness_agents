"""Explicit post-processing stages for layer-2 refinement.

Each stage has a single concern and a uniform interface, so the pipeline
runner in :mod:`core.postprocess_pipeline` is a flat ordered list. Stages
never raise out of ``run``; they return a ``StageResult`` with ``status``
set to ``ok``, ``skipped``, or ``failed``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from core.postprocess_deterministic import (
    diff_date_fields,
    freeze_date_fields_from_raw,
    normalize_units,
    recompute_totals,
)

logger = logging.getLogger(__name__)


@dataclass
class StageContext:
    """Inputs shared across stages — never mutated by a stage."""

    source_text: str
    reference_iso_date: str
    raw_contract: dict[str, Any]
    extraction_model_key: str
    validation_model_key: str | None = None
    organization_info: dict | None = None
    customer_info: dict | None = None


@dataclass
class StageResult:
    """Per-stage outcome. ``contract`` is the (possibly mutated) working contract."""

    name: str
    status: str  # "ok" | "skipped" | "failed"
    contract: dict[str, Any]
    changes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    error: str = ""
    elapsed_ms: float = 0.0

    def to_diag(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "changes": self.changes,
            "warnings": self.warnings,
            "issues": self.issues,
            "notes": self.notes,
            "error": self.error,
        }


class PostprocessStage(Protocol):
    name: str
    enabled_key: str

    def run(self, contract: dict[str, Any], ctx: StageContext) -> StageResult: ...


def _timed(name: str, contract: dict[str, Any]) -> tuple[StageResult, float]:
    return StageResult(name=name, status="ok", contract=contract), time.perf_counter()


# ---------------------------------------------------------------------------
# Stage 1: NormalizeUnits
# ---------------------------------------------------------------------------


class NormalizeUnitsStage:
    name = "normalize_units"
    enabled_key = "enable_normalize_units"

    def run(self, contract: dict[str, Any], ctx: StageContext) -> StageResult:
        t0 = time.perf_counter()
        try:
            new_contract, changes = normalize_units(contract)
            return StageResult(
                name=self.name,
                status="ok",
                contract=new_contract,
                changes=changes,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )
        except Exception as exc:  # defensive; the helper is stdlib-only
            logger.exception("NormalizeUnitsStage failed")
            return StageResult(
                name=self.name,
                status="failed",
                contract=contract,
                error=str(exc),
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )


# ---------------------------------------------------------------------------
# Stage 2: ValidationLLM
# ---------------------------------------------------------------------------


class ValidationLLMStage:
    name = "validation_llm"
    enabled_key = "enable_validation_llm"

    def run(self, contract: dict[str, Any], ctx: StageContext) -> StageResult:
        t0 = time.perf_counter()
        if not ctx.validation_model_key:
            return StageResult(
                name=self.name,
                status="skipped",
                contract=contract,
                notes="No validation_model_key provided.",
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )
        # Lazy import to keep stdlib-only stages testable without LLM creds.
        from core.llm_client import call_llm
        from core.prompt_builder import (
            build_validation_system_prompt,
            build_validation_user_prompt,
        )
        from core.validation_models import SOValidationResult

        try:
            system_prompt = build_validation_system_prompt(
                organization_info=ctx.organization_info,
                customer_info=ctx.customer_info,
            )
            user_prompt = build_validation_user_prompt(
                source_text=ctx.source_text,
                extraction_json=contract,
            )
            result: SOValidationResult = call_llm(
                user_prompt,
                SOValidationResult,
                model_key=ctx.validation_model_key,
                system_prompt=system_prompt,
            )
            return StageResult(
                name=self.name,
                status="ok",
                contract=result.extraction.model_dump(),
                issues=[i.model_dump() for i in result.issues],
                notes=result.notes,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )
        except (ValidationError, ValueError) as exc:
            logger.warning("Validation LLM returned an invalid payload: %s", exc)
            return StageResult(
                name=self.name,
                status="failed",
                contract=contract,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )
        except Exception as exc:  # network / provider errors
            logger.exception("Validation LLM call failed")
            return StageResult(
                name=self.name,
                status="failed",
                contract=contract,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )


# ---------------------------------------------------------------------------
# Stage 3: RecomputeTotals (runs AFTER the validator so rescales propagate)
# ---------------------------------------------------------------------------


class RecomputeTotalsStage:
    name = "recompute_totals"
    enabled_key = "enable_recompute_totals"

    def run(self, contract: dict[str, Any], ctx: StageContext) -> StageResult:
        t0 = time.perf_counter()
        try:
            new_contract, messages = recompute_totals(contract)
            changes = [m for m in messages if m.get("code") == "deterministic_change"]
            warnings = [m for m in messages if m.get("code") != "deterministic_change"]
            return StageResult(
                name=self.name,
                status="ok",
                contract=new_contract,
                changes=changes,
                warnings=warnings,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )
        except Exception as exc:
            logger.exception("RecomputeTotalsStage failed")
            return StageResult(
                name=self.name,
                status="failed",
                contract=contract,
                error=str(exc),
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )


# ---------------------------------------------------------------------------
# Stage 4: FreezeDates (always copies dates from raw; surfaces what was masked)
# ---------------------------------------------------------------------------


class FreezeDatesStage:
    name = "freeze_dates"
    enabled_key = "enable_freeze_dates"

    def run(self, contract: dict[str, Any], ctx: StageContext) -> StageResult:
        t0 = time.perf_counter()
        try:
            attempted_changes = diff_date_fields(ctx.raw_contract, contract)
            new_contract = freeze_date_fields_from_raw(ctx.raw_contract, contract)
            warnings = [
                {
                    "code": "date_change_masked",
                    "path": d["path"],
                    "message": f"Validator proposed {d['candidate']!r}; restored raw {d['raw']!r}",
                }
                for d in attempted_changes
            ]
            return StageResult(
                name=self.name,
                status="ok",
                contract=new_contract,
                warnings=warnings,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )
        except Exception as exc:
            logger.exception("FreezeDatesStage failed")
            return StageResult(
                name=self.name,
                status="failed",
                contract=contract,
                error=str(exc),
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )


# ---------------------------------------------------------------------------
# Stage 5: StructuralAudit (never mutates)
# ---------------------------------------------------------------------------


def _count_items(contract: dict[str, Any]) -> tuple[int, list[int]]:
    data = contract.get("data") if isinstance(contract.get("data"), list) else []
    contracts = len(data)
    items_per = []
    for block in data:
        items = block.get("items") if isinstance(block, dict) and isinstance(block.get("items"), list) else []
        items_per.append(len(items))
    return contracts, items_per


def _non_empty_fields(block: dict[str, Any]) -> set[str]:
    return {k for k, v in block.items() if v not in (None, "", [], {})}


class StructuralAuditStage:
    name = "structural_audit"
    enabled_key = "enable_structural_audit"

    def run(self, contract: dict[str, Any], ctx: StageContext) -> StageResult:
        t0 = time.perf_counter()
        warnings: list[dict[str, Any]] = []
        try:
            raw_contracts, raw_items = _count_items(ctx.raw_contract)
            cur_contracts, cur_items = _count_items(contract)
            if raw_contracts != cur_contracts:
                warnings.append(
                    {
                        "code": "structural_drift",
                        "path": "data",
                        "message": f"Contract count changed: raw={raw_contracts} final={cur_contracts}",
                    }
                )
            for ci in range(min(len(raw_items), len(cur_items))):
                if raw_items[ci] != cur_items[ci]:
                    warnings.append(
                        {
                            "code": "structural_drift",
                            "path": f"data[{ci}].items",
                            "message": f"Item count changed: raw={raw_items[ci]} final={cur_items[ci]}",
                        }
                    )
            raw_data = ctx.raw_contract.get("data") if isinstance(ctx.raw_contract.get("data"), list) else []
            cur_data = contract.get("data") if isinstance(contract.get("data"), list) else []
            for ci in range(min(len(raw_data), len(cur_data))):
                if not isinstance(raw_data[ci], dict) or not isinstance(cur_data[ci], dict):
                    continue
                emptied = _non_empty_fields(raw_data[ci]) - _non_empty_fields(cur_data[ci])
                emptied.discard("items")
                if emptied:
                    warnings.append(
                        {
                            "code": "field_emptied",
                            "path": f"data[{ci}]",
                            "message": f"Validator removed values from: {sorted(emptied)}",
                        }
                    )
            return StageResult(
                name=self.name,
                status="ok",
                contract=contract,
                warnings=warnings,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )
        except Exception as exc:
            logger.exception("StructuralAuditStage failed")
            return StageResult(
                name=self.name,
                status="failed",
                contract=contract,
                error=str(exc),
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )


DEFAULT_STAGES: list[PostprocessStage] = [
    NormalizeUnitsStage(),
    ValidationLLMStage(),
    RecomputeTotalsStage(),
    FreezeDatesStage(),
    StructuralAuditStage(),
]
