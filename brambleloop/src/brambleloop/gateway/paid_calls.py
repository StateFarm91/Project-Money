"""Write-ahead paid-call intents: a reclaimed or retried job never pays twice (F-307, F-339).

The queue is AT-LEAST-ONCE (`queue.effects` says so plainly): a worker that is SIGKILLed or
stalls past its lease has its job reclaimed and the handler runs again from the top. Until
this module, a paid model or image call was the one external effect with no write-ahead
record, so the re-run paid the provider again for the same question (`queue.effects.
AT_LEAST_ONCE_EFFECTS` listed it; the soak FAILED on it). This closes that hole at the one
place every paid call actually leaves the process -- the transport
(`AnthropicProvider.complete`/`see`, `images.generate`) -- so no caller has to remember.

How a paid call inside a job runs
---------------------------------
The worker opens `spend_report.attributed_to(job_product(db, job))` around every handler;
that now also opens a *job scope* here (the job is carried on the slug, see
`spend_report.job_product`). Inside a scope each paid call is keyed by

    (effect, "job:<id>", sha256(request), occurrence of that request in this attempt)

-- job and request identity, NOT the attempt number, so attempt 2 of the same job asking the
same question in the same order lands on the same key as attempt 1. Then:

1. a `paid_call_records` row is written PENDING with the estimate and the reservation the
   ceiling check took (`anthropic.check_budget_cad` notes it into the scope);
2. `queue.effects.claim` durably claims the key (lease re-checked first, so a stale worker
   stops before it pays rather than only having its completion refused afterwards);
3. the provider is called once;
4. the outcome is written: OK with the response (so it can be served again), DECLINED (the
   provider refused before doing any work -- HTTP 4xx/5xx/429, unreachable: never billed,
   the intent is released and a later attempt may ask), FAILED_BILLED (the provider took
   the work and then it failed -- billed, not repeated) or UNCERTAIN (a timeout or an
   unreadable answer: whether it billed is unknown, so it is not repeated automatically).

A later attempt reaching the same key:

* OK -> the stored answer is **replayed** with zero tokens and `replayed=True`; nothing is
  sent and nothing new is billed (`ModelGateway._billing` and `spend_report.record` read the
  replay and label the row `replayed_not_billed`). The answer is the one already paid for.
* DECLINED -> asked again (it never billed).
* FAILED_BILLED -> `PaidCallReplayedFailure` (a PermanentError): the failure is replayed,
  the work is not re-bought.
* UNCERTAIN -> `PaidCallUnresolved` (PermanentError) and a P1 reconciliation incident.
* PENDING (the worker died *during* the call) -> F-339 "no blind restart": the prior call's
  authoritative state is unknown, so it is not re-sent. Its spend, which no ledger row
  recorded and whose reservation would simply expire, is counted ONCE at the reservation's
  estimate through the single ledger writer (`spend_report.record`, billing
  `in_flight_when_worker_lost_counted_at_estimate`) -- UNKNOWN is never zero -- and the
  attempt raises `PaidCallUnresolved` with the incident open.

The explicit way past an unresolved call is the one F-307 names: a new job (a new
evidence/version key), never an automatic resend.

Outside a job scope (a probe run from a shell, a test calling a provider directly) nothing
changes: there is no job to be re-run, so there is nothing to make idempotent.

Spend recording stays single-path: this module never prices a call it made. The only ledger
row it writes is the in-flight orphan above, through `spend_report.record`. Each billed row
carries `paid_call_key` in its detail (`ledger_note`), so reservation -> intent -> cost row is
one chain a reader can follow, and the soak can tell "paid once on a reclaimed job" from
"paid twice".

Known limits, stated rather than implied: a handler whose prompt changes between attempts
(a timestamp in the text, a random seed) makes a different request and is not replayed --
that is a different question, by construction; threads a handler starts do not inherit the
scope (context variables are per thread), so their calls run unguarded exactly as before; a
stale worker that finishes a call after its successor already counted it as an in-flight
orphan double-counts that one call in the conservative direction.
"""
from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import AuditLog, Incident, utcnow
from ..core.resilience import PermanentError

PENDING, OK, DECLINED, FAILED_BILLED, UNCERTAIN = (
    "PENDING", "OK", "DECLINED", "FAILED_BILLED", "UNCERTAIN")
