"""Exercise engineering failures through the real durable lesson bus."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import select

from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog, Incident, Lesson
from brambleloop.improve import design_knowledge, mine


class EngineeringFailureMining(unittest.TestCase):
    def test_unknown_learning_gap_is_not_mined_as_a_product_defect(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/gap.db", scratch=True)
            db.create_all()
            with db.session() as s:
                s.add_all([
                    Incident(signature="learning.knowledge_gap:architecture:1", severity="P2",
                             summary="Reference observations are unknown"),
                    Incident(signature="compile_regression:1", severity="P2",
                             summary="A real engineering incident"),
                ])
            mine.mine(db, fixture_dir=Path(tmp))
            with db.session() as s:
                refs = [row.evidence_ref for row in s.scalars(select(Lesson))]
                self.assertTrue(any(ref.startswith("incident:compile_regression") for ref in refs))
                self.assertFalse(any("learning.knowledge_gap" in ref for ref in refs))
                self.assertIsNotNone(s.scalar(select(Incident).where(
                    Incident.signature == "learning.knowledge_gap:architecture:1",
                    Incident.resolved.is_(False))))

    def test_failed_compile_and_unrepairable_are_mined_once(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/learning.db", scratch=True)
            db.create_all()
            with db.session() as s:
                s.add_all([
                    AuditLog(actor="validator", action="cir.compiled", artifact="a@1",
                             detail={"ok": False, "errors": 1}),
                    AuditLog(actor="validator", action="cir.compiled", artifact="b@1",
                             detail={"ok": True, "errors": 0}),
                    AuditLog(actor="validator", action="cir.compiled", artifact="c@1",
                             detail={}),
                    AuditLog(actor="crochet_engineer", action="cir.revise_unrepairable",
                             artifact="a@1", detail={"codes": ["COUNT_MISMATCH"]}),
                ])
            result = mine.mine(db, fixture_dir=Path(tmp))
            compile_group = next(row for row in result["published"]
                                 if row["evidence_ref"] == "cir.compiled:compile_failed")
            self.assertEqual(compile_group["members"], 1)
            mine.mine(db, fixture_dir=Path(tmp))
            with db.session() as s:
                lessons = list(s.scalars(select(Lesson).where(Lesson.subject == "defect")))
                refs = [row.evidence_ref for row in lessons]
                compile_lesson = next(row for row in lessons
                                      if row.evidence_ref == "cir.compiled:compile_failed")
                self.assertEqual(compile_lesson.source_findings, [])
                lesson_id = compile_lesson.id
            self.assertEqual(refs.count("cir.compiled:compile_failed"), 1)
            self.assertEqual(refs.count("cir.revise_unrepairable:unrepairable"), 1)
            proposal = design_knowledge.propose(db, key="compile_defect", producer="engineer",
                statement={"rule": "include_finishing_checklist", "parameters": {}},
                scope={"writer_section": "finishing"},
                provenance=[{"kind": "lesson", "id": lesson_id}])
            self.assertEqual(proposal["state"], "proposed")


if __name__ == "__main__":
    unittest.main()
