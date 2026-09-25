"""Prepare without activation; a countdown is a recheck date, never permission.

Etsy's audited surface registry has no Ads API. Until a sanctioned collector exists,
the hourly job re-evaluates persisted evidence and routes a due refresh to the existing
owner inbox. It does not pretend that reading our database queried Etsy.
"""
from datetime import datetime, timezone
from math import ceil

from sqlalchemy import select, text

from ..core.db import is_postgres
from ..core.models import MarketplaceCapability, OwnerAction, Product, utcnow

KEY = "etsy_ads"
REFRESH_KEY = "etsy_ads_eligibility_evidence"
REPORTED_RECHECK = datetime(2026, 10, 4, tzinfo=timezone.utc)
SOURCE = "chatgpt-conversation://6aa9ea7a-c154-83ea-901c-53ee8ff2bb22"


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and not value.tzinfo else value


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
    return {
        "etsy_ads_status": row.status,
        "eligible_from": due.isoformat() if due else None,
        "days_remaining": max(0, ceil((due - now).total_seconds() / 86400)) if due else None,
        "evidence_source": row.evidence_source,
        "last_verified_at": aware(row.last_verified_at).isoformat() if row.last_verified_at else None,
        "date_is_estimate": row.detail.get("date_is_estimate", False),
        "last_recheck_at": row.detail.get("last_recheck_at"),
        "collector_status": "NO_SANCTIONED_ADS_COLLECTOR",
        "activation_authorised": False,
        "credit_accounting": {"etsy_plus_credit": "unverified; separate from owner cash",
                              "owner_cash_budget_cad": None},
    }


def state(db, *, now=None):
    now = aware(now or utcnow())
    with db.session() as s:
        row = s.get(MarketplaceCapability, KEY)
        if row is None:
            return {"etsy_ads_status": "NOT_INITIALISED", "activation_authorised": False}
        return snapshot(row, now)


def tick(db, *, now=None):
    now = aware(now or utcnow())
    with db.session() as s:
        row = locked_row(s, db)
        due = aware(row.eligible_from)
        # Even an old eligibility observation must be refreshed before future action.
        stale = row.last_verified_at and (now - aware(row.last_verified_at)).total_seconds() >= 86400
        needs_refresh = bool((due is not None and now >= due) or stale
                             or (due is None and row.last_verified_at is None))
        if needs_refresh:
            row.status = "RECHECK_REQUIRED"
            existing = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == REFRESH_KEY, OwnerAction.done == False))
            if existing is None:
                s.add(OwnerAction(requirement_key=REFRESH_KEY,
                    action="Open Etsy Shop Manager > Marketing > Etsy Ads and record the current eligibility message and timestamp. Do not activate ads.",
                    reason="The stored countdown is due or evidence is stale. The audited Etsy API has no Ads eligibility collector.",
                    max_cost_cad=0, minutes=2,
                    consequence_of_delay="Campaign preparation continues; eligibility remains unverified and ads remain inactive.",
                    blocks="Etsy Ads eligibility verification only"))
        candidates = [{"slug": p.slug, "title": p.title, "product_status": p.status,
                       "ready_to_advertise": False}
                      for p in s.scalars(select(Product).order_by(Product.id))]
        # A durable preparation brief, not invented performance or a campaign purchase.
        prep = {"candidates": candidates, "prepared_at": now.isoformat(),
                "next_work": ["Use existing keyword and benchmark evidence",
                              "Require Product Truth, Visual and owner listing approval",
                              "Measure organic baseline and contribution before selecting spend",
                              "Design bounded experiment; verify Plus credit separately from cash"],
                "campaign_activated": False, "budget_authorised_cad": 0}
        row.detail = {**row.detail, "last_recheck_at": now.isoformat(), "preparation": prep}
        return {**snapshot(row, now), "preparation": prep}


def record_evidence(db, *, status, evidence_source, verified_at, eligible_from=None, now=None):
    """Operator-attested Etsy UI evidence; caller must authenticate before this function."""
    now = aware(now or utcnow())
    verified_at = aware(verified_at)
    eligible_from = aware(eligible_from)
    if status not in {"WAITING", "ELIGIBLE", "INELIGIBLE"}:
        raise ValueError("status must be WAITING, ELIGIBLE or INELIGIBLE")
    if not evidence_source.strip() or len(evidence_source) > 2000:
        raise ValueError("dated Etsy evidence reference required")
    if verified_at is None or verified_at > now or (now - verified_at).total_seconds() > 86400:
        raise ValueError("evidence must be from the last 24 hours and not the future")
    if status == "WAITING" and (eligible_from is None or eligible_from <= verified_at):
        raise ValueError("waiting evidence requires a future recheck date")
    with db.session() as s:
        row = locked_row(s, db)
        if row.last_verified_at and verified_at < aware(row.last_verified_at):
            raise ValueError("older evidence cannot replace newer evidence")
        history = list(row.detail.get("evidence_history", []))
        history.append({"status": status, "source": evidence_source,
                        "verified_at": verified_at.isoformat()})
        row.status = status
        row.evidence_source = evidence_source
        row.last_verified_at = verified_at
        row.eligible_from = eligible_from if status == "WAITING" else None
        row.detail = {**row.detail, "date_is_estimate": status == "WAITING",
                      "evidence_kind": "operator_attested_etsy_ui", "evidence_history": history}
        for action in s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key == REFRESH_KEY, OwnerAction.done == False)):
            action.done = True
        return snapshot(row, now)
