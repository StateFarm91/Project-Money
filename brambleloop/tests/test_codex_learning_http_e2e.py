"""Real intake, owner actions and leased jobs form one durable learning path."""
import copy
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from reportlab.pdfgen import canvas
from sqlalchemy import select

import test_v11_cc_actions as harness
from test_codex_purchase_intake import purchase
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.writer import write_pattern
from brambleloop.core.db import Database
from brambleloop.core.models import (AuditLog, BenchmarkAnalysis, BenchmarkFingerprintRecord,
                                    DesignRule, Job, JobStatus)
from brambleloop.gates.originality import code_benchmarks, record_fingerprint
from brambleloop.improve import design_knowledge
from brambleloop.products import launch0
from brambleloop.quality import design_eval
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline  # noqa: F401
from brambleloop.runtime.worker import Worker
from brambleloop.teardown import library, licence


class LearningHTTPAcceptance(unittest.TestCase):
    def test_intake_review_evaluate_approve_and_write_across_restart(self):
        stream = io.BytesIO()
        pdf = canvas.Canvas(stream)
        pdf.drawString(72, 750, "Materials")
        pdf.drawString(72, 730, "A synthetic test fixture for independent evidence.")
        pdf.drawString(72, 710, "Gauge and sizing for the invented example.")
        pdf.save()
        record = purchase()
        record["pattern_title"] = "Learning HTTP acceptance fixture"
        record["licence_terms"]["allowed_uses"] = ["private_analysis", "similarity_review"]
        with TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
                library.LIBRARY_ENV: str(Path(tmp) / "private")}):
            client, csrf = harness.session()
            self.addCleanup(client.close)
            uploaded = client.post("/api/teardown/intake",
                headers={"Authorization": f"Bearer {harness.OPS}"},
                data={"purchase_record": json.dumps(record)},
                files={"files": ("pattern.pdf", stream.getvalue(), "application/pdf")})
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            ref = uploaded.json()["ref"]
            with harness.DB.session() as s:
                jobs = list(s.scalars(select(Job).where(Job.job_type == "teardown.analyse")))
                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0].status, JobStatus.PENDING)
                fingerprint = s.scalar(select(BenchmarkFingerprintRecord).where(
                    BenchmarkFingerprintRecord.benchmark_ref == ref))
                self.assertTrue(fingerprint and fingerprint.wording_shingles)
            reopened = Database(os.environ["BRAMBLELOOP_DATABASE_URL"], scratch=True)
            self.assertTrue(Worker(reopened, name="acceptance-reader", job_types=["teardown.analyse"])
                            .run_once())
            with reopened.session() as s:
                source = s.scalar(select(BenchmarkAnalysis))
                self.assertEqual(source.observations["dimensions"]["finishing"], "absent")
                source_id = source.id
            self.assertEqual(design_knowledge.applicable(reopened, {"writer_section": "finishing"}), [])
            reviewed = harness.post(client, csrf, "/api/cc/actions/teardown.review_analysis", {
                "analysis_id": source_id, "decision": "reviewed", "reason": "independent review"})
            self.assertEqual(reviewed.status_code, 200, reviewed.text)
            queue = JobQueue(reopened)
            queue.enqueue("orchestrator", "teardown.analyse_sweep", {}, idempotency_key="http-e2e:sweep")
            self.assertTrue(Worker(reopened, name="acceptance-sweep", job_types=["teardown.analyse_sweep"])
                            .run_once())
            with reopened.session() as s:
                rule = s.scalar(select(DesignRule).where(DesignRule.state == "proposed"))
                self.assertIsNotNone(rule)
                rule_id = rule.id
            refused = harness.post(client, csrf, "/api/cc/actions/design_knowledge.review_rule", {
                "rule_id": rule_id, "decision": "approve", "reason": "missing evaluation"})
            self.assertNotEqual(refused.status_code, 200)
            cir = launch0.cir_for("basket_small")
            baseline = write_pattern(cir, compile_cir(cir))
            self.assertEqual(design_knowledge.applicable(reopened, {"writer_section": "finishing"}), [])
            licence.capture_purchase(reopened, design_eval._BENCH2_REF)
            for source_ref in (benchmark.ref for benchmark in code_benchmarks()):
                record_fingerprint(reopened, source_ref, text=(
                    "synthetic quasar nebula lantern velvet meadow cobalt river telescope "
                    "compass marigold dolphin rainforest juniper quartz"))
            queue.enqueue("orchestrator", "design_eval.sweep", {}, idempotency_key="http-e2e:eval")
            self.assertTrue(Worker(reopened, name="acceptance-eval-sweep", job_types=["design_eval.sweep"])
                            .run_once())
            self.assertTrue(Worker(reopened, name="acceptance-eval", job_types=["design_eval.evaluate"])
                            .run_once())
            with reopened.session() as s:
                evaluation_job = s.scalar(select(Job).where(Job.job_type == "design_eval.evaluate"))
                self.assertEqual(evaluation_job.outputs["state"], "passed")
                audit_id = evaluation_job.outputs["audit_id"]
                report = copy.deepcopy(s.get(AuditLog, audit_id).detail)
            report["cases"][0]["after"]["reverse_findings"] += 1
            report["cases"][0]["after"]["reverse_codes"].append("REGRESSION")
            self.assertEqual(design_eval.classify_evaluation(report), "regression")
            approved = harness.post(client, csrf, "/api/cc/actions/design_knowledge.review_rule", {
                "rule_id": rule_id, "decision": "approve", "reason": "independent review",
                "evaluation_id": audit_id})
            self.assertEqual(approved.status_code, 200, approved.text)
            pinned = design_knowledge.freeze_pins(reopened, cir, [approved.json()["result"]["pin"]])
            self.assertEqual(len(design_knowledge.verify_cir_pins(reopened, pinned)), 1)
            changed = write_pattern(pinned, compile_cir(pinned))
            self.assertNotEqual(changed, baseline)
            self.assertIn("\n- Fasten off", changed)
            from brambleloop.core.models import BenchmarkProduct
            with reopened.session() as s:
                source = s.get(BenchmarkAnalysis, source_id)
                product = s.get(BenchmarkProduct, source.benchmark_id)
                product.files = [{**product.files[0], "name": "renamed.txt"}]
            with self.assertRaises(design_knowledge.DesignKnowledgeRefused):
                design_knowledge.verify_cir_pins(reopened, pinned)


if __name__ == "__main__":
    unittest.main()
