"""W5-A7 (P0-SUPPLY-STALL): an exhausted concept pool is recorded, never silent.

`draft:<slug>` is permanent, so once every concept in POOL (plus approved intake) has been
drafted, `radar.scan` can select nothing new. The real `radar.scan` and `radar.score` handlers
run on a SQLite FILE through `JobQueue` and `Worker.run_once`:

* POOL exhausted: one `radar.supply_stall` reading and one audit per scan date, however many
  scans run that day; a new date is a new period; no duplicate `cir.draft` is queued.
* Selection all drafted while undrafted pool concepts remain: the scan selects the
  undrafted concepts instead (ENG-RECOVERY), so no stall and new drafts are queued.
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


def _free_slots_and_admit(db):
    """Finish the research drafts already made, then run the offer admission pass
    (`supply.admit`, the event refill). Launch-0 seeding (`supply.run`) is a separate decision
    with its own priority rules (test_eng_supply) and is not under test here."""
    from brambleloop.agents.registry import Registry as _Reg
    from brambleloop.products import supply
    from brambleloop.runtime.worker import JobContext

    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "cir.draft")):
            j.status = JobStatus.DONE
    holder = JobQueue(db).enqueue("orchestrator", "supply.admit", {},
                                  idempotency_key="admit-after-free", priority=0)
    ctx = JobContext(job=holder, db=db, queue=JobQueue(db), registry=_Reg(db),
                     phase=Phase.SHADOW)
    out = supply.admit(ctx)
    # ENG-DEMAND-SUPPLY: an offer whose family has no certified engine is named on the
    # engine-demand list instead of admitted. Every offer is accounted for -- admitted or
    # named -- never silently dropped.
    assert out["admitted"] or out.get("engine_demand"), out
    return out


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
        # They promoted, so each one really did try to queue `draft:<slug>` -- and was refused.
        assert any((j.outputs or {}).get("promoted") for j in scored)
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


def test_a_drafted_selection_is_replaced_by_undrafted_pool_concepts():
    """ENG-RECOVERY (prod 2026-11-19, `selection_all_drafted` with 18 undrafted in the pool):
    W5-A7 recorded the stall but the next scan selected the very same drafted concepts, so
    original_product did nothing for a week. The scan now selects from the undrafted pool:
    no stall, a different selection, and the scores it queues reach new `cir.draft` jobs."""
    db = _db("selection")
    first = _scan(db, DAY1, "scan-a")
    assert first["concept_supply"]["stalled"] is False
    _drafted(db, first["selected"])
    before = _drafts(db)
    second = _scan(db, DAY1, "scan-b")
    assert second["selected"] and not set(second["selected"]) & set(first["selected"]), second
    supply = second["concept_supply"]
    assert supply["stalled"] is False and supply["recorded"] is False, supply
    assert supply["undrafted_selected"] == len(second["selected"])
    assert _readings(db) == [] and _audits(db) == []
    _score_all(db)
    new_drafts = sorted(set(_drafts(db)) - set(before))
    assert new_drafts and all(k[len("draft:"):] in second["selected"] for k in new_drafts), \
        new_drafts


# The 16 concepts production had drafted when the review read it (8bc96eef, 2026-11-19).
PRODUCTION_DRAFTED = (
    "autumn-oak-mosaic-throw", "cloudline-baby-blanket", "harvest-table-runner",
    "hexie-coaster-set", "market-basket-trio", "mosaic-placemat-pair",
    "nordic-forest-mosaic-throw", "nordic-star-ornaments", "pet-snuggle-mat",
    "pressed-flower-motifs", "pumpkin-cluster-set", "spooky-garland", "valentine-heart-garland",
    "winter-village-graphghan", "heirloom-cable-blanket", "nordic-forest-bundle")


def test_the_production_drafted_set_drafts_what_can_be_drafted_then_names_the_stall():
    """ENG-RECOVERY fix round 1 (review M1), the reviewer's probe on the real POOL.

    "Select undrafted" made three drafts and then re-selected the same ten every scan --
    eight refused by #88 (a radar slot with no premise or storyboard is not a concept), one
    at 0.544 < 0.55 -- with `stalled=False`. Now every promotable undrafted concept is drafted
    on the first scan, and every later scan reports `selection_unpromotable` with each held
    concept's reason. The gate is not relaxed: no held concept is ever drafted."""
    db = _db("production-drafted")
    pool = [c.slug for c in pool_with_intake(db)]
    assert len(pool) == 34 and set(PRODUCTION_DRAFTED) <= set(pool)
    _drafted(db, PRODUCTION_DRAFTED)
    days = ("2026-11-19", "2026-11-19", "2026-11-20", "2026-11-21")
    outs, made = [], []
    for i, day in enumerate(days):
        before = set(_drafts(db))
        outs.append(_scan(db, day, f"prod-{i}"))
        _score_all(db)
        if i == 0:
            # ENG-SUPPLY: a promoted concept is offered to the capacity-aware admission
            # controller. What fits the WIP limit is drafted now; the rest waits in the
            # supply queue (never dropped), and is drafted when a slot frees.
            from brambleloop.products import supply

            waiting = [o["slug"] for o in supply.offers(db)]
            now_made = {k[len("draft:"):] for k in set(_drafts(db)) - before}
            assert now_made and now_made.isdisjoint(waiting), (now_made, waiting)
            assert now_made | set(waiting) == set(outs[0]["selected"]), (now_made, waiting)
            admitted = _free_slots_and_admit(db)
            demanded = set(admitted.get("engine_demand") or [])
            took = {str(k).split(":", 1)[-1] for k in admitted["admitted"]}
            assert set(waiting) <= took | demanded, (waiting, admitted)
            # An engine-demand concept stays queued (drafted once its engine exists); nothing
            # else is left waiting.
            assert {o["slug"] for o in supply.offers(db)} == demanded, supply.offers(db)
        made.append(sorted(k[len("draft:"):] for k in set(_drafts(db)) - before))
    first = outs[0]
    # continued progress: everything the gate passes is drafted (within capacity, then as
    # slots free)
    # ENG-DEMAND-SUPPLY: a selected concept with no certified engine is engine demand, not a draft.
    assert made[0] and set(made[0]) | demanded == set(first["selected"]), (
        made[0], demanded, first["selected"])
    assert first["concept_supply"]["stalled"] is False
    assert first["concept_supply"]["supply_selected"] == len(made[0]) + len(demanded)
    assert first["selection_pool"] == "promotable_undrafted"
    # L1: the full section-33 pool is reported beside the sub-pool selected from
    assert first["pool_size"] == 34 and first["selection_pool_size"] < 34
    # then the stall is named, not hidden behind a non-empty selection
    for out, new in zip(outs[1:], made[1:]):
        supply = out["concept_supply"]
        assert new == [], new
        assert supply["stalled"] is True and supply["reason"] == "selection_unpromotable", supply
        assert supply["promotable_undrafted"] == 0 and supply["undrafted_pool"] > 0
        # ENG-DEMAND-STALL: a queued concept waiting on an engine is counted apart, never as
        # promotable supply, and is held with its engine reason.
        assert supply["engine_demand_undrafted"] == len(demanded), supply
        held = supply["held"]
        assert all(held[s].startswith("engine_demand:") for s in demanded), held
        assert set(held) == set(pool) - set(PRODUCTION_DRAFTED) - set(made[0]), held
        assert "premise_thumbnail" in held["nordic-forest-stocking"], held
        # D-OWNER-RESEARCH-BAR (2026-11-22): alpine-slouch-beanie (0.544) now clears the 0.45
        # bar with no evidence discount; the #88 gate is what holds it, and it still holds.
        assert "below promotion threshold" not in held["alpine-slouch-beanie"], held
        assert "premise_thumbnail" in held["alpine-slouch-beanie"], held
        assert "Class C" in held["boxy-summer-tee"], held
        assert out["pool_size"] == 34
    # every held concept stays undrafted (#88 and the threshold stand)
    assert not set(_drafts(db)) & {f"draft:{s}" for s in outs[-1]["concept_supply"]["held"]}
    # one reading per scan date, and the supply readback shows the reason
    assert [p for p, _ in _readings(db)] == ["2026-11-19", "2026-11-20", "2026-11-21"]
    got = flow_health.concept_supply_stall(db)
    assert got and got["reason"] == "selection_unpromotable" and got["held"] > 0, got
    assert got["promotable_undrafted"] == 0 and got["pool"] == 34, got


