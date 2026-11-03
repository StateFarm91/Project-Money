"""A stale rule can be remeasured, but never silently reapproved or repinned."""
import tempfile
import unittest
import copy
from unittest.mock import patch
from pathlib import Path

from sqlalchemy import select
from brambleloop.agents.registry import Registry
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.writer import write_pattern
from brambleloop.core.db import Database
from brambleloop.core.models import (AuditLog, BenchmarkAnalysis, BenchmarkProduct, Job, JobStatus,
                                    PatternVersion, Product)
from brambleloop.gates.originality import code_benchmarks, record_fingerprint
from brambleloop.improve import design_knowledge as knowledge
from brambleloop.products import launch0
from brambleloop.quality import design_eval, design_revalidation
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline  # noqa: F401
from brambleloop.runtime.worker import Worker
from brambleloop.teardown import licence, review


class RevalidationTests(unittest.TestCase):
    def test_stale_rule_is_remeasured_reapproved_and_explicitly_repinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/revalidation.sqlite"
            db = Database(url, scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                product = BenchmarkProduct(ref="revalidation-fixture", seller="fixture", files=[
                    {"name": "reference.pdf", "sha256": "a" * 64}])
                s.add(product)
                s.flush()
                source = BenchmarkAnalysis(benchmark_id=product.id, file_sha256="a" * 64,
                    observations={"fully_readable": True, "dimensions": {"finishing": "absent"}})
                s.add(source)
                s.flush()
                source_id = source.id
            licence.capture_purchase(db, "revalidation-fixture")
            review.review_analysis(db, source_id, reviewer="owner", decision="reviewed", reason="review")
            proposal = knowledge.propose_from_analysis(db, source_id)
            refs = ["revalidation-fixture", *(b.ref for b in code_benchmarks())]
            for ref in refs:
                record_fingerprint(db, ref, text="quasar velvet orchid comet azure river dolphin forest")
            evidence = design_eval.evaluate(db, proposal["id"])
            self.assertEqual(evidence["state"], "passed")
            approved = knowledge.review_rule(db, proposal["id"], reviewer="owner", decision="approve",
                reason="independent review", evaluation_id=evidence["audit_id"])
            old_pin = approved["pin"]
            cir = launch0.cir_for("basket_small")
            frozen = knowledge.freeze_pins(db, cir, [old_pin])
            baseline_text = write_pattern(frozen, compile_cir(frozen))
            queue = JobQueue(db)
            queue.enqueue("orchestrator", "design_eval.sweep", {}, idempotency_key="revalidate:fresh")
            self.assertTrue(Worker(db, name="fresh-sweep", job_types=["design_eval.sweep"]).run_once())
            with db.session() as s:
                sweep = s.scalar(select(Job).where(Job.idempotency_key == "revalidate:fresh"))
                self.assertEqual(sweep.outputs["queued"], 0)
            with db.session() as s:
                audit = s.get(AuditLog, evidence["audit_id"])
                original = copy.deepcopy(audit.detail)
                altered = copy.deepcopy(audit.detail)
                altered["cases"][0]["after"]["finishing_actions_listed"] += 1
                audit.detail = altered
            with self.assertRaises(design_eval.DesignEvaluationRefused):
                design_revalidation.evaluation_key(db, proposal["id"])
            with db.session() as s:
                s.get(AuditLog, evidence["audit_id"]).detail = original
            record_fingerprint(db, "revalidation-fixture", text="saturn river cedar violet map lantern meadow")
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_cir_pins(db, frozen)
            queue.enqueue("orchestrator", "design_eval.sweep", {}, idempotency_key="revalidate:one")
            self.assertTrue(Worker(db, name="sweep", job_types=["design_eval.sweep"]).run_once())
            reopened = Database(url, scratch=True)
            self.assertTrue(Worker(reopened, name="evaluate", job_types=["design_eval.evaluate"]).run_once())
            with reopened.session() as s:
                job = s.scalar(select(Job).where(Job.job_type == "design_eval.evaluate"))
                self.assertEqual(job.status, JobStatus.DONE, job.last_error)
                self.assertEqual(job.outputs["state"], "passed")
                evaluation_id = job.outputs["audit_id"]
                self.assertNotIn("Fasten off", str(s.get(AuditLog, evaluation_id).detail))
            # Evaluation alone cannot update the approved pin.
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_cir_pins(reopened, frozen)
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(reopened, proposal["id"], reviewer="teardown_analyst",
                    decision="reapprove", reason="self review", evaluation_id=evaluation_id)
            changed = knowledge.review_rule(reopened, proposal["id"], reviewer="owner",
                decision="reapprove", reason="review current evidence", evaluation_id=evaluation_id)
            new_pin = changed["pin"]
            self.assertNotEqual(old_pin["evaluation_digest"], new_pin["evaluation_digest"])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_cir_pins(reopened, frozen)
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.repin_revalidated_cir(reopened, frozen, [new_pin], new_version=frozen.version)
            with reopened.session() as s:
                product = Product(slug=cir.slug, title=cir.title)
                s.add(product)
                s.flush()
                s.add(PatternVersion(product_id=product.id, version="9.0.0", cir_json=cir.to_dict()))
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.repin_revalidated_cir(reopened, frozen, [new_pin], new_version="9.0.0")
            repinned = knowledge.repin_revalidated_cir(reopened, frozen, [new_pin], new_version="2.0.0")
            self.assertEqual(knowledge.verify_cir_pins(reopened, repinned)[0]["pin"], new_pin)
            # The public repin path itself must durably bind the new identity;
            # removing its marker before a real worker boundary must not erase it.
            stripped = copy.deepcopy(repinned)
            stripped.provenance.primitives_used = tuple(
                p for p in stripped.provenance.primitives_used
                if not p.startswith("learning_rule:"))
            revise = JobQueue(reopened).enqueue("crochet_engineer", "cir.revise",
                                                {"cir": stripped.to_dict()})
            self.assertTrue(Worker(reopened, name="repin-check", job_types=["cir.revise"]).run_once())
            with reopened.session() as s:
                result = s.get(Job, revise.id)
                self.assertEqual(result.status, JobStatus.DONE, result.last_error)
                self.assertEqual(result.outputs.get("refused"), "design_knowledge")
                self.assertIn("markers are missing", result.outputs["reasons"][0])
            self.assertIn("\n- Fasten off", write_pattern(repinned, compile_cir(repinned)))
            self.assertIn("\n- Fasten off", baseline_text)
            self.assertNotEqual(repinned.fingerprint, frozen.fingerprint)
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(reopened, proposal["id"], reviewer="owner", decision="reapprove",
                    reason="duplicate", evaluation_id=evaluation_id)

            # A second changed corpus recovers through the full authenticated chain.
            record_fingerprint(reopened, "revalidation-fixture",
                               text="orchid silver river nebula basket horizon cedar")
            queue = JobQueue(reopened)
            queue.enqueue("orchestrator", "design_eval.sweep", {}, idempotency_key="revalidate:two")
            self.assertTrue(Worker(reopened, name="sweep-again", job_types=["design_eval.sweep"])
                            .run_once())
            self.assertTrue(Worker(reopened, name="evaluate-again", job_types=["design_eval.evaluate"])
                            .run_once())
            with reopened.session() as s:
                job = s.scalars(select(Job).where(Job.job_type == "design_eval.evaluate")
                                .order_by(Job.id.desc())).first()
                self.assertEqual(job.outputs["state"], "passed", job.last_error)
                second_id = job.outputs["audit_id"]
            second = knowledge.review_rule(reopened, proposal["id"], reviewer="owner",
                decision="reapprove", reason="review updated evidence", evaluation_id=second_id)
            repinned_again = knowledge.repin_revalidated_cir(reopened, frozen, [second["pin"]],
                                                             new_version="3.0.0")
            self.assertEqual(knowledge.verify_cir_pins(reopened, repinned_again)[0]["pin"],
                             second["pin"])
            licence.capture_purchase(reopened, "revalidation-fixture", terms={"allowed_uses": [],
                                     "prohibited_uses": ["private_analysis"]})
            with self.assertRaises(design_eval.DesignEvaluationRefused):
                design_revalidation.evaluation_key(reopened, proposal["id"])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.repin_revalidated_cir(reopened, frozen, [second["pin"]],
                                                new_version="4.0.0")
            licence.capture_purchase(reopened, "revalidation-fixture", terms={
                "allowed_uses": list(licence.PRIVATE_RESEARCH_USES),
                "prohibited_uses": list(licence.PUBLISHING_USES)})

            # A new technical defect is detected by the real evaluator and blocks reapproval.
            record_fingerprint(reopened, "revalidation-fixture",
                               text="amethyst alpine meadow lantern bronze nebula quartz")
            queue.enqueue("orchestrator", "design_eval.sweep", {}, idempotency_key="revalidate:regression")
            self.assertTrue(Worker(reopened, name="regression-sweep", job_types=["design_eval.sweep"])
                            .run_once())
            measure = design_eval.measure_written_case
            def broken(cir, text, **kwargs):
                result = measure(cir, text, **kwargs)
                # Both current baseline and candidate acquire the same new
                # defect. A before/after-only comparison would miss it.
                result["reverse_findings"] += 1
                result["reverse_codes"].append("INJECTED_REGRESSION")
                return result
            with patch.object(design_eval, "measure_written_case", side_effect=broken):
                self.assertTrue(Worker(reopened, name="regressed", job_types=["design_eval.evaluate"])
                                .run_once())
            with reopened.session() as s:
                job = s.scalars(select(Job).where(Job.job_type == "design_eval.evaluate")
                                .order_by(Job.id.desc())).first()
                self.assertEqual(job.outputs["state"], "regression", job.last_error)
                failed_id = job.outputs["audit_id"]
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(reopened, proposal["id"], reviewer="owner", decision="reapprove",
                    reason="must reject regression", evaluation_id=failed_id)
            # Forging a passing label cannot erase the measured historical regression.
            with reopened.session() as s:
                audit = s.get(AuditLog, failed_id)
                audit.detail = {**audit.detail, "state": "passed", "approval_evidence_complete": True}
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(reopened, proposal["id"], reviewer="owner", decision="reapprove",
                    reason="forged pass must fail", evaluation_id=failed_id)
            record_fingerprint(reopened, "revalidation-fixture",
                               text="willow coral star ocean frost planet indigo")
            with patch.object(design_eval, "implementation_digest", return_value="f" * 64):
                queue.enqueue("orchestrator", "design_eval.sweep", {},
                              idempotency_key="revalidate:implementation")
                self.assertTrue(Worker(reopened, name="implementation-sweep",
                                       job_types=["design_eval.sweep"]).run_once())
                self.assertTrue(Worker(reopened, name="implementation-eval",
                                       job_types=["design_eval.evaluate"]).run_once())
                with reopened.session() as s:
                    job = s.scalars(select(Job).where(Job.job_type == "design_eval.evaluate")
                                    .order_by(Job.id.desc())).first()
                    self.assertEqual(job.outputs["state"], "passed", job.last_error)
                    implementation_id = job.outputs["audit_id"]
                third = knowledge.review_rule(reopened, proposal["id"], reviewer="owner",
                    decision="reapprove", reason="review implementation change",
                    evaluation_id=implementation_id)
                self.assertEqual(knowledge.verify_pins(reopened, [third["pin"]])[0]["pin"],
                                 third["pin"])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(reopened, [third["pin"]])


if __name__ == "__main__":
    unittest.main()
