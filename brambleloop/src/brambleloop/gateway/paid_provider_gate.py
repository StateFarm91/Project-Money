"""P0-PAID-PROVIDER-OWNER-GATE: a credential never authorises a paid image or vision call.

Owner directive 2026-11-02: "Provider credentials must never automatically authorize paid
image generation. ... The presence of an API key must not activate paid calls."

Production (0967c3ee) had `BRAMBLELOOP_IMAGE_KEY_BFL` set and contacted the BFL image API on the
six-hourly capability-probe cadence with no owner activation: `images.probe_if_due` rendered a
paid image because a key existed, a successful probe opened the `image_generation` gate, and
the gate opened paid generation everywhere downstream. The vision probe spent the same way.

Two things live here.

1. **The owner activation record** (`paid_provider_activations`). One row per owner activation
   of one paid provider for one scope (`generation`, `vision` or `probe`). Default OFF: the
   absence of an active row is OFF. A row exists only through `activate`, which demands the
   owner's Command Center step-up -- verified against the `OwnerSession` row the step-up wrote
   (the same mechanism every other consequential owner approval uses), not a boolean a caller
   asserts -- and carries the provider's own CA$ ceilings (per UTC day and per month), a
   per-gallery limit, a retry ceiling, a per-run call ceiling and an expiry. `revoke` stamps
   `revoked_at`; both write an audit row in the same transaction as the change.

2. **The one enforcement point** (`enforce`). Every paid image render (`images.generate`,
   `images.submit_render`) and every paid vision call (`AnthropicProvider.see`,
   `visual.d_judge.see`) passes through it immediately before its network I/O -- probes,
   benches, experiments, repairs and retries included, because they all reach the provider
   through those functions. It refuses with a named reason and no network I/O unless ALL hold:

   * the accounting store is present and readable (`accounting_store_missing` /
     `accounting_store_unreadable`): no evidence, no call;
   * an active, unexpired, unrevoked owner activation covers this provider and scope
     (`not_activated_by_owner`, `activation_expired`, `activation_revoked`);
   * the company-budget reservation this call was allowed on exists and is live
     (`no_budget_reservation`) -- the accounting evidence `check_budget_cad` writes;
   * the month the company ceiling governs (`anthropic.monthly_ceiling_cad`, the
     BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD / spend-policy ceiling -- reused, not restated) is
     not exceeded by billed spend plus every live reservation (`company_monthly_budget`);
   * the provider's activation ceilings, per UTC day and per month, counting reserved, billed
     and uncertain calls (`provider_daily_ceiling`, `provider_monthly_ceiling`);
   * the per-gallery limit (`per_gallery_limit`);
   * idempotency: an identical request already billed (or whose outcome is unknown) in this
     run is never sent again (`already_billed`), keyed like `paid_calls` keys it;
   * the retry ceiling per request (`retry_ceiling`) and the call ceiling per run
     (`run_call_ceiling`).

   A call that passes is written RESERVED in `paid_provider_calls` before it leaves; the
   activation is re-read immediately before the network I/O (`confirm`), so a revocation that
   lands between the reservation and the call refuses it; the row is then settled BILLED,
   RELEASED (refused before the provider did any work) or UNCERTAIN (counted as billed).
   A RESERVED row whose process died is never settled and stays counted: an orphan is billed
   for ceiling purposes, never zero.

The capability gates read activation too: `image_generation` / `image_vision` are open only
while an activation for the scope is active AND the latest probe was made under an activation
that is still active (`probe_activation_open`). A key alone, or an old probe row alone, never
opens either gate.
"""
from __future__ import annotations

import hashlib
import math
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import JSON, DateTime, Float, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow
from ..core.resilience import PermanentError

# ---- vocabulary ------------------------------------------------------------------------------

GENERATION, VISION, PROBE = "generation", "vision", "probe"
SCOPES = (GENERATION, VISION, PROBE)

# The paid vision providers. Image generators come from `images.PROVIDERS` (every one of them,
# read at call time so a provider added there is gated without an edit here).
ANTHROPIC_VISION = "anthropic-vision"     # `AnthropicProvider.see` -- every Claude vision call
OPENAI_VISION = "openai-vision"           # `visual.d_judge.see` -- the research judge
VISION_PROVIDERS: dict[str, str] = {
    ANTHROPIC_VISION: "Anthropic Messages API with images (every vision judge and observer)",
    OPENAI_VISION: "OpenAI chat completions with an inline image (visual.d_judge)",
}

NOT_ACTIVATED = "not_activated_by_owner"
EXPIRED = "activation_expired"
REVOKED = "activation_revoked"

RESERVED, BILLED, RELEASED, UNCERTAIN = "RESERVED", "BILLED", "RELEASED", "UNCERTAIN"
# Statuses that count against a ceiling: reserved (in flight or orphaned), billed, unknown.
COUNTED = (RESERVED, BILLED, UNCERTAIN)

ACTION_ACTIVATED = "paid_provider.activated"
ACTION_REVOKED = "paid_provider.revoked"
ACTION_REFUSED = "paid_provider.refused"
STEP_UP_ACTION = "paid_provider.activate"

