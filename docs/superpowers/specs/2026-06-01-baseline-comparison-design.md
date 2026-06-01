# Baseline Comparison Layer — Design Spec

**Date:** 2026-06-01  
**Status:** Approved

## Overview

Add a baseline comparison layer to quantify how much value the full SO extraction pipeline adds over a vanilla Claude call with no context. The baseline sends each chat to Claude with a single-line prompt and no system prompt, scores the output field-by-field, and surfaces the three-tier accuracy progression (Baseline → Agent Extraction → Validation Layer) in the run report.

---

## 1. Baseline Engine

**File:** `core/baseline_extractor.py`

A single function:

```python
def run_baseline(text: str, model_key: str) -> dict | None
```

Behavior:
- No system prompt
- User message: `"Create a sales order from this:\n\n{text}"`
- Uses the same `SOExtractContractList` Pydantic schema via instructor (structured output), making the output directly comparable field-by-field
- Uses the same `model_key` as the agent run
- Returns the parsed dict on success, `None` on any failure (logged as warning, never raises)

**Data model additions to `AgentRunResult`:**

| Field | Type | Description |
|---|---|---|
| `score_baseline` | `ScoreResult` | Field-level score of baseline output vs. expected |
| `baseline_output_json` | `dict \| None` | Raw baseline JSON for debugging |

**Trigger:** `SOExtractionAgent.run_one()` checks `options.extra.get("run_baseline")` and calls `run_baseline()` at the end of the run. If baseline fails, the agent result is unaffected.

---

## 2. CLI & Runner Integration

**Flag:** `--with-baseline` (boolean, default off) added to `harness/runner.py`

When set:
- Propagated into `RunOptions.extra["run_baseline"] = True` for every case in `_run_bulk`
- `config.json` written per run includes `"with_baseline": true`
- Not applied to pipeline runs (only single-agent extraction runs)

**Dashboard (`dashboard/app.py`):**
- A checkbox "Run baseline comparison" maps to the `--with-baseline` flag when launching a run from the UI

---

## 3. Report Visualization

**File:** `harness/report_dashboard_html.py`

### Default behavior (no baseline)

The existing 2-bar chart remains unchanged:
- Bar 1: Agent Extraction (raw LLM, `score_raw_llm`)
- Bar 2: Validation Layer (final, `score`)

### With baseline (`config["with_baseline"] == true`)

A third bar is prepended on the left of each group:
- Bar 1: Baseline Extraction (`score_baseline`) — new
- Bar 2: Agent Extraction (`score_raw_llm`) — existing
- Bar 3: Validation Layer (`score`) — existing

**Headline lift number** above the chart:
> `Baseline: 61% → Agent: 74% → Validation: 89% (+28pp lift)`

**Summary table** — "Baseline Comparison" section with one row per chat:

| Chat | Baseline | Agent (raw) | Validation | Lift (baseline → validation) |
|---|---|---|---|---|
| chat_01.json | 61% | 74% | 89% | +28pp |
| … | … | … | … | … |

If the run was executed without `--with-baseline`, this entire section is absent from the report.

---

## Constraints & Non-Goals

- The baseline always uses the same model as the agent run; no separate model config for baseline
- No few-shot, no org/customer context, no deterministic post-processing for the baseline
- Baseline failure does not fail the run or the case
- No changes to pipeline runs
- No new agent entry in `configs/agents.json`
