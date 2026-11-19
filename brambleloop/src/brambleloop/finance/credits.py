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

import re
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
    # ENG-CREDITS (W6), additive and nullable (`core.migrate` adds them to an existing table):
    # the usage period an owner-recorded model credit applies to, and who recorded it. Empty
    # on the rows written before them; such a grant keeps its old draw window.
    period_start: Mapped[str | None] = mapped_column(String(10), nullable=True, default="")
    period_end: Mapped[str | None] = mapped_column(String(10), nullable=True, default="")
    recorded_by: Mapped[str | None] = mapped_column(String(80), nullable=True, default="")
    # ENG-CREDITS fix round 1: a grant is never deleted. The owner VOIDS a wrong one (audited,
    # step-up); a voided grant draws nothing, is reported as voided and frees its period.
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)


class ProviderCreditLock(Base):
    """One row per model provider: the serialisation point of `record_model_credit`.

    The overlap check is check-then-insert, and no unique constraint can say "these periods
    overlap". Every recording first UPDATEs its provider's row, which takes a row lock on
    PostgreSQL (the second recorder waits for the first to commit, then reads its row) and the
    database write lock on SQLite, so the check and the insert are one atomic step on both.
    """
    __tablename__ = "provider_credit_locks"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    n: Mapped[int] = mapped_column(default=0)


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
                                                 ProviderCreditLock.__table__,
                                                 AdsCreditCycle.__table__], checkfirst=True)
        _seed_locks(db)
        setattr(engine, _FLAG, True)


def _seed_locks(db) -> None:
    """Make sure each model provider has its lock row (a lost race is harmless)."""
    from sqlalchemy.exc import IntegrityError

    for p in MODEL_PROVIDERS:
        try:
            with db.session() as s:
                if s.get(ProviderCreditLock, p) is None:
                    s.add(ProviderCreditLock(provider=p, n=0))
        except IntegrityError:
            pass


def _live(stmt):
    """Restrict a ProviderCredit select to grants that have not been voided."""
    return stmt.where(ProviderCredit.voided_at.is_(None))


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
        credits = list(s.scalars(_live(select(ProviderCredit)).order_by(
            ProviderCredit.granted_on, ProviderCredit.id)))
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


