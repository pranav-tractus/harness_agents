"""Sales-order extraction agent: chat text -> SOExtractContractList."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.base import AgentRunResult, BaseAgent, Dataset, RunOptions, ScoreResult
from core.baseline_extractor import run_baseline
from core.chat_loader import build_extraction_few_shot_from_paths, load_chat_file
from core.extractor import ExtractionEngine
from core.models import SOExtractContractList
from core.postprocess_pipeline import run_postprocess_pipeline
from harness.scoring import json_diff

logger = logging.getLogger(__name__)


@dataclass
class ChatInput:
    """Input payload for the SO extraction agent."""

    source_path: Path
    text: str
    meta: dict[str, Any]


def _postprocess_options(extra: dict[str, Any], extraction_model_key: str) -> dict[str, Any]:
    enable_det = extra.get("enable_deterministic_postprocess", True)
    enable_val = extra.get("enable_validation_llm", True)
    validation_key = extra.get("validation_model_key") or extraction_model_key
    return {
        "enable_deterministic": bool(enable_det),
        "enable_validation_llm": bool(enable_val),
        "validation_model_key": validation_key if enable_val else None,
    }


class SOExtractionAgent(BaseAgent[ChatInput, dict]):
    """Wraps :class:`core.extractor.ExtractionEngine` as a pluggable agent.

    Few-shot examples are loaded from arbitrary chat JSONs (any subset of the
    agent's few-shot pool, capped to 0..10 by the runner). Per-dataset
    ``organization_info`` / ``customer_info`` / ``db_path`` override the
    engine's defaults so customer-scoped DBs and prompt context still work.

    After primary extraction, deterministic rules and an optional validation LLM
    refine the JSON. Dates are never auto-updated; other fields (totals, units)
    may be corrected. Dual scores compare raw vs final against expected.
    """

    input_type = ChatInput
    output_type = SOExtractContractList

    def load_input(self, source_path: Any) -> ChatInput:
        if isinstance(source_path, ChatInput):
            return source_path
        path = Path(source_path).expanduser().resolve()
        loaded = load_chat_file(path)
        text = (loaded.get("text") or "").strip()
        return ChatInput(source_path=path, text=text, meta=loaded.get("meta", {}))

    def run_one(self, input_payload: ChatInput, options: RunOptions) -> AgentRunResult[dict]:
        dataset_id = options.dataset_id or self._dataset_for(input_payload.source_path)
        dataset = self.get_dataset(dataset_id) if dataset_id else None
        organization_info = dataset.organization_info if dataset else None
        customer_info = dataset.customer_info if dataset else None
        db_path = options.db_path or (dataset.db_path if dataset else None) or self._db_path

        t0 = time.perf_counter()
        engine_kwargs: dict[str, Any] = {"model_key": options.model_key}
        if db_path is not None:
            engine_kwargs["db_path"] = Path(db_path)
        if organization_info:
            engine_kwargs["organization_info"] = organization_info
        if customer_info:
            engine_kwargs["customer_info"] = customer_info
        engine = ExtractionEngine(**engine_kwargs)
        t_engine = time.perf_counter()

        fs_paths = list(options.few_shot_paths or [])
        extra_fs = build_extraction_few_shot_from_paths(fs_paths) if fs_paths else None
        db_few_shot_limit = int(options.extra.get("db_few_shot_limit", 0))
        t_fs = time.perf_counter()

        result = engine.run(
            input_payload.text,
            extra_few_shot_examples=extra_fs,
            db_few_shot_limit=db_few_shot_limit,
        )
        t_extract = time.perf_counter()

        raw_dict: dict[str, Any] | None = None
        final_dict: dict[str, Any] | None = None
        diagnostics: dict[str, Any] | None = None

        if result.status == "success" and result.output_json:
            try:
                raw_dict = json.loads(result.output_json)
            except json.JSONDecodeError:
                raw_dict = None

        pp_opts = _postprocess_options(options.extra, options.model_key)
        validation_model_key = pp_opts["validation_model_key"]

        if raw_dict is not None:
            t_pp = time.perf_counter()
            final_dict, diagnostics = run_postprocess_pipeline(
                raw_dict,
                source_text=input_payload.text,
                reference_iso_date=engine.iso_date,
                extraction_model_key=options.model_key,
                validation_model_key=validation_model_key,
                enable_deterministic=pp_opts["enable_deterministic"],
                enable_validation_llm=pp_opts["enable_validation_llm"],
                organization_info=organization_info,
                customer_info=customer_info,
            )
            if diagnostics is not None:
                diagnostics["llm_extract_ms"] = round((t_extract - t_fs) * 1000, 3)
                diagnostics["chunk_count"] = result.chunk_count
                diagnostics["chunk_truncated"] = result.chunk_truncated
                diagnostics["input_chars"] = result.input_chars
                if result.chunk_truncated:
                    diagnostics.setdefault("warnings", []).append({
                        "code": "chunk_truncated",
                        "path": "<input>",
                        "message": (
                            f"Input was {result.input_chars} chars, split into {result.chunk_count} chunks; "
                            f"only chunk[0] was sent to the extraction LLM."
                        ),
                    })
        t_done = time.perf_counter()

        expected = self.expected_for(input_payload.source_path)
        score_raw = self.score(expected, raw_dict)
        score_final = self.score(expected, final_dict)

        if not result.status == "success" and score_final.expected_available:
            score_final = ScoreResult(
                expected_available=True,
                compared_field_count=score_final.compared_field_count,
                mismatch_count=score_final.mismatch_count + 1,
                mismatches=score_final.mismatches,
                metrics=score_final.metrics,
            )

        flow_ms = {
            "engine_init_ms": round((t_engine - t0) * 1000, 3),
            "fewshot_plan_ms": round((t_fs - t_engine) * 1000, 3),
            "llm_extract_ms": round((t_extract - t_fs) * 1000, 3),
            "postprocess_total_ms": (diagnostics or {}).get("postprocess_total_ms", round((t_done - t_extract) * 1000, 3)),
            "deterministic_ms": (diagnostics or {}).get("deterministic_ms", 0.0),
            "llm_validate_ms": (diagnostics or {}).get("llm_validate_ms", 0.0),
            "total_case_ms": round((t_done - t0) * 1000, 3),
        }

        baseline_dict: dict[str, Any] | None = None
        score_baseline = ScoreResult()
        if options.extra.get("run_baseline"):
            t_baseline_start = time.perf_counter()
            baseline_dict = run_baseline(input_payload.text, options.model_key)
            score_baseline = self.score(expected, baseline_dict)
            flow_ms["baseline_ms"] = round((time.perf_counter() - t_baseline_start) * 1000, 3)

        # Collect token usage from extraction and (if available) validation.
        agent_token_usage: dict | None = None
        if result.token_usage:
            agent_token_usage = dict(result.token_usage)
        val_usage = (diagnostics or {}).get("validation_token_usage")
        if val_usage and isinstance(val_usage, dict):
            if agent_token_usage is None:
                agent_token_usage = dict(val_usage)
            else:
                for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
                    agent_token_usage[k] = agent_token_usage.get(k, 0) + val_usage.get(k, 0)
                agent_token_usage["total_tokens"] = (
                    agent_token_usage.get("input_tokens", 0)
                    + agent_token_usage.get("output_tokens", 0)
                )

        return AgentRunResult[dict](
            agent_id=self.id,
            dataset_id=dataset_id or "default",
            source_path=str(input_payload.source_path),
            success=result.status == "success",
            status=result.status,
            attempts=result.attempts,
            elapsed_sec=round(t_done - t0, 4),
            output=final_dict,
            output_json=final_dict,
            raw_llm_output_json=raw_dict,
            error=result.error,
            model_key=result.model_key,
            model_provider=result.model_provider,
            validation_model_key=validation_model_key,
            score=score_final,
            score_raw_llm=score_raw,
            score_baseline=score_baseline,
            baseline_output_json=baseline_dict,
            token_usage=agent_token_usage,
            extraction_diagnostics=diagnostics,
            flow_stage_ms=flow_ms,
            few_shot_paths=[str(p) for p in fs_paths],
            few_shot_count=len(fs_paths),
        )

    def expected_for(self, source_path: Path) -> dict[str, Any] | None:
        from agents.so_extraction.expected_results import get_expected_for_chat
        return get_expected_for_chat(Path(source_path).name)

    def score(self, expected: dict[str, Any] | None, actual: dict[str, Any] | None) -> ScoreResult:
        return json_diff(expected, actual)

    def _dataset_for(self, path: Path) -> str | None:
        """Best-effort match of an input path to one of this agent's datasets."""
        resolved = Path(path).resolve()
        for ds in self._datasets:
            for candidate in ds.expand(self._repo_root):
                if candidate == resolved:
                    return ds.id
        return None
