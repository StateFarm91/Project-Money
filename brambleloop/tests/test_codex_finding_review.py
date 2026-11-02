"""Independent review refuses self-review and commits its audit atomically."""
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import select

from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog, BenchmarkProduct, Improvement, TeardownFinding
from brambleloop.teardown import enforce, licence, review
from brambleloop.improve import design_knowledge
from brambleloop.improve import cells


class FindingReviewTests(unittest.TestCase):
    def test_review_requires_distinct_known_recorder_and_records_evidence(self):
        with TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/review.db"
            db = Database(url, scratch=True)
            db.create_all()
            with db.session() as s:
                s.add(BenchmarkProduct(ref="purchase", seller="test",
                    files=[{"name": "pattern.pdf", "sha256": "a" * 64}]))
                a = TeardownFinding(benchmark_ref="purchase", dimension="instruction_clarity",
                                    score=4, recorded_by="analyst", recorder_verified=True,
                                    confidence=0.9)
                b = TeardownFinding(benchmark_ref="purchase", dimension="instruction_clarity",
                                    score=4, recorded_by=None, confidence=0.9)
                s.add_all([a, b])
                s.flush()
                a_id, b_id = a.id, b.id
                improvement = Improvement(cell="quality", metric="clarity", hypothesis="test",
                    state="testing", rollback_ref=f"teardown-finding:{a_id}",
                    evidence={"proposed_by": "teardown"})
                s.add(improvement)
                s.flush()
                improvement_id = improvement.id
            licence.capture_purchase(db, "purchase")
            with self.assertRaises(review.ReviewRefused):
                review.review_finding(db, a_id, reviewer="ANALYST", decision="reviewed",
                                      reason="independent check")
            with self.assertRaises(review.ReviewRefused):
                review.review_finding(db, b_id, reviewer="owner", decision="reviewed",
                                      reason="independent check")
            review.attest_finding_recorder(db, b_id, recorder="owner", actor="owner:session-one",
                                           reason="owner recorded this fixture")
            with self.assertRaises(review.ReviewRefused):
                review.review_finding(db, b_id, reviewer="owner:session-two", decision="reviewed",
                                      reason="same owner is not independent")
            with self.assertRaises(review.ReviewRefused):
                review.review_finding(db, a_id, reviewer="owner", decision="reviewed", reason="")
            before = enforce.requirements(db)
            self.assertTrue(before)
            self.assertTrue(all(not row["binding"] for row in before))
            self.assertTrue(enforce.check(db, "unreleased")["blocks"])
            proposal = dict(key="clarity", statement={"rule": "include_finishing_checklist",
                "parameters": {}}, scope={"writer_section": "finishing"},
                provenance=[{"kind": "finding", "id": a_id}], producer="engineer")
            with self.assertRaises(design_knowledge.DesignKnowledgeRefused):
                design_knowledge.propose(db, **proposal)
            with self.assertRaises(cells.ImprovementRefused):
                cells.approve(db, improvement_id, approved_by="quality")
            review.review_finding(db, a_id, reviewer="owner", decision="reviewed",
                                  reason="independent check")
            self.assertTrue(any(row["binding"] for row in enforce.requirements(db)))
            self.assertEqual(design_knowledge.propose(db, **proposal)["state"], "proposed")
            self.assertTrue(cells.approve(db, improvement_id, approved_by="quality")["independent"])
            with self.assertRaises(review.ReviewRefused):
                review.review_finding(db, a_id, reviewer="another", decision="rejected",
                                      reason="second review")
            reopened = Database(url, scratch=True)
            with reopened.session() as s:
                row = s.get(TeardownFinding, a_id)
                self.assertEqual((row.review_state, row.reviewed_by), ("reviewed", "owner"))
                self.assertIsNotNone(row.reviewed_at)
                audits = list(s.scalars(select(AuditLog).where(
                    AuditLog.action == "teardown.finding_reviewed")))
                self.assertEqual(len(audits), 1)
                self.assertEqual(audits[0].detail["evidence_sha256"], row.reviewed_sha256)
                row.score = 1
            self.assertTrue(all(not row["binding"] for row in enforce.requirements(reopened)))
            with self.assertRaises(design_knowledge.DesignKnowledgeRefused):
                design_knowledge.propose(reopened, **{**proposal, "key": "changed_clarity"})
            review.review_finding(reopened, a_id, reviewer="another", decision="reviewed",
                                  reason="reviewed the changed evidence")
            self.assertTrue(any(row["binding"] for row in enforce.requirements(reopened)))


if __name__ == "__main__":
    unittest.main()
