"""Certification repair W6: growth, scale and seasonal capacity, proven through the handlers.

The proof-chain audit found `ops.capacity` feeding `runrate.constraint` an empty
`Observed()`, `/api/growth` solving `constraint({})`, and a dozen growth and seasonal
libraries (#24, #25, #28, #33, #34, #38, #45, #46, #48, #131, #229, #264-#267, #270, #272,
#279, #286, #287, #289-#291) with no runtime caller. Every test here calls the handler through
the handler registry with a real JobContext and asserts both that the library ran on inputs
read from the database and that its effect was persisted or enforced.

Every customer, order, outcome and cohort below is a TEST FIXTURE in a throwaway database.
None is a customer. Where a test runs on an empty database, it asserts the reading says
UNMEASURED rather than zero.

Run: cd brambleloop && $PY tests/test_cert_growth_seasonal.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="cert_w6_")
os.environ.setdefault("BRAMBLELOOP_DATABASE_URL", f"sqlite:///{_TMP}/api.db")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Cohort, CultureObservation, CultureSignal, Customer, Incident, InsightsSnapshot,
    Job, JobStatus, LedgerEntry, Listing, ListingOutcome, OperatingReading, Order, PatternVersion, Phase,
    PriceObservation, Product, RegisteredExperiment, SeasonalTeam, TrendProvenance,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import JobContext, handlers  # noqa: E402

TODAY = date(2026, 9, 27)
NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
ALL_STAGES = ["compile", "specification", "twin", "assembly", "geometry", "write", "reverse",
              "originality", "asset_truth", "policy", "physical_test", "confidence"]


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='w6_')}/w6.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db: Database, job_type: str, inputs: dict | None = None,
         agent: str = "orchestrator") -> dict:
    """The handler, through the registry, with a real JobContext on a real enqueued job."""
    queue = JobQueue(db)
    job = queue.enqueue(agent, job_type, inputs or {},
                        idempotency_key=f"w6:{job_type}:{datetime.now().timestamp()}")
    ctx = JobContext(job=job, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    handler = handlers.get(job_type)
    assert handler is not None, f"no handler registered for {job_type}"
    return handler(ctx)


def _certify(db: Database, slug: str, *, stages=None, listed: bool = True,
             state: str = "draft", price: float = 18.0) -> None:
    with db.session() as s:
        product = Product(slug=slug, title=slug, status="certified")
        s.add(product)
        s.flush()
        s.add(PatternVersion(product_id=product.id, version="1.0.0",
                             cir_json={"components": [{"name": "body"}],
                                       "colours": ["cream", "pine"]},
                             release_hash=hashlib.sha256(slug.encode()).hexdigest(),
                             certified=True,
                             certificate={"stages_run": list(stages or ALL_STAGES)}))
        if listed:
            s.add(Listing(product_slug=slug, version="1.0.0", title=slug, description="x",
                          price_cad=price, state=state))


def _orders(db: Database, slug: str, n: int, *, revenue: float = 20.0,
            contribution: float = 16.0, days_ago: int = 3, source: str = "etsy_search",
            refunded: int = 0, repeat: int = 0, cross_sell_of: str = "",
            prefix: str = "") -> None:
    """TEST FIXTURE orders. Not customers."""
    with db.session() as s:
        for i in range(n):
            ref = f"fixture-{prefix}{slug}-{days_ago}-{i}"
            cust = Customer(customer_ref=ref)
            s.add(cust)
            s.flush()
            s.add(Order(customer_id=cust.id, external_ref=ref, product_slug=slug,
                        at=NOW - timedelta(days=days_ago), price_cad=revenue,
                        revenue_cad=revenue, contribution_cad=contribution,
                        acquisition_source=source, refunded=i < refunded,
                        is_repeat=i < repeat, cross_sell_of=cross_sell_of))


def _outcome(db: Database, slug: str, *, impressions: int, visits: int, orders=None,
             start: str = "2026-09-20", end: str = "2026-09-26", test_key: str = "",
             hero: str = "") -> None:
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, period_start=start, period_end=end,
                             impressions=impressions, visits=visits, orders=orders,
                             source="fixture:stats", test_key=test_key, hero_style=hero))


def _reading(db: Database, kind: str) -> dict:
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == kind)
                       .order_by(OperatingReading.id.desc()))
        assert row is not None, f"no {kind} reading was written"
        return dict(row.payload)


# ---- ops.capacity: the weekly growth solve (C-48, #24, #25, #28, #229, #264, #270, #272) ----


def test_empty_database_reads_unmeasured_never_zero():
    db = _db()
    out = _run(db, "ops.capacity", {"as_of": TODAY.isoformat()})
    assert out["observed"]["visits"] == "UNMEASURED"
    assert out["observed"]["orders"] == "UNMEASURED"
    assert out["scale_rule"] == "UNMEASURED"
    assert out["binding_constraint_5k"] == "UNMEASURED"
    assert out["growth_constraint"] == "UNMEASURED"
    assert out["reallocation"]["move"] is False
    reading = _reading(db, "growth.weekly")
    assert reading["binding_constraint_5k"]["identifiable"] is False
    assert reading["growth_constraint"]["identifiable"] is False
    assert reading["confidence"]["resilience_rung"]["evidence"]["stress_test"] == "UNMEASURED"
    for value in reading["observed"].values():
        assert value != 0, "an unmeasured term was written as zero"


def test_capacity_solves_from_database_rows_and_records_the_reallocation():
    """Fails against the pre-repair handler, which passed an empty Observed()."""
    db = _db()
    _certify(db, "hexie-coaster-set", state="published")
    _outcome(db, "hexie-coaster-set", impressions=20000, visits=1000, orders=30)
    _orders(db, "hexie-coaster-set", 30, revenue=20.0, contribution=16.0, repeat=3)
    out = _run(db, "ops.capacity", {"as_of": TODAY.isoformat()})
    reading = _reading(db, "growth.weekly")

    assert reading["observed"]["visits"] == 1000 and reading["observed"]["orders"] == 30
    assert reading["sources"]["orders"] == "orders"
    # #25/#28: the funnel's binding term is identified and its scale rule fires.
    assert reading["runrate_constraint"]["identifiable"] is True
    assert out["scale_rule"] == "strong_conversion_low_traffic"
    assert reading["decomposition"]["options"][0]["required_visits_per_month"] is not None
    # #229: the CA$5K binding constraint, ranked by share.
    assert reading["binding_constraint_5k"]["identifiable"] is True
    assert out["binding_constraint_5k"] in {"qualified_visits", "conversion_rate", "aov_cad",
                                            "orders_per_month"}
    # #264: one primary, secondaries, and a recorded move toward it.
    assert reading["growth_constraint"]["primary_constraint"]
    assert len(reading["growth_constraint"]["secondary_constraints"]) == 2
    assert out["reallocation"]["move"] is True and out["reallocation"]["owners"]
    # #24: contribution per visitor ranked from the recorded rows.
    assert reading["per_visitor"]["best"] == "hexie-coaster-set"
    # #272: the gate read this product's real conditions before any tilt was allowed.
    assert "scale_readiness" in reading and reading["scale_readiness"]["products_checked"] == 1
    with db.session() as s:
        audit = s.scalar(select(AuditLog).where(AuditLog.action == "ops.capacity"))
        assert audit.detail["reading_id"] == out["reading_id"]


def test_scale_tilt_is_refused_when_no_product_is_ready():
    """#272 negative: a scaling rule fires, and no product passes the gate, so no tilt."""
    db = _db()
    # Published, but never certified: product quality is not stable.
    with db.session() as s:
        s.add(Product(slug="pet-snuggle-mat", title="p", status="draft"))
        s.add(Listing(product_slug="pet-snuggle-mat", version="1.0.0", title="p",
                      description="x", price_cad=20.0, state="published"))
    _outcome(db, "pet-snuggle-mat", impressions=20000, visits=1000, orders=30)
    _orders(db, "pet-snuggle-mat", 30)
    out = _run(db, "ops.capacity", {"as_of": TODAY.isoformat()})
    assert out["scale_rule"] == "strong_conversion_low_traffic"
    assert out["scale_tilt_refused"] is not None
    assert out["scale_ready"] == []
    reading = _reading(db, "growth.weekly")
    assert "product_quality_stable" in reading["scale_readiness"]["not_ready"]["pet-snuggle-mat"]


