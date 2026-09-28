"""Certification C-64: the order source, and everything that reads orders, in the runtime.

Every row that reads orders (#11 #12 #13 #22 #26 #42 #47 #49 #104 #132 #233 #234 #235 #252
#256 #269 #271) was parked or claimed while nothing in the running system could write an
order: `getShopReceipts` was never called and `cohorts.record_order` had no caller. These
tests drive the real handlers through the worker on a temp database:

* with the `transactions_r` gate closed (today), the ingest records UNMEASURED and makes no
  network call -- the injected reader raises if touched, and sockets are refused;
* with the gate's rows present and a FAKE receipt feed injected (never Etsy), the ingest
  writes customers, orders, the version map and the ledger, and every downstream reader
  acts on them: cohorts, offers into portfolio retirement, winner studies into ideation,
  reinvestment owner actions, the ladder and bundles, promotion verdicts into pricing,
  repeat windows, referral, growth loops, net-contribution pricing, the nightly trajectory
  and the creative north star by cohort.

Run: cd brambleloop && $PY tests/test_cert_orders.py
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="cert_orders_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the certification harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.build2 import executor, reachability  # noqa: E402
from brambleloop.commerce import order_readings, orders_ingest, pricing  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Cohort, Customer, GrowthLoop, Incident,  # noqa: E402
                                     Job, JobStatus, LedgerEntry, Listing, ListingOutcome,
                                     OAuthCredential, OperatingReading, Order, OrderVersion,
                                     OwnerAction, Phase, PriceObservation)
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers every handler
from brambleloop.runtime.worker import CADENCES, Worker  # noqa: E402
from brambleloop.swarm.orchestrate import JOB_BANDS  # noqa: E402

NEW_JOBS = {"commerce.orders_ingest": "cfo", "commerce.order_readings": "cfo",
            "scale.trajectory": "orchestrator", "creative.north_star": "creative_director"}
NOW = datetime.now(timezone.utc)
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/orders{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, agent, job_type, inputs=None):
    _n[0] += 1
    job = JobQueue(db).enqueue(agent, job_type, inputs or {},
                               idempotency_key=f"t{_n[0]}:{job_type}")
    worker = Worker(db, "cert-orders", phase=Phase.SHADOW, job_types=[job_type],
                    lease_seconds=900)
    for _ in range(10):          # earlier queued jobs of the same type run first
        if not worker.run_once():
            break
    with db.session() as s:
        done = s.get(Job, job.id)
        assert done.status == JobStatus.DONE, (job_type, done.last_error)
        return dict(done.outputs or {}) if hasattr(done, "outputs") else {}


def _audit(db, action):
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == action)
                       .order_by(AuditLog.id.desc()).limit(1))
        return dict(row.detail or {}) if row else None


class Refusing:
    """A receipt reader that must never be reached."""

    calls = 0

    def receipts(self, *, since):
        Refusing.calls += 1
        raise AssertionError("the receipt reader was called with the gate closed")


class FakeFeed:
    """A fake receipt feed in Etsy's documented ShopReceipt shape. Never Etsy."""

    def __init__(self, receipts):
        self.receipts_list = receipts
        self.calls = 0

    def receipts(self, *, since):
        self.calls += 1
        return list(self.receipts_list)


def _receipt(rid, buyer, listing_id, amount_cents, *, currency="CAD", days_ago=1,
             refunded=False, extra_lines=()):
    lines = [{"transaction_id": rid * 10, "listing_id": listing_id, "quantity": 1,
              "price": {"amount": amount_cents, "divisor": 100, "currency_code": currency}}]
    for i, (lid, cents) in enumerate(extra_lines, start=1):
        lines.append({"transaction_id": rid * 10 + i, "listing_id": lid, "quantity": 1,
                      "price": {"amount": cents, "divisor": 100, "currency_code": currency}})
    return {"receipt_id": rid, "buyer_user_id": buyer, "buyer_email": "never@stored.example",
            "name": "Never Stored",
            "create_timestamp": int((NOW - timedelta(days=days_ago)).timestamp()),
            "refunds": [{"amount": {"amount": amount_cents, "divisor": 100}}] if refunded
            else [], "transactions": lines}


