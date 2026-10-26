"""F-550: the Etsy daily exception report and the once-per-quarter deep audit, read-only."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _no_network(*_a, **_k):
    raise OSError("network refused: this report makes no Etsy call")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, JobStatus  # noqa: E402
from brambleloop.intel import etsy_ops_report as E  # noqa: E402

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb1eo-')}/t.sqlite")
    db.create_all()
    return db


def test_daily_names_each_exception_with_its_row():
    db = _db()
    with db.session() as s:
        s.add(Incident(signature="taxonomy-drift:hex", severity="P1", summary="drift",
                       detail={}))
        s.add(Incident(signature="health:disk", severity="P1", summary="other", detail={}))
        s.add(Job(agent="listing", job_type="listing.seo", status=JobStatus.DEAD,
                  finished_at=NOW - timedelta(hours=2), inputs={}))
        s.add(Job(agent="orchestrator", job_type="ops.slo", status=JobStatus.DEAD,
                  finished_at=NOW - timedelta(hours=2), inputs={}))
        s.add(AuditLog(actor="o", action="etsy.probe", detail={"ok": False}))
    d = E.daily(db, now=NOW)
    kinds = {(x["kind"], x["ref"]) for x in d["exceptions"]}
    assert ("incident", "taxonomy-drift:hex") in kinds
    assert not any(r == "health:disk" for _k, r in kinds)
    assert any(k == "dead_letter" for k, _r in kinds)
    assert not any(x.get("job_type") == "ops.slo" for x in d["exceptions"])
    assert ("stale_cadence", "etsy_probe") in kinds and d["etsy_probe"] == "failing"


def test_quarterly_runs_once_per_quarter_and_outcomes_are_unmeasured_not_zero():
    db = _db()
    first = E.run(db, now=NOW)
    again = E.run(db, now=NOW + timedelta(days=1))
    nextq = E.run(db, now=datetime(2027, 1, 2, tzinfo=timezone.utc))
    assert first["quarterly"] == "2026-Q4" and "quarterly" not in again
    assert nextq["quarterly"] == "2027-Q1"
    with db.session() as s:
        q = s.scalar(select(AuditLog).where(AuditLog.action == E.QUARTERLY_ACTION))
        n_daily = s.query(AuditLog).filter(AuditLog.action == E.DAILY_ACTION).count()
    assert q.detail["listing_outcomes"] == "UNMEASURED" and n_daily == 3


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
