"""Disjoint scope approvals coexist; overlapping scopes never silently win."""
import copy
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from brambleloop.agents.registry import Registry
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir import knowledge as markers
from brambleloop.cir.writer import write_pattern
from brambleloop.core.db import Database
from brambleloop.core.models import BenchmarkAnalysis, BenchmarkProduct, DesignRule
from brambleloop.gates.originality import code_benchmarks, record_fingerprint
from brambleloop.improve import design_knowledge as knowledge
from brambleloop.products import launch0
from brambleloop.quality import design_eval, design_revalidation
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline  # noqa: F401
from brambleloop.runtime.worker import Worker
from brambleloop.teardown import licence, review


class ScopedKnowledgeTests(unittest.TestCase):
    def test_concurrent_disjoint_approvals_can_be_retried_without_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/disjoint-race.db"
            db = Database(url, scratch=True)
            db.create_all()
            with db.session() as s:
                product = BenchmarkProduct(ref="disjoint-race", seller="fixture", files=[
                    {"name": "reference.pdf", "sha256": "a" * 64}])
                s.add(product)
                s.flush()
                observation = BenchmarkAnalysis(benchmark_id=product.id, file_sha256="a" * 64,
                    observations={"fully_readable": True, "dimensions": {"finishing": "absent"}})
                s.add(observation)
                s.flush()
                source_id = observation.id
            licence.capture_purchase(db, "disjoint-race")
            review.review_analysis(db, source_id, reviewer="owner", decision="reviewed", reason="review")
            for ref in ["disjoint-race", *(b.ref for b in code_benchmarks())]:
                record_fingerprint(db, ref, text="quasar violet lantern willow indigo river meadow")
            candidates = []
            for family in ("flat_rows", "joined_rounds"):
                proposal = knowledge.propose(db, key=f"race_{family}", producer="analyst",
                    statement={"rule": "include_finishing_checklist", "parameters": {}},
                    scope={"writer_section": "finishing", "construction_family": family},
                    provenance=[{"kind": "analysis", "id": source_id}])
                evaluation = design_eval.evaluate(db, proposal["id"])
                self.assertEqual(evaluation["state"], "passed")
                candidates.append((proposal["id"], evaluation["audit_id"]))
            barrier = threading.Barrier(2)
            def approve(item):
                barrier.wait()
                try:
                    return knowledge.review_rule(Database(url, scratch=True), item[0], reviewer="owner",
                        decision="approve", reason="disjoint race fixture", evaluation_id=item[1])
                except (knowledge.DesignKnowledgeRefused, OperationalError) as exc:
                    return exc
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(approve, candidates))
            self.assertTrue(any(isinstance(result, dict) for result in outcomes), outcomes)
            for candidate, outcome in zip(candidates, outcomes):
                if not isinstance(outcome, dict):
                    outcome = knowledge.review_rule(db, candidate[0], reviewer="owner",
                        decision="approve", reason="retry disjoint scope", evaluation_id=candidate[1])
                self.assertEqual(knowledge.verify_pins(db, [outcome["pin"]])[0]["pin"], outcome["pin"])
            with db.session() as s:
                self.assertEqual({r.active_slot for r in s.scalars(select(DesignRule).where(
                    DesignRule.state == "approved"))}, {2, 3})

    def test_concurrent_global_and_scoped_approvals_cannot_both_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/scope-race.db"
            db = Database(url, scratch=True)
            db.create_all()
            with db.session() as s:
                product = BenchmarkProduct(ref="scope-race", seller="fixture", files=[
                    {"name": "reference.pdf", "sha256": "a" * 64}])
                s.add(product)
                s.flush()
                observation = BenchmarkAnalysis(benchmark_id=product.id, file_sha256="a" * 64,
                    observations={"fully_readable": True, "dimensions": {"finishing": "absent"}})
                s.add(observation)
                s.flush()
                source_id = observation.id
            licence.capture_purchase(db, "scope-race")
            review.review_analysis(db, source_id, reviewer="owner", decision="reviewed", reason="review")
            for ref in ["scope-race", *(b.ref for b in code_benchmarks())]:
                record_fingerprint(db, ref, text="quasar violet lantern willow indigo river meadow")
            candidates = []
            for key, scope in (("race_global", {"writer_section": "finishing"}),
                               ("race_flat", {"writer_section": "finishing",
                                              "construction_family": "flat_rows"})):
                proposal = knowledge.propose(db, key=key, producer="analyst",
                    statement={"rule": "include_finishing_checklist", "parameters": {}},
                    scope=scope, provenance=[{"kind": "analysis", "id": source_id}])
                evaluation = design_eval.evaluate(db, proposal["id"])
                self.assertEqual(evaluation["state"], "passed")
                candidates.append((proposal["id"], evaluation["audit_id"]))
            barrier = threading.Barrier(2)
            def approve(item):
                barrier.wait()
                try:
                    return knowledge.review_rule(Database(url, scratch=True), item[0], reviewer="owner",
                        decision="approve", reason="race fixture", evaluation_id=item[1])
                except (knowledge.DesignKnowledgeRefused, OperationalError) as exc:
                    return exc
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(approve, candidates))
            winners = [result for result in outcomes if isinstance(result, dict)]
            self.assertEqual(len(winners), 1, outcomes)
            self.assertEqual(knowledge.verify_pins(db, [winners[0]["pin"]])[0]["pin"],
                             winners[0]["pin"])
            with db.session() as s:
                self.assertEqual(len(list(s.scalars(select(DesignRule).where(
                    DesignRule.state == "approved")))), 1)

    def test_disjoint_rules_and_fail_closed_scope_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{tmp}/scoped.db", scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            with db.session() as s:
                p = BenchmarkProduct(ref="scoped-fixture", seller="fixture", files=[
                    {"name": "reference.pdf", "sha256": "a" * 64}])
                s.add(p)
                s.flush()
                observation = BenchmarkAnalysis(benchmark_id=p.id, file_sha256="a" * 64,
                    observations={"fully_readable": True, "dimensions": {"finishing": "absent"}})
                s.add(observation)
                s.flush()
                source_id = observation.id
            licence.capture_purchase(db, "scoped-fixture")
            review.review_analysis(db, source_id, reviewer="owner", decision="reviewed", reason="review")
            for ref in ["scoped-fixture", *(b.ref for b in code_benchmarks())]:
                record_fingerprint(db, ref, text="quasar violet lantern willow indigo river meadow")
            rules = {}
            for family in ("flat_rows", "joined_rounds"):
                JobQueue(db).enqueue("orchestrator", "teardown.analyse_sweep",
                    {"construction_family": family}, idempotency_key=f"scope-sweep:{family}")
                self.assertTrue(Worker(db, name=f"scope-{family}",
                                       job_types=["teardown.analyse_sweep"]).run_once())
                with db.session() as s:
                    proposal = next(r for r in s.scalars(select(DesignRule).where(
                        DesignRule.state == "proposed")) if r.scope.get("construction_family") == family)
                    proposal_id = proposal.id
                evaluation = design_eval.evaluate(db, proposal_id)
                self.assertEqual(evaluation["state"], "passed", evaluation)
                opposite = "joined_rounds" if family == "flat_rows" else "flat_rows"
                out_of_scope = next(slug for slug, build in design_eval._LAUNCH_CASES
                                    if launch0.cir_for(build).construction == opposite)
                tampered = copy.deepcopy(evaluation)
                case = next(item for item in tampered["cases"] if item["case"] == out_of_scope)
                case["after"]["finishing_actions_listed"] += 1
                self.assertEqual(design_eval.classify_evaluation(tampered), "regression")
                tampered = copy.deepcopy(evaluation)
                tampered.pop("out_of_scope_controls")
                self.assertEqual(design_eval.classify_evaluation(tampered), "insufficient_evidence")
                result = knowledge.review_rule(db, proposal_id, reviewer="owner", decision="approve",
                    reason="independent review", evaluation_id=evaluation["audit_id"])
                rules[family] = result["pin"]
            with db.session() as s:
                active = list(s.scalars(select(DesignRule).where(DesignRule.state == "approved")))
                self.assertEqual({r.active_slot for r in active}, {2, 3})
                guard = s.scalar(select(DesignRule).where(DesignRule.active_slot == 1))
                self.assertEqual(guard.state, "retired")
                self.assertEqual(guard.key, "system_design_scope_guard")
            flat = next(launch0.cir_for(key) for _, key in design_eval._LAUNCH_CASES
                        if launch0.cir_for(key).construction == "flat_rows")
            joined = next(launch0.cir_for(key) for _, key in design_eval._LAUNCH_CASES
                          if launch0.cir_for(key).construction == "joined_rounds")
            for family, cir in (("flat_rows", flat), ("joined_rounds", joined)):
                records = knowledge.applicable(db, {"writer_section": "finishing",
                                                    "construction_family": family})
                self.assertEqual([r["pin"] for r in records], [rules[family]])
                self.assertEqual([r["pin"] for r in knowledge.applicable_to_cir(db, cir)],
                                 [rules[family]])
                pinned = knowledge.freeze_pins(db, cir, [rules[family]])
                self.assertEqual(knowledge.verify_cir_pins(db, pinned)[0]["pin"], rules[family])
                self.assertNotEqual(write_pattern(cir, compile_cir(cir)),
                                    write_pattern(pinned, compile_cir(pinned)))
            self.assertEqual(knowledge.applicable(db, {"writer_section": "finishing"}), [])
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.freeze_pins(db, flat, [rules["joined_rounds"]])
            forged = copy.deepcopy(flat)
            forged.provenance.primitives_used += (markers.marker("include_finishing_checklist",
                                                                  rules["joined_rounds"]),)
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_cir_pins(db, forged)
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.freeze_pins(db, flat, list(rules.values()))
            global_candidate = knowledge.propose(db, key="global_scope", producer="analyst",
                statement={"rule": "include_finishing_checklist", "parameters": {}},
                scope={"writer_section": "finishing"}, provenance=[{"kind": "analysis", "id": source_id}])
            global_eval = design_eval.evaluate(db, global_candidate["id"])
            self.assertEqual(global_eval["state"], "passed")
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(db, global_candidate["id"], reviewer="owner", decision="approve",
                                      reason="conflict", evaluation_id=global_eval["audit_id"])
            # Refreshing one scope must leave its disjoint neighbor active.
            record_fingerprint(db, "scoped-fixture", text="cedar indigo velvet galaxy orange orchid forest")
            refreshed = design_revalidation.evaluate(db, rules["flat_rows"]["rule_id"])
            self.assertEqual(refreshed["state"], "passed")
            renewed = knowledge.review_rule(db, rules["flat_rows"]["rule_id"], reviewer="owner",
                decision="reapprove", reason="current evidence", evaluation_id=refreshed["audit_id"])
            self.assertEqual(knowledge.verify_pins(db, [renewed["pin"]])[0]["pin"], renewed["pin"])
            with db.session() as s:
                self.assertEqual(s.get(DesignRule, rules["joined_rounds"]["rule_id"]).state, "approved")
            with db.session() as s:
                guard = s.scalar(select(DesignRule).where(DesignRule.active_slot == 1))
                s.delete(guard)
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.verify_pins(db, [renewed["pin"]])
            # A deliberately repaired guard remains non-approved and lets the
            # owner retire both disjoint rules before approving a global rule.
            with db.session() as s:
                s.add(DesignRule(key="system_design_scope_guard", version=1, statement={}, scope={},
                                 provenance=[], producer="scope_guard", state="retired", active_slot=1))
            for family in ("flat_rows", "joined_rounds"):
                knowledge.review_rule(db, rules[family]["rule_id"], reviewer="owner", decision="retire",
                                      reason="switch to global scope")
            fresh_global = design_eval.evaluate(db, global_candidate["id"])
            self.assertEqual(fresh_global["state"], "passed")
            global_approval = knowledge.review_rule(db, global_candidate["id"], reviewer="owner",
                decision="approve", reason="reviewed global rule", evaluation_id=fresh_global["audit_id"])
            self.assertEqual(knowledge.verify_pins(db, [global_approval["pin"]])[0]["pin"],
                             global_approval["pin"])
            with db.session() as s:
                only = s.scalar(select(DesignRule).where(DesignRule.active_slot == 1))
                self.assertEqual(only.id, global_candidate["id"])
                self.assertEqual(only.state, "approved")
            conflict = knowledge.propose(db, key="flat_conflict", producer="analyst",
                statement={"rule": "include_finishing_checklist", "parameters": {}},
                scope={"writer_section": "finishing", "construction_family": "flat_rows"},
                provenance=[{"kind": "analysis", "id": source_id}])
            conflict_eval = design_eval.evaluate(db, conflict["id"])
            self.assertEqual(conflict_eval["state"], "passed")
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(db, conflict["id"], reviewer="owner", decision="approve",
                    reason="conflicts with global scope", evaluation_id=conflict_eval["audit_id"])
            unmeasured = knowledge.propose(db, key="spiral_unmeasured", producer="analyst",
                statement={"rule": "include_finishing_checklist", "parameters": {}},
                scope={"writer_section": "finishing", "construction_family": "spiral_rounds"},
                provenance=[{"kind": "analysis", "id": source_id}])
            unsupported = design_eval.evaluate(db, unmeasured["id"])
            self.assertEqual(unsupported["state"], "insufficient_evidence")
            with self.assertRaises(knowledge.DesignKnowledgeRefused):
                knowledge.review_rule(db, unmeasured["id"], reviewer="owner", decision="approve",
                    reason="no held-out cases", evaluation_id=unsupported["audit_id"])


if __name__ == "__main__":
    unittest.main()
