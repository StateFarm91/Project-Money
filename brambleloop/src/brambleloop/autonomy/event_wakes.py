"""Business events wake the team that owns them (F-657 Event Wakeups).

Criterion: orders, messages, reviews, refunds, Etsy events, policy changes, incidents, spend
anomalies, research signals, schedules and owner decisions wake the appropriate team.

Before this module a new order waited for the next six-hourly or daily cadence of the team
that reads it. `scan` runs on every `autonomy.orchestrate` tick (15 minutes, and the empty-
queue wake) and on demand: it reads the durable rows each kind of event leaves, compares
them with the last scan's cursor (`OperatingReading` kind ``autonomy.event_wakes``), and for
each kind with something new enqueues ONE job for the owning team -- debounced, keyed
``wake:<kind>:<marker>``, so a burst of fifty orders is one wake and a re-run is a no-op.

=================  =====================================  ==================================
event              durable evidence                       team (agent -> job type)
=================  =====================================  ==================================
order              orders.id                              cfo -> commerce.order_readings
refund             orders refunded / refund amount        cfo -> commerce.order_readings
review             orders.reviewed                        support -> support.triage
message            support_cases.id                       support -> support.triage
Etsy event         etsy_webhook_deliveries (F-512)        cfo -> commerce.orders_ingest
                   (woken directly by the receiver; counted here)
policy change      incidents policy_changed:* /           orchestrator -> ops.policy_watch
                   policy_stale*
incident           incidents.id (other signatures)        orchestrator -> ops.health
spend anomaly      acct_exceptions anomaly:spike:*        cfo -> finance.governor
research signal    culture_signals.id                     market_radar -> radar.scan
owner decision     owner_actions closed (state_at)        coo -> autonomy.orchestrate
schedule           runtime.worker.Scheduler cadences      (each cadence enqueues its own job)
=================  =====================================  ==================================

Every route's job type is held by its agent in the registry (checked by the test), and none is
a protected job type: a wake can only start safe work a cadence would have started anyway.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

CURSOR_KIND = "autonomy.event_wakes"

ROUTES: dict[str, tuple[str, str]] = {
    "order": ("cfo", "commerce.order_readings"),
    "refund": ("cfo", "commerce.order_readings"),
    "review": ("support", "support.triage"),
    "message": ("support", "support.triage"),
    "etsy_event": ("cfo", "commerce.orders_ingest"),
    "policy_change": ("orchestrator", "ops.policy_watch"),
    "incident": ("orchestrator", "ops.health"),
    "spend_anomaly": ("cfo", "finance.governor"),
    "research_signal": ("market_radar", "radar.scan"),
    "owner_decision": ("coo", "autonomy.orchestrate"),
}
SCHEDULE = "schedule: runtime.worker.Scheduler enqueues each cadence's own job when due"


def _fp(items) -> str:
    return hashlib.sha256("\n".join(sorted(map(str, items))).encode()).hexdigest()[:16]


def _observe(db) -> dict[str, dict]:
    """Per kind: a monotone marker (max id or fingerprint) and what is new is judged by it."""
    from sqlalchemy import func, or_, select

    from ..core.models import CultureSignal, Incident, Order, OwnerAction, SupportCase

    out: dict[str, dict] = {}
    with db.session() as s:
        out["order"] = {"max_id": s.scalar(select(func.max(Order.id))) or 0}
        refunded = [r for r, d, f in s.execute(select(Order.external_ref, Order.detail,
                                                      Order.refunded)).all()
                    if f or float(((d or {}).get("refund") or {}).get("cad") or 0) > 0]
        out["refund"] = {"set": refunded}
        out["review"] = {"set": list(s.scalars(select(Order.external_ref).where(
            Order.reviewed == True)))}  # noqa: E712
        out["message"] = {"max_id": s.scalar(select(func.max(SupportCase.id))) or 0}
        pol = or_(Incident.signature.like("policy_changed:%"),
                  Incident.signature.like("policy_stale%"))
        out["policy_change"] = {"max_id": s.scalar(select(func.max(Incident.id)).where(pol))
                                or 0}
        out["incident"] = {"max_id": s.scalar(select(func.max(Incident.id)).where(~pol)) or 0}
        out["research_signal"] = {"max_id": s.scalar(select(func.max(CultureSignal.id))) or 0}
        closed = [f"{i}:{st}" for i, st in s.execute(select(OwnerAction.id, OwnerAction.state)
                                                     .where(OwnerAction.done == True)).all()]  # noqa: E712
        out["owner_decision"] = {"set": closed}
    try:
        from ..finance.accounting.models import AcctException
        from ..finance.accounting.schema import ensure

        ensure(db)
        with db.session() as s:
            out["spend_anomaly"] = {"max_id": s.scalar(select(func.max(AcctException.id)).where(
                AcctException.key.like("anomaly:spike:%"))) or 0}
    except Exception:  # noqa: BLE001 - no accounting tables: nothing to observe
        out["spend_anomaly"] = {"max_id": 0}
    try:
        from ..integrations.etsy_webhooks import EtsyWebhookDelivery, ensure_table

        ensure_table(db)
        with db.session() as s:
            out["etsy_event"] = {"max_id": s.scalar(select(func.max(EtsyWebhookDelivery.id)))
                                 or 0, "direct": True}
    except Exception:  # noqa: BLE001
        out["etsy_event"] = {"max_id": 0, "direct": True}
    return out


def _cursor(db) -> tuple[dict, object]:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == CURSOR_KIND,
                                                      OperatingReading.period_key == "cursor"))
        return (dict(row.payload or {}) if row else {}), row


def _save(db, payload: dict, now: datetime) -> None:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == CURSOR_KIND,
                                                      OperatingReading.period_key == "cursor"))
        if row is None:
            s.add(OperatingReading(kind=CURSOR_KIND, period_key="cursor", at=now,
                                   payload=payload))
        else:
            row.payload, row.at = payload, now


def scan(db, queue=None, *, now: datetime | None = None) -> dict:
    """Wake each team whose events changed since the last scan. Idempotent and debounced."""
    from ..queue.durable import DuplicateJob, JobQueue

    now = now or datetime.now(timezone.utc)
    queue = queue or JobQueue(db)
    seen = _observe(db)
    before, _ = _cursor(db)
    after, woken, skipped = {}, [], []
    for kind, obs in seen.items():
        prev = before.get(kind) or {}
        if "set" in obs:
            current = set(obs["set"])
            new = sorted(current - set(prev.get("seen") or []))
            after[kind] = {"seen": sorted(current)[-2000:]}
            marker = _fp(new) if new else None
        else:
            new_count = max(0, int(obs["max_id"]) - int(prev.get("max_id") or 0))
            after[kind] = {"max_id": int(obs["max_id"])}
            marker = str(obs["max_id"]) if new_count else None
            new = new_count
        if not marker:
            continue
        if obs.get("direct"):
            skipped.append({"kind": kind, "why": "woken directly by the receiver (F-512)"})
            continue
        agent, job_type = ROUTES[kind]
        key = f"wake:{kind}:{marker}"
        try:
            job = queue.enqueue(agent, job_type, {"wake": kind, "new": new if isinstance(
                new, int) else len(new)}, idempotency_key=key)
            woken.append({"kind": kind, "agent": agent, "job_type": job_type,
                          "job_id": job.id})
        except DuplicateJob as dup:
            woken.append({"kind": kind, "agent": agent, "job_type": job_type,
                          "job_id": dup.existing_id, "duplicate": True})
        except Exception as exc:  # noqa: BLE001 - not woken: keep the cursor, retry next scan
            after[kind] = prev
            skipped.append({"kind": kind, "why": f"enqueue failed: {type(exc).__name__}"})
    _save(db, after, now)
    return {"at": now.isoformat(), "woken": woken, "skipped": skipped,
            "schedule": SCHEDULE}
