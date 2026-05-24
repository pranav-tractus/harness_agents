"""Deterministic extraction post-processing (stdlib only).

The two main concerns — string-level unit normalization and unit-aware total
recomputation — are split into separate functions so they can be wired as
distinct pipeline stages. ``apply_deterministic_postprocess`` is preserved as
a thin caller of both for back-compat with existing tests / call sites.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

_TOTAL_TOLERANCE = 0.02
_DATE_FIELDS_CONTRACT = ("po_date", "do_date")
_DATE_FIELDS_ITEM = ("shipment_date",)


def _deep_copy_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(contract)


def _parse_iso_date(value: str) -> date | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def collect_date_warnings(
    contract: dict[str, Any],
    *,
    reference_iso_date: str,
) -> list[dict[str, Any]]:
    """Emit warnings only; never mutate date fields."""
    warnings: list[dict[str, Any]] = []
    ref = _parse_iso_date(reference_iso_date)
    data = contract.get("data")
    if not isinstance(data, list):
        return warnings

    for ci, block in enumerate(data):
        if not isinstance(block, dict):
            continue
        prefix = f"data[{ci}]"
        for field in _DATE_FIELDS_CONTRACT:
            val = block.get(field, "")
            if not val:
                continue
            parsed = _parse_iso_date(str(val))
            if parsed is None:
                warnings.append(
                    {
                        "code": "date_unparseable",
                        "path": f"{prefix}.{field}",
                        "message": f"Could not parse date '{val}'",
                    }
                )
            elif ref and parsed < ref:
                warnings.append(
                    {
                        "code": "date_in_past",
                        "path": f"{prefix}.{field}",
                        "message": f"Date {val} is before reference {reference_iso_date}",
                    }
                )
        items = block.get("items")
        if not isinstance(items, list):
            continue
        line_dates: list[date] = []
        for ii, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            ip = f"{prefix}.items[{ii}]"
            for field in _DATE_FIELDS_ITEM:
                val = item.get(field, "")
                if not val:
                    continue
                parsed = _parse_iso_date(str(val))
                if parsed is None:
                    warnings.append(
                        {
                            "code": "date_unparseable",
                            "path": f"{ip}.{field}",
                            "message": f"Could not parse date '{val}'",
                        }
                    )
                else:
                    line_dates.append(parsed)
                    if ref and parsed < ref:
                        warnings.append(
                            {
                                "code": "date_in_past",
                                "path": f"{ip}.{field}",
                                "message": f"Date {val} is before reference {reference_iso_date}",
                            }
                        )
        do_val = block.get("do_date", "")
        do_parsed = _parse_iso_date(str(do_val)) if do_val else None
        if do_parsed and line_dates:
            max_line = max(line_dates)
            if do_parsed != max_line:
                warnings.append(
                    {
                        "code": "do_date_mismatch_lines",
                        "path": f"{prefix}.do_date",
                        "message": f"do_date {do_val} differs from latest line shipment {max_line.isoformat()}",
                    }
                )

    return warnings


def _normalize_unit_token(unit: str) -> str:
    if not unit:
        return ""
    u = unit.strip().upper()
    aliases = {
        "BAG": "BAGS",
        "BAGS": "BAGS",
        "MT": "MT",
        "KG": "KG",
        "KGS": "KG",
    }
    return aliases.get(u, u)


# Conversion factors to a canonical base unit per family.
_WEIGHT_TO_KG = {
    "KG": 1.0, "KGS": 1.0, "KILOGRAM": 1.0, "KILOGRAMS": 1.0,
    "MT": 1000.0, "TON": 1000.0, "TONS": 1000.0, "TONNE": 1000.0, "TONNES": 1000.0,
    "G": 0.001, "GRAM": 0.001, "GRAMS": 0.001,
    "LB": 0.45359237, "LBS": 0.45359237, "POUND": 0.45359237, "POUNDS": 0.45359237,
    "OZ": 0.0283495, "OUNCE": 0.0283495, "OUNCES": 0.0283495,
}
_VOLUME_TO_L = {
    "L": 1.0, "LITRE": 1.0, "LITRES": 1.0, "LITER": 1.0, "LITERS": 1.0,
    "ML": 0.001,
    "GAL": 3.78541, "GALLON": 3.78541, "GALLONS": 3.78541,
}


def _extract_qty_basis(unit: str) -> str | None:
    if not isinstance(unit, str):
        return None
    return unit.strip().upper() or None


def _extract_price_basis(pricing_unit: str) -> str | None:
    """E.g. 'USD/KG' -> 'KG'. Returns None if no '/'."""
    if not isinstance(pricing_unit, str) or "/" not in pricing_unit:
        return None
    return pricing_unit.split("/", 1)[1].strip().upper() or None


def _strip_plural(token: str) -> str:
    if not token or token in _WEIGHT_TO_KG or token in _VOLUME_TO_L:
        return token
    if token.endswith("ES") and len(token) > 3:
        return token[:-2]
    if token.endswith("S") and len(token) > 2:
        return token[:-1]
    return token


def _scale_factor(qty_basis: str | None, price_basis: str | None) -> float | None:
    """Return multiplier so that total = qty * price * factor."""
    if not qty_basis or not price_basis:
        return 1.0
    if qty_basis == price_basis:
        return 1.0
    if qty_basis in _WEIGHT_TO_KG and price_basis in _WEIGHT_TO_KG:
        return _WEIGHT_TO_KG[qty_basis] / _WEIGHT_TO_KG[price_basis]
    if qty_basis in _VOLUME_TO_L and price_basis in _VOLUME_TO_L:
        return _VOLUME_TO_L[qty_basis] / _VOLUME_TO_L[price_basis]
    if _strip_plural(qty_basis) == _strip_plural(price_basis):
        return 1.0
    return None


def normalize_units(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize ``quantity_unit`` / ``pricing_unit`` casing and aliases.

    Returns ``(new_contract, changes)`` where ``changes`` is a list of
    deterministic-change records (code='deterministic_change', path, action, value).
    """
    out = _deep_copy_contract(contract)
    changes: list[dict[str, Any]] = []
    data = out.get("data")
    if not isinstance(data, list):
        return out, changes
    for ci, block in enumerate(data):
        if not isinstance(block, dict):
            continue
        items = block.get("items")
        if not isinstance(items, list):
            continue
        for ii, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            path = f"data[{ci}].items[{ii}]"
            qu = item.get("quantity_unit")
            if isinstance(qu, str) and qu.strip():
                nu = _normalize_unit_token(qu)
                if nu != qu:
                    item["quantity_unit"] = nu
                    changes.append({"code": "deterministic_change", "path": f"{path}.quantity_unit", "action": "normalized", "value": nu})
            pu = item.get("pricing_unit")
            if isinstance(pu, str) and pu.strip():
                nu = pu.strip().upper()
                if nu != pu:
                    item["pricing_unit"] = nu
                    changes.append({"code": "deterministic_change", "path": f"{path}.pricing_unit", "action": "normalized", "value": nu})
    return out, changes


