"""W4-OVERNIGHT: F-895 overnight-autonomy grading, prepared before the deploy it grades.

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_overnight_grade.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_overnight_")

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, JobStatus  # noqa: E402
from brambleloop.ops import overnight_grade as og  # noqa: E402

END = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
START = END - timedelta(hours=8)
_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _depts():
    exp = og.expected_departments()
    assert len(exp) >= og.MIN_DEPARTMENTS, exp
    return exp


def _night(db, *, useful_depts, idle_depts=(), cadence_every_hour=True, actor="orchestrator"):
    exp = _depts()
    with db.session() as s:
        for i, d in enumerate(useful_depts):
            s.add(Job(agent="x", job_type=exp[d][0], status=JobStatus.DONE, inputs={},
                      outputs={"work_done": 2, "summary": "did a thing"},
                      finished_at=START + timedelta(hours=1, minutes=i)))
        for i, d in enumerate(idle_depts):
            s.add(Job(agent="x", job_type=exp[d][0], status=JobStatus.DONE, inputs={},
                      outputs={"work_done": 0}, finished_at=START + timedelta(hours=2, minutes=i)))
        hours = range(8) if cadence_every_hour else range(0, 8, 2)
        for h in hours:
            s.add(Job(agent="orchestrator", job_type="ops.heartbeat", status=JobStatus.DONE,
                      inputs={}, idempotency_key=f"cadence:hb:{h}",
                      created_at=START + timedelta(hours=h, minutes=1),
                      finished_at=START + timedelta(hours=h, minutes=2)))
        s.add(AuditLog(actor=actor, action="job.completed:ops.heartbeat",
                       at=START + timedelta(hours=3)))


def _crit(rep, prefix):
    return next(c for c in rep["criteria"] if c["criterion"].startswith(prefix))


def test_an_unattended_useful_night_passes_with_every_department_named():
    db = _db()
    depts = sorted(_depts())
    _night(db, useful_depts=depts)
    rep = og.grade_db(db, start=START, end=END)
    assert rep["verdict"] == og.PASS, json.dumps(rep["criteria"], indent=1, default=str)
    assert {r["department"] for r in rep["departments"]} == set(depts)
    assert all(r["example"] and r["example"]["job"].startswith("jobs:")
               for r in rep["departments"])


def test_a_department_that_ran_but_did_nothing_fails_by_name():
    db = _db()
    depts = sorted(_depts())
    _night(db, useful_depts=depts[1:], idle_depts=depts[:1])
    rep = og.grade_db(db, start=START, end=END)
    assert rep["verdict"] == og.FAIL
    row = next(r for r in rep["departments"] if r["department"] == depts[0])
    assert row["result"] == og.FAIL and row["no_work"] == 1
    assert row["why"] == "ran but every finished job did no work"


def test_an_attended_night_is_not_autonomy():
    db = _db()
    _night(db, useful_depts=sorted(_depts()), actor="claude-session")
    rep = og.grade_db(db, start=START, end=END)
    assert _crit(rep, "unattended")["result"] == og.FAIL and rep["verdict"] == og.FAIL


def test_scheduler_gaps_and_incidents_fail_the_night():
    db = _db()
    _night(db, useful_depts=sorted(_depts()), cadence_every_hour=False)
    with db.session() as s:
        s.add(Incident(severity="P1", signature="test:p1", summary="worker died",
                       at=START + timedelta(hours=4)))
    rep = og.grade_db(db, start=START, end=END)
    assert _crit(rep, "scheduler kept scheduling")["result"] == og.FAIL
    assert _crit(rep, "no P0/P1")["result"] == og.FAIL


def test_an_empty_night_is_not_a_pass_and_a_short_or_future_window_is_refused():
    db = _db()
    rep = og.grade_db(db, start=START, end=END)
    assert rep["verdict"] != og.PASS
    short = og.grade_db(db, start=END - timedelta(hours=2), end=END)
    assert _crit(short, "window ended")["result"] == og.FAIL
    try:
        og.grade_db(db, start=START, end=datetime.now(timezone.utc) + timedelta(hours=1))
    except ValueError as exc:
        assert "ended" in str(exc)
    else:
        raise AssertionError("graded a night that has not ended")


def test_the_named_build_must_have_run():
    import os

    db = _db()
    _night(db, useful_depts=sorted(_depts()))
    old = os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    os.environ["RAILWAY_GIT_COMMIT_SHA"] = "0417f3516f30bb7c52926187fc475a0f46536e86"
    try:
        good = og.grade_db(db, start=START, end=END, commit="0417f35")
        bad = og.grade_db(db, start=START, end=END, commit="deadbee")
    finally:
        if old is None:
            os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)
        else:
            os.environ["RAILWAY_GIT_COMMIT_SHA"] = old
    assert _crit(good, "the named build")["result"] == og.PASS
    assert _crit(bad, "the named build")["result"] == og.FAIL


def test_public_precheck_counts_completions_and_is_never_better_than_incomplete():
    exp = _depts()
    first = sorted(exp)[0]
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith("/api/status"):
            return 200, json.dumps({"build": {"commit": "0417f35abc", "known": True}}).encode()
        if "/api/audit?action=job.completed:" in url:
            jt = url.split("job.completed:")[1].split("&")[0]
            rows = ([{"at": (START + timedelta(hours=1)).isoformat(), "actor": "x"},
                     {"at": (START - timedelta(hours=30)).isoformat(), "actor": "x"}]
                    if jt == exp[first][0] else [])
            return 200, json.dumps({"audit": rows}).encode()
        if "/api/audit?limit=1000" in url:
            return 200, json.dumps({"audit": [
                {"at": (START - timedelta(hours=1)).isoformat(), "actor": "orchestrator"},
                {"at": (START + timedelta(hours=1)).isoformat(), "actor": "orchestrator"}]}).encode()
        if url.endswith("/api/swarm/runtime"):
            return 200, json.dumps({"agent_quality": {"agents": {
                "laura": {"function_quality": {"value": 0.19}}}}}).encode()
        return 404, b"{}"

    rep = og.grade_public(fetch, "https://prod.example", start=START, end=END,
                          commit="0417f35")
    assert rep["verdict"] == og.INCOMPLETE and rep["mode"] == "public"
    row = next(r for r in rep["departments"] if r["department"] == first)
    assert row["completed"] == 1 and row["useful"] is None and row["result"] == og.UNKNOWN
    assert _crit(rep, "unattended")["result"] == og.PASS
    assert _crit(rep, "the named build")["result"] == og.PASS
    assert rep["agent_function_quality"] == {"laura": 0.19}
    assert all(u.startswith("https://prod.example/api/") for u in calls)  # GETs, public API only
    md = og.to_markdown(rep)
    assert "INCOMPLETE" in md and "| Unknown |" in md


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
