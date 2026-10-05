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
             refunded=False, extra_lines=(), status="paid", is_paid=True, refunds=None,
             updated_days_ago=None, created_at=None):
    """A receipt in Etsy v3's ShopReceipt shape: status, is_paid, refunds[], update_timestamp.

    `refunds` is a list of cents, or of (cents, transaction_id) for a refund that names its
    line; `refunded=True` is the whole first line refunded. `status=None` omits the field.
    """
    lines = [{"transaction_id": rid * 10, "listing_id": listing_id, "quantity": 1,
              "price": {"amount": amount_cents, "divisor": 100, "currency_code": currency}}]
    for i, (lid, cents) in enumerate(extra_lines, start=1):
        lines.append({"transaction_id": rid * 10 + i, "listing_id": lid, "quantity": 1,
                      "price": {"amount": cents, "divisor": 100, "currency_code": currency}})
    refund_rows = []
    if refunded:
        refund_rows.append({"amount": {"amount": amount_cents, "divisor": 100,
                                       "currency_code": currency}})
    for r in refunds or ():
        cents, tid = (r if isinstance(r, tuple) else (r, None))
        row = {"amount": {"amount": cents, "divisor": 100, "currency_code": currency},
               "created_timestamp": int(NOW.timestamp()), "reason": "test", "status": "done"}
        if tid is not None:
            row["transaction_id"] = tid
        refund_rows.append(row)
    created = created_at or (NOW - timedelta(days=days_ago))
    updated = created if updated_days_ago is None else NOW - timedelta(days=updated_days_ago)
    out = {"receipt_id": rid, "buyer_user_id": buyer, "buyer_email": "never@stored.example",
           "name": "Never Stored",
           "create_timestamp": int(created.timestamp()),
           "update_timestamp": int(max(created, updated).timestamp()),
           "is_paid": is_paid, "is_shipped": False,
           "refunds": refund_rows, "transactions": lines}
    if status is not None:
        out["status"] = status
    return out


def _open_gate(db):
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", detail={"ok": True}))
        s.add(OAuthCredential(provider="etsy", refresh_token_sealed="sealed",
                              token_fingerprint="abcd1234",
                              scopes="listings_r listings_w shops_r transactions_r"))


def _in_band(cir):
    """The fixture's yarn declared at the weight its stated gauge holds.

    Since the gauge gate (gates.certificate.gauge_findings) a 16 sc/10cm design declared in
    worsted (11-14) is refused certification, which left this file's certified fixtures
    uncertified and two order tests failing on the fixture rather than on orders. The
    gate's own remedy is to declare the weight that holds the gauge: light/DK (12-17).
    The gate is not relaxed; the fixture is made honest.
    """
    import dataclasses

    from brambleloop.gates.certificate import gauge_findings

    if cir.gauge is None or not gauge_findings(cir):
        return cir
    fixed = dataclasses.replace(
        cir, gauge=dataclasses.replace(cir.gauge, yarn_weight="dk"),
        materials=[dataclasses.replace(m, yarn_weight="dk") if m.yarn_weight else m
                   for m in cir.materials])
    assert not gauge_findings(fixed), gauge_findings(fixed)
    return fixed


