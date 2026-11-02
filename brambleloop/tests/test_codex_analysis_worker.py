"""A real worker consumes one durable, deduplicated reference-analysis job."""
import hashlib
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import unittest

from sqlalchemy import select

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import (BenchmarkAnalysis, BenchmarkListing, BenchmarkProduct,
                                     DesignRule, Incident, Job, JobStatus, utcnow)
from brambleloop.intel import benchmarks
from brambleloop.products.builder import for_slug
from brambleloop.publish.pdf import build_pattern_pdf
from brambleloop.runtime import pipeline  # noqa: F401 -- registers actual handlers
from brambleloop.runtime.worker import Worker
from brambleloop.queue.durable import JobQueue
from brambleloop.teardown import intake, jobs, library, licence, review


class AnalysisWorkerTests(unittest.TestCase):
    def test_sweep_redrives_dead_analysis_after_source_is_restored(self):
        from reportlab.pdfgen import canvas

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            folder = root / "recovery-purchase"
            folder.mkdir(parents=True)
            stream = io.BytesIO()
            pdf = canvas.Canvas(stream)
            pdf.drawString(72, 750, "Synthetic materials and gauge for this test fixture.")
            pdf.save()
            data = stream.getvalue()
            db = Database(f"sqlite:///{tmp}/recovery.db", scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                product = BenchmarkProduct(ref="recovery-purchase", seller="test", files=[
                    {"name": "pattern.pdf", "sha256": hashlib.sha256(data).hexdigest()}])
                s.add(product)
                s.flush()
                product_id = product.id
            licence.capture_purchase(db, "recovery-purchase")
            jobs.enqueue_purchase(db, product_id)
            with db.session() as s:
                job = s.scalar(select(Job).where(Job.job_type == "teardown.analyse"))
                job.max_attempts = 1
            with mock.patch.dict(os.environ, {library.LIBRARY_ENV: str(root)}):
                self.assertTrue(Worker(db, name="fails", job_types=["teardown.analyse"]).run_once())
                with db.session() as s:
                    self.assertEqual(s.scalar(select(Job).where(
                        Job.job_type == "teardown.analyse")).status, JobStatus.DEAD)
                (folder / "pattern.pdf").write_bytes(data)
                JobQueue(db).enqueue("orchestrator", "teardown.analyse_sweep", {},
                                     idempotency_key="retry-dead-sweep")
                self.assertTrue(Worker(db, name="sweep", job_types=["teardown.analyse_sweep"])
                                .run_once())
                with db.session() as s:
                    sweep = s.scalar(select(Job).where(Job.job_type == "teardown.analyse_sweep"))
                    self.assertEqual(sweep.outputs["requeued"], 1)
                self.assertTrue(Worker(db, name="recovered", job_types=["teardown.analyse"]).run_once())
            with db.session() as s:
                self.assertEqual(s.scalar(select(Job).where(
                    Job.job_type == "teardown.analyse")).status, JobStatus.DONE)
                self.assertEqual(len(list(s.scalars(select(BenchmarkAnalysis)))), 1)

    def test_licence_revoked_during_read_cannot_persist_analysis(self):
        from reportlab.pdfgen import canvas
        from brambleloop.teardown import analysis_store

        with TemporaryDirectory() as tmp:
            stream = io.BytesIO()
            pdf = canvas.Canvas(stream)
            pdf.drawString(72, 750, "Synthetic test document with materials and gauge.")
            pdf.save()
            data = stream.getvalue()
            sha = hashlib.sha256(data).hexdigest()
            db = Database(f"sqlite:///{tmp}/revoked.db", scratch=True)
            db.create_all()
            with db.session() as s:
                product = BenchmarkProduct(ref="revoked", seller="test",
                    files=[{"name": "pattern.pdf", "sha256": sha}])
                s.add(product)
                s.flush()
                product_id = product.id
            licence.capture_purchase(db, "revoked", terms={"allowed_uses": ["private_analysis"],
                                     "prohibited_uses": []})

            def revoke_during_read(*args, **kwargs):
                licence.capture_purchase(db, "revoked", terms={"allowed_uses": [],
                                         "prohibited_uses": ["private_analysis"]})
                return data

            with mock.patch.object(library, "retrieve", side_effect=revoke_during_read):
                with self.assertRaises(analysis_store.AnalysisRefused):
                    analysis_store.analyse_file(db, product_id, sha)
            with db.session() as s:
                self.assertIsNone(s.scalar(select(BenchmarkAnalysis)))

    def test_reviewed_observation_proposes_only_one_unapproved_rule(self):
        from reportlab.pdfgen import canvas

        with TemporaryDirectory() as tmp:
            stream = io.BytesIO()
            pdf = canvas.Canvas(stream)
            pdf.drawString(72, 750, "Materials")
            pdf.drawString(72, 730, "A synthetic fixture with enough text to read.")
            pdf.drawString(72, 710, "Gauge and sizing are written in this invented example.")
            pdf.save()
            data = stream.getvalue()
            root = Path(tmp) / "private"
            url = f"sqlite:///{tmp}/end-to-end.db"
            db = Database(url, scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref="1234",
                    title="Fixture", pod="blankets", product_type="pattern", price_cad=8.5,
                    media_count=0, url="https://example.com/1234", detail={}))
            with mock.patch.dict(os.environ, {library.LIBRARY_ENV: str(root)}):
                received = intake.receive(db, "1234", [("pattern.pdf", data)],
                    env={library.LIBRARY_ENV: str(root)}, mirror_files=False, paid_cad=8.5)
                benchmark_id = received["product_id"]
                self.assertTrue(Worker(db, name="reader", job_types=["teardown.analyse"]).run_once())
                with db.session() as s:
                    analysis = s.scalar(select(BenchmarkAnalysis))
                    analysis_id = analysis.id
                    self.assertEqual(analysis.observations["dimensions"]["finishing"], "absent")
                    self.assertFalse(analysis.observations["architecture_complete"])
                    self.assertTrue(analysis.observations["architecture_withheld"])
                    gap = s.scalar(select(Incident).where(
                        Incident.signature == f"learning.knowledge_gap:analysis:{analysis_id}"))
                    self.assertEqual(gap.detail["state"], "review_required")
                queue = JobQueue(db)
                queue.enqueue("orchestrator", "teardown.analyse_sweep", {}, idempotency_key="sweep:1")
                self.assertTrue(Worker(db, name="sweep1", job_types=["teardown.analyse_sweep"]).run_once())
                with db.session() as s:
                    self.assertEqual(list(s.scalars(select(DesignRule))), [])
                with self.assertRaises(review.ReviewRefused):
                    review.review_analysis(db, analysis_id, reviewer="teardown_analyst",
                                           decision="reviewed", reason="self review")
                review.review_analysis(db, analysis_id, reviewer="owner", decision="reviewed",
                                       reason="independent observation review")
                reopened = Database(url, scratch=True)
                queue = JobQueue(reopened)
                for n in (2, 3):
                    queue.enqueue("orchestrator", "teardown.analyse_sweep", {},
                                  idempotency_key=f"sweep:{n}")
                    self.assertTrue(Worker(reopened, name=f"sweep{n}",
                                           job_types=["teardown.analyse_sweep"]).run_once())
                with reopened.session() as s:
                    rules = list(s.scalars(select(DesignRule)))
                    self.assertEqual(len(rules), 1)
                    self.assertEqual(rules[0].state, "proposed")
                    self.assertEqual(rules[0].provenance, [{"kind": "analysis", "id": analysis_id}])
                    sweeps = list(s.scalars(select(Job).where(
                        Job.job_type == "teardown.analyse_sweep").order_by(Job.id)))
                    self.assertEqual([job.outputs["work_done"] for job in sweeps], [0, 1, 0])
                    rule_id = rules[0].id
                    purchase_ref = s.get(BenchmarkProduct, benchmark_id).ref

                from brambleloop.gates.originality import code_benchmarks, record_fingerprint
                from brambleloop.improve import design_knowledge
                from brambleloop.cir.compiler import compile_cir
                from brambleloop.cir.writer import write_pattern
                from brambleloop.products import launch0

                for benchmark in code_benchmarks():
                    record_fingerprint(reopened, benchmark.ref, text=(
                        "synthetic quasar nebula lantern velvet meadow cobalt river telescope "
                        "compass marigold dolphin rainforest juniper quartz"))
                record_fingerprint(reopened, purchase_ref, text=(
                    "Materials A synthetic fixture with enough text to read. "
                    "Gauge and sizing are written in this invented example."))
                cir = launch0.cir_for("basket_small")
                baseline = write_pattern(cir, compile_cir(cir))
                self.assertEqual(design_knowledge.applicable(reopened,
                                 {"writer_section": "finishing"}), [])
                queue.enqueue("orchestrator", "design_eval.sweep", {}, idempotency_key="eval:sweep")
                self.assertTrue(Worker(reopened, name="eval-sweep", job_types=["design_eval.sweep"])
                                .run_once())
                with reopened.session() as s:
                    queued_eval = s.scalar(select(Job).where(Job.job_type == "design_eval.evaluate"))
                    queued_eval.max_attempts = 1
                with mock.patch("brambleloop.quality.design_eval.evaluate",
                                side_effect=OSError("temporary unavailable fixture")):
                    self.assertTrue(Worker(reopened, name="eval-fails",
                                           job_types=["design_eval.evaluate"]).run_once())
                with reopened.session() as s:
                    self.assertEqual(s.scalar(select(Job).where(
                        Job.job_type == "design_eval.evaluate")).status, JobStatus.DEAD)
                queue.enqueue("orchestrator", "design_eval.sweep", {}, idempotency_key="eval:retry")
                self.assertTrue(Worker(reopened, name="eval-recovery", job_types=["design_eval.sweep"])
                                .run_once())
                with reopened.session() as s:
                    recovered = s.scalar(select(Job).where(Job.idempotency_key == "eval:retry"))
                    self.assertEqual(recovered.outputs["requeued"], 1)
                self.assertTrue(Worker(reopened, name="evaluator", job_types=["design_eval.evaluate"])
                                .run_once())
                with reopened.session() as s:
                    evaluation_job = s.scalar(select(Job).where(Job.job_type == "design_eval.evaluate"))
                    self.assertEqual(evaluation_job.status, JobStatus.DONE, evaluation_job.last_error)
                    self.assertEqual(evaluation_job.outputs["state"], "passed")
                    evaluation_id = evaluation_job.outputs["audit_id"]
                approved = design_knowledge.review_rule(reopened, rule_id, reviewer="owner",
                    decision="approve", reason="independent review", evaluation_id=evaluation_id)
                pin = approved["pin"]
                pinned = design_knowledge.freeze_pins(reopened, cir, [pin])
                self.assertEqual(design_knowledge.verify_cir_pins(reopened, pinned)[0]["pin"], pin)
                written = write_pattern(pinned, compile_cir(pinned))
                self.assertNotEqual(written, baseline)
                self.assertIn("\n- Fasten off", written)
                queue.enqueue("orchestrator", "teardown.analyse_sweep", {},
                              idempotency_key="gap:resolved")
                self.assertTrue(Worker(reopened, name="gap-resolve",
                                       job_types=["teardown.analyse_sweep"]).run_once())
                signature = f"learning.knowledge_gap:analysis:{analysis_id}"
                with reopened.session() as s:
                    gap = s.scalar(select(Incident).where(Incident.signature == signature))
                    self.assertTrue(gap.resolved)
                with reopened.session() as s:
                    source = s.get(BenchmarkAnalysis, analysis_id)
                    source.observations = {**source.observations, "pages": 999}
                with self.assertRaises(design_knowledge.DesignKnowledgeRefused):
                    design_knowledge.verify_pins(reopened, [pin])
                queue.enqueue("orchestrator", "teardown.analyse_sweep", {},
                              idempotency_key="gap:reopened")
                self.assertTrue(Worker(reopened, name="gap-reopen",
                                       job_types=["teardown.analyse_sweep"]).run_once())
                with reopened.session() as s:
                    gaps = list(s.scalars(select(Incident).where(Incident.signature == signature)))
                    self.assertEqual(len(gaps), 2)
                    self.assertEqual(sum(not gap.resolved for gap in gaps), 1)
                self.assertEqual(design_knowledge.propose_from_analysis(reopened, analysis_id)
                                 ["reason"], "not_reviewed")

    def test_real_intake_queues_once_and_worker_persists_analysis(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            url = f"sqlite:///{tmp}/intake.db"
            db = Database(url, scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref="1234",
                    title="Fixture", pod="blankets", product_type="pattern", price_cad=8.5,
                    media_count=0, url="https://example.com/1234", detail={}))
            data = build_pattern_pdf(for_slug("cloudline-baby-blanket")).pdf_bytes
            env = {library.LIBRARY_ENV: str(root)}
            with mock.patch.dict(os.environ, env):
                first = intake.receive(db, "1234", [("pattern.pdf", data)], env=env,
                                       mirror_files=False, paid_cad=8.5)
                intake.receive(db, "1234", [("pattern.pdf", data)], env=env,
                               mirror_files=False, paid_cad=8.5)
                reopened = Database(url, scratch=True)
                self.assertTrue(Worker(reopened, job_types=["teardown.analyse"]).run_once())
            with reopened.session() as s:
                queued = list(s.scalars(select(Job).where(Job.job_type == "teardown.analyse")))
                self.assertEqual(len(queued), 1)
                self.assertEqual(queued[0].status, JobStatus.DONE, queued[0].last_error)
                self.assertIsNotNone(s.scalar(select(BenchmarkAnalysis).where(
                    BenchmarkAnalysis.benchmark_id == first["product_id"])))
                self.assertEqual(s.get(BenchmarkProduct, first["product_id"]).teardown_state,
                                 "analysed")

    def test_unreadable_document_requires_analyst_and_proposes_no_rule(self):
        from reportlab.pdfgen import canvas

        with TemporaryDirectory() as tmp:
            stream = io.BytesIO()
            pdf = canvas.Canvas(stream)
            pdf.showPage()
            pdf.save()
            data = stream.getvalue()
            root = Path(tmp) / "private"
            folder = root / "unreadable"
            folder.mkdir(parents=True)
            (folder / "pattern.pdf").write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            db = Database(f"sqlite:///{tmp}/unreadable.db", scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                row = BenchmarkProduct(ref="unreadable", seller="test", teardown_state="queued",
                    files=[{"name": "pattern.pdf", "sha256": sha}])
                s.add(row)
                s.flush()
                benchmark_id = row.id
            licence.capture_purchase(db, "unreadable")
            jobs.enqueue_purchase(db, benchmark_id)
            with mock.patch.dict(os.environ, {library.LIBRARY_ENV: str(root)}):
                self.assertTrue(Worker(db, name="reader", job_types=["teardown.analyse"]).run_once())
            with db.session() as s:
                self.assertEqual(s.get(BenchmarkProduct, benchmark_id).teardown_state, "needs_analyst")
                self.assertEqual(list(s.scalars(select(DesignRule))), [])

    def test_real_worker_runs_deduplicated_job_on_reopened_database(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            folder = root / "test-purchase"
            folder.mkdir(parents=True)
            data = build_pattern_pdf(for_slug("cloudline-baby-blanket")).pdf_bytes
            (folder / "pattern.pdf").write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            url = f"sqlite:///{tmp}/worker.db"
            db = Database(url, scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                row = BenchmarkProduct(ref="test-purchase", seller="test", teardown_state="queued",
                                       files=[{"name": "pattern.pdf", "sha256": sha}])
                s.add(row)
                s.flush()
                benchmark_id = row.id
            self.assertEqual(jobs.enqueue_purchase(db, benchmark_id)["reason"],
                             "licence_not_recorded")
            licence.capture_purchase(db, "test-purchase")
            self.assertEqual(jobs.enqueue_purchase(db, benchmark_id)["queued"], 1)
            self.assertEqual(jobs.enqueue_purchase(db, benchmark_id)["existing"], 1)
            reopened = Database(url, scratch=True)
            with mock.patch.dict(os.environ, {library.LIBRARY_ENV: str(root)}):
                worker = Worker(reopened, name="test-worker", job_types=["teardown.analyse"])
                self.assertTrue(worker.run_once())
            with reopened.session() as s:
                job = s.scalar(select(Job).where(Job.job_type == "teardown.analyse"))
                self.assertEqual(job.status, JobStatus.DONE, job.last_error)
                analysis = s.scalar(select(BenchmarkAnalysis).where(
                    BenchmarkAnalysis.benchmark_id == benchmark_id))
                self.assertIsNotNone(analysis)
                self.assertEqual(analysis.file_sha256, sha)
                # Simulate a crash after persistence but before progress was reconciled.
                s.get(BenchmarkProduct, benchmark_id).teardown_state = "queued"
            JobQueue(reopened).enqueue("orchestrator", "teardown.analyse_sweep", {},
                                       idempotency_key="recovery:sweep")
            self.assertTrue(Worker(reopened, name="recovery", job_types=["teardown.analyse_sweep"]).run_once())
            with reopened.session() as s:
                self.assertEqual(s.get(BenchmarkProduct, benchmark_id).teardown_state, "analysed")

    def test_failed_read_retries_after_file_is_restored(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            folder = root / "test-purchase"
            folder.mkdir(parents=True)
            data = build_pattern_pdf(for_slug("cloudline-baby-blanket")).pdf_bytes
            sha = hashlib.sha256(data).hexdigest()
            url = f"sqlite:///{tmp}/retry.db"
            db = Database(url, scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                row = BenchmarkProduct(ref="test-purchase", seller="test", teardown_state="queued",
                    files=[{"name": "pattern.pdf", "sha256": sha}])
                s.add(row)
                s.flush()
                benchmark_id = row.id
            licence.capture_purchase(db, "test-purchase")
            jobs.enqueue_purchase(db, benchmark_id)
            with mock.patch.dict(os.environ, {library.LIBRARY_ENV: str(root)}):
                self.assertTrue(Worker(db, name="first", job_types=["teardown.analyse"]).run_once())
                with db.session() as s:
                    job = s.scalar(select(Job).where(Job.job_type == "teardown.analyse"))
                    self.assertEqual(job.status, JobStatus.FAILED)
                    job.run_after = utcnow()  # advance the retry clock without sleeping
                (folder / "pattern.pdf").write_bytes(data)
                reopened = Database(url, scratch=True)
                self.assertTrue(Worker(reopened, name="restarted", job_types=["teardown.analyse"]).run_once())
            with reopened.session() as s:
                job = s.scalar(select(Job).where(Job.job_type == "teardown.analyse"))
                self.assertEqual(job.status, JobStatus.DONE, job.last_error)
                self.assertEqual(job.attempts, 2)
                self.assertEqual(len(list(s.scalars(select(BenchmarkAnalysis)))), 1)


if __name__ == "__main__":
    unittest.main()