def _open_gate(db):
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", detail={"ok": True}))
        s.add(OAuthCredential(provider="etsy", refresh_token_sealed="sealed",
                              token_fingerprint="abcd1234",
                              scopes="listings_r listings_w shops_r transactions_r"))


def _certify(db, cir):
    _n[0] += 1
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                         idempotency_key=f"cert{_n[0]}")
    assert Worker(db, "cert-orders", phase=Phase.SHADOW, job_types=["gate.certify"],
                  lease_seconds=900).run_once()


def _catalogue(db):
    """Three products: a certified throw (A) and two listed products (B, C)."""
    cir = nf.build()
    _certify(db, cir)
    old = NOW - timedelta(weeks=8)
    with db.session() as s:
        s.add(Listing(product_slug=cir.slug, version=cir.version, title="A", description="",
                      price_cad=12.0, state="published", etsy_listing_id="111", created_at=old))
        s.add(Listing(product_slug="cloudline-baby-blanket", version="1.0.0", title="B",
                      description="", price_cad=9.0, state="published",
                      etsy_listing_id="222", created_at=old))
        s.add(Listing(product_slug="harvest-table-runner", version="1.0.0", title="C",
                      description="", price_cad=5.0, state="published",
                      etsy_listing_id="333", created_at=old))
    return cir


def _feed(slug_a_listing="111"):
    receipts = []
    # 40 buyers of A across eight weeks -- a credible winner (#22).
    for i in range(40):
        receipts.append(_receipt(1000 + i, 5000 + i, slug_a_listing, 1200,
                                 days_ago=1 + (i % 50)))
    # B twice, C once; one of B's buyers is a repeat buyer of A (#252), one pays in USD (#269).
    receipts.append(_receipt(2001, 5000, "222", 900, days_ago=2))
    receipts.append(_receipt(2002, 6001, "222", 700, currency="USD", days_ago=3))
    receipts.append(_receipt(2003, 6002, "333", 500, days_ago=4, refunded=False))
    receipts.append(_receipt(2004, 6003, "333", 500, days_ago=5, refunded=True))
    # A line that reconciles to nothing (a negative amount): the cohort writer refuses it and
    # the run records the refusal rather than dying on it. Its buyer already exists above.
    receipts.append(_receipt(2005, 5000, "333", -500, days_ago=6))
    return receipts


# ---------------------------------------------------------------------------


def test_new_jobs_are_scheduled_permitted_and_banded():
    registry = Registry(_db())
    for job_type, agent in NEW_JOBS.items():
        assert any(c[2] == job_type and c[1] == agent for c in CADENCES), job_type
        registry.authorize(agent, job_type)
        assert job_type in JOB_BANDS, job_type


def test_gate_closed_records_unmeasured_and_never_touches_the_reader():
    db = _db()
    orders_ingest.reader_factory = lambda _db: Refusing()
    try:
        _run(db, "cfo", "commerce.orders_ingest")
    finally:
        orders_ingest.reader_factory = None
    got = _audit(db, "commerce.orders_ingested")
    assert got["ran"] is False and got["reading"] == "UNMEASURED"
    assert got["network_calls"] == 0 and Refusing.calls == 0
    assert any("transactions_r" in m for m in got["gate_missing"])
    with db.session() as s:
        assert s.scalar(select(func.count(Order.id))) == 0
    # And every reader of orders still runs on cadence and says UNMEASURED honestly.
    _run(db, "cfo", "commerce.order_readings")
    r = order_readings.latest(db)
    assert r["cohorts"]["reading"] == "UNMEASURED"
    assert r["offers"]["reading"] == "UNMEASURED"
    assert r["winners"]["reading"] == "UNMEASURED"
    assert r["repeat"]["reading"] == "UNMEASURED"
    assert r["referral"]["outcome"]["measurable"] is False
    assert r["reinvestment"]["owner_action"] is None