def test_an_engine_demand_concept_drafts_once_its_engine_exists():
    """ENG-DEMAND-STALL: the engine-demand concept is not dropped. It stays queued, the scan
    counts it as `engine_demand_undrafted` (stalled, not supply), and once an engine for it
    is registered the next scan counts it as promotable supply and admission drafts it."""
    from brambleloop.products import supply

    db = _db("engine-arrives")
    _drafted(db, PRODUCTION_DRAFTED)
    _scan(db, "2026-11-19", "ea-0")
    _score_all(db)
    demanded = set(_free_slots_and_admit(db).get("engine_demand") or [])
    assert demanded, "the production pool holds a concept with no certified engine"
    assert {o["slug"] for o in supply.offers(db)} == demanded
    waiting = _scan(db, "2026-11-20", "ea-1")["concept_supply"]
    assert waiting["stalled"] is True and waiting["promotable_undrafted"] == 0, waiting
    assert waiting["engine_demand_undrafted"] == len(demanded), waiting
    assert not {f"draft:{s}" for s in demanded} & set(_drafts(db))
    # Register an engine for the concept (an engineered design under its slug, the path
    # `cir.draft` and `engine_verdict` both read).
    added = {s: f"fx-engine-{s}" for s in demanded if s not in pipeline.ENGINEERED}
    pipeline.ENGINEERED.update(added)
    try:
        assert supply.engine_demand_waiting(db) == {}
        ready = _scan(db, "2026-11-21", "ea-2")["concept_supply"]
        assert ready["engine_demand_undrafted"] == 0, ready
        assert ready["promotable_undrafted"] == len(demanded), ready
        # Automatic: the scan's radar.score re-offers it and the admission pass it triggers
        # (or the next refill) admits it -- no operator step.
        _score_all(db)
    finally:
        for s in added:
            pipeline.ENGINEERED.pop(s, None)
    assert {f"draft:{s}" for s in demanded} <= set(_drafts(db)), _drafts(db)
    assert supply.offers(db) == []


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
