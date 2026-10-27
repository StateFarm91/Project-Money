"""F-134 Never-Idle Proof: ready work left unclaimed with no completion for
IDLE_STALL_MULTIPLIER x IDLE_ALARM_HOURS raises a second, lower-severity alarm (P3
`build.idle`); before that it stays `awaiting_build_session` with no alarm, a claim or
completion resets the clock, and the incident closes when the condition stops."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.build2 import executor as E  # noqa: E402
from test_executor import _synced_with_ready_work  # noqa: E402


def _age_events(db, hours):
    from sqlalchemy import select

    from brambleloop.core.models import BuildEvent

    with db.session() as s:
        for ev in s.scalars(select(BuildEvent)):
            ev.at = ev.at - timedelta(hours=hours) if ev.at else ev.at


def test_the_second_alarm_fires_after_n_windows_and_not_before():
    assert E.IDLE_STALL_MULTIPLIER >= 2 and E.IDLE_STALL_SEVERITY == "P3"
    db = _synced_with_ready_work()
    now = datetime.now(timezone.utc)
    stall = E.IDLE_ALARM_HOURS * E.IDLE_STALL_MULTIPLIER
    fresh = E.watchdog(db, now=now)
    assert fresh["verdict"] == E.AWAITING_BUILD_SESSION and fresh["alarm"] is False
    assert fresh["idle_alarm"] is False and fresh["idle_stall_hours"] == stall
    # One window idle: still the calendar, no alarm of either kind.
    one = E.watchdog(db, now=now + timedelta(hours=E.IDLE_ALARM_HOURS + 1))
    assert one["verdict"] == E.AWAITING_BUILD_SESSION and one["idle_alarm"] is False
    # N windows idle: the lower-severity alarm, the P2 stall alarm untouched.
    late = now + timedelta(hours=stall + 1)
    idle = E.watchdog(db, now=late)
    assert idle["verdict"] == E.AWAITING_BUILD_SESSION and idle["alarm"] is False
    assert idle["idle_alarm"] is True and idle["idle_severity"] == "P3", idle
    assert idle["idle_hours"] >= stall and "standing still" in idle["idle_note"]
    # A claim (and an honest release) is a sign of life: the clock restarts.
    target = E.next_ready(db)["requirement_id"]
    E.claim(db, target, worker="s1")
    E.release(db, target, worker="s1", why="test")
    assert E.watchdog(db)["idle_alarm"] is False


def test_build_tick_opens_and_closes_the_p3_incident():
    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Incident
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import Worker

    db = _synced_with_ready_work()
    Registry(db).seed_defaults()
    worker = Worker(db, "d2-worker")

    def tick(key):
        JobQueue(db).enqueue("orchestrator", "build.tick", {}, idempotency_key=key)
        for _ in range(20):
            if not worker.run_once():
                break

    def incidents(sig):
        with db.session() as s:
            return [(i.severity, i.resolved) for i in s.scalars(
                select(Incident).where(Incident.signature == sig))]

    tick("t1")
    assert incidents("build.idle") == []
    _age_events(db, E.IDLE_ALARM_HOURS * E.IDLE_STALL_MULTIPLIER + 2)
    tick("t2")
    assert incidents("build.idle") == [("P3", False)], incidents("build.idle")
    assert incidents("build.stalled") == []
    tick("t3")
    assert incidents("build.idle") == [("P3", False)]          # restated, not duplicated
    target = E.next_ready(db)["requirement_id"]
    E.claim(db, target, worker="s1")
    E.release(db, target, worker="s1", why="test")
    tick("t4")
    assert incidents("build.idle") == [("P3", True)], incidents("build.idle")


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
