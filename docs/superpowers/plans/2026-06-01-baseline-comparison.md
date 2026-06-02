# Baseline Comparison Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--with-baseline` mode that sends each chat to Claude with a single-line prompt and no system prompt, scores it field-by-field against expected, and surfaces a three-tier accuracy comparison (Baseline → Agent Extraction → Validation Layer) in the run report and dashboard.

**Architecture:** A thin `run_baseline()` function calls the existing `call_llm` with the locked `SOExtractContractList` schema. `SOExtractionAgent.run_one` invokes it when `options.extra["run_baseline"]` is set and stamps `score_baseline` / `baseline_output_json` onto the result record. The artifact layer emits a `field_match_rate_baseline` metric; the report adds a third chart bar and a comparison table only when baseline metrics are present. The `--with-baseline` CLI flag (and a dashboard checkbox) toggle the whole thing.

**Tech Stack:** Python 3, instructor + Pydantic (LLM structured output), `unittest`, Chart.js (report), Streamlit (dashboard).

---

## File Structure

- **Create:** `core/baseline_extractor.py` — the minimal baseline LLM call (one responsibility: bare prompt → dict).
- **Create:** `tests/test_baseline_extractor.py` — unit tests for the baseline module.
- **Create:** `tests/test_baseline_aggregate.py` — unit tests for the new baseline metric in `record_to_row` / `aggregate`.
- **Modify:** `agents/base.py` — add `score_baseline` and `baseline_output_json` fields to `AgentRunResult`.
- **Modify:** `agents/so_extraction/agent.py` — call the baseline when requested; populate the new fields.
- **Modify:** `harness/artifacts.py` — emit `field_match_rate_baseline` / `mismatch_count_baseline` per row and roll them up in `_summarize`.
- **Modify:** `harness/runner.py` — add `--with-baseline`, thread into `RunOptions.extra` and `config.json`.
- **Modify:** `harness/report_dashboard_html.py` — third chart bar + comparison table when baseline metrics exist.
- **Modify:** `dashboard/app.py` — checkbox that appends `--with-baseline` to the launch command.

---

## Task 1: Baseline extractor module

**Files:**
- Create: `core/baseline_extractor.py`
- Test: `tests/test_baseline_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_baseline_extractor.py
"""Unit tests for the bare-prompt baseline extractor."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.baseline_extractor import BASELINE_PROMPT_TEMPLATE, run_baseline
from core.models import SOExtractContractList


class TestBaselineExtractor(unittest.TestCase):
    def test_prompt_is_single_line_with_text_appended(self):
        prompt = BASELINE_PROMPT_TEMPLATE.format(text="hello world")
        self.assertTrue(prompt.startswith("Create a sales order from this:"))
        self.assertIn("hello world", prompt)

    def test_run_baseline_calls_llm_with_no_system_prompt_and_returns_dict(self):
        fake = SOExtractContractList.model_validate({"data": []})
        with patch("core.baseline_extractor.call_llm", return_value=fake) as mocked:
            out = run_baseline("some chat text", model_key="sonnet-4-6")
        self.assertEqual(out, {"data": []})
        _, kwargs = mocked.call_args
        self.assertIsNone(kwargs.get("system_prompt"))
        self.assertEqual(kwargs.get("model_key"), "sonnet-4-6")
        self.assertEqual(kwargs.get("schema"), SOExtractContractList)

    def test_run_baseline_returns_none_on_failure(self):
        with patch("core.baseline_extractor.call_llm", side_effect=RuntimeError("boom")):
            out = run_baseline("text", model_key="sonnet-4-6")
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_baseline_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.baseline_extractor'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/baseline_extractor.py
"""Bare-prompt baseline extractor.

Control condition for measuring how much the full extraction pipeline adds
over a vanilla Claude call: no system prompt, no few-shot, no org/customer
context, no post-processing — just one line of instruction plus the chat text,
validated against the same ``SOExtractContractList`` schema so the output is
field-comparable with the agent's.
"""

from __future__ import annotations

import logging

from core.llm_client import call_llm
from core.models import SOExtractContractList

logger = logging.getLogger(__name__)

BASELINE_PROMPT_TEMPLATE = "Create a sales order from this:\n\n{text}"


def run_baseline(text: str, model_key: str) -> dict | None:
    """Run the no-context baseline extraction.

    Returns the parsed dict on success, or ``None`` on any failure (logged as a
    warning, never raised) so a baseline miss can never fail the agent run.
    """
    prompt = BASELINE_PROMPT_TEMPLATE.format(text=text)
    try:
        result = call_llm(
            prompt,
            schema=SOExtractContractList,
            model_key=model_key,
            system_prompt=None,
        )
        return result.model_dump()
    except Exception as exc:  # noqa: BLE001 - baseline must never crash the run
        logger.warning("Baseline extraction failed (model=%s): %s", model_key, exc)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_baseline_extractor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/baseline_extractor.py tests/test_baseline_extractor.py
git commit -m "feat: add bare-prompt baseline extractor"
```

