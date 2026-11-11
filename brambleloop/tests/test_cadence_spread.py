"""P1 6783107211 follow-up (review 6785727146): the midnight herd is spread, never doubled.

Every cadence keyed its window as floor(epoch / period), so all ~50 daily cadence windows
opened at 00:00:00Z at once and the single embedded worker drained them back to back (one
~7-min handler held worker 0 every night). A cadence whose period is at least a day now opens
its window at a stable per-cadence offset (a hash of its name) inside the period, keyed
`cadence:<name>:s<window>`; sub-daily cadences keep their keys.

The one way this could run a cadence twice is the deploy that introduces it: the day's
pre-spread run (`cadence:<name>:<window>`) has already happened, and the first spread window
opens later the same day. That transition is guarded: a cadence whose latest legacy-keyed run
is younger than its period skips its first spread window. Steady state needs no guard -- the
spread key itself is the idempotency key.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_cadence_spread.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = tempfile.mkdtemp(prefix="cadence_spread_art_")

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import worker as W  # noqa: E402

DAY = 24 * 60 * 60
DAILY = [c for c in W.CADENCES if c[3] == DAY]


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cadence_spread_')}/c.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _no_wake():
    from brambleloop.autonomy import orchestrator
    saved = orchestrator.idle_wake
    orchestrator.idle_wake = lambda *a, **k: False
    return lambda: setattr(orchestrator, "idle_wake", saved)


def _only(cadences):
    saved = W.CADENCES
    W.CADENCES = list(cadences)
    W._LEGACY_RAN.clear()
    return lambda: setattr(W, "CADENCES", saved)


def _jobs(db, name):
    with db.session() as s:
        return [(j.idempotency_key, j.created_at) for j in s.query(Job).filter(
            Job.idempotency_key.like(f"cadence:{name}:%")).order_by(Job.id)]


def test_daily_windows_no_longer_open_together():
    assert len(DAILY) >= 30, len(DAILY)
    offsets = [W.cadence_offset(n, p) for n, _a, _j, p in DAILY]
    assert all(0 <= o < DAY for o in offsets)
    # the herd: before, every daily window opened in the same second; now at most a few
    # share any 15-minute slice of the day
    per_slot = Counter(o // (15 * 60) for o in offsets)
    assert max(per_slot.values()) <= 4, per_slot.most_common(3)
    assert len(per_slot) >= len(DAILY) // 2, len(per_slot)
    # stable: a pure function of the name (same in every process and every deploy)
    assert offsets == [W.cadence_offset(n, p) for n, _a, _j, p in DAILY]


def test_sub_daily_keys_are_unchanged():
    now = datetime(2026, 11, 11, 4, 30, tzinfo=timezone.utc)
    for name, _a, _j, period in W.CADENCES:
        if period < DAY:
            assert W.cadence_offset(name, period) == 0
            assert W.cadence_key(name, period, now) == \
                f"cadence:{name}:{int(now.timestamp() // period)}", name
    name, _a, _j, period = DAILY[0]
    assert W.cadence_key(name, period, now).startswith(f"cadence:{name}:s")


def test_each_daily_cadence_runs_once_per_window_over_three_days():
    db, restore, unwake = _db(), _only(DAILY[:8]), _no_wake()
    try:
        start = datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc)
        sched = W.Scheduler(db)
        for h in range(0, 72 * 6):                       # every 10 minutes for 3 days
            sched.tick(now=start + timedelta(minutes=10 * h))
        for name, _a, _j, period in DAILY[:8]:
            keys = [k for k, _t in _jobs(db, name)]
            assert len(keys) == len(set(keys)), keys
            assert 3 <= len(keys) <= 4, (name, keys)     # 3 days: 3 windows (+1 partial)
            assert all(k.startswith(f"cadence:{name}:s") for k in keys), keys
    finally:
        restore()
        unwake()


def test_the_deploy_transition_never_runs_a_daily_cadence_twice():
    """The pre-spread run happened at 00:00Z; the deploy lands at 15:21Z. Whatever the
    cadence's offset, it runs once in that period and next at its first full spread window."""
    db, restore, unwake = _db(), _only(DAILY[:8]), _no_wake()
    try:
        midnight = datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc)
        q = JobQueue(db)
        for name, agent, job_type, period in DAILY[:8]:
            legacy = f"cadence:{name}:{int(midnight.timestamp() // period)}"
            q.enqueue(agent, job_type, {"cadence": name}, idempotency_key=legacy)
        with db.session() as s:
            for j in s.query(Job):
                j.created_at = midnight
        deploy = midnight + timedelta(hours=15, minutes=21)
        sched = W.Scheduler(db)
        for m in range(0, 36 * 6):                       # 36 h of ticks after the deploy
            now = deploy + timedelta(minutes=10 * m)
            sched.tick(now=now)
        for name, _a, _j, period in DAILY[:8]:
            rows = _jobs(db, name)
            spread = [(k, t) for k, t in rows if k.startswith(f"cadence:{name}:s")]
            assert len(rows) - len(spread) == 1, rows        # the one legacy run
            assert spread, (name, rows)                       # and it does run again
            # when each run's window opened (created_at is the wall clock, not the simulated
            # tick): the legacy run at midnight, each spread run at its own window's start
            offset = W.cadence_offset(name, period)
            opened = [midnight.timestamp()] + sorted(
                int(k.rsplit(":s", 1)[1]) * period + offset for k, _t in spread)
            # the first spread run opens no earlier than one period after the legacy run's
            # window began... never a second run within the same day's period
            gaps = [b - a for a, b in zip(opened, opened[1:])]
            assert all(g >= period * 0.5 for g in gaps), (name, gaps)
            first_spread = opened[1]
            assert first_spread >= deploy.timestamp() - 1e-6 or \
                first_spread - midnight.timestamp() >= period * 0.5, (name, gaps)
    finally:
        restore()
        unwake()


def test_without_a_legacy_run_the_first_tick_still_enqueues_at_once():
    """A fresh database (or a cadence that never ran) is not held back by the guard."""
    db, restore, unwake = _db(), _only(DAILY[:3]), _no_wake()
    try:
        now = datetime(2026, 11, 11, 15, 21, tzinfo=timezone.utc)
        got = W.Scheduler(db).tick(now=now)
        assert {n for n, *_ in DAILY[:3]} <= set(got), got
    finally:
        restore()
        unwake()


def test_an_old_legacy_run_does_not_hold_the_first_window_back():
    db, restore, unwake = _db(), _only(DAILY[:1]), _no_wake()
    try:
        name, agent, job_type, period = DAILY[0]
        long_ago = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
        JobQueue(db).enqueue(agent, job_type, {"cadence": name},
                             idempotency_key=f"cadence:{name}:{int(long_ago.timestamp() // period)}")
        with db.session() as s:
            s.query(Job).one().created_at = long_ago
        now = datetime(2026, 11, 11, 15, 21, tzinfo=timezone.utc)
        sched = W.Scheduler(db)
        assert name in sched.tick(now=now) and not sched.transition_skipped
    finally:
        restore()
        unwake()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
