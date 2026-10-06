"""Etsy Ads readiness, economics, spend PROPOSALS and the Finance challenge (v1.1 lane H).

Requirements: directive v1.1 section 12 (ads are evidence- and economics-aware; no paid
campaign without owner authority; ceilings enforced in code even after authority exists),
F-912 (spend governor integration), F-918 (KPIs with anti-gaming guardrails), F-919
(cross-agent challenge: Growth proposes, Finance can block), F-930 (24/7 is not reckless), and
the v1.0 Etsy Ads body: F-262..F-274, F-529/F-530, F-569/F-570, F-614..F-616, F-685..F-687.

What this module is, and is not:

* It **prepares and proposes**. It never executes. There is no Etsy Ads API write path in this
  repository (the audited Etsy surface registry has none) and this module must not add one:
  nothing here opens a socket, enqueues `ads.campaign`, calls `paid_media.authorise_spend`, or
  writes a spend row. `tests/test_v11_ads_no_execution.py` reads this source to keep it so.
* **Readiness** is per listing and every gate is PASS / FAIL / UNKNOWN. UNKNOWN is never
  PASS: a listing whose economics cannot be computed from real price and fee data is not
  ready, and nothing assumes a number to make it ready.
* **Economics** carry their basis: `measured` (orders with Etsy-ledger fees), `modelled`
  (listing price x the dated fee reading in `commerce.fee_schedule`) or `unknown`. Break-even
  ROAS is computed from those, with the worst case (every unmodelled fee at its reported rate)
  beside it. Offsite Ads exposure is modelled from the dated advertising reading and labelled
  as exposure, never as a cost this shop controls.
* **Proposals** are rows. Every proposal is challenged by Finance through
  `brambleloop.finance.accounting.policy.check_spend(db, proposal)` (lane E). Until that exists
  the challenge falls back to the Finance rules available today (owner ad caps, the
  conservative paid-media caps, the governor's anomaly hold) and says so in the record. A
  local hard ceiling check runs on every proposal whatever Finance answers, and the most
  restrictive verdict wins: Growth cannot out-vote Finance, and Finance cannot lift a ceiling.
* A proposal Finance does not block becomes an **owner approval item** (`OwnerAction`). Owner
  approval of the item is still not execution: there is no executor.

Provider contract for the Owner Command Center (lane C): `summary(db) -> dict` with
`status`, `as_of`, `basis`, `items`, `sources`. Work contract for the autonomy loop (lane A):
`next_work(db, now=None) -> list[dict]`, each item `{key, department, kind, action, why,
spend_cad, blocked_by}`; every item is internal, zero-spend work.

The eligibility half (`state`, `tick`, `record_evidence`) is reused from Codex's staged
`growth/ads_readiness.py` (origin/codex/continuous-operations-audit @ 8877f05): a countdown
is a recheck date, never permission.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, select, text
from sqlalchemy.orm import Mapped, mapped_column

from ..core import models as _core_models
from ..core.db import Base, is_postgres
from ..core.models import OwnerAction, Product, utcnow

# ---------------------------------------------------------------------------------------------
# Tables. Additive and owned here; registered by `ensure_tables` (and, at integration, by the
# WIRING REQUEST in handoff_H.md adding this module to `core.db.create_all`).
# ---------------------------------------------------------------------------------------------

if hasattr(_core_models, "MarketplaceCapability"):  # lane A may land Codex's core model
    MarketplaceCapability = _core_models.MarketplaceCapability
else:
    class MarketplaceCapability(Base):
        """Dated marketplace evidence, independent of process lifetime and ad authority."""
        __tablename__ = "marketplace_capabilities"
        key: Mapped[str] = mapped_column(String(80), primary_key=True)
        status: Mapped[str] = mapped_column(String(40))
        eligible_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                               nullable=True)
        last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                                  nullable=True)
        evidence_source: Mapped[str] = mapped_column(Text)
        detail: Mapped[dict] = mapped_column(JSON, default=dict)


class AdSpendProposal(Base):
    """A Growth proposal to spend on Etsy Ads. A row, never a campaign."""
    __tablename__ = "ads_spend_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    product_slug: Mapped[str] = mapped_column(String(80), index=True)
    proposed_by: Mapped[str] = mapped_column(String(40), default="growth")
    funding: Mapped[str] = mapped_column(String(24))  # etsy_plus_credit | owner_cash
    daily_budget_cad: Mapped[float] = mapped_column(Float)
    days: Mapped[int] = mapped_column(Integer)
    total_cad: Mapped[float] = mapped_column(Float)
    max_cac_cad: Mapped[float] = mapped_column(Float)
    hypothesis: Mapped[str] = mapped_column(Text)
    stop_condition: Mapped[str] = mapped_column(Text)
    attribution_window_days: Mapped[int] = mapped_column(Integer, default=30)
    economics: Mapped[dict] = mapped_column(JSON, default=dict)
    readiness: Mapped[dict] = mapped_column(JSON, default=dict)
    # PROPOSED -> FINANCE_BLOCKED | NOT_READY | AWAITING_OWNER ; SUPERSEDED on re-challenge
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED", index=True)
    owner_action_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    executed: Mapped[bool] = mapped_column(Boolean, default=False)  # always False: no executor


class AdFinanceChallenge(Base):
    """Finance's challenge of one Growth proposal (F-919), persisted with its reasons."""
    __tablename__ = "ads_finance_challenges"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    proposal_id: Mapped[int] = mapped_column(Integer, index=True)
    challenger: Mapped[str] = mapped_column(String(40), default="finance")
    checker: Mapped[str] = mapped_column(String(120))
    verdict: Mapped[str] = mapped_column(String(12), index=True)  # ALLOW | ESCALATE | BLOCK
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


_TABLES = (MarketplaceCapability.__table__, AdSpendProposal.__table__,
           AdFinanceChallenge.__table__)
_ENSURED: set[int] = set()


def ensure_tables(db) -> None:
    """Create this module's additive tables if missing (idempotent, checkfirst)."""
    if id(db.engine) in _ENSURED:
        return
    Base.metadata.create_all(db.engine, tables=list(_TABLES), checkfirst=True)
    _ENSURED.add(id(db.engine))


# ---------------------------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------------------------

