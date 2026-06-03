# harness/token_report_html.py
"""Token usage HTML report — shares styles with report_dashboard_html."""

from __future__ import annotations

import html as html_lib
import json
from typing import Any

from harness.report_dashboard_html import (
    _REPORT_CHART_CDN,
    _REPORT_FONTS,
    _css_block,
)


def _esc(s: str) -> str:
    return html_lib.escape(str(s), quote=True)


def _fmt_num(n: Any, decimals: int = 0) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def _token_summary_cards(totals: dict[str, Any]) -> str:
    ti = totals.get("total_input_tokens") or 0
    to_ = totals.get("total_output_tokens") or 0
    cr = totals.get("total_cache_read_tokens") or 0
    cw = totals.get("total_cache_write_tokens") or 0
    tt = totals.get("total_tokens") or 0
    cards = "".join([
        f'<div class="dataset-card"><div class="name">Input Tokens</div>'
        f'<div class="score">{_fmt_num(ti)}</div></div>',
        f'<div class="dataset-card"><div class="name">Output Tokens</div>'
        f'<div class="score">{_fmt_num(to_)}</div></div>',
        f'<div class="dataset-card"><div class="name">Cache Read</div>'
        f'<div class="score">{_fmt_num(cr)}</div></div>',
        f'<div class="dataset-card"><div class="name">Cache Write</div>'
        f'<div class="score">{_fmt_num(cw)}</div></div>',
        f'<div class="dataset-card"><div class="name">Total Tokens</div>'
        f'<div class="score">{_fmt_num(tt)}</div></div>',
    ])
    return f'<div class="dataset-grid">{cards}</div>'


def _per_model_table(by_combo: list[dict[str, Any]]) -> str:
    if not by_combo:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(str(r.get('model_key', '')))}</td>"
        f"<td>{_fmt_num(r.get('run_count'))}</td>"
        f"<td>{_fmt_num(r.get('total_input_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_output_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_tokens'))}</td></tr>"
        for r in by_combo
    )
    return (
        "<div class='chart-wrap' style='margin-top:24px;'>"
        "<div class='chart-title'>By Model</div>"
        "<table class='leaderboard'><thead><tr>"
        "<th>Model</th><th>Runs</th><th>Input</th><th>Output</th><th>Total</th>"
        "</tr></thead><tbody>"
        + rows
        + "</tbody></table></div>"
    )


def _per_chat_table(by_chat: list[dict[str, Any]]) -> str:
    if not by_chat:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(str(r.get('chat_filename', '')))}</td>"
        f"<td>{_esc(str(r.get('model_key', '')))}</td>"
        f"<td>{_fmt_num(r.get('total_input_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_output_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_cache_read_tokens'))}</td>"
        f"<td>{_fmt_num(r.get('total_tokens'))}</td></tr>"
        for r in by_chat
    )
    return (
        "<div class='chart-wrap' style='margin-top:24px;'>"
        "<div class='chart-title'>Per Chat</div>"
        "<table class='leaderboard'><thead><tr>"
        "<th>Chat</th><th>Model</th><th>Input</th><th>Output</th><th>Cache Read</th><th>Total</th>"
        "</tr></thead><tbody>"
        + rows
        + "</tbody></table></div>"
    )


def _bar_chart_script(by_combo: list[dict[str, Any]]) -> str:
    if not by_combo:
        return ""
    chart_data = json.dumps([
        {
            "label": str(r.get("model_key", "")),
            "input": int(r.get("total_input_tokens") or 0),
            "output": int(r.get("total_output_tokens") or 0),
            "cache": int((r.get("total_cache_read_tokens") or 0) + (r.get("total_cache_write_tokens") or 0)),
        }
        for r in by_combo
    ], ensure_ascii=False)
    return f"""
const tkData = {chart_data};
if (tkData.length && document.getElementById("tokenChart")) {{
  new Chart(document.getElementById("tokenChart").getContext("2d"), {{
    type: "bar",
    data: {{
      labels: tkData.map((d) => d.label),
      datasets: [
        {{ label: "Input", data: tkData.map((d) => d.input), backgroundColor: "#7a8aa8cc" }},
        {{ label: "Output", data: tkData.map((d) => d.output), backgroundColor: "#2d6b3fcc" }},
        {{ label: "Cache", data: tkData.map((d) => d.cache), backgroundColor: "#b9543fcc" }},
      ],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ position: "bottom" }} }},
      scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }},
    }},
  }});
}}
"""


def render_token_report_html(
    run_id: str,
    generated_at: str,
    config: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    totals = summary.get("totals") or {}
    by_combo = summary.get("by_combo") or []
    by_chat = summary.get("by_chat") or []

    has_tokens = bool(totals.get("total_tokens"))

    if has_tokens:
        summary_cards = _token_summary_cards(totals)
        model_table = _per_model_table(by_combo)
        chat_table = _per_chat_table(by_chat)
        chart_canvas = '<div class="chart-wrap" style="margin-top:24px;"><div class="chart-title">Token Distribution by Model</div><div class="chart-canvas-wrap" style="height:320px;"><canvas id="tokenChart"></canvas></div></div>'
        chart_script = _bar_chart_script(by_combo)
        no_data_msg = ""
    else:
        summary_cards = ""
        model_table = ""
        chat_table = ""
        chart_canvas = ""
        chart_script = ""
        no_data_msg = '<p class="section-intro">No token data available for this run. Re-run with a current version of the harness to capture token usage.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Token Usage · {_esc(run_id)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{_REPORT_FONTS}" rel="stylesheet">
<script src="{_REPORT_CHART_CDN}"></script>
<style>
{_css_block()}
</style>
</head>
<body>
<div class="wrap">
<div class="masthead">
  <div class="masthead-top">
    <span><span class="dot"></span>Token Usage Report</span>
    <span>{_esc(run_id)} &nbsp;·&nbsp; Generated {_esc(generated_at)}</span>
  </div>
  <h1>Token Usage</h1>
</div>
<section id="token-summary" style="padding:32px 40px;">
  <div class="section-head"><span class="section-num">Sec. 1</span><h2>Token Usage</h2></div>
  {no_data_msg}
  {summary_cards}
  {chart_canvas}
  {model_table}
  {chat_table}
</section>
</div>
<script>
{chart_script}
</script>
</body>
</html>"""
