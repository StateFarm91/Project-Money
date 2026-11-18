"""Promotional and cloud credits, kept apart from cash (F-629; the wallet F-614 needs).

A provider credit -- a promotional grant, a cloud credit, an ad or listing credit -- pays for
usage without being cash out of the company. Merged into spend it overstates cash burn; merged
into a budget it reads as authority to spend. Neither is allowed here:

* A credit never raises a ceiling. Every ceiling is checked against recorded exposure, which
  this module does not touch (`ceilings_changed` is always 0).
* What a credit absorbed is an ESTIMATE unless a provider statement says otherwise: the
  provider's draw order is assumed (credits first, the common rule) and named as assumed.
* An unknown expiry is UNKNOWN (None), never "does not expire".

The table lives here (integrator owns `core/models.py`); `ensure_table` creates it on an
existing database.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

KINDS = ("promotional_credit", "cloud_credit", "ads_credit", "listing_credit")
SOURCES = ("owner_reported", "provider_statement")
DRAW_ASSUMPTION = ("credits are assumed to be drawn before cash for usage with the same "
                   "provider after the grant -- an estimate until a provider statement says "
                   "how much was drawn")


class CreditRefused(ValueError):
    """A credit that would be recorded as something it is not."""


class ProviderCredit(Base):
    __tablename__ = "provider_credits"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    granted_on: Mapped[str] = mapped_column(String(10))
    expires_on: Mapped[str] = mapped_column(String(10), default="")
    source: Mapped[str] = mapped_column(String(30), default="owner_reported")
    evidence_ref: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class AdsCreditCycle(Base):
    """F-688: one Etsy Plus Ads-credit cycle, as Etsy states it -- never owner cash.

    `entitlement_usd` is the official entitlement (Etsy states it in USD); `displayed_cad` is
    the value Etsy's Shop Manager displays locally, recorded as read (it is NOT this system's
    conversion, which is reported beside it and labelled as such). `used_displayed_cad` is
    what Etsy reports as used this cycle; NULL is UNKNOWN, never 0.
    """
    __tablename__ = "ads_credit_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    cycle_start: Mapped[str] = mapped_column(String(10), index=True)
    cycle_end: Mapped[str] = mapped_column(String(10))
    entitlement_usd: Mapped[float] = mapped_column(Float)
    displayed_cad: Mapped[float] = mapped_column(Float)
    used_displayed_cad: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="owner_reported")
    evidence_ref: Mapped[str] = mapped_column(String(200), default="")


_LOCK = threading.Lock()
_FLAG = "_brambleloop_provider_credits_ready"


def ensure_table(db) -> None:
    engine = db.engine if hasattr(db, "engine") else db.get_bind()
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[ProviderCredit.__table__,
                                                 AdsCreditCycle.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)


def _to_cad(amount: float, currency: str) -> float:
    if currency == "CAD":
        return float(amount)
    if currency == "USD":
        from ..gateway.routing import USD_PER_CAD

        return float(amount) / USD_PER_CAD
    raise CreditRefused(f"no conversion for {currency!r}")


def grant(db, *, provider: str, kind: str, amount: float, currency: str, granted_on: str,
          expires_on: str = "", source: str = "owner_reported", evidence_ref: str = "",
          note: str = "") -> int:
    """Record one credit grant. Refuses a non-positive amount, an unknown kind or source,
    an unparseable date, or a grant with no evidence."""
    import math

    if kind not in KINDS:
        raise CreditRefused(f"{kind!r} is not a credit kind: {KINDS}")
    if source not in SOURCES:
        raise CreditRefused(f"{source!r} is not a credit source: {SOURCES}")
    amt = float(amount)
    if not math.isfinite(amt) or amt <= 0:
        raise CreditRefused("a credit is a positive amount")
    currency = currency.upper()
    _to_cad(amt, currency)
    date.fromisoformat(granted_on)
    if expires_on:
        date.fromisoformat(expires_on)
    if not evidence_ref:
        raise CreditRefused("a credit with no evidence reference is a claim, not a credit")
    ensure_table(db)
    with db.session() as s:
        row = ProviderCredit(provider=provider, kind=kind, amount=amt, currency=currency,
                             granted_on=granted_on, expires_on=expires_on, source=source,
                             evidence_ref=evidence_ref[:200], note=note)
        s.add(row)
        s.flush()
        return row.id


def wallet(db, *, now: datetime | None = None) -> dict:
    """Credits per provider, what they are estimated to have absorbed, and cash exposure."""
    from sqlalchemy import select

    from ..core.models import CostEntry

    ensure_table(db)
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    with db.session() as s:
        credits = list(s.scalars(select(ProviderCredit).order_by(ProviderCredit.granted_on,
                                                                 ProviderCredit.id)))
        providers = sorted({c.provider for c in credits})
        spend: dict[str, list] = {p: [] for p in providers}
        if providers:
            for e in s.scalars(select(CostEntry).where(CostEntry.provider.in_(providers))):
                at = e.at if e.at.tzinfo else e.at.replace(tzinfo=timezone.utc)
                spend[e.provider].append((at.date().isoformat(), float(e.amount_cad or 0.0)))
        rows = [{"id": c.id, "provider": c.provider, "kind": c.kind, "amount": c.amount,
                 "currency": c.currency, "amount_cad": round(_to_cad(c.amount, c.currency), 6),
                 "granted_on": c.granted_on, "expires_on": c.expires_on or None,
                 "source": c.source, "evidence_ref": c.evidence_ref} for c in credits]
    by_provider = {}
    for p in providers:
        mine = [r for r in rows if r["provider"] == p]
        first = min(r["granted_on"] for r in mine)
        spent_since = round(sum(a for d, a in spend[p] if d >= first), 6)
        # Draw each credit in grant order against spend since it was granted (assumption).
        remaining_spend = spent_since
        active_left = 0.0
        absorbed = 0.0
        for r in mine:
            draw = min(r["amount_cad"], max(remaining_spend, 0.0))
            remaining_spend -= draw
            absorbed += draw
            left = r["amount_cad"] - draw
            expired = bool(r["expires_on"]) and r["expires_on"] < today
            r["estimated_drawn_cad"] = round(draw, 6)
            r["estimated_left_cad"] = 0.0 if expired else round(left, 6)
            r["expired"] = expired
            r["expiry_basis"] = "stated" if r["expires_on"] else "UNKNOWN"
            if not expired:
                active_left += left
        by_provider[p] = {
            "credits": mine,
            "credit_granted_cad": round(sum(r["amount_cad"] for r in mine), 6),
            "recorded_spend_since_first_grant_cad": spent_since,
            "estimated_absorbed_by_credit_cad": round(absorbed, 6),
            "estimated_cash_exposure_cad": round(spent_since - absorbed, 6),
            "estimated_credit_left_cad": round(active_left, 6),
            "basis": "ESTIMATED",
        }
    return {
        "providers": by_provider,
        "credit_granted_cad": round(sum(v["credit_granted_cad"] for v in by_provider.values()), 6),
        "estimated_absorbed_cad": round(
            sum(v["estimated_absorbed_by_credit_cad"] for v in by_provider.values()), 6),
        "draw_assumption": DRAW_ASSUMPTION,
        "ceilings_changed": 0,
        "not_a_budget": ("a credit is not authority to spend: every ceiling is still checked "
                         "against recorded exposure, credit or not"),
        "why_empty": ("" if by_provider else
                      "no promotional or cloud credit has been recorded, so all recorded spend "
                      "is treated as cash exposure"),
        "ads_credit": ads_credit(db, now=now),
    }


def split(db, provider: str, *, now: datetime | None = None) -> dict:
    """S2: one provider's ledger split into promotional credit and billable cash, in CAD.

    The same draw order `wallet` assumes (credits first, in grant order, each against usage
    after its grant date and before its expiry), applied call by call so every ledger row says
    which it is estimated to have been paid from. ESTIMATED until a provider statement says
    otherwise; it changes no ceiling -- the monthly cash ceiling still counts every call.
    """
    from sqlalchemy import select

    from ..core.models import CostEntry

    ensure_table(db)
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        grants = [{"id": c.id, "left": _to_cad(c.amount, c.currency),
                   "from": c.granted_on, "until": c.expires_on or None}
                  for c in s.scalars(select(ProviderCredit).where(
                      ProviderCredit.provider == provider).order_by(
                      ProviderCredit.granted_on, ProviderCredit.id))]
        rows = [(e.id, (e.at if e.at.tzinfo else e.at.replace(tzinfo=timezone.utc)),
                 float(e.amount_cad or 0.0))
                for e in s.scalars(select(CostEntry).where(
                    CostEntry.provider == provider).order_by(CostEntry.at, CostEntry.id))]
    calls, promo, cash = [], 0.0, 0.0
    for row_id, at, cad in rows:
        day, need, from_credit = at.date().isoformat(), cad, 0.0
        for g in grants:
            if need <= 0:
                break
            if g["left"] <= 0 or day < g["from"] or (g["until"] and day > g["until"]):
                continue
            take = min(g["left"], need)
            g["left"] -= take
            need -= take
            from_credit += take
        promo += from_credit
        cash += need
        calls.append({"cost_entry": row_id, "cad": round(cad, 6),
                      "promo_credit_cad": round(from_credit, 6),
                      "billable_cash_cad": round(need, 6),
                      "source": ("promo_credit" if need <= 1e-12 and cad > 0 else
                                 "billable_cash" if from_credit <= 1e-12 else "mixed")})
    from ..gateway.routing import USD_PER_CAD

    today = now.date().isoformat()
    for c in calls:
        c["usd"] = round(c["cad"] * USD_PER_CAD, 6)
    # S2 review 6957356475 (MEDIUM): what is held and what is uncertain is part of the ledger.
    # Live reservations for this provider are money committed but not yet billed; a paid call
    # whose outcome is UNCERTAIN may have billed and is counted at its estimate, never at 0.
    held = _held_and_uncertain(db, provider, now)
    gross_cad = round(promo + cash, 6)
    return {"provider": provider, "currency": "CAD", "calls": calls,
            "ledger_cad": gross_cad, "promo_credit_cad": round(promo, 6),
            "billable_cash_cad": round(cash, 6),
            "gross_usd": round(gross_cad * USD_PER_CAD, 6),
            "usd_basis": (f"DERIVED: recorded CAD x the single assumed rate {USD_PER_CAD:.4f} "
                          f"USD/CAD (core.fx); the provider bills in USD"),
            **held,
            "exposure_cad": round(cash + held["reserved_cad"] + held["uncertain_cad"], 6),
            "grants": [{"id": g["id"], "granted_on": g["from"], "expires_on": g["until"],
                        "expiry_basis": "stated" if g["until"] else "UNKNOWN",
                        "expired": bool(g["until"] and g["until"] < today),
                        "estimated_left_cad": (0.0 if g["until"] and g["until"] < today
                                               else round(max(g["left"], 0.0), 6))}
                       for g in grants],
            "credit_left_cad": round(sum(max(g["left"], 0.0) for g in grants
                                         if not (g["until"] and g["until"] < today)), 6),
            "basis": "ESTIMATED", "draw_assumption": DRAW_ASSUMPTION, "ceilings_changed": 0}


def _held_and_uncertain(db, provider: str, now: datetime) -> dict:
    """Live (unreleased, unexpired) reservations held for `provider`, and its paid calls whose
    billing is UNCERTAIN, at their estimates. A table not yet created reads as nothing held."""
    from sqlalchemy import inspect as sa_inspect, select

    from ..core.models import SpendReservation
    from ..gateway.paid_calls import UNCERTAIN, PaidCallRecord

    reserved = uncertain = 0.0
    n_res = n_unc = 0
    with db.session() as s:
        tables = set(sa_inspect(s.get_bind()).get_table_names())
        if SpendReservation.__tablename__ in tables:
            for r in s.scalars(select(SpendReservation).where(
                    SpendReservation.released_at.is_(None))):
                exp = r.expires_at if (r.expires_at is None or r.expires_at.tzinfo) else \
                    r.expires_at.replace(tzinfo=timezone.utc)
                if (r.detail or {}).get("provider") == provider and exp and exp > now:
                    reserved += float(r.amount_cad or 0.0)
                    n_res += 1
        if PaidCallRecord.__tablename__ in tables:
            for r in s.scalars(select(PaidCallRecord).where(
                    PaidCallRecord.outcome == UNCERTAIN,
                    PaidCallRecord.provider.in_((provider, f"{provider}-vision")))):
                uncertain += float(r.estimate_cad or 0.0)
                n_unc += 1
    return {"reserved_cad": round(reserved, 6), "reservations": n_res,
            "uncertain_cad": round(uncertain, 6), "uncertain_calls": n_unc,
            "uncertain_basis": "UNCERTAIN paid calls counted at their estimate until a provider "
                               "statement settles them; never as 0"}


def model_providers(db, *, now: datetime | None = None) -> dict:
    """The Command Center budget view of every model provider's ledger (S2 / S4 board)."""
    from ..gateway.routing import ROUTABLE_PROVIDERS

    names = sorted(set(ROUTABLE_PROVIDERS) | {"openai"})
    out = {}
    for name in names:
        got = split(db, name, now=now)
        out[name] = {k: v for k, v in got.items() if k != "calls"}
        out[name]["balance"] = "UNKNOWN"
    return {"providers": out,
            "why_balance_unknown": "no supported API reports an API key's remaining credit; "
                                   "the ledger is what was recorded, never a balance"}


