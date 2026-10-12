"""Write-ahead effect intents: the general form of `publish.draft_intent` (audit ddf9c6e L-1).

Execution semantics, stated plainly
-----------------------------------
The queue is AT-LEAST-ONCE. A worker that is SIGKILLed, or that stalls past its lease, has its
job reclaimed and the handler runs again from the top. The lease-token fence makes the *DB
completion* exactly-once; it cannot un-send an HTTP request the first run already made.

So a handler that performs an EXTERNAL effect (a remote create/mutate, a message, a payment,
an upload whose duplicate costs or confuses) must make that effect at-most-once itself:

    with effects.guard(ctx, "etsy.activate", f"{listing_id}:{approval}") as intent:
        remote = client.activate(...)          # the one external call
        intent.applied(f"etsy_listing:{listing_id}")

`guard` (1) re-checks this worker still holds the job's lease (`assert_lease`), so a stale
worker stops *before* the effect rather than only having its completion refused afterwards;
(2) durably claims a unique intent row keyed on (effect, idempotency key) BEFORE the call;
(3) marks it APPLIED on success, RELEASED when the call provably never left the process
(`EffectNotSent`), and UNCERTAIN on any other exception. A second attempt for the same key --
a reclaimed re-run, a retry, a duplicate job -- finds the row and is refused with a
reconciliation incident (or, when the first attempt is APPLIED, told so via
`EffectAlreadyApplied` carrying the recorded result). An unknown outcome is never retried
automatically. That is at-most-once *automatic* attempts per key, not exactly-once remote
execution: an UNCERTAIN row needs a human or a reconciler to read the remote state.

Every refused duplicate increments `duplicate_attempts` and writes an `effect.duplicate_refused`
audit row, which is what the soak criterion "no duplicated external effect" reads
(ops.slo.soak_report) together with reclaim records and cost entries.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import AuditLog, Incident, utcnow
from ..core.resilience import PermanentError, TransientError

CLAIMED, APPLIED, UNCERTAIN, RELEASED = "CLAIMED", "APPLIED", "UNCERTAIN", "RELEASED"


class EffectIntent(Base):
    __tablename__ = "effect_intents"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    effect: Mapped[str] = mapped_column(String(80), index=True)
    idem: Mapped[str] = mapped_column(String(300))
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(80), default="")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    worker: Mapped[str] = mapped_column(String(64), default="")
    token: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24), default=CLAIMED, index=True)
    duplicate_attempts: Mapped[int] = mapped_column(Integer, default=0)
    result_ref: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Every handler that performs an external effect today, and how it is made at-most-once.
# `ops.slo.soak_report` treats these job types as external-effect types: a reclaimed re-run of
# one with no intent row is a possible duplicate and FAILS the criterion.
EFFECT_INVENTORY: dict[str, dict] = {
    "store.publish": {
        "effects": ["Etsy createDraftListing", "Etsy uploadListingImage/File"],
        "guard": "publish.draft_intent (unique per product/version, write-ahead; uploads "
                 "checkpoint the recorded remote id)",
        "semantics": "at-most-one automatic create attempt"},
    "store.activate": {
        "effects": ["Etsy updateListing state=active (listing fee)"],
        "guard": "queue.effects.guard('etsy.activate', '<listing_id>:<approval_id>')",
        "semantics": "at-most-one automatic activation attempt per listing+approval"},
}
EXTERNAL_EFFECT_JOB_TYPES: frozenset[str] = frozenset(EFFECT_INVENTORY)
# Job types whose handlers were read and perform only keyed/idempotent DB writes (no
# network, no spend). A reclaimed re-run of these is a repeated computation, not a repeated
# external effect. Anything not listed here or in the inventory is NOT assumed safe.
EFFECT_FREE_JOB_TYPES: frozenset[str] = frozenset({
    "autonomy.orchestrate", "autonomy.department_review", "autonomy.morning_handoff",
    "ops.heartbeat",
})
# Effects that are NOT made at-most-once here, said so rather than implied:
AT_LEAST_ONCE_EFFECTS: dict[str, str] = {
    "paid model/API calls (gateway.*)":
        "metered per call in cost_entries (job_id) and bounded by the per-agent daily "
        "ceiling and the reservation in agents.registry; a reclaimed re-run can pay twice. "
        "The soak reads cost_entries on reclaimed jobs and FAILS on any.",
    "teardown.intake.mirror (offsite.put)":
        "content-addressed object key (sha256 prefix), so a repeat PUT overwrites the same "
        "object with the same bytes; not invoked by any scheduled handler today.",
}


class EffectRefused(PermanentError):
    """A second automatic attempt at a keyed external effect. Never retried."""


class EffectAlreadyApplied(EffectRefused):
    def __init__(self, msg: str, result_ref: str = ""):
        super().__init__(msg)
        self.result_ref = result_ref


class EffectNotSent(Exception):
    """Raise (or wrap) inside a guard when the external call provably never left this
    process (validation before send, refused by a local gate). The intent is released, so a
    later attempt may run. Anything else leaves it UNCERTAIN."""


class LeaseLost(TransientError):
    """This worker no longer holds the job's lease; it must not perform the effect.

    Transient: if the lease was reclaimed, this attempt's failure write is fenced off anyway;
    if it merely lapsed with nobody else holding it, a later attempt may run."""


_LOCK = threading.Lock()
_FLAG = "_brambleloop_effect_intents"


def ensure_table(db) -> None:
    engine = db.engine
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[EffectIntent.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)


def key_for(effect: str, idem: str) -> str:
    return hashlib.sha256(json.dumps([effect, idem], separators=(",", ":"))
                          .encode()).hexdigest()


def _incident(db, effect: str, idem: str, key: str, why: str) -> None:
    sig = f"effect.reconcile:{key[:40]}"
    with db.session() as s:
        if s.scalar(select(Incident.id).where(Incident.signature == sig,
                                              Incident.resolved.is_(False))) is None:
            s.add(Incident(severity="P1", signature=sig,
                           summary=f"external effect {effect} needs reconciliation; "
                                   f"automatic repeat refused",
                           detail={"effect": effect, "idem": idem[:200], "reason": why}))


def claim(db, effect: str, idem: str, *, job=None, worker: str = "") -> tuple[str, str]:
    """Durably claim (effect, idem) before the call. Returns (key, token).

    Raises EffectAlreadyApplied when the effect was already applied, EffectRefused when an
    earlier attempt's outcome is CLAIMED/UNCERTAIN (unknown: reconcile, never re-send)."""
    ensure_table(db)
    key, token = key_for(effect, idem), uuid.uuid4().hex
    job_id = getattr(job, "id", None)
    try:
        with db.session() as s:
            s.add(EffectIntent(key=key, effect=effect[:80], idem=idem[:300], job_id=job_id,
                               job_type=(getattr(job, "job_type", "") or "")[:80],
                               attempt=int(getattr(job, "attempts", 0) or 0),
                               worker=(worker or getattr(job, "leased_by", "") or "")[:64],
                               token=token, state=CLAIMED, detail={}))
        return key, token
    except IntegrityError:
        pass
    with db.session() as s:
        row = s.get(EffectIntent, key)
        if row is not None and row.state == RELEASED:
            # The earlier attempt provably never sent: this attempt takes the key over.
            row.token, row.state, row.job_id = token, CLAIMED, job_id
            row.attempt = int(getattr(job, "attempts", 0) or 0)
            row.updated_at = utcnow()
            return key, token
        state = row.state if row is not None else "UNKNOWN"
        ref = row.result_ref if row is not None else ""
        if row is not None:
            row.duplicate_attempts = (row.duplicate_attempts or 0) + 1
            row.updated_at = utcnow()
        s.add(AuditLog(actor=(worker or "worker")[:64], action="effect.duplicate_refused",
                       artifact=f"{effect}:{idem}"[:200], job_id=job_id,
                       detail={"key": key, "state": state}))
    if state == APPLIED:
        raise EffectAlreadyApplied(
            f"EFFECT_ALREADY_APPLIED: {effect} for {idem!r} was applied ({ref}); "
            f"not repeated", ref)
    _incident(db, effect, idem, key, f"an earlier attempt is {state}")
    raise EffectRefused(f"EFFECT_RECONCILIATION: {effect} for {idem!r} has an earlier "
                        f"attempt in state {state}; outcome unknown, never blindly repeated")


