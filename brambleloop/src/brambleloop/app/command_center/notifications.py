"""Smart owner notification policy (F-897).

Notify for decisions, risk, deadlines, meaningful commercial events and anomalies -- not
routine machine chatter. Concretely:

* **Sources** are durable state only: open incidents, the owner approval queue, dead letters
  (aggregated into one notification, never one per job), spend scopes paused by a breach, and
  bursts of refused owner-auth attempts. Routine events (completed jobs, heartbeats, lease
  renewals, ordinary audit rows) never become notifications; they are counted as suppressed.
* **Deduplicated** on a stable `dedupe_key` (unique). A condition that holds across many
  refreshes is one notification whose `last_seen_at`/`occurrences` move.
* **Severity-ranked**: critical > high > normal > low. P0 incidents, publication-halting and
  security incidents are critical; P1 and breach-paused spend are high.
* **Deadlines** are first-class: an incident's own `detail.deadline` and an open owner
  action's `expires_at` set the notification's `deadline`; an approval card inherits the
  earliest deadline of the owner actions it merges, and an open owner action with a deadline
  that no card covers becomes its own `deadline` notification. Anything due within
  `DEADLINE_SOON_HOURS` is raised to at least `high`.
* **Meaningful commercial events** (`category="commercial"`) come from the orders table only,
  aggregated so a sale never becomes one alert per row: the shop's first order, one
  per-UTC-day "orders today" notification, and one per refunded order. No order rows means no
  commercial notification -- never a fabricated "0 sales" alert.
* **Actionable**: every notification carries a consequence, at least one evidence reference
  and a `/cc/#/...` deep link to the place the owner acts.
* **Quiet hours** hold non-critical notifications for the digest; critical and security
  notifications always surface.
* **Resolved** automatically when the condition no longer holds.
* **Channel**: in-app only. External delivery (email/SMS/push) is a GATED item: commercial
  electronic messages fall under CASL and any third-party sender is a new integration, so
  nothing here sends anything outside the app.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone

from sqlalchemy import func, select

from .models import Notification, SecurityEvent, ensure_tables, kv_get, kv_set

SEVERITIES = ("critical", "high", "normal", "low")
RANK = {s: i for i, s in enumerate(SEVERITIES)}
POLICY_KEY = "notification_policy"
DEFAULT_POLICY = {"quiet_hours": None, "min_severity": "normal", "digest": "morning",
                  "channels": ["in_app"],
                  "external_channels": "GATED: owner authority + CASL review required"}
SECURITY_BURST = 5  # refused auth attempts in an hour that make one security notification
DEADLINE_SOON_HOURS = 48  # a deadline this close is at least "high"
DEADLINE_HORIZON_DAYS = 30  # owner-action deadlines further out are not yet worth an alert
COMMERCIAL_WINDOW_DAYS = 7  # first order / refunds stay surfaced this long after the order


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _incident_severity(sev: str, halts: bool, signature: str) -> tuple[str, str]:
    sig = (signature or "").lower()
    if any(k in sig for k in ("security", "auth", "tamper", "breach", "credential")):
        return "critical", "security"
    if sev == "P0" or halts:
        return "critical", "risk"
    if sev == "P1":
        return "high", "risk"
    if sev == "P2":
        return "normal", "anomaly"
    return "low", "anomaly"


def _parse_deadline(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return _aware(v)
    try:
        return _aware(datetime.fromisoformat(str(v).replace("Z", "+00:00")))
    except ValueError:
        return None


def _with_deadline(c: dict, deadline, now: datetime) -> dict:
    """Attach `deadline`; one due within DEADLINE_SOON_HOURS is raised to at least high."""
    c["deadline"] = deadline
    if deadline is not None and deadline - now <= timedelta(hours=DEADLINE_SOON_HOURS):
        if RANK[c["severity"]] > RANK["high"]:
            c["severity"] = "high"
    return c


def _owner_deadlines(s, now: datetime) -> dict[int, tuple[datetime, object]]:
    """Open owner actions with their own `expires_at` inside the horizon: {id: (due, row)}."""
    from ...core.models import OwnerAction
    from ...ops.owner_queue import OPEN, effective_state

    out = {}
    horizon = now + timedelta(days=DEADLINE_HORIZON_DAYS)
    for row in s.scalars(select(OwnerAction).where(OwnerAction.expires_at.is_not(None))):
        due = _aware(row.expires_at)
        if effective_state(row) == OPEN and now < due <= horizon:
            out[row.id] = (due, row)
    return out


def _commercial(s, now: datetime) -> list[dict]:
    """Meaningful commercial events from the orders table, aggregated (never one per sale)."""
    from ...core.models import Order

    out: list[dict] = []
    first = s.scalars(select(Order).order_by(Order.at.asc(), Order.id.asc()).limit(1)).first()
    if first is None:
        return out
    window = now - timedelta(days=COMMERCIAL_WINDOW_DAYS)
    if _aware(first.at) >= window:
        out.append({"dedupe_key": "commercial:first_order", "severity": "high",
                    "category": "commercial", "title": "First order received",
                    "body": f"{first.product_slug} v{first.version}".strip(),
                    "consequence": ("fulfilment, support and review follow-up now run on a "
                                    "real customer; check the order reached them"),
                    "evidence": [f"orders:{first.id}"], "deep_link": "/cc/#/insights",
                    "count": 1})
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = list(s.scalars(select(Order).where(Order.at >= day_start)))
    if today:
        out.append({"dedupe_key": f"commercial:orders:{day_start.date().isoformat()}",
                    "severity": "low", "category": "commercial",
                    "title": f"{len(today)} order(s) today (UTC)",
                    "body": ", ".join(sorted({o.product_slug for o in today}))[:1000],
                    "consequence": "none required; informational for the daily picture",
                    "evidence": [f"orders:{o.id}" for o in today[:10]],
                    "deep_link": "/cc/#/insights", "count": len(today)})
    for o in s.scalars(select(Order).where(Order.refunded == True,  # noqa: E712
                                           Order.at >= window)):
        out.append({"dedupe_key": f"commercial:refund:{o.external_ref}", "severity": "high",
                    "category": "commercial",
                    "title": f"Refund on {o.product_slug} v{o.version}".strip(),
                    "body": "a refunded order is a signal about the product or its listing",
                    "consequence": ("an unexplained refund can repeat; check the support case "
                                    "and the listing's promise"),
                    "evidence": [f"orders:{o.id}"]
                    + ([f"support_cases:{o.support_case_id}"] if o.support_case_id else []),
                    "deep_link": "/cc/#/insights", "count": 1})
    return out


def candidates(db) -> tuple[list[dict], int]:
    """(notifications that should exist now, routine events suppressed in the last 24 h)."""
    from ...core.models import AuditLog, Incident, Job, JobStatus, SpendLimit
    from . import approvals

    out: list[dict] = []
    now = _now()
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(Incident.resolved == False)):  # noqa: E712
            sev, cat = _incident_severity(inc.severity, bool(inc.halts_publication),
                                          inc.signature)
            out.append({"dedupe_key": f"incident:{inc.id}", "severity": sev, "category": cat,
                        "title": f"{inc.severity} incident: {inc.summary[:200]}",
                        "body": inc.summary[:1000],
                        "consequence": ("publication is halted until it is resolved"
                                        if inc.halts_publication else
                                        "stays open until its condition clears"),
                        "evidence": [f"incidents:{inc.id}"],
                        "deep_link": f"/cc/#/operations/incident/{inc.id}",
                        "count": int(inc.report_count or 1)})
            _with_deadline(out[-1], _parse_deadline((inc.detail or {}).get("deadline")), now)
        dead = s.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.DEAD)) or 0
        if dead:
            out.append({"dedupe_key": "dead_letters", "severity": "normal",
                        "category": "anomaly", "title": f"{dead} dead-lettered jobs",
                        "body": "jobs exhausted their retries; recovery may need a requeue",
                        "consequence": "the work they carried is not happening",
                        "evidence": ["jobs (status=dead)"],
                        "deep_link": "/cc/#/operations", "count": int(dead)})
        for lim in s.scalars(select(SpendLimit).where(SpendLimit.paused == True)):  # noqa: E712
            out.append({"dedupe_key": f"spend_paused:{lim.scope}", "severity": "high",
                        "category": "anomaly",
                        "title": f"Spend scope {lim.scope} is paused",
                        "body": "all spend in this scope is refused until reviewed",
                        "consequence": "work needing this spend waits",
                        "evidence": [f"spend_limits:{lim.id}"],
                        "deep_link": "/cc/#/money", "count": 1})
        out.extend(_commercial(s, now))
        owner_deadlines = _owner_deadlines(s, now)
        since = _now() - timedelta(hours=24)
        routine = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.at >= since)) or 0
        routine += s.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.DONE, Job.finished_at >= since)) or 0
    ensure_tables(db)
    with db.session() as s:
        # Only refusals that look like an attack count: bad credentials, CSRF, replays and
        # unauthenticated *mutations*. An expired session reloading a tab, or the owner's own
        # action refused by an authority, is not a security event worth waking anyone for.
        from sqlalchemy import and_, or_

        refused = s.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.outcome == "refused",
            SecurityEvent.at >= _now() - timedelta(hours=1),
            or_(SecurityEvent.reason.like("BAD_CREDENTIALS%"),
                SecurityEvent.reason.like("CSRF%"), SecurityEvent.reason.like("REPLAY%"),
                SecurityEvent.reason.like("RATE_LIMITED%"),
                and_(SecurityEvent.reason.like("NOT_AUTHENTICATED%"),
                     SecurityEvent.method != "GET")))) or 0
    if refused >= SECURITY_BURST:
        hour = _now().strftime("%Y-%m-%dT%H")
        out.append({"dedupe_key": f"security_refusals:{hour}", "severity": "critical",
                    "category": "security",
                    "title": f"{refused} refused owner-auth attempts in the last hour",
                    "body": "see Account > security events",
                    "consequence": "possible credential guessing or a misconfigured device",
                    "evidence": ["cc_security_events (outcome=refused)"],
                    "deep_link": "/cc/#/account", "count": int(refused)})
    covered: set[int] = set()
    try:
        box = approvals.inbox(db)
        for c in box["cards"]:
            if not c.get("executable") and c["kind"] == "GATE" and not c.get("unblocks"):
                continue
            spend = c.get("max_spend_cad")
            out.append({"dedupe_key": f"approval:{c['card_id']}",
                        "severity": "high" if (spend or 0) > 0 else "normal",
                        "category": "decision", "title": f"Decision needed: {c['title']}"[:300],
                        "body": c.get("recommendation") or "",
                        "consequence": c.get("consequence_of_no_action") or "",
                        "evidence": c.get("sources") or [],
                        "deep_link": f"/cc/#/approvals/{c['card_id']}", "count": 1})
            ids = {int(x.split(":", 1)[1]) for x in (c.get("sources") or [])
                   if str(x).startswith("owner_actions:") and x.split(":", 1)[1].isdigit()}
            dues = [owner_deadlines[i][0] for i in ids if i in owner_deadlines]
            covered |= ids
            _with_deadline(out[-1], _parse_deadline(c.get("deadline")) or
                           (min(dues) if dues else None), now)
    except Exception:  # noqa: BLE001 - an unreadable queue is reported on the Approvals tab
        pass
    for oid, (due, row) in sorted(owner_deadlines.items()):
        if oid in covered:
            continue
        out.append(_with_deadline({
            "dedupe_key": f"owner_deadline:{oid}", "severity": "normal",
            "category": "deadline", "title": f"Due {due.date().isoformat()}: {row.action}"[:300],
            "body": row.reason or "",
            "consequence": row.consequence_of_delay or "the owner action expires unanswered",
            "evidence": [f"owner_actions:{oid}"], "deep_link": "/cc/#/approvals",
            "count": 1}, due, now))
    # W-OWNERIMG: autonomous image production notifies on exactly two conditions. One is a
    # gallery ready for owner review. The other is a gallery blocked after its permitted
    # attempts. Dedupe is by run and state.
    try:
        from ...visual import image_production

        out.extend(image_production.notification_candidates(db))
    except Exception:  # noqa: BLE001 - an unreadable run table is visible on the Images tab
        pass
    routine_suppressed = max(0, int(routine))
    return out, routine_suppressed


def refresh(db) -> dict:
    ensure_tables(db)
    want, suppressed = candidates(db)
    now = _now()
    created = dedup = resolved = 0
    keys = set()
    with db.session() as s:
        for c in want:
            keys.add(c["dedupe_key"])
            row = s.scalar(select(Notification).where(
                Notification.dedupe_key == c["dedupe_key"]))
            if row is None:
                s.add(Notification(dedupe_key=c["dedupe_key"], severity=c["severity"],
                                   category=c["category"], title=c["title"][:300],
                                   body=c["body"], consequence=c["consequence"],
                                   evidence=c["evidence"], deep_link=c["deep_link"][:300],
                                   deadline=c.get("deadline"), first_seen_at=now, last_seen_at=now,
                                   occurrences=max(1, c["count"])))
                created += 1
                continue
            dedup += 1
            row.last_seen_at = now
            row.occurrences = max(int(row.occurrences or 1), c["count"])
            if RANK[c["severity"]] < RANK.get(row.severity, 9):
                row.severity = c["severity"]  # escalation surfaces again
                row.acked_at = None
            row.title = c["title"][:300]
            row.deadline = c.get("deadline")
            row.resolved_at = None
        for row in s.scalars(select(Notification).where(Notification.resolved_at.is_(None))):
            if row.dedupe_key not in keys:
                row.resolved_at = now
                resolved += 1
    return {"created": created, "deduplicated": dedup, "resolved": resolved,
            "suppressed": suppressed}


def get_policy(db) -> dict:
    ensure_tables(db)
    with db.session() as s:
        return {**DEFAULT_POLICY, **(kv_get(s, POLICY_KEY, {}) or {})}


def set_policy(db, body: dict) -> dict:
    from zoneinfo import ZoneInfo

    policy = get_policy(db)
    qh = body.get("quiet_hours", policy.get("quiet_hours"))
    if qh is not None:
        if not isinstance(qh, dict):
            raise ValueError("quiet_hours must be {start, end, tz} or null")
        try:
            dtime.fromisoformat(str(qh.get("start")))
            dtime.fromisoformat(str(qh.get("end")))
            ZoneInfo(str(qh.get("tz") or "UTC"))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"invalid quiet_hours: {type(exc).__name__}") from exc
        qh = {"start": str(qh["start"]), "end": str(qh["end"]), "tz": str(qh.get("tz") or "UTC")}
    ms = body.get("min_severity", policy["min_severity"])
    if ms not in SEVERITIES:
        raise ValueError(f"min_severity must be one of {list(SEVERITIES)}")
    digest = body.get("digest", policy["digest"])
    if digest not in ("morning", "none"):
        raise ValueError("digest must be 'morning' or 'none'")
    new = {"quiet_hours": qh, "min_severity": ms, "digest": digest}
    with db.session() as s:
        kv_set(s, POLICY_KEY, new)
    return {**DEFAULT_POLICY, **new}


def in_quiet_hours(policy: dict, at: datetime | None = None) -> bool:
    from zoneinfo import ZoneInfo

    qh = policy.get("quiet_hours")
    if not qh:
        return False
    at = at or _now()
    local = at.astimezone(ZoneInfo(qh.get("tz") or "UTC")).time()
    start, end = dtime.fromisoformat(qh["start"]), dtime.fromisoformat(qh["end"])
    return (start <= local < end) if start <= end else (local >= start or local < end)


def _view(r: Notification, held: bool) -> dict:
    return {"id": r.id, "dedupe_key": r.dedupe_key, "severity": r.severity,
            "category": r.category, "title": r.title, "body": r.body,
            "consequence": r.consequence,
            "deadline": _aware(r.deadline).isoformat() if r.deadline else None,
            "evidence": list(r.evidence or []), "deep_link": r.deep_link,
            "first_seen_at": _aware(r.first_seen_at).isoformat(),
            "last_seen_at": _aware(r.last_seen_at).isoformat(),
            "occurrences": r.occurrences,
            "acked_at": _aware(r.acked_at).isoformat() if r.acked_at else None,
            "delivered": "in_app", "held_for_quiet_hours": held}


def listing(db, *, at: datetime | None = None) -> dict:
    stats = refresh(db)
    policy = get_policy(db)
    quiet = in_quiet_hours(policy, at)
    min_rank = RANK[policy["min_severity"]]
    active, digest = [], []
    with db.session() as s:
        rows = list(s.scalars(select(Notification).where(
            Notification.resolved_at.is_(None))))
    far = float("inf")
    rows.sort(key=lambda r: (r.acked_at is not None, RANK.get(r.severity, 9),
                             _aware(r.deadline).timestamp() if r.deadline else far,
                             -(_aware(r.last_seen_at).timestamp())))
    for r in rows:
        always = r.severity == "critical" or r.category == "security"
        held = quiet and not always
        below = RANK.get(r.severity, 9) > min_rank and not always
        (digest if (held or below) else active).append(_view(r, held))
    return {"notifications": active, "digest": digest, "policy": policy,
            "quiet_hours_now": quiet, "suppressed_count": stats["suppressed"],
            "refresh": stats,
            "sources": ["incidents", "owner_actions", "jobs", "spend_limits", "orders",
                        "cc_security_events", "cc_notifications"]}


def ack(db, notification_id: int) -> bool:
    ensure_tables(db)
    with db.session() as s:
        row = s.get(Notification, int(notification_id))
        if row is None:
            return False
        row.acked_at = _now()
        return True
