"""Per-agent scoring helpers.

- :func:`json_diff` powers extraction-style agents whose expected output is a
  pydantic-validated dict (today's ``_compare_recursive`` behavior).
- :func:`retrieval_metrics` powers retrieval-style agents whose expected
  output is a list of doc ids.
"""

from __future__ import annotations

from typing import Any

from agents.base import ScoreResult

SCALAR_TYPES = (str, int, float, bool, type(None))


def normalize_contract_shape(value: Any) -> dict[str, Any] | None:
    """Coerce legacy ``field_data`` shape (single contract) to ``{"data": [...]}``."""
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("data"), list):
        return value
    if isinstance(value.get("items"), list):
        return {"data": [value]}
    return None


def _is_scalar_list(values: list[Any]) -> bool:
    return all(isinstance(x, SCALAR_TYPES) for x in values)


def _compare_recursive(
    expected: Any,
    actual: Any,
    path: str,
    mismatches: list[dict[str, Any]],
) -> int:
    compared_fields = 0
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            mismatches.append({"path": path, "expected": expected, "actual": actual})
            return 1
        for key, expected_val in expected.items():
            compared_fields += _compare_recursive(
                expected_val,
                actual.get(key),
                f"{path}.{key}" if path else key,
                mismatches,
            )
        return compared_fields

    if isinstance(expected, list):
        if _is_scalar_list(expected):
            compared_fields += 1
            if actual not in expected:
                mismatches.append({"path": path, "expected": expected, "actual": actual})
            return compared_fields

        if not isinstance(actual, list):
            mismatches.append({"path": path, "expected": expected, "actual": actual})
            return compared_fields + 1

        compared_fields += 1
        if len(actual) != len(expected):
            mismatches.append(
                {"path": path, "expected_len": len(expected), "actual_len": len(actual)}
            )
        loop_count = min(len(expected), len(actual))
        for idx in range(loop_count):
            compared_fields += _compare_recursive(
                expected[idx],
                actual[idx],
                f"{path}[{idx}]",
                mismatches,
            )
        return compared_fields

    compared_fields += 1
    if expected != actual:
        mismatches.append({"path": path, "expected": expected, "actual": actual})
    return compared_fields


def json_diff(
    expected: dict[str, Any] | None,
    actual: dict[str, Any] | None,
) -> ScoreResult:
    """Recursive JSON diff used by SO-extraction-style agents.

    Returns a populated :class:`ScoreResult` whose ``expected_available`` flag
    reflects whether the expected payload was provided.
    """
    if expected is None:
        return ScoreResult(expected_available=False)
    normalized = normalize_contract_shape(actual) if actual else None
    mismatches: list[dict[str, Any]] = []
    compared = _compare_recursive(expected, normalized, "", mismatches)
    return ScoreResult(
        expected_available=True,
        compared_field_count=compared,
        mismatch_count=len(mismatches),
        mismatches=mismatches,
    )


def retrieval_metrics(
    expected_doc_ids: list[str] | None,
    actual_docs: list[dict[str, Any]] | None,
    k_values: tuple[int, ...] = (1, 3, 5, 10),
) -> ScoreResult:
    """Precision@K, recall@K and reciprocal rank for ranked-doc retrieval agents.

    ``actual_docs`` is expected to be a list of dicts each carrying a ``doc_id``
    key (additional fields like ``score`` and ``snippet`` are ignored for
    scoring).
    """
    if expected_doc_ids is None:
        return ScoreResult(expected_available=False)

    expected_set = {str(d) for d in expected_doc_ids}
    actual_ids = [str(d.get("doc_id", "")) for d in (actual_docs or [])]

    metrics: dict[str, float] = {}
    for k in k_values:
        topk = actual_ids[:k]
        relevant = sum(1 for d in topk if d in expected_set)
        metrics[f"precision@{k}"] = relevant / k if k else 0.0
        metrics[f"recall@{k}"] = relevant / max(len(expected_set), 1)

    rr = 0.0
    for rank, doc_id in enumerate(actual_ids, start=1):
        if doc_id in expected_set:
            rr = 1.0 / rank
            break
    metrics["mrr"] = rr

    mismatches: list[dict[str, Any]] = []
    missing = sorted(expected_set - set(actual_ids))
    extra = [d for d in actual_ids if d not in expected_set]
    if missing:
        mismatches.append({"missing_from_actual": missing})
    if extra:
        mismatches.append({"unexpected_in_actual": extra[:20]})

    return ScoreResult(
        expected_available=True,
        compared_field_count=len(expected_set),
        mismatch_count=len(missing),
        mismatches=mismatches,
        metrics=metrics,
    )
