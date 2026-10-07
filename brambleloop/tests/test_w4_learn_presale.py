"""Wave-4 lane LEARN: the improvement system's zeros, made true, and what moves before a sale.

Hermetic: no network, no model, no secret. See research/final_build/w4/LEARN_DIAGNOSIS.md.

* the runtime cell and the failure miner read only DEFECT dead letters -- a shadow-mode
  refusal is a gate working, and was being counted as a dead letter and mined as a defect;
* the internal pre-sale outcomes are measured from rows, UNMEASURED (never 0) when their
  source is empty, labelled internal, and recorded once per change;
* a routed lesson changes a downstream decision (the Learn review calendar), the change is
  what is recorded as acted on, and with no lesson the decision is unchanged.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from brambleloop.core.db import Database  # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
SHADOW_REFUSAL = ("capability not enabled: store.publish is a production capability; the "
                  "system is in SHADOW mode and has no live Etsy connection.")


def _db(name="w4learn.db"):
    td = tempfile.mkdtemp(prefix="w4learn_")
    db = Database("sqlite:///" + str(Path(td) / name), scratch=True)
    db.create_all()
    return db


def _jobs(db, rows):
    from brambleloop.core.models import Job, JobStatus
    with db.session() as s:
        for job_type, status, error in rows:
            s.add(Job(agent="a", job_type=job_type, status=getattr(JobStatus, status),
                      inputs={}, last_error=error, created_at=NOW - timedelta(days=2)))


# ---- contamination ---------------------------------------------------------------------------


def test_runtime_cell_counts_defect_dead_letters_only():
    from brambleloop.improve import measure
    db = _db()
    _jobs(db, [("store.publish", "DEAD", SHADOW_REFUSAL)] * 3 + [("listing.seo", "DONE", None)])
    m = measure.measure_runtime(db, now=NOW)
    assert isinstance(m, measure.Measurement)
    assert m.value == 0.0, m          # three shadow refusals are not three failures
    assert m.detail["dead_letters_by_kind"] == {"refused": 3}
    _jobs(db, [("assets.render", "DEAD", "RenderError: frame 3 empty")])
    m = measure.measure_runtime(db, now=NOW)
    assert m.detail["dead"] == 1 and m.value > 0   # a real failure is still counted
    db.engine.dispose()


def test_mine_publishes_no_lesson_for_a_shadow_refusal():
    from brambleloop.improve import bus, mine
    db = _db()
    _jobs(db, [("store.publish", "DEAD", SHADOW_REFUSAL)] * 3)
    out = mine.mine(db)
    assert out["found"] == 0 and out["dead"] == 0 and out["dead_not_defects"] == 3, out
    assert bus.compounding(db)["lessons"] == 0
    _jobs(db, [("assets.render", "DEAD", "RenderError: frame 3 empty")])
    out = mine.mine(db)
    assert out["found"] == 1 and out["published"], out
    assert out["published"][0]["evidence_ref"].startswith("dead:assets.render")
    db.engine.dispose()


# ---- post-launch ingestion paths (verified with fixture rows; no customer exists) ------------


def _sales(db, rows):
    """rows: (receipt_ref, product_slug or None, gross). A fixture sale, never a real one."""
    from brambleloop.core.models import Customer, LedgerEntry, Order
    with db.session() as s:
        cust = Customer(customer_ref="fixture-customer")
        s.add(cust)
        s.flush()
        for ref, slug, gross in rows:
            s.add(LedgerEntry(at=NOW - timedelta(days=10), category="sale", gross_cad=gross,
                              evidence_ref=ref, source="fixture", basis="measured"))
            if slug:
                s.add(Order(customer_id=cust.id, external_ref=ref, product_slug=slug,
                            at=NOW - timedelta(days=10), revenue_cad=gross))


def test_portfolio_attributes_revenue_to_the_order_product_not_the_receipt():
    from brambleloop.improve import measure
    db = _db()
    _sales(db, [("etsy:receipt:1", "basket", 10.0), ("etsy:receipt:2", "basket", 10.0),
                ("etsy:receipt:3", "coaster", 5.0), ("etsy:receipt:4", None, 50.0)])
    m = measure.measure_portfolio(db, now=NOW)
    assert isinstance(m, measure.Measurement), m
    # Two products, basket holds 20 of 25 attributed: 0.8. Grouped by receipt it read 0.4.
    assert m.value == 0.8 and m.detail["products"] == 2
    assert m.detail["unattributed_sales"] == 1          # never guessed
    db.engine.dispose()


def test_finance_reads_the_forecasts_the_company_actually_records():
    from brambleloop.core.models import OperatingReading
    from brambleloop.improve import measure
    from brambleloop.scale.evidence import FORECAST_KIND
    db = _db()
    _sales(db, [("etsy:receipt:1", "basket", 30.0)])
    out = measure.measure_finance(db, now=NOW)
    assert isinstance(out, measure.NotMeasured) and out.reason.startswith("data-gated"), out
    sale_day = (NOW - timedelta(days=10)).date()
    start = sale_day - timedelta(days=sale_day.weekday())
    with db.session() as s:
        s.add(OperatingReading(kind=FORECAST_KIND, period_key=start.isoformat(),
                               payload={"period_start": start.isoformat(),
                                        "period_end": (start + timedelta(days=6)).isoformat(),
                                        "made_on": (start - timedelta(days=7)).isoformat(),
                                        "revenue_cad": 40.0, "terms": {}}))
    m = measure.measure_finance(db, now=NOW)
    assert isinstance(m, measure.Measurement), m
    assert m.value == 0.25 and m.sample == 1 and m.detail["source"].startswith("scale.forecast")
    db.engine.dispose()


# ---- pre-sale internal outcomes --------------------------------------------------------------


def test_presale_readings_are_unmeasured_not_zero_on_an_empty_database():
    from brambleloop.improve import presale
    db = _db()
    r = presale.readings(db)
    assert set(r) == set(presale.METRICS) and r
    for metric, v in r.items():
        assert v["reading"] == "UNMEASURED" and v["value"] is None and v["why"], metric
        assert v["customer_outcome"] is False
    db.engine.dispose()


def _seed_presale(db):
    from brambleloop.core.models import AuditLog, Job, JobStatus, ListingAsset, ListingSearchProfile
    with db.session() as s:
        for slug, ok in (("a", True), ("b", False), ("c", True)):
            s.add(AuditLog(actor="gate", action="gate.certified" if ok else "gate.blocked",
                           artifact=f"{slug}@1.0.0", detail={"granted": ok}))
        s.add(AuditLog(actor="gate", action="gate.certified", artifact="b@1.0.0",
                       detail={"granted": True}))           # recertified: not a first pass
        s.add(AuditLog(actor="gate", action="gate.listing_copy_refused", artifact="c@1.0.0",
                       detail={}))
        s.add(AuditLog(actor="cd", action="creative.tournament",
                       detail={"field": {"generated": 10}, "survivors": [{}, {}]}))
        for i, blocked in enumerate((False, False, False, True)):
            s.add(ListingAsset(product_slug="a", version="1.0.0", position=i + 1,
                               asset_class="INFOGRAPHIC", role=f"r{i}", approved=not blocked,
                               blocked_reasons=["thumbnail unreadable"] if blocked else []))
        for slug, verdict in (("a", "REFUSED"), ("c", "PASS")):
            s.add(ListingSearchProfile(product_slug=slug, version="1.0.0", verdict=verdict,
                                       category_status="UNKNOWN" if verdict != "PASS"
                                       else "CERTIFIED"))
        s.add(AuditLog(actor="store", action="store.release_gates", artifact="a",
                       detail={"slug": "a", "blocks_release": True,
                               "reasons": ["search certificate (F-005): category UNKNOWN"]}))
        s.add(AuditLog(actor="store", action="store.release_gates", artifact="c",
                       detail={"slug": "c", "blocks_release": False, "reasons": []}))
        s.add(Job(agent="v", job_type="cir.compile", status=JobStatus.DONE,
                  inputs={"cir": {"slug": "a"}}, created_at=NOW - timedelta(hours=3)))
        s.add(Job(agent="s", job_type="store.publish", status=JobStatus.DEAD,
                  inputs={"slug": "a"}, last_error=SHADOW_REFUSAL,
                  created_at=NOW - timedelta(hours=1)))


def test_presale_readings_are_measured_from_rows():
    from brambleloop.improve import presale
    db = _db()
    _seed_presale(db)
    r = presale.readings(db)
    assert r["gate_first_pass_rate"]["value"] == round(2 / 3, 4)
    assert r["product_truth_refusal_rate"]["value"] == round(1 / 3, 4)
    assert r["creative_survival_rate"]["value"] == 0.2
    assert r["render_qa_block_rate"]["value"] == 0.25
    assert r["render_qa_block_rate"]["detail"]["blocked_by_group"] == {"INFOGRAPHIC/r3": 1}
    assert r["seo_certificate_pass_rate"]["value"] == 0.5
    assert r["release_gate_pass_rate"]["value"] == 0.5
    assert r["release_gate_pass_rate"]["detail"]["release_ready"] == ["c"]
    assert r["time_to_publish_request_hours"]["value"] == 2.0
    # c is release-ready but has no actual CostEntry: cost is unknown, never CA$0.
    cost = r["cost_per_release_ready_cad"]
    assert cost["reading"] == "UNMEASURED" and cost["value"] is None and "not CA$0" in cost["why"]
    measured = [v for v in r.values() if v["reading"] == "MEASURED"]
    assert measured
    for v in measured:
        assert v["kind"] == presale.KIND and v["customer_outcome"] is False and v["sample"] > 0
    db.engine.dispose()


def test_presale_cost_reads_actual_cost_entries_only():
    from brambleloop.core.models import CostEntry
    from brambleloop.improve import presale
    db = _db()
    _seed_presale(db)
    with db.session() as s:
        s.add(CostEntry(agent="render", product_slug="c", amount_cad=1.5,
                        purpose="render model call"))
        s.add(CostEntry(agent="render", product_slug="a", amount_cad=9.0,
                        purpose="not release-ready; not counted"))
    cost = presale.readings(db)["cost_per_release_ready_cad"]
    assert cost["reading"] == "MEASURED" and cost["value"] == 1.5, cost
    db.engine.dispose()


def test_presale_record_is_idempotent_and_movement_is_directional():
    from brambleloop.core.models import AuditLog, ListingAsset
    from brambleloop.improve import measure, presale
    db = _db()
    _seed_presale(db)
    first = measure.record_all(db)["presale"]
    assert first["recorded"] is True and "render_qa_block_rate" in first["measured"]
    again = presale.record(db)
    assert again["recorded"] is False            # same rows, same reading: not re-recorded
    with db.session() as s:
        s.add(ListingAsset(product_slug="c", version="1.0.0", position=9,
                           asset_class="DIGITAL_TWIN_RENDER", role="hero", approved=False,
                           blocked_reasons=["drape mismatch"]))
    assert presale.record(db)["recorded"] is True
    move = presale.movement(db)
    assert move["render_qa_block_rate"]["direction"] == "regressed", move
    assert move["gate_first_pass_rate"]["direction"] == "flat"
    from sqlalchemy import func, select
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog)
                        .where(AuditLog.action == presale.ACTION)) == 2
    db.engine.dispose()


def test_provider_carries_cells_lessons_and_presale():
    from brambleloop.improve import cells
    from brambleloop.learn import improvement_status
    db = _db()
    _seed_presale(db)
    out = improvement_status.summary(db)
    assert out["cells"]["cells"] == len(cells.CELLS)
    assert set(out["cells"]["post_launch_only"]) == {
        "pricing", "customer_experience", "portfolio", "finance", "growth"}
    assert out["presale"]["measured"] >= 6 and out["presale"]["customer_outcome"] is False
    db.engine.dispose()


# ---- a lesson changes a downstream decision --------------------------------------------------


def _gaps(db):
    from brambleloop.learn.models import LearnGap
    with db.session() as s:
        # Evidence-only order: gauge (3 sources), magic_ring (2), colour_change (1).
        s.add(LearnGap(topic="technique:gauge", state="QUEUED", evidence=[{"x": 1}, {"x": 2},
                                                                          {"x": 3}]))
        s.add(LearnGap(topic="technique:magic_ring", state="QUEUED",
                       evidence=[{"x": 1}, {"x": 2}]))
        s.add(LearnGap(topic="technique:colour_change", state="QUEUED", evidence=[{"x": 1}]))


def _order(db):
    from brambleloop.learn.metrics import calendar
    return [slot["topic"] for slot in calendar(db, now=NOW)["slots"]]


def test_without_a_lesson_the_calendar_is_evidence_ordered_and_nothing_is_acted_on():
    from brambleloop.improve import bus
    from brambleloop.learn.metrics import calendar
    db = _db()
    _gaps(db)
    assert _order(db) == ["technique:gauge", "technique:magic_ring", "technique:colour_change"]
    assert calendar(db, now=NOW)["lesson_moves"] == []
    assert bus.compounding(db)["acted_on"] == 0
    db.engine.dispose()


def test_defect_lesson_moves_the_matching_gap_and_is_recorded_acted_on():
    from brambleloop.agents.registry import Registry
    from brambleloop.improve import bus
    from brambleloop.learn import runtime  # noqa: F401 - registers learn.scan
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker
    db = _db()
    _gaps(db)
    assert "learn" in bus.route_for("defect")
    lesson = bus.publish(db, origin_cell="quality", subject="defect",
                         statement=("The certificate chain refused 3 time(s) on hexagon-coaster-"
                                    "set for 'colour change row count mismatch'. A refusal "
                                    "repeated at the same code is a defect upstream"),
                         evidence_ref="gate.blocked:colour change row count mismatch")
    # A lesson that names only one word of a two-word topic is not about it.
    bus.publish(db, origin_cell="quality", subject="defect",
                statement="The magic number of retries was exceeded on render jobs twice today",
                evidence_ref="dead:x:magic")
    assert _order(db) == ["technique:colour_change", "technique:gauge",
                          "technique:magic_ring"]
    Registry(db).seed_defaults()
    JobQueue(db).enqueue("learn", "learn.scan", {})
    worker = Worker(db, job_types=["learn.scan"])
    assert worker.run_once() and worker.stats.completed == 1, worker.stats
    comp = bus.compounding(db)
    assert comp["acted_on"] == 1 and comp["routed"] == 2, comp
    from brambleloop.core.models import Lesson
    with db.session() as s:
        acted = s.get(Lesson, lesson).acted_on_by
    assert acted and acted[0]["cell"] == "learn"
    assert "colour_change from rank 3 to 1" in acted[0]["how"], acted
    # Idempotent: a second scan does not record the same action twice.
    JobQueue(db).enqueue("learn", "learn.scan", {}, idempotency_key="second-scan")
    assert worker.run_once()
    assert bus.compounding(db)["acted_on"] == 1
    db.engine.dispose()


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    assert tests
    failed = 0
    for test in tests:
        try:
            test()
            print("OK  ", test.__name__)
        except Exception as exc:  # noqa: BLE001
            import traceback
            failed += 1
            print("FAIL", test.__name__, type(exc).__name__, exc)
            traceback.print_exc()
    print(len(tests) - failed, "passing,", failed, "failing")
    sys.exit(1 if failed else 0)
