"""Pluggable Agent abstraction.

The runner is generic over the agent: it asks each agent for its datasets,
few-shot pool, run hook, and score hook. Future agents only need to subclass
:class:`BaseAgent` and register in ``configs/agents.json``.

Agents are typed by their input and output (``BaseAgent[I, O]``) so that the
:class:`Pipeline` helper can statically validate "agent A's output feeds agent
B's input".
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

I = TypeVar("I")
O = TypeVar("O")


@dataclass(frozen=True)
class Dataset:
    """A named bag of source files an agent owns.

    For chat-based agents (e.g. ``so_extraction``) ``globs`` resolve to chat
    JSONs; for doc-based agents (e.g. ``product_retrieval``) they resolve to
    spec PDFs/MD files. ``organization_info`` / ``customer_info`` are optional
    context propagated to the underlying engine.
    """

    id: str
    globs: tuple[str, ...]
    db_path: Path | None = None
    organization_info: dict[str, Any] | None = None
    customer_info: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def expand(self, root: Path) -> list[Path]:
        seen: set[Path] = set()
        out: list[Path] = []
        for pattern in self.globs:
            for path in sorted(root.glob(pattern)):
                resolved = path.resolve()
                if resolved in seen or not resolved.is_file():
                    continue
                seen.add(resolved)
                out.append(resolved)
        return out


@dataclass
class ScoreResult:
    """Per-run scoring outcome from an agent.

    Field semantics depend on the agent:
    - extraction-style agents fill ``mismatch_count`` / ``compared_field_count``
    - retrieval-style agents fill ``metrics`` (e.g. ``precision@5``, ``recall@5``)
    """

    expected_available: bool = False
    mismatch_count: int = 0
    compared_field_count: int = 0
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def field_match_rate(self) -> float | None:
        if not self.expected_available or self.compared_field_count <= 0:
            return None
        return 1.0 - (self.mismatch_count / max(self.compared_field_count, 1))


@dataclass
class AgentRunResult(Generic[O]):
    """The output of one agent invocation on one input."""

    agent_id: str
    dataset_id: str
    source_path: str
    success: bool
    status: str
    attempts: int
    elapsed_sec: float
    output: O | None = None
    output_json: dict[str, Any] | None = None
    error: str | None = None
    model_key: str | None = None
    model_provider: str | None = None
    score: ScoreResult = field(default_factory=ScoreResult)
    flow_stage_ms: dict[str, float] = field(default_factory=dict)
    few_shot_paths: list[str] = field(default_factory=list)
    few_shot_count: int = 0
    pipeline_step: int = 0
    started_at_utc: str = ""

    def __post_init__(self) -> None:
        if not self.started_at_utc:
            self.started_at_utc = datetime.now(timezone.utc).isoformat()


@dataclass
class RunOptions:
    """Per-invocation knobs passed to ``run_one``."""

    model_key: str
    few_shot_paths: list[Path] = field(default_factory=list)
    dataset_id: str | None = None
    db_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseAgent(Generic[I, O], ABC):
    """Common surface every agent must implement."""

    id: str
    display_name: str
    input_type: type
    output_type: type

    def __init__(
        self,
        *,
        id: str,
        display_name: str,
        datasets: list[Dataset],
        few_shot_globs: tuple[str, ...] = (),
        repo_root: Path,
        db_path: Path | None = None,
        consumes_output_of: str | None = None,
    ) -> None:
        self.id = id
        self.display_name = display_name
        self._datasets = list(datasets)
        self._few_shot_globs = tuple(few_shot_globs)
        self._repo_root = Path(repo_root).resolve()
        self._db_path = Path(db_path).resolve() if db_path else None
        self.consumes_output_of = consumes_output_of

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def db_path(self) -> Path | None:
        return self._db_path

    def datasets(self) -> list[Dataset]:
        return list(self._datasets)

    def get_dataset(self, dataset_id: str) -> Dataset:
        for ds in self._datasets:
            if ds.id == dataset_id:
                return ds
        known = ", ".join(d.id for d in self._datasets) or "<none>"
        raise KeyError(f"Unknown dataset '{dataset_id}' for agent '{self.id}'. Known: {known}")

    def few_shot_pool(self) -> list[Path]:
        seen: set[Path] = set()
        out: list[Path] = []
        for pattern in self._few_shot_globs:
            for path in sorted(self._repo_root.glob(pattern)):
                resolved = path.resolve()
                if resolved in seen or not resolved.is_file():
                    continue
                seen.add(resolved)
                out.append(resolved)
        return out

    def all_source_paths(self) -> list[tuple[str, Path]]:
        out: list[tuple[str, Path]] = []
        for ds in self._datasets:
            for path in ds.expand(self._repo_root):
                out.append((ds.id, path))
        return out

    # --- abstract surface ---

    @abstractmethod
    def load_input(self, source_path: Path) -> I:
        """Translate a dataset source path into the agent's input payload."""

    @abstractmethod
    def run_one(self, input_payload: I, options: RunOptions) -> AgentRunResult[O]:
        """Execute the agent and return a populated :class:`AgentRunResult`."""

    @abstractmethod
    def expected_for(self, source_path: Path) -> Any | None:
        """Return the manually curated expected output for this source, if any."""

    @abstractmethod
    def score(self, expected: Any | None, actual: dict[str, Any] | None) -> ScoreResult:
        """Compare an actual output against the expected output for the same source."""

    # --- helpers shared by all agents ---

    def coverage(self, dataset_id: str | None = None) -> dict[str, bool]:
        """Map ``chat_filename -> has_expected`` across this agent's datasets."""
        out: dict[str, bool] = {}
        datasets = [self.get_dataset(dataset_id)] if dataset_id else self._datasets
        for ds in datasets:
            for path in ds.expand(self._repo_root):
                out[path.name] = self.expected_for(path) is not None
        return out


class Pipeline:
    """Chain agents so output of step N feeds input of step N+1.

    Agents are responsible for declaring how to interpret upstream output via
    their ``load_input`` hooks; the pipeline simply hands the previous
    ``AgentRunResult.output`` (or ``output_json``) to the next agent's
    ``run_one`` after a wrapping ``load_input`` call.
    """

    def __init__(self, agents: list[BaseAgent]) -> None:
        if not agents:
            raise ValueError("Pipeline requires at least one agent.")
        self.agents = list(agents)

    @property
    def id(self) -> str:
        return "->".join(a.id for a in self.agents)

    def run(
        self,
        source_path: Path,
        options_per_step: list[RunOptions],
    ) -> list[AgentRunResult]:
        if len(options_per_step) != len(self.agents):
            raise ValueError(
                f"Pipeline has {len(self.agents)} steps; got {len(options_per_step)} option sets."
            )
        results: list[AgentRunResult] = []
        current_input: Any = source_path
        for step_idx, (agent, opts) in enumerate(zip(self.agents, options_per_step)):
            t0 = time.perf_counter()
            payload = agent.load_input(current_input) if isinstance(current_input, Path) else current_input
            t_load = time.perf_counter()
            result = agent.run_one(payload, opts)
            result.pipeline_step = step_idx
            result.flow_stage_ms.setdefault(
                "pipeline_input_load_ms", round((t_load - t0) * 1000, 3),
            )
            results.append(result)
            if not result.success or result.output is None:
                logger.warning(
                    "Pipeline halted at step %d (agent=%s, status=%s).",
                    step_idx, agent.id, result.status,
                )
                break
            current_input = result.output
        return results
