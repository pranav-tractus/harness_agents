from __future__ import annotations

import re

from pydantic import BaseModel

from apps.api.models import CRITICAL_SLOTS
from core.models import SOExtractContractList

SHIP_TERMS = {"", "EXW", "FOB", "CIF", "DDP"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Violation(BaseModel):
    code: str
    slot: str | None = None
    message: str
    severity: str = "warn"  # "block" | "warn"


def has_blocking(violations: list[Violation]) -> bool:
    return any(v.severity == "block" for v in violations)


def verify(
    contract: SOExtractContractList,
    slots: list[dict],
    *,
    resolved_codes: set[str] | None,
    window_seqs: set[int],
) -> list[Violation]:
    """Deterministic checks over a drafted/pending contract.

    ``resolved_codes`` is the set of catalog SKUs the matcher pinned for this
    turn; pass ``None`` to skip product-grounding (e.g. at approve time, where
    the matcher is not re-run and grounding was already enforced at draft).
    ``window_seqs`` is the set of message seqs the agent reasoned over.
    """
    out: list[Violation] = []
    items = contract.data[0].items if contract.data else []

    for it in items:
        code = (it.description or "").strip()
        if resolved_codes is not None and code and code not in resolved_codes:
            out.append(Violation(
                code="unknown_product_code", slot="description", severity="block",
                message=f"Line item '{code}' is not a resolved catalog product.",
            ))
        if it.ship_term not in SHIP_TERMS:
            out.append(Violation(
                code="bad_ship_term", slot="ship_term", severity="block",
                message=f"ship_term '{it.ship_term}' is not one of EXW/FOB/CIF/DDP.",
            ))
        if (it.quantity is not None and it.unit_price is not None
                and it.total is not None
                and abs(it.total - it.quantity * it.unit_price) > 0.01):
            out.append(Violation(
                code="total_mismatch", slot="total", severity="warn",
                message=(f"total {it.total} != quantity {it.quantity} "
                         f"x unit_price {it.unit_price}."),
            ))
        if it.shipment_date and not _ISO_DATE.match(it.shipment_date):
            out.append(Violation(
                code="bad_date_format", slot="shipment_date", severity="warn",
                message=f"shipment_date '{it.shipment_date}' is not ISO YYYY-MM-DD.",
            ))

    for s in slots:
        slot = s.get("slot")
        if slot not in CRITICAL_SLOTS:
            continue
        if s.get("value") is None:
            continue
        source = s.get("source", "unknown")
        seqs = s.get("source_seqs") or []
        if source == "unknown":
            out.append(Violation(
                code="critical_unknown_source", slot=slot, severity="block",
                message=f"Critical slot '{slot}' has a value but source='unknown'.",
            ))
        if source == "chat" and not seqs:
            out.append(Violation(
                code="missing_provenance", slot=slot, severity="warn",
                message=f"Critical slot '{slot}' is chat-sourced but cites no message.",
            ))
        stale = [q for q in seqs if q not in window_seqs]
        if stale:
            out.append(Violation(
                code="stale_citation", slot=slot, severity="warn",
                message=f"Slot '{slot}' cites messages not in the window: {stale}.",
            ))
    return out
