"""Unit tests for extraction post-processing (no LLM)."""

from __future__ import annotations

import unittest

from core.postprocess_deterministic import (
    apply_deterministic_postprocess,
    collect_date_warnings,
    diff_date_fields,
    freeze_date_fields_from_raw,
    normalize_units,
    recompute_totals,
)
from core.postprocess_pipeline import run_postprocess_pipeline
from core.postprocess_stages import (
    FreezeDatesStage,
    NormalizeUnitsStage,
    RecomputeTotalsStage,
    StageContext,
    StructuralAuditStage,
    ValidationLLMStage,
)


def _sample_contract():
    return {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "Coffee",
                        "quantity": 10.0,
                        "quantity_unit": "bags",
                        "unit_price": 25.0,
                        "pricing_unit": "usd/bag",
                        "total": 100.0,
                        "shipment_date": "2025-01-15",
                    },
                ],
                "do_date": "2025-01-15",
                "po_date": "",
            },
        ],
    }


class TestPostprocessDeterministic(unittest.TestCase):
    def test_deterministic_fixes_total_and_normalizes_units(self):
        raw = _sample_contract()
        out, _warnings = apply_deterministic_postprocess(
            raw,
            reference_iso_date="2026-05-20",
        )
        item = out["data"][0]["items"][0]
        self.assertEqual(item["quantity_unit"], "BAGS")
        self.assertEqual(item["pricing_unit"], "USD/BAG")
        self.assertEqual(item["total"], 250.0)

    def test_date_warnings_past_date(self):
        raw = _sample_contract()
        warnings = collect_date_warnings(raw, reference_iso_date="2026-05-20")
        codes = {w["code"] for w in warnings}
        self.assertIn("date_in_past", codes)

    def test_freeze_date_fields_from_raw(self):
        raw = _sample_contract()
        candidate = _sample_contract()
        candidate["data"][0]["do_date"] = "2099-12-31"
        candidate["data"][0]["items"][0]["shipment_date"] = "2099-12-31"
        final = freeze_date_fields_from_raw(raw, candidate)
        self.assertEqual(final["data"][0]["do_date"], "2025-01-15")
        self.assertEqual(final["data"][0]["items"][0]["shipment_date"], "2025-01-15")

    def test_aggregate_dual_score_fields(self):
        from agents.base import AgentRunResult, ScoreResult
        from harness.artifacts import aggregate, record_to_row

        rec = AgentRunResult(
            agent_id="so_extraction",
            dataset_id="test",
            source_path="/tmp/x.json",
            success=True,
            status="success",
            attempts=1,
            elapsed_sec=1.0,
            output_json={"data": []},
            raw_llm_output_json={"data": []},
            score=ScoreResult(expected_available=True, mismatch_count=1, compared_field_count=10),
            score_raw_llm=ScoreResult(expected_available=True, mismatch_count=3, compared_field_count=10),
        )
        row = record_to_row(rec)
        self.assertEqual(row["mismatch_count"], 1)
        self.assertEqual(row["mismatch_count_raw"], 3)
        self.assertEqual(row["improvement_mismatches"], 2)
        summary = aggregate([rec])
        self.assertIsNotNone(summary["totals"]["field_match_rate_raw_llm"])
        self.assertIsNotNone(summary["totals"]["field_match_rate_final"])


class TestNormalizeAndRecomputeSplit(unittest.TestCase):
    def test_normalize_units_only(self):
        raw = _sample_contract()
        out, changes = normalize_units(raw)
        item = out["data"][0]["items"][0]
        self.assertEqual(item["quantity_unit"], "BAGS")
        self.assertEqual(item["pricing_unit"], "USD/BAG")
        # total is untouched by the normalize-only path
        self.assertEqual(item["total"], 100.0)
        self.assertTrue(all(c["code"] == "deterministic_change" for c in changes))

    def test_recompute_after_unit_rescale(self):
        contract = {
            "data": [
                {
                    "items": [
                        {
                            "quantity": 10.0,
                            "quantity_unit": "MT",
                            "unit_price": 3.5,
                            "pricing_unit": "USD/KG",
                            "total": 0.0,
                        }
                    ],
                }
            ],
        }
        out, msgs = recompute_totals(contract)
        self.assertEqual(out["data"][0]["items"][0]["total"], 35000.0)
        self.assertTrue(any(m.get("code") == "deterministic_change" for m in msgs))


