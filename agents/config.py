"""Single-source-of-truth agent + pipeline loader.

Replaces ``harness_config.py``. A JSON file (default ``configs/agents.json``)
declares all known agents, their datasets, db paths, few-shot pools, and any
pipelines that chain agents together.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.base import BaseAgent, Dataset, Pipeline


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "agents.json"


@dataclass(frozen=True)
class PipelineSpec:
    id: str
    steps: tuple[str, ...]


@dataclass
class HarnessConfig:
    """Parsed agents.json plus a few helpers."""

    repo_root: Path
    raw: dict[str, Any]
    pipelines: tuple[PipelineSpec, ...] = field(default_factory=tuple)
    _agent_specs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _agent_cache: dict[str, BaseAgent] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "HarnessConfig":
        cfg_path = Path(path or DEFAULT_CONFIG_PATH).expanduser().resolve()
        if not cfg_path.exists():
            raise FileNotFoundError(f"Agent config not found: {cfg_path}")
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid agent config in {cfg_path}: top-level must be an object")
        agent_specs: dict[str, dict[str, Any]] = {}
        for spec in raw.get("agents", []):
            aid = spec.get("id")
            if not aid:
                raise ValueError(f"Agent entry missing 'id' in {cfg_path}")
            agent_specs[aid] = spec
        pipelines = tuple(
            PipelineSpec(id=p["id"], steps=tuple(p["steps"]))
            for p in raw.get("pipelines", [])
        )
        return cls(
            repo_root=REPO_ROOT,
            raw=raw,
            pipelines=pipelines,
            _agent_specs=agent_specs,
        )

    def agent_ids(self) -> list[str]:
        return list(self._agent_specs.keys())

    def pipeline_ids(self) -> list[str]:
        return [p.id for p in self.pipelines]

    def get_pipeline_spec(self, pipeline_id: str) -> PipelineSpec:
        for p in self.pipelines:
            if p.id == pipeline_id:
                return p
        known = ", ".join(self.pipeline_ids()) or "<none>"
        raise KeyError(f"Unknown pipeline '{pipeline_id}'. Known: {known}")

    def _resolve_path(self, value: str | None) -> Path | None:
        if not value:
            return None
        p = Path(value).expanduser()
        return p if p.is_absolute() else (self.repo_root / p).resolve()

    def _build_dataset(self, payload: dict[str, Any], default_db_path: Path | None) -> Dataset:
        ds_id = payload.get("id") or "default"
        chat_globs = tuple(payload.get("chat_globs") or payload.get("doc_globs") or [])
        db_path = self._resolve_path(payload.get("db_path")) or default_db_path
        return Dataset(
            id=ds_id,
            globs=chat_globs,
            db_path=db_path,
            organization_info=payload.get("organization_info"),
            customer_info=payload.get("customer_info"),
            extra={k: v for k, v in payload.items() if k not in {
                "id", "chat_globs", "doc_globs", "db_path",
                "organization_info", "customer_info",
            }},
        )

    def get_agent(self, agent_id: str) -> BaseAgent:
        if agent_id in self._agent_cache:
            return self._agent_cache[agent_id]
        if agent_id not in self._agent_specs:
            known = ", ".join(self.agent_ids()) or "<none>"
            raise KeyError(f"Unknown agent '{agent_id}'. Known: {known}")

        spec = self._agent_specs[agent_id]
        module_path = spec.get("module")
        if not module_path or ":" not in module_path:
            raise ValueError(
                f"Agent '{agent_id}' must declare module as 'pkg.mod:ClassName' (got {module_path!r})."
            )
        module_name, class_name = module_path.split(":", 1)
        module = importlib.import_module(module_name)
        agent_cls = getattr(module, class_name)

        default_db_path = self._resolve_path(spec.get("db_path"))
        datasets = [
            self._build_dataset(ds, default_db_path)
            for ds in spec.get("datasets", [])
        ]
        agent = agent_cls(
            id=spec["id"],
            display_name=spec.get("display_name", spec["id"].replace("_", " ").title()),
            datasets=datasets,
            few_shot_globs=tuple(spec.get("few_shot_globs", [])),
            repo_root=self.repo_root,
            db_path=default_db_path,
            consumes_output_of=spec.get("consumes_output_of"),
        )
        self._agent_cache[agent_id] = agent
        return agent

    def build_pipeline(self, pipeline_id: str) -> Pipeline:
        spec = self.get_pipeline_spec(pipeline_id)
        agents = [self.get_agent(aid) for aid in spec.steps]
        return Pipeline(agents)


def load_config(path: str | Path | None = None) -> HarnessConfig:
    return HarnessConfig.load(path)
