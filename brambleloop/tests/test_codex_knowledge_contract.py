"""The A6 pin interface fails closed until complete evaluations are available."""
from tempfile import TemporaryDirectory
import copy
import unittest
from unittest.mock import Mock, patch

from brambleloop.core.db import Database
from brambleloop.core.models import BenchmarkAnalysis, BenchmarkProduct, DesignRule, utcnow
from brambleloop.improve import design_knowledge as knowledge


class KnowledgeContractTests(unittest.TestCase):
    def test_two_files_from_one_seller_do_not_count_as_independent_sources(self):
        from brambleloop.quality import design_eval
        from brambleloop.teardown import licence, review

        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/independence.db", scratch=True)
            db.create_all()
            identifiers = []
            for index in (1, 2):
                ref = f"same-seller-{index}"
                sha = str(index) * 64
                with db.session() as s:
                    product = BenchmarkProduct(ref=ref, seller="same seller", files=[
                        {"name": "fixture.pdf", "sha256": sha}])
                    s.add(product)
                    s.flush()
                    source = BenchmarkAnalysis(benchmark_id=product.id, file_sha256=sha,
                        observations={"fully_readable": True, "dimensions": {"finishing": "absent"}})
                    s.add(source)
                    s.flush()
                    identifiers.append(source.id)
                licence.capture_purchase(db, ref)
                review.review_analysis(db, identifiers[-1], reviewer="owner", decision="reviewed",
                                       reason="independent review")
            rule = knowledge.propose(db, key="same_seller", statement={
                "rule": "include_checklist_and_end_check", "parameters": {}},
                scope={"writer_section": "finishing"}, producer="analyst",
                provenance=[{"kind": "analysis", "id": ident} for ident in identifiers])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                design_eval.evaluate(db, rule["id"])

    def test_evaluated_independent_approval_changes_written_output_and_revalidates(self):
        from brambleloop.cir.compiler import compile_cir
        from brambleloop.cir.reverse import compare
        from brambleloop.cir.writer import finishing_checklist, write_pattern
        from brambleloop.gates.originality import code_benchmarks, record_fingerprint
        from brambleloop.products import launch0
        from brambleloop.quality import design_eval
        from brambleloop.teardown import licence, review
        from brambleloop.agents.registry import Registry
        from brambleloop.queue.durable import JobQueue
        from brambleloop.runtime import pipeline  # noqa: F401
        from brambleloop.runtime.worker import Worker

        with TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/knowledge.db"
            db = Database(url, scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
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
            unsupported = knowledge.propose(db, key="one_source_end_check", statement={
                "rule": "include_checklist_and_end_check", "parameters": {}},
                scope={"writer_section": "finishing"},
                provenance=[{"kind": "analysis", "id": source_id}], producer="analyst")
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                design_eval.evaluate(db, unsupported["id"])
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
            pinned = knowledge.freeze_pins(reopened, cir, [pin])
            self.assertEqual(knowledge.verify_cir_pins(reopened, pinned)[0]["pin"], pin)
            # A deployment with changed evaluation code cannot silently reuse
            # an older approval or treat that old result as current evidence.
            with patch.object(design_eval, "implementation_digest", return_value="f" * 64):
                with self.assertRaises(knowledge.DesignKnowledgeRefused):
                    knowledge.verify_cir_pins(reopened, pinned)
                with self.assertRaises(knowledge.DesignKnowledgeRefused):
                    knowledge.incumbent_for_evaluation(reopened)
            result = write_pattern(pinned, compile_cir(pinned))
            self.assertNotEqual(result, baseline)
            self.assertIn("\n- Fasten off", result)
            self.assertEqual(compare(cir, result), [])
            for slug in launch0.LAUNCH0_SLUGS:
                item = launch0.cir_for(launch0.candidate(slug).variants[0].build)
                item_plain = write_pattern(item, compile_cir(item))
                item_pinned = knowledge.freeze_pins(reopened, item, [pin])
                self.assertEqual(write_pattern(item_pinned, compile_cir(item_pinned)),
                                 finishing_checklist(item_plain))
            unavailable = Mock()
            unavailable.session.side_effect = RuntimeError("database offline")
            with self.assertLogs(knowledge.__name__, level="ERROR"):
                self.assertEqual(knowledge.write_with_verified_knowledge(
                    unavailable, pinned, compile_cir(pinned)), baseline)
            successor = knowledge.propose(reopened, key=rule["key"], statement={
                "rule": "include_finishing_checklist", "parameters": {}},
                scope={"writer_section": "finishing"},
                provenance=[{"kind": "analysis", "id": source_id}], producer="analyst2",
                supersedes=rule["id"])
            repeated_rule = design_eval.evaluate(reopened, successor["id"])
            self.assertEqual(repeated_rule["incumbent_pins"], [pin])
            self.assertEqual(repeated_rule["state"], "no_improvement")
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(reopened, successor["id"], reviewer="owner", decision="approve",
                                      reason="independent review", evaluation_id=repeated_rule["audit_id"])
            unrelated = knowledge.propose(reopened, key="unrelated", statement={
                "rule": "include_finishing_checklist", "parameters": {}},
                scope={"writer_section": "finishing"},
                provenance=[{"kind": "analysis", "id": source_id}], producer="analyst2")
            with self.assertRaises(design_eval.DesignEvaluationRefused):
                design_eval.evaluate(reopened, unrelated["id"])
            knowledge.review_rule(reopened, successor["id"], reviewer="owner", decision="reject",
                                  reason="no measured improvement")
            with reopened.session() as s:
                duplicate = BenchmarkProduct(ref="duplicate-fixture", seller="another-seller",
                    files=[{"name": "same.pdf", "sha256": sha}])
                s.add(duplicate)
                s.flush()
                duplicate_source = BenchmarkAnalysis(benchmark_id=duplicate.id, file_sha256=sha,
                    observations={"fully_readable": True, "dimensions": {"finishing": "absent"}})
                s.add(duplicate_source)
                s.flush()
                duplicate_id = duplicate_source.id
            licence.capture_purchase(reopened, "duplicate-fixture")
            review.review_analysis(reopened, duplicate_id, reviewer="independent-reviewer",
                                   decision="reviewed", reason="reviewed duplicate evidence")
            self.assertEqual(knowledge.propose_from_analysis(reopened, duplicate_id)["reason"],
                             "source_not_independent")
            record_fingerprint(reopened, "duplicate-fixture", text=(
                "xylophone quasar nebula orbit lantern velvet meadow cobalt river "
                "telescope compass marigold dolphin rainforest juniper quartz"))
            with reopened.session() as s:
                second_product = BenchmarkProduct(ref="second-fixture", seller="other-seller",
                    files=[{"name": "reference.pdf", "sha256": "c" * 64}])
                s.add(second_product)
                s.flush()
                second_source = BenchmarkAnalysis(benchmark_id=second_product.id, file_sha256="c" * 64,
                    observations={"fully_readable": True, "dimensions": {"finishing": "absent"}})
                s.add(second_source)
                s.flush()
                second_id = second_source.id
            licence.capture_purchase(reopened, "second-fixture")
            review.review_analysis(reopened, second_id, reviewer="another-independent-reviewer",
                                   decision="reviewed", reason="reviewed second observation")
            record_fingerprint(reopened, "second-fixture", text=(
                "synthetic azalea orbit meadow silver cloud lantern marble violet sunflower"))
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(reopened, [pin])  # corpus changed: production use holds
            improved = knowledge.propose_from_analysis(reopened, second_id)
            self.assertTrue(improved["proposed"])
            JobQueue(reopened).enqueue("orchestrator", "design_eval.sweep", {},
                                       idempotency_key="successor-eval-sweep")
            self.assertTrue(Worker(reopened, name="successor-sweep", job_types=["design_eval.sweep"])
                            .run_once())
            self.assertTrue(Worker(reopened, name="successor-evaluator",
                                   job_types=["design_eval.evaluate"]).run_once())
            improved_eval = design_eval.evaluate(reopened, improved["id"])
            self.assertFalse(improved_eval["created"])
            self.assertEqual(improved_eval["incumbent_pins"], [pin])
            self.assertEqual(improved_eval["state"], "passed", improved_eval)
            upgraded = knowledge.review_rule(reopened, improved["id"], reviewer="owner",
                decision="approve", reason="reviewed improvement", evaluation_id=improved_eval["audit_id"])
            new_pin = upgraded["pin"]
            new_cir = knowledge.freeze_pins(reopened, cir, [new_pin])
            enhanced = write_pattern(new_cir, compile_cir(new_cir))
            self.assertIn("Gently tug each woven end", enhanced)
            self.assertNotEqual(enhanced, result)
            self.assertEqual(compare(cir, enhanced), [])
            self.assertEqual(knowledge.verify_cir_pins(reopened, new_cir)[0]["pin"], new_pin)
            for slug in launch0.LAUNCH0_SLUGS:
                item = launch0.cir_for(launch0.candidate(slug).variants[0].build)
                item_plain = write_pattern(item, compile_cir(item))
                item_pinned = knowledge.freeze_pins(reopened, item, [new_pin])
                actual = write_pattern(item_pinned, compile_cir(item_pinned))
                self.assertEqual(actual, finishing_checklist(item_plain, check_ends=True))
                self.assertEqual(compare(item, actual), [])
            from brambleloop.quality import design_revalidation
            record_fingerprint(reopened, "second-fixture", text=(
                "synthetic amber violet waterfall cedar ocean sunrise meadow quasar"))
            revalidation = design_revalidation.evaluate(reopened, improved["id"])
            self.assertEqual(revalidation["state"], "passed", revalidation)
            self.assertEqual(revalidation["incumbent_pins"], [pin])
            from brambleloop.core.models import AuditLog
            with reopened.session() as s:
                historical = s.get(AuditLog, improved_eval["audit_id"]).detail
                forged_baseline = copy.deepcopy(revalidation)
                forged_baseline["incumbent_pins"] = []
                self.assertFalse(design_revalidation.no_historical_regression(historical, forged_baseline))
            reaffirmed = knowledge.review_rule(reopened, improved["id"], reviewer="owner",
                decision="reapprove", reason="reviewed current evidence",
                evaluation_id=revalidation["audit_id"])
            new_cir = knowledge.repin_revalidated_cir(reopened, new_cir, [reaffirmed["pin"]],
                                                       new_version="2.0.0")
            new_pin = reaffirmed["pin"]
            self.assertEqual(knowledge.verify_cir_pins(reopened, new_cir)[0]["pin"], new_pin)
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(reopened, [pin])
            licence.capture_purchase(reopened, "fixture-purchase", terms={
                "allowed_uses": [], "prohibited_uses": ["private_analysis"]})
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(reopened, [new_pin])
            retired = knowledge.review_rule(reopened, improved["id"], reviewer="owner",
                                            decision="retire", reason="retire the rule")
            self.assertEqual(retired["decision"], "retired")
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(reopened, [pin])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_cir_pins(reopened, pinned)
            with self.assertLogs(knowledge.__name__, level="ERROR"):
                self.assertEqual(knowledge.write_with_verified_knowledge(
                    reopened, pinned, compile_cir(pinned)), baseline)

    def test_forged_approval_and_preview_cannot_activate_a_pin(self):
        from brambleloop.cir import knowledge as cir_knowledge
        from brambleloop.cir.compiler import compile_cir
        from brambleloop.cir.writer import write_pattern
        from brambleloop.products import launch0

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
            cir = launch0.cir_for("basket_small")
            baseline = write_pattern(cir, compile_cir(cir))
            cir.provenance.primitives_used += (cir_knowledge.marker(
                "include_finishing_checklist", pin),)
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_cir_pins(db, cir)
            with self.assertLogs(knowledge.__name__, level="ERROR"):
                self.assertEqual(knowledge.write_with_verified_knowledge(
                    db, cir, compile_cir(cir)), baseline)
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
