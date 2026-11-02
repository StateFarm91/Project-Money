"""Durable proposals cannot smuggle source text or self-approve."""
from tempfile import TemporaryDirectory
import unittest

from brambleloop.core.db import Database
from brambleloop.core.models import DesignRule, Incident, TeardownFinding
from brambleloop.improve.design_knowledge import DesignKnowledgeRefused, propose


class DesignProposals(unittest.TestCase):
    def test_versioned_proposals_persist_and_bad_evidence_is_refused(self):
        with TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/knowledge.db"
            db = Database(url, scratch=True)
            db.create_all()
            with db.session() as s:
                incident = Incident(signature="count-defect", severity="P1", summary="count")
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
