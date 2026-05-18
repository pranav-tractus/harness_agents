"""Magazine-style harness HTML report (charts, cards, sortable leaderboard)."""

from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentRunResult

from harness.artifacts import record_to_row
from harness.report_summary import HarnessVisualStory

_REPORT_CHART_CDN = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"
_REPORT_FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Instrument+Serif:ital@0;1&family=IBM+Plex+Sans:wght@400;500;600;700&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap"
)


def _esc(s: Any) -> str:
    if s is None:
        return ""
    return html.escape(str(s).strip(), quote=False)


def _fmt_pct(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{100.0 * float(rate):.2f}%"


def _fmt_num(x: Any, nd: int = 4) -> str:
    if x is None:
        return "—"
    if isinstance(x, (int, float)):
        return f"{float(x):.{nd}f}"
    return _esc(x)


def _run_label(config: dict[str, Any], summary: dict[str, Any]) -> str:
    if config.get("pipeline"):
        return str(config["pipeline"])
    if config.get("agent"):
        return str(config["agent"])
    agents = summary.get("by_agent") or []
    if len(agents) == 1:
        return str(agents[0].get("agent_id", "harness"))
    return "multi-agent"


def _multi_agent(summary: dict[str, Any]) -> bool:
    agents = summary.get("by_agent") or []
    return len(agents) > 1


def _leaderboard_js_rows(summary: dict[str, Any]) -> list[list[Any]]:
    """Rows for client-side table + chart: [model_label, fs, runs, elapsed, mismatch, match]."""
    multi = _multi_agent(summary)
    out: list[list[Any]] = []
    for r in summary.get("by_combo") or []:
        agent = r.get("agent_id", "")
        model = str(r.get("model_key", ""))
        label = f"{agent} · {model}" if multi else model
        fm = r.get("field_match_rate")
        mm = r.get("avg_mismatch_per_expected_run")
        out.append(
            [
                label,
                int(r.get("few_shot_count", 0)),
                int(r.get("run_count", 0)),
                float(r.get("avg_elapsed_sec") or 0.0),
                float(mm) if mm is not None else 0.0,
                float(fm) if fm is not None else 0.0,
            ]
        )
    return out


def _fs_counts_from_leaderboard(rows: list[list[Any]]) -> list[int]:
    fs_set = {int(r[1]) for r in rows}
    return sorted(fs_set)


def _fs_rollup_cells(summary: dict[str, Any]) -> tuple[list[tuple[int, float | None]], str]:
    """Per few_shot_count: weighted mean field_match by run_count across agent buckets."""
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in summary.get("by_few_shot_count") or []:
        buckets[int(r.get("few_shot_count", 0))].append(r)
    cells: list[tuple[int, float | None]] = []
    for fs in sorted(buckets.keys()):
        xs = buckets[fs]
        w = 0.0
        num = 0.0
        for row in xs:
            n = int(row.get("run_count", 0))
            fm = row.get("field_match_rate")
            if fm is None or n <= 0:
                continue
            w += n
            num += float(fm) * n
        cells.append((fs, (num / w) if w else None))
    if not cells:
        return [], ""
    vals = [v for _, v in cells if v is not None]
    if len(vals) < 2:
        return cells, ""
    lo, hi = min(vals), max(vals)
    spread_bp = (hi - lo) * 10000.0
    note = (
        f"Spread from lowest to highest few-shot bucket: {spread_bp:.0f} basis points "
        f"({100.0 * lo:.2f}%–{100.0 * hi:.2f}% field match)."
    )
    return cells, note


def _dataset_card_flags(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], bool]]:
    rates = [r.get("field_match_rate") for r in rows if r.get("field_match_rate") is not None]
    if not rates:
        return [(r, False) for r in rows]
    mx, mn = max(rates), min(rates)
    out: list[tuple[dict[str, Any], bool]] = []
    for r in rows:
        fm = r.get("field_match_rate")
        broken = (
            fm is not None
            and mn < 0.75
            and (mx - mn) >= 0.20
            and float(fm) <= mn + 1e-9
        )
        out.append((r, broken))
    return out