KEY = "etsy_ads"
REFRESH_KEY = "etsy_ads_eligibility_evidence"
REPORTED_RECHECK = datetime(2026, 10, 4, tzinfo=timezone.utc)
SOURCE = "chatgpt-conversation://6aa9ea7a-c154-83ea-901c-53ee8ff2bb22"
EVIDENCE_MAX_AGE = timedelta(hours=24)

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
ALLOW, ESCALATE, BLOCK = "ALLOW", "ESCALATE", "BLOCK"
_SEVERITY = {ALLOW: 0, ESCALATE: 1, BLOCK: 2}
FUNDING = ("etsy_plus_credit", "owner_cash")
FINANCE_CHECK = "brambleloop.finance.accounting.policy.check_spend"
FALLBACK_CHECK = "fallback:growth_ops.ad_authority+paid_media.CONSERVATIVE_CAPS+governor.hold"
# F-614: official Etsy Plus entitlement, USD per monthly cycle. A reading, not a balance.
PLUS_CREDIT_USD_PER_CYCLE = 5.0
PROPOSAL_STALE_AFTER = timedelta(days=7)
# F-918: ROAS confidence floor, the paid-media scaling floor already in commerce.paid_media.
MIN_ATTRIBUTED_ORDERS_FOR_CONFIDENCE = 15
SOURCES = ("listings", "listing_set_certificates", "listing_outcomes", "orders",
           "incidents", "spend_limits", "cost_entries(kind=ads)", "marketplace_capabilities",
           "ads_spend_proposals", "ads_finance_challenges", "owner_actions",
           "gates.policy_knowledge:fees", "gates.policy_knowledge:advertising_rules")


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and not value.tzinfo else value


# ---------------------------------------------------------------------------------------------
# Eligibility (reused from Codex 8877f05): a countdown is a recheck date, never permission.
# ---------------------------------------------------------------------------------------------

def locked_row(s, db):
    # Serialize first creation as well as updates and owner-inbox deduplication.
    if is_postgres(db.engine):
        s.execute(text("SELECT pg_advisory_xact_lock(284191002)"))
    else:
        s.execute(text("BEGIN IMMEDIATE"))
    row = s.get(MarketplaceCapability, KEY)
    if row is None:
        row = MarketplaceCapability(
            key=KEY, status="WAITING_REPORTED", eligible_from=REPORTED_RECHECK,
            evidence_source=SOURCE, last_verified_at=None,
            detail={"reported_on": "2026-09-25", "reported_days_remaining": 9,
                    "date_is_estimate": True,
                    "evidence_kind": "conversation_report_of_shop_manager",
                    "etsy_message": "9 days left until you can start advertising your listings"})
        s.add(row)
        s.flush()
    return row


def snapshot(row, now):
    due = aware(row.eligible_from)
    detail = row.detail or {}
    return {
        "etsy_ads_status": row.status,
        "eligible_from": due.isoformat() if due else None,
        "days_remaining": max(0, ceil((due - now).total_seconds() / 86400)) if due else None,
        "evidence_source": row.evidence_source,
        "last_verified_at": aware(row.last_verified_at).isoformat() if row.last_verified_at else None,
        "date_is_estimate": detail.get("date_is_estimate", False),
        "last_recheck_at": detail.get("last_recheck_at"),
        "collector_status": "NO_SANCTIONED_ADS_COLLECTOR",
        "activation_authorised": False,
        "credit_accounting": {"etsy_plus_credit": "unverified; separate from owner cash",
                              "official_entitlement_usd_per_cycle": PLUS_CREDIT_USD_PER_CYCLE,
                              "owner_cash_budget_cad": None},
    }


def state(db, *, now=None):
    ensure_tables(db)
    now = aware(now or utcnow())
    with db.session() as s:
        row = s.get(MarketplaceCapability, KEY)
        if row is None:
            return {"etsy_ads_status": "NOT_INITIALISED", "activation_authorised": False}
        return snapshot(row, now)


def tick(db, *, now=None):
    """Hourly: re-evaluate persisted eligibility evidence; route a due refresh to the owner."""
    ensure_tables(db)
    now = aware(now or utcnow())
    with db.session() as s:
        row = locked_row(s, db)
        due = aware(row.eligible_from)
        # Even an old eligibility observation must be refreshed before future action.
        stale = bool(row.last_verified_at
                     and (now - aware(row.last_verified_at)) >= EVIDENCE_MAX_AGE)
        needs_refresh = bool((due is not None and now >= due) or stale
                             or (due is None and row.last_verified_at is None))
        if needs_refresh:
            row.status = "RECHECK_REQUIRED"
            existing = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == REFRESH_KEY, OwnerAction.done == False))  # noqa: E712
            if existing is None:
                s.add(OwnerAction(requirement_key=REFRESH_KEY,
                    action=("Open Etsy Shop Manager > Marketing > Etsy Ads and record the current "
                            "eligibility message and timestamp. Do not activate ads."),
                    reason=("The stored countdown is due or evidence is stale. The audited Etsy "
                            "API has no Ads eligibility collector."),
                    max_cost_cad=0, minutes=2,
                    consequence_of_delay=("Campaign preparation continues; eligibility remains "
                                          "unverified and ads remain inactive."),
                    blocks="Etsy Ads eligibility verification only"))
        candidates = [{"slug": p.slug, "title": p.title, "product_status": p.status,
                       "ready_to_advertise": False}
                      for p in s.scalars(select(Product).order_by(Product.id))]
        prep = {"candidates": candidates, "prepared_at": now.isoformat(),
                "next_work": ["Use existing keyword and benchmark evidence",
                              "Require Product Truth, Visual and owner listing approval",
                              "Measure organic baseline and contribution before selecting spend",
                              "Design bounded experiment; verify Plus credit separately from cash"],
                "campaign_activated": False, "budget_authorised_cad": 0}
        row.detail = {**(row.detail or {}), "last_recheck_at": now.isoformat(),
                      "preparation": prep}
        return {**snapshot(row, now), "preparation": prep}


