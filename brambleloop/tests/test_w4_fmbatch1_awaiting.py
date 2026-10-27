"""F-464: waiting on an external operation is a deferred poll job, not a held worker thread."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import awaiting as AW  # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker  # noqa: E402


def boot():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb1aw-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


STATE = {"ready_after_polls": 2, "max": 30}


def _registry():
    reg = HandlerRegistry()

    @reg.register("ops.slo")                    # stands in for "start a render"
    def start(ctx):
        return AW.defer(ctx, op_ref="render:42", poll_job_type="ops.queue_check",
                        delay_s=0, max_polls=STATE["max"])

    @reg.register("ops.queue_check")            # stands in for "poll the render"
    def poll(ctx):
        n = int(ctx.job.inputs["await"]["poll"])
        return AW.check(ctx, done=n >= STATE["ready_after_polls"])

    return reg


def _drain(db, reg):
    w = Worker(db, "w", registry=reg, job_types=["ops.slo", "ops.queue_check"])
    while w.run_once():
        pass


def test_the_starter_returns_at_once_and_polls_until_done():
    db = boot()
    STATE.update(ready_after_polls=3, max=30)
    JobQueue(db).enqueue("orchestrator", "ops.slo", {})
    _drain(db, _registry())
    with db.session() as s:
        start = s.scalar(select(Job).where(Job.job_type == "ops.slo"))
        polls = list(s.scalars(select(Job).where(Job.job_type == "ops.queue_check")
                               .order_by(Job.id)))
        done = s.scalar(select(AuditLog).where(AuditLog.action == AW.ACTION + ".done"))
    assert start.status == JobStatus.DONE and start.outputs["thread_held"] is False
    assert [p.inputs["await"]["poll"] for p in polls] == [1, 2, 3]
    assert all(p.status == JobStatus.DONE for p in polls)
    assert done is not None and done.detail["polls"] == 3


def test_a_wait_that_never_finishes_is_given_up_and_recorded():
    db = boot()
    STATE.update(ready_after_polls=99, max=2)
    JobQueue(db).enqueue("orchestrator", "ops.slo", {})
    _drain(db, _registry())
    with db.session() as s:
        n = len(list(s.scalars(select(Job).where(Job.job_type == "ops.queue_check"))))
        gave = s.scalar(select(AuditLog).where(AuditLog.action == AW.ACTION + ".gave_up"))
    assert n == 2 and gave is not None


def test_the_poll_is_scheduled_later_not_run_inline():
    db = boot()

    class Ctx:
        class job:
            agent, job_type, inputs, id = "orchestrator", "ops.slo", {}, 0
        def enqueue(self, *a, **k):
            return JobQueue(db).enqueue(*a, **k)
        def audit(self, *a, **k):
            pass

    now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
    out = AW.defer(Ctx(), op_ref="x", poll_job_type="ops.queue_check", delay_s=120, now=now)
    with db.session() as s:
        j = s.get(Job, out["poll_job_id"])
        ra = j.run_after if j.run_after.tzinfo else j.run_after.replace(tzinfo=timezone.utc)
    assert ra == now + timedelta(seconds=120)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
