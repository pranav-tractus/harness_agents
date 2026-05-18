"""LLM narrative for harness result briefs (Gemini 2.5 Pro via ``call_llm``)."""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import textwrap
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.llm_client import call_llm

logger = logging.getLogger(__name__)

DEFAULT_SUMMARY_MODEL = "gemini:gemini-2.5-pro"
DEFAULT_VISUAL_STORY_MODEL = "sonnet-4-5"

AI_SUMMARY_START = "<!-- harness-ai-summary-start -->"
AI_SUMMARY_END = "<!-- harness-ai-summary-end -->"


class VisualFinding(BaseModel):
    label: str = Field(..., description="Short uppercase-style label, e.g. Overall quality")
    label_critical: bool = Field(False, description="True if this finding flags a serious issue")
    headline: str = Field(..., description="Large headline stat or model name, a few words")
    headline_tone: Literal["good", "bad", "neutral"] = Field(
        "neutral",
        description="Visual tone for the headline number",
    )
    description: str = Field(
        ...,
        description="One or two sentences, plain text only (no HTML). Optional **bold** phrases.",
    )


class NextStep(BaseModel):
    title: str = Field(..., description="Short imperative title for a stakeholder")
    detail: str = Field(..., description="Plain text; what to do and why")


class HarnessVisualStory(BaseModel):
    """Editorial layer for dashboard-style report.html (filled by Claude Sonnet or heuristics)."""

    headline_start: str = Field(..., description="Main title; conversational, non-technical")
    headline_emphasis: str = Field(
        default="",
        description="Optional second clause rendered in italics after the start",
    )
    dek: str = Field(..., description="One sentence deck under the title")
    findings: list[VisualFinding] = Field(default_factory=list)
    dataset_section_intro: str = Field(..., description="Intro for dataset cards")
    alert_lead: str = Field(default="", description="Bold lead-in for alert box, or empty")
    alert_body: str = Field(default="", description="Rest of alert sentence(s), or empty")
    frontier_section_intro: str = Field(..., description="Intro for quality vs speed chart")
    leaderboard_section_intro: str = Field(..., description="Intro for sortable leaderboard")
    fewshot_section_intro: str = Field(..., description="Intro for few-shot rollup")
    fewshot_takeaway: str = Field(
        default="",
        description="Italic takeaway under few-shot cells; empty to use numeric spread fallback",
    )
    actions_section_intro: str = Field(..., description="Intro for next steps list")
    next_steps: list[NextStep] = Field(default_factory=list)


VISUAL_STORY_SYSTEM = textwrap.dedent(
    """\
    You write the editorial layer for an HTML benchmark report aimed at executives and PMs
    who are not engineers. Use ONLY numbers and facts present in the JSON brief and the
    companion machine summary; never invent models, datasets, or metrics.

    Voice: confident, concise, plain English. Avoid jargon unless the brief already uses it.
    Prefer "field match" over acronyms. If leaderboard_truncated is true, say conclusions are
    tentative because only the worst rows were shown to you.

    findings must be exactly three items. next_steps: 3 to 6 items, highest priority first.
    description fields: plain text; you may use **double asterisks** sparingly for two or three
    key phrases per finding (they become bold in the report).

    headline_emphasis may be empty; if used, it completes the thought in headline_start
    (the emphasis renders in italics).
    """
)


def _avg_field_match_by_model(summary: dict[str, Any]) -> list[tuple[str, float]]:
    buckets: dict[str, list[tuple[float, int]]] = {}
    for r in summary.get("by_combo") or []:
        mk = str(r.get("model_key", ""))
        fm = r.get("field_match_rate")
        n = int(r.get("run_count", 0))
        if fm is None or n <= 0:
            continue
        buckets.setdefault(mk, []).append((float(fm), n))
    out: list[tuple[str, float]] = []
    for mk, pairs in buckets.items():
        w = sum(n for _, n in pairs)
        if w <= 0:
            continue
        avg = sum(f * n for f, n in pairs) / w
        out.append((mk, avg))
    out.sort(key=lambda x: -x[1])
    return out


