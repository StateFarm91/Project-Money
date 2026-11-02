"""A non-catalogue purchase needs owner-recorded price and licence provenance."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import select

from brambleloop.core.db import Database
from brambleloop.core.models import BenchmarkLicence, BenchmarkProduct, Job
from brambleloop.teardown import intake, library


def purchase():
    return {"platform": "ravelry", "source_url": "https://www.ravelry.com/patterns/library/example",
            "seller": "Example Designer", "pattern_title": "Example Pattern", "paid_amount": 8.0,
            "paid_currency": "USD", "paid_cad": 11.02, "rate": 1.3775,
            "rate_date": "2026-10-31", "purchased_on": "2026-10-31",
            "licence_terms": {"terms_source": "owner purchase record", "notes": "Personal use only.",
                              "allowed_uses": ["private_analysis"], "prohibited_uses": []}}


class RecordedPurchaseTests(unittest.TestCase):
    def test_ravelry_purchase_preserves_owner_price_and_licence(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/purchase.db", scratch=True)
            db.create_all()
            env = {library.LIBRARY_ENV: str(Path(tmp) / "library")}
            result = intake.receive(db, "", [("pattern.pdf", b"not a readable pdf")],
                                    env=env, mirror_files=False, purchase_record=purchase())
            self.assertEqual(result["paid_cad"], 11.02)
            self.assertEqual(result["paid_source"], "owner purchase record")
            with db.session() as s:
                row = s.get(BenchmarkProduct, result["product_id"])
                self.assertEqual(row.purchase_provenance, purchase())
                self.assertEqual(row.seller, "Example Designer")
                lic = s.scalar(select(BenchmarkLicence).where(BenchmarkLicence.source_ref == row.ref))
                self.assertEqual(lic.notes, "Personal use only.")
                self.assertIn("private_analysis", lic.allowed_uses)
                self.assertNotIn("adapt_pattern_for_sale", lic.allowed_uses)
                self.assertIsNotNone(s.scalar(select(Job).where(Job.job_type == "teardown.analyse")))

    def test_missing_price_or_licence_refused_before_upload(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/purchase.db", scratch=True)
            db.create_all()
            root = Path(tmp) / "private"
            for missing in ("paid_amount", "paid_cad", "licence_terms"):
                record = purchase()
                record.pop(missing)
                with self.assertRaises(intake.IntakeRefused):
                    intake.receive(db, "", [("pattern.pdf", b"content")],
                        env={library.LIBRARY_ENV: str(root)}, mirror_files=False,
                        purchase_record=record)
            self.assertFalse(root.exists())

    def test_no_private_analysis_without_explicit_permission(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/purchase.db", scratch=True)
            db.create_all()
            record = purchase()
            record["licence_terms"]["allowed_uses"] = []
            result = intake.receive(db, "", [("pattern.pdf", b"not a readable pdf")],
                env={library.LIBRARY_ENV: str(Path(tmp) / "library")}, mirror_files=False,
                purchase_record=record)
            with db.session() as s:
                lic = s.scalar(select(BenchmarkLicence).where(BenchmarkLicence.source_ref == result["ref"]))
                self.assertNotIn("private_analysis", lic.allowed_uses)
                self.assertIsNone(s.scalar(select(Job).where(Job.job_type == "teardown.analyse")))


if __name__ == "__main__":
    unittest.main()