---

## Task 2: Add baseline fields to AgentRunResult

**Files:**
- Modify: `agents/base.py` (the `AgentRunResult` dataclass, after `score_raw_llm` / `validation_model_key`)
- Test: covered by Task 3's aggregate test (no standalone test for a dataclass field)

- [ ] **Step 1: Add the two fields**

In `agents/base.py`, inside the `AgentRunResult` dataclass, add these two fields immediately after the existing `score_raw_llm: ScoreResult = field(default_factory=ScoreResult)` line:

```python
    score_baseline: ScoreResult = field(default_factory=ScoreResult)
    baseline_output_json: dict[str, Any] | None = None
```

- [ ] **Step 2: Verify the module still imports**

Run: `python -c "from agents.base import AgentRunResult; r = AgentRunResult(agent_id='a', dataset_id='d', source_path='p', success=True, status='success', attempts=1, elapsed_sec=0.0); print(r.score_baseline.expected_available, r.baseline_output_json)"`
Expected: `False None`

- [ ] **Step 3: Commit**

```bash
git add agents/base.py
git commit -m "feat: add score_baseline and baseline_output_json to AgentRunResult"
```

---

## Task 3: Emit baseline metrics in artifacts

**Files:**
- Modify: `harness/artifacts.py` (`record_to_row` and the `_summarize` inner function inside `aggregate`)
- Test: `tests/test_baseline_aggregate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_baseline_aggregate.py
"""Baseline metric flows through record_to_row and aggregate()."""

from __future__ import annotations

import unittest

from agents.base import AgentRunResult, ScoreResult
from harness.artifacts import aggregate, record_to_row


def _rec_with_scores(*, baseline_mm, raw_mm, final_mm, compared=10):
    return AgentRunResult(
        agent_id="so_extraction",
        dataset_id="default",
        source_path="raw_data/chats/x.json",
        success=True,
        status="success",
        attempts=1,
        elapsed_sec=1.0,
        model_key="sonnet-4-6",
        score=ScoreResult(expected_available=True, mismatch_count=final_mm, compared_field_count=compared),
        score_raw_llm=ScoreResult(expected_available=True, mismatch_count=raw_mm, compared_field_count=compared),
        score_baseline=ScoreResult(expected_available=True, mismatch_count=baseline_mm, compared_field_count=compared),
    )


class TestBaselineAggregate(unittest.TestCase):
    def test_record_row_exposes_baseline_rate(self):
        row = record_to_row(_rec_with_scores(baseline_mm=4, raw_mm=2, final_mm=1))
        self.assertEqual(row["mismatch_count_baseline"], 4)
        self.assertTrue(row["baseline_available"])
        self.assertAlmostEqual(row["field_match_rate_baseline"], 0.6)

    def test_aggregate_rolls_up_baseline_rate(self):
        recs = [
            _rec_with_scores(baseline_mm=4, raw_mm=2, final_mm=1),
            _rec_with_scores(baseline_mm=6, raw_mm=3, final_mm=1),
        ]
        summary = aggregate(recs)
        totals = summary["totals"]
        # baseline: (4+6) mismatches over (10+10) compared -> 1 - 0.5 = 0.5
        self.assertAlmostEqual(totals["field_match_rate_baseline"], 0.5)
        # baseline metric also present per combo
        self.assertIn("field_match_rate_baseline", summary["by_combo"][0])

    def test_aggregate_baseline_rate_none_when_no_baseline(self):
        rec = AgentRunResult(
            agent_id="so_extraction", dataset_id="default", source_path="raw_data/chats/x.json",
            success=True, status="success", attempts=1, elapsed_sec=1.0, model_key="sonnet-4-6",
            score=ScoreResult(expected_available=True, mismatch_count=1, compared_field_count=10),
            score_raw_llm=ScoreResult(expected_available=True, mismatch_count=2, compared_field_count=10),
        )
        summary = aggregate([rec])
        self.assertIsNone(summary["totals"]["field_match_rate_baseline"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_baseline_aggregate.py -v`
