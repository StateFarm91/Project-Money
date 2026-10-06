"""#34 acted on (C-68): a tripped loop is suspended, unchanged polling backs off, progress is
measured per iteration and per dollar, and a retry needs a changed hypothesis.

Every sweep runs `ops.thrash` through the worker; the effect is read where it acts -- the
scheduler that would have re-enqueued the loop, and the dead-letter re-drive.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, Job, JobStatus, utcnow  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Scheduler, Worker  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/thrash.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _done(db, job_type, outputs, *, cost=0.0, n=3, inputs=None, status=JobStatus.DONE,
          error=""):
    now = utcnow()
    with db.session() as s:
        for i in range(n):
            s.add(Job(agent="market_radar", job_type=job_type,
                      inputs=inputs if inputs is not None else {"cadence": "c"},
                      status=status, outputs=outputs, cost_cad=cost, last_error=error or None,
                      started_at=now - timedelta(minutes=30 - i),
                      finished_at=now - timedelta(minutes=20 - i)))


def _sweep(db):
    job = JobQueue(db).enqueue("orchestrator", "ops.thrash", {},
                               idempotency_key=f"sweep:{utcnow().timestamp()}", priority=0)
    Worker(db, "thrash", job_types=["ops.thrash"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        return dict(row.outputs)


def _enqueued(db, job_type):
    with db.session() as s:
        return [j for j in s.scalars(select(Job).where(Job.job_type == job_type,
                                                       Job.status == JobStatus.PENDING))]


def test_a_paid_loop_is_suspended_until_the_hypothesis_changes():
    db = _db()
    _done(db, "mjs.scan", {"same": 1, "at": "t"}, cost=0.2,
          inputs={"cadence": "mjs_scan", "x": 1})
    out = _sweep(db)
    assert out["tripped"] == 1
    assert "mjs.scan" in out["suspended"]
    assert out["progress"]["mjs.scan"]["progress_per_iteration"] == 0
    assert out["progress"]["mjs.scan"]["progress_per_dollar"] == 0
    Scheduler(db).tick()
    assert not _enqueued(db, "mjs.scan"), "the next cadence window restarted the loop"
    # C-85 (Codex P08): a new build is NOT by itself a changed hypothesis -- a deploy that
    # touched a listing template says nothing about the radar loop -- so a new commit alone
    # leaves the suspension standing.
    from brambleloop.swarm import orchestrate

    os.environ["BRAMBLELOOP_COMMIT"] = "f" * 40
    try:
        Scheduler(db).tick()
        assert not _enqueued(db, "mjs.scan"), "a new build alone lifted the suspension"
    finally:
        os.environ.pop("BRAMBLELOOP_COMMIT", None)
    # A change to the code that runs the loop is: the suspension lifts and the cadence runs.
    real = orchestrate.handler_digest
    orchestrate.handler_digest = lambda jt: "changed-handler-source"
    try:
        Scheduler(db).tick()
        assert _enqueued(db, "mjs.scan")
    finally:
        orchestrate.handler_digest = real


def test_unchanged_free_polling_backs_off_and_progress_lifts_it():
    db = _db()
    _done(db, "etsy.probe", {"reachable": False, "checked_at": "x"})
    out = _sweep(db)
    applied = {a["job_type"]: a for a in out["backoff"]["applied"]}
    assert applied["etsy.probe"]["factor"] == 2
    first_until = applied["etsy.probe"]["until"]
    Scheduler(db).tick()
    assert not _enqueued(db, "etsy.probe")
    # C-80 defect 5 (Codex P07): a second sweep that sees *no new run* is not a new
    # observation. The level stays at 1, the factor at 2 and the absolute deadline exactly
    # where the first sweep put it. (This assertion used to enshrine the defect: factor 4
    # after a sweep with nothing new.)
    out = _sweep(db)
    again = {a["job_type"]: a for a in out["backoff"]["applied"]}["etsy.probe"]
    assert again["factor"] == 2 and again["unchanged"] is True
    assert again["until"] == first_until, "the deadline was refreshed with no new observation"
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == f"{orc.BACKOFF_SIGNATURE_PREFIX}etsy.probe",
            Incident.resolved.is_(False)))
        assert inc.detail["suspension"]["level"] == 1
        assert inc.detail["suspension"]["suspend_until"] == first_until
    # a NEW run that observes the same unchanged state is the fourth identical observation:
    # now the backoff doubles, and the deadline moves later, never earlier
    _done(db, "etsy.probe", {"reachable": False, "checked_at": "y"}, n=1)
    out = _sweep(db)
    doubled = {a["job_type"]: a for a in out["backoff"]["applied"]}["etsy.probe"]
    assert doubled["factor"] == 4 and doubled["unchanged"] is False
    assert doubled["until"] > first_until
    # the state changes: progress lifts the backoff
    _done(db, "etsy.probe", {"reachable": True}, n=1)
    out = _sweep(db)
    assert "etsy.probe" in out["backoff"]["lifted"]
    Scheduler(db).tick()
    assert _enqueued(db, "etsy.probe")


def test_liveness_watchdogs_are_never_backed_off():
    db = _db()
    _done(db, "ops.health", {"ok": True})
    out = _sweep(db)
    assert "ops.health" not in {a["job_type"] for a in out["backoff"]["applied"]}


def test_a_dead_call_the_breaker_tripped_is_not_redriven_under_the_same_build():
    db = _db()
    _done(db, "etsy.probe", None, status=JobStatus.DEAD, error="401 unauthorised",
          inputs={"x": 1})
    assert _sweep(db)["tripped"] == 1
    result = JobQueue(db).requeue_dead(job_types=["etsy.probe"])
    assert not result["requeued"] and result["skipped"]
    assert all("changed hypothesis" in s["reason"] for s in result["skipped"])
    # C-85: a new build alone is still the same hypothesis; a change to the handler's code is
    # not.
    from brambleloop.swarm import orchestrate

    os.environ["BRAMBLELOOP_COMMIT"] = "e" * 40
    try:
        result = JobQueue(db).requeue_dead(job_types=["etsy.probe"])
        assert not result["requeued"], ("a new build alone re-drove the dead call", result)
        real = orchestrate.handler_digest
        orchestrate.handler_digest = lambda jt: "changed-handler-source"
        try:
            result = JobQueue(db).requeue_dead(job_types=["etsy.probe"])
        finally:
            orchestrate.handler_digest = real
        assert result["requeued"], result
    finally:
        os.environ.pop("BRAMBLELOOP_COMMIT", None)


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
