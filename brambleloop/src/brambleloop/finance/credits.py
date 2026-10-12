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


_LOCK = threading.Lock()
_FLAG = "_brambleloop_provider_credits_ready"


def ensure_table(db) -> None:
    engine = db.engine if hasattr(db, "engine") else db.get_bind()
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[ProviderCredit.__table__], checkfirst=True)
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
    }