def _css_block() -> str:
    return r"""
:root {
  --bg: #f5f1e8;
  --bg-card: #faf7ef;
  --bg-elevated: #fffdf6;
  --ink: #1a1a1a;
  --ink-soft: #4a4a4a;
  --ink-mute: #7a7a7a;
  --line: #d6cfbe;
  --line-soft: #e8e2d2;
  --accent: #b8341c;
  --accent-soft: #f4d9d2;
  --warn: #c4761c;
  --good: #2d6b3f;
  --good-soft: #d4e3d8;
  --display: 'Instrument Serif', Georgia, serif;
  --sans: 'IBM Plex Sans', system-ui, sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: var(--sans);
  background: var(--bg);
  color: var(--ink);
  line-height: 1.55;
  font-size: 15px;
  padding: 0;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 0 32px; }
.masthead {
  border-bottom: 2px solid var(--ink);
  padding: 28px 0 20px;
  margin-bottom: 32px;
}
.masthead-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-soft);
  margin-bottom: 14px;
}
.masthead-top .dot {
  display: inline-block;
  width: 6px; height: 6px;
  background: var(--good);
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
h1 {
  font-family: var(--display);
  font-weight: 400;
  font-size: clamp(40px, 5vw, 64px);
  line-height: 1.02;
  letter-spacing: -0.01em;
  margin-bottom: 8px;
}
h1 em { font-style: italic; color: var(--ink-soft); }
.dek {
  font-family: var(--display);
  font-style: italic;
  font-size: 21px;
  color: var(--ink-soft);
  max-width: 720px;
  line-height: 1.4;
}
.findings {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border: 1px solid var(--ink);
  margin: 40px 0;
  background: var(--bg-card);
}
.finding {
  padding: 24px 22px;
  border-right: 1px solid var(--line);
  position: relative;
}
.finding:last-child { border-right: none; }
.finding .label {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin-bottom: 12px;
}
.finding .label.critical { color: var(--accent); }
.finding .label.critical::before { content: "▲ "; }
.finding .big {
  font-family: var(--display);
  font-size: 42px;
  line-height: 1;
  margin-bottom: 8px;
  letter-spacing: -0.01em;
}
.finding .big.bad { color: var(--accent); }
.finding .big.good { color: var(--good); }
.finding .desc {
  font-size: 13.5px;
  color: var(--ink-soft);
  line-height: 1.45;
}
.finding .desc strong { color: var(--ink); }
section { margin: 56px 0; scroll-margin-top: 20px; }
.section-head {
  display: flex;
  align-items: baseline;
  gap: 18px;
  margin-bottom: 6px;
  border-bottom: 1px solid var(--ink);
  padding-bottom: 6px;
}
.section-num {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--accent);
  letter-spacing: 0.1em;
}
h2 {
  font-family: var(--display);
  font-weight: 400;
  font-size: 36px;
  line-height: 1.1;
  letter-spacing: -0.01em;
  flex: 1;
}
.section-intro {
  font-family: var(--display);
  font-style: italic;
  font-size: 17px;
  color: var(--ink-soft);
  margin: 12px 0 24px;
  max-width: 760px;
  line-height: 1.45;
}
.alert {
  background: var(--accent-soft);
  border-left: 3px solid var(--accent);
  padding: 18px 22px;
  margin: 20px 0;
  font-size: 14.5px;
}
.alert strong { color: var(--accent); font-weight: 600; }
.dataset-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin: 24px 0;
}
.dataset-card {
  background: var(--bg-card);
  border: 1px solid var(--line);
  padding: 20px 18px;
  position: relative;
}
.dataset-card.broken {
  background: var(--accent-soft);
  border-color: var(--accent);
}
.dataset-card .name {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 500;
  color: var(--ink-soft);
  margin-bottom: 14px;
  letter-spacing: 0.02em;
}
.dataset-card.broken .name { color: var(--accent); font-weight: 600; }
.dataset-card .score {
  font-family: var(--display);
  font-size: 56px;
  line-height: 1;
  margin-bottom: 4px;
}
.dataset-card.broken .score { color: var(--accent); }
.dataset-card .score-label {
  font-size: 11px;
  color: var(--ink-mute);
  margin-bottom: 14px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.dataset-card .meta {
  display: flex;
  justify-content: space-between;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-soft);
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.dataset-card .bar-track {
  height: 6px;
  background: var(--line-soft);
  margin-bottom: 14px;
  position: relative;
  overflow: hidden;
}
.dataset-card .bar-fill {
  height: 100%;
  background: var(--good);
}
.dataset-card.broken .bar-fill { background: var(--accent); }
.chart-wrap {
  background: var(--bg-card);
  border: 1px solid var(--line);
  padding: 24px;
  margin: 20px 0;
}
.chart-title {
  font-family: var(--display);
  font-size: 22px;
  margin-bottom: 4px;
}
.chart-sub {
  font-size: 13px;
  color: var(--ink-mute);
  margin-bottom: 20px;
}
.chart-canvas-wrap {
  position: relative;
  height: 440px;
}
.table-controls {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.control {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.control label {
  font-family: var(--mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-soft);
}
.control select, .control input {
  font-family: var(--mono);
  font-size: 13px;
  padding: 5px 9px;
  background: var(--bg-elevated);
  border: 1px solid var(--line);
  color: var(--ink);
  border-radius: 0;
}
.control select:focus, .control input:focus {
  outline: none;
  border-color: var(--ink);
}
.table-scroll { overflow-x: auto; border: 1px solid var(--line); background: var(--bg-card); }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
}
thead th {
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--ink);
  text-align: left;
  padding: 11px 14px;
  font-family: var(--mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-soft);
  cursor: pointer;
  user-select: none;
  position: sticky;
  top: 0;
  white-space: nowrap;
}
thead th:hover { color: var(--ink); }
thead th.sort-asc::after { content: " ↑"; color: var(--accent); }
thead th.sort-desc::after { content: " ↓"; color: var(--accent); }
tbody td {
  padding: 9px 14px;
  border-bottom: 1px solid var(--line-soft);
  font-family: var(--mono);
  font-size: 12.5px;
}
tbody td:first-child { font-family: var(--sans); font-weight: 500; }
tbody tr:hover td { background: var(--bg-elevated); }
tbody tr.top-quartile td:first-child { color: var(--good); }
tbody tr.top-quartile td:first-child::before { content: "● "; }
tbody tr.bottom-quartile td:first-child { color: var(--accent); }
tbody tr.bottom-quartile td:first-child::before { content: "○ "; }
.numeric { text-align: right; }
.match-cell { position: relative; }
.match-bar {
  display: inline-block;
  width: 50px;
  height: 5px;
  background: var(--line-soft);
  margin-right: 8px;
  vertical-align: middle;
  position: relative;
}
.match-bar::after {
  content: "";
  position: absolute;
  inset: 0;
  width: var(--w);
  background: var(--good);
}
.match-bar.low::after { background: var(--accent); }
.match-bar.mid::after { background: var(--warn); }
.fs-rollup {
  background: var(--bg-card);
  border: 1px solid var(--line);
  padding: 24px;
  margin: 20px 0;
}
.fs-rollup-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 10px;
  margin-top: 18px;
}
.fs-cell {
  text-align: center;
  padding: 14px 6px;
  background: var(--bg-elevated);
  border: 1px solid var(--line-soft);
}
.fs-cell .fs-label {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-mute);
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}
.fs-cell .fs-val {
  font-family: var(--display);
  font-size: 24px;
}
.fs-takeaway {
  margin-top: 18px;
  font-family: var(--display);
  font-style: italic;
  font-size: 16px;
  color: var(--ink-soft);
}
details {
  border: 1px solid var(--line);
  background: var(--bg-card);
  margin: 20px 0;
}
details summary {
  padding: 14px 22px;
  cursor: pointer;
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-soft);
  list-style: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
details summary::-webkit-details-marker { display: none; }
details summary::after {
  content: "+";
  font-family: var(--display);
  font-size: 22px;
  color: var(--ink-soft);
}
details[open] summary::after { content: "−"; }
details summary:hover { color: var(--ink); }
details .details-content { padding: 0 22px 22px; }
details pre {
  font-family: var(--mono);
  font-size: 11.5px;
  background: var(--bg-elevated);
  border: 1px solid var(--line-soft);
  padding: 16px;
  overflow-x: auto;
  line-height: 1.5;
}
.action-grid {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 14px 18px;
  margin-top: 20px;
}
.action-num {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--accent);
  padding-top: 3px;
}
.action-title {
  font-family: var(--display);
  font-size: 19px;
  font-weight: 400;
}
.action-body { color: var(--ink-soft); margin-top: 4px; }
footer {
  margin-top: 80px;
  padding: 24px 0 60px;
  border-top: 1px solid var(--line);
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-mute);
  letter-spacing: 0.04em;
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
@media (max-width: 820px) {
  .wrap { padding: 0 18px; }
  .findings { grid-template-columns: 1fr; }
  .finding { border-right: none; border-bottom: 1px solid var(--line); }
  .finding:last-child { border-bottom: none; }
  .dataset-grid { grid-template-columns: 1fr; }
  h1 { font-size: 36px; }
  h2 { font-size: 28px; }
  .chart-canvas-wrap { height: 360px; }
}
"""


