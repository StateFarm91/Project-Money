"""W3 lane D: Laura's executive tick -- Laura -> COO -> departments -> results -> Laura.

From real database state the tick sets durable priorities with evidence, delegates through the
COO's mission boundary (SAFE_GENERATED only, zero protected jobs), reviews results with the
honest useful-work judge, challenges weak work, escalates repeats, gives an empty queue safe
useful work, and reports an unchanged company as a no-op.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import charters, memory  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Incident, Job, JobStatus, Lesson,  # noqa: E402
                                     OwnerAction)
from brambleloop.laura import executive  # noqa: E402
from brambleloop.laura.executive import loop  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
from brambleloop.runtime.worker import CADENCES, Scheduler, Worker  # noqa: E402


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="w3d-ex-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def drain(db, limit=60, job_types=None) -> Worker:
    w = Worker(db, "w3d", job_types=job_types)
    for _ in range(limit):
        if not w.run_once():
            break
    return w


def all_jobs(db) -> list:
    with db.session() as s:
        rows = list(s.scalars(select(Job)))
        for r in rows:
            s.expunge(r)
    return rows


def laura_jobs(db) -> list:
    return [j for j in all_jobs(db) if (j.inputs or {}).get("laura")]


def assert_no_protected(db):
    jobs = all_jobs(db)
    assert jobs, "no jobs at all"
    bad = [j.job_type for j in jobs if j.job_type in charters.PROTECTED_JOB_TYPES]
    assert bad == [], bad
    lj = laura_jobs(db)
    assert lj, "Laura delegated nothing"
    outside = [j.job_type for j in lj if j.job_type not in charters.SAFE_GENERATED]
    assert outside == [], outside


def test_tick_from_real_state_sets_priorities_delegates_and_reviews():
    db = boot()
    with db.session() as s:
        s.add(Incident(severity="P1", signature="pattern.row_count_mismatch",
                       product_slug="moss-basket", summary="row 14 stitch count disagrees"))
        s.add(OwnerAction(requirement_key="test:etsy_settings", action="Confirm shop settings",
                          reason="needs login"))
    r1 = executive.tick(db)
    keys = {p["key"]: p for p in r1["priorities"]}
    inc = [p for p in r1["priorities"] if p["key"].startswith("laura:incident:")]
    assert len(inc) == 1 and inc[0]["department"] == "product_truth", r1["priorities"]
    assert inc[0]["job_type"] == "ops.sentinel"
    assert "laura:owner_decisions:open" in keys
    # durable, with reasons and evidence
    stored = {p["key"]: p for p in executive.priorities(db)}
    assert stored[inc[0]["key"]]["status"] == "delegated"
    assert stored[inc[0]["key"]]["evidence"][0].startswith("incidents:")
    assert stored["laura:owner_decisions:open"]["status"] == "awaiting_owner"
    assert r1["delegated"] >= 1 and r1["new_decisions"] >= 3
    kinds = {h["kind"] for h in executive.history(db, limit=200)}
    assert {"priority.set", "delegation"} <= kinds, kinds
    # the delegation went through the COO's mission mechanism
    d = executive.history(db, kind="delegation", limit=50)
    assert d, "no delegation"
    mkey = d[-1]["key"].split(":", 1)[1]
    assert mkey.startswith("autonomy:") and memory.get(db, mkey)["kind"] == "mission"
    drain(db)
    r2 = executive.tick(db)
    assert r2["review"]["reviewed"] >= 1, r2["review"]
    reviews = executive.history(db, kind="review", limit=50)
    assert reviews and all(" -> " in r["subject"] for r in reviews)
    assert_no_protected(db)
    # every decision is bound to her verified identity and records its cognition
    hist = executive.history(db, limit=500)
    assert hist and all(h["identity_sha256"] == r1["identity_sha256"] for h in hist)
    assert all(h["cognition"]["engine"] == "deterministic" for h in hist)
    # her actions are on the company timeline as hers
    ev = [e for e in memory.events(db, limit=200) if e["actor"] == "laura"]
    assert ev, "no Laura timeline events"


def test_empty_queue_gets_safe_useful_work():
    db = boot()
    assert not all_jobs(db)
    r = executive.tick(db)
    assert r["idle"] is True
    assert r["idle_delegated"] >= 1, r["outcomes"]
    idle = [p for p in r["priorities"] if p["key"].startswith("laura:idle_work:")]
    assert idle and all(p["job_type"] in charters.SAFE_GENERATED for p in idle)
    drain(db)
    r2 = executive.tick(db)
    assert r2["review"]["accepted"] >= 1, r2["review"]      # honest: at least one was useful
    s = executive.summary(db)
    assert s["status"] == "OK" and s["delegation_outcomes"]["useful"] >= 1, s
    assert_no_protected(db)


def test_an_unchanged_company_is_an_honest_noop():
    db = boot()
    r1 = executive.tick(db)
    assert r1["new_decisions"] > 0
    # Work deferred by the per-tick cap is delegated on the next tick (a real act); after
    # that, with nothing run and nothing changed, a tick records nothing.
    for _ in range(4):
        r2 = executive.tick(db)
        if r2["new_decisions"] == 0:
            break
        assert r2["decisions_by_kind"].keys() <= {"delegation"}, r2["decisions_by_kind"]
    assert r2["new_decisions"] == 0, r2["decisions_by_kind"]
    r3 = executive.tick(db)
    assert r3["new_decisions"] == 0 and r3["delegated"] == 0, r3["decisions_by_kind"]
    # through the worker: the handler reports work_done and the judge reads it
    # Through the worker: the handler reports work_done and the judge reads it. A provider
    # reading can legitimately change between ticks (a real act: a priority closes), so the
    # worker runs until the company is steady, which must happen within three ticks.
    q = JobQueue(db)
    outs = []
    for i in range(3):
        q.enqueue("laura", executive.EXEC_JOB, {}, idempotency_key=f"t:noop:{i}")
        drain(db, job_types=[executive.EXEC_JOB])
        j = [x for x in all_jobs(db) if x.idempotency_key == f"t:noop:{i}"][0]
        assert j.status == JobStatus.DONE, (j.status, j.last_error)
        outs.append(j.outputs)
        if j.outputs["work_done"] == 0:
            break
    assert outs[-1]["work_done"] == 0, outs
    assert pipeline.did_no_work(outs[-1], executive.EXEC_JOB)
    assert all(set(o["decisions_by_kind"]) <= {"priority.closed", "priority.set"}
               for o in outs[:-1]), outs
    assert not pipeline.did_no_work({"ran": True, "work_done": 3}, executive.EXEC_JOB)


def _mission_job(db, decision) -> Job:
    mkey = decision["key"].split(":", 1)[1]
    jid = memory.get(db, mkey)["body"]["job_id"]
    with db.session() as s:
        j = s.get(Job, jid)
        s.expunge(j)
    return j


def _finish(db, job_id, *, status, outputs=None, error=""):
    with db.session() as s:
        j = s.get(Job, job_id)
        j.status = status
        j.outputs = outputs or {}
        j.last_error = error
        j.finished_at = datetime.now(timezone.utc)


def test_weak_work_is_challenged_failed_work_reworked_once_then_escalated():
    db = boot()
    executive.tick(db)
    ds = executive.history(db, kind="delegation", limit=50)
    assert len(ds) >= 2, ds
    weak, bad = _mission_job(db, ds[0]), _mission_job(db, ds[1])
    _finish(db, weak.id, status=JobStatus.DONE, outputs={"ran": False})
    _finish(db, bad.id, status=JobStatus.DEAD, error="RuntimeError: reader broke")
    # everything else Laura delegated stays pending, so only these two close
    r = executive.tick(db)
    assert r["review"]["weak"] == 1 and r["review"]["failed"] == 1, r["review"]
    ch = executive.history(db, kind="challenge", limit=10)
    rw = executive.history(db, kind="rework", limit=10)
    assert len(ch) == 1 and len(rw) == 1, (ch, rw)
    assert "autonomy.department_review" in ch[0]["subject"]
    assert bad.job_type in rw[0]["subject"]
    assert any(e.startswith("company_memory:") for e in rw[0]["evidence"])
    # the rework fails as well -> a routed Lesson, not a third run
    rework_job = _mission_job(db, rw[0])
    assert rework_job.job_type == bad.job_type and rework_job.id != bad.id
    _finish(db, rework_job.id, status=JobStatus.DEAD, error="RuntimeError: still broken")
    r = executive.tick(db)
    esc = executive.history(db, kind="escalation", limit=10)
    assert len(esc) == 1, esc
    with db.session() as s:
        lessons = list(s.scalars(select(Lesson).where(Lesson.subject.like("Laura escalation%"))))
    assert len(lessons) == 1 and "learn" in lessons[0].routed_to
    assert len(executive.history(db, kind="rework", limit=10)) == 1     # no rework loop
    r = executive.tick(db)
    assert len(executive.history(db, kind="escalation", limit=10)) == 1
    assert_no_protected(db)


def test_protected_work_becomes_an_owner_action_never_a_job():
    db = boot()
    from brambleloop.laura.core import identity

    t = loop._Tick(db, datetime.now(timezone.utc), identity.ensure(db)["sha256"])
    p = loop.Priority(rule="launch", subject="publish", department="store_commerce",
                      title="Publish the prepared listings", reason="drafts are certified",
                      score=90, evidence=["listings:1"], job_type="store.publish")
    out = loop._delegate(t, None, p)
    assert out["outcome"] == "owner_action", out
    with db.session() as s:
        oa = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == "laura:store_commerce:store.publish")))
    assert len(oa) == 1
    assert not [j for j in all_jobs(db) if j.job_type == "store.publish"]
    assert executive.history(db, kind="owner_action", limit=5)
    # out-of-charter, non-protected work is refused outright
    p2 = loop.Priority(rule="x", subject="y", department="growth", title="certify",
                       reason="r", score=1, job_type="gate.certify")
    assert loop._delegate(t, None, p2)["outcome"] == "blocked"
    assert not [j for j in all_jobs(db) if j.job_type == "gate.certify"]


def test_the_tick_is_a_scheduled_cadence_run_by_the_real_worker():
    names = [c for c in CADENCES if c[2] == executive.EXEC_JOB]
    assert names == [("laura_executive", "laura", executive.EXEC_JOB, 600)], names
    db = boot()
    enq = Scheduler(db).tick()
    assert "laura_executive" in enq, enq
    w = drain(db, limit=5, job_types=[executive.EXEC_JOB])
    assert w.stats.denied == 0, w.stats
    j = [x for x in all_jobs(db) if x.job_type == executive.EXEC_JOB][0]
    assert j.agent == "laura" and j.status == JobStatus.DONE, (j.status, j.last_error)
    assert j.outputs["work_done"] > 0 and not pipeline.did_no_work(j.outputs, j.job_type)
    assert executive.summary(db)["status"] == "OK"


def test_results_wake_laura_when_the_coo_closes_her_mission():
    db = boot()
    q = JobQueue(db)
    executive.tick(db, q)
    assert executive.results_wake(db, q) is False          # nothing closed yet
    d = executive.history(db, kind="delegation", limit=5)[0]
    _finish(db, _mission_job(db, d).id, status=JobStatus.DONE, outputs={"ran": False})
    q.enqueue("coo", "autonomy.orchestrate", {}, idempotency_key="t:orch:1")
    drain(db, limit=3, job_types=["autonomy.orchestrate"])
    orch = [x for x in all_jobs(db) if x.job_type == "autonomy.orchestrate"][0]
    assert orch.outputs.get("laura_woken") is True, orch.outputs
    wake = [x for x in all_jobs(db) if x.job_type == executive.EXEC_JOB
            and (x.inputs or {}).get("wake") == "results"]
    assert len(wake) == 1


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
