"""Sales-order extraction agent: chat text -> SOExtractContractList."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.base import AgentRunResult, BaseAgent, Dataset, RunOptions, ScoreResult
from core.chat_loader import build_extraction_few_shot_from_paths, load_chat_file
from core.extractor import ExtractionEngine
from core.models import SOExtractContractList
from harness.scoring import json_diff

logger = logging.getLogger(__name__)


@dataclass
class ChatInput:
    """Input payload for the SO extraction agent."""

    source_path: Path
    text: str
    meta: dict[str, Any]


class SOExtractionAgent(BaseAgent[ChatInput, dict]):
    """Wraps :class:`core.extractor.ExtractionEngine` as a pluggable agent.

    Few-shot examples are loaded from arbitrary chat JSONs (any subset of the
    agent's few-shot pool, capped to 0..10 by the runner). Per-dataset
    ``organization_info`` / ``customer_info`` / ``db_path`` override the
    engine's defaults so customer-scoped DBs and prompt context still work.
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
        t_done = time.perf_counter()

        output_dict: dict[str, Any] | None = None
        if result.status == "success" and result.output_json:
            try:
                output_dict = json.loads(result.output_json)
            except json.JSONDecodeError:
                output_dict = None

        score = self.score(self.expected_for(input_payload.source_path), output_dict)
        if not result.status == "success" and score.expected_available:
            score = ScoreResult(
                expected_available=True,
                compared_field_count=score.compared_field_count,
                mismatch_count=score.mismatch_count + 1,
                mismatches=score.mismatches,
                metrics=score.metrics,
            )

        return AgentRunResult[dict](
            agent_id=self.id,
            dataset_id=dataset_id or "default",
            source_path=str(input_payload.source_path),
            success=result.status == "success",
            status=result.status,
            attempts=result.attempts,
            elapsed_sec=round(t_done - t0, 4),
            output=output_dict,
            output_json=output_dict,
            error=result.error,
            model_key=result.model_key,
            model_provider=result.model_provider,
            score=score,
            flow_stage_ms={
                "engine_init_ms": round((t_engine - t0) * 1000, 3),
                "fewshot_plan_ms": round((t_fs - t_engine) * 1000, 3),
                "model_run_ms": round((t_done - t_fs) * 1000, 3),
                "total_case_ms": round((t_done - t0) * 1000, 3),
            },
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
