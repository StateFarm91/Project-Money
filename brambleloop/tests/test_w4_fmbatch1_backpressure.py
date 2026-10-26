"""F-490: defect dead letters and fresh severe incidents scale the swarm down, overriding a
scale_up verdict; deliberate refusals and old or resolved incidents do not."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1bp_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/b.db"

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, JobStatus  # noqa: E402
from brambleloop.queue.durable import DELIBERATE_REFUSAL_TYPES  # noqa: E402
from brambleloop.swarm import backpressure as B, orchestrate as O  # noqa: E402

NOW = datetime.now(timezone.utc)


def _db():
    d = tempfile.mkdtemp(dir=_T)
    db = Database(f"sqlite:///{d}/x.db")
    db.create_all()
    with db.session() as s:     # the governor last advised scale_up
        s.add(AuditLog(actor="cfo", action=O.GOVERNOR_ACTION, at=NOW,
                       detail={"parallelism": {"advice": "scale_up", "why": "faster"}}))
    return db


def _dead(db, n, job_type="listing.seo", err="KeyError: boom"):
    with db.session() as s:
        for _ in range(n):
            s.add(Job(agent="a", job_type=job_type, status=JobStatus.DEAD, inputs={},
                      last_error=err, finished_at=NOW - timedelta(minutes=5)))


def test_no_pressure_leaves_the_governor_verdict():
    db = _db()
    assert B.read(db, now=NOW)["pressure"] is False
    assert O.parallelism_advice(db, now=NOW)["advice"] == "scale_up"


def test_defect_dead_letters_scale_down_but_refusals_do_not():
    db = _db()
    refusal_type = sorted(DELIBERATE_REFUSAL_TYPES)[0]
    _dead(db, 5, job_type=refusal_type, err="shadow mode")
    assert O.parallelism_advice(db, now=NOW)["advice"] == "scale_up"
    _dead(db, B.DEAD_LIMIT)
    a = O.parallelism_advice(db, now=NOW)
    assert a["advice"] == "scale_down" and "dead letters" in a["why"]


def test_fresh_severe_incident_scales_down_old_or_resolved_do_not():
    db = _db()
    with db.session() as s:
        s.add(Incident(severity="P1", signature="old", at=NOW - timedelta(days=2)))
        s.add(Incident(severity="P0", signature="fixed", resolved=True, at=NOW))
        s.add(Incident(severity="P3", signature="minor", at=NOW))
    assert O.parallelism_advice(db, now=NOW)["advice"] == "scale_up"
    with db.session() as s:
        s.add(Incident(severity="P1", signature="contract.regression", at=NOW))
    a = O.parallelism_advice(db, now=NOW)
    assert a["advice"] == "scale_down" and a["backpressure"][0]["trigger"] == \
        "fresh_severe_incidents"


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
