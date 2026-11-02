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
                                     DesignRule, Job, JobStatus, utcnow)
from brambleloop.intel import benchmarks
from brambleloop.products.builder import for_slug
from brambleloop.publish.pdf import build_pattern_pdf
from brambleloop.runtime import pipeline  # noqa: F401 -- registers actual handlers
from brambleloop.runtime.worker import Worker
from brambleloop.queue.durable import JobQueue
from brambleloop.teardown import intake, jobs, library, licence, review


class AnalysisWorkerTests(unittest.TestCase):
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
            folder = root / "test-purchase"
            folder.mkdir(parents=True)
            (folder / "pattern.pdf").write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            url = f"sqlite:///{tmp}/end-to-end.db"
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
                self.assertTrue(Worker(db, name="reader", job_types=["teardown.analyse"]).run_once())
                with db.session() as s:
                    analysis = s.scalar(select(BenchmarkAnalysis))
                    analysis_id = analysis.id
                    self.assertEqual(analysis.observations["dimensions"]["finishing"], "absent")
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