def _ingested():
    db = _db()
    cir = _catalogue(db)
    _open_gate(db)
    feed = FakeFeed(_feed())
    orders_ingest.reader_factory = lambda _db: feed
    try:
        _run(db, "cfo", "commerce.orders_ingest")
        again = FakeFeed(_feed())
        orders_ingest.reader_factory = lambda _db: again
        _run(db, "cfo", "commerce.orders_ingest")      # idempotent re-read
    finally:
        orders_ingest.reader_factory = None
    return db, cir, feed


def test_gate_open_ingest_writes_customers_orders_versions_and_ledger():
    """#11 #12 #42: receipts become customers, orders, the version map and sale entries."""
    db, cir, feed = _ingested()
    assert feed.calls == 1
    with db.session() as s:
        customers = list(s.scalars(select(Customer)))
        orders = list(s.scalars(select(Order)))
        versions = list(s.scalars(select(OrderVersion)))
        ledger = list(s.scalars(select(LedgerEntry).where(LedgerEntry.category == "sale")))
        queued = list(s.scalars(select(Job).where(Job.job_type == "commerce.order_readings")))
    assert len(customers) == 43 and all("@" not in c.customer_ref for c in customers)
    assert not any("Never Stored" in str(c.detail) for c in customers)
    assert len(orders) == 44 and len(ledger) == 44          # the second run added nothing
    # The run reports how many network calls its reader made and which line it refused.
    got = _audit(db, "commerce.orders_ingested")
    assert got["ran"] is True and got["network_calls"] == 1
    assert any(r.get("transaction_id") == "20050" for r in got["not_recorded"])
    assert not any(o.external_ref.endswith(":20050") for o in orders)
    assert all(o.source == "etsy_receipts" for o in orders)
    assert {v.version for v in versions} == {cir.version}   # recorded at sale time
    assert sum(1 for v in versions if v.product_slug == cir.slug) == 40
    assert len(versions) == 44
    usd = next(o for o in orders if o.currency == "USD")
    assert usd.amount_original == 7.0 and usd.fx_usd_per_cad and usd.fx_taken_on
    assert usd.fx_measured is False and abs(usd.price_cad - 7.0 / usd.fx_usd_per_cad) < 0.01
    assert any(o.is_repeat for o in orders)
    assert queued, "an ingest that created orders queues the order readings"
    # The ledger rows carry their evidence, which is what opens the customers data gate.
    assert executor._has_customers(db, {})


