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


WEEKLY = [c for c in W.CADENCES if c[3] == 7 * DAY]


def _transition(cadences, period, deploy_after, step, horizon_periods=3):
    """Legacy-keyed run L of each cadence at its legacy window start; the deploy lands
    `deploy_after` seconds later; the real Scheduler ticks every `step` s from then. Returns
    {name: [run times]} with each spread run timed at max(window open, deploy)."""
    db, restore, unwake = _db(), _only(cadences), _no_wake()
    try:
        base = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)
        L = datetime.fromtimestamp(int(base.timestamp() // period) * period, timezone.utc)
        q = JobQueue(db)
        for name, agent, job_type, p in cadences:
            q.enqueue(agent, job_type, {"cadence": name},
                      idempotency_key=f"cadence:{name}:{int(L.timestamp() // p)}")
        with db.session() as s:
            for j in s.query(Job):
                j.created_at = L
        deploy = L + timedelta(seconds=deploy_after)
        sched = W.Scheduler(db)
        t = deploy
        while t < deploy + timedelta(seconds=horizon_periods * period):
            sched.tick(now=t)
            t += timedelta(seconds=step)
        runs = {}
        for name, _a, _j, p in cadences:
            rows = _jobs(db, name)
            def spread(k):
                return k.rsplit(":", 1)[1].startswith(W.SPREAD_KEY_MARK)
            assert len([k for k, _t in rows if not spread(k)]) == 1, rows   # one legacy run
            off = W.cadence_offset(name, p)
            opened = sorted(max(int(k.rsplit(":", 1)[1][1:]) * p + off, deploy.timestamp())
                            for k, _t in rows if spread(k))
            runs[name] = (L.timestamp(), opened)
        return runs
    finally:
        restore()
        unwake()


def _assert_bounded(runs, period, step):
    """Review 6801029119 MEDIUM-1: never closer than the transition gap to the legacy run,
    and the first spread run less than period + that gap after it (+ one tick of slack)."""
    gap_min = W.transition_min_gap(period)
    for name, (legacy, opened) in runs.items():
        assert opened, (name, "never ran after the deploy")
        first = opened[0] - legacy
        assert first >= gap_min - step, (name, first / 3600)
        assert first < period + gap_min + step, (name, first / 3600)
        later = [b - a for a, b in zip(opened, opened[1:])]
        # the run at the deploy (mid-window) to the next window opening is <= one period --
        # any boot mid-window behaves so; every window after that is exactly one period
        assert not later or 0 < later[0] <= period + step, (name, later)
        assert all(abs(g - period) <= step for g in later[1:]), (name, later)


def test_the_deploy_transition_is_bounded_both_ways_for_daily_cadences():
    """Whatever each cadence's offset (before or after the deploy time), the first spread
    run is >= 12 h and < 36 h after the day's legacy run; then exactly one per day."""
    step = 10 * 60
    for deploy_after in (5 * 60, 6 * 3600, 12 * 3600, DAY - 5 * 60):
        _assert_bounded(_transition(DAILY[:12], DAY, deploy_after, step), DAY, step)


def test_the_deploy_transition_is_bounded_for_weekly_cadences_inside_the_weekly_grace():
    """Weekly: >= 12 h and < 7.5 days after the legacy run -- inside WEEKLY_GRACE (8 d)."""
    assert WEEKLY, "no weekly cadence to check"
    step = 60 * 60
    for deploy_after in (5 * 60, 3 * DAY + 12 * 3600, 7 * DAY - 3600):
        runs = _transition(WEEKLY[:6], 7 * DAY, deploy_after, step, horizon_periods=2)
        _assert_bounded(runs, 7 * DAY, step)
        assert runs, runs
        for name, (legacy, opened) in runs.items():
            assert opened[0] - legacy < 8 * DAY, (name, (opened[0] - legacy) / DAY)


def test_next_wake_surfaces_read_the_spread_offset():
    """LOW-2: the "next" times shown read cadence_next_at, not floor(now/period)+1."""
    from brambleloop.ops import flow_health

    now = datetime(2026, 11, 11, 15, 21, tzinfo=timezone.utc)
    nxt = W.cadence_next_at
    for name, _a, _j, period in DAILY[:5]:
        at = nxt(name, period, now)
        assert now.timestamp() < at <= now.timestamp() + period, name
        assert (at - W.cadence_offset(name, period)) % period == 0, name
    shown = {c["cadence"]: c["next_at"] for c in flow_health.next_cadences(_db(), now=now)}
    for name, _a, _j, period in DAILY[:5]:
        assert shown[name] == datetime.fromtimestamp(nxt(name, period, now),
                                                     timezone.utc).isoformat(), name
    src = ROOT / "src" / "brambleloop"
    for rel in ("autonomy/status.py", "app/command_center/company.py", "ops/flow_health.py"):
        text = (src / rel).read_text()
        assert "cadence_next_at" in text and "// period) + 1) * period" not in text, rel


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
