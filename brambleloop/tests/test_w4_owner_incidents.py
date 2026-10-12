"""W4-OWNER: the 18 incidents production held open on 2026-10-06, reproduced and closed by rule.

Production (deployed fcb982d, `/api/status` open_incidents=18) listed 6 seasonal at-risk rows,
2 collection-calendar rows, 2 preparation-late rows, 6 never-read policy rows, the
provenance backlog and a build stall. Each row is seeded here with the signature the deployed
code wrote, then the real cadence handlers of this build run through a worker. Every row must
either close with a stated resolution and a resolved_at, or stay open because its condition
is still true (the provenance backlog, whose count is real). Nothing is deleted.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Incident, Job, JobStatus, PatternVersion, Product,
)
from brambleloop.ops import incident_lifecycle as L  # noqa: E402

RESULTS: list[str] = []

# The deployed build's signatures (fcb982d runtime/release.py, ops/artefacts.py).
PRODUCTION_18 = [
    ("seasonal.at_risk:market-basket-trio:Halloween", "P2", "market-basket-trio"),
    ("seasonal.at_risk:pet-snuggle-mat:Halloween", "P2", "pet-snuggle-mat"),
    ("policy_stale:seller_policy", "P2", None),
    ("policy_stale:creativity_standards", "P2", None),
    ("policy_stale:listing_image_rules", "P2", None),
    ("policy_stale:advertising_rules", "P2", None),
    ("policy_stale:shilling_and_reviews", "P2", None),
    ("seasonal.at_risk:mosaic-placemat-pair:Halloween", "P2", "mosaic-placemat-pair"),
    ("seasonal.calendar_behind:Halloween", "P2", None),
    ("seasonal.preparation_late:LONG:search_language", "P3", None),
    ("stale-artefact:backlog", "P3", None),
    ("seasonal.calendar_behind:Thanksgiving (CA)", "P2", None),
    ("build.stalled", "P2", None),
    ("seasonal.at_risk:pressed-flower-motifs:Halloween", "P2", "pressed-flower-motifs"),
    ("policy_stale:children_and_baby", "P2", None),
    ("seasonal.at_risk:nordic-forest-bundle:Halloween", "P2", "nordic-forest-bundle"),
    ("seasonal.preparation_late:MEDIUM:search_language", "P3", None),
    ("seasonal.at_risk:nordic-forest-mosaic-throw:Christmas", "P2",
     "nordic-forest-mosaic-throw"),
]


def ok(name: str) -> None:
    RESULTS.append(name)
    print(f"OK {name}")


def _catalogue_db() -> Database:
    from brambleloop.products.builder import CATALOGUE, build

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/w4owner.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    slugs = sorted(CATALOGUE)
    assert slugs
    with db.session() as s:
        for slug in slugs:
            cir = build(CATALOGUE[slug])
            p = Product(slug=slug, title=cir.title, status="certified")
            p.created_at = datetime(2026, 9, 17, tzinfo=timezone.utc)
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version=cir.version,
                                 cir_json=cir.to_dict(), release_hash="0" * 64,
                                 certified=True, certificate={"granted": True}))
    return db


def reproduce_production(as_of: str = "2026-10-06") -> tuple[Database, dict]:
    """Seed the 18 deployed rows, run this build's handlers, return the before/after."""
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import Worker

    db = _catalogue_db()
    assert len(PRODUCTION_18) == 18
    with db.session() as s:
        for sig, sev, slug in PRODUCTION_18:
            s.add(Incident(signature=sig, severity=sev, product_slug=slug,
                           summary=f"production row {sig}", detail={}))
    q = JobQueue(db)
    for i, (jt, inputs) in enumerate([("seasonal.sentinel", {"as_of": as_of}),
                                      ("ops.policy_watch", {}), ("build.tick", {}),
                                      ("ops.sentinel", {})]):
        q.enqueue("orchestrator", jt, inputs, idempotency_key=f"w4-owner-repro-{i}")
    worker = Worker(db, "w4-owner-repro")
    for _ in range(40):
        if not worker.run_once():
            break
    with db.session() as s:
        jobs = list(s.scalars(select(Job)))
        dead = [(j.job_type, (j.last_error or "")[:200]) for j in jobs
                if j.status == JobStatus.DEAD]
        assert not dead, dead
        rows = list(s.scalars(select(Incident).order_by(Incident.id)))
        legacy = {r.signature: {"resolved": bool(r.resolved),
                                "resolution": (r.detail or {}).get("resolution"),
                                "resolved_at": (r.detail or {}).get("resolved_at"),
                                "detail": dict(r.detail or {})}
                  for r in rows if r.id <= 18}
        new_open = [{"signature": r.signature, "severity": r.severity,
                     "summary": r.summary[:300]} for r in rows
                    if r.id > 18 and not r.resolved]
    return db, {"legacy": legacy, "new_open": new_open}


