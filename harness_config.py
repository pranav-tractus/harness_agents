from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class CustomerFewShotConfig(BaseModel):
    labels: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)


class CustomerSyntheticConfig(BaseModel):
    chats_to_generate: int = 0
    complexity_tiers: list[str] = Field(
        default_factory=lambda: ["simple", "medium", "complex"]
    )
    scenario_tags: list[str] = Field(default_factory=list)


class CustomerProfile(BaseModel):
    id: str
    name: str
    db_path: str
    dataset_root: str
    chat_globs: list[str] = Field(default_factory=lambda: ["chats/*.json"])
    few_shot: CustomerFewShotConfig = Field(default_factory=CustomerFewShotConfig)
    organization_info: dict[str, Any] | None = None
    customer_info: dict[str, Any] | None = None
    synthetic_generation: CustomerSyntheticConfig = Field(
        default_factory=CustomerSyntheticConfig
    )


class HarnessConfig(BaseModel):
    version: int = 1
    default_customer_id: str | None = None
    customers: list[CustomerProfile]


@dataclass(frozen=True)
class CustomerRuntimeContext:
    customer: CustomerProfile
    root_dir: Path

    @property
    def db_path(self) -> Path:
        return _resolve_from_root(self.customer.db_path, self.root_dir)

    @property
    def dataset_root(self) -> Path:
        return _resolve_from_root(self.customer.dataset_root, self.root_dir)

    def expand_globs(self) -> list[Path]:
        root = self.dataset_root
        out: list[Path] = []
        for pattern in self.customer.chat_globs:
            out.extend(sorted(root.glob(pattern)))
        # stable + unique
        return sorted({p.resolve() for p in out})


def _resolve_from_root(value: str, root_dir: Path) -> Path:
    p = Path(value).expanduser()
    if p.is_absolute():
        return p
    return (root_dir / p).resolve()


def load_harness_config(path: str | Path) -> HarnessConfig:
    cfg_path = Path(path).expanduser().resolve()
    raw_text = cfg_path.read_text(encoding="utf-8")
    suffix = cfg_path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(raw_text)
    elif suffix in {".yml", ".yaml"}:
        raise ValueError(
            "YAML config is not enabled in this repo yet. Use JSON config files."
        )
    else:
        raise ValueError(f"Unsupported config extension: {cfg_path.suffix}")
    try:
        return HarnessConfig.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid harness config at {cfg_path}: {exc}") from exc


def get_customer_context(
    config: HarnessConfig,
    root_dir: Path,
    customer_id: str | None = None,
) -> CustomerRuntimeContext:
    target_id = customer_id or config.default_customer_id
    if not target_id and config.customers:
        target_id = config.customers[0].id
    for customer in config.customers:
        if customer.id == target_id:
            return CustomerRuntimeContext(customer=customer, root_dir=root_dir)
    known = ", ".join(sorted(c.id for c in config.customers))
    raise ValueError(f"Unknown customer id '{target_id}'. Known customers: {known}")