def record_evidence(db, *, status, evidence_source, verified_at, eligible_from=None, now=None):
    """Operator-attested Etsy UI evidence; caller must authenticate before this function."""
    ensure_tables(db)
    now = aware(now or utcnow())
    verified_at = aware(verified_at)
    eligible_from = aware(eligible_from)
    if status not in {"WAITING", "ELIGIBLE", "INELIGIBLE"}:
        raise ValueError("status must be WAITING, ELIGIBLE or INELIGIBLE")
    if not (evidence_source or "").strip() or len(evidence_source) > 2000:
        raise ValueError("dated Etsy evidence reference required")
    if verified_at is None or verified_at > now or (now - verified_at) > EVIDENCE_MAX_AGE:
        raise ValueError("evidence must be from the last 24 hours and not the future")
    if status == "WAITING" and (eligible_from is None or eligible_from <= verified_at):
        raise ValueError("waiting evidence requires a future recheck date")
    with db.session() as s:
        row = locked_row(s, db)
        if row.last_verified_at and verified_at < aware(row.last_verified_at):
            raise ValueError("older evidence cannot replace newer evidence")
        history = list((row.detail or {}).get("evidence_history", []))
        history.append({"status": status, "source": evidence_source,
                        "verified_at": verified_at.isoformat()})
        row.status = status
        row.evidence_source = evidence_source
        row.last_verified_at = verified_at
        row.eligible_from = eligible_from if status == "WAITING" else None
        row.detail = {**(row.detail or {}), "date_is_estimate": status == "WAITING",
                      "evidence_kind": "operator_attested_etsy_ui", "evidence_history": history}
        for action in s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key == REFRESH_KEY, OwnerAction.done == False)):  # noqa: E712
            action.done = True
        return snapshot(row, now)


def _eligibility_gate(db, now) -> dict:
    snap = state(db, now=now)
    status = snap["etsy_ads_status"]
    verified = snap.get("last_verified_at")
    fresh = bool(verified and now - datetime.fromisoformat(verified) < EVIDENCE_MAX_AGE)
    if status == "ELIGIBLE" and fresh:
        return {"gate": "ads_eligibility", "status": PASS,
                "why": f"operator-attested ELIGIBLE at {verified}", "evidence": snap}
    if status in ("NOT_INITIALISED", "WAITING_REPORTED", "RECHECK_REQUIRED") or not fresh:
        return {"gate": "ads_eligibility", "status": UNKNOWN,
                "why": (f"eligibility is {status}; no fresh (<24h) operator-attested Etsy UI "
                        f"evidence. A countdown is not eligibility"), "evidence": snap}
    return {"gate": "ads_eligibility", "status": FAIL,
            "why": f"Etsy reports {status}", "evidence": snap}


# ---------------------------------------------------------------------------------------------
# Unit economics and break-even ROAS, with basis labels.
# ---------------------------------------------------------------------------------------------

def _latest_listing(s, slug):
    from ..core.models import Listing
    rows = list(s.scalars(select(Listing).where(Listing.product_slug == slug)
                          .order_by(Listing.id.desc()).limit(1)))
    return rows[0] if rows else None


def offsite_exposure(price_cad: float, *, trailing_365_sales_usd: float | None) -> dict:
    """What an Offsite-Ads-attributed order would pay, from the dated advertising reading.

    Exposure, not a cost this shop chooses: Etsy decides which orders are attributed. Below
    the threshold participation is optional and the standard rate applies; above it the
    reduced rate applies and participation is mandatory. With the shop's trailing sales
    unknown, both rates are reported and the higher one is the conservative figure.
    """
    from ..commerce import paid_media
    from ..finance.currency import ASSUMED_USD_PER_CAD
    try:
        terms = paid_media.offsite_ads_terms()
    except Exception as e:  # noqa: BLE001 - a reading that changed shape is UNKNOWN, not 0
        return {"status": UNKNOWN, "basis": "unknown", "why": f"offsite terms unreadable: {e}"}
    cap_cad = terms["fee_cap_usd"] / ASSUMED_USD_PER_CAD
    std = round(min(price_cad * terms["standard_fee_rate"], cap_cad), 4)
    red = round(min(price_cad * terms["reduced_fee_rate"], cap_cad), 4)
    if trailing_365_sales_usd is None:
        applied, participation = None, "UNKNOWN (trailing 365-day sales not measured)"
    else:
        above = trailing_365_sales_usd >= terms["threshold_usd"]
        applied = red if above else std
        participation = "mandatory" if above and terms["mandatory_above_threshold"] else "optional"
    return {"status": "modelled", "basis": "modelled",
            "fee_per_attributed_order_cad_standard": std,
            "fee_per_attributed_order_cad_reduced": red,
            "fee_per_attributed_order_cad_applied": applied,
            "fee_per_attributed_order_cad_conservative": max(std, red),
            "participation": participation,
            "attribution_window_days": terms["attribution_window_days"],
            "fx": {"usd_per_cad": ASSUMED_USD_PER_CAD, "basis": "assumed"},
            "terms_source": terms["source"],
            "controllable": False,
            "note": ("Offsite Ads fees fall only on orders Etsy attributes to an ad it placed; "
                     "Brambleloop cannot choose those listings (F-273). Exposure, not spend.")}


