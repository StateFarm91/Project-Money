"""W4-CLOSE5 batch 5: F-491 Failure Isolation.

  F-491  "A failed department task does not roll back unrelated validated work. Contain failures
          to their dependency branch and preserve successful independent outputs."

The cited tests (test_cert_orchestration) assert retry, back-off and dead-lettering of the
failing job itself; none asserted what happens to the work around it. This does: a dead-lettered
job leaves an already-completed job's outputs and audit untouched, independent work queued
beside it completes, and the failure stays on its own row.

Local, deterministic; a private handler registry, no provider, no network.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_rows5.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_f491_a_dead_letter_neither_rolls_back_nor_blocks_independent_work():
    from sqlalchemy import func, select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog, Job, JobStatus, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import HandlerRegistry, Worker

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/iso.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    reg = HandlerRegistry()

    @reg.register("ops.heartbeat")
    def _ok(ctx):
        ctx.audit("test.validated_output", detail={"job": ctx.job.id})
        return {"validated": True, "n": (ctx.job.inputs or {}).get("n")}

    @reg.register("ops.queue_check")
    def _broken(ctx):
        raise RuntimeError("this department's task fails")

    q = JobQueue(db)
    worker = Worker(db, "iso", phase=Phase.SHADOW, registry=reg)
    done_before = q.enqueue("orchestrator", "ops.heartbeat", {"n": 1}, idempotency_key="a")
    assert worker.run_once()
    with db.session() as s:
        before = s.get(Job, done_before.id)
        snapshot = (before.status, dict(before.outputs or {}), before.finished_at)
    assert snapshot[0] == JobStatus.DONE and snapshot[1]["validated"] is True

    failing = q.enqueue("orchestrator", "ops.queue_check", {}, idempotency_key="b",
                        max_attempts=1)
    beside = q.enqueue("orchestrator", "ops.heartbeat", {"n": 2}, idempotency_key="c")
    ran = 0
    while worker.run_once() and ran < 10:
        ran += 1
    with db.session() as s:
        f, b, a = s.get(Job, failing.id), s.get(Job, beside.id), s.get(Job, done_before.id)
        assert f.status == JobStatus.DEAD and "fails" in (f.last_error or ""), f.status
        assert b.status == JobStatus.DONE and b.outputs == {"validated": True, "n": 2}
        # the completed job is exactly as it was: nothing was rolled back
        assert (a.status, dict(a.outputs or {}), a.finished_at) == snapshot
        outputs = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "test.validated_output"))
        assert outputs == 2, "a validated output's audit row was lost with the failure"
        others = list(s.scalars(select(Job).where(Job.id.notin_([failing.id]),
                                                  Job.status != JobStatus.DONE)))
    assert others == [], [(j.job_type, j.status) for j in others]


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 1, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
