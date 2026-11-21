"""A deploy is new code: a rebuild attempt that ended before the current commit's first boot
does not hold the product in RETRY_AFTER; an in-flight one still does."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core import build  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.ops import rebuild_graph as RG  # noqa: E402

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/r.db")
    db.create_all()
    return db


def _job(db, slug, status, finished):
    with db.session() as s:
        s.add(Job(agent="listing", job_type="chain.rebuild", inputs={"product_slug": slug},
                  status=status, finished_at=finished, created_at=NOW - timedelta(hours=6)))


def _boot(db, commit, at):
    with db.session() as s:
        s.add(AuditLog(at=at, actor="orchestrator", action="runtime.started",
                       detail={"commit": commit}))


def test_an_attempt_that_ended_before_this_deploy_does_not_hold_the_product():
    db = _db()
    real = build.identity
    build.identity = lambda: {"commit": "newsha"}
    try:
        _boot(db, "oldsha", NOW - timedelta(hours=8))
        _boot(db, "newsha", NOW - timedelta(hours=1))
        _job(db, "ended-before", JobStatus.DONE, NOW - timedelta(hours=3))
        _job(db, "ended-after", JobStatus.DONE, NOW - timedelta(minutes=30))
        _job(db, "in-flight", JobStatus.PENDING, None)
        with db.session() as s:
            got = RG._recent_rebuild_slugs(s, NOW)
        assert "ended-before" not in got, got
        assert {"ended-after", "in-flight"} <= got, got
    finally:
        build.identity = real


def test_without_a_known_deploy_the_plain_window_holds():
    db = _db()
    real = build.identity
    build.identity = lambda: {"commit": "dev"}
    try:
        _job(db, "ended-before", JobStatus.DONE, NOW - timedelta(hours=3))
        with db.session() as s:
            assert "ended-before" in RG._recent_rebuild_slugs(s, NOW)
    finally:
        build.identity = real


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
