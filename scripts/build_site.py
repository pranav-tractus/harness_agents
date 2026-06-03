"""Assemble a static site from `results/` for GitHub Pages.

The harness drops two kinds of HTML reports into ``results/`` (any depth):

  1. Standalone ``*.html`` files (for example ``archives/fewshot_*.html`` or
     ``example/harness_report_reorganized.html``). ``report.html`` is reserved
     for per-run folders and is not listed as a standalone benchmark.
  2. Per-run directories containing ``report.html`` plus
     ``aggregate.json`` / ``config.json`` / ``run.jsonl`` (timestamps like
     ``20260512T191113Z`` at the top level or nested under other folders).
     ``report.html`` is a dashboard-style page (charts + cards + sortable table);
     optional Gemini narrative may still be prepended via ``python -m harness.report_summary``.

This script copies everything under ``results/`` into ``site/`` (preserving
structure) and writes a top-level ``index.html`` that links to each report
with light metadata (agent, models, datasets, timestamps, file size).

Run:

    python scripts/build_site.py --results results --out site
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ReportEntry:
    """One row in the generated index."""

    title: str
    href: str
    kind: str
    timestamp: str
    size_bytes: int
    agent: str | None = None
    models: list[str] | None = None
    datasets: list[str] | None = None

    def size_human(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} GB"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _load_aggregate(aggregate_path: Path) -> dict:
    try:
        with aggregate_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _format_timestamp(token: str) -> str:
    # Expected formats: 20260512T191113Z or similar.
    try:
        parsed = dt.datetime.strptime(token, "%Y%m%dT%H%M%SZ")
        return parsed.replace(tzinfo=dt.timezone.utc).isoformat()
    except ValueError:
        return token


def _rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _skip_path_rel(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def discover_reports(results_dir: Path) -> list[ReportEntry]:
    """Find all reports under ``results_dir`` recursively."""
    entries: list[ReportEntry] = []
    root = results_dir.resolve()

    # Per-run folders: any directory (under root) that contains report.html
    for report_html in sorted(root.rglob("report.html")):
        rel = report_html.relative_to(root)
        if _skip_path_rel(rel):
            continue
        run_dir = report_html.parent
        run_rel = _rel_posix(run_dir, root)
        aggregate = _load_aggregate(run_dir / "aggregate.json")
        cfg = aggregate.get("config", {}) if isinstance(aggregate, dict) else {}
        title = run_rel
        if cfg.get("report_style") == "pitch":
            title = f"Pitch · {run_rel}"
        entries.append(
            ReportEntry(
                title=title,
                href=f"{run_rel}/report.html",
                kind="run",
                timestamp=_format_timestamp(run_dir.name),
                size_bytes=report_html.stat().st_size,
                agent=cfg.get("agent"),
                models=cfg.get("models") or None,
                datasets=cfg.get("datasets") or None,
            )
        )

    # Standalone HTML (not report.html); report.html is only indexed via runs.
    for path in sorted(root.rglob("*.html")):
        rel = path.relative_to(root)
        if _skip_path_rel(rel) or path.name == "report.html":
            continue
        if not path.is_file() or path.suffix.lower() != ".html":
            continue
        stem = path.stem
        rel_str = _rel_posix(path, root)
        title = path.relative_to(root).with_suffix("").as_posix()
        ts_token = stem.split("_")[-1]
        entries.append(
            ReportEntry(
                title=title,
                href=rel_str,
                kind="benchmark",
                timestamp=_format_timestamp(ts_token),
                size_bytes=path.stat().st_size,
            )
        )

    # Newest first, falling back to title.
    entries.sort(key=lambda e: (e.timestamp, e.title), reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


PAGE_CSS = """
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
  --good: #2d6b3f;
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
.toolbar {
  display: flex;
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
  margin: 28px 0 8px;
}
.toolbar input[type="search"] {
  flex: 1 1 360px;
  padding: 12px 14px;
  border: 1px solid var(--ink);
  background: var(--bg-elevated);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 14px;
  outline: none;
}
.toolbar input[type="search"]:focus { border-color: var(--accent); }
.toolbar .pill {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-soft);
  background: var(--bg-card);
  border: 1px solid var(--line);
  padding: 8px 12px;
}
section { margin: 48px 0; }
.section-head {
  display: flex;
  align-items: baseline;
  gap: 18px;
  margin-bottom: 22px;
  border-bottom: 1px solid var(--ink);
  padding-bottom: 6px;
}
.section-num {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--accent);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
section h2 {
  font-family: var(--display);
  font-weight: 400;
  font-size: 32px;
  line-height: 1.1;
  letter-spacing: -0.01em;
  flex: 1;
}
.section-count {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-mute);
  letter-spacing: 0.08em;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}
