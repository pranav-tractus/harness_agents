from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic.type_adapter import TypeAdapter


class LLMExtractContractProductItem(BaseModel):
    sr_no: int = Field(
        description="Serial number for this line item (1, 2, 3, ...)."
    )
    description: str = Field(
        description=(
            "Product name exactly as agreed in the chat. Copy verbatim — "
            "exact casing, spacing, and punctuation. Empty string if not stated."
        )
    )
    quantity: Optional[float] = Field(
        description=(
            "Agreed numeric quantity as a float. null if not stated or not "
            "yet mutually agreed by both parties."
        )
    )
    quantity_unit: str = Field(
        description=(
            "Unit for quantity exactly as written in the chat (e.g. MT, KG, lb, "
            "bags, cartons, reams). Preserve capitalisation. Empty string if not stated."
        )
    )
    unit_price: Optional[float] = Field(
        description=(
            "Final agreed unit price as a float. Use only the mutually accepted "
            "price — not initial quotes or unaccepted counter-offers. null if not stated."
        )
    )
    pricing_unit: str = Field(
        description=(
            "Pricing basis exactly as written in the chat (e.g. USD/MT, SGD/MT, "
            "USD/KG, INR/MT). Preserve capitalisation. Empty string if not stated."
        )
    )
    ship_term: str = Field(
        description=(
            "Incoterm only: one of EXW, FOB, CIF, DDP. Copy the exact term from "
            "the chat. Empty string if not stated."
        )
    )
    delivery_terms: str = Field(
        description=(
            "Full per-product delivery terms including incoterm and location, verbatim "
            "from chat (e.g. 'CIF Busan', 'FOB Shanghai'). Empty string if not stated."
        )
    )
    shipment_date: str = Field(
        description=(
            "Per-product shipment date in ISO 8601 format (YYYY-MM-DD). For partial "
            "months use last day (e.g. 'November 2026' -> '2026-11-30'). "
            "Empty string if not stated."
        )
    )
    shipping_address: str = Field(
        description=(
            "Per-product ship-to destination or address, verbatim from the chat. "
            "Empty string if not stated."
        )
    )
    packing: str = Field(
        description=(
            "Physical packaging description verbatim from the chat (e.g. '25kg bags', "
            "'50lb sacks'). This is NOT a logistics phrase. Empty string if not stated."
        )
    )
    loading: str = Field(
        description=(
            "Loading specification verbatim from the chat (e.g. '23MT/40FCL', "
            "'12MT/20FCL'). Empty string if not stated."
        )
    )
    total: Optional[float] = Field(
        description=(
            "quantity x unit_price. Only set when both values are present and share "
            "the same unit basis. null if either is missing or units differ."
        )
    )


class SalesOrderExtractContractKeyDetails(BaseModel):
    items: List[LLMExtractContractProductItem] = Field(
        description="Ordered list of agreed line items."
    )
    do_date: str = Field(
        description=(
            "Delivery or shipment date in ISO 8601 (YYYY-MM-DD). Empty string if not stated."
        ),
        default="",
    )
    po_date: str = Field(
        description=(
            "Sales order date in ISO 8601 (YYYY-MM-DD). Empty string if not stated."
        ),
        default="",
    )
    po_ref_no: str = Field(
        description=(
            "Purchase order reference number from the chat. Empty string if not stated."
        ),
        default="",
    )
    vendor_name: str = Field(
        description=(
            "Seller/vendor name. Use the vendor reference block if provided; "
            "chat wording wins if it names a different party. Empty string if not available."
        )
    )
    payment_date: str = Field(
        description=(
            "Payment terms: either a calendar date (YYYY-MM-DD) or an explicit "
            "phrase from the chat such as 'Net 30 from delivery', '100% Advance', "
            "'70% CAD'. Do NOT copy shipping instructions or document-handling notes "
            "(e.g. 'Against scan copies of documents') into this field. Empty string if unclear."
        )
    )
    delivery_terms: str = Field(
        description=(
            "Block-level delivery terms from the chat, verbatim. Empty string if not stated."
        )
    )
    billing_address: str = Field(
        description=(
            "Buyer billing address. May be filled from the counterparty reference block "
            "when not contradicted by the chat. Empty string if not available."
        )
    )
    shipping_method: str = Field(
        description=(
            "Shipping method exactly as stated in the chat (e.g. 'by sea', 'by air'). "
            "Empty string if not stated."
        )
    )
    shipping_address: str = Field(
        description=(
            "Block-level ship-to address. May be filled from the counterparty reference block "
            "when no item-level shipping_address is set and the chat does not contradict. "
            "Empty string if not available."
        )
    )


class SalesOrderUpdateContractKeyDetails(BaseModel):
    items: List[LLMExtractContractProductItem] = Field(
        description="Ordered list of agreed line items."
    )
    do_date: str = Field(
        description="Delivery or shipment date in ISO 8601 (YYYY-MM-DD). Empty string if not stated.",
        default="",
    )
    po_date: str = Field(
        description="Sales order date in ISO 8601 (YYYY-MM-DD). Empty string if not stated.",
        default="",
    )
    po_ref_no: str = Field(
        description="Purchase order reference number. Empty string if not stated.",
        default="",
    )
    vendor_name: str = Field(
        description=(
            "Seller/vendor name from the chat or prior summary. Empty string if not stated."
        )
    )
    payment_date: str = Field(
        description=(
            "Payment terms: calendar date or explicit phrase (e.g. 'Net 30 from delivery'). "
            "Never copy shipping/document notes. Empty string if unclear."
        )
    )
    delivery_terms: str = Field(
        description="Block-level delivery terms verbatim from chat. Empty string if not stated."
    )
    billing_address: str = Field(
        description="Buyer billing address from chat or counterparty reference. Empty string if not available."
    )
    shipping_method: str = Field(
        description="Shipping method from chat (e.g. 'by sea'). Empty string if not stated."
    )
    shipping_address: str = Field(
        description="Ship-to address from chat or counterparty reference. Empty string if not available."
    )


class SOExtractContractList(BaseModel):
    data: List[SalesOrderExtractContractKeyDetails] = Field(
        description="List of contracts, one entry per distinct purchase order."
    )


class SOUpdateContractList(BaseModel):
    data: List[SalesOrderUpdateContractKeyDetails] = Field(
        description="List of contracts, one entry per distinct purchase order."
    )


def dict_to_items_type(items: List[dict]):
    ExtractedListAdapter = TypeAdapter(List[LLMExtractContractProductItem])
    return ExtractedListAdapter.validate_python(items)


def dict_to_llm_details(details: dict):
    ExtractedListAdapter = TypeAdapter(SalesOrderExtractContractKeyDetails)
    return ExtractedListAdapter.validate_python(details)
