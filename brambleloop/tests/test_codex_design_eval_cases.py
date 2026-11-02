"""The held-out evidence set is fixed and cannot be chosen by a challenger."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from brambleloop.quality import design_eval


class FrozenCaseTests(unittest.TestCase):
    def test_new_finding_is_a_regression_even_if_an_old_one_disappears(self):
        before = {"compile_errors": 0, "twin_failures": 0, "reverse_findings": 1,
                  "reverse_codes": ["OLD"], "policy_findings": 0, "policy_codes": [],
                  "truth_findings": 0, "truth_codes": [], "originality_escalations": 0,
                  "originality_escalation_keys": [],
                  "originality_unmeasured": 0, "finishing_actions_present": 1}
        after = {**before, "reverse_codes": ["NEW"]}
        with patch.object(design_eval, "measure_written_case", side_effect=[before, after]):
            result = design_eval.compare_written_case(None, "same", "same")
        self.assertIn("reverse_codes", result["regressions"])

    def test_persistent_preview_measures_every_case_but_cannot_approve(self):
        from sqlalchemy import select
        from brambleloop.core.db import Database
        from brambleloop.core.models import AuditLog, DesignRule

        with TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/evaluation.db"
            db = Database(url, scratch=True)
            db.create_all()
            with db.session() as s:
                row = DesignRule(key="finishing", version=1,
                    statement={"rule": "include_finishing_checklist", "parameters": {}},
                    scope={"writer_section": "finishing"}, state="proposed",
                    provenance=[{"kind": "analysis", "id": 1}], producer="analyst")
                s.add(row)
                s.flush()
                rule_id = row.id
            first = design_eval.preview_registered_rule(db, rule_id)
            reopened = Database(url, scratch=True)
            with reopened.session() as s:
                audit = s.scalar(select(AuditLog).where(AuditLog.id == first["audit_id"]))
                self.assertEqual(audit.action, "design_eval.preview")
                self.assertEqual(len(audit.detail["cases"]), 8)
                self.assertTrue(audit.detail["benchmark_checks"]["bench1_compiles"])
                self.assertTrue(audit.detail["benchmark_checks"]["bench1_twins"])
                self.assertEqual(audit.detail["state"], "insufficient_evidence")
                self.assertFalse(audit.detail["approval_evidence_complete"])
                self.assertTrue(any(case["before"]["originality_unmeasured"] > 0
                                    for case in audit.detail["cases"]))
                self.assertTrue(all(case["before"]["twin_failures"] == 0
                                    for case in audit.detail["cases"]))
                self.assertEqual(audit.detail["benchmark_checks"]["bench2_stages"]["pattern"],
                                 "PASS")
                self.assertEqual(audit.detail["benchmark_checks"]["bench2_stages"]["reference"],
                                 "UNKNOWN")
                self.assertNotIn("Fasten off", str(audit.detail))
                self.assertEqual(s.get(DesignRule, rule_id).state, "proposed")
            second = design_eval.preview_registered_rule(reopened, rule_id)
            self.assertEqual(first["cases"], second["cases"])
            self.assertEqual(first["benchmark_checks"], second["benchmark_checks"])
            self.assertEqual(first["rule_sha256"], second["rule_sha256"])

    def test_actual_output_metrics_find_missing_finishing_and_do_not_authorize(self):
        from brambleloop.cir.compiler import compile_cir
        from brambleloop.cir.writer import FINISHING_HEADING, write_pattern
        from brambleloop.products import launch0

        cir = launch0.cir_for("basket_small")
        original = write_pattern(cir, compile_cir(cir))
        broken = original.split(FINISHING_HEADING)[0]
        report = design_eval.compare_written_case(cir, original, broken)
        self.assertGreater(report["before"]["finishing_actions_present"], 0)
        self.assertEqual(report["after"]["finishing_actions_present"], 0)
        self.assertIn("finishing_actions_present", report["regressions"])
        self.assertFalse(report["approval_evidence_complete"])
        self.assertNotIn(original, repr(report))

    def test_formatting_change_is_measured_without_exposing_text(self):
        from brambleloop.cir.compiler import compile_cir
        from brambleloop.cir.writer import FINISHING_HEADING, write_pattern
        from brambleloop.products import launch0

        cir = launch0.cir_for("cloudline_blanket")
        original = write_pattern(cir, compile_cir(cir))
        head, finishing = original.split(FINISHING_HEADING, 1)
        changed = head + FINISHING_HEADING + "\n" + "\n".join(
            "- " + line if line else line for line in finishing.strip().splitlines()) + "\n"
        report = design_eval.compare_written_case(cir, original, changed)
        self.assertEqual(report["before"]["finishing_actions_listed"], 0)
        self.assertGreater(report["after"]["finishing_actions_listed"], 0)
        self.assertTrue(report["same_word_shingles"])
        self.assertEqual(report["regressions"], [])
        self.assertFalse(report["approval_evidence_complete"])

    def test_case_hash_is_stable_and_includes_each_required_source(self):
        from brambleloop.products import launch0

        first = design_eval.load_cases()
        self.assertEqual(first, design_eval.load_cases())
        self.assertEqual(len(first["sha256"]), 64)
        self.assertEqual({c["kind"] for c in first["cases"]},
                         {"launch0", "benchmark_truth", "stitch_family"})
        self.assertEqual({c["id"] for c in first["cases"] if c["kind"] == "benchmark_truth"},
                         {"bench1_xs", "bench2"})
        self.assertEqual({c["id"] for c in first["cases"] if c["kind"] == "launch0"},
                         set(launch0.LAUNCH0_SLUGS))

    def test_challenger_cases_and_changed_truth_are_refused(self):
        with self.assertRaises(design_eval.DesignEvaluationRefused):
            design_eval.load_cases(challenger_cases=[])
        with TemporaryDirectory() as tmp:
            changed = Path(tmp) / "truth.json"
            changed.write_text("{}")
            with patch.object(design_eval, "_BENCH2", changed):
                with self.assertRaises(design_eval.DesignEvaluationRefused):
                    design_eval.load_cases()
            with patch.object(design_eval, "_BENCH2", changed.parent / "missing.json"):
                with self.assertRaises(design_eval.DesignEvaluationRefused):
                    design_eval.load_cases()


if __name__ == "__main__":
    unittest.main()
