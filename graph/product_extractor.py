from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from core.llm_client import call_llm

_PROMPT = """\
You normalize a product catalog entry for a commodity trading system.
Given the product description and spec, extract:
- aliases: common alternate names / how a customer might refer to it in chat
- grade, packing_size, unit: normalized spec attributes when present
- attributes: any other normalized spec key/value pairs

Return empty lists, empty objects, or null when a field is not determinable.

Product description: {description}
Product spec: {spec}
"""


class ProductFacts(BaseModel):
    aliases: list[str] = Field(default_factory=list, description="Alternate names / common references")
    grade: Optional[str] = Field(default=None, description="Product grade if stated")
    packing_size: Optional[str] = Field(default=None, description="Packing size, e.g. 25kg")
    unit: Optional[str] = Field(default=None, description="Trading unit, e.g. MT, KG")
    attributes: dict[str, str] = Field(default_factory=dict, description="Other normalized spec key/values")


def extract_product_facts(description: str, spec: str | None, model_key: str = "openai:5.5") -> ProductFacts:
    prompt = _PROMPT.format(description=description, spec=spec or "")
    return call_llm(prompt, ProductFacts, model_key)
