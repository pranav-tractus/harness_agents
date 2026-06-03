# Merge OpenAI + Anthropic Extraction Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one combined harness run under `results/` that compares Bedrock/OpenAI models plus Anthropic API Opus 4.7/4.8, with baseline bars enabled everywhere Anthropic Opus rows use the Bedrock `opus-4-6` baseline extraction.

**Architecture:** A small `scripts/merge_extraction_runs.py` loads `run.jsonl` from `20260603T053802Z` (5 models, `--with-baseline`) and `20260603T051559Z` (adds `anthropic:opus-4-7` / `anthropic:opus-4-8`). Shared model×chat keys come from the baseline run; Anthropic-only rows get `baseline_output_json` + `score_baseline` copied from the matching `opus-4-6` row (same `source_path`). Regenerate artifacts via existing `harness.artifacts` writers so `report.html` / `token_report.html` match the editorial dashboard style.

**Tech Stack:** Python 3, existing `harness/artifacts.py`, `harness/report_dashboard_html.py`, heuristic visual story (no LLM required).

---

## Source runs

| Run ID | Records | Models | Baseline |
|--------|---------|--------|----------|
| `20260603T053802Z` | 350 | sonnet-4-6, opus-4-6, openai:5.4, openai:5.2, gemini:gemini-2.5-pro | per-model `--with-baseline` |
| `20260603T051559Z` | 490 | above + anthropic:opus-4-7, anthropic:opus-4-8 | none |

**Merged output:** 490 rows (7 models × 70 chats).

**Baseline policy:**

- `sonnet-4-6`, `opus-4-6`, `openai:*`, `gemini:*` — keep each model's own baseline from `053802Z`.
- `anthropic:opus-4-7`, `anthropic:opus-4-8` — copy `opus-4-6` baseline fields from `053802Z` keyed by `source_path`.

---

## File structure

- **Create:** `scripts/merge_extraction_runs.py` — merge + artifact regeneration CLI.
- **Create:** `results/<new_run_id>/` — `run.jsonl`, `config.json`, `aggregate.json`, `report.html`, `token_report.html`.

---

### Task 1: Merge script

**Files:**
- Create: `scripts/merge_extraction_runs.py`

- [ ] **Step 1: Implement row loader and baseline lookup**

```python
def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def opus46_baseline_by_source(rows: list[dict]) -> dict[str, dict]:
    return {
        r["source_path"]: r
        for r in rows
        if r.get("model_key") == "opus-4-6" and r.get("baseline_available")
    }
```

- [ ] **Step 2: Implement `inject_opus46_baseline(row, baseline_row)`**

Copy `baseline_output_json`, `score_baseline`, and re-derive flat fields via `record_to_row` after building `AgentRunResult`.

- [ ] **Step 3: Implement `merge_runs(primary, supplemental, anthropic_models)`**

- Take all rows from `primary` (`053802Z`).
- Append rows from `supplemental` where `model_key in anthropic_models`.
- Inject baseline for those Anthropic rows.

- [ ] **Step 4: Regenerate artifacts**

```python
records = [row_to_result(r) for r in merged_rows]
summary = artifacts.aggregate(records)
artifacts.write_config(...)
artifacts.write_aggregate(...)
# write run.jsonl manually (sorted)
artifacts.write_report(..., generate_llm_story=False)
artifacts.write_token_report(...)
```

- [ ] **Step 5: CLI**

```bash
python scripts/merge_extraction_runs.py \
  --primary results/20260603T053802Z \
  --supplemental results/20260603T051559Z \
  --anthropic-models anthropic:opus-4-7,anthropic:opus-4-8 \
  --out results
```

Expected: prints new run dir path, 490 lines in `run.jsonl`.

---

### Task 2: Verify merged report

- [ ] **Step 1: Row counts**

```bash
wc -l results/<new_id>/run.jsonl
# Expected: 490

python3 -c "
import json
from collections import Counter
c=Counter()
for l in open('results/<new_id>/run.jsonl'):
  c[json.loads(l)['model_key']]+=1
print(c)
"
# Expected: 7 models × 70
```

- [ ] **Step 2: Anthropic baseline present**

```bash
python3 -c "
import json
for l in open('results/<new_id>/run.jsonl'):
  r=json.loads(l)
  if r['model_key'].startswith('anthropic:'):
    assert r['baseline_available'], r['model_key']
print('ok')
"
```

- [ ] **Step 3: Open `report.html`**

Confirm: Instrument Serif / IBM Plex styling, baseline chart bar, 7 model rows in leaderboard, `field_match_rate_baseline` non-null for Anthropic Opus combos in `aggregate.json`.

---

## Open questions (for stakeholder)

1. **Gemini** — both source runs include `gemini:gemini-2.5-pro`. Include in merged report, or drop to match "OpenAI + Anthropic" scope only?
2. **LLM narrative** — regenerate Gemini/Sonnet story (`generate_llm_story=True`, needs API keys) or heuristic-only (`False`)?
3. **Run folder name** — auto UTC timestamp vs fixed slug (e.g. `20260603T-merged-opus-openai`)?
4. **Provenance block** — add `merged_from` / `baseline_policy` keys to `config.json` for the static site index?

---

## Self-review

- **Spec coverage:** merge rows ✓, opus-4.6 baseline for anthropic opus ✓, regenerate styled reports ✓.
- **Placeholder scan:** none.
- **Type consistency:** uses `record_to_row` / `aggregate` same as harness runner ✓.
