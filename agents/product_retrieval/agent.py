"""Product spec retrieval agent (scaffold).

Consumes the upstream SO summary and (eventually) queries a separate
product-specs DB to return the K most relevant spec documents per line item.
For now the agent is a stub: it returns a ``NotImplementedError`` failure so
the pipeline plumbing can be exercised end-to-end while the real retrieval
backend is implemented separately.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.base import AgentRunResult, BaseAgent, RunOptions, ScoreResult
from harness.scoring import retrieval_metrics

logger = logging.getLogger(__name__)


@dataclass
class SummaryInput:
    """Input payload for the retrieval agent: the upstream SO summary."""

    summary: dict[str, Any]
    source_chat: str | None = None


class ProductRetrievalAgent(BaseAgent[SummaryInput, list[dict[str, Any]]]):
    """Skeleton retrieval agent.

    Future work (not in this revamp):
    - build / load an index over ``raw_data/product_specs/`` declared in the
      agent's dataset globs
    - implement ``run_one`` to query that index and return ``[{doc_id, score, snippet}]``
    - extend ``expected_for`` to return the curated relevant-doc list per chat
    """

    input_type = SummaryInput
    output_type = list

    def load_input(self, source_path: Any) -> SummaryInput:
        if isinstance(source_path, SummaryInput):
            return source_path
        if isinstance(source_path, dict):
            return SummaryInput(summary=source_path)
        raise TypeError(
            "ProductRetrievalAgent expects an SOExtractContractList dict from the upstream agent; "
            f"got {type(source_path).__name__}."
        )

    def run_one(self, input_payload: SummaryInput, options: RunOptions) -> AgentRunResult[list[dict[str, Any]]]:
        t0 = time.perf_counter()
        error = (
            "ProductRetrievalAgent.run_one is not implemented yet. "
            "Plug in your retrieval backend (vector store / BM25 / LLM rerank) here."
        )
        return AgentRunResult[list[dict[str, Any]]](
            agent_id=self.id,
            dataset_id=options.dataset_id or "specs",
            source_path=input_payload.source_chat or "",
            success=False,
            status="not_implemented",
            attempts=0,
            elapsed_sec=round(time.perf_counter() - t0, 4),
            output=None,
            output_json=None,
            error=error,
            model_key=options.model_key,
            model_provider=None,
            score=ScoreResult(expected_available=False),
            few_shot_paths=[str(p) for p in (options.few_shot_paths or [])],
            few_shot_count=len(options.few_shot_paths or []),
        )

    def expected_for(self, source_path: Path) -> list[str] | None:
        from agents.product_retrieval.expected_results import get_expected_doc_ids
        return get_expected_doc_ids(Path(source_path).name)

    def score(self, expected: list[str] | None, actual: list[dict[str, Any]] | None) -> ScoreResult:
        return retrieval_metrics(expected, actual)

    def expected_from_output(self, output: Any) -> Any:
        """Reduce ``[{doc_id, score, snippet}, ...]`` to the ordered doc-id list."""
        if isinstance(output, list):
            doc_ids: list[str] = []
            for entry in output:
                if isinstance(entry, dict) and entry.get("doc_id"):
                    doc_ids.append(str(entry["doc_id"]))
            return doc_ids
        return output
