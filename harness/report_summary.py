"""LLM narrative for harness result briefs (Gemini 2.5 Pro via ``call_llm``)."""

from __future__ import annotations

import argparse
import html
import json
import re
import textwrap
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.llm_client import call_llm

DEFAULT_SUMMARY_MODEL = "gemini:gemini-2.5-pro"

AI_SUMMARY_START = "<!-- harness-ai-summary-start -->"
AI_SUMMARY_END = "<!-- harness-ai-summary-end -->"


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
    "AI_SUMMARY_START",
    "AI_SUMMARY_END",
    "summarize_brief",
    "narrative_to_markdown",
    "narrative_to_html_fragment",
    "strip_ai_summary_html",
    "insert_summary_after_body_open",
    "prepend_summary_to_report_html",
    "DEFAULT_SUMMARY_MODEL",
    "main",
]