DEFAULT_EXPIRY = timedelta(days=30)
MAX_EXPIRY = timedelta(days=90)
DEFAULT_MAX_ATTEMPTS = 2           # one call and one retry of the same request
DEFAULT_MAX_CALLS_PER_RUN = 40
KEY_IS_NOT_ACTIVATION = (
    "a provider API key is a credential, not an activation: no paid image or vision call is "
    "made until the owner activates that provider here (step-up), with its own daily and "
    "monthly CA$ ceilings, a per-gallery limit and an expiry")


class PaidCallRefused(PermanentError):
    """Refused at the enforcement point before any network I/O. `.code` names the reason."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code


class ActivationRefused(ValueError):
    """An activation or revocation request that does not meet the owner-approval rule."""


# ---- tables (additive; unknown to 0967c3ee, so a rollback simply ignores them) -------------

class PaidProviderActivation(Base):
    __tablename__ = "paid_provider_activations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    scope: Mapped[str] = mapped_column(String(16), index=True)
    activated_by: Mapped[str] = mapped_column(String(120))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    step_up: Mapped[dict] = mapped_column(JSON, default=dict)
    daily_ceiling_cad: Mapped[float] = mapped_column(Float)
    monthly_ceiling_cad: Mapped[float] = mapped_column(Float)
    per_gallery_cad: Mapped[float] = mapped_column(Float)
    max_attempts_per_request: Mapped[int] = mapped_column(Integer, default=DEFAULT_MAX_ATTEMPTS)
    max_calls_per_run: Mapped[int] = mapped_column(Integer, default=DEFAULT_MAX_CALLS_PER_RUN)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str] = mapped_column(String(120), default="")
    revoke_reason: Mapped[str] = mapped_column(String(300), default="")
    note: Mapped[str] = mapped_column(String(300), default="")


class PaidProviderCall(Base):
    __tablename__ = "paid_provider_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activation_id: Mapped[int] = mapped_column(Integer, index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    scope: Mapped[str] = mapped_column(String(16))
    gallery: Mapped[str] = mapped_column(String(160), index=True)
    run_key: Mapped[str] = mapped_column(String(80), index=True)
    idem_key: Mapped[str] = mapped_column(String(64), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(80), default="")
    estimate_cad: Mapped[float] = mapped_column(Float)
    actual_cad: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default=RESERVED, index=True)
    reservation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(String(300), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


_LOCK = threading.Lock()
_FLAG = "_brambleloop_paid_provider_gate"


def ensure_tables(db) -> None:
    engine = db.engine
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[PaidProviderActivation.__table__,
                                                 PaidProviderCall.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)


def _now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


# ---- which providers are paid, and for what --------------------------------------------------

def image_providers() -> list[str]:
    from . import images

    return [p.key for p in images.PROVIDERS]


def family(provider: str) -> str:
    """`image` or `vision`; anything else is not a provider this gate knows (refused)."""
    if provider in VISION_PROVIDERS:
        return "vision"
    if provider in image_providers():
        return "image"
    return ""


def scopes_for(provider: str) -> tuple[str, ...]:
    fam = family(provider)
    return (GENERATION, PROBE) if fam == "image" else (VISION, PROBE) if fam == "vision" else ()


def _covering(scope: str) -> tuple[str, ...]:
    """Activation scopes that authorise a call of `scope`. A generation (or vision) activation
    covers that provider's probe; a probe-only activation covers nothing else."""
    return (scope,) if scope != PROBE else (PROBE, GENERATION, VISION)


# ---- gallery context ------------------------------------------------------------------------

_GALLERY: ContextVar[str] = ContextVar("brambleloop_paid_gallery", default="")


@contextmanager
def gallery_scope(key: str | None):
    """Charge every paid call inside this block to gallery `key` (an image-production run)."""
    token = _GALLERY.set(str(key or "")[:160])
    try:
        yield
    finally:
        _GALLERY.reset(token)


def current_gallery() -> str:
    """The gallery a call is charged to: the explicit scope, else the product the running job
    works for, else the job, else `shared`. Never empty, so a limit always has a bucket."""
    g = _GALLERY.get()
    if g:
        return g
    from ..finance import spend_report
    from . import paid_calls

    slug = spend_report.current_product()
    if slug:
        return f"product:{slug}"[:160]
    jid = paid_calls.current_job_id()
    return f"job:{jid}" if jid is not None else "shared"


# ---- which scope a vision call is made for (a probe, or ordinary vision work) -----------------

_CALL_SCOPE: ContextVar[str] = ContextVar("brambleloop_paid_call_scope_name", default="")


@contextmanager
def call_scope(scope: str):
    """Mark the paid vision calls inside this block as `scope` (the vision probe: PROBE)."""
    token = _CALL_SCOPE.set(scope)
    try:
        yield
    finally:
        _CALL_SCOPE.reset(token)


def current_call_scope(default: str) -> str:
    return _CALL_SCOPE.get() or default


# ---- the budget evidence a vision call is allowed on ------------------------------------------
#
# `anthropic.check_budget_cad` notes every reservation it writes here (per context, so per
# thread); `AnthropicProvider.see` consumes the note. A vision call with no reservation in its
# context has no accounting evidence and is refused. Images pass their reservation explicitly.