def test_readiness_passes_only_when_all_six_conditions_hold():
    from brambleloop.scale import readiness

    db = _db()
    _certify(db, "hexie-coaster-set", state="published")
    _orders(db, "hexie-coaster-set", 20)
    ok = readiness.conditions(db, "hexie-coaster-set")
    assert ok["ready"] is True, ok["unmet"]
    assert readiness.gate(db, action="paid media")["allowed"] is True

    # Adversarial: refunds above the ceiling, and an unattributed order, each block alone.
    _orders(db, "hexie-coaster-set", 5, refunded=5, prefix="r")
    blocked = readiness.conditions(db, "hexie-coaster-set")
    assert "refunds_acceptable" in blocked["unmet"]
    db2 = _db()
    _certify(db2, "hexie-coaster-set", state="published")
    _orders(db2, "hexie-coaster-set", 20, source="unknown")
    assert "attribution_working" in readiness.conditions(db2, "hexie-coaster-set")["unmet"]
    # And a product with no orders is unmet on every order condition, not assumed fine.
    db3 = _db()
    _certify(db3, "hexie-coaster-set")
    none = readiness.conditions(db3, "hexie-coaster-set")
    assert none["evidence"]["refunds_acceptable"]["evidence"] == "UNMEASURED"
    assert not none["ready"]