def _certify(db, cir, correction=None):
    _n[0] += 1
    cir = _in_band(cir)
    inputs = {"cir": cir.to_dict()}
    if correction is not None:
        inputs["correction"] = correction
    JobQueue(db).enqueue("quality_director", "gate.certify", inputs,
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
    # #271 (CB2-O06): an Etsy receipt names no acquisition channel, so the orders are
    # counted apart as unattributed -- paid events beside the net outcome -- and NO loop is
    # credited with them; the organic marketplace loop is not assumed.
    with db.session() as s:
        etsy = s.scalar(select(GrowthLoop).where(GrowthLoop.key == "etsy_organic"))
        assert etsy.orders == 0 and etsy.contribution_cad == 0
    un = r["loops"]["unattributed"]
    assert un["orders"] == 44 and un["refunded"] == 1 and un["net_orders"] == 43
    assert un["contribution"] > 0 and "assumed organic" in un["why"]
    assert r["loops"]["money_basis"]["fees"] == "estimated"
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
        # CB2-O08: the guard withheld the discard verdict from the stored classification
        # itself, so nothing reading the label can retire the design.
        assert review.classifications.get("OFFER_UNTESTED", 0) >= 1
    runner = next(c for c in got["classifications_detail"] if c["slug"] == "harvest-table-runner")
    assert runner["label"] == "OFFER_UNTESTED"
    assert runner["evidence"]["discard_verdict_withheld"] == "APPEAL_PROBLEM"
    assert not any("retire" in i.lower() for i in runner["interventions"])
    del out


CORRECTION = {"of_versions": ["1.0.0"],
              "what_changed": "Row 12 read 84 stitches and should read 86 stitches."}


def test_a_correcting_version_prepares_the_notice_for_its_buyers():
    """#42: gate.certify of a DECLARED correction finds the buyers of the version it names."""
    import dataclasses

    db, cir, _ = _ingested()
    corrected = dataclasses.replace(cir, version="1.0.1")
    _certify(db, corrected, correction={**CORRECTION, "of_versions": [cir.version]})
    with db.session() as s:
        rows = list(s.scalars(select(OrderVersion).where(
            OrderVersion.product_slug == cir.slug)))
        action = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"correction_notice:{cir.slug}@1.0.1"))
    assert rows and all(r.current_safe_version == "1.0.1" for r in rows)
    notices = [(r.detail or {}).get("correction_notice", {}) for r in rows]
    assert all(n.get("sent") is False for n in notices)
    # CB2-O09: preparation and delivery are separate states, and nothing was delivered.
    assert all(n.get("state") == "prepared" for n in notices)
    assert all(n.get("delivery", {}).get("state") == "not_sent" for n in notices)
    assert all(r.correction_notice_sent_at is None for r in rows)
    assert action is not None and "40 buyer" in action.action
    got = _audit(db, "buyer_trust.correction_prepared")
    assert got["affected_count"] == 40
    assert got["states"] == {"preparation": "prepared", "delivery": "not_sent"}


def test_a_routine_newer_version_is_not_a_correction():
    """CB2-O09: without a declared correction relation no buyer is moved or notified; a
    declared correction of a version nobody holds prepares nothing; an undeclared relation
    on an ineligible (uncertified) release is refused."""
    import dataclasses

    from brambleloop.commerce import buyer_trust

    db, cir, _ = _ingested()
    _certify(db, dataclasses.replace(cir, version="1.0.1"))          # routine release
    with db.session() as s:
        rows = list(s.scalars(select(OrderVersion).where(
            OrderVersion.product_slug == cir.slug)))
        actions = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("correction_notice:%"))))
    assert rows and all(r.current_safe_version == cir.version for r in rows)
    assert not any("correction_notice" in (r.detail or {}) for r in rows)
    assert actions == [] and _audit(db, "buyer_trust.correction_prepared") is None
    # A declared correction naming a version nobody bought prepares nothing either.
    got = buyer_trust.on_certified(db, product_slug=cir.slug, version="1.0.1",
                                   correction={**CORRECTION, "of_versions": ["0.9.0"]})
    assert got["correction"] is True and got["affected_count"] == 0 and got["notice"] is None
    # And a correction declared for a version that is not a certified stored release is
    # not releasable, so nothing is prepared and the reason says why.
    got = buyer_trust.on_certified(db, product_slug=cir.slug, version="1.0.2",
                                   correction={**CORRECTION, "of_versions": [cir.version]})
    assert got["eligible"] is False and got["affected_count"] == 0
    assert "not releasable" in got["why"]
    with db.session() as s:
        assert all(r.current_safe_version == cir.version for r in s.scalars(
            select(OrderVersion).where(OrderVersion.product_slug == cir.slug)))


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
    """#104 #132: the computable metrics by monthly cohort, from the lifecycle rows, never {}.

    CB2-O10: engineering survival is the month's drafted CIRs over the concepts generated,
    not tournament survival, which is reported apart as a labelled proxy.
    """
    db = _db()
    months = [NOW - timedelta(days=70), NOW - timedelta(days=5)]
    for at, novelty, survived, drafted in ((months[0], 0.50, 8, 6), (months[1], 0.20, 8, 2)):
        with db.session() as s:
            s.add(AuditLog(actor="creative_director", action="creative.tournament", at=at,
                           detail={"field": {"generated": 10},
                                   "survivors": [{"key": f"k{i}"} for i in range(survived)],
                                   "research_survivors": [{"key": "k", "novelty_distance":
                                                           novelty}]}))
            for i in range(drafted):
                s.add(AuditLog(actor="crochet_engineer", action="cir.drafted", at=at,
                               artifact=f"concept-{at.month}-{i}@1.0.0"))
    _run(db, "creative_director", "creative.north_star")
    got = _audit(db, "creative.north_star")
    assert got["answerable"] is True and len(got["cohorts"]) == 2
    assert set(got["regressing"]) >= {"novelty_distance", "concept_to_engineering_survival"}
    assert got["incident"] == "opened"
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == "creative.north_star_regression"))
        assert inc is not None and not inc.halts_publication
    from brambleloop.creative import standard

    ns = standard.north_star_from_db(db)
    by = ns["by_cohort"]
    assert [by[m]["concept_to_engineering_survival"] for m in ns["cohorts"]] == [0.6, 0.2]
    # The tournament's own survival rate did not move (8/10 both months) and is a proxy,
    # named as one and kept out of the north-star metrics.
    assert all("tournament_survival" not in by[m] for m in ns["cohorts"])
    assert [ns["proxies_by_cohort"][m]["tournament_survival"] for m in ns["cohorts"]] == [0.8, 0.8]
    assert "tournament_survival" in ns["proxies"] and "listing_drafted_share" in ns["proxies"]