def _dataset_outlier(summary: dict[str, Any]) -> tuple[str | None, float | None, float | None]:
    """(dataset_id, its field_match, spread) if an outlier exists."""
    rows = summary.get("by_dataset") or []
    rates = [(r, r.get("field_match_rate")) for r in rows if r.get("field_match_rate") is not None]
    if len(rates) < 2:
        return None, None, None
    vals = [float(fm) for _, fm in rates]
    lo, hi = min(vals), max(vals)
    if hi - lo < 0.18:
        return None, None, hi - lo
    worst = min(rates, key=lambda x: float(x[1]))
    return str(worst[0].get("dataset_id")), float(worst[1]), hi - lo


def heuristic_visual_story(
    brief: dict[str, Any],
    summary: dict[str, Any],
    config: dict[str, Any],
) -> HarnessVisualStory:
    """Deterministic copy when the LLM is unavailable or skipped."""
    totals = summary.get("totals") or {}
    runs = int(totals.get("run_count") or 0)
    fm = totals.get("field_match_rate")
    sr = totals.get("success_rate")
    label = str(config.get("agent") or config.get("pipeline") or "harness")
    by_model = _avg_field_match_by_model(summary)
    best_model, best_fm = by_model[0] if by_model else ("—", None)
    out_ds, out_fm, spread = _dataset_outlier(summary)
    outlier_note = ""
    if out_ds and out_fm is not None:
        outlier_note = (
            f"The {out_ds} bucket is much lower than the others (~{100.0 * out_fm:.0f}% field match); "
            "treat it as a **data or evaluation** signal until spot-checked."
        )
    headline_em = ""
    if out_ds and out_fm is not None and spread and spread >= 0.22:
        headline_start = "One dataset is dragging the average."
        headline_em = "The rest look fine."
    else:
        headline_start = "Here is how this benchmark run shook out."
    dek = (
        f"{runs:,} harness runs for **{label}**. "
        f"Overall field match is **{_fmt_story_pct(fm)}** with **{_fmt_story_pct(sr)}** run success."
    )
    crit = bool(out_ds and out_fm is not None and spread and spread >= 0.22)
    f1 = VisualFinding(
        label="Dataset check" if crit else "Overall",
        label_critical=crit,
        headline=_fmt_story_pct(out_fm) if out_fm is not None else _fmt_story_pct(fm),
        headline_tone="bad" if crit else "neutral",
        description=outlier_note
        or "Scan the dataset cards below; uneven bars usually mean mixed data quality or evaluation drift.",
    )
    f2 = VisualFinding(
        label="Strongest model (avg across few-shot)",
        label_critical=False,
        headline=best_model[:24] + ("…" if len(best_model) > 24 else ""),
        headline_tone="good" if best_fm and best_fm >= 0.75 else "neutral",
        description=(
            f"By weighted field match across all few-shot counts, **{best_model}** leads at "
            f"**{_fmt_story_pct(best_fm)}**. Compare the leaderboard when filtering to a single few-shot count."
            if best_fm is not None
            else "Not enough expected-output rows to rank models by field match."
        ),
    )
    elapsed = totals.get("avg_elapsed_sec")
    f3 = VisualFinding(
        label="Speed",
        label_critical=False,
        headline=f"{float(elapsed):.1f}s" if isinstance(elapsed, (int, float)) else "—",
        headline_tone="neutral",
        description=(
            "Average wall time per run across the whole batch (latency proxy only — add cost to compare dollars)."
            if isinstance(elapsed, (int, float))
            else "Latency averages were not available for this rollup."
        ),
    )
    alert_lead, alert_body = "", ""
    if crit and out_ds:
        alert_lead = "Investigate before swapping models."
        alert_body = (
            f"Every model bucket inherits the same weak **{out_ds}** signal in the aggregate. "
            "Fix data or goldens first; model changes may not move the headline much."
        )
    steps = [
        NextStep(
            title="Confirm what “field match” covers",
            detail="Open the glossary under this page and align stakeholders on success vs quality metrics.",
        ),
        NextStep(
            title="Split conclusions by dataset",
            detail="If one dataset is an outlier, report model winners per dataset instead of one blended score.",
        ),
        NextStep(
            title="Spot-check the worst chats",
            detail="Expand “Sample mismatches” and compare agent JSON to the golden reference for a handful of rows.",
        ),
    ]
    if out_ds:
        steps.insert(
            0,
            NextStep(
                title=f"Audit the {out_ds} dataset",
                detail="Compare outputs to goldens; schema drift or bad references mimic low model quality.",
            ),
        )
    return HarnessVisualStory(
        headline_start=headline_start,
        headline_emphasis=headline_em,
        dek=dek,
        findings=[f1, f2, f3],
        dataset_section_intro=(
            "Each card is one dataset bucket: height is field match, width of the bar is the same. "
            "Use this view to see whether the story is uniform or split."
        ),
        alert_lead=alert_lead,
        alert_body=alert_body,
        frontier_section_intro=(
            "Bubble chart: horizontal axis is average latency (log scale), vertical axis is field match. "
            "Upper-left is ideal; bubble size encodes mismatch pressure."
        ),
        leaderboard_section_intro=(
            "Sort any column, filter few-shot count, and type in the search box. "
            "Green and red rows highlight top and bottom quartiles of field match in the current filter."
        ),
        fewshot_section_intro=(
            "Cells aggregate every agent row in the run for each few-shot count (weighted by runs). "
            "Flat rows suggest few-shot is not the lever to pull."
        ),
        fewshot_takeaway="",
        actions_section_intro="Practical follow-ups in priority order:",
        next_steps=steps[:6],
    )