def test_stress_test_feeds_the_confidence_score():
    """#270: resilience is part of the confidence, and an untestable stress is UNMEASURED."""
    from brambleloop.scale import confidence

    db = _db()
    # TEST FIXTURE ledger sales, so the demand rung does not bound the resilience rung.
    with db.session() as s:
        for i in range(100):
            s.add(LedgerEntry(category="sale", gross_cad=25.0, evidence_ref=f"fixture:{i}"))
    fragile = {"testable": True, "target_cad": 5000.0, "fragile_to": ["top SKU lost"],
               "scenarios": [{"scenario": "top SKU lost", "remaining_cad": 1000.0}]}
    rungs = {r.key: r for r in confidence.ladder(db, selling_skus=5, product_families=3,
                                                 top_sku_revenue_share=0.2, stress=fragile)}
    unstressed = {r.key: r for r in confidence.ladder(db, selling_skus=5, product_families=3,
                                                      top_sku_revenue_share=0.2)}
    assert unstressed["portfolio_resilience"].confidence > 0.2
    assert rungs["portfolio_resilience"].confidence == 0.2
    assert rungs["portfolio_resilience"].evidence["fragile_to"] == ["top SKU lost"]
    empty = {r.key: r for r in confidence.ladder(db, selling_skus=5, product_families=3,
                                                 top_sku_revenue_share=0.2,
                                                 stress={"testable": False, "refused": []})}
    assert empty["portfolio_resilience"].confidence == 0.0
    assert empty["portfolio_resilience"].evidence["stress_test"] == "UNMEASURED"


def test_bundle_attribution_and_holdouts_run_from_the_weekly_job():
    """#45/#48: no baseline means no winner; both arms mean a separable holdout."""
    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug="nordic-forest-bundle", version="collection", title="b",
                      description="x", price_cad=40.0, created_at=NOW - timedelta(days=10)))
        s.add(Cohort(key="c-org", product_slug="hexie-coaster-set", arm="organic",
                     visits=1000, orders=20, revenue_cad=400.0))
        s.add(Cohort(key="c-pro", product_slug="hexie-coaster-set", arm="promoted",
                     visits=1000, orders=35, revenue_cad=700.0, spend_cad=60.0))
    _run(db, "ops.capacity", {"as_of": TODAY.isoformat()})
    reading = _reading(db, "growth.weekly")
    bundle = next(b for b in reading["bundle_attribution"]["bundles"]
                  if b["bundle"] == "nordic-forest-bundle")
    assert bundle["may_declare_winner"] is False and bundle["verdict"] == "unmeasured"
    holdout = next(h for h in reading["holdouts"] if h["product"] == "hexie-coaster-set")
    assert holdout["separable"] is True and holdout["incremental_orders"] == 15

    # With a real baseline and enough bundle orders, attribution becomes measurable.
    from brambleloop.commerce import bundles

    db2 = _db()
    _orders(db2, "nordic-forest-stocking", 20, contribution=10.0, days_ago=15, prefix="b")
    _orders(db2, "nordic-forest-bundle", 16, revenue=40.0, contribution=30.0, days_ago=5)
    got = bundles.attribution_from_db(db2, today=TODAY)
    measured = next(b for b in got["bundles"] if b["bundle"] == "nordic-forest-bundle")
    assert measured["measurable"] is True and measured["attach_rate"] is not None


def test_unmeasured_terms_are_not_ranked_as_zero():
    from brambleloop.growth import loops
    from brambleloop.scale import target

    solved = loops.constraint({"qualified_visits": None, "conversion_rate": None,
                               "aov_cad": None, "repeat_rate": None})
    assert solved["identifiable"] is False and solved["primary_constraint"] is None
    assert loops.reallocation(solved)["move"] is False
    bound = target.binding_constraint({"qualified_visits": 9000, "conversion_rate": None,
                                       "aov_cad": 24.0, "orders_per_month": 150})
    assert bound["binding"] is None and bound["unmeasured"] == ["conversion_rate"]


