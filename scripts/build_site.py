"""Assemble a static site from `results/` for GitHub Pages.

The harness drops two kinds of HTML reports into `results/`:

  1. Top-level files such as ``fewshot_benchmark_<timestamp>.html``.
  2. Per-run folders such as ``20260512T191113Z/`` that contain
     ``report.html`` plus ``aggregate.json`` / ``config.json`` / ``run.jsonl``.
     An AI summary may be prepended into ``report.html`` by
     ``python -m harness.report_summary``.

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


def discover_reports(results_dir: Path) -> list[ReportEntry]:
    entries: list[ReportEntry] = []

    for item in sorted(results_dir.iterdir()):
        if item.name.startswith("."):
            continue

        if item.is_file() and item.suffix.lower() == ".html":
            stem = item.stem
            # Try to pull a trailing timestamp like ...20260507T192249Z out.
            ts_token = stem.split("_")[-1]
            entries.append(
                ReportEntry(
                    title=stem,
                    href=item.name,
                    kind="benchmark",
                    timestamp=_format_timestamp(ts_token),
                    size_bytes=item.stat().st_size,
                )
            )
            continue

        if item.is_dir():
            report_html = item / "report.html"
            if not report_html.is_file():
                continue
            aggregate = _load_aggregate(item / "aggregate.json")
            cfg = aggregate.get("config", {}) if isinstance(aggregate, dict) else {}
            entries.append(
                ReportEntry(
                    title=item.name,
                    href=f"{item.name}/report.html",
                    kind="run",
                    timestamp=_format_timestamp(item.name),
                    size_bytes=report_html.stat().st_size,
                    agent=cfg.get("agent"),
                    models=cfg.get("models") or None,
                    datasets=cfg.get("datasets") or None,
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
  color-scheme: light dark;
  --bg: #f7f8fb;
  --fg: #1f2937;
  --muted: #6b7280;
  --card: #ffffff;
  --border: #e5e7eb;
  --accent: #2563eb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f172a;
    --fg: #e5e7eb;
    --muted: #94a3b8;
    --card: #111827;
    --border: #1f2937;
    --accent: #60a5fa;
  }
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
    Arial, sans-serif;
  margin: 0;
  padding: 32px 16px 64px;
  background: var(--bg);
  color: var(--fg);
}
.container { max-width: 1100px; margin: 0 auto; }
h1 { margin: 0 0 8px; font-size: 28px; }
.subtitle { color: var(--muted); margin: 0 0 24px; }
.toolbar {
  display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
  margin-bottom: 20px;
}
.toolbar input[type="search"] {
  flex: 1 1 320px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--fg);
  font-size: 14px;
}
.toolbar .pill {
  font-size: 12px;
  color: var(--muted);
  background: var(--card);
  border: 1px solid var(--border);
  padding: 6px 10px;
  border-radius: 999px;
}
section { margin-bottom: 32px; }
section h2 { margin: 0 0 12px; font-size: 18px; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  transition: transform 0.05s ease, border-color 0.1s ease;
}
.card:hover { border-color: var(--accent); }
.card a.title {
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
  font-size: 15px;
  word-break: break-word;
}
.card a.title:hover { text-decoration: underline; }
.meta { color: var(--muted); font-size: 12px; margin-top: 6px; }
.meta-row { margin-top: 4px; }
.tag {
  display: inline-block;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--accent);
  margin-right: 4px;
  margin-top: 4px;
}
footer {
  margin-top: 40px;
  color: var(--muted);
  font-size: 12px;
  text-align: center;
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
        tags.append(f"<span class='tag'>agent: {html.escape(entry.agent)}</span>")
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

    def render_section(title: str, items: list[ReportEntry]) -> str:
        if not items:
            return ""
        cards = "\n".join(_render_card(item) for item in items)
        return (
            f"<section><h2>{html.escape(title)} ({len(items)})</h2>"
            f"<div class='grid'>{cards}</div></section>"
        )

    sections = render_section("Run reports", runs) + render_section(
        "Benchmark reports", benchmarks
    )

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Harness Agents · Reports</title>
  <style>{PAGE_CSS}</style>
</head>
<body>
  <div class=\"container\">
    <h1>Harness Agents · Reports</h1>
    <p class=\"subtitle\">Static index of HTML reports generated by the harness.
    Last built {html.escape(generated_at)}.</p>
    <div class=\"toolbar\">
      <input id=\"search\" type=\"search\" placeholder=\"Filter by name, model, dataset, timestamp...\" />
      <span class=\"pill\">{len(entries)} report(s)</span>
    </div>
    {sections}
    <footer>Generated by <code>scripts/build_site.py</code>.</footer>
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