.card {
  background: var(--bg-card);
  border: 1px solid var(--line);
  padding: 18px 18px 16px;
  transition: border-color 0.1s ease, background 0.1s ease;
  display: flex;
  flex-direction: column;
}
.card:hover { border-color: var(--accent); background: var(--bg-elevated); }
.card a.title {
  font-family: var(--display);
  font-weight: 400;
  font-size: 22px;
  line-height: 1.15;
  color: var(--ink);
  text-decoration: none;
  letter-spacing: -0.005em;
  word-break: break-word;
}
.card a.title:hover { color: var(--accent); }
.meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-mute);
  letter-spacing: 0.04em;
  margin-top: 10px;
}
.meta-row { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; }
.tag {
  display: inline-block;
  font-family: var(--mono);
  font-size: 10.5px;
  padding: 3px 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--line);
  color: var(--ink-soft);
  letter-spacing: 0.02em;
}
.tag-agent { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
footer {
  margin: 48px 0 32px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  color: var(--ink-mute);
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-align: center;
}
footer code { font-family: var(--mono); color: var(--ink-soft); }
.empty {
  font-family: var(--display);
  font-style: italic;
  font-size: 18px;
  color: var(--ink-mute);
  padding: 24px 0;
}
"""

PAGE_JS = """
const search = document.getElementById('search');
const cards = Array.from(document.querySelectorAll('.card'));
search.addEventListener('input', () => {
  const q = search.value.trim().toLowerCase();
  cards.forEach((card) => {
    const haystack = card.dataset.search || '';
    card.style.display = !q || haystack.includes(q) ? '' : 'none';
  });
  document.querySelectorAll('section').forEach((sec) => {
    const visible = sec.querySelectorAll('.card:not([style*="display: none"])').length;
    sec.style.display = visible === 0 ? 'none' : '';
  });
});
"""


def _render_card(entry: ReportEntry) -> str:
    tags: list[str] = []
    if entry.agent:
        tags.append(
            f"<span class='tag tag-agent'>{html.escape(entry.agent)}</span>"
        )
    if entry.models:
        for model in entry.models[:4]:
            tags.append(f"<span class='tag'>{html.escape(model)}</span>")
        if len(entry.models) > 4:
            tags.append(f"<span class='tag'>+{len(entry.models) - 4} more</span>")
    if entry.datasets:
        for dataset in entry.datasets[:3]:
            tags.append(f"<span class='tag'>{html.escape(dataset)}</span>")

    search_blob = " ".join(
        filter(
            None,
            [
                entry.title,
                entry.href,
                entry.timestamp,
                entry.agent or "",
                " ".join(entry.models or []),
                " ".join(entry.datasets or []),
            ],
        )
    ).lower()

    tag_html = "".join(tags)
    meta_html = (
        f"<div class='meta'>{html.escape(entry.timestamp)} · "
        f"{entry.size_human()}</div>"
    )
    tag_block = (
        f"<div class='meta-row'>{tag_html}</div>" if tag_html else ""
    )

    return (
        f"<article class='card' data-search=\"{html.escape(search_blob)}\">"
        f"<a class='title' href='{html.escape(entry.href)}'>"
        f"{html.escape(entry.title)}</a>"
        f"{meta_html}{tag_block}"
        "</article>"
    )


def render_index(entries: list[ReportEntry], generated_at: str) -> str:
    runs = [e for e in entries if e.kind == "run"]
    benchmarks = [e for e in entries if e.kind == "benchmark"]

    def render_section(num: str, title: str, items: list[ReportEntry]) -> str:
        if not items:
            return ""
        cards = "\n".join(_render_card(item) for item in items)
        return (
            f"<section>"
            f"<div class='section-head'>"
            f"<span class='section-num'>Sec. {html.escape(num)}</span>"
            f"<h2>{html.escape(title)}</h2>"
            f"<span class='section-count'>{len(items)} report{'s' if len(items) != 1 else ''}</span>"
            f"</div>"
            f"<div class='grid'>{cards}</div>"
            f"</section>"
        )

    sections = render_section("01", "Run reports", runs) + render_section(
        "02", "Benchmark reports", benchmarks
    )
    if not sections:
        sections = "<p class='empty'>No reports have been published yet.</p>"

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Harness Agents · Reports</title>
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
  <link href=\"https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap\" rel=\"stylesheet\">
  <style>{PAGE_CSS}</style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"masthead\">
      <div class=\"masthead-top\">
        <span><span class=\"dot\"></span>Harness Agents · Report Index</span>
        <span>{html.escape(generated_at)} &nbsp;·&nbsp; {len(entries)} report{'s' if len(entries) != 1 else ''}</span>
      </div>
      <h1>The harness archive <em>— every run, every benchmark, in one place.</em></h1>
      <p class=\"dek\">Browse every report generated by the harness. Each card opens the full editorial-style report for that run, with charts, leaderboards, and recommendations.</p>
      <div class=\"toolbar\">
        <input id=\"search\" type=\"search\" placeholder=\"Filter by name, model, dataset, timestamp…\" />
        <span class=\"pill\">{len(entries)} total</span>
      </div>
    </div>
    {sections}
    <footer>Generated by <code>scripts/build_site.py</code></footer>
  </div>
  <script>{PAGE_JS}</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_site(results_dir: Path, out_dir: Path) -> int:
    if not results_dir.is_dir():
        raise SystemExit(f"results directory not found: {results_dir}")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Mirror results/ into site/ so links resolve as-is.
    for item in results_dir.iterdir():
        if item.name.startswith("."):
            continue
        target = out_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    entries = discover_reports(results_dir)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    (out_dir / "index.html").write_text(
        render_index(entries, generated_at), encoding="utf-8"
    )
    # Prevent Jekyll on GitHub Pages from skipping files starting with `_`.
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("results"),
        help="Source directory containing HTML reports (default: results)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("site"),
        help="Output directory for the static site (default: site)",
    )
    args = parser.parse_args()

    count = build_site(args.results.resolve(), args.out.resolve())
    print(f"Built site at {args.out} with {count} report(s).")


if __name__ == "__main__":
    main()