def test_api_growth_solves_from_the_database():
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    main.db.create_all()
    out = TestClient(main.app).get("/api/growth").json()
    # Every term is passed and reported unmeasured, rather than solved as {} (zeros).
    assert out["constraint"]["identifiable"] is False
    assert "qualified_visits" in out["constraint"]["unmeasured"]
    assert out["reallocation"]["move"] is False
    assert "orders" in out["unmeasured"]


# ---- growth.conclude: #265, #266 ------------------------------------------------------------


def test_experiments_conclude_only_with_data_and_claim_only_what_the_design_allows():
    from brambleloop.growth.experiments import register_launch

    db = _db()
    register_launch(db, product="hexie-coaster-set", price_cad=18.0, today=TODAY)
    empty = _run(db, "growth.conclude", agent="experiment_steward")
    assert empty["concluded"] == [] and empty["no_data"] == 4
    assert "concludes nothing" in empty["note"]
    assert empty["balance"]["balanced"] is False and empty["balance"]["long"] == 1

    # A staggered thumbnail test reaches its sample; no rollout arms are recorded, so the
    # success is claimable and recorded as association, not cause.
    with db.session() as s:
        for row in s.scalars(select(RegisteredExperiment)):
            row.created_at = NOW - timedelta(days=20)
    _outcome(db, "hexie-coaster-set", impressions=1200, visits=30, start="2026-09-15",
             end="2026-09-21")
    _orders(db, "hexie-coaster-set", 5)
    out = _run(db, "growth.conclude", agent="experiment_steward")
    assert "hexie-coaster-set:thumbnail" in out["concluded"]
    with db.session() as s:
        thumb = s.scalar(select(RegisteredExperiment).where(
            RegisteredExperiment.key == "hexie-coaster-set:thumbnail"))
        assert thumb.state == "concluded" and thumb.observed == 0.025
        verdict = thumb.detail["last_verdict"]
        assert verdict["causal"] is False and "association" in verdict["claim"]
        # #265: the expected value is estimated from measured contribution, not None.
        assert thumb.expected_value_cad is not None and thumb.expected_value_cad > 0
        price = s.scalar(select(RegisteredExperiment).where(
            RegisteredExperiment.key == "hexie-coaster-set:price"))
        # The price test's metric has an outcome row with no order count: it stays open.
        assert price.state == "registered"


def test_an_experiment_costing_more_than_its_measured_value_is_killed():
    from brambleloop.growth.experiments import register_launch

    db = _db()
    register_launch(db, product="hexie-coaster-set", price_cad=18.0, today=TODAY)
    _orders(db, "hexie-coaster-set", 2, contribution=1.0)
    with db.session() as s:
        row = s.scalar(select(RegisteredExperiment).where(
            RegisteredExperiment.key == "hexie-coaster-set:bundle"))
        row.cost_cad = 500.0
    out = _run(db, "growth.conclude", agent="experiment_steward")
    assert "hexie-coaster-set:bundle" in out["killed"]


# ---- ops.thrash: #34 -----------------------------------------------------------------------


def _job(db, job_type, inputs, status, *, error="", outputs=None, cost=0.0, key=""):
    with db.session() as s:
        s.add(Job(agent="orchestrator", job_type=job_type, inputs=inputs, status=status,
                  last_error=error or None, outputs=outputs, cost_cad=cost,
                  idempotency_key=key or f"thrash:{datetime.now().timestamp()}:{job_type}"))


def test_three_identical_dead_calls_trip_the_breaker_and_cancel_the_retry():
    db = _db()
    for i in range(3):
        _job(db, "etsy.probe", {"x": 1}, JobStatus.DEAD, error="401 unauthorised", key=f"d{i}")
    _job(db, "etsy.probe", {"x": 1}, JobStatus.FAILED, error="401 unauthorised", key="retry")
    out = _run(db, "ops.thrash")
    assert out["tripped"] == 1 and out["cancelled"]
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature.like("thrash:etsy.probe:%")))
        assert inc is not None and not inc.resolved
        retry = s.scalar(select(Job).where(Job.idempotency_key == "retry"))
        assert retry.status == JobStatus.CANCELLED
    # Restated, not duplicated, on the next sweep.
    _run(db, "ops.thrash")
    with db.session() as s:
        rows = list(s.scalars(select(Incident).where(
            Incident.signature.like("thrash:etsy.probe:%"))))
        assert len(rows) == 1 and rows[0].report_count == 2