def unit_economics(db, slug: str) -> dict:
    """Per-order contribution and break-even ROAS for one listing, never assumed.

    measured: >= MIN_ORDERS_FOR_REFUND_RATE booked orders whose fees were read from Etsy's
    ledger (`fees_basis == "measured"`), refund rate measured. modelled: the listing's price
    against the dated fee reading; refund rate UNMEASURED, so the break-even is a lower bound.
    unknown: no price, or the fee reading cannot be applied.
    """
    from ..commerce import orders_ingest as oi
    from ..commerce import pricing
    from ..commerce.benchmarks import MIN_ORDERS_FOR_REFUND_RATE
    from ..core.models import Order

    with db.session() as s:
        listing = _latest_listing(s, slug)
        price = float(listing.price_cad or 0.0) if listing is not None else 0.0
        held = oi.held_refs(s)
        booked = oi.booked_orders(s, select(Order).where(Order.product_slug == slug))
        measured = [o for o in booked if (o.fees_basis or "") == "measured"]
        refunded = sum(1 for o in measured if not oi.countable(o, held))
        countable = [o for o in measured if oi.countable(o, held)]
        trailing = None  # shop-level trailing 365-day USD sales: not measured by this module
        rows = [{"external_ref": o.external_ref, "revenue_cad": float(o.revenue_cad or 0),
                 "fees_cad": float(o.fees_cad or 0),
                 "offsite_ads_fee_cad": o.offsite_ads_fee_cad} for o in countable]

    out = {"slug": slug, "price_cad": price if price > 0 else None,
           "sources": [f"listings:{listing.id}"] if listing is not None else []}
    if len(measured) >= MIN_ORDERS_FOR_REFUND_RATE and countable:
        n = len(countable)
        revenue = sum(r["revenue_cad"] for r in rows) / n
        net = sum(r["revenue_cad"] - r["fees_cad"] - (r["offsite_ads_fee_cad"] or 0.0)
                  for r in rows) / n
        refund_rate = refunded / len(measured)
        contribution = net * (1 - refund_rate)
        out.update({
            "status": "measured", "basis": "measured", "confidence": "measured",
            "orders": len(measured), "refund_rate": round(refund_rate, 4),
            "revenue_per_order_cad": round(revenue, 4),
            "contribution_per_order_cad": round(contribution, 4),
            "contribution_per_order_cad_conservative": round(contribution, 4),
            "break_even_roas": round(revenue / contribution, 4) if contribution > 0 else None,
            "break_even_roas_conservative": (round(revenue / contribution, 4)
                                             if contribution > 0 else None),
            "sources": out["sources"] + [f"orders:{r['external_ref']}" for r in rows[:20]],
        })
    elif price > 0:
        try:
            modelled = pricing.fees(price)
            worst = pricing.worst_case_fees(price)
        except Exception as e:  # noqa: BLE001
            out.update({"status": UNKNOWN, "basis": "unknown",
                        "why": f"fee reading cannot be applied: {e}"})
            return out
        net, worst_net = modelled.net_cad, worst["worst_case_net_cad"]
        out.update({
            "status": "modelled", "basis": "modelled", "confidence": "low",
            "orders": len(measured), "refund_rate": "UNMEASURED",
            "revenue_per_order_cad": round(price, 4),
            "fees": modelled.to_dict(),
            "contribution_per_order_cad": round(net, 4),
            "contribution_per_order_cad_conservative": round(worst_net, 4),
            "break_even_roas": round(price / net, 4) if net > 0 else None,
            "break_even_roas_conservative": round(price / worst_net, 4) if worst_net > 0 else None,
            "excluded": ["refunds (rate UNMEASURED)", "support time", "variable AI cost per sale"],
            "note": ("modelled from listing price and the dated fee reading; refunds excluded, "
                     "so break-even ROAS is a lower bound. Conservative figure applies every "
                     "unmodelled fee at its reported rate"),
            "fee_reading": {"read_on": modelled.to_dict()["fee_schedule"]["read_on"],
                            "basis": modelled.to_dict()["fee_schedule"]["basis"]},
        })
    else:
        out.update({"status": UNKNOWN, "basis": "unknown",
                    "why": ("no listing price on file" if listing is None or price <= 0
                            else "unreadable"),
                    "break_even_roas": None, "contribution_per_order_cad": None})
        return out
    out["offsite_ads"] = offsite_exposure(out["revenue_per_order_cad"],
                                          trailing_365_sales_usd=trailing)
    return out


# ---------------------------------------------------------------------------------------------
# Readiness per listing (F-263, F-272, F-242/F-529 organic first, F-685 eligibility).
# ---------------------------------------------------------------------------------------------

def _trust_gate(db) -> dict:
    """Shop-wide #17 trust ladder, as `runtime.growth_ops.ads_plan` reads it."""
    try:
        from ..commerce import first_hundred, trust
        from ..runtime.growth_ops import trust_checks
        from ..support import service
        readiness, _ = first_hundred.readiness_from_evidence(db)
        gate = trust.may_scale_ads(db, **trust_checks(db, readiness, service.service_level(db)))
    except Exception as e:  # noqa: BLE001 - unreadable is UNKNOWN, never PASS
        return {"gate": "trust_ladder", "status": UNKNOWN, "why": f"unreadable: {e!r}"[:300]}
    return {"gate": "trust_ladder", "status": PASS if gate["may_scale"] else FAIL,
            "why": gate["note"], "blocking": gate["blocking"]}


def listing_readiness(db, slug: str, *, now=None, trust_gate: dict | None = None) -> dict:
    from ..core.models import Incident, ListingSetCertificateRecord
    from ..commerce import paid_media
    from ..runtime.growth_ops import organic_period

    now = aware(now or utcnow())
    gates = []
    with db.session() as s:
        listing = _latest_listing(s, slug)
        live = bool(listing is not None and listing.state == "published"
                    and (listing.etsy_listing_id or ""))
        gates.append({"gate": "listing_live", "status": PASS if live else FAIL,
                      "why": ("published with an Etsy listing id" if live else
                              "no published Etsy listing to send traffic to (F-263)"),
                      "source": f"listings:{listing.id}" if listing is not None else None})
        cert = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.state == "valid").order_by(
            ListingSetCertificateRecord.id.desc()).limit(1))
        gates.append({"gate": "listing_certified", "status": PASS if cert is not None else FAIL,
                      "why": ("valid listing-set certificate" if cert is not None else
                              "no valid listing-set certificate: never buy traffic to an "
                              "uncertified listing (F-263, F-272)"),
                      "source": f"listing_set_certificates:{cert.id}" if cert else None})
        halting = [i.id for i in s.scalars(select(Incident).where(
            Incident.resolved == False, Incident.product_slug == slug))  # noqa: E712
            if i.halts_publication or i.severity in ("P0", "P1")]
        gates.append({"gate": "product_truth_clear", "status": FAIL if halting else PASS,
                      "why": (f"open P0/P1 or halting incident(s) {halting}: ads never "
                              f"override Product Truth (F-272)" if halting else
                              "no open P0/P1 incident for this product"),
                      "source": [f"incidents:{i}" for i in halting]})
    try:
        organic = paid_media.organic_first_gate(organic_period(db, slug))
        gates.append({"gate": "organic_signal",
                      "status": PASS if organic["allowed"] else
                      (UNKNOWN if organic["status"] == "UNMEASURED" else FAIL),
                      "why": organic["reason"], "detail": organic})
    except Exception as e:  # noqa: BLE001
        gates.append({"gate": "organic_signal", "status": UNKNOWN, "why": f"unreadable: {e!r}"})
    econ = unit_economics(db, slug)
    if econ["status"] == UNKNOWN:
        gates.append({"gate": "unit_economics", "status": UNKNOWN,
                      "why": f"economics UNKNOWN ({econ.get('why')}); never assumed"})
    elif not econ.get("break_even_roas"):
        gates.append({"gate": "unit_economics", "status": FAIL,
                      "why": "contribution per order is not positive; ads cannot recover it"})
    else:
        gates.append({"gate": "unit_economics", "status": PASS,
                      "why": (f"{econ['basis']} break-even ROAS {econ['break_even_roas']} "
                              f"(conservative {econ['break_even_roas_conservative']})"),
                      "basis": econ["basis"]})
    gates.append(_eligibility_gate(db, now))
    gates.append(trust_gate if trust_gate is not None else _trust_gate(db))
    blocking = [g for g in gates if g["status"] != PASS]
    return {"slug": slug, "ready": not blocking,
            "status": "READY" if not blocking else
            ("UNKNOWN" if all(g["status"] == UNKNOWN for g in blocking) else "NOT_READY"),
            "gates": gates, "blocking": [f"{g['gate']}: {g['status']}" for g in blocking],
            "economics": econ, "as_of": now.isoformat()}