# ---------------------------------------------------------------------------------------------
# F-688: Etsy Plus Ads credit, cycle by cycle, separate from owner cash.
# ---------------------------------------------------------------------------------------------

def record_ads_credit_cycle(db, *, cycle_start: str, cycle_end: str, entitlement_usd: float,
                            displayed_cad: float, used_displayed_cad: float | None = None,
                            source: str = "owner_reported", evidence_ref: str = "") -> dict:
    """Record (or update, keyed by `cycle_start`) one Ads-credit cycle as Etsy states it.

    Refuses: no evidence, an unknown source, unparseable or inverted dates, a non-positive
    entitlement or displayed value, a negative use, or a use larger than the displayed credit
    (a credit cannot absorb more than it holds; the excess is cash and is recorded as ad
    spend, not here)."""
    import math

    if source not in SOURCES:
        raise CreditRefused(f"{source!r} is not a credit source: {SOURCES}")
    if not (evidence_ref or "").strip():
        raise CreditRefused("an Ads-credit cycle with no evidence reference is a claim")
    if date.fromisoformat(cycle_end) <= date.fromisoformat(cycle_start):
        raise CreditRefused("a cycle ends after it starts")
    ent, shown = float(entitlement_usd), float(displayed_cad)
    if not (math.isfinite(ent) and ent > 0 and math.isfinite(shown) and shown > 0):
        raise CreditRefused("entitlement and displayed value are positive amounts")
    used = None if used_displayed_cad is None else float(used_displayed_cad)
    if used is not None and not (math.isfinite(used) and 0 <= used <= shown):
        raise CreditRefused("credit used is between 0 and the displayed credit")
    ensure_table(db)
    from sqlalchemy import select

    with db.session() as s:
        row = s.scalar(select(AdsCreditCycle).where(AdsCreditCycle.cycle_start == cycle_start))
        if row is None:
            row = AdsCreditCycle(cycle_start=cycle_start)
            s.add(row)
        row.cycle_end, row.entitlement_usd, row.displayed_cad = cycle_end, ent, shown
        row.used_displayed_cad, row.source = used, source
        row.evidence_ref = evidence_ref[:200]
        s.flush()
        return {"id": row.id, "cycle_start": cycle_start, "cycle_end": cycle_end}


