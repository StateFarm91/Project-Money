"""Durable proposals cannot smuggle source text or self-approve."""
from tempfile import TemporaryDirectory
import unittest

from brambleloop.core.db import Database
from brambleloop.core.models import (BenchmarkAnalysis, BenchmarkProduct, DesignRule, Incident,
                                     TeardownFinding, utcnow)
from brambleloop.improve.design_knowledge import (DesignKnowledgeRefused, propose,
                                                  propose_from_analysis)
from brambleloop.teardown import licence


class DesignProposals(unittest.TestCase):
    def test_reviewed_analysis_cannot_propose_after_licence_or_manifest_changes(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/knowledge.db", scratch=True)
            db.create_all()
            sha = "a" * 64
            with db.session() as s:
                product = BenchmarkProduct(ref="purchase", seller="test",
                    files=[{"name": "pattern.pdf", "sha256": sha}])
                s.add(product)
                s.flush()
                analysis = BenchmarkAnalysis(benchmark_id=product.id, file_sha256=sha,
                    review_state="reviewed", recorded_by="teardown_analyst", reviewed_by="owner",
                    reviewed_at=utcnow(), observations={"fully_readable": True,
                    "dimensions": {"finishing": "absent"}})
                s.add(analysis)
                forged = BenchmarkAnalysis(benchmark_id=product.id, file_sha256="b" * 64,
                    review_state="reviewed", recorded_by="analyst", reviewed_by="analyst",
                    reviewed_at=utcnow(), observations={"fully_readable": True,
                    "dimensions": {"finishing": "absent"}})
                s.add(forged)
                s.flush()
                ident, product_id, forged_id = analysis.id, product.id, forged.id
            self.assertEqual(propose_from_analysis(db, forged_id)["reason"], "not_reviewed")
            licence.capture_purchase(db, "purchase", terms={"allowed_uses": [],
                "prohibited_uses": ["private_analysis"]})
            with self.assertRaises(DesignKnowledgeRefused):
                propose_from_analysis(db, ident)
            licence.capture_purchase(db, "purchase", terms={"allowed_uses": ["private_analysis"],
                "prohibited_uses": []})
            with db.session() as s:
                s.get(BenchmarkProduct, product_id).files = []
            with self.assertRaises(DesignKnowledgeRefused):
                propose_from_analysis(db, ident)

    def test_versioned_proposals_persist_and_bad_evidence_is_refused(self):
        with TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/knowledge.db"
            db = Database(url, scratch=True)
            db.create_all()
            with db.session() as s:
                incident = Incident(signature="count-defect", severity="P1", summary="count",
                                    detail={"source_findings": []})
                s.add(incident)
                finding = TeardownFinding(benchmark_ref="benchmark", dimension="instruction_clarity",
                                          score=4, mechanism="clarity", improvement="clarity")
                s.add(finding)
                s.flush()
                incident_id = incident.id
                finding_id = finding.id
            args = dict(key="finishing", statement={"rule": "include_finishing_checklist",
                        "parameters": {}}, scope={"writer_section": "finishing"},
                        provenance=[{"kind": "incident", "id": incident_id}],
                        producer="engineer")
            first = propose(db, **args)
            second = propose(db, **args, supersedes=first["id"])
            self.assertEqual((first["version"], second["version"]), (1, 2))
            reopened = Database(url, scratch=True)
            with reopened.session() as s:
                row = s.get(DesignRule, second["id"])
                self.assertEqual(row.state, "proposed")
                self.assertIsNone(row.approved_by)
                self.assertEqual(row.supersedes, first["id"])
                self.assertEqual(row.provenance, args["provenance"])
            with self.assertRaises(DesignKnowledgeRefused):
                propose(db, **{**args, "provenance": [{"kind": "incident", "id": 999}]})
            with self.assertRaises(DesignKnowledgeRefused):
                propose(db, **{**args, "statement": {"rule": "include_finishing_checklist",
                    "parameters": {"instructions": "copied source text"}}})
            with self.assertRaises(DesignKnowledgeRefused):
                propose(db, **{**args, "scope": {"writer_section": "Row 1: copied text"}})
            with self.assertRaises(DesignKnowledgeRefused):
                propose(db, **{**args, "provenance": [{"kind": "finding", "id": finding_id}]})


if __name__ == "__main__":
    unittest.main()