def test_launch_survival_needs_a_publication_not_a_draft():
    """CB2-O10: a drafted listing is not a launch; the draft share is a labelled proxy."""
    from brambleloop.core.models import Product
    from brambleloop.creative import standard

    db = _db()
    at = NOW - timedelta(days=3)
    with db.session() as s:
        for slug in ("p-one", "p-two"):
            s.add(Product(slug=slug, title=slug, status="certified", created_at=at))
            s.add(Listing(product_slug=slug, version="1.0.0", title=slug, description="",
                          price_cad=9.0, state="draft", created_at=at))
    cohorts, proxies = standard.north_star_cohorts(db, with_proxies=True)
    m = at.strftime("%Y-%m")
    assert cohorts[m]["concept_to_launch_survival"] == 0.0
    assert proxies[m]["listing_drafted_share"] == 1.0
    with db.session() as s:
        s.add(AuditLog(actor="listing", action="store.published", at=at,
                       artifact="p-one@1.0.0", detail={"etsy_listing_id": "9"}))
    cohorts, _ = standard.north_star_cohorts(db, with_proxies=True)
    assert cohorts[m]["concept_to_launch_survival"] == 0.5


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


# ---------------------------------------------------------------------------
# Adversarial handler-level tests for the Codex findings CB2-O01..O10


def _ingest_with(db, receipts):
    feed = FakeFeed(receipts)
    orders_ingest.reader_factory = lambda _db: feed
    try:
        _run(db, "cfo", "commerce.orders_ingest")
    finally:
        orders_ingest.reader_factory = None
    return _audit(db, "commerce.orders_ingested"), feed


def _order(db, ref):
    with db.session() as s:
        o = s.scalar(select(Order).where(Order.external_ref == ref))
        led = s.scalar(select(LedgerEntry).where(LedgerEntry.evidence_ref == ref))
        return ((dict(revenue_cad=o.revenue_cad, contribution_cad=o.contribution_cad,
                      refunded=o.refunded, price_cad=o.price_cad, fees_cad=o.fees_cad,
                      detail=dict(o.detail or {}), is_repeat=o.is_repeat) if o else None),
                (dict(gross=led.gross_cad, fees=led.fees_cad, refunds=led.refunds_cad)
                 if led else None))