def readiness(db, *, now=None) -> list[dict]:
    """Every product with a listing, read for ads readiness."""
    from ..core.models import Listing
    ensure_tables(db)
    with db.session() as s:
        slugs = sorted({r for r in s.scalars(select(Listing.product_slug))})
    trust = _trust_gate(db) if slugs else None
    return [listing_readiness(db, slug, now=now, trust_gate=trust) for slug in slugs]


# ---------------------------------------------------------------------------------------------
# Finance challenge (F-912, F-919) and spend proposals.
# ---------------------------------------------------------------------------------------------

def _ad_authority(db) -> dict:
    from ..runtime.growth_ops import ad_authority
    return ad_authority(db)


def hard_ceiling(db, proposal: dict) -> dict:
    """Ceilings enforced in code on every proposal, whatever any approval says (directive §12).

    owner_cash with owner ad authority: the owner's SpendLimit('ads') daily cap and lifetime
    headroom bind. owner_cash without authority: the conservative paid-media caps bind (the
    proposal asks the owner to create authority; it cannot ask for more than this). Credit:
    the official Plus entitlement per cycle (FX assumed) and never more.
    """
    from ..commerce.paid_media import CONSERVATIVE_CAPS
    from ..finance.currency import ASSUMED_USD_PER_CAD

    daily, total = float(proposal["daily_budget_cad"]), float(proposal["total_cad"])
    reasons = []
    if daily <= 0 or total <= 0 or proposal["days"] <= 0:
        reasons.append("budget, days and total must be positive")
    authority = _ad_authority(db)
    if proposal["funding"] == "owner_cash":
        if authority["granted"]:
            cap_daily = authority["daily_cap_cad"] - authority["spent_today_cad"]
            lifetime = authority["lifetime_cap_cad"] or authority["daily_cap_cad"] * 30
            cap_total = lifetime - authority["spent_lifetime_cad"]
            basis = "owner SpendLimit('ads')"
        else:
            cap_daily, cap_total = CONSERVATIVE_CAPS.daily_cad, CONSERVATIVE_CAPS.campaign_cad
            basis = "paid_media.CONSERVATIVE_CAPS (no owner ad authority yet)"
    else:
        credit_cad = round(PLUS_CREDIT_USD_PER_CYCLE / ASSUMED_USD_PER_CAD, 2)
        cap_daily, cap_total = credit_cad, credit_cad
        basis = (f"official Etsy Plus entitlement US${PLUS_CREDIT_USD_PER_CYCLE:.2f}/cycle at "
                 f"assumed FX (balance unverified)")
    if daily > cap_daily + 1e-9:
        reasons.append(f"daily CA${daily:.2f} exceeds the CA${cap_daily:.2f} ceiling ({basis})")
    if total > cap_total + 1e-9:
        reasons.append(f"total CA${total:.2f} exceeds the CA${cap_total:.2f} ceiling ({basis})")
    return {"verdict": BLOCK if reasons else ALLOW, "reasons": reasons,
            "ceiling": {"daily_cad": round(cap_daily, 2), "total_cad": round(cap_total, 2),
                        "basis": basis}, "authority": authority}


def _fallback_finance_policy(db, proposal: dict) -> dict:
    """Finance's rules as they exist before lane E's `accounting.policy.check_spend`."""
    from ..core.models import Incident
    from ..finance import governor

    reasons, verdict = [], ALLOW
    econ = proposal.get("economics") or {}
    contrib = econ.get("contribution_per_order_cad_conservative")
    if econ.get("status") in (None, UNKNOWN) or contrib is None:
        return {"verdict": BLOCK, "reasons": ["unit economics UNKNOWN: Finance cannot "
                                              "evaluate contribution, so spend is refused"]}
    if contrib <= 0:
        return {"verdict": BLOCK, "reasons": [
            f"conservative contribution per order CA${contrib:.2f} is not positive "
            f"(margin policy)"]}
    if proposal["max_cac_cad"] > contrib + 1e-9:
        verdict = BLOCK
        reasons.append(f"max CAC CA${proposal['max_cac_cad']:.2f} exceeds conservative "
                       f"contribution CA${contrib:.2f}: every acquired order would lose money "
                       f"(F-530 margin policy)")
    with db.session() as s:
        hold = [i.id for i in s.scalars(select(Incident).where(
            Incident.resolved == False,  # noqa: E712
            Incident.signature.like(f"{governor.ANOMALY_SIGNATURE}%")))]
    if hold:
        verdict = BLOCK
        reasons.append(f"spend governor anomaly hold open (incidents {hold}) (F-912)")
    if proposal["funding"] == "owner_cash":
        if econ.get("basis") != "measured":
            verdict = max(verdict, ESCALATE, key=_SEVERITY.get)
            reasons.append("owner cash on modelled economics (refund rate UNMEASURED): owner "
                           "must see the uncertainty (F-530)")
        verdict = max(verdict, ESCALATE, key=_SEVERITY.get)
        reasons.append("cash position not available to the fallback checker; lane E's "
                       "accounting policy has not been consulted")
    else:
        verdict = max(verdict, ESCALATE, key=_SEVERITY.get)
        reasons.append("Etsy Plus credit balance and cycle dates are unverified (F-614); owner "
                       "confirms the credit exists before it is relied on")
    off = econ.get("offsite_ads") or {}
    fee = off.get("fee_per_attributed_order_cad_conservative")
    if fee is not None and contrib - fee <= 0:
        verdict = max(verdict, ESCALATE, key=_SEVERITY.get)
        reasons.append("an Offsite-Ads-attributed order would have non-positive contribution")
    if not reasons:
        reasons.append("within fallback Finance policy")
    return {"verdict": verdict, "reasons": reasons}


