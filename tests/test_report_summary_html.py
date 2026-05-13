"""Tests for HTML injection helpers (no LLM)."""

from __future__ import annotations

from harness.report_summary import (
    AI_SUMMARY_END,
    AI_SUMMARY_START,
    insert_summary_after_body_open,
    strip_ai_summary_html,
)


def test_strip_ai_summary_removes_block():
    frag = f"{AI_SUMMARY_START}\n<section>x</section>\n{AI_SUMMARY_END}\n"
    doc = f"<!doctype><html><body>{frag}<h1>Hi</h1></body></html>"
    out = strip_ai_summary_html(doc)
    assert AI_SUMMARY_START not in out
    assert "<h1>Hi</h1>" in out


def test_insert_summary_after_body():
    doc = '<!doctype html><html><body class="x">\n<h1>Hi</h1>\n</body></html>'
    out = insert_summary_after_body_open(doc, "<p>NEW</p>")
    assert out.index("<p>NEW</p>") < out.index("<h1>Hi</h1>")


def test_strip_then_insert_idempotent():
    frag = f"{AI_SUMMARY_START}<p>v1</p>{AI_SUMMARY_END}"
    doc = f"<html><body>{frag}<main>z</main></body></html>"
    doc2 = insert_summary_after_body_open(strip_ai_summary_html(doc), f"{AI_SUMMARY_START}<p>v2</p>{AI_SUMMARY_END}")
    assert "v1" not in doc2
    assert "v2" in doc2
    assert "<main>z</main>" in doc2