REPLAY_ACTION = "paid_call.replayed"
ORPHAN_BILLING = "in_flight_when_worker_lost_counted_at_estimate"
REPLAY_BILLING = "replayed_not_billed"


class PaidCallRecord(Base):
    __tablename__ = "paid_call_records"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    effect: Mapped[str] = mapped_column(String(80), index=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(80), default="")
    fingerprint: Mapped[str] = mapped_column(String(64))
    occurrence: Mapped[int] = mapped_column(Integer, default=0)
    first_attempt: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(16), default=PENDING, index=True)
    intent_token: Mapped[str] = mapped_column(String(64), default="")
    estimate_cad: Mapped[float] = mapped_column(Float, default=0.0)
    reservation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_kind: Mapped[str] = mapped_column(String(20), default="")
    provider: Mapped[str] = mapped_column(String(40), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    agent: Mapped[str] = mapped_column(String(64), default="")
    replays: Mapped[int] = mapped_column(Integer, default=0)
    orphan_billed: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(300), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaidCallUnresolved(PermanentError):
    """An earlier attempt's paid call has no known outcome; it is never blindly re-sent."""


class PaidCallReplayedFailure(PermanentError):
    """An earlier attempt paid for this call and it failed; the failure is replayed, the
    work is not bought again."""


# ---------------------------------------------------------------------------
# The job scope


@dataclass
class JobRef:
    """What the guard needs from a job, copied so a detached ORM row is never touched."""

    id: int | None
    job_type: str = ""
    agent: str = ""
    attempts: int = 0
    lease_token: str | None = None
    leased_by: str = ""

    @classmethod
    def of(cls, job) -> "JobRef | None":
        if job is None or getattr(job, "id", None) is None:
            return None
        return cls(id=int(job.id), job_type=str(getattr(job, "job_type", "") or ""),
                   agent=str(getattr(job, "agent", "") or ""),
                   attempts=int(getattr(job, "attempts", 0) or 0),
                   lease_token=getattr(job, "lease_token", None),
                   leased_by=str(getattr(job, "leased_by", "") or ""))


@dataclass
class _Scope:
    db: Any
    job: JobRef
    counts: dict = field(default_factory=dict)
    reservation: dict | None = None
    last_call: dict | None = None
    unresolved: set = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def occurrence(self, fp: str) -> int:
        with self.lock:
            n = self.counts.get(fp, 0)
            self.counts[fp] = n + 1
            return n


_SCOPE: ContextVar[_Scope | None] = ContextVar("brambleloop_paid_call_scope", default=None)


@contextmanager
def job_scope(db, job):
    """Guard every paid call inside this block against re-execution of `job`."""
    ref = JobRef.of(job)
    if db is None or ref is None:
        yield None
        return
    token = _SCOPE.set(_Scope(db=db, job=ref))
    try:
        yield _SCOPE.get()
    finally:
        _SCOPE.reset(token)


def current_job_id() -> int | None:
    scope = _SCOPE.get()
    return scope.job.id if scope is not None else None


def note_reservation(budget: dict | None) -> None:
    """Called by `anthropic.check_budget_cad` with the reservation it took, so the next paid
    call in this scope knows the estimate it was allowed on (for the orphan rule)."""
    scope = _SCOPE.get()
    if scope is not None and budget:
        scope.reservation = {"estimate_cad": float(budget.get("estimate_cad") or 0.0),
                             "reservation_id": budget.get("reservation_id")}


def ledger_note() -> dict:
    """Detail fields for the cost row the caller writes after a guarded call (consumed once).

    `{"paid_call_key": ..., "billing": "replayed_not_billed"}` for a replay; the key alone
    for a live call; `{}` outside a scope or when no guarded call preceded the write."""
    scope = _SCOPE.get()
    if scope is None or not scope.last_call:
        return {}
    note, scope.last_call = dict(scope.last_call), None
    return note


def peek_replayed() -> bool:
    scope = _SCOPE.get()
    return bool(scope and scope.last_call and scope.last_call.get("replayed"))


# ---------------------------------------------------------------------------
# Storage

_LOCK = threading.Lock()
_FLAG = "_brambleloop_paid_call_records"


def ensure_table(db) -> None:
    engine = db.engine
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[PaidCallRecord.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)


def fingerprint(*parts) -> str:
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _update(db, key: str, **kw) -> None:
    with db.session() as s:
        row = s.get(PaidCallRecord, key)
        if row is None:
            return
        for k, v in kw.items():
            setattr(row, k, v)
        row.updated_at = utcnow()


def _assert_lease(db, job: JobRef) -> None:
    """The `JobContext.assert_lease` rule, read from the job row (the scope has no ctx)."""
    if not job.lease_token or job.id is None:
        return
    from ..core.models import Job, JobStatus
    from ..queue.effects import LeaseLost

    with db.session() as s:
        row = s.execute(select(Job.status, Job.lease_token, Job.lease_expires_at)
                        .where(Job.id == job.id)).first()
    if row is None or row.status != JobStatus.RUNNING or row.lease_token != job.lease_token:
        raise LeaseLost(f"job {job.id}: lease no longer held by this attempt; paid call "
                        f"not made")
    exp = row.lease_expires_at
    if exp is not None:
        exp = exp if exp.tzinfo else exp.replace(tzinfo=utcnow().tzinfo)
        if exp <= utcnow():
            raise LeaseLost(f"job {job.id}: lease expired at {exp.isoformat()}; paid call "
                            f"not made")


def _incident(db, key: str, effect: str, job_id, why: str) -> None:
    sig = f"paid_call.unresolved:{key[:40]}"
    with db.session() as s:
        if s.scalar(select(Incident.id).where(Incident.signature == sig,
                                              Incident.resolved.is_(False))) is None:
            s.add(Incident(severity="P1", signature=sig,
                           summary=f"paid call {effect} on job {job_id} has no known "
                                   f"outcome; not re-sent automatically (F-339)",
                           detail={"key": key, "effect": effect, "job_id": job_id,
                                   "reason": why[:300]}))


def _count_orphan(db, row: PaidCallRecord) -> None:
    """Count a call that was in flight when its worker died, once, at its estimate."""
    if row.orphan_billed:
        return
    from ..finance import spend_report

    estimate = round(float(row.estimate_cad or 0.0), 8)
    spend_report.record(
        db, agent=row.agent or "gateway", amount_cad=estimate, estimated_cad=estimate,
        purpose=row.effect[:60], provider=row.provider, model=row.model,
        job_id=row.job_id, kind=row.cost_kind or "llm", department="gateway",
        detail={"billing": ORPHAN_BILLING, "paid_call_key": row.key,
                "price_basis": "assumed",
                "cost_basis_note": "the worker died while this call was in flight; whether "
                                   "the provider billed is UNKNOWN and counted at the "
                                   "reservation estimate, never as zero",
                "reservation_id": row.reservation_id})
    if row.reservation_id is not None:
        from . import anthropic as gw

        gw.release_reservation(db, row.reservation_id, actual_cad=estimate)
    _update(db, row.key, orphan_billed=True, outcome=UNCERTAIN,
            error="worker lost during the call")


# ---------------------------------------------------------------------------
# The guard


def guarded(effect: str, fp: str, call: Callable[[], Any], *,
            encode: Callable[[Any], dict], decode: Callable[[dict], Any],
            classify: Callable[[BaseException], str],
            cost_kind: str = "llm", provider: str = "", model: str = "", agent: str = "",
            estimate_cad: float | None = None, reservation_id: int | None = None):
    """Run `call` at most once per (job, request, occurrence). See the module docstring.

    `classify(exc)` returns DECLINED, FAILED_BILLED or UNCERTAIN for a failed call."""
    scope = _SCOPE.get()
    if scope is None:
        return call()
    from ..queue import effects

    db, job = scope.db, scope.job
    ensure_table(db)
    n = scope.occurrence(fp)
    idem = f"job:{job.id}:{fp[:40]}:{n}"
    key = effects.key_for(effect, idem)
    held, scope.reservation = scope.reservation or {}, None   # consumed by this call
    estimate_cad = held.get("estimate_cad", 0.0) if estimate_cad is None else estimate_cad
    reservation_id = held.get("reservation_id") if reservation_id is None else reservation_id

    with db.session() as s:
        row = s.get(PaidCallRecord, key)
        if row is not None:
            s.expunge(row)
    if row is not None and row.outcome != DECLINED:
        return _replay(scope, row, effect, idem, fp, decode)
    if fp in scope.unresolved:
        raise PaidCallUnresolved(f"{effect}: an earlier occurrence of this request on job "
                                 f"{job.id} has no known outcome; later ones are not sent")

    # Write-ahead: the record and the intent exist before the provider is asked.
    _assert_lease(db, job)
    fresh = dict(effect=effect[:80], job_id=job.id, job_type=job.job_type[:80],
                 fingerprint=fp, occurrence=n, first_attempt=job.attempts,
                 outcome=PENDING, estimate_cad=float(estimate_cad or 0.0),
                 reservation_id=reservation_id, cost_kind=cost_kind[:20],
                 provider=provider[:40], model=str(model or "")[:80],
                 agent=(agent or job.agent or "")[:64], payload={}, error="")
    try:
        with db.session() as s:
            if row is None:
                s.add(PaidCallRecord(key=key, **fresh))
            else:                                      # DECLINED before: asked again
                live = s.get(PaidCallRecord, key)
                for k, v in fresh.items():
                    if k not in ("first_attempt", "occurrence"):
                        setattr(live, k, v)
                live.updated_at = utcnow()
    except IntegrityError:
        with db.session() as s:
            row = s.get(PaidCallRecord, key)
            s.expunge(row)
        return _replay(scope, row, effect, idem, fp, decode)
    _key, token = effects.claim(db, effect, idem, job=job, worker=job.leased_by)
    _update(db, key, intent_token=token)
    # Set before the call: an image render bills inside it (`images.record_render`), a model
    # call is billed by its caller after it returns; either way the row carries this key.
    scope.last_call = {"paid_call_key": key}
    try:
        result = call()
    except BaseException as exc:
        kind = classify(exc) if isinstance(exc, Exception) else UNCERTAIN
        why = f"{type(exc).__name__}: {exc}"[:300]
        if kind == DECLINED:
            _update(db, key, outcome=DECLINED, error=why)
            effects.release_unsent(db, key, token)
        else:
            _update(db, key, outcome=kind, error=why)
            effects.mark_uncertain(db, key, token, why)
            if kind == UNCERTAIN:
                _incident(db, key, effect, job.id, why)
        raise
    _update(db, key, outcome=OK, payload=encode(result))
    effects.mark_applied(db, key, token, f"paid_call:{key[:16]}")
    return result


def _replay(scope: _Scope, row: PaidCallRecord, effect: str, idem: str, fp: str,
            decode: Callable[[dict], Any]):
    from ..queue import effects

    db, job = scope.db, scope.job
    if row.outcome == OK and row.intent_token:
        # The answer was stored and the process died before the intent was closed: close
        # it now (token-fenced), so the replay below reads as APPLIED, not as unknown.
        effects.mark_applied(db, row.key, row.intent_token, f"paid_call:{row.key[:16]}")
    # Counted as a duplicate attempt the guard refused (`effect.duplicate_refused`), which is
    # what the soak's "no duplicated external effect" reads. The refusal is the point.
    try:
        _k, token = effects.claim(db, effect, idem, job=job, worker=job.leased_by)
    except effects.EffectRefused:
        token = None
    else:
        # No intent existed (the record was written, the claim never was): nothing was
        # sent under this key, and the fresh claim is closed rather than left CLAIMED.
        if row.outcome == OK:
            effects.mark_applied(db, row.key, token, "paid_call:replay")
        else:
            effects.mark_uncertain(db, row.key, token, "record without intent")
    with db.session() as s:
        live = s.get(PaidCallRecord, row.key)
        live.replays = (live.replays or 0) + 1
        live.updated_at = utcnow()
        s.add(AuditLog(actor=(job.leased_by or "worker")[:64], action=REPLAY_ACTION,
                       artifact=f"{effect}:{row.key[:16]}"[:200], job_id=job.id,
                       detail={"key": row.key, "outcome": row.outcome,
                               "first_attempt": row.first_attempt,
                               "this_attempt": job.attempts}))
    if row.outcome == OK:
        scope.last_call = {"paid_call_key": row.key, "replayed": True,
                           "billing": REPLAY_BILLING}
        return decode(row.payload or {})
    scope.last_call = None
    if row.outcome == FAILED_BILLED:
        raise PaidCallReplayedFailure(
            f"{effect}: job {job.id} already paid for this call in attempt "
            f"{row.first_attempt} and it failed ({row.error[:160]}); not bought again")
    if row.outcome == PENDING:
        _count_orphan(db, row)
    scope.unresolved.add(fp)
    _incident(db, row.key, effect, job.id, row.error or "worker lost during the call")
    raise PaidCallUnresolved(
        f"{effect}: job {job.id}'s earlier paid call (attempt {row.first_attempt}) has no "
        f"known outcome ({row.error[:120] or 'in flight when its worker was lost'}); "
        f"F-339: not re-sent until reconciled. A new job is the explicit way to ask again")


def rows(db, *, job_id: int | None = None) -> list[dict]:
    ensure_table(db)
    with db.session() as s:
        q = select(PaidCallRecord)
        if job_id is not None:
            q = q.where(PaidCallRecord.job_id == job_id)
        return [{"key": r.key, "effect": r.effect, "job_id": r.job_id,
                 "occurrence": r.occurrence, "outcome": r.outcome, "replays": r.replays,
                 "orphan_billed": r.orphan_billed, "estimate_cad": r.estimate_cad,
                 "first_attempt": r.first_attempt}
                for r in s.scalars(q.order_by(PaidCallRecord.at))]


def summary(db) -> dict:
    """Provider-contract summary for the Command Center: replays avoided, unresolved calls."""
    try:
        ensure_table(db)
        with db.session() as s:
            all_rows = list(s.scalars(select(PaidCallRecord)))
    except Exception as exc:  # noqa: BLE001 - never raise on an empty or odd DB
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": ["paid_call_records"], "reason": f"{type(exc).__name__}"}
    unresolved = [r for r in all_rows if r.outcome in (PENDING, UNCERTAIN)]
    items = [{"key": r.key[:16], "effect": r.effect, "job_id": r.job_id,
              "outcome": r.outcome, "orphan_billed": r.orphan_billed} for r in unresolved]
    return {"status": ("UNKNOWN" if not all_rows else "DEGRADED" if unresolved else "OK"),
            "as_of": utcnow().isoformat(), "basis": "measured",
            "guarded_calls": len(all_rows),
            "replays_not_billed": sum(int(r.replays or 0) for r in all_rows
                                      if r.outcome == OK),
            "unresolved": len(unresolved), "items": items[:50],
            "sources": ["paid_call_records", "effect_intents"]}


def reclaimed_spend_violations(session, job_ids) -> list[dict]:
    """For the soak (`ops.slo._effect_evidence`): which reclaimed jobs may have paid twice.

    A reclaimed job's cost rows are NOT a violation when every billed row carries the
    `paid_call_key` of its write-ahead intent and no key was billed twice: the reclaimed
    attempt replayed (CA$0, `replayed_not_billed`) or the orphan was counted once at its
    estimate. A billed row with no key (an unguarded path) or two billed rows for one key
    are violations, as before."""
    from collections import defaultdict

    from ..core.models import CostEntry

    ids = [j for j in (job_ids or []) if j is not None]
    if not ids:
        return []
    billed: dict[int, list] = defaultdict(list)
    for jid, amount, detail in session.execute(
            select(CostEntry.job_id, CostEntry.amount_cad, CostEntry.detail)
            .where(CostEntry.job_id.in_(ids))).all():
        d = detail if isinstance(detail, dict) else {}
        if d.get("billing") == REPLAY_BILLING:
            continue
        if float(amount or 0.0) <= 0 and not d.get("paid_call_key"):
            continue
        billed[jid].append(d.get("paid_call_key"))
    out = []
    for jid, keys in sorted(billed.items()):
        if any(k is None for k in keys):
            out.append({"job_id": jid, "why": "paid call(s) with no write-ahead intent "
                                               "recorded on a re-executed job"})
        elif len(keys) != len(set(keys)):
            out.append({"job_id": jid, "why": "one paid-call intent billed more than once"})
    return out
