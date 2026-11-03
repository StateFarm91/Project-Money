"""Legacy analyses gain separately reviewed, versioned cues without mutation."""
import hashlib
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import select

import test_v11_cc_actions as harness
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import (BenchmarkAnalysis, BenchmarkProduct,
                                    BenchmarkTechniqueObservation, Job, JobStatus)
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline  # noqa: F401
from brambleloop.runtime.worker import Worker
from brambleloop.teardown import analysis_store, jobs, library, licence, review


class HistoricalTechniqueTests(unittest.TestCase):
    def test_changed_source_makes_queued_extraction_stale_without_mutation(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/stale.sqlite", scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                product = BenchmarkProduct(ref="stale-technique", seller="fixture", files=[
                    {"name": "pattern.pdf", "sha256": "a" * 64}])
                s.add(product)
                s.flush()
                source = BenchmarkAnalysis(benchmark_id=product.id, file_sha256="a" * 64,
                                            observations={"construction": {}})
                s.add(source)
                s.flush()
                source_id = source.id
            licence.capture_purchase(db, "stale-technique")
            self.assertEqual(jobs.enqueue_technique_supplement(db, source_id)["queued"], 1)
            with db.session() as s:
                source = s.get(BenchmarkAnalysis, source_id)
                source.observations = {"construction": {}, "pages": 1}
                updated = review.evidence_digest(source)
            self.assertTrue(Worker(db, name="stale-supplement", job_types=["teardown.analyse"]).run_once())
            with db.session() as s:
                job = s.scalar(select(Job).where(Job.job_type == "teardown.analyse"))
                self.assertEqual(job.outputs["state"], "stale")
                self.assertEqual(list(s.scalars(select(BenchmarkTechniqueObservation))), [])
            self.assertEqual(jobs.enqueue_technique_supplement(db, source_id)["queued"], 1)
            with db.session() as s:
                jobs_for_source = [job for job in s.scalars(select(Job).where(
                    Job.job_type == "teardown.analyse")) if job.inputs.get("analysis_id") == source_id]
                self.assertEqual(len(jobs_for_source), 2)
                self.assertEqual(jobs_for_source[-1].inputs["source_digest"], updated)

    def test_failed_supplement_recovers_after_restart_without_duplicate(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            folder = root / "recovery-technique"
            folder.mkdir(parents=True)
            stream = io.BytesIO()
            pdf = canvas.Canvas(stream)
            pdf.drawString(72, 750, "Synthetic fixture: Join each round.")
            pdf.save()
            payload = stream.getvalue()
            sha = hashlib.sha256(payload).hexdigest()
            url = f"sqlite:///{tmp}/recovery.sqlite"
            db = Database(url, scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                product = BenchmarkProduct(ref="recovery-technique", seller="fixture", files=[
                    {"name": "pattern.pdf", "sha256": sha}])
                s.add(product)
                s.flush()
                source = BenchmarkAnalysis(benchmark_id=product.id, file_sha256=sha,
                    observations={"pages": 1, "pages_with_text": 1, "construction": {}})
                s.add(source)
                s.flush()
                source_id = source.id
                original_digest = review.evidence_digest(source)
            licence.capture_purchase(db, "recovery-technique")
            self.assertEqual(jobs.enqueue_technique_supplement(db, source_id)["queued"], 1)
            with db.session() as s:
                job = s.scalar(select(Job).where(Job.job_type == "teardown.analyse"))
                job.max_attempts = 1
                job_id = job.id
            with mock.patch.dict(os.environ, {library.LIBRARY_ENV: str(root)}):
                self.assertTrue(Worker(db, name="missing-source", job_types=["teardown.analyse"])
                                .run_once())
                with db.session() as s:
                    self.assertEqual(s.get(Job, job_id).status, JobStatus.DEAD)
                    self.assertEqual(list(s.scalars(select(BenchmarkTechniqueObservation))), [])
                (folder / "pattern.pdf").write_bytes(payload)
                reopened = Database(url, scratch=True)
                JobQueue(reopened).enqueue("orchestrator", "teardown.analyse_sweep", {},
                                           idempotency_key="supplement-recovery")
                self.assertTrue(Worker(reopened, name="supplement-sweep",
                                       job_types=["teardown.analyse_sweep"]).run_once())
                with reopened.session() as s:
                    sweep = s.scalar(select(Job).where(Job.idempotency_key == "supplement-recovery"))
                    self.assertEqual(sweep.outputs["technique_requeued"], 1)
                worker = Worker(reopened, name="supplement-restart", job_types=["teardown.analyse"])
                while worker.run_once():
                    pass
                with reopened.session() as s:
                    self.assertEqual(s.get(Job, job_id).status, JobStatus.DONE)
                    self.assertEqual(s.get(Job, job_id).automatic_redrives, 1)
                    self.assertEqual(len(list(s.scalars(select(BenchmarkTechniqueObservation)))), 1)
                    self.assertEqual(review.evidence_digest(s.get(BenchmarkAnalysis, source_id)),
                                     original_digest)

    def test_real_sweep_and_owner_review_preserve_old_evidence_and_reject_staleness(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            folder = root / "legacy-technique-fixture"
            folder.mkdir(parents=True)
            data = io.BytesIO()
            pdf = canvas.Canvas(data)
            pdf.drawString(72, 750, "Synthetic fixture: Join each round.")
            pdf.save()
            payload = data.getvalue()
            sha = hashlib.sha256(payload).hexdigest()
            (folder / "pattern.pdf").write_bytes(payload)
            with harness.DB.session() as s:
                product = BenchmarkProduct(ref="legacy-technique-fixture", seller="fixture", files=[
                    {"name": "pattern.pdf", "sha256": sha}])
                s.add(product)
                s.flush()
                source = BenchmarkAnalysis(benchmark_id=product.id, file_sha256=sha, observations={
                    "pages": 1, "pages_with_text": 1, "fully_readable": True,
                    "dimensions": {"finishing": "observed"}, "construction": {}})
                s.add(source)
                s.flush()
                source_id = source.id
            licence.capture_purchase(harness.DB, "legacy-technique-fixture")
            client, csrf = harness.session()
            self.addCleanup(client.close)
            old_review = harness.post(client, csrf, "/api/cc/actions/teardown.review_analysis", {
                "analysis_id": source_id, "decision": "reviewed", "reason": "review old evidence"})
            self.assertEqual(old_review.status_code, 200, old_review.text)
            with harness.DB.session() as s:
                source = s.get(BenchmarkAnalysis, source_id)
                original_digest = review.evidence_digest(source)
                self.assertTrue(review.independently_reviewed(source))
            with mock.patch.dict(os.environ, {library.LIBRARY_ENV: str(root)}):
                queue = JobQueue(harness.DB)
                queue.enqueue("orchestrator", "teardown.analyse_sweep", {}, idempotency_key="legacy-cue:sweep")
                self.assertTrue(Worker(harness.DB, name="legacy-sweep", job_types=["teardown.analyse_sweep"])
                                .run_once())
                worker = Worker(harness.DB, name="legacy-reader", job_types=["teardown.analyse"])
                while worker.run_once():
                    pass
                with harness.DB.session() as s:
                    source = s.get(BenchmarkAnalysis, source_id)
                    self.assertEqual(review.evidence_digest(source), original_digest)
                    self.assertTrue(review.independently_reviewed(source))
                    rows = list(s.scalars(select(BenchmarkTechniqueObservation).where(
                        BenchmarkTechniqueObservation.analysis_id == source_id)))
                    self.assertEqual(len(rows), 1)
                    cue = rows[0]
                    self.assertEqual(cue.review_state, "proposed")
                    self.assertEqual(cue.observation, {"kind": "joined_rounds_cue", "pages": [1]})
                    self.assertNotIn("Join each round", str(cue.observation))
                    cue_id = cue.id
                inbox = client.get("/api/cc/approvals")
                self.assertEqual(inbox.status_code, 200, inbox.text)
                self.assertIn(f"technique:{cue_id}", inbox.text)
                self.assertIn("joined_rounds_cue", inbox.text)
                self.assertNotIn("Join each round", inbox.text)
                anonymous = TestClient(harness.main.app, base_url="https://testserver")
                self.addCleanup(anonymous.close)
                self.assertIn(anonymous.get("/api/cc/approvals").status_code, (401, 403))
                with self.assertRaises(review.ReviewRefused):
                    review.review_technique_observation(harness.DB, cue_id, reviewer="teardown_analyst",
                                                       decision="reviewed", reason="self review")
                action = "/api/cc/actions/teardown.review_technique"
                body = {"observation_id": cue_id, "decision": "reviewed", "reason": "independent review"}
                no_session = TestClient(harness.main.app, base_url="https://testserver")
                self.addCleanup(no_session.close)
                denied = no_session.post(action, json=body,
                                         headers={"Authorization": f"Bearer {harness.OPS}"})
                self.assertIn(denied.status_code, (401, 403))
                harness.expire_stepup(client)
                self.assertEqual(harness.post(client, csrf, action, body).status_code, 403)
                self.assertEqual(harness.post(client, csrf, "/api/cc/auth/step-up",
                                              {"passphrase": harness.PASS}).status_code, 200)
                accepted = harness.post(client, csrf, action, body)
                self.assertEqual(accepted.status_code, 200, accepted.text)
                self.assertTrue(review.independently_reviewed_technique(harness.DB, cue_id))
                queue.enqueue("orchestrator", "teardown.analyse_sweep", {}, idempotency_key="legacy-cue:repeat")
                self.assertTrue(Worker(harness.DB, name="legacy-repeat", job_types=["teardown.analyse_sweep"])
                                .run_once())
                with harness.DB.session() as s:
                    self.assertEqual(len(list(s.scalars(select(BenchmarkTechniqueObservation).where(
                        BenchmarkTechniqueObservation.analysis_id == source_id)))), 1)
                # A new extractor implementation gets a new proposal, while
                # the previously reviewed observation remains historical evidence.
                with mock.patch.object(analysis_store, "technique_extractor_digest", return_value="f" * 64):
                    queue.enqueue("orchestrator", "teardown.analyse_sweep", {},
                                  idempotency_key="legacy-cue:new-extractor")
                    self.assertTrue(Worker(harness.DB, name="legacy-new-extractor",
                                           job_types=["teardown.analyse_sweep"]).run_once())
                    while worker.run_once():
                        pass
                    with harness.DB.session() as s:
                        versions = list(s.scalars(select(BenchmarkTechniqueObservation).where(
                            BenchmarkTechniqueObservation.analysis_id == source_id).order_by(
                            BenchmarkTechniqueObservation.id)))
                        self.assertEqual(len(versions), 2)
                        self.assertEqual(versions[1].extractor_sha256, "f" * 64)
                        self.assertEqual(versions[1].review_state, "proposed")
                    self.assertTrue(review.independently_reviewed_technique(harness.DB, cue_id))
                licence.capture_purchase(harness.DB, "legacy-technique-fixture", terms={
                    "allowed_uses": [], "prohibited_uses": ["private_analysis"]})
                self.assertFalse(review.independently_reviewed_technique(harness.DB, cue_id))
                licence.capture_purchase(harness.DB, "legacy-technique-fixture", terms={
                    "allowed_uses": list(licence.PRIVATE_RESEARCH_USES),
                    "prohibited_uses": list(licence.PUBLISHING_USES)})
                self.assertTrue(review.independently_reviewed_technique(harness.DB, cue_id))
                with harness.DB.session() as s:
                    source = s.get(BenchmarkAnalysis, source_id)
                    source.observations = {**source.observations, "pages": 2}
                self.assertFalse(review.independently_reviewed_technique(harness.DB, cue_id))
                queue.enqueue("orchestrator", "teardown.analyse_sweep", {}, idempotency_key="legacy-cue:changed")
                self.assertTrue(Worker(harness.DB, name="legacy-changed", job_types=["teardown.analyse_sweep"])
                                .run_once())
                while worker.run_once():
                    pass
                with harness.DB.session() as s:
                    rows = list(s.scalars(select(BenchmarkTechniqueObservation).where(
                        BenchmarkTechniqueObservation.analysis_id == source_id).order_by(
                        BenchmarkTechniqueObservation.id)))
                    self.assertEqual(len(rows), 3)
                    self.assertEqual(rows[0].review_state, "reviewed")
                    self.assertEqual(rows[2].review_state, "proposed")
                    self.assertNotEqual(rows[0].source_digest, rows[2].source_digest)


if __name__ == "__main__":
    unittest.main()