def ads_credit(db, *, now: datetime | None = None) -> dict:
    """Every recorded Ads-credit cycle: entitlement, displayed CAD value, cycle, used and
    expired credit, and the incremental CASH ad spend beyond it. The credit never raises a
    ceiling and is never counted as owner cash."""
    from sqlalchemy import select

    from ..core.models import CostEntry

    ensure_table(db)
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    with db.session() as s:
        cycles = list(s.scalars(select(AdsCreditCycle).order_by(AdsCreditCycle.cycle_start)))
        ads = [((e.at if e.at.tzinfo else e.at.replace(tzinfo=timezone.utc)).date().isoformat(),
                float(e.amount_cad or 0.0))
               for e in s.scalars(select(CostEntry).where(CostEntry.kind == "ads"))]
    out = []
    for c in cycles:
        spend = round(sum(a for d, a in ads if c.cycle_start <= d < c.cycle_end), 6)
        ended = c.cycle_end <= today
        used = c.used_displayed_cad
        if used is None:
            # Without Etsy's reading of what the credit absorbed, cash beyond it is unknown --
            # unless nothing was spent at all.
            cash = 0.0 if spend == 0 else None
            expired = None
        else:
            cash = round(max(spend - used, 0.0), 6)
            expired = round(c.displayed_cad - used, 6) if ended else 0.0
        out.append({
            "cycle_start": c.cycle_start, "cycle_end": c.cycle_end,
            "official_entitlement_usd": c.entitlement_usd,
            "displayed_cad": c.displayed_cad,
            "converted_cad_at_assumed_rate": round(_to_cad(c.entitlement_usd, "USD"), 6),
            "used_cad": used, "used_basis": "etsy_reported" if used is not None else "UNKNOWN",
            "expired_cad": expired, "cycle_ended": ended,
            "recorded_ad_spend_cad": spend,
            "incremental_cash_spend_cad": cash,
            "source": c.source, "evidence_ref": c.evidence_ref,
        })
    return {
        "cycles": out,
        "owner_cash_is_separate": True,
        "ceilings_changed": 0,
        "rule": ("Ads credit is Etsy's to spend, not the owner's cash: it is reported beside "
                 "cash ad spend, never subtracted from a ceiling and never a budget"),
        "why_empty": ("" if out else "no Etsy Plus Ads-credit cycle has been recorded: the "
                      "entitlement is unverified and all recorded ad spend is cash"),
    }