Expected: FAIL with `KeyError: 'mismatch_count_baseline'`

- [ ] **Step 3: Add baseline fields to `record_to_row`**

In `harness/artifacts.py`, inside `record_to_row`, after the line `score_raw = asdict(rec.score_raw_llm) if rec.score_raw_llm else {}`, add:

```python
    score_baseline = asdict(rec.score_baseline) if rec.score_baseline else {}
```

Then, in the returned dict, add these keys immediately after the existing `"score_raw_llm": score_raw,` entry:

```python
        "score_baseline": score_baseline,
        "baseline_available": score_baseline.get("expected_available", False),
        "mismatch_count_baseline": score_baseline.get("mismatch_count", 0),
        "field_match_rate_baseline": _field_match_rate_from_score_dict(score_baseline),
        "baseline_output_json": rec.baseline_output_json,
```

- [ ] **Step 4: Roll baseline up in `_summarize`**

In `harness/artifacts.py`, inside the `_summarize` inner function of `aggregate`, after the line that computes `total_mismatch_raw = ...`, add:

```python
        baseline_rows = [r for r in with_expected if r.get("baseline_available")]
        total_mismatch_baseline = sum(r.get("mismatch_count_baseline", 0) for r in baseline_rows)
        total_compared_baseline = sum(r["compared_field_count"] for r in baseline_rows)
```

Then, in the dict returned by `_summarize`, add this key immediately after the existing `"field_match_rate_raw_llm": (...)` entry:

```python
            "field_match_rate_baseline": (
                1 - (total_mismatch_baseline / max(total_compared_baseline, 1))
                if baseline_rows else None
            ),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_baseline_aggregate.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add harness/artifacts.py tests/test_baseline_aggregate.py
git commit -m "feat: emit baseline field-match metric in artifacts"
```

---

## Task 4: Invoke baseline from the agent

**Files:**
- Modify: `agents/so_extraction/agent.py` (`run_one`)
- Test: `tests/test_baseline_extractor.py` (add an agent-integration test)

- [ ] **Step 1: Add the failing integration test**

Append this test class to `tests/test_baseline_extractor.py`:

```python
class TestAgentBaselineWiring(unittest.TestCase):
    def test_run_one_populates_baseline_when_requested(self):
        from pathlib import Path
        from unittest.mock import patch

        from agents.so_extraction.agent import ChatInput, SOExtractionAgent
        from agents.base import RunOptions
        from core.models import SOExtractContractList

        agent = SOExtractionAgent(
            id="so_extraction",
            display_name="SO Extraction",
            datasets=[],
            repo_root=Path(__file__).resolve().parents[1],
        )
        payload = ChatInput(source_path=Path("raw_data/chats/x.json"), text="buy 10 bags", meta={})
        opts = RunOptions(model_key="sonnet-4-6", extra={"run_baseline": True})

        # Stub the heavy engine + postprocess so we only exercise the baseline branch.
        with patch.object(agent, "_run_core_extraction", return_value=(
            {"data": []}, {"data": []}, None, "success", 1, None, "sonnet-4-6", "bedrock",
        )), patch("agents.so_extraction.agent.run_baseline", return_value={"data": []}) as mocked_base, \
                patch.object(agent, "expected_for", return_value=None):
            result = agent.run_one(payload, opts)

        mocked_base.assert_called_once()
        self.assertEqual(result.baseline_output_json, {"data": []})

    def test_run_one_skips_baseline_by_default(self):
        from pathlib import Path
        from unittest.mock import patch

        from agents.so_extraction.agent import ChatInput, SOExtractionAgent
        from agents.base import RunOptions

        agent = SOExtractionAgent(
            id="so_extraction", display_name="SO Extraction", datasets=[],
            repo_root=Path(__file__).resolve().parents[1],
        )
        payload = ChatInput(source_path=Path("raw_data/chats/x.json"), text="buy 10 bags", meta={})
        opts = RunOptions(model_key="sonnet-4-6", extra={})

        with patch.object(agent, "_run_core_extraction", return_value=(
            {"data": []}, {"data": []}, None, "success", 1, None, "sonnet-4-6", "bedrock",
        )), patch("agents.so_extraction.agent.run_baseline") as mocked_base, \
                patch.object(agent, "expected_for", return_value=None):
            result = agent.run_one(payload, opts)

        mocked_base.assert_not_called()
        self.assertIsNone(result.baseline_output_json)
```

> NOTE: The test patches a helper `_run_core_extraction` that does not exist yet. Rather than introduce that refactor, the simpler implementation below patches the real collaborators. **Replace the two `patch.object(agent, "_run_core_extraction", ...)` blocks** with patches of the engine instead — see Step 3 for the exact implementation, then update these tests to patch `agents.so_extraction.agent.ExtractionEngine` and `agents.so_extraction.agent.run_postprocess_pipeline`. Keep the `run_baseline` assertions unchanged.

Concretely, in both tests replace the `patch.object(agent, "_run_core_extraction", return_value=(...))` context manager with:

```python
        from unittest.mock import MagicMock
        engine = MagicMock()
        engine.run.return_value = MagicMock(
            status="success", output_json='{"data": []}', attempts=1, error=None,
            model_key="sonnet-4-6", model_provider="bedrock",
            chunk_count=1, chunk_truncated=False, input_chars=10,
        )
        engine.iso_date = "2026-06-01"
        with patch("agents.so_extraction.agent.ExtractionEngine", return_value=engine), \
                patch("agents.so_extraction.agent.run_postprocess_pipeline", return_value=({"data": []}, {})), \
                patch("agents.so_extraction.agent.run_baseline", return_value={"data": []}) as mocked_base, \
                patch.object(agent, "expected_for", return_value=None):
            result = agent.run_one(payload, opts)
```

