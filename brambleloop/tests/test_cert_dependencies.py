"""#50, #29 and #31 on a cadence, acted on (C-68/C-69).

`ops.dependencies` (daily) probes the dependency map against the database and raises what
fails; the anti-fragility axes raise an existential concentration; `finance.governor`
(hourly) measures validated products per operating dollar and caps the lanes that spent
without producing one. Each runs through the worker on a real database.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, CostEntry, Incident, Job, JobStatus, utcnow,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, Worker  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/deps.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, agent, job_type):
    job = JobQueue(db).enqueue(agent, job_type, {}, priority=0,
                               idempotency_key=f"{job_type}:{utcnow().timestamp()}")
    Worker(db, "deps", job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        return dict(row.outputs)


def _open(db, prefix):
    with db.session() as s:
        return sorted(i.signature for i in s.scalars(select(Incident).where(
            Incident.resolved.is_(False), Incident.signature.like(f"{prefix}%"))))


def test_the_dependency_sweep_is_scheduled_granted_and_banded():
    assert any(jt == "ops.dependencies" for _n, _a, jt, _p in CADENCES)
    assert orc.band_for("ops.dependencies")["mapped"]


def test_failed_probes_and_an_unproved_recovery_are_raised_and_resolve_when_fixed():
    db = _db()
    out = _run(db, "orchestrator", "ops.dependencies")
    assert "postgres" in out["failing"], out["failing"]      # restore never proved
    assert "model_provider" in out["failing"]
    opened = _open(db, "dependency:")
    assert "dependency:postgres" in opened and "dependency:model_provider" in opened
    assert "dependency:etsy_account" not in opened, "owner-only recoveries are not our incident"
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action="continuity.verified", detail={}))
    out = _run(db, "orchestrator", "ops.dependencies")
    assert "dependency:postgres" in out["resolved"]
    assert "dependency:postgres" not in _open(db, "dependency:")


def test_the_railway_probe_reads_the_health_record_or_says_unknown():
    """C-80 defect 9: the host probe was a constant `ok: True`. Off Railway it is UNKNOWN;
    on Railway a gap in the ops.health record fails it and opens the incident, and a
    continuous record resolves it -- all through the daily sweep on the worker."""
    import os

    db = _db()
    for marker in ("RAILWAY_ENVIRONMENT", "RAILWAY_GIT_COMMIT_SHA", "RAILWAY_SERVICE_ID",
                   "RAILWAY_PROJECT_ID"):
        os.environ.pop(marker, None)
    out = _run(db, "orchestrator", "ops.dependencies")
    assert out["probes"]["railway"]["ok"] is None and "UNKNOWN" in out["probes"]["railway"]["why"]
    assert "railway" in out["unknown"] and "dependency:railway" not in _open(db, "dependency:")

    os.environ["RAILWAY_ENVIRONMENT"] = "production"
    try:
        # on Railway with no sweep yet: still UNKNOWN, not healthy
        out = _run(db, "orchestrator", "ops.dependencies")
        assert out["probes"]["railway"]["ok"] is None and out["probes"]["railway"]["on_railway"]
        # a five-hour hole in the last day's health record: the host let the container die
        now = utcnow()
        with db.session() as s:
            for minutes in (20 * 60, 19 * 60, 18 * 60, 5 * 60, 30, 10):
                s.add(AuditLog(actor="orchestrator", action="ops.health", detail={},
                               at=now - timedelta(minutes=minutes)))
        out = _run(db, "orchestrator", "ops.dependencies")
        railway = out["probes"]["railway"]
        assert railway["ok"] is False and railway["max_gap_minutes"] >= 12 * 60, railway
        assert "railway" in out["failing"] and "dependency:railway" in _open(db, "dependency:")
        # a continuous record since: the probe recovers and the incident resolves
        with db.session() as s:
            for minutes in range(15, 20 * 60, 15):
                s.add(AuditLog(actor="orchestrator", action="ops.health", detail={},
                               at=now - timedelta(minutes=minutes)))
        out = _run(db, "orchestrator", "ops.dependencies")
        assert out["probes"]["railway"]["ok"] is True
        assert "dependency:railway" in out["resolved"]
        assert "dependency:railway" not in _open(db, "dependency:")
    finally:
        os.environ.pop("RAILWAY_ENVIRONMENT", None)


def test_a_billed_provider_the_map_does_not_name_is_raised():
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="creative_director", amount_cad=0.3, provider="mistral",
                        kind="llm"))
    out = _run(db, "orchestrator", "ops.dependencies")
    assert out["unmapped"] == ["mistral"]
    assert "dependency:unmapped:mistral" in _open(db, "dependency:")


def test_one_ai_provider_carrying_all_the_spend_is_raised_as_existential():
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="creative_director", amount_cad=2.0, provider="anthropic",
                        kind="llm"))
    out = _run(db, "orchestrator", "ops.dependencies")
    assert "ai_provider" in out["existential"], out["axes"]
    assert out["axes"]["ai_provider"]["largest"] == "anthropic"
    assert "anti-fragility:ai_provider" in _open(db, "anti-fragility:")


def test_spend_without_a_validated_pattern_is_an_incident_and_caps_the_lane():
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="creative_director", amount_cad=6.0, provider="anthropic",
                        kind="llm", at=utcnow() - timedelta(days=2)))
    out = _run(db, "cfo", "finance.governor")
    uc = out["unit_cost"]
    assert uc["measurable"] and uc["validated_products"] == 0
    assert uc["action"] == "incident_and_lane_cap"
    assert "creative_director" in uc["unproductive_agents"]
    assert _open(db, "throughput-no-validated-output:")
    # enough queued work that the lane would otherwise be granted two specialists
    for i in range(13):
        JobQueue(db).enqueue("creative_director", "creative.blinded", {"i": i},
                             idempotency_key=f"b{i}", priority=85)
    alloc = orc.allocate(db)
    lane = alloc["lanes"]["creative_director"]
    assert lane["wanted"] >= 2 and lane["granted"] == 1, lane
    assert any("no validated pattern" in b for b in lane["boosts"]), lane["boosts"]


def test_below_the_spend_floor_the_ratio_is_noise_and_nothing_acts():
    db = _db()
    out = _run(db, "cfo", "finance.governor")
    assert out["unit_cost"]["measurable"] is False and out["unit_cost"]["action"] == "none"


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
