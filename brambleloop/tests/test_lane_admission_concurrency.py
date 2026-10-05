"""Codex CB2-P09: lane limits under concurrent multi-worker admission.

The lane check counts the *other* RUNNING jobs of a lane, and a just-claimed job is RUNNING
before it is decided. Two workers that claimed same-lane jobs at once could each read the
other as running and both give their job back -- the whole lane held while nothing of it ran.
`lane_hold` now decides under one admission lock, so concurrent deciders are serialized.

Every job, allocation and worker here is a TEST FIXTURE on a throwaway file-backed SQLite
database. Nothing spends, publishes or sends.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_lane_admission_concurrency.py
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Agent, AuditLog, Job, JobStatus, SwarmAllocation  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

# Two lanes in one function, so the function-share rule cannot be what holds a job here.
LANES = {"market_radar": 1, "creative_director": 2}
JOB_TYPE = "cert.lane_work"


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='lanes_cc_')}/lanes.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        for name in LANES:
            a = s.scalar(select(Agent).where(Agent.name == name))
            assert a is not None, f"fixture agent {name} is not in the seeded registry"
            a.allowed_job_types = list(a.allowed_job_types or []) + [JOB_TYPE]
        s.add(SwarmAllocation(open_work=10, granted=sum(LANES.values()),
                              lanes={k: {"granted": v, "open_work": 5}
                                     for k, v in LANES.items()}))
    return db


def _status(db, job_id):
    with db.session() as s:
        return s.get(Job, job_id).status


def test_two_deciders_reading_at_once_never_both_hold_the_lane():
    """The interleaving that produced mutual deferral, forced: both deciders pause right after
    reading the lane. Before the admission lock both read the other as running and both held.
    Now the second decider cannot read until the first has decided."""
    db = _db()
    q = JobQueue(db)
    a = q.enqueue("market_radar", JOB_TYPE, {"i": 1}, priority=50)
    b = q.enqueue("market_radar", JOB_TYPE, {"i": 2}, priority=50)
    ja, jb = q.claim("wa"), q.claim("wb")
    assert {ja.id, jb.id} == {a.id, b.id}
    original = orc._running_in_lane
    barrier = threading.Barrier(2, timeout=1.5)

    def paused(*args, **kw):
        out = original(*args, **kw)
        try:
            barrier.wait()          # both decide "at once" if nothing serializes them
        except threading.BrokenBarrierError:
            pass
        return out

    held: dict[int, bool] = {}
    errors: list = []

    def decide(job, worker):
        try:
            held[job.id] = orc.lane_hold(db, job, worker=worker)
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    orc._running_in_lane = paused
    try:
        threads = [threading.Thread(target=decide, args=(ja, "wa")),
                   threading.Thread(target=decide, args=(jb, "wb"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
    finally:
        orc._running_in_lane = original
    assert not errors, errors
    assert sorted(held.values()) == [False, True], (
        f"lane of 1 with two runnable jobs: exactly one must run and one wait, got {held}")
    statuses = sorted(str(_status(db, j)) for j in (a.id, b.id))
    assert statuses == sorted([str(JobStatus.RUNNING), str(JobStatus.PENDING)]), statuses


def test_three_or_more_workers_hold_every_lane_limit_and_finish_all_runnable_work():
    db = _db()
    reg = HandlerRegistry()
    lock = threading.Lock()
    in_flight: Counter = Counter()
    peak: Counter = Counter()
    executions: Counter = Counter()

    @reg.register(JOB_TYPE)
    def _work(ctx):
        lane = ctx.job.agent
        with lock:
            in_flight[lane] += 1
            peak[lane] = max(peak[lane], in_flight[lane])
            executions[ctx.job.id] += 1
        time.sleep(0.03)
        with lock:
            in_flight[lane] -= 1
        return {}

    q = JobQueue(db)
    ids = [q.enqueue(lane, JOB_TYPE, {"i": i}, priority=50).id
           for i in range(8) for lane in LANES]
    saved_hold = orc.LANE_HOLD_SECONDS
    orc.LANE_HOLD_SECONDS = 0          # a held job is claimable again at once
    n_workers = 4
    barrier = threading.Barrier(n_workers)
    errors: list = []
    deadline = time.monotonic() + 120

    def run(k):
        w = Worker(db, f"pool-{k}", registry=reg)
        barrier.wait()
        idle = 0
        while time.monotonic() < deadline:
            try:
                if w.run_once():
                    idle = 0
                    continue
            except Exception as e:  # noqa: BLE001
                errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                return
            idle += 1
            if idle > 20:
                return
            time.sleep(0.01)

    try:
        threads = [threading.Thread(target=run, args=(k,)) for k in range(n_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(150)
    finally:
        orc.LANE_HOLD_SECONDS = saved_hold
    assert not errors, errors[:5]
    for lane, limit in LANES.items():
        assert peak[lane] <= limit, f"{lane} ran {peak[lane]} at once against a lane of {limit}"
    assert peak["creative_director"] >= 1 and peak["market_radar"] >= 1
    with db.session() as s:
        states = Counter(str(s.get(Job, i).status) for i in ids)
        held = len(list(s.scalars(select(AuditLog).where(
            AuditLog.action == orc.LANE_HELD_ACTION))))
    assert states == Counter({str(JobStatus.DONE): len(ids)}), (states, held)
    assert all(executions[i] == 1 for i in ids), "a lane-held job ran twice"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
