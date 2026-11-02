"""The A6 pin interface fails closed until complete evaluations are available."""
from tempfile import TemporaryDirectory
import copy
import unittest
from unittest.mock import Mock

from brambleloop.core.db import Database
from brambleloop.core.models import BenchmarkAnalysis, BenchmarkProduct, DesignRule, utcnow
from brambleloop.improve import design_knowledge as knowledge


class KnowledgeContractTests(unittest.TestCase):
    def test_evaluated_independent_approval_changes_written_output_and_revalidates(self):
        from brambleloop.cir.compiler import compile_cir
        from brambleloop.cir.reverse import compare
        from brambleloop.cir.writer import write_pattern
        from brambleloop.gates.originality import code_benchmarks, record_fingerprint
        from brambleloop.products import launch0
        from brambleloop.quality import design_eval
        from brambleloop.teardown import licence, review

        with TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/knowledge.db"
            db = Database(url, scratch=True)
            db.create_all()
            sha = "b" * 64
            with db.session() as s:
                product = BenchmarkProduct(ref="fixture-purchase", seller="fixture",
                    files=[{"name": "reference.pdf", "sha256": sha}])
                s.add(product)
                s.flush()
                source = BenchmarkAnalysis(benchmark_id=product.id, file_sha256=sha,
                    observations={"fully_readable": True, "dimensions": {"finishing": "absent"}})
                s.add(source)
                s.flush()
                source_id = source.id
            licence.capture_purchase(db, "fixture-purchase")
            review.review_analysis(db, source_id, reviewer="independent-reviewer",
                                   decision="reviewed", reason="reviewed observation")
            rule = knowledge.propose_from_analysis(db, source_id)
            cir = launch0.cir_for("basket_small")
            baseline = write_pattern(cir, compile_cir(cir))
            self.assertEqual(knowledge.applicable(db, {"writer_section": "finishing"}), [])
            incomplete = design_eval.evaluate(db, rule["id"])
            self.assertEqual(incomplete["state"], "insufficient_evidence")
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(db, rule["id"], reviewer="owner", decision="approve",
                                      reason="review", evaluation_id=incomplete["audit_id"])
            for ref in [*(benchmark.ref for benchmark in code_benchmarks()), "fixture-purchase"]:
                # Synthetic fixture wording, never a purchased pattern.
                record_fingerprint(db, ref, text=(
                    "xylophone quasar nebula orbit lantern velvet meadow cobalt river "
                    "telescope compass marigold dolphin rainforest juniper quartz"))
            evaluation = design_eval.evaluate(db, rule["id"])
            self.assertEqual(evaluation["state"], "passed", evaluation)
            worsened = copy.deepcopy(evaluation)
            worsened["cases"][0]["after"]["reverse_findings"] += 1
            worsened["cases"][0]["after"]["reverse_codes"].append("REGRESSION")
            self.assertEqual(design_eval.classify_evaluation(worsened), "regression")
            unchanged = copy.deepcopy(evaluation)
            for case in unchanged["cases"]:
                case["after"]["finishing_actions_listed"] = case["before"]["finishing_actions_listed"]
            self.assertEqual(design_eval.classify_evaluation(unchanged), "no_improvement")
            repeated = design_eval.evaluate(Database(url, scratch=True), rule["id"])
            self.assertFalse(repeated["created"])
            self.assertEqual(repeated["audit_id"], evaluation["audit_id"])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(db, rule["id"], reviewer="teardown_analyst", decision="approve",
                                      reason="self review", evaluation_id=evaluation["audit_id"])
            approved = knowledge.review_rule(db, rule["id"], reviewer="owner", decision="approve",
                                             reason="independent review",
                                             evaluation_id=evaluation["audit_id"])
            pin = approved["pin"]
            reopened = Database(url, scratch=True)
            self.assertEqual(knowledge.applicable(reopened, {"writer_section": "finishing"})[0]
                             ["pin"], pin)
            result = write_pattern(cir, compile_cir(cir), knowledge_pins=[pin], db=reopened)
            self.assertNotEqual(result, baseline)
            self.assertIn("\n- Fasten off", result)
            self.assertEqual(compare(cir, result), [])
            licence.capture_purchase(reopened, "fixture-purchase", terms={
                "allowed_uses": [], "prohibited_uses": ["private_analysis"]})
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(reopened, [pin])
            retired = knowledge.review_rule(reopened, rule["id"], reviewer="owner",
                                            decision="retire", reason="retire the rule")
            self.assertEqual(retired["decision"], "retired")
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(reopened, [pin])
            with self.assertLogs("brambleloop.cir.writer", level="ERROR"):
                self.assertEqual(write_pattern(cir, compile_cir(cir), knowledge_pins=[pin],
                                               db=reopened), baseline)

    def test_forged_approval_and_preview_cannot_activate_a_pin(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/knowledge.db", scratch=True)
            db.create_all()
            with db.session() as s:
                rule = DesignRule(key="fixture", version=1, state="approved",
                    statement={"rule": "include_finishing_checklist", "parameters": {}},
                    scope={"writer_section": "finishing"}, provenance=[], producer="analyst",
                    approved_by="owner", approved_at=utcnow())
                s.add(rule)
                s.flush()
                pin = {"rule_id": rule.id, "rule_version": rule.version,
                       "rule_digest": knowledge.rule_digest(rule), "evaluation_digest": "a" * 64}
            self.assertEqual(knowledge.applicable(db, {"writer_section": "finishing"}), [])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(db, [pin])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(db, [pin, pin])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(db, [{**pin, "rule_version": 2}])
            self.assertEqual(knowledge.verify_pins(db, []), [])

    def test_unavailable_store_logs_failure_and_applies_no_rules(self):
        db = Mock()
        db.session.side_effect = RuntimeError("database offline")
        with self.assertLogs(knowledge.__name__, level="ERROR"):
            self.assertEqual(knowledge.applicable(db, {"writer_section": "finishing"}), [])


if __name__ == "__main__":
    unittest.main()