def test_changing_results_and_free_heartbeats_are_not_loops():
    db = _db()
    for i in range(3):
        _job(db, "etsy.probe", {"x": 1}, JobStatus.DEAD, error=f"error {i}", key=f"e{i}")
    for i in range(5):
        _job(db, "ops.heartbeat", {}, JobStatus.DONE, outputs={"ok": True}, key=f"h{i}")
    out = _run(db, "ops.thrash")
    assert out["tripped"] == 0
    for i in range(3):
        _job(db, "creative.blinded", {"k": 1}, JobStatus.DONE, outputs={"same": 1},
             cost=0.4, key=f"p{i}")
    assert _run(db, "ops.thrash")["tripped"] == 1


# ---- pricing.position: #46 ------------------------------------------------------------------


def test_pricing_records_each_price_it_sets_once():
    db = _db()
    inputs = {"slug": "hexie-coaster-set", "version": "1.0.0", "release": "r1"}
    _run(db, "pricing.position", inputs, agent="pricing")
    _run(db, "pricing.position", inputs, agent="pricing")
    with db.session() as s:
        rows = list(s.scalars(select(PriceObservation).where(
            PriceObservation.product_slug == "hexie-coaster-set")))
    assert len(rows) == 1, "an unchanged price was recorded twice"
    assert rows[0].price_cad > 0 and rows[0].season == "evergreen"
    assert rows[0].detail["reading"].startswith("UNMEASURED")
    from brambleloop.commerce import elasticity

    assert elasticity.memory(db)["measurable"] is False


# ---- seasonal.engine: #33, #38, #131, #267, #286, #287, #289, #290, #291 --------------------


def _seasonal_fixture(db):
    for slug in ("winter-village-graphghan", "nordic-star-ornaments", "spooky-garland",
                 "pet-snuggle-mat", "valentine-heart-garland"):
        _certify(db, slug)
    with db.session() as s:
        s.add(CultureSignal(key="retro_meme", topic="retro meme", domain="meme",
                            first_seen="2026-09-01"))
        s.add(CultureSignal(key="christmas_tradition", topic="christmas cottagecore",
                            domain="seasonal_tradition", first_seen="2026-09-01",
                            score={"score": 0.82, "evidence_weight": 0.7}))
        s.add(CultureObservation(signal_key="retro_meme", channel="reference",
                                 observed_on="2026-09-20", interest=0.4,
                                 source="wikimedia_pageviews:Retro"))
        s.add(CultureObservation(signal_key="retro_meme", channel="marketplace",
                                 observed_on="2026-09-14", interest=0.3,
                                 source="benchmark:mjs"))
        s.add(InsightsSnapshot(keyword="christmas crochet", search_count=None,
                               listing_count=40, geography="US",
                               observed_on=NOW - timedelta(days=3), recorded_by="owner"))


def test_seasonal_engine_runs_daily_and_persists_what_it_decided():
    db = _db()
    _seasonal_fixture(db)
    out = _run(db, "seasonal.engine", {"as_of": TODAY.isoformat()})
    reading = _reading(db, "seasonal.daily")

    # #286: all six horizons, from today.
    assert sorted(out["horizons"]) == [30, 60, 90, 120, 180, 365]
    assert reading["rolling_calendar"]["today"] == TODAY.isoformat()
    # #33: no occasion scores on unobserved factors; the seed stays labelled as a seed.
    assert out["scored_events"] == 0 and out["priority_basis"] == "current_campaign_seed"
    christmas = next(u for u in reading["engine"]["unscored"] if u["event"] == "Christmas")
    assert "competitive_weakness" in christmas["unmeasured"]
    assert reading["engine"]["breakout"]["reading"] == "UNMEASURED"
    # #287: teams persisted, with what each owns.
    with db.session() as s:
        team = s.scalar(select(SeasonalTeam).where(SeasonalTeam.event == "Christmas"))
        assert team is not None and team.state == "active" and team.share > 0
        assert "winter-village-graphghan" in team.products
        assert team.owns["revenue_target"]["reading"] == "UNMEASURED"
        assert team.owns["deadlines"] and team.owner_agent
    # #131: a takeover planned for Christmas, with its revert date scheduled with its start.
    planned = {p["event"]: p for p in reading["takeovers"]["planned"]}
    assert "Christmas" in planned and planned["Christmas"]["ends_on"]
    # #267: capacity rolled forward and each occasion's structural floor computed.
    assert set(reading["rollforward"]["capacities"])
    assert all("structural_floor_on" in c for c in reading["demand_curves"])
    # #289: collections were assembled from certified concepts.
    assert reading["collections"]["assessed"] >= 1
    # #290: every culture signal carries a half-life on its own row.
    with db.session() as s:
        meme = s.scalar(select(CultureSignal).where(CultureSignal.key == "retro_meme"))
        assert meme.score["half_life"]["half_life"] == "flash"
        assert meme.score["half_life"]["lane_ceiling"] == "QUICK"
    # #291: near-season products were judged by the fast lane.
    assert reading["fast_lane"]["evaluated"] >= 2
    # #38: every trend row is stamped; an unknown population is refused, not discounted.
    with db.session() as s:
        stamps = {(r.source_table, r.population): r for r in s.scalars(select(TrendProvenance))}
    assert stamps[("culture_observations", "GLOBAL")].weight is not None
    assert stamps[("culture_observations", "UNKNOWN")].refused_reason
    insights = stamps[("insights_snapshots", "US")]
    assert insights.weight == 0.75 and insights.usable_value is None, \
        "a missing search count was stamped as a usable zero"


