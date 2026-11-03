"""Real PDF analysis persists only structured observations, once per file hash."""
import hashlib
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from sqlalchemy import select

from brambleloop.core.db import Database
from brambleloop.core.models import (BenchmarkAnalysis, BenchmarkFingerprintRecord, BenchmarkProduct,
                                     Job, JobStatus)
from brambleloop.agents.registry import Registry
from brambleloop.products.builder import for_slug
from brambleloop.publish.pdf import build_pattern_pdf
from brambleloop.runtime import pipeline  # noqa: F401 -- register real worker handlers
from brambleloop.runtime.worker import Worker
from brambleloop.teardown import analysis_store, jobs, library, licence


class AnalysisStoreTests(unittest.TestCase):
    def test_round_joining_is_structured_page_cited_and_withheld_when_ambiguous(self):
        from reportlab.pdfgen import canvas

        self.assertEqual(analysis_store.round_joining_observation(
            ["Join each round.", "Work in a continuous spiral."], fully_readable=True),
            {"kind": "mixed_cues", "pages": [1, 2]})
        self.assertEqual(analysis_store.round_joining_observation(
            ["Join each round."], fully_readable=False), {"kind": "unknown", "pages": []})
        self.assertEqual(analysis_store.round_joining_observation(
            ["No explicit joining cue."], fully_readable=True), {"kind": "unknown", "pages": []})
        for ambiguous in ("Do not join colours.", "Do not join each round.",
                          "No need to join each round.", "You may join each round.",
                          "Join each round if desired.",
                          "This is not a continuous spiral.", ""):
            self.assertEqual(analysis_store.round_joining_observation(
                [ambiguous], fully_readable=True), {"kind": "unknown", "pages": []})
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            folder = root / "joining-fixture"
            folder.mkdir(parents=True)
            stream = io.BytesIO()
            pdf = canvas.Canvas(stream)
            pdf.drawString(72, 750, "Synthetic fixture: Join each round.")
            pdf.save()
            data = stream.getvalue()
            (folder / "pattern.pdf").write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            db = Database(f"sqlite:///{tmp}/joining.db", scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                product = BenchmarkProduct(ref="joining-fixture", seller="fixture", files=[
                    {"name": "pattern.pdf", "sha256": sha}])
                s.add(product)
                s.flush()
                product_id = product.id
            licence.capture_purchase(db, "joining-fixture")
            jobs.enqueue_purchase(db, product_id)
            with mock.patch.dict(os.environ, {library.LIBRARY_ENV: str(root)}):
                self.assertTrue(Worker(db, name="joining-analyst", job_types=["teardown.analyse"]).run_once())
            with db.session() as s:
                self.assertEqual(s.scalar(select(Job).where(
                    Job.job_type == "teardown.analyse")).status, JobStatus.DONE)
                analysis = s.scalar(select(BenchmarkAnalysis))
                self.assertEqual(analysis.review_state, "proposed")
                observation = analysis.observations
                self.assertEqual(observation["construction"]["round_joining"],
                                 {"kind": "joined_rounds_cue", "pages": [1]})
                self.assertNotIn("Join each round", str(observation))

    def test_pdf_is_licensed_hashed_and_persisted_without_text_or_fingerprint_loss(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            folder = root / "test-purchase"
            folder.mkdir(parents=True)
            data = build_pattern_pdf(for_slug("cloudline-baby-blanket")).pdf_bytes
            path = folder / "pattern.pdf"
            path.write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            url = f"sqlite:///{tmp}/learning.db"
            db = Database(url, scratch=True)
            db.create_all()
            with db.session() as s:
                row = BenchmarkProduct(ref="test-purchase", seller="test",
                                       files=[{"name": "pattern.pdf", "sha256": sha}])
                s.add(row)
                s.add(BenchmarkFingerprintRecord(benchmark_ref="test-purchase",
                                                  wording_shingles=["existing-hash"]))
                s.flush()
                benchmark_id = row.id
            licence.capture_purchase(db, "test-purchase")
            env = {library.LIBRARY_ENV: str(root)}
            one = analysis_store.analyse_file(db, benchmark_id, sha, env=env)
            two = analysis_store.analyse_file(db, benchmark_id, sha, env=env)
            self.assertTrue(one["created"])
            self.assertEqual(one["id"], two["id"])
            self.assertFalse(two["created"])
            reopened = Database(url, scratch=True)
            with reopened.session() as s:
                result = s.get(BenchmarkAnalysis, one["id"])
                self.assertTrue(result.observations["fully_readable"])
                self.assertEqual(result.observations["schematic_state"], "UNKNOWN")
                self.assertEqual(result.benchmark_id, benchmark_id)
                fingerprint = s.scalar(select(BenchmarkFingerprintRecord).where(
                    BenchmarkFingerprintRecord.benchmark_ref == "test-purchase"))
                self.assertEqual(fingerprint.wording_shingles, ["existing-hash"])
                self.assertNotIn("Row 1", str(result.observations))
            path.write_bytes(b"changed")
            with self.assertRaises(analysis_store.AnalysisRefused):
                analysis_store.analyse_file(db, benchmark_id, sha, env=env)


if __name__ == "__main__":
    unittest.main()