_BUDGET: ContextVar[tuple | None] = ContextVar("brambleloop_paid_gate_budget", default=None)


def note_budget(db, decided: dict | None) -> None:
    if db is not None and decided and decided.get("reservation_id") is not None:
        _BUDGET.set((db, dict(decided)))


def take_budget() -> tuple[Any, dict] | tuple[None, None]:
    held = _BUDGET.get()
    _BUDGET.set(None)
    return held if held else (None, None)


# ---- activation: the owner's route ---------------------------------------------------------

def _finite_positive(name: str, value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ActivationRefused(f"{name} must be a number of CA$; got {value!r}") from None
    if not math.isfinite(v) or v <= 0:
        raise ActivationRefused(f"{name} must be a finite amount above zero; got {value!r}")
    return round(v, 6)


def verify_step_up(db, session_public_id: str, *, now: datetime | None = None) -> dict:
    """The owner's step-up, read from the session row the step-up itself wrote
    (`command_center.auth.grant_stepup`). Not a flag: a live, unrevoked owner session whose
    step-up window is open now. Returns the evidence stored with the activation."""
    from ..app.command_center import auth as cc_auth
    from ..app.command_center.models import OwnerSession

    pid = str(session_public_id or "").strip()
    if not pid:
        raise ActivationRefused("no step-up evidence: an activation needs the owner's Command "
                                "Center session with a fresh step-up")
    now = _now(now)
    cc_auth.ensure_tables(db)
    with db.session() as s:
        row = s.scalar(select(OwnerSession).where(OwnerSession.public_id == pid))
        if row is None:
            raise ActivationRefused("no step-up evidence: the session named is not an owner "
                                    "session")
        if row.revoked_at is not None:
            raise ActivationRefused("no step-up evidence: the owner session was revoked")
        if _aware(row.expires_at) is not None and _aware(row.expires_at) <= now:
            raise ActivationRefused("no step-up evidence: the owner session has expired")
        until = _aware(row.stepup_until)
        if until is None or until <= now:
            raise ActivationRefused("no step-up evidence: the owner session has no open "
                                    "step-up window; re-authenticate (step-up) first")
        return {"mechanism": "command_center.auth step-up (OwnerSession.stepup_until)",
                "session_public_id": pid, "stepup_until": until.isoformat(),
                "verified_at": now.isoformat()}


def activate(db, *, provider: str, scope: str, by: str, session_public_id: str,
             daily_ceiling_cad, monthly_ceiling_cad, per_gallery_cad,
             expires_at: datetime | None = None,
             max_attempts_per_request: int = DEFAULT_MAX_ATTEMPTS,
             max_calls_per_run: int = DEFAULT_MAX_CALLS_PER_RUN, note: str = "",
             now: datetime | None = None) -> dict:
    """The owner activates one paid provider for one scope. Step-up verified; audited."""
    from ..core.models import AuditLog

    now = _now(now)
    if scope not in scopes_for(provider):
        raise ActivationRefused(
            f"{provider!r} cannot be activated for {scope!r}: known paid providers and their "
            f"scopes are {sorted((p, scopes_for(p)) for p in image_providers() + list(VISION_PROVIDERS))}")
    if not str(by or "").strip():
        raise ActivationRefused("an activation names the owner who gave it")
    evidence = verify_step_up(db, session_public_id, now=now)
    daily = _finite_positive("daily_ceiling_cad", daily_ceiling_cad)
    monthly = _finite_positive("monthly_ceiling_cad", monthly_ceiling_cad)
    gallery = _finite_positive("per_gallery_cad", per_gallery_cad)
    if daily > monthly:
        raise ActivationRefused(f"the daily ceiling CA${daily} exceeds the monthly ceiling "
                                f"CA${monthly}")
    from . import anthropic as gw

    company = gw.monthly_ceiling_cad()
    if monthly > company:
        raise ActivationRefused(f"the provider's monthly ceiling CA${monthly} exceeds the "
                                f"company's monthly ceiling CA${company:.2f}; the company "
                                f"ceiling is raised separately, never through an activation")
    try:
        attempts, per_run = int(max_attempts_per_request), int(max_calls_per_run)
    except (TypeError, ValueError):
        raise ActivationRefused("the retry and per-run call ceilings must be integers") from None
    if not 1 <= attempts <= 5 or not 1 <= per_run <= 500:
        raise ActivationRefused("retry ceiling must be 1..5 attempts per request and the run "
                                "ceiling 1..500 calls")
    expires = _aware(expires_at) if expires_at is not None else now + DEFAULT_EXPIRY
    if expires <= now or expires - now > MAX_EXPIRY:
        raise ActivationRefused(f"an activation expires after now and within "
                                f"{MAX_EXPIRY.days} days")
    ensure_tables(db)
    with db.session() as s:
        superseded = []
        for old in s.scalars(select(PaidProviderActivation).where(
                PaidProviderActivation.provider == provider,
                PaidProviderActivation.scope == scope,
                PaidProviderActivation.revoked_at.is_(None))):
            old.revoked_at, old.revoked_by = now, str(by)[:120]
            old.revoke_reason = "superseded by a new activation"
            superseded.append(old.id)
        row = PaidProviderActivation(
            provider=provider, scope=scope, activated_by=str(by)[:120], activated_at=now,
            step_up=evidence, daily_ceiling_cad=daily, monthly_ceiling_cad=monthly,
            per_gallery_cad=gallery, max_attempts_per_request=attempts,
            max_calls_per_run=per_run, expires_at=expires, note=str(note or "")[:300])
        s.add(row)
        s.flush()
        out = _view(row, now)
        s.add(AuditLog(actor=str(by)[:64], action=ACTION_ACTIVATED,
                       artifact=f"{provider}:{scope}",
                       detail={**out, "superseded": superseded}))
    return out


def revoke(db, *, provider: str, scope: str, by: str, session_public_id: str,
           reason: str = "", now: datetime | None = None) -> dict:
    """The owner turns a provider OFF for a scope. Takes effect before the next call."""
    from ..core.models import AuditLog

    now = _now(now)
    if not str(by or "").strip():
        raise ActivationRefused("a revocation names the owner who gave it")
    evidence = verify_step_up(db, session_public_id, now=now)
    ensure_tables(db)
    revoked = []
    with db.session() as s:
        for row in s.scalars(select(PaidProviderActivation).where(
                PaidProviderActivation.provider == provider,
                PaidProviderActivation.scope == scope,
                PaidProviderActivation.revoked_at.is_(None))):
            row.revoked_at, row.revoked_by = now, str(by)[:120]
            row.revoke_reason = str(reason or "revoked by the owner")[:300]
            revoked.append(row.id)
        s.add(AuditLog(actor=str(by)[:64], action=ACTION_REVOKED,
                       artifact=f"{provider}:{scope}",
                       detail={"provider": provider, "scope": scope, "revoked": revoked,
                               "reason": str(reason or "")[:300], "step_up": evidence,
                               "at": now.isoformat()}))
    return {"provider": provider, "scope": scope, "revoked": revoked, "at": now.isoformat()}


def _view(row: PaidProviderActivation, now: datetime) -> dict:
    exp = _aware(row.expires_at)
    status = ("revoked" if row.revoked_at is not None else
              "expired" if exp is not None and exp <= now else "active")
    return {"id": row.id, "provider": row.provider, "scope": row.scope, "status": status,
            "activated_by": row.activated_by,
            "activated_at": _aware(row.activated_at).isoformat() if row.activated_at else None,
            "step_up": dict(row.step_up or {}),
            "daily_ceiling_cad": row.daily_ceiling_cad,
            "monthly_ceiling_cad": row.monthly_ceiling_cad,
            "per_gallery_cad": row.per_gallery_cad,
            "max_attempts_per_request": row.max_attempts_per_request,
            "max_calls_per_run": row.max_calls_per_run,
            "expires_at": exp.isoformat() if exp else None,
            "revoked_at": _aware(row.revoked_at).isoformat() if row.revoked_at else None,
            "revoked_by": row.revoked_by, "revoke_reason": row.revoke_reason}


def _current(session, provider: str, scope: str, now: datetime) -> tuple[Any, str]:
    """(active row or None, reason). Reads the newest row for each covering scope."""
    reason = NOT_ACTIVATED
    for sc in _covering(scope):
        row = session.scalar(select(PaidProviderActivation).where(
            PaidProviderActivation.provider == provider, PaidProviderActivation.scope == sc)
            .order_by(PaidProviderActivation.id.desc()).limit(1))
        if row is None:
            continue
        if row.revoked_at is not None:
            reason = REVOKED if reason == NOT_ACTIVATED else reason
            continue
        exp = _aware(row.expires_at)
        if exp is None or exp <= now:
            reason = EXPIRED
            continue
        if not (row.step_up or {}).get("session_public_id"):
            continue                    # a row with no step-up evidence authorises nothing
        return row, ""
    return None, reason


def activation_state(db, provider: str, scope: str, *, now: datetime | None = None) -> dict:
    """{active, reason, activation} -- never raises; an unreadable store reads as OFF."""
    now = _now(now)
    if db is None:
        return {"active": False, "reason": "accounting_store_missing", "activation": None}
    try:
        ensure_tables(db)
        with db.session() as s:
            row, reason = _current(s, provider, scope, now)
            return {"active": row is not None, "reason": reason,
                    "activation": _view(row, now) if row is not None else None}
    except Exception as exc:  # noqa: BLE001 - unreadable approval evidence is OFF
        return {"active": False, "reason": "accounting_store_unreadable",
                "error": f"{type(exc).__name__}: {str(exc)[:160]}", "activation": None}


def require_active(db, provider: str, scope: str, *, now: datetime | None = None) -> dict:
    st = activation_state(db, provider, scope, now=now)
    if not st["active"]:
        raise PaidCallRefused(st["reason"], _explain(st["reason"], provider, scope))
    return st["activation"]


def is_active_id(db, activation_id, *, now: datetime | None = None) -> bool:
    """Whether a specific activation is still in force (not revoked, not expired)."""
    if db is None or activation_id is None:
        return False
    try:
        ensure_tables(db)
        with db.session() as s:
            row = s.get(PaidProviderActivation, int(activation_id))
            return (row is not None and row.revoked_at is None
                    and _aware(row.expires_at) is not None and _aware(row.expires_at) > _now(now)
                    and bool((row.step_up or {}).get("session_public_id")))
    except Exception:  # noqa: BLE001 - fail closed
        return False


def probe_activation_open(db, probe: dict | None, provider: str | None, scope: str) -> bool:
    """A capability gate's condition: the latest probe succeeded, was made under an activation
    that is still in force, and `scope` is currently activated for that provider."""
    if not probe or not probe.get("ok") or not provider:
        return False
    if not is_active_id(db, probe.get("activation_id")):
        return False
    return activation_state(db, provider, scope)["active"]


def _explain(code: str, provider: str, scope: str) -> str:
    return {
        NOT_ACTIVATED: f"{provider} is not activated by the owner for {scope}. "
                       f"{KEY_IS_NOT_ACTIVATION}",
        EXPIRED: f"the owner's activation of {provider} for {scope} has expired; nothing is "
                 f"sent until the owner activates it again",
        REVOKED: f"the owner revoked {provider} for {scope}; nothing is sent",
        "accounting_store_missing": "no accounting store, so neither the owner's approval nor "
                                    "the spend can be verified; refused (fail closed)",
        "accounting_store_unreadable": "the accounting store could not be read, so neither "
                                       "the owner's approval nor the spend can be verified; "
                                       "refused (fail closed)",
    }.get(code, code)


# ---- the enforcement point -----------------------------------------------------------------

def _run_key(now: datetime) -> str:
    from . import paid_calls

    jid = paid_calls.current_job_id()
    return f"job:{jid}" if jid is not None else f"day:{now.date().isoformat()}"


def _idem_key(provider: str, scope: str, fp: str, run_key: str) -> str:
    from . import paid_calls

    key = paid_calls.current_call_key()
    if key:
        return key[:64]       # in a job: the paid_calls key (job + request + occurrence)
    return hashlib.sha256(f"{provider}|{scope}|{fp}|{run_key}".encode()).hexdigest()


def _sum(session, *where) -> float:
    total = 0.0
    for row in session.scalars(select(PaidProviderCall).where(
            PaidProviderCall.status.in_(COUNTED), *where)):
        amount = row.actual_cad if row.status == BILLED and row.actual_cad is not None \
            else row.estimate_cad
        amount = float(amount or 0.0)
        if not math.isfinite(amount) or amount <= 0:
            amount = float(row.estimate_cad or 0.0)
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("paid attempt has no valid positive accounting estimate")
        total += amount
    return round(total, 6)


def uncovered_company_exposure(session, *, now: datetime | None = None) -> float:
    """Conservatively count paid attempts not covered by a live company reservation.

    This intentionally does not subtract booked costs: until reconciliation can bind
    an attempt to its exact ledger entry, double-counting is safer than losing a paid
    call. RESERVED/UNCERTAIN attempts survive month boundaries; BILLED attempts are
    included in their calendar month. Any malformed amount fails the budget closed.
    """
    from sqlalchemy import inspect
    from ..core.models import SpendReservation

    if not inspect(session.get_bind()).has_table(PaidProviderCall.__tablename__):
        return 0.0
    invalid = session.scalar(select(PaidProviderCall.id).where(
        (PaidProviderCall.status.is_(None)) |
        (~PaidProviderCall.status.in_((*COUNTED, RELEASED)))).limit(1))
    if invalid is not None:
        raise ValueError("paid attempt has unknown outcome; reconciliation required")
    now = _now(now)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = 0.0
    covered_ids = set()
    rows = session.scalars(select(PaidProviderCall).where(
        PaidProviderCall.status.in_(COUNTED)).order_by(PaidProviderCall.id))
    for row in rows:
        at = _aware(row.at)
        settled = _aware(row.settled_at)
        # A previous-month call can settle in this month; do not free its
        # headroom between settlement and the later ledger write.
        if (row.status == BILLED and at is not None and at < month_start
                and settled is not None and settled < month_start):
            continue
        estimate = float(row.estimate_cad or 0.0)
        if not math.isfinite(estimate) or estimate <= 0:
            raise ValueError("unresolved paid attempt has invalid estimate")
        actual = row.actual_cad if row.status == BILLED else None
        if actual is not None:
            actual = float(actual)
            if math.isfinite(actual) and actual > estimate:
                estimate = actual
        reservation = session.get(SpendReservation, row.reservation_id) if row.reservation_id else None
        live = (reservation is not None and reservation.id not in covered_ids
                and _aware(reservation.at) is not None and at is not None
                and _aware(reservation.at) <= at and reservation.released_at is None
                and _aware(reservation.expires_at) is not None
                and _aware(reservation.expires_at) > now)
        covered = 0.0
        if live:
            covered_ids.add(reservation.id)
            covered = float(reservation.amount_cad or 0.0)
            if not math.isfinite(covered) or covered < 0:
                raise ValueError("paid attempt has invalid company reservation")
        total += max(0.0, estimate - covered)
    return round(total, 6)


def _refuse(db, code: str, message: str, *, provider: str, scope: str, purpose: str,
            estimate: float, gallery: str = "") -> PaidCallRefused:
    """Record the refusal (best effort: an unreadable store cannot take a row) and return it."""
    try:
        if db is not None and code not in ("accounting_store_missing",
                                           "accounting_store_unreadable"):
            from ..core.models import AuditLog

            with db.session() as s:
                s.add(AuditLog(actor="gateway", action=ACTION_REFUSED,
                               artifact=f"{provider}:{scope}",
                               detail={"code": code, "why": message[:400], "purpose": purpose,
                                       "estimate_cad": estimate, "gallery": gallery}))
    except Exception:  # noqa: BLE001 - the refusal stands whether or not it was recorded
        pass
    return PaidCallRefused(code, message)


def authorize(db, *, provider: str, scope: str, estimate_cad: float, fingerprint: str,
              reservation_id: int | None, purpose: str = "", gallery: str | None = None,
              now: datetime | None = None) -> dict:
    """Every check, then a RESERVED row. Returns the ticket `confirm`/`settle` take.

    Raises `PaidCallRefused` with a named code; nothing is sent by this function."""
    now = _now(now)
    if db is None:
        raise _refuse(None, "accounting_store_missing",
                      _explain("accounting_store_missing", provider, scope),
                      provider=provider, scope=scope, purpose=purpose, estimate=0.0)
    if scope not in scopes_for(provider):
        raise _refuse(db, "unknown_paid_provider",
                      f"{provider!r} is not a paid provider this gate knows for {scope!r}",
                      provider=provider, scope=scope, purpose=purpose, estimate=0.0)
    try:
        estimate = float(estimate_cad)
    except (TypeError, ValueError):
        estimate = float("nan")
    if not math.isfinite(estimate) or estimate <= 0:
        raise _refuse(db, "invalid_estimate",
                      f"the estimate {estimate_cad!r} is not a finite positive amount",
                      provider=provider, scope=scope, purpose=purpose, estimate=0.0)
    gallery = (gallery or current_gallery())[:160]
    run_key = _run_key(now)
    fp = str(fingerprint or "")[:64]
    idem = _idem_key(provider, scope, fp, run_key)
    try:
        ensure_tables(db)
        from . import anthropic as gw
        from ..core.models import SpendReservation
        from ..finance import reservations

        with gw.budget_lock(db) as s:
            act, why = _current(s, provider, scope, now)
            if act is None:
                refusal = (why, _explain(why, provider, scope))
            else:
                refusal = None
                res = (s.get(SpendReservation, int(reservation_id))
                       if reservation_id is not None else None)
                res_exp = _aware(res.expires_at) if res is not None else None
                if res is None or res.released_at is not None or (
                        res_exp is not None and res_exp <= now):
                    refusal = ("no_budget_reservation",
                               f"no live company-budget reservation for this call (reservation "
                               f"{reservation_id!r}); the accounting evidence the month ceiling "
                               f"writes is missing, so the call is refused (fail closed)")
                elif (not math.isfinite(float(res.amount_cad or 0.0))
                      or float(res.amount_cad or 0.0) + 1e-9 < estimate):
                    refusal = ("reservation_underfunded",
                               "the company-budget reservation does not cover this call's estimate")
                elif s.scalar(select(PaidProviderCall.id).where(
                        PaidProviderCall.reservation_id == res.id).limit(1)) is not None:
                    # One reservation accounts for one attempt, even if that attempt was
                    # released: retrying must obtain a fresh company-budget decision.
                    refusal = ("reservation_already_used",
                               "the company-budget reservation already backed a paid attempt")
            if refusal is None:
                ceiling = gw.monthly_ceiling_cad()
                committed = round(gw.spent_this_month_cad(db, now=now)
                                  + reservations.outstanding(db, now=now)["cad"]
                                  + uncovered_company_exposure(s, now=now), 6)
                if not math.isfinite(ceiling) or ceiling <= 0 or committed > ceiling + 1e-9:
                    refusal = ("company_monthly_budget",
                               f"the company has CA${committed:.4f} billed or reserved this "
                               f"month, including this call, against a monthly ceiling of "
                               f"CA${ceiling:.2f}")
            if refusal is None:
                day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
                month0 = day0.replace(day=1)
                mine = PaidProviderCall.provider == provider
                today = _sum(s, mine, PaidProviderCall.at >= day0)
                month = _sum(s, mine, PaidProviderCall.at >= month0)
                in_gallery = _sum(s, PaidProviderCall.activation_id == act.id,
                                  PaidProviderCall.gallery == gallery)
                same = list(s.scalars(select(PaidProviderCall).where(
                    PaidProviderCall.provider == provider, PaidProviderCall.idem_key == idem)))
                in_run = len(list(s.scalars(select(PaidProviderCall.id).where(
                    PaidProviderCall.activation_id == act.id,
                    PaidProviderCall.run_key == run_key))))
                if today + estimate > act.daily_ceiling_cad + 1e-9:
                    refusal = ("provider_daily_ceiling",
                               f"{provider} has CA${today:.4f} reserved or billed today against "
                               f"the owner's CA${act.daily_ceiling_cad:.2f} daily ceiling; this "
                               f"call is CA${estimate:.4f}")
                elif month + estimate > act.monthly_ceiling_cad + 1e-9:
                    refusal = ("provider_monthly_ceiling",
                               f"{provider} has CA${month:.4f} reserved or billed this month "
                               f"against the owner's CA${act.monthly_ceiling_cad:.2f} monthly "
                               f"ceiling; this call is CA${estimate:.4f}")
                elif in_gallery + estimate > act.per_gallery_cad + 1e-9:
                    refusal = ("per_gallery_limit",
                               f"gallery {gallery!r} has CA${in_gallery:.4f} on {provider} "
                               f"against the owner's CA${act.per_gallery_cad:.2f} per-gallery "
                               f"limit; this call is CA${estimate:.4f}")
                elif any(r.status in COUNTED for r in same):
                    refusal = ("already_billed",
                               f"this identical {provider} request was already billed (or its "
                               f"outcome is unknown) in {run_key}; it is not bought again")
                elif len(same) >= int(act.max_attempts_per_request or 1):
                    refusal = ("retry_ceiling",
                               f"this {provider} request has been attempted {len(same)} time(s) "
                               f"in {run_key} against a retry ceiling of "
                               f"{act.max_attempts_per_request}")
                elif in_run >= int(act.max_calls_per_run or 1):
                    refusal = ("run_call_ceiling",
                               f"{in_run} {provider} call(s) already made in {run_key} against "
                               f"the activation's ceiling of {act.max_calls_per_run} per run")
            if refusal is None:
                row = PaidProviderCall(
                    activation_id=act.id, provider=provider, scope=scope, gallery=gallery,
                    run_key=run_key, idem_key=idem, fingerprint=fp,
                    purpose=str(purpose or "")[:80], estimate_cad=round(estimate, 6),
                    status=RESERVED, reservation_id=reservation_id, at=now)
                s.add(row)
                s.flush()
                ticket = {"call_id": row.id, "activation_id": act.id, "provider": provider,
                          "scope": scope, "gallery": gallery, "estimate_cad": estimate}
    except PaidCallRefused:
        raise
    except Exception as exc:  # noqa: BLE001 - unreadable evidence: refused, fail closed
        raise _refuse(None, "accounting_store_unreadable",
                      f"{_explain('accounting_store_unreadable', provider, scope)} "
                      f"({type(exc).__name__}: {str(exc)[:160]})",
                      provider=provider, scope=scope, purpose=purpose,
                      estimate=estimate) from None
    if refusal is not None:
        raise _refuse(db, refusal[0], refusal[1], provider=provider, scope=scope,
                      purpose=purpose, estimate=estimate, gallery=gallery)
    return ticket


def confirm(db, ticket: dict, *, now: datetime | None = None) -> None:
    """Re-read the activation immediately before the network I/O. A revocation or expiry that
    landed after `authorize` refuses here, and the reservation is released unbilled."""
    if is_active_id(db, ticket.get("activation_id"), now=now):
        return
    settle(db, ticket, RELEASED, error="activation no longer in force at send time")
    raise _refuse(db, REVOKED, f"the owner's activation of {ticket.get('provider')} ended "
                               f"between the reservation and the call; nothing was sent",
                  provider=str(ticket.get("provider")), scope=str(ticket.get("scope")),
                  purpose="", estimate=float(ticket.get("estimate_cad") or 0.0))


def settle(db, ticket: dict, status: str, *, actual_cad: float | None = None,
           error: str = "") -> None:
    """BILLED / RELEASED / UNCERTAIN. Never raises: a row left RESERVED stays counted."""
    try:
        # An unknown outcome is not evidence that a paid call is free.  In
        # particular, arbitrary status strings are outside COUNTED and would
        # otherwise silently release the budget exposure.
        if status not in (BILLED, RELEASED, UNCERTAIN):
            status = UNCERTAIN
            error = "invalid provider outcome; counted at the reserved estimate"
        # Settlement changes the same exposure used by check-and-reserve, so
        # serialize it with that decision (including across processes).
        from . import anthropic as gw
        with gw.budget_lock(db) as s:
            row = s.get(PaidProviderCall, int(ticket["call_id"]))
            if row is None:
                return
            if row.status != RESERVED:
                # Contradictory final reports are not evidence of a free call.
                # Keep the greatest known positive exposure while escalating
                # the attempt to UNCERTAIN, regardless of report order.
                conflicting = status != row.status
                if status == row.status == BILLED and actual_cad is not None:
                    try:
                        repeat_actual = float(actual_cad)
                        existing_actual = float(row.actual_cad)
                        conflicting = (not math.isfinite(repeat_actual) or repeat_actual <= 0
                                       or not math.isfinite(existing_actual)
                                       or repeat_actual != existing_actual)
                    except (TypeError, ValueError, OverflowError):
                        conflicting = True
                if row.status in (RELEASED, BILLED, UNCERTAIN) and conflicting:
                    amounts = [row.estimate_cad, row.actual_cad]
                    if status == BILLED:
                        amounts.append(actual_cad)
                    valid = []
                    for amount in amounts:
                        try:
                            value = float(amount)
                        except (TypeError, ValueError, OverflowError):
                            continue
                        if math.isfinite(value) and value > 0:
                            valid.append(value)
                    if not valid:
                        return  # invalid original evidence stays fail-closed
                    row.estimate_cad = max(valid)
                    row.status = UNCERTAIN
                    row.error = "conflicting provider outcomes; reconciliation required"
                    row.settled_at = utcnow()
                return
            if status == BILLED:
                # Missing/zero usage is not proof a provider call was free. Invalid
                # usage must never become a negative credit against the owner's cap.
                try:
                    value = float(actual_cad) if actual_cad is not None else None
                except (TypeError, ValueError, OverflowError):
                    value = float("nan")
                if value is not None and (not math.isfinite(value) or value < 0):
                    status = UNCERTAIN
                    error = "invalid provider usage; counted at the reserved estimate"
                else:
                    row.actual_cad = round(value if value and value > 0
                                           else float(row.estimate_cad), 6)
            row.status = status
            row.error = str(error or "")[:300]
            row.settled_at = utcnow()
    except Exception:  # noqa: BLE001 - unsettled means still counted, the safe direction
        pass


def enforce(db, *, provider: str, scope: str, estimate_cad: float, fingerprint: str,
            reservation_id: int | None, call: Callable[[], Any],
            classify: Callable[[BaseException], str],
            actual: Callable[[Any], float | None] | None = None, purpose: str = "",
            gallery: str | None = None):
    """authorize -> confirm -> call -> settle. `classify(exc)` returns BILLED, RELEASED or
    UNCERTAIN for a failed call; `actual(result)` the settled CA$ (default: the estimate)."""
    ticket = authorize(db, provider=provider, scope=scope, estimate_cad=estimate_cad,
                       fingerprint=fingerprint, reservation_id=reservation_id,
                       purpose=purpose, gallery=gallery)
    confirm(db, ticket)
    try:
        result = call()
    except BaseException as exc:
        try:
            status = classify(exc) if isinstance(exc, Exception) else UNCERTAIN
        except Exception:  # noqa: BLE001
            status = UNCERTAIN
        settle(db, ticket, status if status in (BILLED, RELEASED, UNCERTAIN) else UNCERTAIN,
               error=f"{type(exc).__name__}: {exc}")
        raise
    amount = None
    if actual is not None:
        try:
            amount = actual(result)
        except Exception:  # noqa: BLE001 - unknown actual is the estimate, never zero
            amount = None
    settle(db, ticket, BILLED, actual_cad=amount)
    return result


# ---- the owner's view -----------------------------------------------------------------------

def owner_view(db, *, now: datetime | None = None) -> dict:
    """Every paid provider, its activation state and this month's gated spend. Names only;
    never a credential value."""
    now = _now(now)
    out: dict = {"key_is_not_activation": KEY_IS_NOT_ACTIVATION, "providers": []}
    try:
        from . import images

        keyed = set(images.available())
    except Exception:  # noqa: BLE001
        keyed = set()
    for provider in image_providers() + list(VISION_PROVIDERS):
        for scope in scopes_for(provider):
            st = activation_state(db, provider, scope, now=now)
            out["providers"].append({
                "provider": provider, "family": family(provider), "scope": scope,
                "key_present": provider in keyed if family(provider) == "image" else None,
                "active": st["active"], "state": "active" if st["active"] else st["reason"],
                "activation": st["activation"]})
    try:
        ensure_tables(db)
        month0 = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with db.session() as s:
            out["month_gated_cad"] = {
                p: _sum(s, PaidProviderCall.provider == p, PaidProviderCall.at >= month0)
                for p in image_providers() + list(VISION_PROVIDERS)}
    except Exception as exc:  # noqa: BLE001
        out["month_gated_cad"] = f"UNKNOWN ({type(exc).__name__})"
    return out


def gate_card(db, gate: str) -> dict:
    """What the owner queue shows for `image_generation` / `image_vision`."""
    fam = "image" if gate == "image_generation" else "vision"
    scope = GENERATION if fam == "image" else VISION
    view = owner_view(db)
    rows = [r for r in view["providers"] if r["family"] == fam and r["scope"] == scope]
    active = [r["provider"] for r in rows if r["active"]]
    keyed = [r["provider"] for r in rows if r.get("key_present")]
    return {"key_is_not_activation": KEY_IS_NOT_ACTIVATION,
            "activated_providers": active,
            "providers_with_key_but_not_activated": [p for p in keyed if p not in active],
            "activation_state": {r["provider"]: r["state"] for r in rows},
            "how": ("Command Center: POST /api/cc/paid-providers/activate with provider, "
                    f"scope={scope!r}, daily_ceiling_cad, monthly_ceiling_cad, "
                    "per_gallery_cad and expires_at, after a step-up")}


def generation_gate_reason(db) -> str:
    """Why `image_generation` reads closed, as a named reason (for refusals and the queue)."""
    active = [p for p in image_providers()
              if activation_state(db, p, GENERATION)["active"]]
    if not active:
        return f"{NOT_ACTIVATED}: {KEY_IS_NOT_ACTIVATION}"
    return (f"no_probe_under_activation: {', '.join(active)} activated, but no probe has yet "
            f"succeeded under an activation still in force")