def recompute_totals(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Recompute line ``total`` from ``quantity * unit_price`` with unit scaling.

    Returns ``(new_contract, messages)``. Messages include both
    ``deterministic_change`` records (when a total is rewritten) and
    ``total_unit_mismatch`` warnings (when the unit family is unknown).
    """
    out = _deep_copy_contract(contract)
    messages: list[dict[str, Any]] = []
    data = out.get("data")
    if not isinstance(data, list):
        return out, messages
    for ci, block in enumerate(data):
        if not isinstance(block, dict):
            continue
        items = block.get("items")
        if not isinstance(items, list):
            continue
        for ii, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            path = f"data[{ci}].items[{ii}]"
            qty = item.get("quantity")
            price = item.get("unit_price")
            if not (isinstance(qty, (int, float)) and isinstance(price, (int, float))):
                continue
            qty_basis = _extract_qty_basis(item.get("quantity_unit") or "")
            price_basis = _extract_price_basis(item.get("pricing_unit") or "")
            factor = _scale_factor(qty_basis, price_basis)
            if factor is None:
                messages.append(
                    {
                        "code": "total_unit_mismatch",
                        "path": f"{path}.total",
                        "message": (
                            f"Cannot recompute total: quantity_unit={qty_basis} "
                            f"vs pricing_unit basis={price_basis}"
                        ),
                    }
                )
                continue
            expected = round(float(qty) * float(price) * factor, 4)
            total = item.get("total")
            needs_fix = (
                total is None
                or (isinstance(total, (int, float)) and float(total) == 0.0)
                or (
                    isinstance(total, (int, float))
                    and abs(float(total) - expected)
                    > _TOTAL_TOLERANCE * max(abs(expected), 1.0)
                )
            )
            if needs_fix:
                old = total
                item["total"] = expected
                messages.append(
                    {
                        "code": "deterministic_change",
                        "path": f"{path}.total",
                        "action": "recalculated",
                        "from": old,
                        "to": expected,
                    }
                )
    return out, messages


def apply_deterministic_postprocess(
    contract: dict[str, Any],
    *,
    reference_iso_date: str,
    normalize_units: bool = True,  # noqa: ARG001 - kept for arg compatibility
    fix_totals: bool = True,       # noqa: ARG001 - kept for arg compatibility
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Back-compat shim: normalize_units + recompute_totals + date warnings.

    Returns ``(contract, messages)`` where messages mix date warnings and
    ``deterministic_change`` records, matching the original API.
    """
    out, change_msgs = _normalize_and_recompute(contract)
    warnings = collect_date_warnings(out, reference_iso_date=reference_iso_date)
    return out, warnings + change_msgs


def _normalize_and_recompute(
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out, unit_changes = normalize_units(contract)
    out, total_msgs = recompute_totals(out)
    return out, unit_changes + total_msgs


def freeze_date_fields_from_raw(raw: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Copy all date fields from raw into candidate; structure must align."""
    out = _deep_copy_contract(candidate)
    raw_data = raw.get("data") if isinstance(raw.get("data"), list) else []
    out_data = out.get("data") if isinstance(out.get("data"), list) else []

    for ci in range(min(len(raw_data), len(out_data))):
        rb, ob = raw_data[ci], out_data[ci]
        if not isinstance(rb, dict) or not isinstance(ob, dict):
            continue
        for field in _DATE_FIELDS_CONTRACT:
            if field in rb:
                ob[field] = rb[field]
        raw_items = rb.get("items") if isinstance(rb.get("items"), list) else []
        out_items = ob.get("items") if isinstance(ob.get("items"), list) else []
        for ii in range(min(len(raw_items), len(out_items))):
            ri, oi = raw_items[ii], out_items[ii]
            if not isinstance(ri, dict) or not isinstance(oi, dict):
                continue
            for field in _DATE_FIELDS_ITEM:
                if field in ri:
                    oi[field] = ri[field]
    return out


def diff_date_fields(raw: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Return per-field records where candidate's date differs from raw's date.

    Used by the FreezeDates stage to surface what the validator tried to change
    before the freeze masks it.
    """
    diffs: list[dict[str, Any]] = []
    raw_data = raw.get("data") if isinstance(raw.get("data"), list) else []
    cand_data = candidate.get("data") if isinstance(candidate.get("data"), list) else []
    for ci in range(min(len(raw_data), len(cand_data))):
        rb, cb = raw_data[ci], cand_data[ci]
        if not isinstance(rb, dict) or not isinstance(cb, dict):
            continue
        for field in _DATE_FIELDS_CONTRACT:
            rv, cv = rb.get(field), cb.get(field)
            if rv != cv:
                diffs.append({"path": f"data[{ci}].{field}", "raw": rv, "candidate": cv})
        raw_items = rb.get("items") if isinstance(rb.get("items"), list) else []
        cand_items = cb.get("items") if isinstance(cb.get("items"), list) else []
        for ii in range(min(len(raw_items), len(cand_items))):
            ri, ci_item = raw_items[ii], cand_items[ii]
            if not isinstance(ri, dict) or not isinstance(ci_item, dict):
                continue
            for field in _DATE_FIELDS_ITEM:
                rv, cv = ri.get(field), ci_item.get(field)
                if rv != cv:
                    diffs.append({"path": f"data[{ci}].items[{ii}].{field}", "raw": rv, "candidate": cv})
    return diffs
