"""Etsy webhook receiver: a verified, durable, idempotent wake for the order layer
(F-512 Webhook Reliability, F-501 Etsy Event Feedback, F-657 Event Wakeups).

Primary documentation (F-437), read 2026-10-12 from
https://developers.etsy.com/documentation/essentials/webhooks:

* events: ``order.paid``, ``order.canceled``, ``order.shipped``, ``order.delivered``;
* headers: ``webhook-id`` (unchanged on retries), ``webhook-timestamp`` (Unix seconds),
  ``webhook-signature`` (possibly several space-separated ``v1,<base64>`` entries);
* signature: HMAC-SHA256 over ``<webhook-id>.<webhook-timestamp>.<raw body>`` keyed with the
  Base64-decoded part of the ``whsec_`` secret, Base64-encoded; accept if ANY entry matches;
* the documented example refuses a timestamp more than 300 s from server time;
* Etsy retries a failed delivery (immediately, 5 s, 5 min, 30 min, 2 h, 5 h, 10 h, 10 h);
* payload: ``event_type``, ``resource_url``, ``shop_id`` (+ event-specific fields).
Registration is a Developer Portal action (the owner's), not an API call.

Design: the webhook is a *wake*, never a source of truth. A verified delivery is stored once
(unique on ``webhook-id``), and enqueues ONE ``commerce.orders_ingest`` job keyed by that id,
which re-reads the receipt from Etsy through the authenticated reader. Nothing in the payload
is written to an order, so a forged or stale payload that somehow passed verification still
cannot invent a sale. Each step is observable (``summary``), and the five properties the
criterion names map to code:

=================  ==========================================================================
validation         ``verify``: secret format, required headers, skew <= 300 s, HMAC, event
                   type, body JSON, shop id against the bound shop
idempotency        ``webhook_id`` UNIQUE; ingest job idempotency key ``etsy.webhook:<id>``
duplicate guard    a retry/replay of a stored id answers 200 ``duplicate`` and writes nothing
                   but its counter
retries            a failure to store/enqueue answers 500 so Etsy retries; the ingest job has
                   ``max_attempts`` and dead-letters like every job
storage            ``etsy_webhook_deliveries`` (body digest, never the body)
observability      ``summary``: counts by status/event, last delivery, refusals by reason,
                   served under ``GET /api/etsy`` (``webhooks``)
=================  ==========================================================================

REL2 (independent security review of a25a377, M1/L1/L2): the endpoint is public, so a refusal
must cost the server O(1) storage however often it is provoked. A refusal increments one
counter row per reason (``etsy_webhook_refusals``, a closed set of code-defined reasons) and
writes at most one sampled audit row per reason per ``AUDIT_SAMPLE_SECONDS``; ``summary``
aggregates in SQL. The body is read as a stream against a running cap (``read_body``), so an
oversized body is refused without being buffered, and a signature header that is not ASCII is
compared as bytes, so it is a clean ``bad_signature`` refusal rather than a 500.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import threading
from datetime import datetime, timezone
from typing import Mapping

from sqlalchemy import BigInteger, DateTime, Integer, String, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

SECRET_ENV = "ETSY_WEBHOOK_SECRET"
SUPPORTED_EVENTS = ("order.paid", "order.canceled", "order.shipped", "order.delivered")
MAX_SKEW_SECONDS = 300
MAX_BODY_BYTES = 64 * 1024
INGEST_AGENT, INGEST_JOB = "cfo", "commerce.orders_ingest"
# Legacy: one audit row per refusal (a25a377 and earlier). No longer written; still counted.
REFUSED_ACTION = "etsy.webhook_refused"
# REL2/M1: at most one sampled audit row per refusal reason per AUDIT_SAMPLE_SECONDS.
REFUSAL_SAMPLE_ACTION = "etsy.webhook_refusal_sampled"
AUDIT_SAMPLE_SECONDS = 3600
# The closed set of refusal reasons. A reason outside it is counted as "other", so the counter
# table can never grow with what a request says.
REFUSAL_REASONS = ("not_configured", "secret_malformed", "missing_headers", "malformed",
                   "too_large", "stale", "bad_signature", "unsupported_event", "foreign_shop")
DOCS = "https://developers.etsy.com/documentation/essentials/webhooks"


class WebhookRefused(ValueError):
    """A delivery that is not provably from Etsy, for this shop, now. `status` is the HTTP
    answer; `reason` a stable code for the refusal counters."""

    def __init__(self, reason: str, why: str, status: int = 401):
        super().__init__(f"{reason}: {why}")
        self.reason, self.why, self.status = reason, why, status


class EtsyWebhookDelivery(Base):
    __tablename__ = "etsy_webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    webhook_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    shop_id: Mapped[str] = mapped_column(String(40), default="")
    emitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                  index=True)
    body_sha256: Mapped[str] = mapped_column(String(64))
    resource_url: Mapped[str] = mapped_column(String(500), default="")
    # accepted -> the ingest job is queued; the job's own row carries its outcome.
    status: Mapped[str] = mapped_column(String(20), default="accepted", index=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    last_duplicate_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                               nullable=True)


class EtsyWebhookRefusal(Base):
    """REL2/M1: one row per refusal reason, incremented in place (never one row per request)."""

    __tablename__ = "etsy_webhook_refusals"

    reason: Mapped[str] = mapped_column(String(40), primary_key=True)
    # Security review of 5f18d11 (L1): BIGINT, so a flood cannot overflow the counter (int4
    # stops at 2^31-1 and the swallowed error would freeze it silently).
    count: Mapped[int] = mapped_column(BigInteger, default=0)
    last_status: Mapped[int] = mapped_column(Integer, default=0)
    first_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Unix seconds of the last sampled audit row, compared as an integer on every dialect.
    last_audit_epoch: Mapped[int] = mapped_column(BigInteger, default=0)


_LOCK = threading.Lock()
_FLAG = "_brambleloop_etsy_webhooks_ready"


def ensure_table(db) -> None:
    engine = db.engine
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if not getattr(engine, _FLAG, False):
            Base.metadata.create_all(engine, tables=[EtsyWebhookDelivery.__table__,
                                                     EtsyWebhookRefusal.__table__],
                                     checkfirst=True)
            setattr(engine, _FLAG, True)


# ---------------------------------------------------------------------------
# Validation


def _key(secret: str | None) -> bytes:
    if not secret:
        raise WebhookRefused("not_configured", f"{SECRET_ENV} is not set: no delivery can be "
                             "verified, so none is accepted", status=503)
    raw = secret[len("whsec_"):] if secret.startswith("whsec_") else None
    if not raw:
        raise WebhookRefused("secret_malformed", "the signing secret is not a whsec_ secret",
                             status=503)
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise WebhookRefused("secret_malformed", "the whsec_ secret is not Base64",
                             status=503) from None


def sign(secret: str, webhook_id: str, timestamp: str, body: bytes) -> str:
    """The documented signature, as Etsy sends it (``v1,<base64>``). Used by tests and by
    anyone checking a captured delivery by hand."""
    mac = hmac.new(_key(secret), f"{webhook_id}.{timestamp}.".encode() + body,
                   hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode()


def _header(headers: Mapping[str, str], name: str) -> str:
    for k, v in headers.items():
        if k.lower() == name:
            return str(v).strip()
    return ""


class BodyTooLarge(WebhookRefused):
    def __init__(self, why: str):
        super().__init__("too_large", why, status=413)


async def read_body(stream, content_length: str | None, *, cap: int = MAX_BODY_BYTES) -> bytes:
    """REL2/L1: the request body, refused before it is buffered past `cap`.

    A declared Content-Length above the cap is refused without reading a byte; a body that
    declares nothing (chunked) or understates itself is read chunk by chunk and refused the
    moment the running total passes the cap. Raises BodyTooLarge or WebhookRefused."""
    if content_length is not None and str(content_length).strip():
        try:
            declared = int(str(content_length).strip())
        except ValueError:
            raise WebhookRefused("malformed", "Content-Length is not an integer",
                                 status=400) from None
        if declared < 0:
            raise WebhookRefused("malformed", "Content-Length is negative", status=400)
        if declared > cap:
            raise BodyTooLarge(f"declared body over {cap} bytes")
    buf = bytearray()
    async for chunk in stream:
        buf += chunk
        if len(buf) > cap:
            raise BodyTooLarge(f"body over {cap} bytes")
    return bytes(buf)


def _ascii_bytes(value: str) -> bytes:
    """A header value as bytes for a constant-time compare. Starlette decodes headers as
    latin-1, so a non-ASCII value is legal input here; it must mismatch, never raise (L2)."""
    return value.encode("utf-8", "surrogateescape") if isinstance(value, str) else bytes(value)


def expected_shop_id() -> str | None:
    """The shop this company's grant is bound to, when known. None means not yet bound; a
    delivery is then still only a wake (it writes nothing an ingest would not)."""
    sid = (os.environ.get("ETSY_SHOP_ID") or "").strip()
    return sid or None


def verify(headers: Mapping[str, str], body: bytes, *, secret: str | None,
           now: datetime | None = None, shop_id: str | None = None) -> dict:
    """Return the verified delivery's fields, or raise WebhookRefused. Order matters: nothing
    in the body is parsed until the signature over the raw bytes has matched."""
    key = _key(secret)
    wid = _header(headers, "webhook-id")
    ts = _header(headers, "webhook-timestamp")
    sig = _header(headers, "webhook-signature")
    if not (wid and ts and sig):
        raise WebhookRefused("missing_headers", "webhook-id, webhook-timestamp and "
                             "webhook-signature are all required", status=400)
    if len(wid) > 200:
        raise WebhookRefused("malformed", "webhook-id is longer than 200 characters", 400)
    if len(body) > MAX_BODY_BYTES:
        raise WebhookRefused("too_large", f"body over {MAX_BODY_BYTES} bytes", status=413)
    try:
        emitted = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise WebhookRefused("malformed", "webhook-timestamp is not Unix seconds",
                             status=400) from None
    now = now or datetime.now(timezone.utc)
    skew = abs((now - emitted).total_seconds())
    if skew > MAX_SKEW_SECONDS:
        raise WebhookRefused("stale", f"timestamp {skew:.0f}s from server time (limit "
                             f"{MAX_SKEW_SECONDS}s): a replay or a clock fault")
    mac = hmac.new(key, f"{wid}.{ts}.".encode() + body, hashlib.sha256).digest()
    want = base64.b64encode(mac)
    offered = [p.split(",", 1)[1] for p in sig.split() if "," in p]
    # REL2/L2: compare bytes. compare_digest(str, str) raises TypeError on non-ASCII text.
    if not any(hmac.compare_digest(want, _ascii_bytes(o)) for o in offered):
        raise WebhookRefused("bad_signature", "no webhook-signature entry matches")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise WebhookRefused("malformed", "signed body is not JSON", status=400) from None
    if not isinstance(payload, dict):
        raise WebhookRefused("malformed", "signed body is not a JSON object", status=400)
    event = str(payload.get("event_type") or "")
    if event not in SUPPORTED_EVENTS:
        raise WebhookRefused("unsupported_event", f"event_type {event!r} is not one of "
                             f"{SUPPORTED_EVENTS}", status=422)
    got_shop = str(payload.get("shop_id") or "")
    if shop_id and got_shop != str(shop_id):
        raise WebhookRefused("foreign_shop", "the event names a shop this company's grant "
                             "is not bound to", status=403)
    return {"webhook_id": wid, "emitted_at": emitted, "event_type": event,
            "shop_id": got_shop, "resource_url": str(payload.get("resource_url") or "")[:500],
            "body_sha256": hashlib.sha256(body).hexdigest(), "skew_seconds": round(skew, 1)}


# ---------------------------------------------------------------------------
# Storage, idempotency and the wake


def _upsert(dialect: str, reason: str, now: datetime, status: int):
    """INSERT ... ON CONFLICT (reason) DO UPDATE count = count + 1: one statement, atomic,
    on the two dialects this runs on. None for any other dialect (then the two-step path)."""
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        return None
    t = EtsyWebhookRefusal
    ins = insert(t).values(reason=reason, count=1, first_at=now, last_at=now,
                           last_status=status, last_audit_epoch=0)
    return ins.on_conflict_do_update(index_elements=[t.reason],
                                     set_={"count": t.count + 1, "last_at": now,
                                           "last_status": status})


def _refused(db, exc: WebhookRefused, *, now: datetime | None = None) -> None:
    """Count one refusal: an upsert on its reason's counter row, and an audit row only when
    that reason has not been sampled within AUDIT_SAMPLE_SECONDS (REL2/M1). Storage is bounded
    by the closed reason set, whatever the request rate.

    Security review of 5f18d11 (M1): ONE transaction per refusal -- the counter upsert, the
    conditional claim of the sample slot and (when claimed) the sampled audit row commit
    together -- instead of up to three. The route runs this off the event loop."""
    from ..core.models import AuditLog

    reason = exc.reason if exc.reason in REFUSAL_REASONS else "other"
    now = now or datetime.now(timezone.utc)
    epoch = int(now.timestamp())
    status = int(exc.status)
    try:
        ensure_table(db)
        upsert = _upsert(db.engine.dialect.name, reason, now, status)
        if upsert is None:  # pragma: no cover - only sqlite and postgresql are deployed
            bump = (update(EtsyWebhookRefusal).where(EtsyWebhookRefusal.reason == reason)
                    .values(count=EtsyWebhookRefusal.count + 1, last_at=now,
                            last_status=status))
            with db.session() as s:
                hit = s.execute(bump).rowcount
            if not hit:
                try:
                    with db.session() as s:
                        s.add(EtsyWebhookRefusal(reason=reason, count=1, first_at=now,
                                                 last_at=now, last_status=status,
                                                 last_audit_epoch=0))
                except IntegrityError:  # a concurrent first refusal won the insert
                    with db.session() as s:
                        s.execute(bump)
        with db.session() as s:
            if upsert is not None:
                s.execute(upsert)
            # Claim the sample slot with a conditional update, so concurrent refusals write
            # one audit row between them rather than one each.
            claimed = s.execute(
                update(EtsyWebhookRefusal).where(
                    EtsyWebhookRefusal.reason == reason,
                    EtsyWebhookRefusal.last_audit_epoch <= epoch - AUDIT_SAMPLE_SECONDS)
                .values(last_audit_epoch=epoch)).rowcount
            if claimed:
                total = s.scalar(select(EtsyWebhookRefusal.count).where(
                    EtsyWebhookRefusal.reason == reason))
                s.add(AuditLog(actor="orchestrator", action=REFUSAL_SAMPLE_ACTION,
                               detail={"reason": reason, "why": exc.why[:300],
                                       "status": exc.status, "count_so_far": int(total or 0),
                                       "sample_window_seconds": AUDIT_SAMPLE_SECONDS}))
    except Exception:  # noqa: BLE001 - a refusal is answered even if it cannot be counted
        pass


def refuse(db, exc: WebhookRefused) -> tuple[int, dict]:
    """Count a refusal raised outside `receive` (the route's body read) and answer it."""
    _refused(db, exc)
    return exc.status, {"accepted": False, "reason": exc.reason, "why": exc.why}


def receive(db, headers: Mapping[str, str], body: bytes, *, secret: str | None = None,
            now: datetime | None = None, shop_id: str | None = None,
            queue=None) -> tuple[int, dict]:
    """Handle one delivery. Returns (HTTP status, JSON body). Never raises for a refusal."""
    secret = secret if secret is not None else os.environ.get(SECRET_ENV)
    shop_id = shop_id if shop_id is not None else expected_shop_id()
    try:
        got = verify(headers, body, secret=secret, now=now, shop_id=shop_id)
    except WebhookRefused as exc:
        return refuse(db, exc)
    ensure_table(db)
    from ..queue.durable import DuplicateJob, JobQueue

    queue = queue or JobQueue(db)
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(EtsyWebhookDelivery).where(
            EtsyWebhookDelivery.webhook_id == got["webhook_id"]))
        if row is not None:
            row.duplicates = int(row.duplicates or 0) + 1
            row.last_duplicate_at = now
            return 200, {"accepted": True, "duplicate": True, "job_id": row.job_id,
                         "why": "already received under this webhook-id; nothing re-run"}
    key = f"etsy.webhook:{got['webhook_id']}"
    try:
        job = queue.enqueue(INGEST_AGENT, INGEST_JOB,
                            {"wake": "etsy.webhook", "event_type": got["event_type"],
                             "webhook_id": got["webhook_id"]},
                            idempotency_key=key)
        job_id = job.id
    except DuplicateJob as dup:
        job_id = dup.existing_id
    except Exception as exc:  # noqa: BLE001 - not woken: answer 5xx so Etsy retries
        return 500, {"accepted": False, "reason": "enqueue_failed",
                     "why": f"{type(exc).__name__}: not stored; Etsy will retry"}
    try:
        with db.session() as s:
            s.add(EtsyWebhookDelivery(
                webhook_id=got["webhook_id"], event_type=got["event_type"],
                shop_id=got["shop_id"], emitted_at=got["emitted_at"], received_at=now,
                body_sha256=got["body_sha256"], resource_url=got["resource_url"],
                status="accepted", job_id=job_id))
    except Exception as exc:  # noqa: BLE001 - a lost race is a duplicate, anything else retries
        with db.session() as s:
            if s.scalar(select(EtsyWebhookDelivery.id).where(
                    EtsyWebhookDelivery.webhook_id == got["webhook_id"])) is not None:
                return 200, {"accepted": True, "duplicate": True, "job_id": job_id}
        return 500, {"accepted": False, "reason": "storage_failed",
                     "why": f"{type(exc).__name__}: not stored; Etsy will retry"}
    return 202, {"accepted": True, "duplicate": False, "job_id": job_id,
                 "event_type": got["event_type"],
                 "note": "a wake only: the receipt is re-read from Etsy by commerce.orders_ingest"}