def test_a_late_refund_is_reconciled_through_every_reader():
    """CB2-O01 / O07: paid -> partial refund -> late full refund on an OLD receipt, each
    picked up by the cursor, applied once, and read consistently by every reader."""
    from brambleloop.runtime import release
    from brambleloop.scale import runrate

    db = _db()
    cir = _catalogue(db)
    _open_gate(db)
    base = _feed()
    ref = "etsy:2003:20030"                       # C's one sale, CA$5.00, 4 days ago
    first, _ = _ingest_with(db, base)
    assert first["orders_created"] == 44 and first["read_mode"].startswith("initial")
    o0, l0 = _order(db, ref)
    assert o0["revenue_cad"] == 5.0 and o0["refunded"] is False and l0["refunds"] == 0.0
    assert o0["detail"]["state"] == "paid" and o0["detail"]["money"]["fees"]["basis"] == "estimated"
    assert o0["detail"]["money"]["fx"]["basis"] in ("measured", "assumed")
    fees = o0["fees_cad"]
    assert fees > 0 and abs(o0["contribution_cad"] - (5.0 - fees)) < 0.01
    _run(db, "cfo", "commerce.order_readings")
    before = order_readings.latest(db)
    winners_before = before["winners"]["top"]

    # A partial refund of CA$2.00 arrives later on that receipt; only it changed.
    partial = _receipt(2003, 6002, "333", 500, days_ago=4, status="partially refunded",
                       refunds=[200], updated_days_ago=0)
    second, feed = _ingest_with(db, [partial])
    assert second["read_mode"].startswith("cursor") and second["since"] is not None
    assert second["orders_created"] == 0 and second["orders_reconciled"] == 1
    o1, l1 = _order(db, ref)
    assert o1["revenue_cad"] == 3.0 and o1["refunded"] is False
    assert o1["detail"]["state"] == "partially_refunded"
    assert abs(o1["contribution_cad"] - (3.0 - fees)) < 0.01 and l1["refunds"] == 2.0
    # Re-reading the same revision changes nothing: no double counting.
    again, _ = _ingest_with(db, [partial])
    assert again["orders_reconciled"] == 0 and _order(db, ref) == (o1, l1)

    # Then the rest comes back: a full refund. The loss (the fees) is kept as a loss.
    full = _receipt(2003, 6002, "333", 500, days_ago=4, status="fully refunded",
                    refunds=[200, 300], updated_days_ago=0)
    third, _ = _ingest_with(db, [full])
    assert third["orders_reconciled"] == 1
    o2, l2 = _order(db, ref)
    assert o2["revenue_cad"] == 0.0 and o2["refunded"] is True
    assert o2["detail"]["state"] == "fully_refunded" and l2["refunds"] == 5.0
    assert o2["contribution_cad"] < 0 and abs(o2["contribution_cad"] + fees) < 0.01
    # A fully-refunded status with no refund rows at all means the same thing.
    bare = _receipt(2004, 6003, "333", 500, days_ago=5, status="fully refunded",
                    updated_days_ago=0)
    _ingest_with(db, [bare])
    o3, l3 = _order(db, "etsy:2004:20040")
    assert o3["refunded"] is True and l3["refunds"] == 5.0

    # Every reader sees the same truth.
    _run(db, "cfo", "commerce.order_readings")
    r = order_readings.latest(db)
    rows = order_readings.orders(db)
    mine = next(x for x in rows if x["product_slug"] == "harvest-table-runner"
                and x["customer_ref"] == "etsy-user-6002")
    assert mine["state"] == "fully_refunded" and mine["refund_cad"] == 5.0
    # offers (#13): the runner has no buyer left and its contribution is a loss.
    runner = next(x for x in r["offers"]["results"] if x["design"] == "harvest-table-runner")
    assert runner["buyers"] == 0 and runner["revenue_per_buyer"] is None
    result = next(x for x in order_readings.offer_results(db)
                  if x.design_slug == "harvest-table-runner")
    assert result.buyers == 0 and result.revenue_cad == 0.0 and result.contribution_cad < 0
    assert r["offers"]["money_basis"]["fees"] == "estimated"
    # winners (#22): unchanged, and the runner has no counted order.
    assert r["winners"]["top"] == winners_before == cir.slug
    # cohorts / lifetime contribution (#11 #12): losses retained, still measured.
    assert r["cohorts"]["lifetime_contribution_per_buyer_cad"] > 0
    validation = r["cohorts"]["validation"]
    assert validation["customers"] == 43
    # loops (#271): two refunded events in the unattributed bucket, net outcome apart.
    un = r["loops"]["unattributed"]
    assert un["orders"] == 44 and un["refunded"] == 2 and un["net_orders"] == 42
    # pricing (#269): refunded orders are not price evidence.
    inputs = release._pricing_net_inputs(db, cir.slug)
    assert inputs["foreign_share"] is not None
    # reinvestment (#49): the ledger nets the refunds out.
    with db.session() as s:
        since = NOW - timedelta(days=30)
        gross = sum(x.gross_cad - x.refunds_cad for x in s.scalars(
            select(LedgerEntry).where(LedgerEntry.category == "sale"))
            if (x.at if x.at.tzinfo else x.at.replace(tzinfo=timezone.utc)) >= since)
    assert abs(r["reinvestment"]["gross_cad_30d"] - round(gross, 2)) < 0.01
    assert r["reinvestment"]["gross_cad_30d"] < before["reinvestment"]["gross_cad_30d"]
    # run-rate (the CAC / conversion terms): the refunds count in the refund rate.
    funnel = runrate.observed_funnel(db) if hasattr(runrate, "observed_funnel") else None
    if funnel is not None and isinstance(funnel, dict) and funnel.get("refund_rate") is not None:
        assert funnel["refund_rate"] > 0
    # The cursor is durable and advanced.
    cur = orders_ingest.cursor(db)
    assert cur["last_modified"] and cur["runs"] >= 5 and cur["last_full_sweep"]


