"""Legacy teardown rows remain visible without creating uncleareable holds."""
from tempfile import TemporaryDirectory
import unittest

from brambleloop.core.db import Database
from brambleloop.core.models import TeardownFinding
from brambleloop.teardown import enforce


class LegacyFindings(unittest.TestCase):
    def test_legacy_and_met_proposals_do_not_create_review_holds(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/legacy.db", scratch=True)
            db.create_all()
            with db.session() as s:
                s.add_all([
                    TeardownFinding(benchmark_ref="legacy-ref", dimension="instruction_clarity",
                                    score=4, confidence=0.9, recorded_by=None),
                    TeardownFinding(benchmark_ref="new-ref", dimension="instruction_clarity",
                                    score=4, confidence=0.9, recorded_by="analyst"),
                    TeardownFinding(benchmark_ref="brambleloop:product", dimension="instruction_clarity",
                                    score=5, confidence=0.9),
                ])
            result = enforce.check(db, "product", consumers=enforce.PUBLISH_CONSUMERS)
            self.assertFalse(result["blocks"], result["reasons"])
            self.assertEqual({row["review_state"] for row in result["rows"]}, {"legacy", "proposed"})
            self.assertTrue(all(row["verdict"] == "met" and not row["binding"]
                                for row in result["rows"]))
            with db.session() as s:
                for row in s.query(TeardownFinding).filter_by(benchmark_ref="brambleloop:product"):
                    row.score = 1
            result = enforce.check(db, "product", consumers=enforce.PUBLISH_CONSUMERS)
            self.assertTrue(result["blocks"])
            self.assertEqual(len(result["reasons"]), 1)
            self.assertIn("independent review", result["reasons"][0])

    def test_unmet_legacy_without_attribution_is_nonbinding(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/legacy.db", scratch=True)
            db.create_all()
            with db.session() as s:
                s.add(TeardownFinding(benchmark_ref="legacy-ref", dimension="instruction_clarity",
                                      score=4, confidence=0.9, recorded_by=None))
            result = enforce.check(db, "product", consumers=enforce.PUBLISH_CONSUMERS)
            self.assertFalse(result["blocks"])
            self.assertEqual(result["rows"][0]["review_state"], "legacy")
            self.assertEqual(result["rows"][0]["verdict"], "unmeasured")


if __name__ == "__main__":
    unittest.main()