def _rich_text_to_html(s: str) -> str:
    """Escape then turn paired **segments** into <strong> (LLM + heuristic copy)."""
    parts = html.escape(s.strip(), quote=False).split("**")
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(f"<strong>{part}</strong>")
        else:
            out.append(part)
    return "".join(out)


def _finding_tone_class(tone: str) -> str:
    if tone == "good":
        return "good"
    if tone == "bad":
        return "bad"
    return ""


def _finding_block(story: HarnessVisualStory, idx: int) -> str:
    f = story.findings[idx]
    lab_cls = "label critical" if f.label_critical else "label"
    big_cls = "big " + _finding_tone_class(f.headline_tone)
    desc_html = _rich_text_to_html(f.description)
    return (
        f'<div class="finding">'
        f'<div class="{lab_cls}">{_esc(f.label)}</div>'
        f'<div class="{big_cls.strip()}">{_esc(f.headline)}</div>'
        f'<div class="desc">{desc_html}</div>'
        f"</div>"
    )


def _actions_section(story: HarnessVisualStory) -> str:
    parts = []
    for i, step in enumerate(story.next_steps[:8], start=1):
        parts.append(f'<div class="action-num">{i:02d}</div><div>')
        parts.append(f'<div class="action-title">{_esc(step.title)}</div>')
        parts.append(f'<div class="action-body">{_esc(step.detail)}</div></div>')
    inner = "".join(parts) if parts else "<p>No follow-up steps.</p>"
    return (
        f'<section id="actions">'
        f'<div class="section-head"><span class="section-num">Sec. 05</span>'
        f"<h2>What to check next</h2></div>"
        f'<p class="section-intro">{_esc(story.actions_section_intro)}</p>'
        f'<div class="action-grid">{inner}</div></section>'
    )


