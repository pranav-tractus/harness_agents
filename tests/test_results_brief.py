"""Tests for harness.results_brief metrics (Results Browser parity)."""

from __future__ import annotations

import json
import math

from harness.results_brief import brief_from_run_dir, headline_metrics, leaderboard_by_combo, slim_record


def _row(
    *,
    agent: str = "a1",
    model: str = "m1",
    fs: int = 0,
    success: bool = True,
    elapsed: float = 1.0,
    expected: bool = True,
    mismatch: int = 0,
    compared: int = 10,
    chat: str = "c.json",
) -> dict:
    return {
        "agent_id": agent,
        "model_key": model,
        "few_shot_count": fs,
        "dataset_id": "d1",
        "source_filename": chat,
        "success": success,
        "elapsed_sec": elapsed,
        "expected_available": expected,
        "mismatch_count": mismatch,
        "compared_field_count": compared,
    }


def test_headline_metrics_success_and_stdev():
    rows = [
        _row(mismatch=2, compared=8),
        _row(mismatch=4, compared=8),
        _row(mismatch=6, compared=8),
    ]
    h = headline_metrics(rows)
    assert h["runs"] == 3
    assert abs(h["success_rate"] - 1.0) < 1e-9
    assert abs((h["avg_runtime_sec"] or 0) - 1.0) < 1e-9
    # pstdev uses population variance: sqrt(((2-4)^2+(4-4)^2+(6-4)^2)/3) == sqrt(8/3)
    assert abs((h["mismatch_stdev"] or 0) - math.sqrt(8 / 3)) < 1e-9


def test_headline_metrics_stdev_single_expected_run():
    rows = [_row(mismatch=5)]
    h = headline_metrics(rows)
    assert h["mismatch_stdev"] == 0.0


def test_headline_metrics_ignores_mismatch_when_no_expected():
    rows = [
        _row(expected=False, mismatch=99),
        _row(expected=True, mismatch=2),
    ]
    h = headline_metrics(rows)
    assert h["mismatch_stdev"] == 0.0


def test_leaderboard_two_combos():
    rows = [
        _row(agent="ag", model="mx", fs=0, mismatch=1, compared=10),
        _row(agent="ag", model="mx", fs=0, mismatch=3, compared=10),
        _row(agent="ag", model="my", fs=1, mismatch=0, compared=20),
    ]
    lb = leaderboard_by_combo(rows)
    assert len(lb) == 2
    by_model = {r["model"]: r for r in lb}
    assert by_model["mx"]["runs"] == 2
    assert by_model["mx"]["avg_mismatch_per_expected_run"] == 2.0
    assert abs(by_model["mx"]["field_match_rate"] - (1 - 4 / 20)) < 1e-9
    assert by_model["my"]["fs_count"] == 1
    assert by_model["my"]["avg_mismatch_per_expected_run"] == 0.0


def test_leaderboard_no_expected_bucket():
    rows = [
        _row(model="mz", expected=False, mismatch=0, compared=0),
    ]
    lb = leaderboard_by_combo(rows)
    assert len(lb) == 1
    assert lb[0]["avg_mismatch_per_expected_run"] is None
    assert lb[0]["field_match_rate"] is None


def test_slim_record_drops_bulk():
    fat = _row()
    fat["output_json"] = {"x": "y" * 1000}
    fat["mismatches"] = [{"path": "a"}]
    fat["few_shot_paths"] = ["/tmp/a"]
    s = slim_record(fat)
    assert "output_json" not in s
    assert "mismatches" not in s
    assert "few_shot_paths" not in s
    assert s["agent_id"] == "a1"


def test_brief_from_run_dir_roundtrip(tmp_path):
    run = tmp_path / "20260101T000000Z"
    run.mkdir()
    aggregate = {
        "run_id": run.name,
        "config": {"agent": "ag", "models": ["m1"]},
        "summary": {
            "totals": {
                "run_count": 1,
                "success_rate": 1.0,
                "avg_elapsed_sec": 2.0,
                "avg_mismatch_per_expected_run": 1.0,
                "field_match_rate": 0.9,
            },
            "by_combo": [
                {
                    "agent_id": "ag",
                    "model_key": "m1",
                    "few_shot_count": 0,
                    "run_count": 1,
                    "success_rate": 1.0,
                    "avg_attempts": 1.0,
                    "avg_elapsed_sec": 2.0,
                    "avg_mismatch_per_expected_run": 1.0,
                    "field_match_rate": 0.9,
                }
            ],
        },
    }
    (run / "aggregate.json").write_text(json.dumps(aggregate), encoding="utf-8")
    row = {
        "agent_id": "ag",
        "model_key": "m1",
        "few_shot_count": 0,
        "dataset_id": "d",
        "source_filename": "c.json",
        "success": True,
        "elapsed_sec": 2.0,
        "expected_available": True,
        "mismatch_count": 1,
        "compared_field_count": 10,
    }
    (run / "run.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    b = brief_from_run_dir(run)
    assert b["run_id"] == run.name
    assert b["totals_from_aggregate"]["run_count"] == 1
    assert b["headlines_from_jsonl"]["runs"] == 1
    assert b["headlines_from_jsonl"]["mismatch_stdev"] == 0.0
    assert len(b["leaderboard_agent_model_fs"]) == 1