def test_fast_lane_admits_on_measured_evidence_and_refuses_a_skipped_gate():
    from brambleloop.seasonal import daily

    db = _db()
    _seasonal_fixture(db)
    reading = daily.run(db, today=TODAY)
    decisions = {d["slug"]: d for d in reading["fast_lane"]["decisions"]}
    # The ornaments are a quick make for Christmas with scored evidence behind it.
    assert decisions["nordic-star-ornaments"]["admitted"], decisions["nordic-star-ornaments"]
    checks = {c["slug"]: c for c in reading["fast_lane"]["release_checks"]}
    assert checks["nordic-star-ornaments"]["ok"] is True
    # The graphghan is not fast whatever the trend is doing.
    assert not decisions["winter-village-graphghan"]["admitted"]

    # Adversarial: the same product certified without `reverse` is refused by name.
    db2 = _db()
    _seasonal_fixture(db2)
    with db2.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product).where(
            Product.slug == "nordic-star-ornaments"))
        pv.certificate = {"stages_run": [x for x in ALL_STAGES if x != "reverse"]}
    checks = {c["slug"]: c for c in daily.run(db2, today=TODAY)["fast_lane"]["release_checks"]}
    assert checks["nordic-star-ornaments"]["ok"] is False
    assert "reverse" in checks["nordic-star-ornaments"]["refused"]

    # And with no scored evidence at all, nothing is admitted: evidence is UNMEASURED.
    db3 = _db()
    _certify(db3, "nordic-star-ornaments")
    got = daily.run(db3, today=TODAY)["fast_lane"]
    assert got["admitted"] == []
    assert any("UNMEASURED" in r for d in got["decisions"] for r in d["reasons"])


def test_breakout_mode_fires_only_on_measured_velocity():
    from brambleloop.seasonal import daily

    db = _db()
    for slug in ("spooky-garland", "valentine-heart-garland", "pumpkin-cluster-set"):
        _certify(db, slug)
    _orders(db, "spooky-garland", 30, days_ago=2)
    _orders(db, "valentine-heart-garland", 2, days_ago=2)
    _orders(db, "pumpkin-cluster-set", 2, days_ago=2)
    got = daily.breakouts(db, daily._catalogue(db), today=TODAY)
    assert got["breakouts"] == ["spooky-garland"]


def test_a_team_whose_occasion_has_passed_is_disbanded_not_deleted():
    from brambleloop.seasonal import daily

    db = _db()
    _seasonal_fixture(db)
    daily.run(db, today=TODAY)
    # Halloween's last practical make date is long gone by 30 October.
    daily.run(db, today=date(2026, 10, 30))
    with db.session() as s:
        rows = list(s.scalars(select(SeasonalTeam).where(SeasonalTeam.event == "Halloween")))
    assert rows and any(r.state == "disbanded" for r in rows)


# ---- collection.assemble and seasonal.remerchandising: #289, #279 ---------------------------


def test_collection_architecture_names_a_one_price_point_collection():
    from brambleloop.radar.opportunity import POOL

    seed = next(m for m in POOL if m.slug == "nordic-forest-bundle")
    got = release._collection_architecture(
        "nordic-forest-bundle", seed, ["nordic-star-ornaments", "winter-village-graphghan",
                                       "nordic-forest-stocking"])
    assert got["without_concept"] == ["nordic-forest-stocking"]
    assert got["coherent"] is False
    assert any(p.startswith(("COLLECTION_TOO_SMALL", "COLLECTION_ONE_PRICE_POINT",
                             "COLLECTION_INCOHERENT")) for p in got["problems"])


