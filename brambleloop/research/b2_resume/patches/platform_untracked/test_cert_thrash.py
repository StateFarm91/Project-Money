"""#34 acted on (C-68): a tripped loop is suspended, unchanged polling backs off, progress is
measured per iteration and per dollar, and a retry needs a changed hypothesis.

Every sweep runs `ops.thrash` through the worker; the effect is read where it acts -- the
scheduler that would have re-enqueued the loop, and the dead-letter re-drive.
"""
from __future__ import annotations

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
    # a new build is a changed hypothesis: the suspension lifts and the cadence runs again
    os.environ["BRAMBLELOOP_COMMIT"] = "f" * 40
    try:
        Scheduler(db).tick()
        assert _enqueued(db, "mjs.scan")
    finally:
        os.environ.pop("BRAMBLELOOP_COMMIT", None)


def test_unchanged_free_polling_backs_off_and_progress_lifts_it():
    db = _db()
    _done(db, "etsy.probe", {"reachable": False, "checked_at": "x"})
    out = _sweep(db)
    applied = {a["job_type"]: a for a in out["backoff"]["applied"]}
    assert applied["etsy.probe"]["factor"] == 2
    Scheduler(db).tick()
    assert not _enqueued(db, "etsy.probe")
    # still unchanged: the backoff doubles
    out = _sweep(db)
    assert {a["job_type"]: a for a in out["backoff"]["applied"]}["etsy.probe"]["factor"] == 4
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
    os.environ["BRAMBLELOOP_COMMIT"] = "e" * 40
    try:
        result = JobQueue(db).requeue_dead(job_types=["etsy.probe"])
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