def test_order_readings_drive_every_downstream_reader():
    db, cir, _ = _ingested()
    _run(db, "cfo", "commerce.order_readings")
    r = order_readings.latest(db)
    # #11/#12: cohorts from the rows, below-floor metrics UNMEASURED rather than invented.
    assert r["cohorts"]["customers"] == 43
    assert r["cohorts"]["validation"]["customers"] == 43
    # 43 buyers clear the floor of 30 and one bought again, so lifetime contribution per
    # buyer is measured -- and it is the reward ceiling the referral check reads (#256).
    ltv = r["cohorts"]["lifetime_contribution_per_buyer_cad"]
    assert ltv is not None and ltv > 0
    # #13: offer results per design from the orders.
    assert any(x["design"] == cir.slug and x["buyers"] == 40 for x in r["offers"]["results"])
    # #22: a credible winner opens a bounded study, and ideation reads it into its briefs.
    assert r["winners"]["top"] == cir.slug and r["winners"]["verdict"]["credible"]
    study = order_readings.directives(db)["replication"]
    assert study and study["winner"] == cir.slug and study["capacity_share"] <= 0.35
    from brambleloop.creative import ideation

    plan = ideation.plan(db, kind="tournament", event="Christmas", pod="home_decor",
                         forms=["rectangle_throw"], cycle=0)
    assert plan["commerce"]["replication"]["winner"] == cir.slug
    briefs = [ideation.constraints_text(plan, i)[0] for i in range(6)]
    # The study's capacity share of the calls carry the adjacent-experiment constraint, and
    # (#233) the empty ladder rungs reach the briefs too.
    assert 0 < sum("replication study of" in b for b in briefs) < len(briefs)
    assert any("value ladder:" in b for b in briefs)
    # #252: repeat windows per first-purchase cohort and lifetime contribution per buyer.
    assert f"first_product={cir.slug}" in r["repeat"]["windows"]
    assert r["repeat"]["lifetime_contribution_per_buyer_cad"][f"first_product={cir.slug}"] > 0
    # #256: the referral outcome is measured from the rows (nobody was referred) and every
    # declared mechanic is checked against the measured contribution per buyer: the free
    # mechanics may run, and a credit is refused if it exceeds 30% of that contribution.
    assert r["referral"]["outcome"]["measurable"] is True
    assert r["referral"]["outcome"]["attributed_customers"] == 0
    checks = {c["mechanic"]: c for c in r["referral"]["mechanics"]}
    assert set(checks) == {"show_your_make", "share_the_pattern", "first_purchase_credit"}
    assert "show_your_make" in r["referral"]["may_run"]
    assert checks["first_purchase_credit"]["ok"] is (1.0 <= ltv * 0.30)
    # #271 read through F-283/F-289: a receipt does not say how the buyer arrived, so the
    # ingested orders are `unknown` and credit NO loop -- the organic loop is not handed
    # orders nobody attributed to it (the old blanket "etsy" label did exactly that).
    with db.session() as s:
        etsy = s.scalar(select(GrowthLoop).where(GrowthLoop.key == "etsy_organic"))
        assert etsy.orders == 0 and etsy.contribution_cad == 0
        assert {o.acquisition_source for o in s.scalars(select(Order))} == {"unknown"}
    # #233: the catalogue on rungs, and #234: pairs from product facts.
    assert r["ladder"]["reading"] == "measured" and r["ladder"]["products"]
    assert "considered" in r["bundles"]
    # #49: reserves from the ledger's 30 days.
    with db.session() as s:
        since = NOW - timedelta(days=30)
        gross = sum(x.gross_cad - x.refunds_cad for x in s.scalars(
            select(LedgerEntry).where(LedgerEntry.category == "sale"))
            if (x.at if x.at.tzinfo else x.at.replace(tzinfo=timezone.utc)) >= since)
    assert abs(r["reinvestment"]["gross_cad_30d"] - round(gross, 2)) < 0.01
    assert r["reinvestment"]["recommendation"]["owner_approval_required"] is True


def test_reinvestment_raises_an_owner_action_when_the_envelope_is_non_zero():
    """#49: reserves from the ledger; a non-zero recommendation is an owner action."""
    from brambleloop.scale import confidence

    db = _db()
    with db.session() as s:
        s.add(LedgerEntry(category="sale", gross_cad=5000.0, evidence_ref="etsy:9:90",
                          at=NOW - timedelta(days=2)))
    # Today the modelled confidence is 0.0, so the envelope is spare and nothing is
    # recommended -- the honest reading.
    _run(db, "cfo", "commerce.order_readings")
    first = order_readings.latest(db)["reinvestment"]
    assert first["recommendation"]["envelope"]["envelope_cad"] > 0
    assert first["recommendation"]["recommended_cad"] == 0 and first["owner_action"] is None
    # When the confidence ladder reads above zero, the same job raises the owner action.
    original = confidence.probability
    confidence.probability = lambda _db, **_k: {"probability": 0.5}
    try:
        _run(db, "cfo", "commerce.order_readings")
    finally:
        confidence.probability = original
    got = order_readings.latest(db)["reinvestment"]
    with db.session() as s:
        action = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == got["owner_action"]))
    assert got["recommendation"]["recommended_cad"] > 0
    assert action is not None and action.max_cost_cad == got["recommendation"]["recommended_cad"]