def _normalise(result) -> dict:
    """Read lane E's answer. Anything unrecognised fails closed (BLOCK)."""
    if isinstance(result, bool):
        return {"verdict": ALLOW if result else BLOCK, "reasons": [], "raw": result}
    if isinstance(result, dict):
        v = str(result.get("verdict") or result.get("decision") or "").upper()
        if v in ("APPROVE", "APPROVED", "OK", "PASS"):
            v = ALLOW
        if v in ("REFUSE", "REFUSED", "DENY", "DENIED", "REJECT"):
            v = BLOCK
        if v not in _SEVERITY and "allowed" in result:
            v = ALLOW if result["allowed"] else BLOCK
        if v in _SEVERITY:
            reasons = result.get("reasons") or result.get("why") or []
            return {"verdict": v, "reasons": [reasons] if isinstance(reasons, str)
                    else list(reasons), "raw": json.loads(json.dumps(result, default=str))}
    return {"verdict": BLOCK, "reasons": [f"unrecognised Finance answer {result!r}"[:300]],
            "raw": None}


def finance_check(db, proposal: dict) -> dict:
    """Ask Finance (F-919). Lane E's function if present, else the fallback; never self-approve."""
    try:
        from ..finance.accounting.policy import check_spend
    except ImportError:
        got = _fallback_finance_policy(db, proposal)
        return {**got, "checker": FALLBACK_CHECK,
                "note": f"{FINANCE_CHECK} not built yet; fallback applied"}
    try:
        got = _normalise(check_spend(db, proposal))
    except Exception as e:  # noqa: BLE001 - a Finance error is a refusal, not a pass
        got = {"verdict": BLOCK, "reasons": [f"Finance check raised {e!r}"[:300]]}
    return {**got, "checker": FINANCE_CHECK}


def _key(slug, funding, daily, days, now) -> str:
    raw = f"{slug}|{funding}|{daily:.2f}|{days}|{now.date().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def propose(db, slug: str, *, daily_budget_cad: float, days: int, funding: str,
            hypothesis: str, stop_condition: str, max_cac_cad: float | None = None,
            now=None, trust_gate: dict | None = None) -> dict:
    """Record a Growth spend PROPOSAL, have Finance challenge it, route the survivor to the owner.

    Never spends and never schedules spend. Status: FINANCE_BLOCKED (most restrictive wins),
    NOT_READY (readiness gate not PASS), AWAITING_OWNER (an OwnerAction exists).
    """
    ensure_tables(db)
    now = aware(now or utcnow())
    if funding not in FUNDING:
        raise ValueError(f"funding must be one of {FUNDING}")
    if not (hypothesis or "").strip() or not (stop_condition or "").strip():
        raise ValueError("a proposal needs a hypothesis and a stop condition (F-529, F-616)")
    days = int(days)
    daily = round(float(daily_budget_cad), 2)
    ready = listing_readiness(db, slug, now=now, trust_gate=trust_gate)
    econ = ready["economics"]
    window = (econ.get("offsite_ads") or {}).get("attribution_window_days") or 30
    cac = (float(max_cac_cad) if max_cac_cad is not None
           else float(econ.get("contribution_per_order_cad_conservative") or 0.0))
    proposal = {"kind": "ads_spend", "department": "growth", "proposer": "growth.ads",
                "purpose": "etsy_ads_experiment", "currency": "CAD", "slug": slug,
                "funding": funding, "daily_budget_cad": daily, "days": days,
                "total_cad": round(daily * days, 2), "amount_cad": round(daily * days, 2),
                "max_cac_cad": round(cac, 2), "hypothesis": hypothesis,
                "stop_condition": stop_condition, "attribution_window_days": int(window),
                "economics": econ, "readiness_status": ready["status"]}
    key = _key(slug, funding, daily, days, now)
    proposal["key"] = key
    ceiling = hard_ceiling(db, proposal)
    finance = finance_check(db, proposal)
    verdict = max(finance["verdict"], ceiling["verdict"], key=_SEVERITY.get)
    reasons = list(finance.get("reasons") or []) + [f"hard ceiling: {r}"
                                                     for r in ceiling["reasons"]]
    if verdict == BLOCK:
        status = "FINANCE_BLOCKED"
    elif not ready["ready"]:
        status = "NOT_READY"
    else:
        status = "AWAITING_OWNER"
    payload = json.loads(json.dumps(proposal, default=str))
    with db.session() as s:
        row = s.scalar(select(AdSpendProposal).where(AdSpendProposal.key == key))
        if row is None:
            row = AdSpendProposal(key=key, product_slug=slug)
            s.add(row)
        row.at, row.funding, row.daily_budget_cad, row.days = now, funding, daily, days
        row.total_cad, row.max_cac_cad = payload["total_cad"], payload["max_cac_cad"]
        row.hypothesis, row.stop_condition = hypothesis, stop_condition
        row.attribution_window_days = int(window)
        row.economics = payload["economics"]
        row.readiness = json.loads(json.dumps(
            {k: ready[k] for k in ("status", "ready", "blocking", "gates")}, default=str))
        row.status, row.executed = status, False
        s.flush()
        ch = AdFinanceChallenge(
            at=now, proposal_id=row.id, checker=finance["checker"], verdict=verdict,
            reasons=reasons,
            evidence=json.loads(json.dumps({
                "finance_verdict": finance["verdict"], "finance_raw": finance.get("raw"),
                "finance_note": finance.get("note"), "hard_ceiling": ceiling,
                "proposal": {k: payload[k] for k in ("funding", "daily_budget_cad", "days",
                                                      "total_cad", "max_cac_cad")}},
                default=str)))
        s.add(ch)
        if status == "AWAITING_OWNER":
            rk = f"ads.proposal:{key}"
            act = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == rk,
                                                     OwnerAction.done == False))  # noqa: E712
            if act is None:
                act = OwnerAction(
                    requirement_key=rk,
                    action=(f"Decide Etsy Ads experiment for {slug}: CA${daily:.2f}/day x "
                            f"{days} days = max CA${payload['total_cad']:.2f} "
                            f"({funding}). Brambleloop has no ads executor and will not "
                            f"spend; if approved, activation is yours in Etsy within this cap."),
                    reason=(f"Finance {verdict}: {'; '.join(reasons)}. Hypothesis: "
                            f"{hypothesis}. Stop: {stop_condition}. Break-even ROAS "
                            f"{econ.get('break_even_roas')} ({econ.get('basis')})."),
                    max_cost_cad=payload["total_cad"], minutes=5,
                    consequence_of_delay="no paid traffic; organic work continues",
                    blocks="F-267 ad budget owner authority")
                s.add(act)
                s.flush()
            row.owner_action_id = act.id
        s.flush()
        return {"proposal_id": row.id, "key": key, "status": status, "verdict": verdict,
                "reasons": reasons, "checker": finance["checker"],
                "ceiling": ceiling["ceiling"], "readiness": ready["status"],
                "owner_action_id": row.owner_action_id, "executed": False,
                "challenge_id": ch.id}


