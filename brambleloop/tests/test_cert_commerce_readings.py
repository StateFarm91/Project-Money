"""Certification C-59: gated rows' machinery runs in the runtime, not only in unit tests.

Six rows (#23, #236, #253, #254, #256, #257) were parked on a data or owner gate while the
library each named was reached by nothing in the running system. This drives the scheduled
`commerce.readings` job through the worker and proves each library produced its reading --
UNMEASURED where the data does not exist, which is today.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers every handler
from brambleloop.runtime.worker import CADENCES, Worker  # noqa: E402
from brambleloop.build2 import reachability  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/readings.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_the_readings_job_is_scheduled_permitted_and_runs_every_library():
    assert any(c[2] == "commerce.readings" for c in CADENCES)
    db = _db()
    job = JobQueue(db).enqueue("cfo", "commerce.readings", {}, idempotency_key="cr-1")
    assert Worker(db, "readings", phase=Phase.SHADOW, job_types=["commerce.readings"]).run_once()
    with db.session() as s:
        done = s.get(Job, job.id)
        assert done.status == JobStatus.DONE, done.last_error
        row = s.scalar(select(AuditLog).where(AuditLog.action == "commerce.readings"))
        reading = row.detail["reading"]
    for key in ("kill_table", "reviews", "club", "referral", "personalisation", "insights_plan"):
        assert key in reading, key
    # Nothing is invented: with no orders the referral outcome is not measurable, the club may
    # not launch, and the review stars are unmeasured.
    assert reading["referral"]["measurable"] is False
    assert reading["club"]["may_launch"].get("may_launch") is False


def test_each_gated_library_is_now_reached_from_the_runtime():
    reachability.reachable.cache_clear()
    reachability._references.cache_clear()
    for rel in ("commerce/kill_table.py", "commerce/reviews.py", "commerce/club.py",
                "commerce/referral.py", "products/personalisation.py",
                "intel/insights_budget.py"):
        v = reachability.reached(rel)
        assert v["reached"], v


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
