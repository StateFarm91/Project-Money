"""R2 autonomy, audit ddf9c6e L-2: a department block binds that department's cadences
(never-pause departments excepted, F-889) and expires unless explicitly renewed.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_autonomy_scheduler_blocks.py
"""
from __future__ import annotations

from datetime import timedelta

from r2_autonomy_harness import boot, run_tests

from sqlalchemy import select


def _types(db, prefix_dept):
    from brambleloop.autonomy.charters import department_of
    from brambleloop.core.models import Job

    with db.session() as s:
        return [j.job_type for j in s.scalars(select(Job))
                if department_of(j.job_type) == prefix_dept]


def test_a_blocked_department_gets_no_cadences_and_others_continue():
    from brambleloop.autonomy import memory
    from brambleloop.autonomy.charters import department_of
    from brambleloop.core.models import utcnow
    from brambleloop.runtime.worker import CADENCES, Scheduler

    db = boot()
    support = [n for n, _a, jt, _p in CADENCES if department_of(jt) == "support"]
    assert support, "support has no cadence to block"
    memory.block_department(db, "support", reason="owner action: refund policy",
                            owner_action="refund_policy")
    sched = Scheduler(db)
    enqueued = sched.tick(now=utcnow())
    assert not _types(db, "support"), _types(db, "support")
    assert set(support) <= set(sched.blocked_skipped), sched.blocked_skipped
    others = [n for n, _a, jt, _p in CADENCES if department_of(jt) not in ("support",)]
    assert others and set(others) <= set(enqueued), sorted(set(others) - set(enqueued))[:5]


def test_never_pause_departments_keep_their_cadences_even_with_a_block_row():
    from brambleloop.autonomy import memory
    from brambleloop.core.models import utcnow
    from brambleloop.runtime.worker import Scheduler

    db = boot()
    memory.block_department(db, "platform", reason="legacy block row")
    Scheduler(db).tick(now=utcnow())
    assert _types(db, "platform"), "platform (never paused) lost its cadences"


def test_blocks_expire_after_the_default_ttl_unless_renewed():
    from brambleloop.autonomy import memory
    from brambleloop.core.models import utcnow

    db = boot()
    t0 = utcnow()
    memory.block_department(db, "growth", reason="x", now=t0)
    assert memory.BLOCK_DEFAULT_TTL == timedelta(hours=24)
    assert memory.active_block(db, "growth", now=t0 + timedelta(hours=23)) is not None
    assert memory.active_block(db, "growth", now=t0 + timedelta(hours=25)) is None
    # explicit renewal
    memory.block_department(db, "visual", reason="y", now=t0)
    assert memory.renew_block(db, "visual", now=t0 + timedelta(hours=20)) is not None
    assert memory.active_block(db, "visual", now=t0 + timedelta(hours=40)) is not None
    assert memory.active_block(db, "visual", now=t0 + timedelta(hours=45)) is None
    # an expired block no longer binds the scheduler
    from brambleloop.runtime.worker import Scheduler

    Scheduler(db).tick(now=t0 + timedelta(hours=30))
    assert _types(db, "growth"), "an expired block still silenced growth"


def test_a_legacy_block_without_until_also_lapses():
    from brambleloop.autonomy import memory
    from brambleloop.core.models import utcnow

    db = boot()
    t0 = utcnow()
    memory.remember(db, "block:support", kind="block", department="support", state="active",
                    body={"reason": "old", "until": None, "since": t0.isoformat()}, now=t0)
    assert memory.active_block(db, "support", now=t0 + timedelta(hours=1)) is not None
    assert memory.active_block(db, "support", now=t0 + timedelta(hours=25)) is None


if __name__ == "__main__":
    run_tests(globals())