def rechallenge(db, proposal_id: int, *, now=None, trust_gate: dict | None = None) -> dict:
    """Revalidate a proposal from scratch (readiness, Finance, ceiling); the old row is SUPERSEDED.

    Authority revoked, economics changed or a ceiling lowered since the proposal was written
    therefore refuses now, not at some later execution that does not exist.
    """
    ensure_tables(db)
    with db.session() as s:
        p = s.get(AdSpendProposal, proposal_id)
        if p is None:
            raise ValueError(f"no proposal {proposal_id}")
        args = dict(slug=p.product_slug, daily_budget_cad=p.daily_budget_cad, days=p.days,
                    funding=p.funding, hypothesis=p.hypothesis,
                    stop_condition=p.stop_condition, max_cac_cad=p.max_cac_cad)
        p.status = "SUPERSEDED"
        if p.owner_action_id:
            act = s.get(OwnerAction, p.owner_action_id)
            if act is not None and not act.done:
                act.done = True  # withdrawn; a fresh item is raised if it still survives
    slug = args.pop("slug")
    return propose(db, slug, now=now, trust_gate=trust_gate, **args)


def proposals(db) -> list[dict]:
    ensure_tables(db)
    with db.session() as s:
        out = []
        for p in s.scalars(select(AdSpendProposal).order_by(AdSpendProposal.id)):
            ch = s.scalar(select(AdFinanceChallenge).where(
                AdFinanceChallenge.proposal_id == p.id).order_by(
                AdFinanceChallenge.id.desc()).limit(1))
            act = s.get(OwnerAction, p.owner_action_id) if p.owner_action_id else None
            out.append({
                "id": p.id, "key": p.key, "slug": p.product_slug, "at": aware(p.at).isoformat(),
                "status": p.status, "funding": p.funding, "daily_budget_cad": p.daily_budget_cad,
                "days": p.days, "total_cad": p.total_cad, "max_cac_cad": p.max_cac_cad,
                "hypothesis": p.hypothesis, "stop_condition": p.stop_condition,
                "economics_basis": (p.economics or {}).get("basis", "unknown"),
                "break_even_roas": (p.economics or {}).get("break_even_roas"),
                "challenge": ({"verdict": ch.verdict, "checker": ch.checker,
                               "reasons": list(ch.reasons or []),
                               "at": aware(ch.at).isoformat()} if ch else None),
                "owner_action": ({"id": act.id, "done": bool(act.done)} if act else None),
                "executed": False, "execution_capability": "none",
            })
        return out


# ---------------------------------------------------------------------------------------------
# Anti-gaming KPIs (F-918, F-262, F-269, F-616).
# ---------------------------------------------------------------------------------------------

def attributed_roas(orders: list[dict], *, spend_cad: float | None, spend_basis: str) -> dict:
    """ROAS on evidence-attributed Etsy Ads revenue only, with its confidence.

    `orders`: dicts with `channel`, `revenue_cad`, `contribution_cad`, `evidence`. Organic,
    unattributed and Offsite orders are excluded and counted, never blended in; an "etsy_ads"
    order without attribution evidence is excluded as unattributed. Spend must be measured.
    """
    used = [o for o in orders if o.get("channel") == "etsy_ads" and (o.get("evidence") or "")]
    excluded = len(orders) - len(used)
    revenue = round(sum(float(o.get("revenue_cad") or 0) for o in used), 2)
    contribution = round(sum(float(o.get("contribution_cad") or 0) for o in used), 2)
    base = {"attributed_orders": len(used), "excluded_orders": excluded,
            "attributed_revenue_cad": revenue, "attributed_contribution_cad": contribution,
            "spend_cad": spend_cad, "spend_basis": spend_basis}
    if spend_basis != "measured" or not spend_cad or spend_cad <= 0:
        return {**base, "status": UNKNOWN, "roas": None, "contribution_roas": None,
                "confidence": "none", "why": "ad spend not measured; ROAS is not computed"}
    confidence = ("adequate" if len(used) >= MIN_ATTRIBUTED_ORDERS_FOR_CONFIDENCE
                  else "low")
    return {**base, "status": "measured", "roas": round(revenue / spend_cad, 4),
            "contribution_roas": round(contribution / spend_cad, 4), "confidence": confidence,
            "why": (f"{len(used)} evidence-attributed Etsy Ads order(s); confidence "
                    f"{confidence} against a floor of {MIN_ATTRIBUTED_ORDERS_FOR_CONFIDENCE}")}


def kpis(db) -> dict:
    """Outcome KPI (contribution ROAS) plus guardrails; a good ROAS cannot override them."""
    from ..commerce import orders_ingest as oi
    from ..core.models import CostEntry, Incident
    from ..finance.sources import channel

    with db.session() as s:
        orders = [{"channel": channel(o.acquisition_source),
                   "revenue_cad": float(o.revenue_cad or 0),
                   "contribution_cad": float(o.contribution_cad or 0),
                   "evidence": ((o.detail or {}).get("attribution") or {}).get("evidence", ""),
                   "refunded": False} for o in oi.countable_orders(s)]
        spend_rows = list(s.scalars(select(CostEntry).where(CostEntry.kind == "ads")))
        open_truth = [i.id for i in s.scalars(select(Incident).where(
            Incident.resolved == False)) if i.severity in ("P0", "P1")]  # noqa: E712
    spend = round(sum(float(r.amount_cad or 0) for r in spend_rows), 2) if spend_rows else None
    roas = attributed_roas(orders, spend_cad=spend,
                           spend_basis="measured" if spend_rows else "unknown")
    guardrails = {
        "product_truth_incidents_open": open_truth,
        "organic_and_paid_separate": True,
        "roas_on_attributed_revenue_only": True,
        "confidence_floor_orders": MIN_ATTRIBUTED_ORDERS_FOR_CONFIDENCE,
    }
    may_scale = bool(roas["status"] == "measured" and roas["confidence"] == "adequate"
                     and (roas["contribution_roas"] or 0) > 1.0 and not open_truth)
    return {"outcome_kpi": "contribution_roas", "roas": roas, "guardrails": guardrails,
            "may_scale_on_kpis": may_scale,
            "why": ("scaling also needs Finance's challenge and owner authority; a KPI never "
                    "authorises spend (F-918)")}


