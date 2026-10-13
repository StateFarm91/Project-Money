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

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

SECRET_ENV = "ETSY_WEBHOOK_SECRET"
SUPPORTED_EVENTS = ("order.paid", "order.canceled", "order.shipped", "order.delivered")
MAX_SKEW_SECONDS = 300
MAX_BODY_BYTES = 64 * 1024
INGEST_AGENT, INGEST_JOB = "cfo", "commerce.orders_ingest"
REFUSED_ACTION = "etsy.webhook_refused"
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


_LOCK = threading.Lock()
_FLAG = "_brambleloop_etsy_webhooks_ready"


def ensure_table(db) -> None:
    engine = db.engine
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if not getattr(engine, _FLAG, False):
            Base.metadata.create_all(engine, tables=[EtsyWebhookDelivery.__table__],
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
    want = base64.b64encode(mac).decode()
    offered = [p.split(",", 1)[1] for p in sig.split() if "," in p]
    if not any(hmac.compare_digest(want, o) for o in offered):
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


def _refused(db, exc: WebhookRefused) -> None:
    from ..core.models import AuditLog

    try:
        with db.session() as s:
            s.add(AuditLog(actor="orchestrator", action=REFUSED_ACTION,
                           detail={"reason": exc.reason, "why": exc.why[:300],
                                   "status": exc.status}))
    except Exception:  # noqa: BLE001 - a refusal is answered even if it cannot be counted
        pass


def receive(db, headers: Mapping[str, str], body: bytes, *, secret: str | None = None,
            now: datetime | None = None, shop_id: str | None = None,
            queue=None) -> tuple[int, dict]:
    """Handle one delivery. Returns (HTTP status, JSON body). Never raises for a refusal."""
    secret = secret if secret is not None else os.environ.get(SECRET_ENV)
    shop_id = shop_id if shop_id is not None else expected_shop_id()
    try:
        got = verify(headers, body, secret=secret, now=now, shop_id=shop_id)
    except WebhookRefused as exc:
        _refused(db, exc)
        return exc.status, {"accepted": False, "reason": exc.reason, "why": exc.why}
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
    """Observability for GET /api/etsy: what arrived, what it woke, what was refused."""
    from sqlalchemy import func

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
            for d in s.scalars(select(AuditLog.detail).where(
                    AuditLog.action == REFUSED_ACTION)):
                r = (d or {}).get("reason") or "unknown"
                refused[r] = refused.get(r, 0) + 1
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