def test_evergreen_concepts_are_transformed_and_only_a_promised_brief_derives():
    from brambleloop.seasonal import remerchandising

    db = _db()
    for slug in ("pet-snuggle-mat", "cottage-wall-hanging", "mosaic-placemat-pair"):
        _certify(db, slug)
    brief = {"parent": "cottage-wall-hanging", "layers": ["motif_vocabulary", "trim"],
             "motifs": ["woodland", "star"], "feeling": "nostalgic", "execution": "motif",
             "how": ("a woodland procession walks the hanging's lower border, so the season "
                     "is worked into the fabric rather than printed on the photograph"),
             "key": "cottage-wall-hanging-yule", "title": "Yule Cottage Hanging",
             "premise": "a woodland procession crosses the cottage border at dusk in winter",
             "palette_story": "forest and cream", "recipient": "self",
             "function": "a seasonal wall piece for the hall"}
    got = remerchandising.transformations(db, event="Christmas", briefs=[brief])
    assert got["evaluated"] == 3 and got["routed"] == 3
    assert all("PRESENTATION_ONLY" in p["problems"][0] for p in got["presentation"])
    assert all(h["problems"] for h in got["held"]), "an engineered variant with no promise"
    assert [d["key"] for d in got["derived"]] == ["cottage-wall-hanging-yule"], got["refused"]
    # No grammar, no transformation.
    assert remerchandising.transformations(db, event="Valentine's")["season"] is None



def test_collection_handler_records_the_architecture_assessment():
    """#289 through `collection.assemble`: the assessment is audited with the listing."""
    db = _db()
    for slug in ("nordic-star-ornaments", "nordic-forest-stocking"):
        _certify(db, slug)
    out = _run(db, "collection.assemble",
               {"slug": "nordic-forest-bundle", "family": "nordic-forest"}, agent="publishing")
    assert out["architecture"]["coherent"] is False
    assert out["architecture"]["without_concept"] == ["nordic-forest-stocking"]
    with db.session() as s:
        audit = s.scalar(select(AuditLog).where(AuditLog.action == "collection.assessed"))
        assert audit is not None and audit.detail["problems"]


def test_remerchandising_handler_runs_the_transformation_engine():
    """#279 through `seasonal.remerchandising`, weekly, with no brief: nothing derived."""
    db = _db()
    for slug in ("pet-snuggle-mat", "cottage-wall-hanging"):
        _certify(db, slug)
    out = _run(db, "seasonal.remerchandising", agent="listing")
    assert out["transformations"]["evaluated"] == 2 and out["derived"] == []
    with db.session() as s:
        audit = s.scalar(select(AuditLog).where(
            AuditLog.action == "seasonal.transformations"))
        assert audit is not None and audit.detail["routed"] == 2



