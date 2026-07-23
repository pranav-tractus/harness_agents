from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from core.llm_client import call_llm

_PROMPT = """\
You normalize a product catalog entry for a commodity trading system.
Given the product name, descriptions, spec, and structured metadata, extract:
- aliases: common alternate names / how a customer might refer to it in chat
  (mine these from the name, short description, and long description)
- grade, packing_size, unit: normalized spec attributes when present
- attributes: any other normalized spec key/value pairs; TREAT the provided
  metadata as authoritative and carry each metadata entry through verbatim

Return empty lists, empty objects, or null when a field is not determinable.

Product name: {name}
Short description: {short_description}
Long description: {long_description}
Product spec: {spec}
Metadata (authoritative key/values): {metadata}
"""


class ProductFacts(BaseModel):
    aliases: list[str] = Field(default_factory=list, description="Alternate names / common references")
    grade: Optional[str] = Field(default=None, description="Product grade if stated")
    packing_size: Optional[str] = Field(default=None, description="Packing size, e.g. 25kg")
    unit: Optional[str] = Field(default=None, description="Trading unit, e.g. MT, KG")
    attributes: dict[str, str] = Field(default_factory=dict, description="Other normalized spec key/values")


def _fmt_metadata(metadata: dict[str, str] | None) -> str:
    if not metadata:
        return ""
    return ", ".join(f"{k}={v}" for k, v in sorted(metadata.items()))


def extract_product_facts(
    name: str | None,
    short_description: str,
    long_description: str | None,
    spec: str | None,
    metadata: dict[str, str] | None = None,
    model_key: str = "openai:5.5",
) -> ProductFacts:
    prompt = _PROMPT.format(
        name=name or "",
        short_description=short_description or "",
        long_description=long_description or "",
        spec=spec or "",
        metadata=_fmt_metadata(metadata),
    )
    return call_llm(prompt, ProductFacts, model_key)