(For the "skips" test, use `patch("agents.so_extraction.agent.run_baseline") as mocked_base` with no return value.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_baseline_extractor.py::TestAgentBaselineWiring -v`
Expected: FAIL with `ImportError: cannot import name 'run_baseline'` (the agent does not import it yet)

- [ ] **Step 3: Wire the baseline into `run_one`**

In `agents/so_extraction/agent.py`, add this import near the other `core` imports at the top:

```python
from core.baseline_extractor import run_baseline
```

Then, in `run_one`, locate the block that computes scores:

```python
        expected = self.expected_for(input_payload.source_path)
        score_raw = self.score(expected, raw_dict)
        score_final = self.score(expected, final_dict)
```

Immediately after those three lines, add:

```python
        baseline_dict: dict[str, Any] | None = None
        score_baseline = ScoreResult()
        if options.extra.get("run_baseline"):
            baseline_dict = run_baseline(input_payload.text, options.model_key)
            score_baseline = self.score(expected, baseline_dict)
```

Finally, in the `return AgentRunResult[dict](...)` call, add these two keyword arguments next to the existing `score_raw_llm=score_raw,` argument:

```python
            score_baseline=score_baseline,
            baseline_output_json=baseline_dict,
```

> The existing return already passes `score=score_final` and `score_raw_llm=score_raw`; `ScoreResult` is already imported in this module (it comes from `agents.base`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_baseline_extractor.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add agents/so_extraction/agent.py tests/test_baseline_extractor.py
git commit -m "feat: run baseline extraction from SOExtractionAgent when requested"
```

---

## Task 5: CLI `--with-baseline` flag

**Files:**
- Modify: `harness/runner.py` (`_parse_args`, `_run_extra`, the `config_payload` dict in `main`)
- Test: `tests/test_runner_baseline_flag.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runner_baseline_flag.py
"""--with-baseline flips run_baseline in RunOptions.extra."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from harness.runner import _run_extra


class TestRunnerBaselineFlag(unittest.TestCase):
    def test_run_extra_sets_run_baseline_true(self):
        args = SimpleNamespace(validation_model="", db_few_shot_limit=0, with_baseline=True)
        extra = _run_extra(args, "sonnet-4-6")
        self.assertTrue(extra["run_baseline"])

    def test_run_extra_run_baseline_defaults_false(self):
        args = SimpleNamespace(validation_model="", db_few_shot_limit=0, with_baseline=False)
        extra = _run_extra(args, "sonnet-4-6")
        self.assertFalse(extra["run_baseline"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runner_baseline_flag.py -v`
Expected: FAIL with `KeyError: 'run_baseline'`

- [ ] **Step 3: Add the flag and thread it through**

In `harness/runner.py`, inside `_parse_args`, add this argument next to the other boolean flags (e.g. after the `--skip-without-expected` line):

```python
    p.add_argument(
        "--with-baseline",
        action="store_true",
        help="Also run a no-context baseline extraction (single-line prompt, no system prompt) per chat for comparison.",
    )
```

In `_run_extra`, change the returned dict to include the baseline flag:

```python
def _run_extra(args: argparse.Namespace, extraction_model_key: str) -> dict[str, Any]:
    validation_key = (args.validation_model or "").strip() or extraction_model_key
    return {
        "db_few_shot_limit": args.db_few_shot_limit,
        "validation_model_key": validation_key,
        "enable_validation_llm": True,
        "enable_deterministic_postprocess": True,
        "run_baseline": bool(getattr(args, "with_baseline", False)),
    }
```

In `main`, inside the `config_payload` dict, add this key (e.g. after `"skip_without_expected": bool(args.skip_without_expected),`):

```python
        "with_baseline": bool(args.with_baseline),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runner_baseline_flag.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add harness/runner.py tests/test_runner_baseline_flag.py
git commit -m "feat: add --with-baseline flag to the harness runner"
```

---

## Task 6: Report — third bar + comparison table

**Files:**
- Modify: `harness/report_dashboard_html.py` (`_postprocess_comparison_html`)
- Test: `tests/test_report_baseline_html.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_baseline_html.py
"""Report adds a baseline bar + table only when baseline metrics exist."""

from __future__ import annotations

import unittest

from harness.report_dashboard_html import _postprocess_comparison_html


def _summary(with_baseline: bool):
    totals = {
        "run_count": 2,
        "field_match_rate_raw_llm": 0.74,
        "field_match_rate_final": 0.89,
        "field_match_rate": 0.89,
        "improvement_rate": 0.5,
        "regression_count": 0,
    }
    combo = {
        "model_key": "sonnet-4-6",
        "few_shot_count": 0,
        "field_match_rate_raw_llm": 0.74,
        "field_match_rate_final": 0.89,
        "field_match_rate": 0.89,
    }
    if with_baseline:
        totals["field_match_rate_baseline"] = 0.61
        combo["field_match_rate_baseline"] = 0.61
    return {"totals": totals, "by_combo": [combo], "by_chat": []}


class TestReportBaseline(unittest.TestCase):
    def test_baseline_bar_present_when_metric_exists(self):
        html, script = _postprocess_comparison_html(_summary(with_baseline=True))
        self.assertIn("Baseline", script)
        self.assertIn("baseline_pct", script)

    def test_no_baseline_bar_when_metric_absent(self):
        html, script = _postprocess_comparison_html(_summary(with_baseline=False))
        self.assertNotIn("baseline_pct", script)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report_baseline_html.py -v`
Expected: FAIL — `baseline_pct` not found in the script.

- [ ] **Step 3: Add baseline to the chart and headline**

In `harness/report_dashboard_html.py`, inside `_postprocess_comparison_html`, after the line `final_rate = totals.get("field_match_rate_final") or totals.get("field_match_rate")`, add:

```python
    baseline_rate = totals.get("field_match_rate_baseline")
    has_baseline = baseline_rate is not None
```

In the `for r in summary.get("by_combo") or []:` loop, add a baseline value to each `combo_points` dict. Replace the existing `combo_points.append({...})` call with:

```python
        cb = r.get("field_match_rate_baseline")
        point = {
            "label": label,
            "fs": int(r.get("few_shot_count", 0)),
            "raw_pct": round(100.0 * float(cr), 2) if cr is not None else 0.0,
            "final_pct": round(100.0 * float(cf), 2) if cf is not None else 0.0,
        }
        if cb is not None:
            point["baseline_pct"] = round(100.0 * float(cb), 2)
        combo_points.append(point)
```

- [ ] **Step 4: Inject the baseline dataset into the Chart.js script**

Still in `_postprocess_comparison_html`, replace the `datasets: [...]` block in the `script` f-string so the baseline bar is prepended only when present. Change the existing `script` assignment's `datasets` array to be built dynamically. Replace:

```python
      datasets: [
        {{ label: "Raw LLM", data: ppData.map((p) => p.raw_pct), backgroundColor: "#7a8aa8cc" }},
        {{ label: "Final", data: ppData.map((p) => p.final_pct), backgroundColor: "#2d6b3fcc" }},
      ],
```

with:

```python
      datasets: ([]).concat(
        (ppData.length && ppData[0].baseline_pct !== undefined)
          ? [{{ label: "Baseline Extraction", data: ppData.map((p) => p.baseline_pct), backgroundColor: "#b9543fcc" }}]
          : [],
        [
          {{ label: "Agent Extraction", data: ppData.map((p) => p.raw_pct), backgroundColor: "#7a8aa8cc" }},
          {{ label: "Validation Layer", data: ppData.map((p) => p.final_pct), backgroundColor: "#2d6b3fcc" }},
        ]
      ),
```

> The bar labels change from "Raw LLM"/"Final" to "Agent Extraction"/"Validation Layer" to match the three-tier story. This is intentional and applies in both the baseline and no-baseline cases.

- [ ] **Step 5: Add the headline lift line when baseline exists**

Still in `_postprocess_comparison_html`, find the `delta_note = ""` assignment. Immediately before the `html = f"""` line, add a baseline headline string:

```python
    baseline_note = ""
    if has_baseline:
        b_pct = 100.0 * float(baseline_rate)
        a_pct = 100.0 * float(raw_rate) if raw_rate is not None else 0.0
        v_pct = 100.0 * float(final_rate) if final_rate is not None else 0.0
        lift_total = v_pct - b_pct
        baseline_note = (
            f"<p class=\"section-intro\"><strong>Baseline: {b_pct:.0f}% → "
            f"Agent: {a_pct:.0f}% → Validation: {v_pct:.0f}%</strong> "
            f"(+{lift_total:.0f}pp lift over no-context baseline).</p>"
        )
```

Then insert `{baseline_note}` into the `html` f-string immediately after the line `<p class="section-intro">Compare primary extraction ...</p>` (i.e. add `  {baseline_note}` on its own line right after that paragraph).

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_report_baseline_html.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Run the existing report tests to confirm no regression**

Run: `python -m pytest tests/test_report_summary_html.py tests/test_report_dashboard_html.py -v`
Expected: PASS (existing report tests still green)

- [ ] **Step 8: Commit**

```bash
git add harness/report_dashboard_html.py tests/test_report_baseline_html.py
git commit -m "feat: add baseline bar and three-tier headline to report"
```

---

## Task 6b: Report — per-chat comparison table

**Files:**
- Modify: `harness/report_dashboard_html.py` (add `_baseline_table_html`; call it from `_postprocess_comparison_html`)
- Test: `tests/test_report_baseline_html.py` (extend)

- [ ] **Step 1: Extend the failing test**

Append to `tests/test_report_baseline_html.py`, inside `TestReportBaseline`:

```python
    def test_per_chat_table_rendered_with_baseline(self):
        summary = _summary(with_baseline=True)
        summary["by_chat"] = [{
            "chat_filename": "chat_01.json",
            "model_key": "sonnet-4-6",
            "few_shot_count": 0,
            "field_match_rate_baseline": 0.61,
            "field_match_rate_raw_llm": 0.74,
            "field_match_rate_final": 0.89,
            "field_match_rate": 0.89,
        }]
        html, _script = _postprocess_comparison_html(summary)
        self.assertIn("Baseline Comparison", html)
        self.assertIn("chat_01.json", html)
        self.assertIn("+28", html)  # lift: 89 - 61 = 28pp

    def test_no_table_without_baseline(self):
        html, _script = _postprocess_comparison_html(_summary(with_baseline=False))
        self.assertNotIn("Baseline Comparison", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report_baseline_html.py::TestReportBaseline::test_per_chat_table_rendered_with_baseline -v`
Expected: FAIL — "Baseline Comparison" not in html.

- [ ] **Step 3: Add the table builder**

In `harness/report_dashboard_html.py`, add this helper function immediately above `_postprocess_comparison_html`:

```python
def _baseline_table_html(summary: dict[str, Any]) -> str:
    """Per-chat baseline → agent → validation comparison table.

    Returns an empty string when no baseline metrics are present so the
    section disappears for runs without ``--with-baseline``.
    """
    rows = [
        r for r in (summary.get("by_chat") or [])
        if r.get("field_match_rate_baseline") is not None
    ]
    if not rows:
        return ""

    def _pct(v: Any) -> str:
        return f"{100.0 * float(v):.0f}%" if v is not None else "—"

    body = []
    for r in rows:
        b = r.get("field_match_rate_baseline")
        a = r.get("field_match_rate_raw_llm")
        f = r.get("field_match_rate_final") or r.get("field_match_rate")
        lift = (
            f"+{100.0 * (float(f) - float(b)):.0f}pp"
            if (b is not None and f is not None) else "—"
        )
        body.append(
            "<tr>"
            f"<td>{_esc(str(r.get('chat_filename', '')))}</td>"
            f"<td>{_pct(b)}</td>"
            f"<td>{_pct(a)}</td>"
            f"<td>{_pct(f)}</td>"
            f"<td>{_esc(lift)}</td>"
            "</tr>"
        )
    return (
        "<div class=\"chart-wrap\" style=\"margin-top:24px;\">"
        "<div class=\"chart-title\">Baseline Comparison (per chat)</div>"
        "<table class=\"leaderboard\"><thead><tr>"
        "<th>Chat</th><th>Baseline</th><th>Agent (raw)</th>"
        "<th>Validation</th><th>Lift (baseline → validation)</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )
```

> `_esc` is the module's existing HTML-escape helper (used throughout this file); no new import is needed. The `leaderboard` CSS class is already defined in the report's `<style>` block.

- [ ] **Step 4: Render the table inside the section**

In `_postprocess_comparison_html`, build the table just before the `html = f"""` assignment:

```python
    baseline_table = _baseline_table_html(summary)
```

Then insert `{baseline_table}` into the `html` f-string immediately after the `</div>` that closes the `<div class="chart-wrap" ...>` chart block (i.e. right before the closing `</section>`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_report_baseline_html.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 6: Commit**

```bash
git add harness/report_dashboard_html.py tests/test_report_baseline_html.py
git commit -m "feat: add per-chat baseline comparison table to report"
```

---

## Task 7: Dashboard checkbox

**Files:**
- Modify: `dashboard/app.py` (Bulk Benchmark tab — add a checkbox near `bulk_skip_no_expected` and append the flag in the launch command at line ~602)
- Test: manual (Streamlit UI; no unit harness for the dashboard)

- [ ] **Step 1: Add the checkbox control**

In `dashboard/app.py`, immediately after the existing line:

```python
    skip_no_expected = st.checkbox("Skip chats without expected entries", value=True, key="bulk_skip_no_expected")
```

add:

```python
    with_baseline = st.checkbox(
        "Run baseline comparison",
        value=False,
        key="bulk_with_baseline",
        help=(
            "Also run a no-context baseline (single-line prompt, no system prompt) per chat. "
            "Adds a 'Baseline Extraction' bar and a three-tier comparison to the report."
        ),
    )
```

- [ ] **Step 2: Append the flag to the launch command**

In `dashboard/app.py`, in the `if st.button("Launch bulk run", ...)` block, after the line:

```python
        if skip_no_expected:
            cmd += ["--skip-without-expected"]
```

add:

```python
        if with_baseline:
            cmd += ["--with-baseline"]
```

- [ ] **Step 3: Smoke-test the dashboard imports**

Run: `python -c "import ast; ast.parse(open('dashboard/app.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add dashboard/app.py
git commit -m "feat: add baseline comparison checkbox to dashboard bulk runner"
```

---

## Task 8: Full verification

- [ ] **Step 1: Run the whole test suite**

Run: `python -m pytest tests/ -v`
Expected: all tests PASS (including the four new test files).

- [ ] **Step 2: Sanity-check the runner help shows the flag**

Run: `python -m harness.runner --help`
Expected: output includes `--with-baseline`.

- [ ] **Step 3: Commit any final fixes (if needed)**

```bash
git add -A
git commit -m "test: verify baseline comparison end to end"
```

---

## Self-Review Notes

- **Spec §1 (Baseline Engine):** Task 1 (`run_baseline`, no system prompt, same schema, warn-and-skip) + Task 2 (`score_baseline`, `baseline_output_json` fields) + Task 4 (triggered via `options.extra["run_baseline"]`). ✓
- **Spec §2 (CLI & Runner):** Task 5 (`--with-baseline`, `RunOptions.extra`, `config.json` `with_baseline`) + Task 7 (dashboard checkbox). Pipeline runs are untouched (the flag only flows through `_run_extra`, which the pipeline path also calls for step 0 — harmless, baseline simply runs for the first agent; acceptable since the spec scopes baseline to single-agent extraction and the pipeline's first agent IS the extraction agent). ✓
- **Spec §3 (Report chart):** Task 6 — third bar prepended only when `field_match_rate_baseline` present; default stays 2 bars; headline lift line; bar relabeled to "Agent Extraction"/"Validation Layer". ✓
- **Spec §3 (Report table):** Task 6b — dedicated "Baseline Comparison" per-chat table with Baseline / Agent (raw) / Validation / Lift columns, rendered only when baseline metrics exist. ✓
- **Type consistency:** `field_match_rate_baseline` / `mismatch_count_baseline` / `baseline_available` used identically across `record_to_row`, `_summarize`, and the report. `score_baseline` is a `ScoreResult` everywhere. ✓
