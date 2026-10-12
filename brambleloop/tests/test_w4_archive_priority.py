"""W4-ARCHIVEPRIO (#51): the continuity proof and the daily offsite archive are not starved.

Production 2026-10-12: ops.offsite_archive job 12678 (enqueued ~00:01Z) had not run by 08:20Z
on a one-worker pool behind ~66 older exploration/opportunity jobs (creative.tournament etc.).
Bounded aging saturates at AGING_CAP, so an older low-band backlog keeps out-ranking a fresh
housekeeping job. Both job types now sit in the protected truth_defect band (the system's own
claim that its state survives losing the database or the provider), which the claim orders
ahead of every ordinary tier whatever the stored priority or age.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, JobStatus, utcnow  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.swarm import orchestrate as O  # noqa: E402

BACKLOG = ("creative.tournament", "creative.white_space", "plan.strategy", "portfolio.review",
           "seasonal.harvest", "creative.outcome_learning")


def _queue_with_backlog(n=66, hours_old=30):
    db = Database("sqlite://")
    db.create_all()
    old = utcnow() - timedelta(hours=hours_old)
    with db.session() as s:
        for i in range(n):
            jt = BACKLOG[i % len(BACKLOG)]
            s.add(Job(agent="creative_director", job_type=jt, inputs={},
                      priority=O.band_for(jt)["band"], status=JobStatus.PENDING,
                      created_at=old, run_after=old))
    return db, JobQueue(db)


def test_continuity_and_archive_are_in_the_protected_truth_band():
    for jt in ("ops.offsite_archive", "ops.continuity"):
        b = O.band_for(jt)
        assert b["mapped"] and b["kind"] == "truth_defect", b
        assert O.claim_tier(jt) < O.ORDINARY_TIER
    assert "ops.offsite_archive" in O.protected_job_types()["truth_defect"]


def test_a_fresh_archive_runs_first_behind_an_older_low_value_backlog():
    db, q = _queue_with_backlog()
    # enqueued the way the scheduler does: no explicit priority, the band decides
    arch = q.enqueue("orchestrator", "ops.offsite_archive", {"cadence": "offsite_archive"},
                     idempotency_key="cadence:offsite_archive:test")
    cont = q.enqueue("orchestrator", "ops.continuity", {"cadence": "continuity_proof"},
                     idempotency_key="cadence:continuity_proof:test")
    first = q.claim("web-1")
    second = q.claim("web-1")
    assert {first.job_type, second.job_type} == {"ops.offsite_archive", "ops.continuity"}, \
        (first.job_type, second.job_type)
    assert {first.id, second.id} == {arch.id, cont.id}
    third = q.claim("web-1")
    assert third.job_type in BACKLOG


def test_an_archive_left_at_the_old_stored_priority_still_runs_first():
    # A job already queued in production before this change carries priority 95; the claim
    # tier comes from the job type, so it is claimed first after the deploy too.
    db, q = _queue_with_backlog()
    with db.session() as s:
        s.add(Job(agent="orchestrator", job_type="ops.offsite_archive", inputs={},
                  priority=95, status=JobStatus.PENDING, run_after=utcnow()))
    assert q.claim("web-1").job_type == "ops.offsite_archive"


def test_customer_work_still_comes_before_the_archive():
    db, q = _queue_with_backlog(n=6)
    q.enqueue("orchestrator", "ops.offsite_archive", {}, idempotency_key="a")
    q.enqueue("support", "support.reply", {}, idempotency_key="b")
    assert q.claim("web-1").job_type == "support.reply"
    assert q.claim("web-1").job_type == "ops.offsite_archive"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