def test_production_18_close_by_rule_or_stay_true():
    _db, out = reproduce_production()
    legacy = out["legacy"]
    assert len(legacy) == 18, sorted(legacy)
    still = sorted(s for s, v in legacy.items() if not v["resolved"])
    # The provenance backlog is a real, counted condition in this fixture (certificates with
    # no provenance row); it is the only legacy row allowed to stay open.
    assert still == ["stale-artefact:backlog"], still
    backlog = legacy["stale-artefact:backlog"]["detail"]
    assert backlog.get("unproven", 0) > 0, backlog
    for sig, v in legacy.items():
        if v["resolved"]:
            assert v["resolution"] and v["resolved_at"], (sig, v)
    text = legacy["seasonal.at_risk:nordic-forest-mosaic-throw:Christmas"]["resolution"]
    assert "not merchandised for Christmas (its occasion is Christmas)" not in text, text
    assert out["new_open"], "this build re-raises the current seasonal conditions"
    for row in out["new_open"]:
        # Anything this build raises is year-keyed (or the backlog), never the old shape.
        fam = L.kind_of(row["signature"])
        if fam.startswith("seasonal."):
            parts = row["signature"].split(":")
            assert any(len(x) == 4 and x.isdigit() for x in parts[2:]), row
    ok(f"production 18: {18 - len(still)} closed by rule with reasons, 1 still true; "
       f"{len(out['new_open'])} current conditions re-raised year-keyed")


def test_every_production_family_names_its_remediation_owner():
    fams = {L.kind_of(sig) for sig, _s, _p in PRODUCTION_18}
    assert fams
    for fam in fams:
        assert fam in L.REMEDIATION, fam
    ok(f"{len(fams)} production families have a remediation owner and path")


def _plain_db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def test_duplicates_close_into_the_oldest_row():
    db = _plain_db()
    with db.session() as s:
        for n in range(3):
            s.add(Incident(signature="health:queue", severity="P1", summary=f"dup {n}",
                           report_count=2, detail={}))
        s.add(Incident(signature="health:other", severity="P1", summary="single", detail={}))
    with db.session() as s:
        closed = L.close_duplicates(s)
    assert len(closed) == 2 and {c["duplicate_of"] for c in closed} == {1}, closed
    with db.session() as s:
        rows = list(s.scalars(select(Incident).order_by(Incident.id)))
        assert rows
        assert not rows[0].resolved and rows[0].report_count == 6
        assert all(r.resolved and r.detail["resolved_at"] and "duplicate of incident #1"
                   in r.detail["resolution"] for r in rows[1:3])
        assert not rows[3].resolved
        total = s.scalar(select(func.count()).select_from(Incident))
    assert total == 4, "closing by rule never deletes"
    ok("duplicate signatures close into the oldest row; nothing deleted")


def test_failed_cadence_closes_when_it_enqueues_again():
    db = _plain_db()
    then = datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc)
    with db.session() as s:
        s.add(Incident(signature="scheduler.cadence_failed:nightly", severity="P2",
                       summary="x", detail={"job_type": "improve.nightly"}, at=then))
        s.add(Incident(signature="scheduler.cadence_failed:weekly", severity="P2",
                       summary="y", detail={"job_type": "improve.weekly"}, at=then))
        s.add(Job(agent="orchestrator", job_type="improve.nightly", inputs={},
                  idempotency_key="k1", created_at=then + timedelta(hours=1)))
        s.add(Job(agent="orchestrator", job_type="improve.weekly", inputs={},
                  idempotency_key="k2", created_at=then - timedelta(hours=1)))
    with db.session() as s:
        closed = L.close_recovered_cadences(s)
    assert closed == ["scheduler.cadence_failed:nightly"], closed
    ok("a failed cadence closes once it enqueues after the failure; one that has not stays")


def test_health_sweep_runs_hygiene():
    from brambleloop.ops import truth

    db = _plain_db()
    with db.session() as s:
        s.add(Incident(signature="dependency:x", severity="P2", summary="a", detail={}))
        s.add(Incident(signature="dependency:x", severity="P2", summary="b", detail={}))
    out = truth.sweep(db)
    assert "incident_hygiene" in out and "error" not in out["incident_hygiene"], out
    assert len(out["incident_hygiene"]["duplicates"]) == 1, out["incident_hygiene"]
    ok("ops.health truth sweep closes duplicates by rule")


def test_backlog_close_carries_resolved_at():
    from brambleloop.ops import artefacts

    db = _plain_db()
    with db.session() as s:
        s.add(Incident(signature=f"{artefacts.SENTINEL_SIGNATURE}:backlog", severity="P3",
                       summary="275 derived artefact(s)", detail={"unproven": 275}))
    with db.session() as s:
        artefacts.sweep(s, current={}, expected=[])
    with db.session() as s:
        row = s.scalar(select(Incident))
        assert row.resolved and row.detail.get("resolved_at"), row.detail
    ok("the provenance backlog closes with resolved_at when nothing is unproven")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert tests
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(RESULTS)} passed, {failed} failed")
    sys.exit(1 if failed else 0)