def _mismatch_details(records: list[AgentRunResult]) -> str:
    rows = [record_to_row(r) for r in records]
    mismatched = [r for r in rows if r.get("mismatch_count", 0) > 0]
    mismatched.sort(key=lambda r: (-r["mismatch_count"], r.get("source_filename", "")))
    body_rows = []
    for r in mismatched[:80]:
        sample = json.dumps(r.get("mismatches", [])[:5], indent=2, ensure_ascii=False)
        body_rows.append(
            "<tr>"
            f"<td>{_esc(r.get('agent_id'))}</td>"
            f"<td>{_esc(r.get('source_filename'))}</td>"
            f"<td>{_esc(r.get('model_key'))}</td>"
            f"<td>{_esc(r.get('few_shot_count'))}</td>"
            f"<td>{_esc(r.get('mismatch_count'))}</td>"
            f"<td><pre>{_esc(sample)}</pre></td>"
            "</tr>"
        )
    if not body_rows:
        return "<p>No mismatches in this run.</p>"
    head = "<thead><tr><th>Agent</th><th>Chat</th><th>Model</th><th>FS</th><th>Mismatches</th><th>Sample</th></tr></thead>"
    return f"<div class='table-scroll'><table>{head}<tbody>{''.join(body_rows)}</tbody></table></div>"