# ---------------------------------------------------------------------------------------------
# Provider contract (lane C) and work contract (lane A).
# ---------------------------------------------------------------------------------------------

def summary(db) -> dict:
    """Ads readiness/economics, spend proposals and Finance challenges. Never raises."""
    now = aware(utcnow())
    try:
        ensure_tables(db)
        elig = state(db, now=now)
        rows = readiness(db, now=now)
        props = proposals(db)
        k = kpis(db)
    except Exception as e:  # noqa: BLE001
        return {"status": "UNKNOWN", "as_of": now.isoformat(), "basis": "unknown",
                "items": [], "sources": list(SOURCES),
                "reason": f"ads readiness unreadable: {e!r}"[:300]}
    bases = {r["economics"].get("basis", "unknown") for r in rows}
    basis = ("unknown" if not rows or bases == {"unknown"} else
             "measured" if bases == {"measured"} else "modelled")
    ready = [r["slug"] for r in rows if r["ready"]]
    if not rows:
        status, reason = "UNKNOWN", "no listings on file to read for ads readiness"
    elif ready:
        status, reason = "OK", f"{len(ready)} listing(s) ads-ready; spend still owner-gated"
    else:
        status, reason = "BLOCKED", "no listing passes every ads readiness gate"
    items = [{"type": "listing_readiness", "slug": r["slug"], "status": r["status"],
              "blocking": r["blocking"],
              "economics_basis": r["economics"].get("basis"),
              "break_even_roas": r["economics"].get("break_even_roas"),
              "break_even_roas_conservative":
                  r["economics"].get("break_even_roas_conservative"),
              "contribution_per_order_cad": r["economics"].get("contribution_per_order_cad"),
              "offsite_ads": {k2: (r["economics"].get("offsite_ads") or {}).get(k2) for k2 in
                              ("fee_per_attributed_order_cad_conservative", "participation",
                               "basis")}} for r in rows]
    items += [{"type": "spend_proposal", **p} for p in props]
    return {
        "status": status, "as_of": now.isoformat(), "basis": basis, "items": items,
        "sources": list(SOURCES), "reason": reason,
        "eligibility": elig,
        "proposals": {"total": len(props),
                      "finance_blocked": [p["id"] for p in props
                                          if p["status"] == "FINANCE_BLOCKED"],
                      "awaiting_owner": [p["id"] for p in props
                                         if p["status"] == "AWAITING_OWNER"],
                      "not_ready": [p["id"] for p in props if p["status"] == "NOT_READY"]},
        "kpis": k,
        "spend_executed_cad": 0.0, "execution_capability": "none",
        "activation_authorised": False,
    }


def next_work(db, *, now=None) -> list[dict]:
    """Zero-spend Growth/ads work available now, for the autonomy loop (lane A).

    Contract: list of {key, department: "growth", kind, action, why, spend_cad: 0.0,
    blocked_by: str | None}. `blocked_by` names an owner/external blocker; such items are
    reported, not runnable. No item spends, activates or contacts anyone.
    """
    now = aware(now or utcnow())
    ensure_tables(db)
    out = []
    elig = state(db, now=now)
    if elig["etsy_ads_status"] in ("NOT_INITIALISED",) or not elig.get("last_recheck_at") or \
            now - datetime.fromisoformat(elig["last_recheck_at"]) >= timedelta(hours=1):
        out.append({"key": "ads.eligibility_tick", "department": "growth", "kind": "internal",
                    "action": "growth.ads_readiness.tick", "spend_cad": 0.0, "blocked_by": None,
                    "why": "re-evaluate persisted Etsy Ads eligibility evidence (F-686)"})
    if elig["etsy_ads_status"] == "RECHECK_REQUIRED":
        out.append({"key": "ads.eligibility_evidence", "department": "growth",
                    "kind": "owner_action", "action": f"OwnerAction {REFRESH_KEY}",
                    "spend_cad": 0.0, "why": "fresh Etsy UI eligibility evidence needed",
                    "blocked_by": "owner: no sanctioned Etsy Ads collector exists"})
    for r in readiness(db, now=now):
        for g in r["gates"]:
            if g["gate"] == "organic_signal" and g["status"] != PASS:
                out.append({"key": f"ads.organic_baseline:{r['slug']}", "department": "growth",
                            "kind": "internal", "spend_cad": 0.0,
                            "action": "capture organic baseline from Stats/listing outcomes",
                            "why": g["why"][:200],
                            "blocked_by": None if any(x["gate"] == "listing_live" and
                                                      x["status"] == PASS for x in r["gates"])
                            else "listing not live"})
            if g["gate"] == "unit_economics" and g["status"] == UNKNOWN:
                out.append({"key": f"ads.economics:{r['slug']}", "department": "growth",
                            "kind": "internal", "spend_cad": 0.0, "blocked_by": None,
                            "action": "record listing price so economics can be modelled",
                            "why": g["why"][:200]})
    with db.session() as s:
        stale = [p.id for p in s.scalars(select(AdSpendProposal).where(
            AdSpendProposal.status == "AWAITING_OWNER"))
            if now - aware(p.at) >= PROPOSAL_STALE_AFTER]
    for pid in stale:
        out.append({"key": f"ads.rechallenge:{pid}", "department": "growth", "kind": "internal",
                    "action": "re-run readiness and Finance challenge on proposal",
                    "spend_cad": 0.0, "blocked_by": None,
                    "why": "a proposal older than 7 days must be revalidated before any decision"})
    return out
