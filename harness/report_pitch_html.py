"""Executive pitch HTML report — charts and headline numbers only."""

from __future__ import annotations

import json
from typing import Any

from harness.report_dashboard_html import (
    _REPORT_CHART_CDN,
    _REPORT_FONTS,
    _css_block,
    _esc,
    _finding_block,
    _fmt_pct,
    _has_postprocess_metrics,
)
from harness.report_summary import HarnessVisualStory, VisualFinding

# Friendly labels for stakeholder decks (no internal registry keys in charts).
MODEL_LABELS: dict[str, str] = {
    "sonnet-4-6": "Sonnet 4.6",
    "opus-4-6": "Opus 4.6",
    "anthropic:opus-4-7": "Opus 4.7",
    "anthropic:opus-4-8": "Opus 4.8",
    "openai:5.4": "GPT-5.4",
    "openai:5.2": "GPT-5.2",
}

PITCH_EXTRA_CSS = """
.pitch-hero { margin: 48px 0 56px; }
.pitch-kpi-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin: 36px 0 48px;
}
.pitch-kpi {
  background: var(--bg-card);
  border: 1px solid var(--ink);
  padding: 28px 24px;
}
.pitch-kpi .kpi-val {
  font-family: var(--display);
  font-size: 48px;
  line-height: 1;
  margin: 8px 0 10px;
  letter-spacing: -0.02em;
}
.pitch-kpi .kpi-val.good { color: var(--good); }
.pitch-kpi .kpi-label {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-mute);
}
.pitch-kpi .kpi-desc { font-size: 13px; color: var(--ink-soft); line-height: 1.45; }
.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 28px;
  margin: 28px 0;
}
.chart-grid .chart-wrap.full { grid-column: 1 / -1; }
.chart-canvas-wrap.tall { height: 380px; }
.chart-canvas-wrap.wide { height: 300px; }
.pitch-foot {
  margin: 64px 0 40px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
  font-size: 12px;
  color: var(--ink-mute);
  font-family: var(--mono);
  line-height: 1.6;
}
@media (max-width: 900px) {
  .chart-grid { grid-template-columns: 1fr; }
  .pitch-kpi-row { grid-template-columns: 1fr; }
  .findings { grid-template-columns: 1fr; }
  .finding { border-right: none; border-bottom: 1px solid var(--line); }
}
"""


def _friendly_model(model_key: str) -> str:
    if model_key in MODEL_LABELS:
        return MODEL_LABELS[model_key]
    # Strip common provider prefixes from registry keys.
    for prefix in ("anthropic:", "openai:", "gemini:", "bedrock:"):
        if model_key.startswith(prefix):
            return model_key.split(":", 1)[-1]
    return model_key


def _unique_chat_count(summary: dict[str, Any]) -> int:
    chats = {
        r.get("chat_filename")
        for r in (summary.get("by_chat") or [])
        if r.get("chat_filename")
    }
    return len(chats)


