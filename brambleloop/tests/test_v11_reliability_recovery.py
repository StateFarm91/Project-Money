"""v1.1 lane I: remote recovery actions (F-900) -- safe, idempotent, audited."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.ops import recovery, slo  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402

NOW = datetime.now(timezone.utc)
ACTOR = "owner"


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _job(db, *, status, lease=None, holder=None, attempts=1, job_type="finance.governor",
         run_after=None, last_error=None, key=None) -> int:
    with db.session() as s:
        j = Job(agent="cfo", job_type=job_type, status=status, inputs={}, attempts=attempts,
                max_attempts=3, leased_by=holder, lease_expires_at=lease,
                run_after=run_after or NOW - timedelta(hours=1), started_at=NOW - timedelta(hours=1),
                created_at=NOW - timedelta(hours=1), last_error=last_error,
                idempotency_key=key)
        s.add(j)
        s.flush()
        return j.id


def _audits(db):
    with db.session() as s:
        return [(r.action, r.artifact) for r in s.scalars(
            select(AuditLog).where(AuditLog.action.like("recovery.%")))]


def test_restart_stuck_job_is_idempotent_and_audited():
    db = _db()
    jid = _job(db, status=JobStatus.RUNNING, lease=NOW - timedelta(minutes=10), holder="dead-w")
    first = recovery.restart_stuck_job(db, jid, actor=ACTOR, request_id="r-1", now=NOW)
    assert first["done"] and not first["replayed"] and first["previous_holder"] == "dead-w"
    job = JobQueue(db).get(jid)
    assert job.status == JobStatus.PENDING and job.leased_by is None
    # The same tap again: nothing happens, the recorded result comes back.
    again = recovery.restart_stuck_job(db, jid, actor=ACTOR, request_id="r-1", now=NOW)
    assert again["replayed"] and again["job_id"] == jid
    audits = _audits(db)
    assert audits == [("recovery.restart_stuck_job", "recovery:r-1")], audits
    # The restarted job is claimable by a worker.
    claimed = JobQueue(db).claim("w2")
    assert claimed is not None and claimed.id == jid


def test_restart_refuses_a_job_on_a_live_lease_and_audits_the_refusal():
    db = _db()
    jid = _job(db, status=JobStatus.RUNNING, lease=NOW + timedelta(minutes=4), holder="alive")
    out = recovery.restart_stuck_job(db, jid, actor=ACTOR, request_id="r-2", now=NOW)
    assert out["done"] is False and "live lease" in out["refused"]
    assert JobQueue(db).get(jid).status == JobStatus.RUNNING
    assert _audits(db) == [("recovery.refused", "recovery:r-2")]
    # The refusal is also replayed, not re-attempted.
    assert recovery.restart_stuck_job(db, jid, actor=ACTOR, request_id="r-2",
                                      now=NOW)["replayed"] is True


def test_restart_brings_a_backed_off_failure_forward():
    db = _db()
    jid = _job(db, status=JobStatus.FAILED, run_after=NOW + timedelta(minutes=50))
    out = recovery.restart_stuck_job(db, jid, actor=ACTOR, request_id="r-3", now=NOW)
    assert out["done"] and out["was"] == "failed"
    assert JobQueue(db).get(jid).status == JobStatus.PENDING


def test_restart_refuses_done_and_unknown_jobs():
    db = _db()
    jid = _job(db, status=JobStatus.DONE)
    assert recovery.restart_stuck_job(db, jid, actor=ACTOR, request_id="r-4")["done"] is False
    assert recovery.restart_stuck_job(db, 99999, actor=ACTOR, request_id="r-5")["done"] is False


def test_actor_and_request_id_are_required():
    db = _db()
    for actor, rid in (("", "x"), (ACTOR, ""), (ACTOR, "y" * 200)):
        try:
            recovery.restart_stuck_job(db, 1, actor=actor, request_id=rid)
        except recovery.RecoveryRefused:
            continue
        raise AssertionError(f"accepted actor={actor!r} request_id={rid!r}")


def test_a_request_id_cannot_be_reused_for_a_different_action():
    db = _db()
    jid = _job(db, status=JobStatus.RUNNING, lease=NOW - timedelta(minutes=10), holder="d")
    recovery.restart_stuck_job(db, jid, actor=ACTOR, request_id="same", now=NOW)
    try:
        recovery.rerun_department_cycle(db, "finance_governor", actor=ACTOR, request_id="same")
    except recovery.RecoveryRefused:
        pass
    else:
        raise AssertionError("one request id performed two different actions")


def test_release_stale_lease_only_when_expired():
    db = _db()
    assert slo.acquire_lease(db, "scheduler", "old-holder", ttl_s=60, now=NOW - timedelta(minutes=5))
    out = recovery.release_stale_lease(db, "scheduler", actor=ACTOR, request_id="l-1", now=NOW)
    assert out["done"] and out["previous_holder"] == "old-holder"
    assert slo.lease_state(db, "scheduler", now=NOW)["holder"] is None
    assert slo.acquire_lease(db, "scheduler", "live", ttl_s=600, now=NOW)
    refused = recovery.release_stale_lease(db, "scheduler", actor=ACTOR, request_id="l-2", now=NOW)
    assert refused["done"] is False and "live" in refused["refused"]
    assert slo.lease_state(db, "scheduler", now=NOW)["holder"] == "live"


def test_rerun_cycle_enqueues_once_and_refuses_a_double_run():
    db = _db()
    out = recovery.rerun_department_cycle(db, "finance_governor", actor=ACTOR,
                                          request_id="c-1", now=NOW)
    assert out["done"] and out["mode"] == "enqueued", out
    job = JobQueue(db).get(out["job_id"])
    assert job.job_type == "finance.governor" and job.status == JobStatus.PENDING
    assert recovery.rerun_department_cycle(db, "finance_governor", actor=ACTOR,
                                           request_id="c-1", now=NOW)["replayed"] is True
    second = recovery.rerun_department_cycle(db, "finance_governor", actor=ACTOR,
                                             request_id="c-2", now=NOW)
    assert second["done"] is False and "in flight" in second["refused"]
    with db.session() as s:
        n = len(list(s.scalars(select(Job).where(Job.job_type == "finance.governor"))))
    assert n == 1


def test_rerun_redrives_a_defect_dead_letter_but_never_a_refusal():
    db = _db()
    dead = _job(db, status=JobStatus.DEAD, attempts=3, last_error="KeyError: boom")
    out = recovery.rerun_department_cycle(db, "finance_governor", actor=ACTOR,
                                          request_id="c-3", now=NOW)
    assert out["done"] and out["mode"] == "redrove_dead_letter" and out["job_id"] == dead, out
    j = JobQueue(db).get(dead)
    assert j.status == JobStatus.PENDING and j.attempts == 0

    db2 = _db()
    _job(db2, status=JobStatus.DEAD, attempts=3, job_type="finance.governor",
         last_error="capability not enabled: shadow mode")
    out2 = recovery.rerun_department_cycle(db2, "finance_governor", actor=ACTOR,
                                           request_id="c-4", now=NOW)
    assert out2["done"] is False and "refused on purpose" in out2["refused"], out2


def test_rerun_refuses_an_unknown_cadence():
    db = _db()
    out = recovery.rerun_department_cycle(db, "no_such_cadence", actor=ACTOR, request_id="c-5")
    assert out["done"] is False


def test_recent_lists_the_trail_newest_first():
    db = _db()
    recovery.rerun_department_cycle(db, "finance_governor", actor=ACTOR, request_id="t-1")
    recovery.rerun_department_cycle(db, "finance_governor", actor=ACTOR, request_id="t-2")
    trail = recovery.recent(db)
    assert [t["request"] for t in trail] == ["recovery:t-2", "recovery:t-1"]
    assert trail[0]["action"] == "recovery.refused" and trail[1]["actor"] == ACTOR


def test_actions_work_inside_a_callers_session():
    db = _db()
    jid = _job(db, status=JobStatus.RUNNING, lease=NOW - timedelta(minutes=10), holder="d")
    with db.session() as s:
        out = recovery.restart_stuck_job(s, jid, actor=ACTOR, request_id="s-1", now=NOW)
    assert out["done"]
    assert JobQueue(db).get(jid).status == JobStatus.PENDING


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