def test_portfolio_review_reads_exposure_and_consults_offers_before_retiring():
    """#47 and #13 in the running review."""
    db, cir, _ = _ingested()
    period = (date.today() - timedelta(days=7)).isoformat()
    with db.session() as s:
        from brambleloop.core.models import Product

        s.add(Product(slug="harvest-table-runner", title="C", status="certified"))
        s.add(ListingOutcome(product_slug="harvest-table-runner", period_start=period,
                             period_end=date.today().isoformat(), impressions=2000,
                             visits=80, favourites=1, orders=0, source="test"))
    # The runner's single order was refunded above; make its exposure the only evidence.
    with db.session() as s:
        for o in s.scalars(select(Order).where(Order.product_slug == "harvest-table-runner")):
            o.refunded = True
    out = _run(db, "orchestrator", "portfolio.review")
    got = _audit(db, "portfolio.reviewed")
    guard = {g["slug"]: g for g in got["offer_guard"]}
    assert "harvest-table-runner" in guard
    assert guard["harvest-table-runner"]["label"] == "APPEAL_PROBLEM"
    assert guard["harvest-table-runner"]["may_retire"] is False
    assert got["exposure_read"]["listing_outcomes"] >= 1
    with db.session() as s:
        from brambleloop.core.models import PortfolioReview

        review = s.scalar(select(PortfolioReview).order_by(PortfolioReview.id.desc()))
        assert any("harvest-table-runner" in a and "#13" in a for a in review.actions)
    del out


def test_a_correcting_version_prepares_the_notice_for_its_buyers():
    """#42: gate.certify of a newer version finds the buyers of the older one."""
    import dataclasses

    db, cir, _ = _ingested()
    corrected = dataclasses.replace(cir, version="1.0.1")
    _certify(db, corrected)
    with db.session() as s:
        rows = list(s.scalars(select(OrderVersion).where(
            OrderVersion.product_slug == cir.slug)))
        action = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"correction_notice:{cir.slug}@1.0.1"))
    assert rows and all(r.current_safe_version == "1.0.1" for r in rows)
    assert all((r.detail or {}).get("correction_notice", {}).get("sent") is False for r in rows)
    assert action is not None and "40 buyer" in action.action
    got = _audit(db, "buyer_trust.correction_prepared")
    assert got["affected_count"] == 40


def test_pricing_decides_on_net_contribution_with_currency_normalised():
    """#269: measured price points and the net floor decide; the handler reads the orders."""
    points = [{"price_cad": 8.0, "visits": 400, "contribution_cad": 60.0},
              {"price_cad": 11.0, "visits": 400, "contribution_cad": 40.0}]
    d = pricing.decide_price("x", category_band_cad=(6.0, 14.0), proposed_cad=11.0,
                             price_points=points, foreign_share=0.5)
    assert d.price_cad == 8.0 and any("contribution per visitor" in r for r in d.reasons)
    assert d.net_contribution["foreign_share"]["value"] == 0.5
    assert d.net_contribution["fees"]["currency_conversion"] > 0
    low = pricing.decide_price("y", category_band_cad=(0.5, 14.0), proposed_cad=0.5)
    assert low.net_contribution["net_contribution"]["amount"] >= pricing.MIN_NET_CONTRIBUTION_CAD
    db, cir, _ = _ingested()
    from brambleloop.runtime import release

    inputs = release._pricing_net_inputs(db, cir.slug)
    assert inputs["foreign_share"] is not None and 0 < inputs["foreign_share"] < 1


def test_promotion_verdicts_reach_pricing():
    """#235: a promotion measured against a full-price arm; a loser is not repeated."""
    db = _db()
    today = date.today()
    with db.session() as s:
        s.add(Cohort(key="o1", product_slug="p", arm="organic", visits=1000, orders=30,
                     revenue_cad=360.0))
        s.add(Cohort(key="p1", product_slug="p", arm="promoted", visits=1000, orders=31,
                     revenue_cad=260.0))
        s.add(PriceObservation(product_slug="p", price_cad=8.4, on_sale=True,
                               regular_price_cad=12.0,
                               from_date=(today - timedelta(days=10)).isoformat(),
                               to_date=today.isoformat()))
    got = order_readings.promotion_block(db)
    assert got["reading"] == "measured"
    assert "p" in got["do_not_repeat"]