def _interactive_script(multi: bool, data_json: str) -> str:
    """Client-side leaderboard + Chart.js; JSON is injected (must be valid JS literal)."""
    multi_js = "true" if multi else "false"
    tmpl = r"""
const MULTI_AGENT = __MULTI__;
const DATA = __DATA__;
const rows = DATA.map((row) => {
  if (MULTI_AGENT) {
    const parts = row[0].split(" · ");
    const agent = parts[0] || "";
    const model = parts.length > 1 ? parts.slice(1).join(" · ") : row[0];
    return { agent, model, fs: row[1], runs: row[2], elapsed: row[3], mismatch: row[4], match: row[5] };
  }
  return { agent: "", model: row[0], fs: row[1], runs: row[2], elapsed: row[3], mismatch: row[4], match: row[5] };
});
const sortedMatches = [...rows.map((r) => r.match)].sort((a, b) => b - a);
const topQuartile = sortedMatches.length ? sortedMatches[Math.floor(rows.length * 0.25)] : 0;
const bottomQuartile = sortedMatches.length ? sortedMatches[Math.floor(rows.length * 0.75)] : 0;
const modelFilter = document.getElementById("modelFilter");
const models = [...new Set(rows.map((r) => r.model))].sort();
models.forEach((m) => {
  const opt = document.createElement("option");
  opt.value = m;
  opt.textContent = m;
  modelFilter.appendChild(opt);
});
let state = { sort: "match", dir: "desc", fs: "all", model: "all", search: "" };
function matchBarClass(v) {
  if (v < 0.78) return "low";
  if (v < 0.85) return "mid";
  return "";
}
function render() {
  let filtered = rows.filter((r) => {
    if (state.fs !== "all" && r.fs !== Number(state.fs)) return false;
    if (state.model !== "all" && r.model !== state.model) return false;
    if (state.search) {
      const q = state.search.toLowerCase();
      const blob = (r.agent + " " + r.model).toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  });
  filtered.sort((a, b) => {
    const av = a[state.sort];
    const bv = b[state.sort];
    if (typeof av === "string") {
      return state.dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    }
    return state.dir === "asc" ? av - bv : bv - av;
  });
  const tbody = document.getElementById("leaderboard-body");
  const agentCell = (r) => (MULTI_AGENT ? `<td>${r.agent}</td>` : "");
  tbody.innerHTML = filtered
    .map((r) => {
      const cls =
        r.match >= topQuartile ? "top-quartile" : r.match <= bottomQuartile ? "bottom-quartile" : "";
      const barCls = matchBarClass(r.match);
      const barW = Math.round(r.match * 100) + "%";
      return (
        `<tr class="${cls}">${agentCell(r)}<td>${r.model}</td>` +
        `<td class="numeric">${r.fs}</td>` +
        `<td class="numeric">${r.runs}</td>` +
        `<td class="numeric">${r.elapsed.toFixed(2)}</td>` +
        `<td class="numeric">${r.mismatch.toFixed(2)}</td>` +
        `<td class="numeric match-cell"><span class="match-bar ${barCls}" style="--w:${barW}"></span>${(r.match * 100).toFixed(2)}%</td></tr>`
      );
    })
    .join("");
  document.getElementById("rowCount").textContent = `${filtered.length} of ${rows.length} rows`;
  document.querySelectorAll("thead th").forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.sort === state.sort) {
      th.classList.add(state.dir === "asc" ? "sort-asc" : "sort-desc");
    }
  });
}
document.querySelectorAll("thead th").forEach((th) => {
  th.addEventListener("click", () => {
    const k = th.dataset.sort;
    if (state.sort === k) {
      state.dir = state.dir === "asc" ? "desc" : "asc";
    } else {
      state.sort = k;
      state.dir = th.dataset.type === "num" ? "desc" : "asc";
    }
    render();
  });
});
document.getElementById("fsFilter").addEventListener("change", (e) => {
  state.fs = e.target.value;
  render();
});
document.getElementById("modelFilter").addEventListener("change", (e) => {
  state.model = e.target.value;
  render();
});
document.getElementById("search").addEventListener("input", (e) => {
  state.search = e.target.value;
  render();
});
render();
const modelAgg = {};
rows.forEach((r) => {
  const k = r.model;
  if (!modelAgg[k]) modelAgg[k] = { elapsed: [], match: [], mismatch: [] };
  modelAgg[k].elapsed.push(r.elapsed);
  modelAgg[k].match.push(r.match);
  modelAgg[k].mismatch.push(r.mismatch);
});
const avg = (arr) => arr.reduce((a, b) => a + b, 0) / arr.length;
const modelPoints = Object.entries(modelAgg).map(([model, d]) => ({
  model,
  x: avg(d.elapsed),
  y: avg(d.match) * 100,
  r: 6 + avg(d.mismatch) * 1.5,
}));
const colorFor = (model) => {
  if (model.startsWith("sonnet") || model.startsWith("opus")) return "#2d6b3f";
  if (model.startsWith("openai:4")) return "#1a5490";
  if (model.startsWith("openai")) return "#7a8aa8";
  if (model.startsWith("gemini")) return "#b8341c";
  return "#7a7a7a";
};
if (modelPoints.length) {
  const ctx = document.getElementById("frontierChart").getContext("2d");
  new Chart(ctx, {
    type: "bubble",
    data: {
      datasets: modelPoints.map((p) => ({
        label: p.model,
        data: [{ x: p.x, y: p.y, r: p.r, model: p.model }],
        backgroundColor: colorFor(p.model) + "cc",
        borderColor: colorFor(p.model),
        borderWidth: 1.5,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "right",
          labels: {
            font: { family: "'JetBrains Mono', monospace", size: 11 },
            color: "#4a4a4a",
            boxWidth: 10,
            boxHeight: 10,
            padding: 8,
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const d = ctx.raw;
              return `${d.model}: ${d.y.toFixed(1)}% match, ${d.x.toFixed(2)}s avg`;
            },
          },
          bodyFont: { family: "'JetBrains Mono', monospace", size: 12 },
          titleFont: { family: "'IBM Plex Sans', sans-serif" },
        },
      },
      scales: {
        x: {
          type: "logarithmic",
          title: {
            display: true,
            text: "Avg latency (s, log scale)",
            font: { family: "'JetBrains Mono', monospace", size: 11, weight: 500 },
            color: "#4a4a4a",
          },
          ticks: {
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            color: "#7a7a7a",
            callback: (v) => v + "s",
          },
          grid: { color: "#e8e2d2" },
        },
        y: {
          title: {
            display: true,
            text: "Field match (%)",
            font: { family: "'JetBrains Mono', monospace", size: 11, weight: 500 },
            color: "#4a4a4a",
          },
          ticks: {
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            color: "#7a7a7a",
            callback: (v) => v + "%",
          },
          grid: { color: "#e8e2d2" },
        },
      },
    },
  });
}
"""
    return tmpl.replace("__MULTI__", multi_js).replace("__DATA__", data_json)


