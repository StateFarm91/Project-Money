"""Continuous operations: fenced recovery and dedicated lanes (ported from Codex 8877f05).

Codex's original file was pytest-based and also covered `growth/ads_readiness.py` and gateway
budget-admission changes; those belong to other lanes (H, and the gateway owner) and are not
ported here. What is ported is the recovery and lane half, rewritten against this runtime's
queue API (a fenced write returns False/None instead of raising `LeaseLost`) and its control
lane (`runtime.lanes`), and run as a plain script like the rest of the suite.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import update  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Agent, Job, JobStatus, utcnow  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.lanes import CONTROL, partitions  # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker, handlers  # noqa: E402


def boot() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='contops-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_stale_attempt_cannot_mutate_successor():
    for operation in ("complete", "fail", "heartbeat"):
        db = boot()
        q = JobQueue(db)
        job = q.enqueue("validator", "cir.compile")
        first = q.claim("same-worker-name")
        with db.session() as s:
            s.execute(update(Job).where(Job.id == job.id).values(
                lease_expires_at=utcnow() - timedelta(seconds=1)))
        second = q.claim("same-worker-name")
        assert first.lease_token != second.lease_token
        if operation == "complete":
            res = q.complete(job.id, {"stale": 1}, worker="same-worker-name",
                             lease_token=first.lease_token)
            assert res is False, operation
        elif operation == "fail":
            res = q.fail(job.id, "old failure", worker="same-worker-name",
                         lease_token=first.lease_token)
            assert res is None, operation
        else:
            res = q.heartbeat(job.id, worker="same-worker-name",
                              lease_token=first.lease_token)
            assert res is False, operation
        assert q.get(job.id).lease_token == second.lease_token, operation
        assert q.complete(job.id, {"winner": True}, worker="same-worker-name",
                          lease_token=second.lease_token) is True
        assert q.get(job.id).outputs == {"winner": True}


def test_simultaneous_claims_are_distinct():
    db = boot()
    q = JobQueue(db)
    for _ in range(8):
        q.enqueue("validator", "cir.compile")
    start = threading.Barrier(8)

    def claim(i):
        start.wait()
        for _ in range(50):
            job = q.claim(f"w{i}")
            if job is not None:
                return job.id
        return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(claim, range(8)))
    got = [i for i in ids if i is not None]
    assert got and len(got) == len(set(got)), ids


def test_lane_partitions_cover_every_handler():
    known = handlers.known()
    assert len(known) > 100
    assert partitions(known, "serial") == {"company": None}
    control = partitions(known, "control")
    assert control["company"] is None                       # the pool still takes everything
    assert set(control["control"]) == CONTROL & set(known)
    assert "autonomy.orchestrate" in control["control"]
    depts = partitions(known, "departments")
    flattened = [k for lane, kinds in depts.items() if lane != "company" for k in kinds]
    assert len(flattened) == len(set(flattened)), "a job type in two department lanes"
    assert set(flattened) == set(known), sorted(set(known) - set(flattened))
    try:
        partitions(known, "nonsense")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown lane mode was accepted")


def test_control_lane_progresses_while_production_is_blocked():
    db = boot()
    with db.session() as s:
        a = s.query(Agent).filter(Agent.name == "validator").one()
        a.allowed_job_types = list(a.allowed_job_types) + ["test.slow_render"]
    registry = HandlerRegistry()
    started, release = threading.Event(), threading.Event()

    @registry.register("test.slow_render")
    def slow(ctx):
        started.set()
        assert release.wait(30)
        return {"finished": True}

    @registry.register("autonomy.orchestrate")
    def orchestrate(ctx):
        return {"ran": True, "enqueued": 1}

    q = JobQueue(db)
    q.enqueue("validator", "test.slow_render", {})
    production = Worker(db, "pool-0", registry=registry)
    control = Worker(db, "pool-0-control", registry=registry, job_types=sorted(CONTROL))
    t = threading.Thread(target=production.run_once)
    t.start()
    try:
        assert started.wait(10), "the slow job never started"
        q.enqueue("coo", "autonomy.orchestrate", {})
        assert control.run_once() is True
        assert control.stats.completed == 1, control.stats
        with db.session() as s:
            rows = {j.job_type: j.status for j in s.query(Job).all()}
        assert rows["autonomy.orchestrate"] == JobStatus.DONE
        assert rows["test.slow_render"] == JobStatus.RUNNING
    finally:
        release.set()
        t.join(30)
    assert production.stats.completed == 1, production.stats


def test_runner_starts_the_control_lane():
    import os

    from brambleloop.app import runner

    db = boot()
    old = {k: os.environ.get(k) for k in ("BRAMBLELOOP_WORKER_LANES",)}
    os.environ["BRAMBLELOOP_WORKER_LANES"] = "control"
    saved_delay = runner._START_DELAY
    runner._START_DELAY = 0
    try:
        runner.start(db)
        names = [t.name for t in runner._threads]
        assert any("_lane_loop" in n for n in names), names
        assert "control" in runner.STATE.to_dict()["lanes"]
    finally:
        runner.stop()
        runner._START_DELAY = saved_delay
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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