def _draw_until(c) -> str | None:
    """The last day a grant may absorb usage: the earlier of its stated expiry and the end of
    the usage period it was granted for (ENG-CREDITS). A grant with neither keeps the old
    reading (no stated end; its expiry basis is still UNKNOWN)."""
    ends = [d for d in (c.expires_on or "", getattr(c, "period_end", "") or "") if d]
    return min(ends) if ends else None


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
                   "from": c.period_start or c.granted_on,
                   "until": _draw_until(c),
                   "basis": _expiry_basis(c.expires_on, getattr(c, "period_end", ""))}
                  for c in s.scalars(_live(select(ProviderCredit)).where(
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
                        "expiry_basis": g["basis"],
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


# ---------------------------------------------------------------------------------------------
# ENG-CREDITS (W6): the owner's model-provider promotional credit, accounted per provider.
#
# The owner receives roughly US$100 a month of Anthropic API credit, and possibly an OpenAI
# credit. Neither is spending authority. This section only *accounts*:
#
# * The remaining eligible credit is UNKNOWN until the owner records a verified grant for the
#   period (`record_model_credit`, the Command Center's step-up action). Nothing here assumes a
#   credit exists, and nothing reads "no grant recorded" as "credit is zero" either.
# * Gross usage is the recorded ledger at this system's assumed list prices; billed usage is
#   only what a provider statement reported (`CostEntry.observed_cad`), else UNKNOWN; cash is
#   gross less the ESTIMATED credit draw, and with no grant recorded every call is cash.
# * The cash ceiling (`finance.spend_policy.CEILING_CAD`) is reported beside the credit and is
#   never changed by it: `routing.spent_this_month` and every reservation still count every
#   call at its recorded cost, credit or not (`ceilings_changed` is always 0).
# * Nothing here calls a provider, probes a balance, tops up or recharges: no supported API
#   reports an API key's remaining promotional credit, and a paid probe to find out would be
#   spend with nothing on the other side of it.
# ---------------------------------------------------------------------------------------------

MODEL_PROVIDERS: tuple[str, ...] = ("anthropic", "openai")
MODEL_CREDIT_ACTION = "finance.model_credit"     # the Command Center step-up action name
MODEL_CREDIT_RECORDED = "finance.model_credit_recorded"   # audit action (written, never read)
MIN_EVIDENCE_CHARS = 12
UNKNOWN = "UNKNOWN"
MODEL_COST_KINDS: tuple[str, ...] = ("llm",)


def _provider_of(name: str) -> str:
    """`anthropic-vision` is billed on the same Anthropic key as `anthropic`."""
    name = (name or "").strip().lower()
    for p in MODEL_PROVIDERS:
        if name == p or name.startswith(p + "-"):
            return p
    return name


MAX_GRANT_USD = 1000.0       # a sane per-provider ceiling for ONE period's promotional credit
MAX_NOTE_CHARS = 1000
MAX_PERIOD_DAYS = 366        # a credit period is at most a year, both ends inclusive
MODEL_CREDIT_VOID_ACTION = "finance.model_credit_void"            # step-up action name
MODEL_CREDIT_VOIDED = "finance.model_credit_voided"               # audit action (written, never read)
_CURRENCIES = ("CAD", "USD")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Test seam: called after the overlap check and before the insert, inside the transaction.
_before_insert = None


def _iso_date(label: str, value) -> date:
    """A strict YYYY-MM-DD (date.fromisoformat also takes 20261101 and 2026-W01-1)."""
    text = value if isinstance(value, str) else ""
    if not _ISO_DATE.match(text):
        raise CreditRefused(f"{label} is an ISO date, YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise CreditRefused(f"{label} is an ISO date, YYYY-MM-DD") from None


def _screened_note(label: str, value, minimum: int) -> str:
    """The note with whitespace collapsed, refused if it is too short to be evidence or looks
    like it carries a secret. A refusal names the kind of pattern, never the matched text."""
    from ..ops import log_secret_guard

    if isinstance(value, str) and len(value) > MAX_NOTE_CHARS * 4:
        raise CreditRefused(f"the {label} is at most {MAX_NOTE_CHARS} characters")
    note = " ".join(str(value or "").split())
    if len(note) > MAX_NOTE_CHARS:
        raise CreditRefused(f"the {label} is at most {MAX_NOTE_CHARS} characters")
    hits = log_secret_guard.scan_text(note)
    if hits:
        kinds = sorted({name for _, name, _ in hits})
        raise CreditRefused(f"the {label} looks like it contains a secret ({', '.join(kinds)}); "
                            f"write where it was read, never a key or token -- nothing was "
                            f"recorded")
    if len(note) < minimum:
        raise CreditRefused(
            "an evidence note says where the grant was read (the provider's billing page, an "
            "email, a statement); without it the grant is a claim, not a credit"
            if label == "evidence note" else f"the {label} is at least {minimum} characters")
    return note


def _expiry_basis(expires_on, period_end) -> str:
    """How the end of a grant's draw window is known: stated by the owner, bounded only by the
    period the owner recorded, or UNKNOWN. Never "does not expire"."""
    return "stated" if expires_on else ("period_end" if period_end else UNKNOWN)


def record_model_credit(db, *, provider: str, amount, currency: str,
                        period_start: str, period_end: str, expires_on: str = "",
                        evidence_note: str, recorded_by: str) -> dict:
    """Record one owner-verified model-provider credit grant for a usage period.

    Refuses: a provider that is not a model provider; an amount that is not a real number (a
    bool, a string, None), is non-positive, non-finite or above `MAX_GRANT_USD` (US$1000)
    per period; a currency other than CAD or USD; dates that are not strict YYYY-MM-DD, a
    period that ends before it starts or runs past `MAX_PERIOD_DAYS` (one year), an expiry
    before the period starts; an evidence note too short to be evidence or carrying a
    secret-like string; a recorder that is not the owner's Command Center session; and a second
    grant for the same provider whose period overlaps a live one (the same credit counted
    twice would read as twice the credit). A voided grant frees its period. The overlap check
    and the insert are one atomic step (`ProviderCreditLock`). An empty `expires_on` is
    recorded with expiry_basis "period_end", never "does not expire". The grant is accounting
    only: it changes no ceiling and authorises no call.
    """
    import math

    from sqlalchemy import select, update

    provider = (provider or "").strip().lower() if isinstance(provider, str) else ""
    if provider not in MODEL_PROVIDERS:
        raise CreditRefused(f"that is not a model provider: {MODEL_PROVIDERS}")
    if not str(recorded_by or "").startswith("owner:"):
        raise CreditRefused("only the owner records a model credit grant")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise CreditRefused("amount is a number")
    amt = float(amount)
    if not math.isfinite(amt) or amt <= 0:
        raise CreditRefused("a credit is a positive amount")
    cur = currency.strip().upper() if isinstance(currency, str) else ""
    if cur not in _CURRENCIES:
        raise CreditRefused(f"currency is one of {_CURRENCIES}")
    start = _iso_date("period_start", period_start)
    end = _iso_date("period_end", period_end)
    expiry = _iso_date("expires_on", expires_on) if expires_on else None
    if end < start:
        raise CreditRefused("the credit period ends before it starts")
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise CreditRefused(f"a credit period is at most {MAX_PERIOD_DAYS} days")
    if expiry is not None and expiry < start:
        raise CreditRefused("the credit expires before its period starts")
    from ..gateway.routing import USD_PER_CAD

    usd = amt if cur == "USD" else amt * USD_PER_CAD
    if usd > MAX_GRANT_USD + 1e-6:       # float round trip of a CAD edge amount
        raise CreditRefused(f"a credit above US${MAX_GRANT_USD:,.0f} per period is not "
                            f"recorded; check the amount and the currency")
    note = _screened_note("evidence note", evidence_note, MIN_EVIDENCE_CHARS)
    ensure_table(db)
    with db.session() as s:
        # Serialise recorders of this provider: the overlap read and the insert are one step.
        locked = s.execute(update(ProviderCreditLock).where(
            ProviderCreditLock.provider == provider).values(n=ProviderCreditLock.n + 1))
        if locked.rowcount != 1:
            raise CreditRefused("the credit ledger lock is missing; nothing was recorded")
        for c in s.scalars(_live(select(ProviderCredit)).where(
                ProviderCredit.provider == provider,
                ProviderCredit.kind == "promotional_credit")):
            c_start = c.period_start or c.granted_on
            c_end = c.period_end or c.expires_on or "9999-12-31"
            if c_start <= end.isoformat() and start.isoformat() <= c_end:
                raise CreditRefused(f"a {provider} credit for an overlapping period "
                                    f"({c_start}..{c_end}) is already recorded (id {c.id}); "
                                    f"void it first if it was recorded wrongly")
        if _before_insert is not None:
            _before_insert()
        row = ProviderCredit(provider=provider, kind="promotional_credit", amount=amt,
                             currency=cur, granted_on=start.isoformat(),
                             expires_on=expiry.isoformat() if expiry else "",
                             source="owner_reported", evidence_ref=note[:200], note=note,
                             period_start=start.isoformat(), period_end=end.isoformat(),
                             recorded_by=str(recorded_by)[:80])
        s.add(row)
        s.flush()
        rid = row.id
    return {"id": rid, "provider": provider, "amount": amt, "currency": cur,
            "amount_cad": round(_to_cad(amt, cur), 6),
            "period_start": start.isoformat(), "period_end": end.isoformat(),
            "expires_on": expiry.isoformat() if expiry else None,
            "expiry_basis": _expiry_basis(expiry, end),
            "ceilings_changed": 0}


def void_model_credit(db, *, grant_id, reason: str, voided_by: str,
                      now: datetime | None = None) -> dict:
    """Void one recorded model credit grant: the owner's correction for a wrong grant.

    Nothing is deleted. The row stays, marked voided with who, when and why; from then on it
    draws no usage, is not counted as credit, and no longer blocks an overlapping grant. Only
    the owner voids; the reason must say why and must not carry a secret; a grant already
    voided, or one that does not exist, is refused. Accounting only: no ceiling changes.
    """
    from sqlalchemy import select, update

    if not str(voided_by or "").startswith("owner:"):
        raise CreditRefused("only the owner voids a model credit grant")
    if isinstance(grant_id, bool) or not isinstance(grant_id, int) or grant_id < 1:
        raise CreditRefused("grant_id is the id of a recorded grant")
    why = _screened_note("void reason", reason, MIN_EVIDENCE_CHARS)
    now = now or datetime.now(timezone.utc)
    ensure_table(db)
    with db.session() as s:
        row = s.scalar(select(ProviderCredit).where(
            ProviderCredit.id == grant_id, ProviderCredit.kind == "promotional_credit",
            ProviderCredit.source == "owner_reported"))
        if row is None:
            raise CreditRefused(f"no owner-recorded model credit grant has id {grant_id}")
        provider = _provider_of(row.provider)
        # Same lock as recording, so a void and a new grant for the provider do not interleave.
        s.execute(update(ProviderCreditLock).where(
            ProviderCreditLock.provider == provider).values(n=ProviderCreditLock.n + 1))
        s.refresh(row)
        if row.voided_at is not None:
            raise CreditRefused(f"grant {grant_id} is already voided")
        row.voided_at, row.voided_by, row.void_reason = now, str(voided_by)[:80], why[:300]
        out = {"id": row.id, "provider": provider, "amount": row.amount,
               "currency": row.currency, "period_start": row.period_start or row.granted_on,
               "period_end": row.period_end or None, "voided_at": now.isoformat(),
               "void_reason": why[:300]}
    return {**out, "ceilings_changed": 0}


def _month_window(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start.replace(year=start.year + 1, month=1) if start.month == 12
           else start.replace(month=start.month + 1))
    return start, nxt


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _failed_and_uncertain(db, provider: str, start: datetime, end: datetime) -> dict:
    """Paid calls this month for `provider` (and its `-vision` key) by outcome. UNCERTAIN is
    counted at its estimate, never 0; DECLINED never billed; FAILED_BILLED billed and failed."""
    from sqlalchemy import inspect as sa_inspect, select

    from ..gateway.paid_calls import DECLINED, FAILED_BILLED, UNCERTAIN, PaidCallRecord

    out = {"declined": 0, "failed_billed": 0, "failed_billed_estimate_cad": 0.0,
           "uncertain": 0, "uncertain_estimate_cad": 0.0}
    with db.session() as s:
        if PaidCallRecord.__tablename__ not in set(sa_inspect(s.get_bind()).get_table_names()):
            out["why"] = "no paid call has been guarded yet (the table does not exist)"
            return out
        for r in s.scalars(select(PaidCallRecord).where(
                PaidCallRecord.provider.in_((provider, f"{provider}-vision")),
                PaidCallRecord.outcome.in_((DECLINED, FAILED_BILLED, UNCERTAIN)))):
            at = _aware(r.at)
            if at is None or not (start <= at < end):
                continue
            if r.outcome == DECLINED:
                out["declined"] += 1
            elif r.outcome == FAILED_BILLED:
                out["failed_billed"] += 1
                out["failed_billed_estimate_cad"] += float(r.estimate_cad or 0.0)
            else:
                out["uncertain"] += 1
                out["uncertain_estimate_cad"] += float(r.estimate_cad or 0.0)
    out["failed_billed_estimate_cad"] = round(out["failed_billed_estimate_cad"], 6)
    out["uncertain_estimate_cad"] = round(out["uncertain_estimate_cad"], 6)
    return out


def model_credit_accounting(db, *, now: datetime | None = None) -> dict:
    """Per model provider, this calendar month: the remaining eligible promotional credit
    (UNKNOWN until recorded), gross usage, provider-billed usage (UNKNOWN until a statement is
    read), estimated cash, failed and uncertain calls -- beside the cash ceiling, unchanged.

    Read-only: no row is written, no provider is called.
    """
    from sqlalchemy import select

    from ..core.models import CostEntry
    from ..gateway.routing import USD_PER_CAD
    from . import spend_policy

    ensure_table(db)
    now = now or datetime.now(timezone.utc)
    start, end = _month_window(now)
    today = now.date().isoformat()
    m0, m1 = start.date().isoformat(), (end.date().isoformat())
    with db.session() as s:
        all_grants = list(s.scalars(select(ProviderCredit).where(
            ProviderCredit.kind == "promotional_credit").order_by(
            ProviderCredit.granted_on, ProviderCredit.id)))
        grants = [g for g in all_grants if g.voided_at is None]
        voided_rows = [{"id": g.id, "provider": _provider_of(g.provider), "amount": g.amount,
                        "currency": g.currency, "period_start": g.period_start or g.granted_on,
                        "period_end": g.period_end or None,
                        "voided_at": g.voided_at.isoformat(), "voided_by": g.voided_by or "",
                        "void_reason": g.void_reason or ""}
                       for g in all_grants if g.voided_at is not None]
        grant_rows = [{"id": g.id, "provider": _provider_of(g.provider), "amount": g.amount,
                       "currency": g.currency, "amount_cad": round(_to_cad(g.amount, g.currency), 6),
                       "period_start": g.period_start or g.granted_on,
                       "period_end": g.period_end or None,
                       "expires_on": g.expires_on or None,
                       "expiry_basis": _expiry_basis(g.expires_on, g.period_end),
                       "recorded_by": g.recorded_by or "", "evidence_ref": g.evidence_ref,
                       "draw_until": _draw_until(g)} for g in grants]
        entries = [(e.id, _provider_of(e.provider), float(e.amount_cad or 0.0),
                    e.observed_cad, e.kind)
                   for e in s.scalars(select(CostEntry).where(
                       CostEntry.at >= start, CostEntry.at < end))]
    providers = {}
    for p in MODEL_PROVIDERS:
        mine = [e for e in entries if e[1] == p]
        gross = round(sum(e[2] for e in mine), 6)
        observed = [e for e in mine if e[3] is not None]
        reported = round(sum(float(e[3]) for e in observed), 6) if observed else None
        # Billed usage is a total only when the provider reported every row; with only some
        # rows reported it is UNKNOWN (the partial sum is shown beside it, labelled partial).
        billed_state = ("UNKNOWN" if not observed else
                        "COMPLETE" if len(observed) == len(mine) else "PARTIAL")
        billed = reported if billed_state == "COMPLETE" else UNKNOWN
        p_grants = [g for g in grant_rows if g["provider"] == p]
        # A grant is eligible this month when its usage window overlaps the month.
        active = [g for g in p_grants
                  if g["period_start"] < m1 and (g["draw_until"] or "9999-12-31") >= m0]
        current = [g for g in active if g["period_start"] <= today
                   and (g["draw_until"] or "9999-12-31") >= today]
        led = split(db, p, now=now) if p_grants else None
        if led is not None:
            month_calls = {c["cost_entry"]: c for c in led["calls"]}
            promo = round(sum(month_calls[e[0]]["promo_credit_cad"] for e in mine
                              if e[0] in month_calls), 6)
            cash = round(gross - promo, 6)
            left_by_id = {g["id"]: g["estimated_left_cad"] for g in led["grants"]}
        else:
            promo, cash, left_by_id = 0.0, gross, {}
        for g in p_grants:
            g["estimated_left_cad"] = left_by_id.get(g["id"])
        if current:
            remaining = round(sum(left_by_id.get(g["id"]) or 0.0 for g in current), 6)
            credit = {"state": "RECORDED", "remaining_eligible_cad": remaining,
                      "remaining_eligible_usd": round(remaining * USD_PER_CAD, 6),
                      "basis": "ESTIMATED: owner-recorded grant less the assumed draw "
                               "(credits first) of recorded usage; never a provider balance",
                      "why": ""}
        else:
            credit = {"state": UNKNOWN, "remaining_eligible_cad": UNKNOWN,
                      "remaining_eligible_usd": UNKNOWN, "basis": UNKNOWN,
                      "why": (f"no verified {p} credit grant is recorded for the period "
                              f"covering {today}; the credit is not assumed to exist, and "
                              f"every call is counted as cash")}
        providers[p] = {
            "credit": credit,
            "grants": p_grants,
            "voided_grants": [v for v in voided_rows if v["provider"] == p],
            "gross_usage_cad": gross,
            "gross_usage_usd": round(gross * USD_PER_CAD, 6),
            "gross_basis": "recorded at this system's assumed list prices (not an invoice)",
            "calls": len(mine),
            "billed_usage_cad": billed,
            "billed_state": billed_state,
            "billed_reported_partial_cad": reported if billed_state == "PARTIAL" else None,
            "billed_basis": (f"provider-reported for {len(observed)} of {len(mine)} rows"
                             + ("" if billed_state == "COMPLETE" else
                                "; the total is UNKNOWN until every row is reported (the "
                                "reported part is shown as a partial figure, never as the bill)")
                             if observed else
                             "UNKNOWN: no provider statement has been read for this month"),
            "estimated_credit_absorbed_cad": promo,
            "estimated_cash_cad": cash,
            "cash_basis": ("ESTIMATED: gross less the assumed credit draw" if p_grants else
                           "no credit recorded: all recorded usage is treated as cash"),
            "calls_outcomes": _failed_and_uncertain(db, p, start, end),
        }
    ceiling = spend_policy.ceiling_cad()
    return {
        "month": start.strftime("%Y-%m"), "as_of": now.isoformat(), "currency": "CAD",
        "providers": providers,
        "cash_ceiling_cad": ceiling,
        "ceiling_rule": ("a promotional credit is not spending authority: the monthly cash "
                         "ceiling counts every recorded call at its cost, credit or not"),
        "ceilings_changed": 0,
        "balance_probe": "none: no supported API reports a key's remaining promotional "
                         "credit, and no paid probe or auto-recharge is made to find out",
        "draw_assumption": DRAW_ASSUMPTION,
    }


def model_cost_by_product(db, *, now: datetime | None = None) -> dict:
    """Model (`llm`) cost this calendar month per product and per certified listing package.

    Reconciles: per-product totals plus the unattributed remainder equal the month's model
    ledger total. The ledger records the product, not the release version, so a package's
    cost is its product's cost when the product has exactly one certified package; with
    several, the per-package figure is UNKNOWN rather than an invented split.
    """
    from sqlalchemy import select

    from ..core.models import CostEntry

    now = now or datetime.now(timezone.utc)
    start, end = _month_window(now)
    with db.session() as s:
        rows = [(e.product_slug or "", float(e.amount_cad or 0.0), _provider_of(e.provider))
                for e in s.scalars(select(CostEntry).where(
                    CostEntry.kind.in_(MODEL_COST_KINDS),
                    CostEntry.at >= start, CostEntry.at < end))]
    total = round(sum(r[1] for r in rows), 6)
    by_product: dict[str, dict] = {}
    unattributed = 0.0
    for slug, cad, prov in rows:
        if not slug:
            unattributed += cad
            continue
        b = by_product.setdefault(slug, {"product_slug": slug, "cad": 0.0, "calls": 0,
                                         "by_provider": {}})
        b["cad"] += cad
        b["calls"] += 1
        b["by_provider"][prov] = round(b["by_provider"].get(prov, 0.0) + cad, 6)
    products = sorted(({**v, "cad": round(v["cad"], 6)} for v in by_product.values()),
                      key=lambda r: (-r["cad"], r["product_slug"]))
    packages, why_packages = [], ""
    try:
        from ..publish import listing_package

        certified = listing_package.certified_releases(db)
        per_slug: dict[str, int] = {}
        for slug, _v in certified:
            per_slug[slug] = per_slug.get(slug, 0) + 1
        for slug, version in certified:
            pkg = listing_package.latest(db, slug, version) or {}
            product_cad = round(by_product.get(slug, {}).get("cad", 0.0), 6)
            alone = per_slug[slug] == 1
            packages.append({
                "package": f"{slug}@{version}", "status": pkg.get("status") or UNKNOWN,
                "product_model_cost_cad": product_cad,
                "package_model_cost_cad": product_cad if alone else UNKNOWN,
                "basis": ("product-level: the only certified package of this product" if alone
                          else "UNKNOWN: the ledger records the product, not the version, "
                               "and this product has several certified packages")})
    except Exception as exc:  # noqa: BLE001 - unreadable packages never blank the products
        why_packages = f"certified packages unreadable: {type(exc).__name__}"
    accounted = round(sum(p["cad"] for p in products) + unattributed, 6)
    return {"month": start.strftime("%Y-%m"), "kinds": list(MODEL_COST_KINDS),
            "ledger_total_cad": total, "by_product": products,
            "unattributed_cad": round(unattributed, 6),
            "reconciles": abs(accounted - total) < 1e-6,
            "certified_packages": packages, "why_packages": why_packages,
            "basis": "recorded at this system's assumed list prices (not an invoice)"}


# ENG-CREDITS part 3: where an approved model call would raise certified throughput or quality,
# and whether it is starved now. Read-only; it wires nothing and changes no ceiling. A family
# with no call site is reported NO_CALLER (adding one is a routing change for the owner card).
PRODUCTIVE_FAMILIES: tuple[dict, ...] = (
    {"family": "concept_generation", "agent": "creative_director",
     "tasks": ("concept_generation", "concept_ideation", "construction_reading")},
    {"family": "independent_review", "agent": "creative_director",
     "tasks": ("benchmark_challenge",)},
    {"family": "image_review", "agent": "quality_director", "tasks": ("asset_inspection",)},
    {"family": "taste_gate", "agent": "creative_director",
     "tasks": ("creative_evaluation", "gallery_observation")},
    {"family": "listing_copy_refinement", "agent": "publishing", "tasks": ("listing_copy",),
     "no_caller": "listing copy is deterministic templating (commerce.seo); no model call "
                  "site exists"},
    {"family": "defect_learning", "agent": "", "tasks": (),
     "no_caller": "no model task is declared; improve.failure_memory is deterministic"},
)


def productive_model_use(db, *, now: datetime | None = None) -> dict:
    """Per productive family, this month: model calls and spend, ceiling refusals by which
    ceiling refused, and the governing agent's daily ceiling. STARVED when a ceiling refused
    its work this month; NO_CALLER when no call site exists; IDLE when nothing ran."""
    from sqlalchemy import select

    from ..agents.registry import DEFAULT_AGENTS
    from ..core.models import AuditLog, CostEntry
    from . import spend_policy, spend_report

    now = now or datetime.now(timezone.utc)
    start, end = _month_window(now)
    ceilings = {a.get("name"): a.get("daily_cost_ceiling_cad") for a in DEFAULT_AGENTS}
    with db.session() as s:
        costs = [(e.purpose or (e.detail or {}).get("task") or "", e.agent or "",
                  float(e.amount_cad or 0.0))
                 for e in s.scalars(select(CostEntry).where(
                     CostEntry.kind.in_(MODEL_COST_KINDS),
                     CostEntry.at >= start, CostEntry.at < end))]
        refused = []
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == spend_report.REFUSED_ACTION)):
            at = _aware(row.at)
            if at is None or not (start <= at < end):
                continue
            d = row.detail or {}
            refused.append((str(d.get("purpose") or row.artifact or ""),
                            str(d.get("agent") or row.actor or ""),
                            str(d.get("which") or "unknown")))
    out = []
    for fam in PRODUCTIVE_FAMILIES:
        tasks = set(fam["tasks"])
        mine = [c for c in costs if c[0] in tasks]
        refusals: dict[str, int] = {}
        for purpose, agent, which in refused:
            if purpose in tasks or (fam["agent"] and agent == fam["agent"] and which == "agent"):
                refusals[which] = refusals.get(which, 0) + 1
        if fam.get("no_caller"):
            state, why = "NO_CALLER", fam["no_caller"]
        elif refusals:
            state = "STARVED"
            why = "refused this month by: " + ", ".join(
                f"{k} x{v}" for k, v in sorted(refusals.items()))
        elif mine:
            state, why = "RUNNING", "model calls were recorded this month, none refused"
        else:
            state, why = "IDLE", "no model call and no refusal recorded this month"
        out.append({"family": fam["family"], "tasks": list(fam["tasks"]), "state": state,
                    "why": why, "calls": len(mine),
                    "spend_cad": round(sum(c[2] for c in mine), 6),
                    "refusals": refusals, "agent": fam["agent"] or None,
                    "agent_daily_ceiling_cad": ceilings.get(fam["agent"]),
                    "allocations": {t: spend_policy.ALLOCATION[t] for t in fam["tasks"]
                                    if t in spend_policy.ALLOCATION}})
    return {"month": start.strftime("%Y-%m"), "families": out, "ceilings_changed": 0,
            "wired": "nothing: this view reports; raising a ceiling or adding a call site is an "
                     "owner decision with this evidence attached"}