def test_unpaid_cancelled_and_unknown_receipts_never_become_sales():
    """CB2-O02: only paid receipts in a recognised state are sales; the rest are held by
    name. A held receipt that later pays becomes a sale; a paid one later cancelled is
    voided, not deleted, and its money reads as returned."""
    db = _db()
    _catalogue(db)
    _open_gate(db)
    feed = [
        _receipt(3001, 7001, "111", 1200, status="open", is_paid=False),
        _receipt(3002, 7002, "111", 1200, status="payment processing", is_paid=False),
        _receipt(3003, 7003, "111", 1200, status="canceled", is_paid=True),
        _receipt(3004, 7004, "111", 1200, status="weird new state", is_paid=True),
        _receipt(3005, 7005, "111", 1200, status=None, is_paid=True),        # no status
        _receipt(3006, 7006, "111", 1200, status="paid", is_paid=False),     # contradictory
        _receipt(3007, 7007, "111", 1200, status="paid", is_paid=True),      # the one sale
    ]
    got, _ = _ingest_with(db, feed)
    assert got["orders_created"] == 1 and got["customers_created"] == 1
    assert got["held_by_state"] == {"cancelled": 1, "unknown": 3, "unpaid": 2}
    held = {h["ref"]: h for h in got["held"]}
    assert "not a sale" in held["etsy:3004:30040"]["why"]
    with db.session() as s:
        assert s.scalar(select(func.count(Order.id))) == 1
        assert s.scalar(select(func.count(Customer.id))) == 1
        assert s.scalar(select(func.count(LedgerEntry.id))) == 1
        assert s.scalar(select(func.count(OrderVersion.id))) == 1
    # The open receipt is paid a day later: Etsy changes its update_timestamp, the cursor
    # sees it, and only now is it a sale.
    paid_now = _receipt(3001, 7001, "111", 1200, status="paid", is_paid=True,
                        updated_days_ago=0)
    got, _ = _ingest_with(db, [paid_now])
    assert got["orders_created"] == 1 and got["held"] == []
    # The recorded sale 3007 is cancelled after the fact: voided in place.
    cancelled = _receipt(3007, 7007, "111", 1200, status="canceled", is_paid=True,
                         updated_days_ago=0)
    got, _ = _ingest_with(db, [cancelled])
    assert got["orders_created"] == 0 and got["orders_reconciled"] == 1
    o, led = _order(db, "etsy:3007:30070")
    assert o["refunded"] is True and o["revenue_cad"] == 0.0
    assert o["detail"]["state"] == "cancelled" and led["refunds"] == 12.0
    # A recorded sale whose receipt later reads as an unrecognised state is held, not
    # rewritten.
    got, _ = _ingest_with(db, [_receipt(3001, 7001, "111", 1200, status="mystery",
                                        is_paid=True, updated_days_ago=0)])
    assert got["held_by_state"] == {"unknown": 1}
    o, _ = _order(db, "etsy:3001:30010")
    assert o["detail"]["state"] == "paid" and o["revenue_cad"] == 12.0
    with db.session() as s:
        assert s.scalar(select(func.count(Order.id))) == 2