def summary(db) -> dict:
    """Observability for GET /api/etsy: what arrived, what it woke, what was refused.

    Every count is a SQL aggregate (REL2/M1): refusals are the per-reason counter rows plus
    the legacy one-row-per-refusal audit rows grouped by reason in SQL, never iterated."""
    from ..core.models import AuditLog, Job

    configured = bool(os.environ.get(SECRET_ENV))
    try:
        ensure_table(db)
        with db.session() as s:
            by_event = dict(s.execute(select(EtsyWebhookDelivery.event_type,
                                             func.count()).group_by(
                EtsyWebhookDelivery.event_type)).all())
            dupes = s.scalar(select(func.coalesce(func.sum(EtsyWebhookDelivery.duplicates),
                                                  0))) or 0
            last = s.scalar(select(EtsyWebhookDelivery).order_by(
                EtsyWebhookDelivery.received_at.desc()).limit(1))
            job_ids = [j for j in s.scalars(select(EtsyWebhookDelivery.job_id)) if j]
            job_states: dict[str, int] = {}
            if job_ids:
                for st, n in s.execute(select(Job.status, func.count()).where(
                        Job.id.in_(job_ids)).group_by(Job.status)).all():
                    job_states[getattr(st, "value", str(st))] = n
            refused: dict[str, int] = {}
            for r, n in s.execute(select(EtsyWebhookRefusal.reason,
                                         EtsyWebhookRefusal.count)).all():
                refused[r] = refused.get(r, 0) + int(n or 0)
            legacy_reason = AuditLog.detail["reason"].as_string()
            for r, n in s.execute(select(legacy_reason, func.count()).where(
                    AuditLog.action == REFUSED_ACTION).group_by(legacy_reason)).all():
                refused[r or "unknown"] = refused.get(r or "unknown", 0) + int(n or 0)
    except Exception as exc:  # noqa: BLE001 - a status read never 500s
        return {"configured": configured, "reading": "UNKNOWN",
                "why": f"{type(exc).__name__}"}
    received = sum(by_event.values())
    return {
        "configured": configured, "reading": "measured" if received else
        ("no_deliveries" if configured else "not_configured"),
        "received": received, "by_event": by_event, "duplicates": int(dupes),
        "woken_jobs": job_states, "refused": refused,
        "last": ({"event_type": last.event_type, "received_at": last.received_at.isoformat()
                  if last.received_at else None, "job_id": last.job_id} if last else None),
        "events_supported": list(SUPPORTED_EVENTS), "docs": DOCS,
        "note": ("deliveries are wakes: orders come only from the authenticated receipt read. "
                 "Registering the endpoint is an owner Developer Portal action."),
    }
