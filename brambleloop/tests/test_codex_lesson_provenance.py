"""Teardown-derived lessons cannot launder unreviewed or untraceable findings."""
import hashlib
from tempfile import TemporaryDirectory
import unittest

from brambleloop.core.db import Database
from sqlalchemy import select

from brambleloop.agents.registry import Registry
from brambleloop.core.models import BenchmarkProduct, DesignRule, Lesson, SupportCase, TeardownFinding, utcnow
from brambleloop.improve import bus, design_knowledge, readings_bus
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline  # noqa: F401 -- register real handlers
from brambleloop.runtime.worker import Worker
from brambleloop.teardown import enforce, lab, licence, review


class LessonProvenanceTests(unittest.TestCase):
    def test_real_customer_aggregate_retains_non_reference_provenance(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/customer.db", scratch=True)
            db.create_all()
            with db.session() as s:
                for i in range(3):
                    s.add(SupportCase(customer_ref=f"person-{i}", product_slug="sample",
                                      question="The instructions were unclear."))
            lessons = readings_bus._customer(db, utcnow())
            self.assertEqual(len(lessons), 1)
            result = design_knowledge.propose(db, key="customer_clarity", producer="engineer",
                statement={"rule": "include_finishing_checklist", "parameters": {}},
                scope={"writer_section": "finishing"},
                provenance=[{"kind": "lesson", "id": lessons[0]}])
            self.assertEqual(result["state"], "proposed")

    def test_low_confidence_cannot_affect_reviewed_binding_group(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/confidence.db", scratch=True)
            db.create_all()
            with db.session() as s:
                high = TeardownFinding(benchmark_ref="a", dimension="instruction_clarity",
                    score=5, confidence=0.9, recorded_by="analyst")
                low = TeardownFinding(benchmark_ref="b", dimension="instruction_clarity",
                    score=1, confidence=0.2, recorded_by="analyst")
                s.add_all([high, low])
                s.flush()
                high_id, low_id = high.id, low.id
            for ident in (high_id, low_id):
                review.review_finding(db, ident, reviewer="owner", decision="reviewed",
                                      reason="independent review")
            requirements = enforce.requirements(db)
            binding = [r for r in requirements if r["binding"]]
            self.assertEqual([(r["kind"], r["findings"]) for r in binding], [("exceed", [high_id])])
            self.assertFalse(any(r["binding"] and low_id in r["findings"] for r in requirements))

    def test_real_enforcement_handler_publishes_only_reviewed_roots(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/worker.db", scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                s.add(BenchmarkProduct(ref="reference", seller="test",
                    files=[{"name": "p.pdf", "sha256": "a" * 64}]))
            licence.capture_purchase(db, "reference")
            finding_id = lab.record_finding(db, "reference", "instruction_clarity", 1,
                "A synthetic observation describes confusing presentation.",
                "Provide a clearer navigation aid for the original document.", confidence=0.9)["finding"]
            queue = JobQueue(db)
            queue.enqueue("orchestrator", "teardown.enforce", {}, idempotency_key="enforce:before")
            self.assertTrue(Worker(db, job_types=["teardown.enforce"]).run_once())
            with db.session() as s:
                self.assertEqual(list(s.scalars(select(Lesson).where(
                    Lesson.evidence_ref.like("teardown_requirement:%")))), [])
            review.review_finding(db, finding_id, reviewer="owner", decision="reviewed",
                                  reason="independent review")
            queue.enqueue("orchestrator", "teardown.enforce", {}, idempotency_key="enforce:after")
            self.assertTrue(Worker(db, job_types=["teardown.enforce"]).run_once())
            with db.session() as s:
                lesson = s.scalar(select(Lesson).where(Lesson.evidence_ref.like("teardown_requirement:%")))
                self.assertIsNotNone(lesson)
                self.assertEqual(lesson.source_findings, [finding_id])
                lesson_id = lesson.id
            result = design_knowledge.propose(db, key="reviewed_lesson", producer="engineer",
                statement={"rule": "include_finishing_checklist", "parameters": {}},
                scope={"writer_section": "finishing"},
                provenance=[{"kind": "lesson", "id": lesson_id}])
            with db.session() as s:
                self.assertIn({"kind": "finding", "id": finding_id},
                              s.get(DesignRule, result["id"]).provenance)

    def test_every_root_is_reviewed_and_stored_with_the_rule(self):
        with TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/provenance.db", scratch=True)
            db.create_all()
            with db.session() as s:
                s.add(BenchmarkProduct(ref="reference", seller="test",
                    files=[{"name": "p.pdf", "sha256": "a" * 64}]))
                a = TeardownFinding(benchmark_ref="reference", dimension="instruction_clarity",
                    score=1, confidence=0.9, recorded_by="analyst")
                b = TeardownFinding(benchmark_ref="reference", dimension="instruction_clarity",
                    score=1, confidence=0.8, recorded_by="analyst")
                legacy = Lesson(origin_cell="quality", subject="instruction_clarity",
                    statement="A legacy lesson cannot prove its original reference finding.",
                    evidence_ref="teardown_requirement:dimension:instruction_clarity:prevent")
                s.add_all([a, b, legacy])
                s.flush()
                ids, legacy_id = [a.id, b.id], legacy.id
            licence.capture_purchase(db, "reference")
            stamp = hashlib.sha256(",".join(str(i) for i in ids).encode()).hexdigest()[:16]
            lesson_id = bus.publish(db, origin_cell="quality", subject="instruction_clarity",
                statement="A reference finding proposes clearer original finishing instructions.",
                evidence_ref=f"teardown_requirement:dimension:instruction_clarity:prevent:roots-{stamp}",
                source_findings=ids)
            args = {"key": "finish", "statement": {"rule": "include_finishing_checklist",
                    "parameters": {}}, "scope": {"writer_section": "finishing"},
                    "producer": "engineer"}
            with self.assertRaises(design_knowledge.DesignKnowledgeRefused):
                design_knowledge.propose(db, **args, provenance=[{"kind": "lesson", "id": legacy_id}])
            review.review_finding(db, ids[0], reviewer="owner", decision="reviewed",
                                  reason="independent review")
            with self.assertRaises(design_knowledge.DesignKnowledgeRefused):
                design_knowledge.propose(db, **args, provenance=[{"kind": "lesson", "id": lesson_id}])
            review.review_finding(db, ids[1], reviewer="owner", decision="reviewed",
                                  reason="independent review")
            with self.assertRaises(design_knowledge.DesignKnowledgeRefused):
                design_knowledge.propose(db, **args, provenance=[{"kind": "lesson", "id": legacy_id}])
            made = design_knowledge.propose(db, **args, provenance=[{"kind": "lesson", "id": lesson_id}])
            with db.session() as s:
                rule = s.get(DesignRule, made["id"])
                self.assertEqual(rule.provenance, [{"kind": "lesson", "id": lesson_id},
                    {"kind": "finding", "id": ids[0]}, {"kind": "finding", "id": ids[1]}])
            licence.capture_purchase(db, "reference", terms={"allowed_uses": [],
                                      "prohibited_uses": ["private_analysis"]})
            with self.assertRaises(design_knowledge.DesignKnowledgeRefused):
                design_knowledge.propose(db, **args, provenance=[{"kind": "lesson", "id": lesson_id}])


if __name__ == "__main__":
    unittest.main()