def _set(db, key: str, token: str, state: str, **kw) -> bool:
    with db.session() as s:
        row = s.get(EffectIntent, key)
        if row is None or row.token != token:
            return False
        row.state = state
        row.updated_at = utcnow()
        for k, v in kw.items():
            setattr(row, k, v)
    return True


def mark_applied(db, key: str, token: str, result_ref: str = "") -> bool:
    return _set(db, key, token, APPLIED, result_ref=(result_ref or "")[:200])


def mark_uncertain(db, key: str, token: str, why: str = "") -> bool:
    return _set(db, key, token, UNCERTAIN, detail={"why": why[:300],
                                                   "automatic_retry": False})


def release_unsent(db, key: str, token: str) -> bool:
    with db.session() as s:
        row = s.get(EffectIntent, key)
        if row is None or row.token != token or row.state != CLAIMED:
            return False
        row.state, row.updated_at = RELEASED, utcnow()
    return True


class _Intent:
    def __init__(self, db, key, token):
        self.db, self.key, self.token = db, key, token
        self.result_ref = ""
        self._applied = False

    def applied(self, result_ref: str = "") -> None:
        self.result_ref = result_ref
        self._applied = mark_applied(self.db, self.key, self.token, result_ref)


@contextmanager
def guard(ctx, effect: str, idem: str):
    """Lease check + write-ahead intent around ONE external effect (see module docstring)."""
    assert_lease = getattr(ctx, "assert_lease", None)
    if callable(assert_lease):
        assert_lease()
    key, token = claim(ctx.db, effect, idem, job=ctx.job,
                       worker=getattr(ctx.job, "leased_by", "") or "")
    intent = _Intent(ctx.db, key, token)
    try:
        yield intent
    except EffectNotSent:
        release_unsent(ctx.db, key, token)
        raise
    except BaseException as exc:
        mark_uncertain(ctx.db, key, token, f"{type(exc).__name__}: {exc}")
        _incident(ctx.db, effect, idem, key, f"interrupted: {type(exc).__name__}")
        raise
    if not intent._applied:
        mark_applied(ctx.db, key, token, intent.result_ref)


def rows(db, *, since: datetime | None = None) -> list[dict]:
    """Effect intent rows (for the soak report and the command center)."""
    ensure_table(db)
    with db.session() as s:
        q = select(EffectIntent)
        if since is not None:
            q = q.where(EffectIntent.updated_at >= since)
        return [{"key": r.key, "effect": r.effect, "idem": r.idem, "job_id": r.job_id,
                 "job_type": r.job_type, "state": r.state,
                 "duplicate_attempts": r.duplicate_attempts, "result_ref": r.result_ref}
                for r in s.scalars(q)]
