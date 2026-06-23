"""Memory-assisted extraction evaluation.

Two passes per synthetic chat:
  baseline  — extract_entities(chat_text)               (no memory block)
  with_mem  — extract_entities(chat_text, memory_block)

Both passes are scored against expected_facts using field-by-field comparison.
Results are printed as a delta table after all tests run.

Run: pytest tests/test_memory_extraction.py -v -s
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from graph.extractor import ExtractedFacts, ExtractedProduct, extract_entities

CHATS_DIR = Path(__file__).resolve().parent / "synthetic_chats"

# Collect all 60 chat files at module load time so parametrize picks them up.
_ALL_CHAT_FILES: list[Path] = sorted(CHATS_DIR.glob("*.json"))


# ── Scoring ──────────────────────────────────────────────────────────────────

def _score_product(expected: dict, actual: ExtractedProduct | None) -> tuple[int, int]:
    """Returns (matched_fields, total_fields) for one product."""
    if actual is None:
        total = sum(1 for v in expected.values() if v is not None and v != "" and v != [])
        return 0, total
    fields = ["name", "quantity", "unit", "price", "price_unit", "incoterm", "port"]
    matched = 0
    total = 0
    for f in fields:
        ev = expected.get(f)
        av = getattr(actual, f, None)
        if ev is None or ev == "":
            continue
        total += 1
        if isinstance(ev, str) and isinstance(av, str):
            if ev.strip().lower() == av.strip().lower():
                matched += 1
        elif ev == av:
            matched += 1
    return matched, total


def _find_best_product_match(expected: dict, actuals: list[ExtractedProduct]) -> ExtractedProduct | None:
    """Return the actual product whose name best matches expected."""
    if not actuals:
        return None
    name = (expected.get("name") or "").strip().lower()
    for a in actuals:
        if a.name.strip().lower() == name:
            return a
    return None


def _score_facts(expected: dict, actual: ExtractedFacts) -> float:
    """Return accuracy in [0.0, 1.0]: matched_fields / total_fields."""
    total = 0
    matched = 0

    # Products
    for ep in expected.get("products", []):
        ap = _find_best_product_match(ep, actual.products)
        m, t = _score_product(ep, ap)
        matched += m
        total += t

    # Scalar fields
    scalar_fields = [
        ("payment_terms", actual.payment_terms),
        ("packing", actual.packing),
        ("loading", actual.loading),
    ]
    for key, av in scalar_fields:
        ev = expected.get(key, "")
        if not ev:
            continue
        total += 1
        if isinstance(ev, str) and isinstance(av, str):
            if ev.strip().lower() == av.strip().lower():
                matched += 1
        elif ev == av:
            matched += 1

    # Ports
    exp_ports = [p.strip().lower() for p in expected.get("ports", []) if p]
    act_ports = [p.strip().lower() for p in actual.ports]
    for ep in exp_ports:
        total += 1
        if ep in act_ports:
            matched += 1

    if total == 0:
        return 1.0
    return matched / total


# ── Per-run result accumulator (module-level, populated by each test) ─────────

@dataclass
class _RunResult:
    chat_id: str
    category: str
    chat_type: str
    customer_id: str
    baseline_score: float
    memory_score: float
    delta: float = field(init=False)

    def __post_init__(self) -> None:
        self.delta = self.memory_score - self.baseline_score


_RESULTS: list[_RunResult] = []


# ── pytest fixtures & tests ───────────────────────────────────────────────────

def pytest_configure(config: Any) -> None:
    config.addinivalue_line(
        "markers", "memory_eval: marks memory extraction evaluation tests"
    )


@pytest.fixture(scope="session", autouse=True)
def _print_delta_report() -> Any:
    """Print summary table after all tests complete."""
    yield
    if not _RESULTS:
        return
    print("\n\n" + "=" * 80)
    print(f"{'MEMORY EXTRACTION DELTA REPORT':^80}")
    print("=" * 80)
    header = f"{'chat_id':<18} {'category':<18} {'type':<20} {'baseline':>8} {'memory':>8} {'delta':>8}"
    print(header)
    print("-" * 80)
    for r in sorted(_RESULTS, key=lambda x: (x.category, x.chat_type, x.chat_id)):
        delta_str = f"+{r.delta:.2f}" if r.delta >= 0 else f"{r.delta:.2f}"
        print(
            f"{r.chat_id:<18} {r.category:<18} {r.chat_type:<20} "
            f"{r.baseline_score:>8.2f} {r.memory_score:>8.2f} {delta_str:>8}"
        )
    print("-" * 80)
    # Aggregates by category
    for cat in ("memory_required", "memory_boost"):
        subset = [r for r in _RESULTS if r.category == cat]
        if not subset:
            continue
        avg_b = sum(r.baseline_score for r in subset) / len(subset)
        avg_m = sum(r.memory_score for r in subset) / len(subset)
        avg_d = avg_m - avg_b
        d_str = f"+{avg_d:.2f}" if avg_d >= 0 else f"{avg_d:.2f}"
        print(f"{'AVG ' + cat:<56} {avg_b:>8.2f} {avg_m:>8.2f} {d_str:>8}")
    print("=" * 80 + "\n")


@pytest.mark.memory_eval
@pytest.mark.parametrize("chat_file", _ALL_CHAT_FILES, ids=lambda p: p.stem)
def test_memory_extraction_delta(chat_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """For each synthetic chat, run extraction twice and record accuracy delta."""
    data = json.loads(chat_file.read_text())
    chat_text: str = data["chat_text"]
    memory_block: str | None = data.get("mock_memory_block")
    expected: dict = data["expected_facts"]
    model_key = "sonnet-4-6"

    # Baseline: no memory block
    baseline_facts = extract_entities(chat_text, model_key=model_key)
    baseline_score = _score_facts(expected, baseline_facts)

    # Memory-assisted
    memory_facts = extract_entities(chat_text, model_key=model_key, memory_block=memory_block)
    memory_score = _score_facts(expected, memory_facts)

    result = _RunResult(
        chat_id=data["chat_id"],
        category=data["category"],
        chat_type=data["chat_type"],
        customer_id=data["customer_id"],
        baseline_score=baseline_score,
        memory_score=memory_score,
    )
    _RESULTS.append(result)

    # Memory-required: memory_score must be >= baseline (memory should never hurt)
    if data["category"] == "memory_required":
        assert memory_score >= baseline_score, (
            f"{data['chat_id']}: memory score {memory_score:.2f} < baseline {baseline_score:.2f} "
            f"— memory block degraded extraction on a memory-required chat"
        )

    # Memory-boost: no strict assertion — we just measure delta
    # (memory may or may not improve; the report captures this)