def render_dashboard_report_html(
    run_id: str,
    generated_at_utc: str,
    config: dict[str, Any],
    summary: dict[str, Any],
    records: list[AgentRunResult],
    story: HarnessVisualStory,
) -> str:
    totals = summary.get("totals") or {}
    run_count = int(totals.get("run_count") or 0)
    success_rate = totals.get("success_rate")
    field_match = totals.get("field_match_rate")
    label = _run_label(config, summary)

    h1_em = story.headline_emphasis.strip()
    h1_html = f"{_esc(story.headline_start)}" + (f" <em>{_esc(h1_em)}</em>" if h1_em else "")

    findings_html = "".join(_finding_block(story, i) for i in range(3))

    lb_rows = _leaderboard_js_rows(summary)
    data_json = json.dumps(lb_rows, ensure_ascii=False)
    fs_cells, fs_spread = _fs_rollup_cells(summary)
    fs_takeaway = story.fewshot_takeaway.strip() or fs_spread
    fs_opts = "".join(f'<option value="{fs}">{fs}</option>' for fs in _fs_counts_from_leaderboard(lb_rows))
    if fs_opts:
        fs_opts = '<option value="all">All</option>' + fs_opts
    else:
        fs_opts = '<option value="all">All</option>'

    multi = _multi_agent(summary)
    th_agent = "<th data-sort=\"agent\" data-type=\"str\">Agent</th>" if multi else ""

    dataset_rows = summary.get("by_dataset") or []
    cards_html_parts = []
    for r, broken in _dataset_card_flags(dataset_rows):
        agent = r.get("agent_id", "")
        ds = r.get("dataset_id", "")
        name = f"{agent} · {ds}" if multi else str(ds)
        fm = r.get("field_match_rate")
        pct = 100.0 * float(fm) if fm is not None else None
        width = f"{pct:.1f}%" if pct is not None else "0%"
        mm = r.get("avg_mismatch_per_expected_run")
        card_cls = "dataset-card broken" if broken else "dataset-card"
        sub = "Field match — investigate" if broken else "Field match"
        cards_html_parts.append(
            f'<div class="{card_cls}">'
            f'<div class="name">{_esc(name)}</div>'
            f'<div class="score">{_fmt_pct(fm)}</div>'
            f'<div class="score-label">{_esc(sub)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width}"></div></div>'
            f'<div class="meta"><span>{int(r.get("run_count", 0))} runs</span>'
            f"<span>{_fmt_num(mm, 2)} mismatch</span></div></div>"
        )
    grid_inner = "".join(cards_html_parts) if cards_html_parts else "<p>No dataset breakdown.</p>"

    alert_html = ""
    if story.alert_lead.strip() or story.alert_body.strip():
        alert_html = (
            f'<div class="alert"><strong>{_esc(story.alert_lead)}</strong> {_esc(story.alert_body)}</div>'
        )

    fs_cells_html = "".join(
        f'<div class="fs-cell"><div class="fs-label">FS {fs}</div>'
        f'<div class="fs-val">{_fmt_pct(fm)}</div></div>'
        for fs, fm in fs_cells
    )
    fs_takeaway_html = f'<p class="fs-takeaway">{_esc(fs_takeaway)}</p>' if fs_takeaway else ""

    cfg_pre = _esc(json.dumps(config, indent=2, ensure_ascii=False))
    script = _interactive_script(multi, data_json)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Harness Run {_esc(run_id)} — {_esc(label)}</title>
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
    <span><span class="dot"></span>Harness Run · {_esc(label)}</span>
    <span>{_esc(run_id)} &nbsp;·&nbsp; {run_count:,} runs &nbsp;·&nbsp; Generated {_esc(generated_at_utc)}</span>
  </div>
  <h1>{h1_html}</h1>
  <p class="dek">{_esc(story.dek)}</p>
