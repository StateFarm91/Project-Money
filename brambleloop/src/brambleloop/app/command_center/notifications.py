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


def candidates(db) -> tuple[list[dict], int]:
    """(notifications that should exist now, routine events suppressed in the last 24 h)."""
    from ...core.models import AuditLog, Incident, Job, JobStatus, SpendLimit
    from . import approvals

    out: list[dict] = []
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
        since = _now() - timedelta(hours=24)
        routine = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.at >= since)) or 0
        routine += s.scalar(select(func.count()).select_from(Job).where(
            Job.status == JobStatus.DONE, Job.finished_at >= since)) or 0
    ensure_tables(db)
    with db.session() as s:
        refused = s.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.outcome == "refused",
            SecurityEvent.at >= _now() - timedelta(hours=1))) or 0
    if refused >= SECURITY_BURST:
        hour = _now().strftime("%Y-%m-%dT%H")
        out.append({"dedupe_key": f"security_refusals:{hour}", "severity": "critical",
                    "category": "security",
                    "title": f"{refused} refused owner-auth attempts in the last hour",
                    "body": "see Account > security events",
                    "consequence": "possible credential guessing or a misconfigured device",
                    "evidence": ["cc_security_events (outcome=refused)"],
                    "deep_link": "/cc/#/account", "count": int(refused)})
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
    except Exception:  # noqa: BLE001 - an unreadable queue is reported on the Approvals tab
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
                                   first_seen_at=now, last_seen_at=now,
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
    rows.sort(key=lambda r: (r.acked_at is not None, RANK.get(r.severity, 9),
                             -(_aware(r.last_seen_at).timestamp())))
    for r in rows:
        always = r.severity == "critical" or r.category == "security"
        held = quiet and not always
        below = RANK.get(r.severity, 9) > min_rank and not always
        (digest if (held or below) else active).append(_view(r, held))
    return {"notifications": active, "digest": digest, "policy": policy,
            "quiet_hours_now": quiet, "suppressed_count": stats["suppressed"],
            "refresh": stats,
            "sources": ["incidents", "owner_actions", "jobs", "spend_limits",
                        "cc_security_events", "cc_notifications"]}


def ack(db, notification_id: int) -> bool:
    ensure_tables(db)
    with db.session() as s:
        row = s.get(Notification, int(notification_id))
        if row is None:
            return False
        row.acked_at = _now()
        return True
