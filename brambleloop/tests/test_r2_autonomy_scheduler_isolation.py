"""R2 autonomy, audit ddf9c6e M-2: one poisoned cadence cannot starve the others or drive
the stale-scheduler self-exit.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_autonomy_scheduler_isolation.py
"""
from __future__ import annotations

import threading
from datetime import timedelta

from r2_autonomy_harness import boot, run_tests

from sqlalchemy import select


def _poison(job_types):
    from brambleloop.queue import durable

    orig = durable.JobQueue.enqueue

    def enq(self, agent, job_type, *a, **k):
        if job_type in job_types:
            raise ValueError("handler-specific validation error (schema drift)")
        return orig(self, agent, job_type, *a, **k)

    durable.JobQueue.enqueue = enq
    return lambda: setattr(durable.JobQueue, "enqueue", orig)


def test_a_poisoned_cadence_is_isolated_recorded_and_the_rest_enqueue():
    from brambleloop.core.models import AuditLog, Incident, Job
    from brambleloop.runtime import worker as W

    db = boot()
    poison_name, _a, poison_jt, _p = W.CADENCES[5]
    restore = _poison({poison_jt})
    try:
        sched = W.Scheduler(db)
        enqueued = sched.tick()                     # must not raise
        sched.tick()                                # and again next tick
    finally:
        restore()
    expected = {n for n, _a, jt, _p in W.CADENCES if jt != poison_jt}
    assert expected, "no cadences"
    assert expected <= set(enqueued), sorted(expected - set(enqueued))[:10]
    assert poison_name in sched.failures, sched.failures
    with db.session() as s:
        n = len(list(s.scalars(select(Job))))
        inc = list(s.scalars(select(Incident).where(
            Incident.signature == f"scheduler.cadence_failed:{poison_name}")))
        audits = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "scheduler.cadence_failed")))
    assert n >= len(expected), (n, len(expected))
    assert len(inc) == 1 and inc[0].report_count >= 2, inc   # deduplicated, counted
    assert len(audits) >= 2, audits


def test_the_runner_keeps_ticking_so_the_supervisor_never_exits():
    from brambleloop.app import runner
    from brambleloop.runtime import worker as W

    db = boot()
    poison_jt = W.CADENCES[5][2]
    restore = _poison({poison_jt})
    exits: list[int] = []
    old_exit, old_interval = runner._exit, runner._SCHEDULER_INTERVAL
    runner._exit = lambda c: exits.append(c)
    stop = threading.Event()
    try:
        runner.STATE.enabled = True
        runner._SCHEDULER_INTERVAL = 0.2
        old_delay = runner._START_DELAY
        runner._START_DELAY = 0
        t = threading.Thread(target=runner._scheduler_loop, args=(db, stop), daemon=True)
        t.start()
        for _ in range(100):
            if runner.STATE.scheduler_last_tick is not None and \
                    runner.STATE.scheduler_last_tick >= runner.STATE.scheduler_started_at:
                break
            stop.wait(0.1)
        stop.set()
        t.join(timeout=30)
        last = runner.STATE.scheduler_last_tick
        assert last is not None and last >= runner.STATE.scheduler_started_at, last
        strikes = 0
        for minute in range(0, 40):
            # the scheduler keeps ticking every minute despite the poisoned cadence
            runner.STATE.scheduler_last_tick = last + timedelta(minutes=minute)
            strikes = runner.supervise_once(strikes, now=last + timedelta(minutes=minute,
                                                                          seconds=30))
        assert not exits, exits
    finally:
        restore()
        runner._exit, runner._SCHEDULER_INTERVAL = old_exit, old_interval
        runner._START_DELAY = old_delay
        runner.STATE.enabled = False


def test_every_cadence_failing_is_still_a_scheduler_failure():
    from brambleloop.runtime import worker as W

    db = boot()
    restore = _poison({jt for _n, _a, jt, _p in W.CADENCES})
    try:
        try:
            W.Scheduler(db).tick()
            raised = False
        except RuntimeError:
            raised = True
    finally:
        restore()
    assert raised, "a scheduler that enqueued nothing at all must not report a healthy tick"


if __name__ == "__main__":
    run_tests(globals())