class TestStages(unittest.TestCase):
    def _ctx(self, raw, validation_model_key=None):
        return StageContext(
            source_text="chat",
            reference_iso_date="2026-05-20",
            raw_contract=raw,
            extraction_model_key="m",
            validation_model_key=validation_model_key,
        )

    def test_freeze_dates_stage_surfaces_masked_changes(self):
        raw = _sample_contract()
        candidate = _sample_contract()
        candidate["data"][0]["do_date"] = "2099-12-31"
        result = FreezeDatesStage().run(candidate, self._ctx(raw))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.contract["data"][0]["do_date"], "2025-01-15")
        self.assertTrue(any(w.get("code") == "date_change_masked" for w in result.warnings))

    def test_structural_audit_detects_item_count_drift(self):
        raw = _sample_contract()
        candidate = _sample_contract()
        candidate["data"][0]["items"].pop()  # validator dropped an item
        result = StructuralAuditStage().run(candidate, self._ctx(raw))
        codes = {w.get("code") for w in result.warnings}
        self.assertIn("structural_drift", codes)

    def test_validation_stage_skips_without_model_key(self):
        raw = _sample_contract()
        result = ValidationLLMStage().run(raw, self._ctx(raw, validation_model_key=None))
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.contract, raw)

    def test_normalize_units_stage_status_ok(self):
        result = NormalizeUnitsStage().run(_sample_contract(), self._ctx(_sample_contract()))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.contract["data"][0]["items"][0]["quantity_unit"], "BAGS")

    def test_recompute_after_validation_uses_validator_rescale(self):
        # Simulate validator rescaling unit_price; ensure pipeline recomputes totals
        # AFTER the validator stage (the new ordering).
        raw = {
            "data": [
                {
                    "items": [
                        {
                            "quantity": 10.0,
                            "quantity_unit": "MT",
                            "unit_price": 3.5,
                            "pricing_unit": "USD/MT",
                            "total": 35.0,  # wrong baseline; recompute should fix
                            "shipment_date": "2026-06-15",
                        }
                    ],
                    "po_date": "2026-06-01",
                    "do_date": "2026-06-15",
                }
            ],
        }
        final, diag = run_postprocess_pipeline(
            raw,
            source_text="x",
            reference_iso_date="2026-05-20",
            extraction_model_key="m",
            validation_model_key=None,
            enable_validation_llm=False,
        )
        self.assertEqual(final["data"][0]["items"][0]["total"], 35.0)


class TestPipelineRunner(unittest.TestCase):
    def test_pipeline_records_stage_diagnostics(self):
        raw = _sample_contract()
        final, diag = run_postprocess_pipeline(
            raw,
            source_text="x",
            reference_iso_date="2026-05-20",
            extraction_model_key="m",
            validation_model_key=None,
            enable_validation_llm=False,
        )
        names = [s["name"] for s in diag["stages"]]
        self.assertEqual(
            names,
            ["normalize_units", "validation_llm", "recompute_totals", "freeze_dates", "structural_audit"],
        )
        # validation_llm should be skipped when no key.
        val_stage = next(s for s in diag["stages"] if s["name"] == "validation_llm")
        self.assertEqual(val_stage["status"], "skipped")

    def test_pipeline_warns_when_validation_enabled_without_key(self):
        _final, diag = run_postprocess_pipeline(
            _sample_contract(),
            source_text="x",
            reference_iso_date="2026-05-20",
            extraction_model_key="m",
            validation_model_key=None,
            enable_validation_llm=True,
        )
        codes = {w.get("code") for w in diag["warnings"]}
        self.assertIn("validation_skipped_no_model", codes)

    def test_pipeline_validator_failure_surfaces_status_failed(self):
        from core.postprocess_stages import PostprocessStage, StageResult

        class FailingValidator:
            name = "validation_llm"
            enabled_key = "enable_validation_llm"

            def run(self, contract, ctx):
                return StageResult(
                    name=self.name,
                    status="failed",
                    contract=contract,
                    error="boom",
                )

        from core.postprocess_stages import (
            FreezeDatesStage as F,
            NormalizeUnitsStage as N,
            RecomputeTotalsStage as R,
            StructuralAuditStage as S,
        )

        stages: list[PostprocessStage] = [N(), FailingValidator(), R(), F(), S()]
        final, diag = run_postprocess_pipeline(
            _sample_contract(),
            source_text="x",
            reference_iso_date="2026-05-20",
            extraction_model_key="m",
            validation_model_key="dummy",
            enable_validation_llm=True,
            stages=stages,
        )
        self.assertIn("validation_error", diag)
        self.assertEqual(diag["validation_error"], "boom")
        # working contract continues through downstream stages despite failure
        self.assertEqual(final["data"][0]["items"][0]["quantity_unit"], "BAGS")


class TestDiffDateFields(unittest.TestCase):
    def test_diff_lists_changed_paths(self):
        raw = _sample_contract()
        candidate = _sample_contract()
        candidate["data"][0]["do_date"] = "2099-12-31"
        candidate["data"][0]["items"][0]["shipment_date"] = "2099-12-31"
        diffs = diff_date_fields(raw, candidate)
        paths = {d["path"] for d in diffs}
        self.assertIn("data[0].do_date", paths)
        self.assertIn("data[0].items[0].shipment_date", paths)


if __name__ == "__main__":
    unittest.main()
