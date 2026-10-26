"""F-496: an HQ worker claims only GREEN-only, handled job types the cloud can also run;
its jobs return to PENDING when its lease lapses."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1hq_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/h.db"

from brambleloop.app import hq_worker as H  # noqa: E402


def _refused(fn):
    try:
        fn()
    except H.HQRefused as exc:
        return str(exc)
    raise AssertionError("accepted")


def test_plan_accepts_green_handled_types_only():
    assert H.plan(["learn.scan"])["job_types"] == ["learn.scan"]
    assert "GREEN-only" in _refused(lambda: H.plan(["store.publish"]))
    assert "names no job type" in _refused(lambda: H.plan([" "]))
    assert "no registered handler" in _refused(
        lambda: H.plan(["learn.scan"], registered=lambda t: False))
    assert "independence" in _refused(lambda: H.plan(["learn.scan"], cloud_types=["x"]))
    assert H.plan(["learn.scan"], cloud_types=["learn.scan", "x"])["independent"]


def test_an_hq_lease_that_lapses_returns_the_job_to_the_cloud():
    from brambleloop.core.db import Database
    from brambleloop.queue.durable import JobQueue

    db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
    db.create_all()
    q = JobQueue(db, lease_seconds=1)
    q.enqueue("learn", "learn.scan", {}, idempotency_key="hq-1")
    job = q.claim("hq-box", ["learn.scan"])
    assert job is not None and job.status.value == "running"
    import time

    time.sleep(1.5)                               # HQ went offline without finishing
    again = q.claim("cloud-1", None)
    assert again is not None and again.id == job.id


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
