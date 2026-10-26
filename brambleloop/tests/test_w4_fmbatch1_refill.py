"""F-722: a deployed worker wakes the orchestrator the moment a job's end empties the
runnable queue; a hand-built worker does not; the wake is keyed and cannot flood."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import handlers as _h  # noqa: E402,F401  (registers handlers)
from brambleloop.autonomy.orchestrator import ORCHESTRATE_JOB  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker  # noqa: E402


def boot():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb1rf-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _registry():
    reg = HandlerRegistry()
    reg.register("ops.slo")(lambda ctx: {"ok": True})
    return reg


def _orchestrate_jobs(db):
    with db.session() as s:
        return list(s.scalars(select(Job.id).where(Job.job_type == ORCHESTRATE_JOB)))


def test_last_job_ending_wakes_the_orchestrator_once():
    db = boot()
    q = JobQueue(db)
    q.enqueue("orchestrator", "ops.slo", {"n": 1})
    q.enqueue("orchestrator", "ops.slo", {"n": 2})
    w = Worker(db, "w", registry=_registry(), job_types=["ops.slo"], refill_on_idle=True)
    assert w.run_once() and _orchestrate_jobs(db) == []        # work still runnable
    assert w.run_once() and len(_orchestrate_jobs(db)) == 1     # queue now empty: wake
    assert w.refill_wakes == 1
    q.enqueue("orchestrator", "ops.slo", {"n": 3})
    assert w.run_once() and len(_orchestrate_jobs(db)) == 1     # an orchestrate job is
    #                                                             pending: not idle, no flood


def test_hand_built_worker_does_not_wake():
    db = boot()
    JobQueue(db).enqueue("orchestrator", "ops.slo", {})
    w = Worker(db, "w", registry=_registry(), job_types=["ops.slo"])
    assert w.run_once() and _orchestrate_jobs(db) == [] and w.refill_wakes == 0


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