def test_a_crash_between_writes_then_a_rerun_converges_to_exactly_once():
    """CB2-O05: a line's customer, order, version and ledger rows are one transaction. A
    crash after the order and before the ledger leaves nothing behind; the next run writes
    every row once and the counts match a run that never crashed."""
    db = _db()
    _catalogue(db)
    _open_gate(db)
    feed = [_receipt(4000 + i, 8000 + i, "111", 1200, days_ago=1 + i) for i in range(6)]
    feed.append(_receipt(4100, 8000, "222", 900, days_ago=1))   # a repeat buyer
    calls = [0]

    def die_on_third(line):
        calls[0] += 1
        if calls[0] == 3:
            raise RuntimeError("simulated crash between the order and the ledger")

    orders_ingest.mid_line_hook = die_on_third
    try:
        try:
            orders_ingest.ingest(db, reader=FakeFeed(feed))
        except RuntimeError:
            pass
        else:
            raise AssertionError("the simulated crash did not propagate")
    finally:
        orders_ingest.mid_line_hook = None
    with db.session() as s:
        n_orders = s.scalar(select(func.count(Order.id)))
        n_versions = s.scalar(select(func.count(OrderVersion.id)))
        n_ledger = s.scalar(select(func.count(LedgerEntry.id)))
        n_customers = s.scalar(select(func.count(Customer.id)))
    # Two complete lines, and the third left NO partial row of any kind.
    assert n_orders == n_versions == n_ledger == n_customers == 2
    assert orders_ingest.cursor(db) == {}          # a run that died moved no cursor
    # The re-run (through the worker) converges.
    got, _ = _ingest_with(db, feed)
    assert got["orders_created"] == 5 and got["ran"] is True
    with db.session() as s:
        orders = list(s.scalars(select(Order)))
        assert len(orders) == 7
        assert s.scalar(select(func.count(OrderVersion.id))) == 7
        assert s.scalar(select(func.count(LedgerEntry.id))) == 7
        assert s.scalar(select(func.count(Customer.id))) == 6
        assert len({o.external_ref for o in orders}) == 7
    # And a third run adds nothing at all.
    got, _ = _ingest_with(db, feed)
    assert got["orders_created"] == 0 and got["ledger_entries"] == 0
    assert got["orders_reconciled"] == 0
    # The same repair applies to an order that exists without its version row (a row a
    # pre-transactional run could have left): re-reading writes the missing version.
    with db.session() as s:
        s.delete(s.scalar(select(OrderVersion).where(OrderVersion.order_ref == "etsy:4000:40000")))
    got, _ = _ingest_with(db, feed)
    with db.session() as s:
        assert s.scalar(select(func.count(OrderVersion.id))) == 7


def _first_purchase_facts(db):
    with db.session() as s:
        customers = {c.customer_ref: (c.first_product_slug, c.first_category, c.first_season,
                                      c.first_seen_at.replace(tzinfo=timezone.utc)
                                      if c.first_seen_at.tzinfo is None else c.first_seen_at)
                     for c in s.scalars(select(Customer))}
        from brambleloop.core.models import CohortMembership

        memberships = sorted((
            s.get(Customer, m.customer_id).customer_ref, m.axis, m.value)
            for m in s.scalars(select(CohortMembership)))
        repeats = {o.external_ref: o.is_repeat for o in s.scalars(select(Order))}
    return customers, memberships, repeats


