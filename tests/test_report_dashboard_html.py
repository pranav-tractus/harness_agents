"""Smoke tests for dashboard-style report.html (no LLM)."""

from __future__ import annotations

from pathlib import Path

from harness.artifacts import write_report
from harness.report_summary import heuristic_visual_story, summarize_visual_story_safe
from harness.report_dashboard_html import render_dashboard_report_html


def test_heuristic_story_has_three_findings():
    brief = {"kind": "single_run_dir", "run_id": "x", "leaderboard_agent_model_fs": []}
    summary = {
        "totals": {"run_count": 10, "success_rate": 1.0, "field_match_rate": 0.8, "avg_elapsed_sec": 2.5},
        "by_combo": [],
        "by_dataset": [
            {
                "agent_id": "a1",
                "dataset_id": "d1",
                "run_count": 5,
                "field_match_rate": 0.9,
                "avg_mismatch_per_expected_run": 1.0,
            },
            {
                "agent_id": "a1",
                "dataset_id": "d2",
                "run_count": 5,
                "field_match_rate": 0.4,
                "avg_mismatch_per_expected_run": 8.0,
            },
        ],
    }
    config = {"agent": "a1"}
    story = heuristic_visual_story(brief, summary, config)
    assert len(story.findings) == 3
    assert len(story.next_steps) >= 3


def test_render_dashboard_contains_chart_and_leaderboard(tmp_path: Path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    aggregate = {
        "run_id": "run1",
        "config": {"agent": "so_extraction", "models": ["m1"]},
        "summary": {
            "totals": {
                "run_count": 2,
                "success_rate": 1.0,
                "field_match_rate": 0.85,
                "avg_elapsed_sec": 1.2,
            },
            "by_combo": [
                {
                    "agent_id": "so_extraction",
                    "model_key": "m1",
                    "few_shot_count": 0,
                    "run_count": 2,
                    "success_rate": 1.0,
                    "avg_elapsed_sec": 1.2,
                    "avg_mismatch_per_expected_run": 2.0,
                    "field_match_rate": 0.85,
                },
            ],
            "by_dataset": [
                {
                    "agent_id": "so_extraction",
                    "dataset_id": "acme",
                    "run_count": 2,
                    "success_rate": 1.0,
                    "avg_elapsed_sec": 1.2,
                    "avg_mismatch_per_expected_run": 2.0,
                    "field_match_rate": 0.85,
                },
            ],
            "by_few_shot_count": [
                {
                    "agent_id": "so_extraction",
                    "few_shot_count": 0,
                    "run_count": 2,
                    "success_rate": 1.0,
                    "field_match_rate": 0.85,
                    "avg_mismatch_per_expected_run": 2.0,
                },
            ],
            "by_agent": [
                {
                    "agent_id": "so_extraction",
                    "run_count": 2,
                    "success_rate": 1.0,
                    "avg_attempts": 1.0,
                    "avg_elapsed_sec": 1.2,
                    "avg_mismatch_per_expected_run": 2.0,
                    "field_match_rate": 0.85,
                },
            ],
            "by_chat": [],
        },
    }
    import json

    (run_dir / "aggregate.json").write_text(json.dumps(aggregate), encoding="utf-8")
    (run_dir / "run.jsonl").write_text("", encoding="utf-8")

    from harness.results_brief import brief_from_run_dir

    brief = brief_from_run_dir(run_dir)
    story = summarize_visual_story_safe(brief, aggregate["summary"], aggregate["config"], use_llm=False)
    html = render_dashboard_report_html(
        "run1",
        "2099-01-01 00:00 UTC",
        aggregate["config"],
        aggregate["summary"],
        [],
        story,
    )
    assert "Chart.js" in html or "chart.umd" in html
    assert "frontierChart" in html
    assert "leaderboard-body" in html
    assert "Sec. 01" in html


def test_write_report_end_to_end(tmp_path: Path):
    run_dir = tmp_path / "r2"
    run_dir.mkdir()
    summary = {
        "totals": {
            "run_count": 1,
            "success_rate": 1.0,
            "avg_attempts": 1.0,
            "avg_elapsed_sec": 1.0,
            "avg_mismatch_per_expected_run": 0.0,
            "field_match_rate": 1.0,
        },
        "by_combo": [
            {
                "agent_id": "a",
                "model_key": "m",
                "few_shot_count": 0,
                "run_count": 1,
                "success_rate": 1.0,
                "avg_elapsed_sec": 1.0,
                "avg_mismatch_per_expected_run": 0.0,
                "field_match_rate": 1.0,
            },
        ],
        "by_dataset": [],
        "by_few_shot_count": [
            {
                "agent_id": "a",
                "few_shot_count": 0,
                "run_count": 1,
                "success_rate": 1.0,
                "field_match_rate": 1.0,
                "avg_mismatch_per_expected_run": 0.0,
            },
        ],
        "by_agent": [
            {
                "agent_id": "a",
                "run_count": 1,
                "success_rate": 1.0,
                "avg_attempts": 1.0,
                "avg_elapsed_sec": 1.0,
                "avg_mismatch_per_expected_run": 0.0,
                "field_match_rate": 1.0,
            },
        ],
        "by_chat": [],
    }
    import json

    (run_dir / "aggregate.json").write_text(
        json.dumps({"run_id": "r2", "config": {"agent": "a"}, "summary": summary}),
        encoding="utf-8",
    )
    (run_dir / "run.jsonl").write_text("", encoding="utf-8")
    write_report(run_dir, "r2", {"agent": "a"}, summary, [], generate_llm_story=False)
    text = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "Harness Run" in text
    assert 'class="finding"' in text
