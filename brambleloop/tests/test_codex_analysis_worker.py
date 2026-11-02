"""A real worker consumes one durable, deduplicated reference-analysis job."""
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import unittest

from sqlalchemy import select

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import (BenchmarkAnalysis, BenchmarkListing, BenchmarkProduct,
                                     Job, JobStatus, utcnow)
from brambleloop.intel import benchmarks
from brambleloop.products.builder import for_slug
from brambleloop.publish.pdf import build_pattern_pdf
from brambleloop.runtime import pipeline  # noqa: F401 -- registers actual handlers
from brambleloop.runtime.worker import Worker
from brambleloop.teardown import intake, jobs, library, licence


class AnalysisWorkerTests(unittest.TestCase):
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
