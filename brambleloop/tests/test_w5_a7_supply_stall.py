"""W5-A7 (P0-SUPPLY-STALL): an exhausted concept pool is recorded, never silent.

`draft:<slug>` is permanent, so once every concept in POOL (plus approved intake) has been
drafted, `radar.scan` can select nothing new. The real `radar.scan` and `radar.score` handlers
run on a SQLite FILE through `JobQueue` and `Worker.run_once`:

* POOL exhausted: one `radar.supply_stall` reading and one audit per scan date, however many
  scans run that day; a new date is a new period; no duplicate `cir.draft` is queued.
* Selection all drafted while undrafted pool concepts remain: recorded, with its own reason.
* Supply available: no reading.
* The reading is visible on the Command Center Production view (stalls_loops) and in the
  readback evidence (autonomy_loop), informational only: no /api/verify check is added.

Every drafted job here is a TEST FIXTURE standing in for an earlier real draft.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w5_a7_supply_stall.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="w5_a7_supply_stall_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse
socket.create_connection = _refuse

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, OperatingReading, Phase, utcnow,
)
from brambleloop.ops import flow_health  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar.intake import pool_with_intake  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

DAY1, DAY2 = "2026-11-02", "2026-11-03"


def _db(name):
    path = Path(tempfile.mkdtemp(dir=_TMP)) / f"{name}.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    assert path.exists()                         # a real file, not :memory:
    return db


def _drafted(db, slugs):
    """Fixture: the permanent `draft:<slug>` job an earlier real draft would have left."""
    with db.session() as s:
        for slug in slugs:
            s.add(Job(agent="crochet_engineer", job_type="cir.draft", inputs={"slug": slug},
                      outputs={"drafted": True}, status=JobStatus.DONE,
                      idempotency_key=f"draft:{slug}"))


def _scan(db, as_of, key):
    job = JobQueue(db).enqueue("market_radar", "radar.scan", {"target": 10, "as_of": as_of},
                               idempotency_key=key, priority=0)
    assert Worker(db, f"w-{key}", phase=Phase.SHADOW, job_types=["radar.scan"],
                  lease_seconds=900).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
    assert row.status is JobStatus.DONE, row.last_error
    return row.outputs


def _score_all(db):
    w = Worker(db, "w-score", phase=Phase.SHADOW, job_types=["radar.score"], lease_seconds=900)
    for _ in range(200):
        if not w.run_once():
            break


def _readings(db):
    with db.session() as s:
        return [(r.period_key, dict(r.payload or {})) for r in s.scalars(
            select(OperatingReading).where(
                OperatingReading.kind == flow_health.SUPPLY_STALL_KIND).order_by(
                OperatingReading.id))]


def _audits(db):
    with db.session() as s:
        return list(s.scalars(select(AuditLog.id).where(AuditLog.action == "radar.supply_stall")))


def _drafts(db):
    with db.session() as s:
        return sorted(s.scalars(select(Job.idempotency_key).where(Job.job_type == "cir.draft")))


def test_an_exhausted_pool_is_recorded_once_per_period_and_drafts_nothing_twice():
    db = _db("exhausted")
    pool = [c.slug for c in pool_with_intake(db)]
    assert pool
    _drafted(db, pool)
    before = _drafts(db)

    out = _scan(db, DAY1, "scan-1")
    supply = out["concept_supply"]
    assert supply["stalled"] is True and supply["recorded"] is True, supply
    assert supply["reason"] == "pool_exhausted" and supply["undrafted_pool"] == 0
    assert supply["drafted"] == supply["pool"] == len(set(pool))
    rows = _readings(db)
    assert [p for p, _ in rows] == [DAY1], rows
    assert rows[0][1]["reason"] == "pool_exhausted" and rows[0][1]["undrafted_pool"] == []
    assert len(_audits(db)) == 1

    # The same period again (the 6-hourly cadence, the daily plan.cycle): nothing new.
    again = _scan(db, DAY1, "scan-2")
    assert again["concept_supply"]["stalled"] is True
    assert again["concept_supply"]["recorded"] is False
    assert len(_readings(db)) == 1 and len(_audits(db)) == 1

    # The scores the scans queued run for real; none can queue a second cir.draft.
    _score_all(db)
    with db.session() as s:
        scored = list(s.scalars(select(Job).where(Job.job_type == "radar.score")))
        assert scored and all(j.status is JobStatus.DONE for j in scored), \
            [(j.status, j.last_error) for j in scored if j.status is not JobStatus.DONE][:3]
        # An already admitted slug is held, never reported as a newly promoted draft.
        assert any((j.outputs or {}).get("draft_hold") for j in scored)
        assert all(not (j.outputs or {}).get("promoted") for j in scored)
    assert _drafts(db) == before

    # A new period is a new reading, once.
    _scan(db, DAY2, "scan-3")
    _scan(db, DAY2, "scan-4")
    assert [p for p, _ in _readings(db)] == [DAY1, DAY2] and len(_audits(db)) == 2
    _score_all(db)
    assert _drafts(db) == before


def test_with_supply_available_there_is_no_reading():
    db = _db("supply")
    out = _scan(db, DAY1, "scan-s")
    supply = out["concept_supply"]
    assert supply["stalled"] is False and supply["recorded"] is False, supply
    assert supply["undrafted_selected"] == len(out["selected"]) > 0
    assert _readings(db) == [] and _audits(db) == []
    assert flow_health.concept_supply_stall(db) is None


def test_noncanonical_existing_drafts_are_not_new_supply_or_scored_again():
    db = _db("noncanonical-drafts")
    pool = [c.slug for c in pool_with_intake(db)]
    with db.session() as s:
        for slug in pool:
            s.add(Job(agent="crochet_engineer", job_type="cir.draft", inputs={"slug": slug},
                      status=JobStatus.DONE, idempotency_key=f"recovery:{slug}:v1"))
    before = _drafts(db)
    out = _scan(db, DAY1, "noncanonical-scan")
    assert out["concept_supply"]["reason"] == "pool_exhausted"
    _score_all(db)
    assert _drafts(db) == before
    with db.session() as s:
        scores = list(s.scalars(select(Job).where(Job.job_type == "radar.score")))
        assert any((j.outputs or {}).get("draft_hold") for j in scores)
        assert all(not (j.outputs or {}).get("promoted") for j in scores)


def test_a_selection_of_only_drafted_concepts_is_recorded_with_its_own_reason():
    db = _db("selection")
    first = _scan(db, DAY1, "scan-a")
    assert first["concept_supply"]["stalled"] is False
    _drafted(db, first["selected"])
    # Same date, so the same deterministic selection -- now every one of them drafted.
    second = _scan(db, DAY1, "scan-b")
    assert second["selected"] == first["selected"]
    supply = second["concept_supply"]
    assert supply["stalled"] is True and supply["recorded"] is True, supply
    assert supply["undrafted_pool"] > 0 and supply["reason"] == "selection_all_drafted"
    assert [p for p, _ in _readings(db)] == [DAY1] and len(_audits(db)) == 1
    assert _readings(db)[0][1]["undrafted_pool"]          # what could still be drafted


def test_recovery_and_a_later_stall_are_reported_from_real_scans():
    db = _db("recovery")
    pool = [c.slug for c in pool_with_intake(db)]
    _drafted(db, pool)
    first = _scan(db, DAY1, "recovery-stalled")
    assert first["concept_supply"]["stalled"] is True
    assert flow_health.concept_supply_stall(db) is not None
    selected = first["selected"]
    assert selected
    # Remove one test-only draft fixture to simulate newly eligible supply.
    with db.session() as session:
        fixture = session.scalar(select(Job).where(
            Job.idempotency_key == f"draft:{selected[0]}"))
        session.delete(fixture)
    recovered = _scan(db, DAY1, "recovery-available")
    assert recovered["concept_supply"]["stalled"] is False, recovered
    assert flow_health.concept_supply_stall(db) is None
    fresh = Database(str(db.engine.url))
    assert flow_health.concept_supply_stall(fresh) is None
    # A fresh stall later that day must not stay hidden by the healthy scan.
    _drafted(db, [selected[0]])
    stalled_again = _scan(db, DAY1, "recovery-stalled-again")
    assert stalled_again["concept_supply"]["stalled"] is True
    assert flow_health.concept_supply_stall(db) is not None
    assert flow_health.concept_supply_stall(Database(str(db.engine.url))) is not None
    assert len(_readings(db)) == 1


def test_backdated_or_future_scan_cannot_clear_a_current_stall():
    from datetime import date, timedelta

    db = _db("as-of-replay")
    today = date.today()
    current, historical, future = (today.isoformat(), (today - timedelta(days=1)).isoformat(),
                                   (today + timedelta(days=1)).isoformat())
    _drafted(db, [c.slug for c in pool_with_intake(db)])
    original = _scan(db, current, "current-stall")
    assert original["concept_supply"]["stalled"] is True
    assert flow_health.concept_supply_stall(db) is not None
    # Remove test-only fixtures so both replayed scans find available supply.
    with db.session() as session:
        for row in session.scalars(select(Job).where(Job.job_type == "cir.draft")):
            session.delete(row)
    old = _scan(db, historical, "historical-supply")
    assert old["concept_supply"]["stalled"] is False
    assert flow_health.concept_supply_stall(db) is not None
    projected = _scan(db, future, "future-supply")
    assert projected["concept_supply"]["stalled"] is False
    assert flow_health.concept_supply_stall(db) is not None
    current_supply = _scan(db, current, "current-supply")
    assert current_supply["concept_supply"]["stalled"] is False
    assert flow_health.concept_supply_stall(db) is None


def test_unmeasured_scan_never_proves_recovery():
    db = _db("unknown")
    _drafted(db, [c.slug for c in pool_with_intake(db)])
    _scan(db, DAY1, "unknown-stalled")
    with db.session() as session:
        session.add(Job(agent="market_radar", job_type="radar.scan",
                        inputs={}, outputs={"concept_supply": {"measured": False}},
                        status=JobStatus.DONE, finished_at=utcnow(),
                        idempotency_key="fixture-unmeasured"))
    assert flow_health.concept_supply_stall(db) is not None


def test_the_reading_is_visible_to_the_command_center_and_the_readback_evidence():
    from brambleloop.app.command_center import production
    from brambleloop.ops import production_evidence as pe

    db = _db("visible")
    quiet = {"rows": [], "stalled_count": 0, "looping_count": 0, "thresholds": {}}
    assert production._stalls_loops(quiet, flow_health.concept_supply_stall(db))["status"] == "OK"
    assert pe.autonomy_loop(db, now=utcnow())["concept_supply_stall"] is None

    _drafted(db, [c.slug for c in pool_with_intake(db)])
    _scan(db, DAY1, "scan-v")
    got = flow_health.concept_supply_stall(db)
    assert got and got["period"] == DAY1 and got["reason"] == "pool_exhausted", got
    env = production._stalls_loops(quiet, got)
    assert env["status"] == "DEGRADED" and "operating_readings" in env["sources"]
    assert any("no new concept supply" in i["kind"] for i in env["items"]), env["items"]
    loop = pe.autonomy_loop(db, now=utcnow())
    assert loop["concept_supply_stall"]["period"] == DAY1
    # Informational: the anonymous /api/verify checks are unchanged.
    assert tuple(c["check"] for c in pe.checks(db)) == pe.CHECK_NAMES


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
