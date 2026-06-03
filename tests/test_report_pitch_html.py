"""Tests for executive pitch HTML reports."""

from __future__ import annotations

from pathlib import Path

from harness.artifacts import write_pitch_report


def _minimal_summary() -> dict:
    return {
        "totals": {
            "run_count": 2,
            "success_rate": 1.0,
            "avg_elapsed_sec": 10.0,
            "field_match_rate": 0.9,
            "field_match_rate_raw_llm": 0.85,
            "field_match_rate_baseline": 0.8,
            "field_match_rate_final": 0.9,
        },
        "by_combo": [
            {
                "agent_id": "so_extraction",
                "model_key": "opus-4-6",
                "few_shot_count": 0,
                "run_count": 1,
                "field_match_rate": 0.92,
                "field_match_rate_raw_llm": 0.88,
                "field_match_rate_baseline": 0.8,
                "field_match_rate_final": 0.92,
                "avg_elapsed_sec": 12.0,
                "avg_mismatch_per_expected_run": 1.0,
            },
            {
                "agent_id": "so_extraction",
                "model_key": "gemini:gemini-2.5-pro",
                "few_shot_count": 0,
                "run_count": 1,
                "field_match_rate": 0.5,
                "avg_elapsed_sec": 40.0,
                "avg_mismatch_per_expected_run": 5.0,
            },
        ],
        "by_dataset": [
            {"agent_id": "so_extraction", "dataset_id": "acme", "field_match_rate": 0.9, "run_count": 2},
        ],
        "by_few_shot_count": [],
        "by_agent": [],
        "by_chat": [],
    }


def test_pitch_report_excludes_gemini_and_skips_tables(tmp_path: Path):
    run_dir = tmp_path / "pitch_run"
    run_dir.mkdir()
    config = {
        "agent": "so_extraction",
        "models": ["opus-4-6", "gemini:gemini-2.5-pro"],
        "datasets": ["acme"],
        "report_style": "pitch",
    }
    summary = _minimal_summary()
    write_pitch_report(run_dir, "pitch_run", config, summary)
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "accuracyChart" in html
    assert "pipelineChart" in html
    assert "leaderboard-body" not in html
    assert "Run configuration (JSON)" not in html
    assert "gemini" not in html.lower()
    assert "Opus 4.6" in html
    assert "Bedrock" not in html
    assert "Anthropic" not in html
    assert "Sales order extraction" in html
