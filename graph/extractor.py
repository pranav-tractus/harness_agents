from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field
from core.llm_client import call_llm

_EXTRACTION_PROMPT = """\
You are an expert at extracting structured facts from commodity trading chat messages.
{memory_section}
Extract the entities below from the chat. Return ONLY agreed/confirmed values.
Return empty strings or empty lists when a field is not confirmed in the chat.

Chat:
{chat_text}
"""


class ExtractedProduct(BaseModel):
    name: str = Field(description="Product name exactly as stated")
    quantity: Optional[float] = Field(default=None, description="Agreed quantity as a number")
    unit: Optional[str] = Field(default=None, description="Unit for quantity (MT, KG, bags, etc.)")
    price: Optional[float] = Field(default=None, description="Agreed unit price as a number")
    price_unit: Optional[str] = Field(default=None, description="Price unit (USD/MT, USD/KG, etc.)")
    incoterm: Optional[str] = Field(default=None, description="Incoterm (FOB, CIF, EXW, DDP)")
    port: Optional[str] = Field(default=None, description="Port or destination city")


class ExtractedFacts(BaseModel):
    products: list[ExtractedProduct] = Field(
        default_factory=list,
        description="All products agreed in the chat"
    )
    ports: list[str] = Field(
        default_factory=list,
        description="Ports or destinations mentioned and agreed"
    )
    payment_terms: str = Field(
        default="",
        description="Payment terms (e.g. Net 30, 100% Advance, 50% CAD)"
    )
    packing: str = Field(
        default="",
        description="Agreed packing description (e.g. 25kg PP bags)"
    )
    loading: str = Field(
        default="",
        description="Agreed loading description (e.g. 1x20 FCL)"
    )


def extract_entities(
    chat_text: str,
    model_key: str = "openai:5.5",
    memory_block: str | None = None,
) -> ExtractedFacts:
    memory_section = f"\n{memory_block}\n" if memory_block else ""
    prompt = _EXTRACTION_PROMPT.format(
        memory_section=memory_section,
        chat_text=chat_text,
    )
    return call_llm(prompt, ExtractedFacts, model_key)
