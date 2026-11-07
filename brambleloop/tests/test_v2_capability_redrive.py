"""V2 / P2-a: an image run blocked only on a closed capability gate restarts once when it opens.

The run rows are fixtures in the real `image_production_runs` table, and the restart is the
real `image_production.restart` (epoch, history, the job through `follow`). The only stub is
the gate's open/closed reading: opening the real `image_generation` gate is an owner
activation (V0), and no paid call is possible here because nothing generates. The real
`chain.successors` handler is run once through the Worker to prove the sweep calls it.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_v2_capability_redrive.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job  # noqa: E402
from brambleloop.visual import gallery  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual.image_records import ImageProductionRun, ensure_tables  # noqa: E402

GATE_REASON = "image_generation gate closed: a paid generator may not be called"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='v2r_')}/v2r.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    ensure_tables(db)
    return db


def _blocked(db, slug, reason, stage="product_generation"):
    key = IP.run_key(slug, "1.0.0", f"{slug}-release")
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.0.0",
                                 release=f"{slug}-release", listing=slug, stage=stage,
                                 status="blocked", blocked_reason=reason, stages={}))
    return key


class _Gate:
    def __init__(self):
        self.open = False

    def __call__(self, db, keys=("image_generation",)):
        return {k: self.open for k in keys}


def _with_gate(gate):
    real = gallery.gates_now
    gallery.gates_now = gate
    return real


def _follow(calls):
    def follow(inputs, key, *, session=None):
        calls.append((inputs, key))
        return object()
    return follow


def test_a_gate_blocked_run_waits_while_closed_and_restarts_once_when_open():
    db = _db()
    key = _blocked(db, "basket-a", GATE_REASON)
    gate, calls = _Gate(), []
    real = _with_gate(gate)
    try:
        out = IP.redrive_capability_blocked(db, follow=_follow(calls))
        assert out["waiting"] and not out["restarted"] and calls == [], out
        gate.open = True
        out = IP.redrive_capability_blocked(db, follow=_follow(calls))
        assert [r["run_key"] for r in out["restarted"]] == [key], out
        assert len(calls) == 1 and calls[0][0]["stage"] == "product_generation"
        assert calls[0][1].endswith(":e1"), calls[0][1]
        run = IP.get_run(db, key)
        assert run["state"] != "blocked" and run["restarts"] == 1, run
        # Blocked again on the same gate: the automatic restart is spent for it.
        with db.session() as s:
            r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
            r.status, r.blocked_reason = "blocked", GATE_REASON
        out = IP.redrive_capability_blocked(db, follow=_follow(calls))
        assert not out["restarted"] and "already re-driven" in out["refused"][0]["why"], out
        assert len(calls) == 1
    finally:
        gallery.gates_now = real


def test_a_failed_run_or_another_block_is_never_re_driven():
    db = _db()
    failed = _blocked(db, "basket-f", GATE_REASON)
    budget = _blocked(db, "basket-b", "budget stop: the gallery spend plan is spent")
    owner = _blocked(db, "basket-o", "owner card: awaiting the visual approval")
    gate, calls = _Gate(), []
    gate.open = True
    real = _with_gate(gate)
    real_failed = IP._run_candidates_failed
    IP._run_candidates_failed = lambda db, key, listing: (["product_flat_lay"]
                                                           if key == failed else [])
    try:
        out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    finally:
        gallery.gates_now = real
        IP._run_candidates_failed = real_failed
    assert calls == [] and out["restarted"] == [], out
    assert [r["run_key"] for r in out["refused"]] == [failed]
    assert "FAIL" in out["refused"][0]["why"], out["refused"]
    # Budget and owner blocks are not capability blocks: not even considered.
    assert budget not in str(out) and owner not in str(out)


def test_the_hourly_chain_successors_sweep_runs_it():
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime import release  # noqa: F401
    from brambleloop.runtime.worker import Worker

    db = _db()
    key = _blocked(db, "basket-s", GATE_REASON)
    gate = _Gate()
    gate.open = True
    real = _with_gate(gate)
    try:
        job = JobQueue(db).enqueue("listing", "chain.successors", {}, priority=0)
        assert Worker(db, "w", job_types=["chain.successors"]).run_once()
    finally:
        gallery.gates_now = real
    with db.session() as s:
        row = s.get(Job, job.id)
        out = dict(row.outputs or {})
        queued = list(s.scalars(select(Job).where(Job.job_type == IP.JOB_TYPE)))
    assert [r["run_key"] for r in out["images"]["restarted"]] == [key], (row.status,
                                                                           row.last_error, out)
    assert len(queued) == 1 and queued[0].inputs["epoch"] == 1, queued


def test_an_experiment_run_blocked_on_the_gate_is_never_re_driven():
    """Review V2 F10 (mutant R4): a controlled experiment run ('#' in its key) is one-shot,
    even when its blocked reason names the capability gate."""
    db = _db()
    key = IP.run_key("basket-x", "1.0.0", "basket-x-release") + "#exp1"
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug="basket-x", version="1.0.0",
                                 release="basket-x-release", listing="basket-x",
                                 stage="product_generation", status="blocked",
                                 blocked_reason=GATE_REASON, stages={}))
    gate, calls = _Gate(), []
    gate.open = True
    real = _with_gate(gate)
    try:
        out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    finally:
        gallery.gates_now = real
    assert calls == [] and out["restarted"] == [], out
    assert [r["run_key"] for r in out["refused"]] == [key], out
    assert "one-shot" in out["refused"][0]["why"], out


def _sweep_once(db):
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime import release  # noqa: F401
    from brambleloop.runtime.worker import Worker

    job = JobQueue(db).enqueue("listing", "chain.successors", {}, priority=0)
    assert Worker(db, "w", job_types=["chain.successors"]).run_once()
    with db.session() as s:
        return dict(s.get(Job, job.id).outputs or {})


def test_a_duplicate_restart_job_rolls_the_restart_back_on_a_real_queue():
    """Review VISUAL_STACK N3 (mutants R_exc_as_restarted, R_dup_swallow): the restart's job
    key already exists. The real sweep's follow re-raises the duplicate under V1's restart
    transaction, so the un-block rolls back: refused, still blocked, no restart history, and
    the only job is the one that was already there."""
    from brambleloop.queue.durable import JobQueue

    db = _db()
    key = _blocked(db, "basket-d", GATE_REASON)
    dup = IP.stage_key("basket-d", "1.0.0", "basket-d-release", "product_generation", 0, 1)
    JobQueue(db).enqueue(IP.AGENT, IP.JOB_TYPE, {"stage": "product_generation"},
                         idempotency_key=dup)
    gate = _Gate()
    gate.open = True
    real = _with_gate(gate)
    try:
        out = _sweep_once(db)["images"]
    finally:
        gallery.gates_now = real
    assert out["restarted"] == [], out
    assert [r["run_key"] for r in out["refused"]] == [key], out
    assert "DuplicateJob" in out["refused"][0]["why"], out
    run = IP.get_run(db, key)
    assert run["state"] == "blocked" and run["blocked_reason"] == GATE_REASON, run
    with db.session() as s:
        row = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        history = ((row.stages or {}).get(IP.RESTART_KEY) or {}).get("history")
    assert run["restarts"] == 0 and not history, (run, history)
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type == IP.JOB_TYPE)))
    assert [j.idempotency_key for j in jobs] == [dup], jobs


def test_the_restart_job_is_enqueued_inside_the_restart_transaction():
    """Review VISUAL_STACK N3 (mutant R_follow_nosession): the sweep's follow hands V1's
    session to the queue, so the job and the un-block commit or roll back together."""
    from brambleloop.queue.durable import JobQueue

    db = _db()
    _blocked(db, "basket-t", GATE_REASON)
    seen = []
    real_enqueue = JobQueue.enqueue

    def spy(self, agent, job_type, inputs=None, **kw):
        if job_type == IP.JOB_TYPE:
            seen.append(kw.get("session"))
        return real_enqueue(self, agent, job_type, inputs, **kw)

    gate = _Gate()
    gate.open = True
    real = _with_gate(gate)
    JobQueue.enqueue = spy
    try:
        out = _sweep_once(db)["images"]
    finally:
        JobQueue.enqueue = real_enqueue
        gallery.gates_now = real
    assert len(out["restarted"]) == 1, out
    assert seen and all(s is not None for s in seen), seen


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
