"""W4-CLOSE5 batch 4: F-487 Department Health, and the production 500 it uncovered.

  F-487  "Expose each department's active task, blocker, READY backlog, last durable progress,
          spend, output/evidence and whether capacity is idle."

Production b931d17 answers GET /api/departments with HTTP 500
(research/final_build/w4/evidence_BOARD/prod_api_departments_20261020T0540Z.json). The cause is
`swarm.metrics.agents_view`, which indexed `parked[t]["why"]`. A job type in *backoff* (an
unchanged poll; `swarm.orchestrate.suspended_job_types`) carries `until`/`factor` and no `why`,
so any agent holding a backed-off job type raised KeyError. W4-SWARMMETRICS' route test only
checked that the route string exists in main.py; it never executed the route.

These tests execute the route against a database holding a backoff and a suspension, and
assert the "output/evidence" clause the agents view did not carry.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_rows4.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="w4_close5_rows4_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP}/route.sqlite"
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.models import Incident, Job, JobStatus  # noqa: E402
from brambleloop.swarm import metrics, orchestrate  # noqa: E402

NOW = datetime.now(timezone.utc)


def _backoff_and_suspension(db, *, backoff_type: str, suspended_type: str) -> None:
    with db.session() as s:
        s.add(Incident(
            severity="P3", signature=f"{orchestrate.BACKOFF_SIGNATURE_PREFIX}{backoff_type}",
            summary="unchanged poll backing off", halts_publication=False,
            detail={"suspension": {"kind": orchestrate.BACKOFF, "job_type": backoff_type,
                                   "level": 1, "factor": 2,
                                   "suspend_until": (NOW + timedelta(hours=2)).isoformat()}}))
        s.add(Incident(
            severity="P2", signature=f"{orchestrate.THRASH_SIGNATURE_PREFIX}{suspended_type}",
            summary="paid loop without progress", halts_publication=False,
            detail={"suspension": {"kind": orchestrate.SUSPENDED, "job_type": suspended_type,
                                   "commit": orchestrate._commit()}}))


def _agent_holding(db, job_type: str) -> str:
    from brambleloop.core.models import Agent
    from sqlalchemy import select

    with db.session() as s:
        for a in s.scalars(select(Agent)):
            if job_type in (a.allowed_job_types or []):
                return a.name
    raise AssertionError(f"no agent holds {job_type}")


def test_f487_departments_route_serves_a_backed_off_job_type_instead_of_a_500():
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    main.db.create_all()
    Registry(main.db).seed_defaults()
    backoff, suspended = "intel.gallery_analysis", "listing.seo"
    _backoff_and_suspension(main.db, backoff_type=backoff, suspended_type=suspended)
    parked = orchestrate.suspended_job_types(main.db)
    assert parked[backoff]["kind"] == orchestrate.BACKOFF and "why" not in parked[backoff], \
        "premise: a backoff entry has no `why` (the shape that raised in production)"
    r = TestClient(main.app).get("/api/departments")
    assert r.status_code == 200, (r.status_code, r.text[:300])
    rows = {row["agent"]: row for row in r.json()["agents"]}
    held = rows[_agent_holding(main.db, backoff)]["parked_job_types"]
    assert held[backoff].startswith("backing off until") and "x2" in held[backoff], held
    if suspended in parked:      # a suspension (with its own why) is still said in its words
        sus = rows[_agent_holding(main.db, suspended)]["parked_job_types"][suspended]
        assert "without progress" in sus, sus


def test_f487_every_clause_is_on_each_department_row():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/d.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        s.add(Job(agent="listing", job_type="listing.seo", status=JobStatus.RUNNING,
                  inputs={}, created_at=NOW, run_after=NOW, started_at=NOW))
        s.add(Job(agent="listing", job_type="listing.seo", status=JobStatus.PENDING,
                  inputs={}, created_at=NOW, run_after=NOW))
        old = Job(agent="pricing", job_type="pricing.position", status=JobStatus.DONE,
                  inputs={}, created_at=NOW, run_after=NOW,
                  finished_at=NOW - timedelta(hours=2), outputs={"ok": True})
        new = Job(agent="pricing", job_type="pricing.position", status=JobStatus.DONE,
                  inputs={}, created_at=NOW, run_after=NOW,
                  finished_at=NOW - timedelta(minutes=5), outputs={"ok": True})
        s.add_all([old, new])
        s.flush()
        newest = new.id
    _backoff_and_suspension(db, backoff_type="pricing.position", suspended_type="listing.seo")
    rows = {r["agent"]: r for r in metrics.agents_view(db, now=NOW)["agents"]}
    li, pr = rows["listing"], rows["pricing"]
    for row in (li, pr):          # active task, blocker, READY backlog, progress, spend,
        assert {"running_job", "parked_job_types", "pending_ready", "last_completion",
                "month_spend_cad", "last_output", "idle"} <= set(row), row
    assert li["running_job"]["job_type"] == "listing.seo" and li["pending_ready"] == 1
    assert li["idle"] is False
    assert pr["last_output"] == {"job": f"jobs:{newest}", "job_type": "pricing.position"}
    assert pr["parked_job_types"]["pricing.position"].startswith("backing off until")
    assert pr["idle"] is True
    nobody = next(r for r in rows.values() if r["last_completion"] is None)
    assert nobody["last_output"] is None, "no finished job is no output, never invented"


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
    assert ran >= 2, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