def _fmt_story_pct(x: Any) -> str:
    if x is None:
        return "n/a"
    return f"{100.0 * float(x):.1f}%"


def summarize_visual_story(
    brief: dict[str, Any],
    *,
    model_key: str = DEFAULT_VISUAL_STORY_MODEL,
) -> HarnessVisualStory:
    """Claude Sonnet on Bedrock (default ``sonnet-4-5``) for narrative HTML layer."""
    payload = json.dumps(brief, indent=2, ensure_ascii=False)
    prompt = (
        "Machine summary (trust these numbers for consistency checks):\n"
        + json.dumps(
            {
                "totals": (brief.get("totals_from_aggregate") or {}),
                "datasets": [
                    {
                        "dataset_id": r.get("dataset_id"),
                        "field_match_rate": r.get("field_match_rate"),
                        "run_count": r.get("run_count"),
                    }
                    for r in (brief.get("_by_dataset") or [])
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n\nHarness brief (JSON):\n"
        + payload
    )
    return call_llm(
        prompt,
        HarnessVisualStory,
        model_key=model_key,
        system_prompt=VISUAL_STORY_SYSTEM,
    )


def _story_is_complete(s: HarnessVisualStory) -> bool:
    return len(s.findings) == 3 and len(s.next_steps) >= 3


def summarize_visual_story_safe(
    brief: dict[str, Any],
    summary: dict[str, Any],
    config: dict[str, Any],
    *,
    model_key: str = DEFAULT_VISUAL_STORY_MODEL,
    use_llm: bool = True,
) -> HarnessVisualStory:
    """LLM story with Sonnet fallback to :func:`heuristic_visual_story`."""
    base = heuristic_visual_story(brief, summary, config)
    if not use_llm:
        return base
    brief = dict(brief)
    brief["_by_dataset"] = summary.get("by_dataset") or []
    try:
        out = summarize_visual_story(brief, model_key=model_key)
        if not _story_is_complete(out):
            logger.warning("Harness visual story incomplete; using heuristic copy.")
            return base
        return out
    except Exception as exc:
        logger.warning("Harness visual story LLM failed (%s); using heuristic copy.", exc)
        return base


class HarnessReportNarrative(BaseModel):
    """Structured interpretation of a harness results brief."""

    metric_cheatsheet: str = Field(
        ...,
        description="Short prose: what Success rate, Avg runtime, Mismatch stdev, "
        "avg mismatch/expected run, and field match mean in this harness.",
    )
    overall_assessment: str = Field(..., description="One short paragraph.")
    what_is_working: list[str] = Field(default_factory=list, description="Bullet points.")
    what_is_not_working: list[str] = Field(default_factory=list, description="Bullet points.")
    leaderboard_highlights: str = Field(
        ...,
        description="Compare models/agents/fs_count; do not restate every table cell.",
    )


SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are a senior ML engineer interpreting agent harness benchmark results.
    Rules:
    - Use ONLY the JSON brief provided by the user. Do not invent runs, models, or numbers.
    - If a field is null or missing, say it is unavailable rather than guessing.
    - Success (HTTP/agent completed) is not the same as low mismatch vs expected JSON.
    - Mismatch stdev (when present) is across individual runs with expected output, not across leaderboard rows.
    - Be actionable: call out the strongest and weakest (agent, model, fs_count) combos when the data supports it.
    - If leaderboard_truncated is true, note that only the worst-N combo rows by mismatch were shown.
    """
)

USER_PROMPT_PREFIX = textwrap.dedent(
    """\
    Glossary:
    - expected_available: golden expected output existed for this run; mismatch metrics apply.
    - mismatch_count: fields differing vs expected for that run.
    - field_match_rate (combo-level): 1 - total_mismatches/total_compared_fields across runs in that bucket.
    - fs_count: few-shot example count for that variant.

    Brief (JSON):
    """
)


def summarize_brief(
    brief: dict[str, Any],
    *,
    model_key: str = DEFAULT_SUMMARY_MODEL,
) -> HarnessReportNarrative:
    """Call Gemini 2.5 Pro (default) with structured output."""
    payload = json.dumps(brief, indent=2, ensure_ascii=False)
    prompt = USER_PROMPT_PREFIX + payload
    return call_llm(
        prompt,
        HarnessReportNarrative,
        model_key=model_key,
        system_prompt=SYSTEM_PROMPT,
    )


def narrative_to_markdown(run_label: str, narrative: HarnessReportNarrative) -> str:
    """Markdown for Streamlit / logs (dashboard)."""
    lines = [
        f"# Harness report summary · {run_label}",
        "",
        "## Overall",
        "",
        narrative.overall_assessment.strip(),
        "",
        "## What the numbers mean",
        "",
        narrative.metric_cheatsheet.strip(),
        "",
        "## Leaderboard highlights",
        "",
        narrative.leaderboard_highlights.strip(),
        "",
        "## What looks healthy",
        "",
    ]
    for item in narrative.what_is_working:
        lines.append(f"- {item}")
    if not narrative.what_is_working:
        lines.append("- _(none called out)_")
    lines.extend(["", "## What needs attention", ""])
    for item in narrative.what_is_not_working:
        lines.append(f"- {item}")
    if not narrative.what_is_not_working:
        lines.append("- _(none called out)_")
    lines.append("")
    return "\n".join(lines)


def _esc(s: str) -> str:
    return html.escape(s.strip(), quote=False)


def narrative_to_html_fragment(run_label: str, narrative: HarnessReportNarrative) -> str:
    """Safe HTML block inserted at the top of ``report.html``."""
    box_style = (
        "background:#f0fdf4;border:1px solid #86efac;padding:16px 20px;"
        "margin-bottom:24px;border-radius:8px;color:#14532d;"
    )
    h2_style = "margin-top:0;color:#166534;"
    h3_style = "margin:14px 0 6px;font-size:15px;color:#15803d;"

    def bullets(items: list[str], empty: str) -> str:
        if not items:
            return f"<p><em>{_esc(empty)}</em></p>"
        lis = "".join(f"<li>{_esc(x)}</li>" for x in items)
        return f"<ul style='margin:8px 0;padding-left:22px;'>{lis}</ul>"

    inner = (
        f'<section id="harness-ai-summary" style="{box_style}">'
        f'<h2 style="{h2_style}">Summary {_esc(run_label)}</h2>'
        f'<h3 style="{h3_style}">Overall</h3>'
        f"<p>{_esc(narrative.overall_assessment)}</p>"
        f'<h3 style="{h3_style}">What the numbers mean</h3>'
        f"<p>{_esc(narrative.metric_cheatsheet)}</p>"
        f'<h3 style="{h3_style}">Leaderboard highlights</h3>'
        f"<p>{_esc(narrative.leaderboard_highlights)}</p>"
        f'<h3 style="{h3_style}">What looks healthy</h3>'
        f"{bullets(narrative.what_is_working, 'none called out')}"
        f'<h3 style="{h3_style}">What needs attention</h3>'
        f"{bullets(narrative.what_is_not_working, 'none called out')}"
        "</section>"
    )
    return f"{AI_SUMMARY_START}\n{inner}\n{AI_SUMMARY_END}\n"


def strip_ai_summary_html(html_text: str) -> str:
    """Remove a previously injected AI summary so re-runs do not duplicate."""
    pattern = re.compile(
        re.escape(AI_SUMMARY_START) + r".*?" + re.escape(AI_SUMMARY_END) + r"\s*",
        flags=re.DOTALL,
    )
    return pattern.sub("", html_text)


def insert_summary_after_body_open(html_text: str, fragment: str) -> str:
    """Insert ``fragment`` immediately after the opening ``<body...>`` tag."""
    lower = html_text.lower()
    idx = lower.find("<body")
    if idx == -1:
        raise ValueError("report.html has no <body> tag")
    gt = html_text.find(">", idx)
    if gt == -1:
        raise ValueError("report.html has malformed <body>")
    insert_at = gt + 1
    return html_text[:insert_at] + "\n" + fragment + html_text[insert_at:]


def prepend_summary_to_report_html(
    run_dir: Path,
    *,
    model_key: str = DEFAULT_SUMMARY_MODEL,
) -> Path:
    """Build brief, call LLM, prepend HTML summary into ``report.html`` (replace prior block if any)."""
    from harness.results_brief import brief_from_run_dir

    run_dir = run_dir.resolve()
    report_path = run_dir / "report.html"
    if not report_path.is_file():
        raise FileNotFoundError(f"No report.html in {run_dir}")

    brief = brief_from_run_dir(run_dir)
    narrative = summarize_brief(brief, model_key=model_key)
    label = str(brief.get("run_id") or run_dir.name)
    fragment = narrative_to_html_fragment(label, narrative)

    text = report_path.read_text(encoding="utf-8")
    text = strip_ai_summary_html(text)
    text = insert_summary_after_body_open(text, fragment)
    report_path.write_text(text, encoding="utf-8")
    return report_path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prepend a summary section into report.html for a harness run directory.",
        epilog="Requires GOOGLE_API_KEY in the environment for Gemini (see instructor google-genai client).",
    )
    p.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Path to results/<run_id> containing aggregate.json and report.html",
    )
    p.add_argument(
        "--model-key",
        default=DEFAULT_SUMMARY_MODEL,
        help=f"Model catalog key for summarization (default: {DEFAULT_SUMMARY_MODEL})",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    path = prepend_summary_to_report_html(args.run_dir.resolve(), model_key=args.model_key)
    print(f"Updated {path}")


if __name__ == "__main__":
    main()

__all__ = [
    "HarnessReportNarrative",
    "HarnessVisualStory",
    "VisualFinding",
    "NextStep",
    "AI_SUMMARY_START",
    "AI_SUMMARY_END",
    "summarize_brief",
    "summarize_visual_story",
    "summarize_visual_story_safe",
    "heuristic_visual_story",
    "narrative_to_markdown",
    "narrative_to_html_fragment",
    "strip_ai_summary_html",
    "insert_summary_after_body_open",
    "prepend_summary_to_report_html",
    "DEFAULT_SUMMARY_MODEL",
    "DEFAULT_VISUAL_STORY_MODEL",
    "main",
]