</div>
<div class="findings">
{findings_html}
</div>
<section id="datasets">
  <div class="section-head"><span class="section-num">Sec. 01</span><h2>Results by dataset</h2></div>
  <p class="section-intro">{_esc(story.dataset_section_intro)}</p>
  {alert_html}
  <div class="dataset-grid">{grid_inner}</div>
</section>
<section id="frontier">
  <div class="section-head"><span class="section-num">Sec. 02</span><h2>Quality vs. speed</h2></div>
  <p class="section-intro">{_esc(story.frontier_section_intro)}</p>
  <div class="chart-wrap">
    <div class="chart-title">Model frontier</div>
    <div class="chart-sub">Each bubble is one row in the table below (model × few-shot). Bubble size reflects mismatch load.</div>
    <div class="chart-canvas-wrap"><canvas id="frontierChart"></canvas></div>
  </div>
</section>
<section id="leaderboard">
  <div class="section-head"><span class="section-num">Sec. 03</span><h2>Leaderboard</h2></div>
  <p class="section-intro">{_esc(story.leaderboard_section_intro)}</p>
  <div class="table-controls">
    <div class="control"><label for="fsFilter">FS Count</label>
      <select id="fsFilter">{fs_opts}</select></div>
    <div class="control"><label for="modelFilter">Model</label>
      <select id="modelFilter"><option value="all">All</option></select></div>
    <div class="control"><label for="search">Search</label>
      <input id="search" type="text" placeholder="filter…" style="width:180px"></div>
    <div class="control" style="margin-left:auto;color:var(--ink-mute);font-family:var(--mono);font-size:11px;">
      <span id="rowCount">0 rows</span></div>
  </div>
  <div class="table-scroll">
    <table id="leaderboard-table">
      <thead><tr>
        {th_agent}
        <th data-sort="model" data-type="str">Model</th>
        <th data-sort="fs" data-type="num" class="numeric">FS</th>
        <th data-sort="runs" data-type="num" class="numeric">Runs</th>
        <th data-sort="elapsed" data-type="num" class="numeric">Avg s</th>
        <th data-sort="mismatch" data-type="num" class="numeric">Mismatch</th>
        <th data-sort="match" data-type="num" class="numeric sort-desc">Field match</th>
      </tr></thead>
      <tbody id="leaderboard-body"></tbody>
    </table>
  </div>
