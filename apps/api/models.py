from __future__ import annotations

from pydantic import BaseModel, Field

# The sales-order summary reuses the same pydantic schema the `core` extraction
# pipeline produces: initial extraction -> SOExtractContractList, edits ->
# SOUpdateContractList. Both share an identical field layout, so one renderer
# handles either.
from core.models import SOExtractContractList, SOUpdateContractList

SalesOrderSummary = SOExtractContractList | SOUpdateContractList


class CustomerProfile(BaseModel):
    email: str | None = None
    phone: str | None = None
    business_address: str | None = None
    delivery_address: str | None = None
    contact_point: str | None = None
    approved_credit_term: str | None = None
    approved_white_label: str | None = None
    latest_packing_and_loading: str | None = None


class CustomerOut(BaseModel):
    id: str
    name: str
    profile: CustomerProfile
    last_contract_seq: int
    org_id: str | None = None


class ProfileUpdate(BaseModel):
    profile: CustomerProfile
    org_id: str | None = None


class CustomerCreate(BaseModel):
    name: str
    org_id: str


class ProductOut(BaseModel):
    id: str
    code: str
    name: str | None = None
    short_description: str
    long_description: str | None = None
    spec: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    build_status: str = "not built"
    source_label: str | None = None
    org_id: str | None = None


class ProductCreate(BaseModel):
    code: str
    name: str | None = None
    short_description: str
    long_description: str | None = None
    spec: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    org_id: str


class ProductUpdate(BaseModel):
    name: str | None = None
    short_description: str | None = None
    long_description: str | None = None
    spec: str | None = None
    metadata: dict[str, str] | None = None
    org_id: str | None = None


class OrgOut(BaseModel):
    id: str
    name: str
    tagline: str | None = None
    is_catchall: bool = False
    product_count: int = 0
    customer_count: int = 0
    unbuilt_count: int = 0


class OrgCreate(BaseModel):
    name: str
    tagline: str | None = None


class OrgUpdate(BaseModel):
    name: str | None = None
    tagline: str | None = None


class MessageIn(BaseModel):
    role: str  # "me" | "customer"
    body: str
    model_key: str | None = None  # only read when the body tags @agent


class MessageOut(BaseModel):
    id: str
    customer_id: str
    seq: int
    role: str
    kind: str
    body: str
    summary_id: str | None = None
    summary_json: str | None = None  # raw model response (pretty JSON) for summary cards
    created_at: str


class ModelOption(BaseModel):
    key: str
    display_name: str
    provider: str


def render_summary_markdown(summary: SalesOrderSummary, customer_name: str | None = None) -> str:
    """Render a core contract-list response (extract or update) as a chat card.

    Both ``SOExtractContractList`` and ``SOUpdateContractList`` expose ``.data``
    (a list of contracts) with the same field layout, so this handles either.
    """
    heading = "**Sales Order Summary**"
    if customer_name:
        heading += f" — {customer_name}"
    lines: list[str] = []
    contracts = summary.data
    for idx, c in enumerate(contracts):
        lines.append(f"{heading} · Contract {idx + 1}" if len(contracts) > 1 else heading)
        if c.vendor_name:
            lines.append(f"Vendor: {c.vendor_name}")
        lines.append("")
        for it in c.items:
            qty = f"{it.quantity:g} {it.quantity_unit}".strip() if it.quantity is not None else "-"
            price = f"{it.unit_price:g} {it.pricing_unit}".strip() if it.unit_price is not None else "-"
            detail = it.delivery_terms or it.ship_term or "-"
            ship_to = it.shipping_address or "-"
            line = f"- **{it.description or '(unnamed)'}** — qty {qty}, price {price}, terms {detail}, ship-to {ship_to}"
            if it.total is not None:
                line += f", total {it.total:g}"
            lines.append(line)
        lines += [
            "",
            f"Payment: {c.payment_date or '-'}",
            f"Delivery terms: {c.delivery_terms or '-'}",
            f"Shipping: {c.shipping_method or '-'} → {c.shipping_address or '-'}",
            f"Billing: {c.billing_address or '-'}",
            f"PO ref: {c.po_ref_no or '-'}",
        ]
        lines.append("")
    return "\n".join(lines).rstrip()


CRITICAL_SLOTS_ORDER = ["description", "quantity", "unit_price", "ship_term"]
CRITICAL_SLOTS = set(CRITICAL_SLOTS_ORDER)

# Slots worth remembering as a customer default (recurring "typical terms").
# Deliberately excludes quantity / description / unit_price, which vary per order.
PREFERABLE_SLOTS = {"ship_term", "packing", "loading", "payment_date"}


def is_preferable_slot(slot: str) -> bool:
    return slot in PREFERABLE_SLOTS


def missing_agreement(slots: list[dict]) -> list[str]:
    out: list[str] = []
    for slot in CRITICAL_SLOTS_ORDER:
        entries = [entry for entry in slots if entry.get("slot") == slot]
        if not entries or any(
            not {"seller", "customer"} <= set(entry.get("agreed_by", []))
            for entry in entries
        ):
            out.append(slot)
    return out


def is_ready(slots: list[dict]) -> bool:
    return bool(slots) and missing_agreement(slots) == []


class SlotBelief(BaseModel):
    slot: str
    value: str | None = None
    source: str = "unknown"        # chat | last_order | profile | inferred | unknown
    confidence: str = "low"        # high | med | low
    agreed_by: list[str] = Field(default_factory=list)   # subset of {seller, customer}
    source_seqs: list[int] = Field(default_factory=list)  # message seqs that justify `value`
    evidence: str | None = None                            # verbatim snippet backing `value`
    line: int | None = None        # contract item sr_no for line-scoped slots; None = order-level


class AgentQuestion(BaseModel):
    slot: str
    directed_to: str = "both"      # seller | customer | both
    text: str


class AgentDecision(BaseModel):
    mode: str                       # clarify | draft | finalize
    message: str
    questions: list[AgentQuestion] = Field(default_factory=list)
    contract: SOExtractContractList | None = None
    ledger: list[SlotBelief] = Field(default_factory=list)
    ready_to_finalize: bool = False


def cap_questions(decision: AgentDecision, limit: int = 3) -> AgentDecision:
    ordered = sorted(decision.questions, key=lambda q: q.slot not in CRITICAL_SLOTS)
    decision.questions = ordered[:limit]
    return decision


class ChatOut(BaseModel):
    id: str
    customer_id: str
    title: str
    status: str
    channel: str
    created_at: str
    last_contract_seq: int


class ChatCreate(BaseModel):
    title: str
