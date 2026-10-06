"""v1.1 lane A: the Executive Orchestrator gives idle departments evidence-driven work.

F-890, F-892, F-893, F-894, F-929, F-930 and PRIORITY ZERO ("an empty queue must not mean an
idle company"), plus the §95 test "block one department on an owner action overnight:
independent departments continue READY work".
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import (DEFAULT_AGENTS, FORBIDDEN_COMBINATIONS,  # noqa: E402
                                         Registry)
from brambleloop.autonomy import charters, generators, memory, orchestrator  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Job, JobStatus, Listing, OwnerAction,  # noqa: E402
                                     PatternVersion, Product, SupportCase)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, Scheduler, Worker, handlers  # noqa: E402


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="v11a-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def drain(db, limit=200) -> Worker:
    w = Worker(db, "drain")
    for _ in range(limit):
        if not w.run_once():
            break
    return w


def jobs(db, **where):
    with db.session() as s:
        q = select(Job)
        for k, v in where.items():
            q = q.where(getattr(Job, k) == v)
        rows = list(s.scalars(q))
        for r in rows:
            s.expunge(r)
        return rows


# ---- charters --------------------------------------------------------------------------


def test_eleven_charters_are_valid_and_cover_every_wired_job_type():
    assert charters.validate() == []
    names = {c.name for c in charters.CHARTERS}
    assert len(names) == 11, names
    for expected in ("Executive / COO", "Intelligence", "Product & Design",
                     "Product Truth / QA", "Visual", "Store / Commerce", "Customer Support",
                     "Finance / Accounting", "Growth / Marketing", "Learn / Improvement",
                     "Platform / Reliability"):
        assert expected in names, expected
    wired = set(handlers.known()) | {jt for _n, _a, jt, _p in CADENCES} | {
        j for a in DEFAULT_AGENTS for j in a["allowed_job_types"]}
    assert len(wired) > 100, len(wired)
    unowned = sorted(jt for jt in wired if charters.department_of(jt) is None)
    assert unowned == [], unowned


def test_every_charter_has_kpis_with_guardrails_and_a_generator():
    assert len(charters.CHARTERS) == 11
    for ch in charters.CHARTERS:
        assert ch.mission and ch.escalation and ch.evidence_requirement, ch.key
        assert ch.generatable, ch.key
        ups = [k for k in ch.kpis if k.direction == "up"]
        assert ups, ch.key
        assert all(k.guardrails for k in ups), ch.key
        assert ch.forbidden, ch.key


def test_no_protected_job_type_is_ever_generatable_and_coo_is_structurally_forbidden():
    assert charters.PROTECTED_JOB_TYPES >= {"store.publish", "store.activate", "ads.campaign",
                                            "support.reply"}
    generatable = {jt for ch in charters.CHARTERS for jt in ch.generatable}
    assert generatable, "no generatable work at all"
    assert not (generatable & charters.PROTECTED_JOB_TYPES)
    coo = next(a for a in DEFAULT_AGENTS if a["name"] == "coo")
    assert not (set(coo["allowed_job_types"]) & charters.PROTECTED_JOB_TYPES)
    assert charters.PROTECTED_JOB_TYPES <= FORBIDDEN_COMBINATIONS["coo"]
    # Every generatable job type has a handler and a permitted agent.
    for jt in generatable:
        assert handlers.get(jt) is not None, jt
        agent = orchestrator._agent_for(jt)
        assert agent, jt
        spec = next(a for a in DEFAULT_AGENTS if a["name"] == agent)
        assert jt in spec["allowed_job_types"], (agent, jt)
        assert jt not in FORBIDDEN_COMBINATIONS.get(agent, set()), (agent, jt)


def test_the_orchestrator_is_a_scheduled_cadence_with_a_permitted_agent():
    rows = [c for c in CADENCES if c[2] == "autonomy.orchestrate"]
    assert rows == [("executive_orchestrator", "coo", "autonomy.orchestrate", 900)], rows


# ---- idle departments get work ----------------------------------------------------------


def test_every_idle_department_is_given_evidence_backed_work():
    db = boot()
    report = orchestrator.tick(db)
    states = {k: v["state"] for k, v in report["departments"].items()}
    assert len(states) == 11, states
    assert all(s == "GENERATED" for s in states.values()), states
    assert report["errors"] == {}
    assert len(report["missions"]) == 11
    for m in report["missions"]:
        job = JobQueue(db).get(m["job_id"])
        assert job.inputs["source"] == "autonomy"
        assert job.inputs["evidence"], m
        assert job.job_type not in charters.PROTECTED_JOB_TYPES
        mem = memory.get(db, m["key"])
        assert mem and mem["kind"] == "mission" and mem["sources"], m
    # Re-ticking with the same evidence does not duplicate anything.
    before = len(jobs(db))
    again = orchestrator.tick(db)
    assert all(v["state"] == "BUSY" for v in again["departments"].values()), again
    assert len(jobs(db)) == before


def test_a_busy_department_is_left_alone():
    db = boot()
    JobQueue(db).enqueue("support", "support.triage", {"cadence": "support_triage"})
    report = orchestrator.tick(db)
    assert report["departments"]["support"]["state"] == "BUSY"
    assert report["departments"]["finance"]["state"] == "GENERATED"
    assert len(jobs(db, job_type="support.triage")) == 1


def test_handoff_evidence_outranks_routine_work():
    db = boot()
    with db.session() as s:
        s.add(SupportCase(customer_ref="c-1", question="Is row 12 right?"))
    report = orchestrator.tick(db)
    m = next(x for x in report["missions"] if x["department"] == "support")
    assert m["source"] == "handoff" and m["job_type"] == "support.triage", m
    job = JobQueue(db).get(m["job_id"])
    assert any(e.startswith("support_cases") for e in job.inputs["evidence"]), job.inputs


def test_completed_missions_are_measured_and_the_next_tick_moves_on():
    db = boot()
    first = orchestrator.tick(db)
    drain(db)
    second = orchestrator.tick(db)
    rec = second["reconciled"]
    assert rec["useful"] + rec["noop"] + rec["failed"] == len(first["missions"]), rec
    closed = memory.recall(db, kind="mission", limit=100)
    assert closed and all(m["state"] in ("useful", "noop", "failed", "queued")
                          for m in closed)
    assert sum(1 for m in closed if m["state"] != "queued") == len(first["missions"])
    # No key generated twice.
    keys = [j.idempotency_key for j in jobs(db) if (j.inputs or {}).get("source") == "autonomy"]
    assert keys and len(keys) == len(set(keys))


# ---- protected actions become approvals --------------------------------------------------


def _certified_listing(db, slug="tea-cosy"):
    with db.session() as s:
        p = Product(slug=slug, title="Tea cosy")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True,
                             certificate={"ok": True}))
        s.add(Listing(product_slug=slug, version="1.0.0", title="t", description="d"))


def test_protected_work_becomes_one_owner_approval_never_a_job():
    db = boot()
    _certified_listing(db)
    r1 = orchestrator.tick(db)
    drain(db)
    r2 = orchestrator.tick(db)
    assert r1["approvals"], r1
    assert not jobs(db, job_type="store.publish")
    for jt in charters.PROTECTED_JOB_TYPES:
        assert not [j for j in jobs(db, job_type=jt)
                    if (j.inputs or {}).get("source") == "autonomy"], jt
    with db.session() as s:
        n = s.scalar(select(func.count()).select_from(OwnerAction).where(
            OwnerAction.requirement_key == "autonomy:store_commerce:publication_review"))
    assert n == 1, n
    assert r2["approvals"] and not r2["approvals"][0]["created"], r2["approvals"]


def test_the_enqueue_boundary_refuses_protected_and_out_of_charter_work():
    db = boot()
    ch = charters.BY_KEY["store_commerce"]
    snap = generators.Snapshot.read(db, datetime.now(timezone.utc))
    for jt in ("store.publish", "finance.reconcile"):
        c = generators.Candidate(department=ch.key, job_type=jt, value=99, source="test",
                                 reason="r", fingerprint=f"t:{jt}")
        try:
            orchestrator._enqueue_mission(db, JobQueue(db), ch, c, snap.now)
        except orchestrator.ProtectedActionRefused:
            continue
        raise AssertionError(f"{jt} was enqueued for store_commerce")
    assert not jobs(db)


# ---- isolation (§95) ----------------------------------------------------------------------


def test_blocked_and_failing_departments_do_not_stop_the_others():
    db = boot()
    memory.block_department(db, "store_commerce", reason="awaiting owner Etsy approval",
                            owner_action="OA-test")
    real = generators.candidates

    def broken(db_, charter, snap):
        if charter.key == "visual":
            raise RuntimeError("visual evidence store unreadable")
        return real(db_, charter, snap)

    generators.candidates = broken
    try:
        report = orchestrator.tick(db)
    finally:
        generators.candidates = real
    states = {k: v["state"] for k, v in report["departments"].items()}
    assert states["store_commerce"] == "BLOCKED", states
    assert states["visual"] == "DEGRADED", states
    others = [k for k in states if k not in ("store_commerce", "visual")]
    assert len(others) == 9
    assert all(states[k] == "GENERATED" for k in others), states
    assert not [m for m in report["missions"] if m["department"] == "store_commerce"]
    assert "visual" in report["errors"]
    w = drain(db)
    assert w.stats.completed >= 9, w.stats
    # Unblocking lets the department work again.
    memory.unblock_department(db, "store_commerce")
    after = orchestrator.tick(db)
    assert after["departments"]["store_commerce"]["state"] in ("GENERATED", "SATURATED")


def test_repeated_noop_missions_are_suppressed_from_measured_outcomes():
    db = boot()
    now = datetime.now(timezone.utc)
    for i in range(3):
        memory.remember(db, f"autonomy:growth:fake{i}", kind="mission", department="growth",
                        state="noop", body={"job_type": "growth.distribution"},
                        now=now - timedelta(minutes=10 - i))
    supp = orchestrator._suppressed(db, charters.BY_KEY["growth"], now)
    assert "growth.distribution" in supp, supp
    report = orchestrator.tick(db, now=now)
    m = next(x for x in report["missions"] if x["department"] == "growth")
    assert m["job_type"] != "growth.distribution", m


def test_an_empty_queue_wakes_the_orchestrator_immediately():
    db = boot()
    q = JobQueue(db)
    now = datetime.now(timezone.utc)
    assert orchestrator.idle_wake(db, q, now=now) is True
    assert orchestrator.idle_wake(db, q, now=now) is False      # pending now: no flood
    db2 = boot()
    Scheduler(db2).tick()       # cadences pending -> no idle wake
    assert not [j for j in jobs(db2, job_type="autonomy.orchestrate")
                if (j.inputs or {}).get("wake") == "idle_queue"]


def test_the_orchestrate_job_runs_through_the_worker_and_permission_layer():
    db = boot()
    JobQueue(db).enqueue("coo", "autonomy.orchestrate", {})
    w = Worker(db, "w")
    assert w.run_once() is True
    assert w.stats.completed == 1 and w.stats.denied == 0, w.stats
    done = jobs(db, job_type="autonomy.orchestrate")[0]
    assert done.status == JobStatus.DONE
    assert done.outputs["enqueued"] == 11, done.outputs


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