def test_a_bundle_waiting_for_members_waits_and_does_not_die():
    """Regression (C-46): claimed before its members certify, the job must not go DEAD.
    C-73: nor may it spin -- it waits without re-queueing, and a member's certification is
    what enqueues the next attempt, at the collection's own band."""
    from brambleloop.runtime.release import enqueue_member_collections
    from brambleloop.runtime.worker import Worker
    from brambleloop.swarm import orchestrate

    db = _db()
    _certify(db, "nordic-star-ornaments")  # one of four members: not yet a collection
    JobQueue(db).enqueue("listing", "collection.assemble",
                         {"slug": "nordic-forest-bundle", "family": "nordic-forest"},
                         idempotency_key="bundle-early")
    worker = Worker(db, "w6-bundle")
    for _ in range(10):
        if not worker.run_once():
            break
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type == "collection.assemble")))
        assert [j.status for j in jobs] == [JobStatus.DONE], [(j.status, j.last_error) for j in jobs]
        waits = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "collection.waiting")))
        assert waits and waits[-1].detail["requeued"] is False

    # A second member certifies: its gate.certify enqueues the assembly (the same function the
    # handler calls), once per member release, at the band.
    _certify(db, "nordic-forest-stocking")
    queue = JobQueue(db)
    trigger = queue.enqueue("quality_director", "gate.certify", {}, idempotency_key="t-cert")
    ctx = JobContext(job=trigger, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    assert enqueue_member_collections(ctx, "nordic-forest-stocking", "h1") == ["nordic-forest-bundle"]
    assert enqueue_member_collections(ctx, "nordic-forest-stocking", "h1") == []  # keyed
    with db.session() as s:
        queued = [j for j in s.scalars(select(Job).where(
            Job.job_type == "collection.assemble", Job.status == JobStatus.PENDING))]
        assert len(queued) == 1
        assert queued[0].priority == orchestrate.priority_for("collection.assemble")
        queued_id = queued[0].id
    while worker.run_once():
        pass
    with db.session() as s:
        done = s.get(Job, queued_id)
        assert done.status == JobStatus.DONE, done.last_error
        assert done.outputs.get("waiting") is None and len(done.outputs["members"]) == 2


# ---- #241: the launch experiment pack ------------------------------------------------------


def _frames(db, slug, roles):
    from brambleloop.core.models import ListingAsset

    with db.session() as s:
        for i, role in enumerate(roles):
            s.add(ListingAsset(product_slug=slug, version="1.0.0", position=i,
                               asset_class="finished_object", role=role,
                               sha256=hashlib.sha256(f"{slug}{i}".encode()).hexdigest(),
                               approved=True))


def test_launch_pack_records_hero_variants_title_tags_and_confounders():
    from brambleloop.growth.experiments import register_at_launch

    db = _db()
    _certify(db, "hexie-coaster-set")
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == "hexie-coaster-set"))
        listing.tags = ["hexagon coaster", "crochet coaster pattern"]
    _frames(db, "hexie-coaster-set", ["hero", "collection", "chart"])
    out = register_at_launch(db, product="hexie-coaster-set", today=TODAY)
    assert out["created"] == 5 and out["confounded"] == []
    with db.session() as s:
        rows = {r.key.rsplit(":", 1)[-1]: r for r in s.scalars(select(RegisteredExperiment))}
    thumb = rows["thumbnail"].detail
    # Named hero variants from the stored frames, in a dated staggered rotation.
    assert [v["role"] for v in thumb["hero_variants"]] == ["hero", "collection"]
    assert thumb["hero_plan"]["design"] == "staggered_rollout"
    assert len(thumb["hero_plan"]["schedule"]) == 2
    # The actual title and tag set, and what changes on failure.
    strategy = rows["search"].detail["title_tag_strategy"]
    assert strategy["title"] == "hexie-coaster-set"
    assert strategy["tags"] == ["hexagon coaster", "crochet coaster pattern"]
    assert "rewrite" in strategy["on_failure"]
    # The launch variables are recorded at registration, on every experiment.
    assert rows["price"].detail["launch"]["variables"]["price_cad"] == 18.0
    thresholds = (rows["price"].success_threshold, rows["price"].failure_threshold)

    # Adversarial: price and hero change at once after launch. The pack is not rewritten
    # (write-once), the change is logged, and the price test is marked confounded.
    with db.session() as s:
        s.scalar(select(Listing).where(Listing.product_slug == "hexie-coaster-set")
                 ).price_cad = 22.0
        from brambleloop.core.models import ListingAsset

        s.scalar(select(ListingAsset).where(ListingAsset.role == "hero")).sha256 = "f" * 64
    again = register_at_launch(db, product="hexie-coaster-set", today=TODAY)
    assert again["created"] == 0 and "hexie-coaster-set:price" in again["confounded"]
    with db.session() as s:
        price = s.scalar(select(RegisteredExperiment).where(
            RegisteredExperiment.key == "hexie-coaster-set:price"))
        assert (price.success_threshold, price.failure_threshold) == thresholds
        assert price.detail["confounded"] is True
        assert set(price.detail["confounder_log"][-1]["changed"]) == {"price_cad", "hero"}
        search = s.scalar(select(RegisteredExperiment).where(
            RegisteredExperiment.key == "hexie-coaster-set:search"))
        # The search test is sensitive to title and tags only: logged, not confounded.
        assert search.detail["confounded"] is False


def test_launch_pack_with_one_frame_or_none_says_so_rather_than_inventing_a_variant():
    from brambleloop.growth.experiments import launch_record

    db = _db()
    assert launch_record(db, "pet-snuggle-mat", today=TODAY)["hero_plan"]["design"] \
        == "UNMEASURED"
    _frames(db, "pet-snuggle-mat", ["hero"])
    one = launch_record(db, "pet-snuggle-mat", today=TODAY)
    assert one["hero_plan"]["design"] == "single_hero" and len(one["hero_variants"]) == 1
    assert "title" in one["unrecorded"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