</section>
<section id="fewshot">
  <div class="section-head"><span class="section-num">Sec. 04</span><h2>Few-shot sweep</h2></div>
  <p class="section-intro">{_esc(story.fewshot_section_intro)}</p>
  <div class="fs-rollup">
    <div class="fs-rollup-grid">{fs_cells_html}</div>
    {fs_takeaway_html}
  </div>
</section>
{_actions_section(story)}
<details>
  <summary>Run configuration (JSON)</summary>
  <div class="details-content"><pre>{cfg_pre}</pre></div>
</details>
<details>
  <summary>How to read these numbers</summary>
  <div class="details-content">
    <div style="font-size:13.5px;color:var(--ink-soft);line-height:1.7;">
      <p style="margin-bottom:10px;"><strong style="color:var(--ink);font-family:var(--mono);font-size:12px;">SUCCESS RATE</strong>
      — Share of runs that finished without a harness or HTTP error. High success means the run was stable; it does not prove the answers matched the reference.</p>
      <p style="margin-bottom:10px;"><strong style="color:var(--ink);font-family:var(--mono);font-size:12px;">AVG ELAPSED (S)</strong>
      — Average wall time per run in that bucket. Useful for latency comparisons.</p>
      <p style="margin-bottom:10px;"><strong style="color:var(--ink);font-family:var(--mono);font-size:12px;">AVG MISMATCH / EXPECTED RUN</strong>
      — Average count of fields that differed from the golden JSON when a reference existed. Lower is better.</p>
      <p><strong style="color:var(--ink);font-family:var(--mono);font-size:12px;">FIELD MATCH</strong>
      — Fraction of compared fields that matched the golden output across runs in that bucket. Higher is better.</p>
    </div>
  </div>
</details>
<details>
  <summary>Sample mismatches (up to 80 rows)</summary>
  <div class="details-content">{_mismatch_details(records)}</div>
</details>
<footer>
  <span>{_esc(label)} · {_esc(run_id)}</span>
  <span>{run_count:,} runs · {_fmt_pct(success_rate)} success · {_fmt_pct(field_match)} field match</span>
</footer>
</div>
<script>
{script}
</script>
</body>
</html>
"""


def dashboard_generated_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