def test_trajectory_runs_nightly_from_the_database():
    """#26: observed terms from the rows; a changed binding constraint re-plans capacity."""
    db = _db()
    _run(db, "orchestrator", "scale.trajectory",
         {"as_of": (date.today() - timedelta(days=1)).isoformat()})
    first = _audit(db, "scale.trajectory")
    assert first["kind"] == "assumption_space" and first["probability"] is None
    assert "listing_count" in first["observed_terms"]
    # Exposure and orders arrive; the funnel becomes identifiable and the constraint changes.
    db2, cir, _ = _ingested()
    _run(db2, "orchestrator", "scale.trajectory",
         {"as_of": (date.today() - timedelta(days=1)).isoformat()})
    with db2.session() as s:
        s.add(ListingOutcome(product_slug=cir.slug, period_start=date.today().isoformat(),
                             period_end=date.today().isoformat(), impressions=20000,
                             visits=900, favourites=40, orders=40, source="test"))
    _run(db2, "orchestrator", "scale.trajectory", {"as_of": date.today().isoformat()})
    got = _audit(db2, "scale.trajectory")
    assert {"ctr", "conversion", "aov_cad", "qualified_traffic"} <= set(got["observed_terms"])
    assert got["constraint_changed"] and got["previous_constraint"] == "UNMEASURED"
    with db2.session() as s:
        assert s.scalar(select(Job).where(Job.job_type == "ops.capacity")) is not None
    with db2.session() as s:
        stored = s.scalar(select(func.count(OperatingReading.id)).where(
            OperatingReading.kind == "scale.trajectory"))
    assert stored == 2


def test_north_star_is_computed_by_cohort_and_a_regression_is_a_defect():
    """#104 #132: the four computable metrics by monthly cohort, from rows, never {}."""
    db = _db()
    months = [NOW - timedelta(days=70), NOW - timedelta(days=5)]
    for at, novelty, survived in ((months[0], 0.50, 6), (months[1], 0.20, 2)):
        with db.session() as s:
            s.add(AuditLog(actor="creative_director", action="creative.tournament", at=at,
                           detail={"field": {"generated": 10},
                                   "survivors": [{"key": f"k{i}"} for i in range(survived)],
                                   "research_survivors": [{"key": "k", "novelty_distance":
                                                           novelty}]}))
    _run(db, "creative_director", "creative.north_star")
    got = _audit(db, "creative.north_star")
    assert got["answerable"] is True and len(got["cohorts"]) == 2
    assert set(got["regressing"]) >= {"novelty_distance", "concept_to_engineering_survival"}
    assert got["incident"] == "opened"
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == "creative.north_star_regression"))
        assert inc is not None and not inc.halts_publication


def test_bundle_pairs_come_from_certified_product_facts():
    """#234: combination identification needs no customers; it runs on the catalogue."""
    from brambleloop.products.builder import for_slug

    db = _db()
    for slug in ("autumn-oak-mosaic-throw", "harvest-table-runner", "cloudline-baby-blanket"):
        _certify(db, for_slug(slug))
    _run(db, "cfo", "commerce.order_readings")
    got = order_readings.latest(db)["bundles"]
    assert got["reading"] == "measured" and got["considered"] == 3
    pairs = [sorted(c["slugs"]) for c in got["candidates"]]
    assert ["autumn-oak-mosaic-throw", "harvest-table-runner"] in pairs
    assert not any("cloudline-baby-blanket" in p and "harvest-table-runner" in p
                   for p in pairs)


def test_the_route_reads_the_database_not_an_empty_dict():
    src = (ROOT / "src/brambleloop/app/main.py").read_text()
    assert "north_star({})" not in src and "trajectory.nightly(None)" not in src


def test_new_modules_are_reached_from_the_runtime():
    reachability.reachable.cache_clear()
    reachability._references.cache_clear()
    for rel in ("commerce/orders_ingest.py", "commerce/order_readings.py",
                "commerce/offers.py", "commerce/replication.py", "finance/reinvestment.py",
                "commerce/ladder.py", "commerce/bundles.py", "commerce/promotion.py",
                "commerce/repeat.py", "commerce/referral.py", "growth/loops.py",
                "scale/trajectory.py", "commerce/cohorts.py", "runtime/orders.py"):
        v = reachability.reached(rel)
        assert v["reached"], v


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
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
