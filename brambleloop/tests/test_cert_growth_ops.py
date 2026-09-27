"""Certification C-60 (C-66, C-70, part of C-67): growth, ads, distribution, customer
experience and scale machinery, proven through the running handlers.

The final function-level audit of 9434c53 found the ads job types granted with no handler,
the distribution and customer-experience libraries reached only by tests, commerce readings
fed hard-coded empty inputs, the confidence model never given its conditions or calibration,
and the weekly reallocation and war-room board read by no agent. Every test here drives a
registered handler (through the worker or the handler registry with a real JobContext and a
real database) and asserts the downstream effect: a reading persisted, an incident opened or
resolved, a job enqueued or re-prioritised, a relationship stopped, a draft refused.

Every customer, order, outcome and roster row below is a TEST FIXTURE in a throwaway
database. None is a customer, and nothing here spends, publishes or sends.

Run: cd brambleloop && $PY tests/test_cert_growth_ops.py
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

_TMP = tempfile.mkdtemp(prefix="cert_growth_ops_")
os.environ.setdefault("BRAMBLELOOP_DATABASE_URL", f"sqlite:///{_TMP}/api.db")
TOKEN = "cert-growth-ops-token-0123456789abcdef"
os.environ["BRAMBLELOOP_OPS_TOKEN"] = TOKEN

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Collaboration, CreatorProfile, Customer, Experiment, Incident, Job, JobStatus,
    LearningObservation, LedgerEntry, Listing, ListingOutcome, OperatingReading, Order,
    OwnerAction, PatternVersion, Phase, PhysicalTest, Product, RegisteredExperiment,
    SpendLimit, SupportCase,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import growth_ops, pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, JobContext, Worker, handlers  # noqa: E402

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
FLAGSHIP = "nordic-forest-mosaic-throw"      # a Christmas seed, 30-60 maker hours


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='gops_')}/g.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _work(db, agent: str, job_type: str, inputs: dict | None = None) -> Job:
    """Enqueue and run one job through the worker, as the scheduler would."""
    job = JobQueue(db).enqueue(agent, job_type, inputs or {},
                               idempotency_key=f"t:{job_type}:{datetime.now().timestamp()}")
    assert Worker(db, "t", phase=Phase.SHADOW, job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _run(db, job_type: str, inputs: dict | None = None, agent: str = "orchestrator") -> dict:
    queue = JobQueue(db)
    job = queue.enqueue(agent, job_type, inputs or {},
                        idempotency_key=f"r:{job_type}:{datetime.now().timestamp()}")
    ctx = JobContext(job=job, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    return handlers.get(job_type)(ctx)


def _certify(db, slug: str, *, published: bool = True, description: str = "",
             tags=("mosaic throw", "christmas blanket", "crochet pattern"),
             created_at: datetime | None = None) -> None:
    with db.session() as s:
        product = Product(slug=slug, title=slug, status="certified")
        s.add(product)
        s.flush()
        s.add(PatternVersion(product_id=product.id, version="1.0.0",
                             cir_json={"components": [{"name": "body"}]},
                             release_hash=hashlib.sha256(slug.encode()).hexdigest(),
                             certified=True, certificate={"stages_run": ["compile"]},
                             created_at=created_at or NOW))
        if published is not None:
            s.add(Listing(product_slug=slug, version="1.0.0", title=f"{slug} crochet pattern",
                          description=description or "A lovely throw.", tags=list(tags),
                          price_cad=12.5, state="published" if published else "draft",
                          created_at=NOW - timedelta(days=120)))


def _orders(db, slug: str, n: int, *, contribution: float = 10.0, revenue: float = 12.5,
            source: str = "etsy_search", at: datetime | None = None, **extra) -> None:
    with db.session() as s:
        for k in range(n):
            ref = f"{slug}-{source}-{k}-{datetime.now().timestamp()}"
            c = Customer(customer_ref=ref, acquisition_source=source,
                         first_seen_at=at or NOW - timedelta(days=2))
            s.add(c)
            s.flush()
            s.add(Order(customer_id=c.id, external_ref=ref, at=at or NOW - timedelta(days=2),
                        product_slug=slug, revenue_cad=revenue, price_cad=revenue,
                        contribution_cad=contribution, acquisition_source=source, **extra))


def _reading(db, kind: str) -> dict:
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == kind)
                       .order_by(OperatingReading.id.desc()).limit(1))
        return dict(row.payload or {})


# ---- registration ----------------------------------------------------------------------------

def test_every_new_job_type_is_handled_scheduled_granted_and_banded():
    from brambleloop.swarm.orchestrate import JOB_BANDS

    db = _db()
    reg = Registry(db)
    scheduled = {c[2]: c[1] for c in CADENCES}
    for agent, job_type in (("ads", "ads.adjust"), ("ads", "ads.campaign"),
                            ("growth", "growth.distribution"), ("growth", "growth.journey"),
                            ("swarm_steward", "growth.steer")):
        assert handlers.get(job_type) is not None, job_type
        reg.authorize(agent, job_type)
        assert job_type in JOB_BANDS, job_type
        if job_type != "ads.campaign":        # enqueued upstream by ads.adjust
            assert scheduled.get(job_type) == agent, job_type


# ---- paid media behind the owner gate (#17, #242-#245, #294, #295) -------------------------

def test_ads_are_refused_without_the_owner_gate_and_planned_never_spent_with_it():
    from brambleloop.build2.executor import _ads_authorised

    db = _db()
    done = _work(db, "ads", "ads.adjust")
    assert done.status == JobStatus.DONE, done.last_error
    plan = _reading(db, growth_ops.ADS_KIND)
    assert plan["authority"]["granted"] is False and plan["spend_cad"] == 0.0
    for key in ("cac_split", "offsite_ads", "share_and_save", "trust_gate"):
        assert key in plan, key
    assert plan["share_and_save"]["status"] == "UNMEASURED"
    with db.session() as s:
        assert not list(s.scalars(select(Job).where(Job.job_type == "ads.campaign")))

    # A campaign job with no owner budget is hard-refused, terminally.
    dead = _work(db, "ads", "ads.campaign", {"slug": "x", "daily_budget_cad": 1.0})
    assert dead.status == JobStatus.DEAD and "ad_authority" in dead.last_error
    assert _ads_authorised(db, {}) is False

    # The owner sets a budget: the same job now runs the real machinery -- caps enforced in
    # code, then authorise_spend, which refuses outside production -- and spends nothing.
    with db.session() as s:
        s.add(SpendLimit(scope="ads", daily_cap_cad=5.0, lifetime_cap_cad=100.0))
    assert _ads_authorised(db, {}) is True
    planned = _work(db, "ads", "ads.campaign",
                    {"slug": "x", "daily_budget_cad": 3.0, "max_cac_cad": 4.0})
    assert planned.status == JobStatus.DONE, planned.last_error
    assert planned.outputs["planned"] is True and planned.outputs["spent_cad"] == 0.0
    assert "production" in planned.outputs["refused_by"]
    over = _work(db, "ads", "ads.campaign",
                 {"slug": "x", "daily_budget_cad": 50.0, "max_cac_cad": 4.0})
    assert over.outputs["planned"] is False and "headroom" in over.outputs["refused"]
    with db.session() as s:
        limit = s.scalar(select(SpendLimit).where(SpendLimit.scope == "ads"))
        assert limit.spent_today_cad == 0.0 and limit.spent_lifetime_cad == 0.0
        assert s.scalar(select(AuditLog).where(AuditLog.action == "ads.campaign_planned"))


def test_ads_adjust_reads_economics_from_rows_and_escalates_a_winner():
    db = _db()
    _certify(db, FLAGSHIP)
    with db.session() as s:
        s.add(SpendLimit(scope="ads", daily_cap_cad=4.0, lifetime_cap_cad=120.0))
    # Twenty orders across three products, one earning well above three times the median.
    _orders(db, FLAGSHIP, 18, contribution=10.0)
    _orders(db, "other-a", 1, contribution=1.0)
    _orders(db, "other-b", 1, contribution=1.0, offsite_ad_attributed=True)
    out = _run(db, "ads.adjust", agent="ads")
    plan = _reading(db, growth_ops.ADS_KIND)
    row = next(p for p in plan["products"] if p["slug"] == FLAGSHIP)
    # #242 organic-first, #243 CAC, #294 window and #17 trust are each read and each block.
    assert row["eligible"] is False and row["blocked_by"]
    assert any(b.startswith("trust") for b in row["blocked_by"])
    assert row["learning_window"]["seasonal"] is True
    assert plan["cac_split"]["blended_cac_cad"]["status"] == "measured"
    assert plan["offsite_ads"]["attributed_orders"] > 0          # #244 from the orders table
    assert out["escalations"] == 1 and plan["winners"][0]["product"] == FLAGSHIP
    with db.session() as s:
        action = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"ads.scale:{FLAGSHIP}"))
        assert action is not None and action.max_cost_cad > 0 and "#295" in action.blocks


# ---- distribution (#246-#251, #255, #258, #260, #295) ---------------------------------------

def test_growth_distribution_plans_from_rows_amplifies_a_winner_and_stops_a_weak_creator():
    db = _db()
    _certify(db, FLAGSHIP)
    with db.session() as s:
        s.add(LearningObservation(domain="customer_pain", source="benchmark_reviews",
                                  citation="fixture", observed_on=NOW, summary="fixture",
                                  detail={"recurring": {"counts_wrong": 5,
                                                        "yarn_estimate_wrong": 3}}))
        for _ in range(2):
            s.add(Collaboration(creator_ref="weak", pod="blankets", fee_cad=100.0,
                                state="active", conversions=1, support_cases=0,
                                measured_on=NOW))
        s.add(PhysicalTest(product_slug=FLAGSHIP, version="1.0.0", tester_ref="t1",
                           completed_at=NOW, passed=True))
        s.add(PhysicalTest(product_slug=FLAGSHIP, version="1.0.0", tester_ref="t1",
                           completed_at=NOW, passed=True))
        s.add(CreatorProfile(ref="t1", permissions=["advocate:consent-form-7"]))
    _orders(db, "creator-order", 1, contribution=5.0, source="creator:weak")
    # The flagship is a winner (#295): the pin plan grows by a new angle, never a copy.
    _orders(db, FLAGSHIP, 18, contribution=10.0)
    _orders(db, "other-a", 1, contribution=1.0)

    done = _work(db, "growth", "growth.distribution")
    assert done.status == JobStatus.DONE, done.last_error
    r = _reading(db, growth_ops.DISTRIBUTION_KIND)
    pin = next(p for p in r["pins"]["products"] if p["slug"] == FLAGSHIP)
    assert pin["schedule"]["from_calendar"] and pin["landable"] is True
    assert len(pin["angles"]) == 4 and pin["amplified"]["next_angles"]
    assert FLAGSHIP in r["pins"]["ready"]
    assert "counts_wrong" in r["clusters"]["buildable"]
    video = next(p for p in r["video"]["products"] if p["slug"] == FLAGSHIP)
    assert video["planned"] > 0 and "counts_wrong" in video["troubleshooting_for"]
    assert r["creators"]["portfolio"]["by_state"].get("stop") == ["weak"]
    assert "t1" in r["creators"]["graduated"]
    assert r["tools"]["hostable"] and all(f["may_claim_contribution"] for f in r["tools"]["flows"])
    assert r["interviews"]["gate"]["may_open"] is True
    # #250 acted on: the graduable tester is one owner card (the offer is the owner's), once.
    assert r["creators"]["owner_cards"] == ["creators.graduate:t1"]
    with db.session() as s:
        assert {c.state for c in s.scalars(select(Collaboration))} == {"stopped"}
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "creators.graduate:t1"))
        assert card is not None and card.max_cost_cad == 0.0 and "#250" in card.blocks

    # The design moves: every video module cut from the old tutorial is re-planned.
    with db.session() as s:
        pv = s.scalar(select(PatternVersion))
        pv.release_hash = "f" * 64
    _run(db, "growth.distribution", {"as_of": (TODAY + timedelta(days=1)).isoformat()},
         agent="growth")
    r2 = _reading(db, growth_ops.DISTRIBUTION_KIND)
    assert [x["slug"] for x in r2["video"]["stale_replanned"]] == [FLAGSHIP]
    assert r2["creators"]["owner_cards"] == []           # the card is not raised twice
    with db.session() as s:
        assert len(list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == "creators.graduate:t1")))) == 1


# ---- the buyer journey (#17, #19, #238, #239, #259, #261) -----------------------------------

def test_growth_journey_audits_listings_raises_and_resolves_and_attaches_proof():
    db = _db()
    _certify(db, FLAGSHIP, description="A lovely throw.")
    with db.session() as s:
        s.add(PhysicalTest(product_slug=FLAGSHIP, version="1.0.0", tester_ref="t1",
                           completed_at=NOW, passed=True))
        s.add(Experiment(name="promo-1", kind="promotion", product_slug=FLAGSHIP,
                         hypothesis="a short seasonal sale", state="running",
                         arms=[{"arm": "organic", "visits": 1000, "orders": 20,
                                "revenue_cad": 250.0},
                               {"arm": "promoted", "visits": 1000, "orders": 21,
                                "revenue_cad": 21 * 9.0}],
                         result={"full_price_cad": 12.5, "promo_price_cad": 9.0,
                                 "starts": (TODAY - timedelta(days=20)).isoformat(),
                                 "ends": (TODAY - timedelta(days=1)).isoformat()}))
        # Three listings in one cell; the first converts at zero against the cohort's rate.
        for k in range(3):
            s.add(ListingOutcome(product_slug=f"bench-{k}", period_start="2026-08-01",
                                 period_end="2026-08-31", impressions=400, visits=40,
                                 orders=0 if k == 0 else 1, source="fixture"))
    done = _work(db, "growth", "growth.journey")
    assert done.status == JobStatus.DONE, done.last_error
    r = _reading(db, growth_ops.JOURNEY_KIND)
    assert FLAGSHIP in r["friction"]["with_defects"]
    assert r["first_customer"]["incidents_open"]
    assert r["proof"]["recorded"] == 1
    promo = r["promotions"]["promotions"][0]
    assert promo["measurable"] is True and promo["verdict"] != "worth repeating"
    assert r["benchmarks"]["cells"]["occupied"] >= 1
    verdicts = {d["slug"]: d["verdict"] for d in r["benchmarks"]["diagnoses"]}
    assert verdicts["bench-0"] == "below_cohort" and verdicts["bench-1"] == "at_or_above"
    # #238 acted on: the below-cohort listing is an incident naming the factors to test.
    assert r["benchmarks"]["incidents"]["opened"] == ["benchmark:bench-0:below_cohort"]
    with db.session() as s:
        friction = [i.signature for i in s.scalars(select(Incident).where(
            Incident.signature.like("friction:%"), Incident.resolved == False))]  # noqa: E712
        assert friction and all(sig.startswith(f"friction:{FLAGSHIP}:") for sig in friction)
        assert s.scalar(select(Experiment)).state == "not_repeatable"
        bench = s.scalar(select(Incident).where(
            Incident.signature == "benchmark:bench-0:below_cohort"))
        assert bench is not None and not bench.resolved
        assert "price" in bench.detail["factors_to_test"]

    # Re-run: proof is attached once, and friction resolves when the listing no longer has it.
    with db.session() as s:
        for row in s.scalars(select(Listing)):
            s.delete(row)
    _run(db, "growth.journey", agent="growth")
    r2 = _reading(db, growth_ops.JOURNEY_KIND)
    assert r2["proof"]["recorded"] == 0
    assert sorted(r2["friction"]["resolved"]) == sorted(friction)
    with db.session() as s:
        assert len(list(s.scalars(select(AuditLog).where(
            AuditLog.action == "trust.proof")))) == 1


# ---- the week applied to the queue (#264, #267, #276, #291) ---------------------------------

def test_growth_steer_moves_the_queue_and_orders_the_experiment_queue():
    from brambleloop.scale.war_room import board

    db = _db()
    with db.session() as s:
        s.add(OperatingReading(kind="growth.weekly", period_key="2026-W39", payload={
            "reallocation": {"move": True, "toward": "conversion_rate",
                             "owners": ["publishing", "pricing"],
                             "experiments": ["thumbnail", "price"], "why": "fixture"}}))
        s.add(OperatingReading(kind="seasonal.daily", period_key=TODAY.isoformat(), payload={
            "rollforward": {"capacities": {
                "engineering": {"moves": [{"from": "Halloween", "to": "Christmas"}]},
                "marketing": {"moves": []}}},
            "fast_lane": {"admitted": ["fast-slug"]}}))
        s.add(RegisteredExperiment(key="s:price", product_slug="s", state="registered"))
        s.add(RegisteredExperiment(key="s:search", product_slug="s", state="registered"))
    q = JobQueue(db)
    pricing = q.enqueue("pricing", "pricing.position", {"slug": "s", "version": "1"},
                        idempotency_key="p", priority=70)
    late = q.enqueue("orchestrator", "seasonal.sentinel", {"season": "Halloween"},
                     idempotency_key="h", priority=70)
    fast = q.enqueue("listing", "listing.draft", {"slug": "fast-slug", "version": "1"},
                     idempotency_key="f", priority=70)
    done = _work(db, "swarm_steward", "growth.steer")
    assert done.status == JobStatus.DONE, done.last_error
    with db.session() as s:
        assert s.get(Job, pricing.id).priority == 60      # toward the constraint's owners
        assert s.get(Job, late.id).priority == 80         # the occasion that released capacity
        assert s.get(Job, fast.id).priority == 50         # admitted to the fast lane
        chain = s.scalar(select(Job).where(Job.job_type == "chain.rebuild"))
        assert chain is not None and chain.priority == 25
        assert chain.inputs["slugs"] == ["fast-slug"]
        ranks = {e.key: e.detail["steer_rank"] for e in s.scalars(select(RegisteredExperiment))}
    assert ranks == {"s:price": 0, "s:search": 2}
    flight = board(db)["board"]["experiments_in_flight"]["value"]
    assert flight[0]["key"] == "s:price"
    # Steered once: another hour does not drift the same jobs further.
    _run(db, "growth.steer", agent="swarm_steward")
    with db.session() as s:
        assert s.get(Job, pricing.id).priority == 60


# ---- support (#18, #257) --------------------------------------------------------------------

def test_support_reply_times_the_case_and_refuses_a_gating_draft():
    from brambleloop.support import department, service

    db = _db()
    with db.session() as s:
        case = SupportCase(customer_ref="buyer-1", question="where is my pattern file?",
                           at=NOW - timedelta(minutes=3), detail={})
        s.add(case)
        s.flush()
        cid = case.id
    done = _work(db, "support", "support.reply", {"case_id": cid})
    assert done.status == JobStatus.DONE, done.last_error
    with db.session() as s:
        detail = dict(s.get(SupportCase, cid).detail)
    assert 2.5 <= detail["response_minutes"] < 60
    assert detail["response_measured_as"] == "draft_ready"
    level = service.service_level(db)
    assert level["draft_ready"]["cases"] == 1 and level["meets_target"] is None

    # A draft that asks for a rating attached to owed support never stays on the case.
    original = department.CustomerExperience.handle

    def gating(self, **kw):
        reply = original(self, **kw)
        reply.body = reply.body + " If this helped, a review would mean a lot!"
        with self.db.session() as s2:
            row = s2.get(SupportCase, kw["case_id"])
            row.answer = reply.body
        return reply

    with db.session() as s:
        case2 = SupportCase(customer_ref="buyer-2", question="where is my pattern file?",
                            detail={})
        s.add(case2)
        s.flush()
        cid2 = case2.id
    department.CustomerExperience.handle = gating
    try:
        refused = _work(db, "support", "support.reply", {"case_id": cid2})
    finally:
        department.CustomerExperience.handle = original
    assert refused.status == JobStatus.DONE, refused.last_error
    assert refused.outputs["copy_check"]["ok"] is False and refused.outputs["body"] == ""
    with db.session() as s:
        row = s.get(SupportCase, cid2)
        assert row.answer == "" and row.escalated is True
        assert "if this helped" in row.detail["draft_refused"]
        assert s.scalar(select(AuditLog).where(AuditLog.action == "support.draft_refused"))


# ---- commerce readings read the real sources (#253, #256, #257) ----------------------------

def test_commerce_readings_read_stars_club_answers_and_referral_and_act():
    db = _db()
    for k in range(3):
        _certify(db, f"club-{k}", published=None, created_at=NOW - timedelta(days=30 - 10 * k))
    _orders(db, "starred", 20, reviewed=True, detail={"review_stars": 5})
    _orders(db, "referred", 2, contribution=4.0, source="referral")
    with db.session() as s:
        s.add(LedgerEntry(category="referral_reward", expense_cad=50.0))
        for _ in range(3):
            s.add(SupportCase(customer_ref="b", question="q",
                              detail={"theme": "expected_a_finished_item"}))
    done = _work(db, "cfo", "commerce.readings")
    assert done.status == JobStatus.DONE, done.last_error
    with db.session() as s:
        reading = s.scalar(select(AuditLog).where(
            AuditLog.action == "commerce.readings")).detail["reading"]
        sigs = {i.signature for i in s.scalars(select(Incident))}
    assert reading["reviews"]["stars"]["readable"] is True
    assert reading["club"]["cadence"]["fits"] is True
    assert reading["club"]["may_launch"]["may_launch"] is False     # demand etc. unanswered
    assert reading["club"]["evidence"]["cadence"].startswith("median")
    assert reading["referral"]["measurable"] is True and reading["referral"]["worth_it"] is False
    assert "review_route:expected_a_finished_item" in sigs and "referral:negative" in sigs


# ---- the confidence model fed from rows (#27, #243, #262, #273, #275) ----------------------

def test_weekly_solve_feeds_conditions_scenarios_calibration_and_cac():
    from brambleloop.growth import weekly
    from brambleloop.scale import evidence

    db = _db()
    _certify(db, FLAGSHIP)
    _orders(db, FLAGSHIP, 30, contribution=10.0)
    with db.session() as s:
        s.add(ListingOutcome(product_slug=FLAGSHIP, period_start=(TODAY - timedelta(days=20))
                             .isoformat(), period_end=TODAY.isoformat(), impressions=20000,
                             visits=1000, orders=30, source="fixture"))
        # A forecast made before a past week, far above what that week sold.
        start = TODAY - timedelta(days=TODAY.weekday() + 14)
        s.add(OperatingReading(kind=evidence.FORECAST_KIND, period_key=start.isoformat(),
                               payload={"period_start": start.isoformat(),
                                        "period_end": (start + timedelta(days=6)).isoformat(),
                                        "made_on": (start - timedelta(days=3)).isoformat(),
                                        "revenue_cad": 5000.0, "terms": {}}))
    _orders(db, FLAGSHIP, 1, at=datetime(start.year, start.month, start.day, 12,
                                         tzinfo=timezone.utc) + timedelta(days=2))
    reading = weekly.solve(db, today=TODAY)
    assert reading["scenarios"]["conversion_source"].startswith("observed")
    assert reading["scenarios"]["evidence_supported_paths"] > 0
    assert "positive_contribution_margin" in reading["confidence"]["conditions_met"]
    assert "conservative_scenario_near_target" in reading["conditions"]["conditions"]
    cond = reading["conditions"]["evidence"]["conversion_over_meaningful_sample"]
    assert cond["visits_needed"] != "UNMEASURED"           # adaptive to the observed rate
    assert reading["calibration"]["scored"] == 1
    assert reading["confidence"]["calibration_ceiling"] < 1.0
    assert reading["cac_split"]["blended_cac_cad"]["status"] == "measured"

    # The weekly job writes next week's forecast before the week starts.
    _run(db, "ops.capacity", {"as_of": TODAY.isoformat()})
    with db.session() as s:
        keys = {r.period_key for r in s.scalars(select(OperatingReading).where(
            OperatingReading.kind == evidence.FORECAST_KIND))}
    assert len(keys) == 2


# ---- pricing and launch readiness (#7, #24, #259, #17) --------------------------------------

def test_pricing_prices_the_customer_outcome_and_reads_contribution_per_visitor():
    db = _db()
    _run(db, "pricing.position", {"slug": FLAGSHIP, "version": "1.0.0",
                                  "finished_size_cm": [120.0, 150.0],
                                  "yardage": {"cream": 900.0, "pine": 700.0}},
         agent="pricing")
    with db.session() as s:
        detail = s.scalar(select(AuditLog).where(
            AuditLog.action == "pricing.positioned")).detail
    assert detail["outcome_price"] is not None
    assert "page_count" in detail["outcome_price"]["never_priced_on"]
    assert detail["outcome_price"]["anchor_basis"].startswith("midpoint")
    assert detail["per_visitor"]["status"] == "UNMEASURED"


def test_launch_readiness_carries_the_first_customer_verdicts_and_the_trust_gate():
    db = _db()
    out = _run(db, "launch.readiness")
    assert "first_hundred:truthful_expectations" in out["outstanding"]
    assert out["paid_traffic"]["may_scale"] is False and out["paid_traffic"]["blocking"]


# ---- routes that read the database (#237, #238, #239, #273) ---------------------------------

def test_stats_ingest_benchmarks_and_scale_routes_read_the_database():
    from fastapi.testclient import TestClient

    from brambleloop.app import main
    from brambleloop.runtime import release

    csv_text = ("Search term,Impressions,Visits,Orders,Revenue\n"
                "mosaic blanket,5000,40,0,0\n"
                "christmas throw,800,30,2,25\n")
    auth = {"authorization": f"Bearer {TOKEN}"}
    with TestClient(main.app) as c:
        assert c.post("/api/attribution/stats", content=csv_text).status_code == 401
        bad = c.post("/api/attribution/stats", content="nope\n1\n", headers=auth)
        assert bad.status_code == 400
        ok = c.post("/api/attribution/stats", content=csv_text, headers=auth)
        assert ok.status_code == 200, ok.text
        assert ok.json()["vanity_terms"] == ["mosaic blanket"]
        bench = c.get("/api/benchmarks").json()
        assert "diagnoses" in bench and "opportunities" in bench
        scale = c.get("/api/scale").json()
        for key in ("probability", "scenarios", "conditions", "calibration", "cac_split"):
            assert key in scale, key

    class Q:
        def __init__(self, phrase):
            self.phrase = phrase

    # #237 / #24: the vanity tag's slot goes to the term the export shows earning per visit
    # before it goes to an unproven phrase.
    tags, got = release._drop_vanity_tags(
        main.db, [Q("mosaic blanket"), Q("nordic throw")], ["mosaic blanket", "xmas"])
    assert got["vanity_dropped"] == ["mosaic blanket"]
    assert tags == ["xmas", "christmas throw"]
    assert got["refilled_from_earning"] == ["christmas throw"]


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
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