def _combo_points(summary: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for r in summary.get("by_combo") or []:
        mk = str(r.get("model_key", ""))
        if mk.startswith("gemini:"):
            continue
        final = r.get("field_match_rate_final") or r.get("field_match_rate")
        raw = r.get("field_match_rate_raw_llm")
        base = r.get("field_match_rate_baseline")
        if final is None:
            continue
        points.append(
            {
                "key": mk,
                "label": _friendly_model(mk),
                "final_pct": round(100.0 * float(final), 1),
                "raw_pct": round(100.0 * float(raw), 1) if raw is not None else None,
                "baseline_pct": round(100.0 * float(base), 1) if base is not None else None,
                "elapsed": round(float(r.get("avg_elapsed_sec") or 0.0), 2),
                "mismatch": round(float(r.get("avg_mismatch_per_expected_run") or 0.0), 2),
            }
        )
    points.sort(key=lambda p: -p["final_pct"])
    return points


def _dataset_points(summary: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in summary.get("by_dataset") or []:
        fm = r.get("field_match_rate")
        if fm is None:
            continue
        ds = str(r.get("dataset_id", ""))
        out.append(
            {
                "label": ds.replace("_", " ").title(),
                "pct": round(100.0 * float(fm), 1),
            }
        )
    out.sort(key=lambda p: -p["pct"])
    return out


def _pitch_story(summary: dict[str, Any], config: dict[str, Any]) -> HarnessVisualStory:
    totals = summary.get("totals") or {}
    combos = _combo_points(summary)
    chats = _unique_chat_count(summary) or int((totals.get("run_count") or 0) / max(len(combos), 1))
    n_models = len(combos)
    best = combos[0] if combos else None
    best_label = best["label"] if best else "—"
    best_pct = best["final_pct"] if best else 0.0

    lifts: list[float] = []
    for p in combos:
        if p["baseline_pct"] is not None:
            lifts.append(p["final_pct"] - p["baseline_pct"])
    avg_lift = sum(lifts) / len(lifts) if lifts else 0.0

    baseline_note = str(config.get("baseline_policy") or "")
    anthropic_note = ""
    if "anthropic:opus" in baseline_note:
        anthropic_note = (
            " Opus 4.7 and Opus 4.8 use the same Opus 4.6 no-context baseline "
            "for a fair comparison."
        )

    return HarnessVisualStory(
        headline_start="The full pipeline wins on validated field accuracy",
        headline_emphasis="across every model in the bake-off.",
        dek=(
            f"Head-to-head benchmark on {chats} real sales-order chats × {n_models} frontier models. "
            f"Numbers below are **field match vs. golden JSON** after validation — what you can ship."
        ),
        findings=[
            VisualFinding(
                label="Recommended model",
                label_critical=False,
                headline=f"{best_pct:.1f}%",
                headline_tone="good",
                description=(
                    f"**{best_label}** leads on validated output quality in this bake-off. "
                    "Use the accuracy chart to compare the full lineup at a glance."
                ),
            ),
            VisualFinding(
                label="Pipeline lift",
                label_critical=False,
                headline=f"+{avg_lift:.1f} pp",
                headline_tone="good" if avg_lift > 0 else "neutral",
                description=(
                    "Average gain from bare extraction → validated JSON "
                    f"(baseline → final) across models.{anthropic_note}"
                ),
            ),
            VisualFinding(
                label="Coverage",
                label_critical=False,
                headline=f"{chats}",
                headline_tone="neutral",
                description=(
                    f"Production-style chats across **{len(config.get('datasets') or [])} datasets** "
                    f"({', '.join(config.get('datasets') or [])}). "
                    "Same evaluation harness for every vendor — apples-to-apples for procurement."
                ),
            ),
        ],
        dataset_section_intro="",
        alert_lead="",
        alert_body="",
        frontier_section_intro="",
        leaderboard_section_intro="",
        fewshot_section_intro="",
        fewshot_takeaway="",
        actions_section_intro="",
        next_steps=[],
    )


def _charts_script(
    summary: dict[str, Any],
    *,
    combos: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
) -> str:
    combo_json = json.dumps(combos, ensure_ascii=False)
    ds_json = json.dumps(datasets, ensure_ascii=False)
    has_pp = _has_postprocess_metrics(summary)
    pipeline_datasets = ""
    if has_pp:
        pipeline_datasets = """
        { label: "Bare extraction", data: comboData.map((p) => p.raw_pct), backgroundColor: "#7a8aa8cc" },
        { label: "Validated output", data: comboData.map((p) => p.final_pct), backgroundColor: "#2d6b3fcc" },
        """
        if combos and combos[0].get("baseline_pct") is not None:
            pipeline_datasets = (
                '{ label: "No-context baseline", data: comboData.map((p) => p.baseline_pct), backgroundColor: "#b9543fcc" },\n'
                + pipeline_datasets
            )

    return f"""
const comboData = {combo_json};
const datasetData = {ds_json};

if (comboData.length && document.getElementById("accuracyChart")) {{
  new Chart(document.getElementById("accuracyChart").getContext("2d"), {{
    type: "bar",
    data: {{
      labels: comboData.map((p) => p.label),
      datasets: [{{
        label: "Validated field match",
        data: comboData.map((p) => p.final_pct),
        backgroundColor: "#2d6b3fcc",
        borderRadius: 2,
      }}],
    }},
    options: {{
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ min: 0, max: 100, ticks: {{ callback: (v) => v + "%" }} }},
      }},
    }},
  }});
}}

if (comboData.length && document.getElementById("pipelineChart")) {{
  new Chart(document.getElementById("pipelineChart").getContext("2d"), {{
    type: "bar",
    data: {{
      labels: comboData.map((p) => p.label),
      datasets: [
        {pipeline_datasets}
      ],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      scales: {{
        y: {{ min: 0, max: 100, ticks: {{ callback: (v) => v + "%" }} }},
      }},
    }},
  }});
}}

if (comboData.length && document.getElementById("frontierChart")) {{
  new Chart(document.getElementById("frontierChart").getContext("2d"), {{
    type: "bubble",
    data: {{
      datasets: [{{
        label: "Model",
        data: comboData.map((p) => ({{
          x: p.elapsed,
          y: p.final_pct,
          r: Math.max(6, Math.min(22, p.mismatch * 3)),
        }})),
        backgroundColor: "#b8341c99",
      }}],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      scales: {{
        x: {{
          type: "logarithmic",
          title: {{ display: true, text: "Avg latency (s)" }},
        }},
        y: {{
          min: 0,
          max: 100,
          title: {{ display: true, text: "Validated field match (%)" }},
          ticks: {{ callback: (v) => v + "%" }},
        }},
      }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            label: (ctx) => {{
              const p = comboData[ctx.dataIndex];
              return `${{p.label}}: ${{p.final_pct}}% match, ${{p.elapsed}}s`;
            }},
          }},
        }},
      }},
    }},
  }});
}}

if (datasetData.length && document.getElementById("datasetChart")) {{
  new Chart(document.getElementById("datasetChart").getContext("2d"), {{
    type: "bar",
    data: {{
      labels: datasetData.map((p) => p.label),
      datasets: [{{
        label: "Blended field match",
        data: datasetData.map((p) => p.pct),
        backgroundColor: "#c4761ccc",
      }}],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        y: {{ min: 0, max: 100, ticks: {{ callback: (v) => v + "%" }} }},
      }},
    }},
  }});
}}
"""


def render_pitch_report_html(
    run_id: str,
    generated_at_utc: str,
    config: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    """Sales deck: KPI strip + Chart.js only (no per-run tables or config dumps)."""
    story = _pitch_story(summary, config)
    totals = summary.get("totals") or {}
    combos = _combo_points(summary)
    datasets = _dataset_points(summary)
    n_chats = _unique_chat_count(summary) or int(
        (totals.get("run_count") or 0) / max(len(combos), 1)
    )
    n_models = len(combos)

    h1_em = story.headline_emphasis.strip()
    h1_html = f"{_esc(story.headline_start)}" + (
        f" <em>{_esc(h1_em)}</em>" if h1_em else ""
    )
    findings_html = "".join(_finding_block(story, i, summary) for i in range(3))

    best = combos[0] if combos else None
    lifts = [
        p["final_pct"] - p["baseline_pct"]
        for p in combos
        if p.get("baseline_pct") is not None
    ]
    avg_lift = sum(lifts) / len(lifts) if lifts else 0.0

    kpi_row = f"""
<div class="pitch-kpi-row">
  <div class="pitch-kpi">
    <div class="kpi-label">Leader</div>
    <div class="kpi-val good">{best["final_pct"]:.1f}%</div>
    <div class="kpi-desc">{_esc(best["label"] if best else "—")} validated field match</div>
  </div>
  <div class="pitch-kpi">
    <div class="kpi-label">Pipeline value</div>
    <div class="kpi-val good">+{avg_lift:.1f} pp</div>
    <div class="kpi-desc">Avg lift from no-context baseline → validated JSON</div>
  </div>
  <div class="pitch-kpi">
    <div class="kpi-label">Benchmark scope</div>
    <div class="kpi-val">{n_chats}</div>
    <div class="kpi-desc">Chats × {n_models} models ({int(totals.get("run_count") or 0):,} scored runs)</div>
  </div>
</div>
"""

    script = _charts_script(summary, combos=combos, datasets=datasets)
    merged_from = config.get("merged_from") or []
    provenance = (
        f"Merged benchmark · sources: {', '.join(merged_from)}"
        if merged_from
        else "Harness benchmark"
    )
    run_counts = [int(r.get("run_count") or 0) for r in summary.get("by_combo") or []]
    coverage_note = ""
    if run_counts and min(run_counts) < max(run_counts):
        coverage_note = (
            f" Opus 4.7/4.8: {min(run_counts)} chats "
            f"(other models: {max(run_counts)})."
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Model benchmark — {_esc(run_id)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{_REPORT_FONTS}" rel="stylesheet">
<script src="{_REPORT_CHART_CDN}"></script>
<style>
{_css_block()}
{PITCH_EXTRA_CSS}
</style>
</head>
<body>
<div class="wrap">
<div class="masthead pitch-hero">
  <div class="masthead-top">
    <span><span class="dot"></span>Sales order extraction · model benchmark</span>
    <span>{_esc(generated_at_utc)}</span>
  </div>
  <h1>{h1_html}</h1>
  <p class="dek">{_esc(story.dek).replace("**", "")}</p>
</div>
<div class="findings">
{findings_html}
</div>
{kpi_row}
<section id="charts-accuracy">
  <div class="section-head"><span class="section-num">01</span><h2>Validated accuracy by model</h2></div>
  <p class="section-intro">Single number that matters for production: field match after the full extraction + validation pipeline.</p>
  <div class="chart-wrap full">
    <div class="chart-canvas-wrap tall"><canvas id="accuracyChart"></canvas></div>
  </div>
</section>
<section id="charts-pipeline">
  <div class="section-head"><span class="section-num">02</span><h2>What the pipeline adds</h2></div>
  <p class="section-intro">Compare bare LLM output against validated JSON. Baseline is a one-line prompt with no system context.</p>
  <div class="chart-wrap full">
    <div class="chart-canvas-wrap tall"><canvas id="pipelineChart"></canvas></div>
  </div>
</section>
<div class="chart-grid">
  <section id="charts-frontier">
    <div class="section-head"><span class="section-num">03</span><h2>Quality vs. speed</h2></div>
    <p class="section-intro">Bubble size reflects average mismatches per chat — smaller is cleaner.</p>
    <div class="chart-wrap">
      <div class="chart-canvas-wrap wide"><canvas id="frontierChart"></canvas></div>
    </div>
  </section>
  <section id="charts-dataset">
    <div class="section-head"><span class="section-num">04</span><h2>By dataset</h2></div>
    <p class="section-intro">Blended accuracy across all models in each data slice.</p>
    <div class="chart-wrap">
      <div class="chart-canvas-wrap wide"><canvas id="datasetChart"></canvas></div>
    </div>
  </section>
</div>
<div class="pitch-foot">
  {provenance} · {_fmt_pct(totals.get("field_match_rate"))} blended field match ·
  {_fmt_pct(totals.get("success_rate"))} run success ·
  Field match = share of compared JSON fields matching golden expected output.{coverage_note}
</div>
</div>
<script>
{script}
</script>
</body>
</html>
"""