def test_out_of_order_arrival_yields_the_same_first_purchase_cohort():
    """CB2-O04: the first purchase is the earliest PAID order, whatever order the receipts
    arrived in -- in one run or across a newest-first backfill."""
    older = _receipt(5001, 9001, "222", 900, days_ago=40)     # B first, 40 days ago
    newer = _receipt(5002, 9001, "111", 1200, days_ago=2)     # then A, 2 days ago
    other = _receipt(5003, 9002, "333", 500, days_ago=20)
    results = []
    for arrival in ([older, newer, other], [newer, other, older]):
        db = _db()
        _catalogue(db)
        _open_gate(db)
        _ingest_with(db, arrival)
        results.append(_first_purchase_facts(db))
    assert results[0] == results[1]
    customers, memberships, repeats = results[0]
    assert customers["etsy-user-9001"][0] == "cloudline-baby-blanket"
    assert ("etsy-user-9001", "first_product", "cloudline-baby-blanket") in memberships
    assert repeats["etsy:5001:50010"] is False and repeats["etsy:5002:50020"] is True
    # A newest-first backfill across two runs lands on the same facts.
    db = _db()
    cir = _catalogue(db)
    _open_gate(db)
    _ingest_with(db, [newer, other])
    customers_mid, _m, repeats_mid = _first_purchase_facts(db)
    # With only the newer receipt seen, A (listing 111) is provisionally their first...
    assert customers_mid["etsy-user-9001"][0] == cir.slug
    assert repeats_mid["etsy:5002:50020"] is False           # so far it is their first
    # ...and the older receipt arriving later re-derives every fact, not merely appends.
    _ingest_with(db, [older])
    assert _first_purchase_facts(db) == results[0]
    # And the validation cohort is ranked by earliest purchase, not by insertion.
    with db.session() as s:
        from brambleloop.core.models import CohortMembership

        first_hundred = {s.get(Customer, m.customer_id).customer_ref for m in s.scalars(
            select(CohortMembership).where(CohortMembership.axis == "validation"))}
    assert first_hundred == {"etsy-user-9001", "etsy-user-9002"}


def test_unknown_acquisition_stays_unknown_and_loop_counters_reconcile_down():
    """CB2-O06: an Etsy receipt names no channel, so the buyer's acquisition is `unknown`
    with its basis recorded; no loop is credited; and a loop's counters follow the facts
    down when an order is refunded."""
    from brambleloop.growth import loops

    db, cir, _ = _ingested()
    with db.session() as s:
        customers = list(s.scalars(select(Customer)))
        orders = list(s.scalars(select(Order)))
    assert all(c.acquisition_source == "unknown" for c in customers)
    assert all(o.acquisition_source == "unknown" for o in orders)
    attribution = orders[0].detail["attribution"]
    assert attribution["channel"] == "unknown" and attribution["confidence"] == "none"
    assert attribution["basis"] == "etsy_receipt"
    assert "etsy" not in order_readings.SOURCE_TO_LOOP
    _run(db, "cfo", "commerce.order_readings")
    with db.session() as s:
        assert all(row.orders == 0 for row in s.scalars(select(GrowthLoop)))
    # A loop that was credited (by an attributed source) is corrected downward when the
    # facts change: the reconcile is signed, not add-only.
    loops.observe(db, "pinterest", visits=50, orders=3)
    got = loops.reconcile(db, "pinterest", orders=1, contribution_cad=4.0)
    assert got["delta"]["orders"] == -2 and got["strength"] == "attempted"
    got = loops.reconcile(db, "pinterest", orders=0, contribution_cad=0.0, visits=0)
    assert got["strength"] == "untested" and got["delta"]["visits"] == -50


def test_the_delivered_version_comes_from_history_or_is_unknown():
    """CB2-O03: the version a sale delivered is the one listed under that Etsy listing at
    the time of the sale, from the listing/publication history -- never the current one --
    and a sale older than any record is explicitly unknown and routed to correction review."""
    from brambleloop.commerce import buyer_trust
    from brambleloop.core.models import PatternVersion, Product

    db = _db()
    _open_gate(db)
    with db.session() as s:
        p = Product(slug="fir", title="Fir", status="certified")
        s.add(p)
        s.flush()
        for v, h in (("1.0.0", "a" * 64), ("1.0.1", "b" * 64), ("1.0.2", "c" * 64)):
            s.add(PatternVersion(product_id=p.id, version=v, cir_json={}, release_hash=h,
                                 certified=True))
        s.add(Listing(product_slug="fir", version="1.0.0", title="F", description="",
                      price_cad=9.0, state="published", etsy_listing_id="777",
                      created_at=NOW - timedelta(days=60)))
        s.add(Listing(product_slug="fir", version="1.0.1", title="F", description="",
                      price_cad=9.0, state="published", etsy_listing_id="777",
                      created_at=NOW - timedelta(days=10)))
        # The publication event is the immutable record; 1.0.1 went live 8 days ago.
        s.add(AuditLog(actor="listing", action="store.published", artifact="fir@1.0.1",
                       at=NOW - timedelta(days=8), detail={"etsy_listing_id": "777"}))
    feed = [_receipt(6001, 9101, "777", 900, days_ago=30),    # while 1.0.0 was listed
            _receipt(6002, 9102, "777", 900, days_ago=9),     # 1.0.1 drafted, not yet live
            _receipt(6003, 9103, "777", 900, days_ago=5),     # 1.0.1 live
            _receipt(6004, 9104, "777", 900, days_ago=90)]    # before any record
    got, _ = _ingest_with(db, feed)
    assert got["orders_created"] == 4 and got["versions_recorded"] == 3
    assert got["versions_unknown"] == ["etsy:6004:60040"]
    with db.session() as s:
        by_ref = {o.external_ref: o for o in s.scalars(select(Order))}
        versions = {v.order_ref: v.version for v in s.scalars(select(OrderVersion))}
    assert versions == {"etsy:6001:60010": "1.0.0", "etsy:6002:60020": "1.0.0",
                        "etsy:6003:60030": "1.0.1"}
    assert by_ref["etsy:6004:60040"].version == ""
    assert by_ref["etsy:6004:60040"].detail["version_basis"].startswith("unknown")
    assert by_ref["etsy:6003:60030"].detail["version_basis"] == "store.published"
    # A correction of 1.0.0 reaches its two buyers, and the unknown one is routed to review
    # rather than treated as unaffected.
    got = buyer_trust.on_certified(db, product_slug="fir", version="1.0.2",
                                   release_hash="c" * 64,
                                   correction={**CORRECTION, "of_versions": ["1.0.0"]})
    assert sorted(got["affected_orders"]) == ["etsy:6001:60010", "etsy:6002:60020"]
    assert got["version_unknown_orders"] == ["etsy:6004:60040"]
    with db.session() as s:
        action = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == got["owner_action"]))
    assert "1 further order(s)" in action.action and "unrecorded version" in action.action


