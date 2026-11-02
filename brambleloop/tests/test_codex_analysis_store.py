"""Real PDF analysis persists only structured observations, once per file hash."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import select

from brambleloop.core.db import Database
from brambleloop.core.models import BenchmarkAnalysis, BenchmarkFingerprintRecord, BenchmarkProduct
from brambleloop.products.builder import for_slug
from brambleloop.publish.pdf import build_pattern_pdf
from brambleloop.teardown import analysis_store, library, licence


class AnalysisStoreTests(unittest.TestCase):
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