def test_pricing_refusals_stop_the_chain_rather_than_annotate():
    """CB2-O08: a net floor no band price clears stops pricing.position (no listing job);
    a discount-guard or promotion refusal drops the requested sale before the listing."""
    from brambleloop.runtime import release

    db = _db()
    cir = _catalogue(db)
    original = release.CATEGORY_BANDS_CAD.get(nf.build().slug), dict(release.CATEGORY_BANDS_CAD)
    release.DEFAULT_BAND_SAVED = release.DEFAULT_BAND
    try:
        for k in list(release.CATEGORY_BANDS_CAD):
            release.CATEGORY_BANDS_CAD[k] = (0.50, 0.90)
        release.DEFAULT_BAND = (0.50, 0.90)
        out = _run(db, "pricing", "pricing.position", {"slug": cir.slug, "version": cir.version,
                                                       "release": "r1"})
    finally:
        release.CATEGORY_BANDS_CAD.clear()
        release.CATEGORY_BANDS_CAD.update(original[1])
        release.DEFAULT_BAND = release.DEFAULT_BAND_SAVED
    assert out.get("stopped") is True and "net contribution" in out["refused"]
    refused = _audit(db, "pricing.refused")
    assert refused and refused["stopped"] == "listing.seo not enqueued"
    with db.session() as s:
        assert s.scalar(select(Job).where(Job.job_type == "listing.seo")) is None
    d = pricing.decide_price("z", category_band_cad=(0.5, 0.9), proposed_cad=0.8)
    assert d.refused and d.to_dict()["refused"] == d.refused

    # The discount guard: a recorded reading refuses a sale price for this product, and the
    # job was asked to run one. The promotion is dropped, audited, and the listing is told.
    reading = order_readings.read(db)
    reading["ladder"]["discount_refused"] = [cir.slug]
    order_readings.record(db, order_readings._now(None) and __import__("json").loads(
        __import__("json").dumps(reading, default=str)))
    assert cir.slug in order_readings.directives(db)["discount_refused"]
    out = _run(db, "pricing", "pricing.position",
               {"slug": cir.slug, "version": cir.version, "release": "r2",
                "promotion": {"promo_price_cad": 6.0, "days": 5}})
    assert out.get("stopped") is None
    dropped = _audit(db, "pricing.promotion_refused")
    assert dropped and dropped["discount_refused"] is True
    with db.session() as s:
        seo = s.scalar(select(Job).where(Job.job_type == "listing.seo"))
    assert seo is not None and seo.inputs["sale_allowed"] is False
    assert "promotion" not in seo.inputs
    assert any("full price only" in r for r in seo.inputs["pricing_reasons"])


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
