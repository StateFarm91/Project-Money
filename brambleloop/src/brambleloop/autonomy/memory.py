"""Keyed writes to company memory and the company timeline.

Every write is idempotent on its key. That is the property the §95 recovery test needs: a
handler that wrote its memory row and was then killed before completing its job is re-run by
whichever worker reclaims the lease, and the re-run must leave one row, not two.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import CompanyMemory, TimelineEvent, ensure_tables


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def remember(db, key: str, *, kind: str, department: str = "", subject: str = "",
             state: str = "", body: dict | None = None, sources: list | None = None,
             now: datetime | None = None, session=None) -> dict:
    """Upsert one memory row by key. Returns {"key", "created": bool}."""
    ensure_tables(db)
    now = now or _now()

    def _do(s) -> dict:
        row = s.scalar(select(CompanyMemory).where(CompanyMemory.key == key))
        if row is None:
            try:
                with s.begin_nested():
                    s.add(CompanyMemory(key=key, kind=kind, department=department,
                                        subject=subject[:200], state=state, body=body or {},
                                        sources=list(sources or []), created_at=now,
                                        updated_at=now))
                return {"key": key, "created": True}
            except IntegrityError:
                row = s.scalar(select(CompanyMemory).where(CompanyMemory.key == key))
        row.kind, row.department = kind, department or row.department
        if subject:
            row.subject = subject[:200]
        if state:
            row.state = state
        if body is not None:
            row.body = body
        if sources is not None:
            row.sources = list(sources)
        row.updated_at = now
        return {"key": key, "created": False}

    if session is not None:
        return _do(session)
    with db.session() as s:
        return _do(s)


def recall(db, *, kind: str | None = None, department: str | None = None,
           state: str | None = None, since: datetime | None = None,
           limit: int = 200) -> list[dict]:
    """Query memory, newest first."""
    ensure_tables(db)
    q = select(CompanyMemory).order_by(CompanyMemory.updated_at.desc(),
                                       CompanyMemory.id.desc()).limit(limit)
    if kind:
        q = q.where(CompanyMemory.kind == kind)
    if department:
        q = q.where(CompanyMemory.department == department)
    if state:
        q = q.where(CompanyMemory.state == state)
    if since is not None:
        q = q.where(CompanyMemory.updated_at >= since)
    with db.session() as s:
        return [_mem_dict(r) for r in s.scalars(q)]


def get(db, key: str) -> dict | None:
    ensure_tables(db)
    with db.session() as s:
        row = s.scalar(select(CompanyMemory).where(CompanyMemory.key == key))
        return _mem_dict(row) if row else None


def _mem_dict(r: CompanyMemory) -> dict:
    return {"id": r.id, "key": r.key, "kind": r.kind, "department": r.department,
            "subject": r.subject, "state": r.state, "body": r.body or {},
            "sources": list(r.sources or []),
            "created_at": _aware(r.created_at).isoformat() if r.created_at else None,
            "updated_at": _aware(r.updated_at).isoformat() if r.updated_at else None}


def record_event(db, key: str, *, kind: str, summary: str, department: str = "",
                 actor: str = "coo", severity: str = "info", refs: list | None = None,
                 at: datetime | None = None, session=None) -> bool:
    """Append one timeline event unless its key exists. True when this call wrote it."""
    ensure_tables(db)
    at = at or _now()

    def _do(s) -> bool:
        if s.scalar(select(TimelineEvent.id).where(TimelineEvent.key == key)) is not None:
            return False
        try:
            with s.begin_nested():
                s.add(TimelineEvent(key=key, at=at, kind=kind, department=department,
                                    actor=actor, severity=severity, summary=summary[:2000],
                                    refs=list(refs or [])))
            return True
        except IntegrityError:
            return False

    if session is not None:
        return _do(session)
    with db.session() as s:
        return _do(s)


def events(db, *, limit: int = 50, since: datetime | None = None,
           department: str | None = None) -> list[dict]:
    ensure_tables(db)
    q = select(TimelineEvent).order_by(TimelineEvent.at.desc(),
                                       TimelineEvent.id.desc()).limit(limit)
    if since is not None:
        q = q.where(TimelineEvent.at >= since)
    if department:
        q = q.where(TimelineEvent.department == department)
    with db.session() as s:
        return [{"id": e.id, "key": e.key, "at": _aware(e.at).isoformat(), "kind": e.kind,
                 "department": e.department, "actor": e.actor, "severity": e.severity,
                 "summary": e.summary, "refs": list(e.refs or [])} for e in s.scalars(q)]


# ---- department blocks (F-894 / §95 "block one department on an owner action") ----------

def block_department(db, department: str, *, reason: str, owner_action: str = "",
                     until: datetime | None = None, now: datetime | None = None) -> dict:
    """Record that a department is blocked (owner action, emergency pause). Others continue."""
    now = now or _now()
    out = remember(db, f"block:{department}", kind="block", department=department,
                   subject=reason[:200], state="active",
                   body={"reason": reason, "owner_action": owner_action,
                         "until": until.isoformat() if until else None,
                         "since": now.isoformat()},
                   sources=[f"owner_actions:{owner_action}"] if owner_action else [], now=now)
    record_event(db, f"block:{department}:{now.isoformat()}", kind="department.blocked",
                 department=department, summary=f"{department} blocked: {reason}",
                 severity="warn", at=now)
    return out


def unblock_department(db, department: str, *, now: datetime | None = None) -> None:
    now = now or _now()
    row = get(db, f"block:{department}")
    if row is None or row["state"] != "active":
        return
    remember(db, f"block:{department}", kind="block", department=department,
             state="cleared", body={**row["body"], "cleared": now.isoformat()}, now=now)
    record_event(db, f"unblock:{department}:{now.isoformat()}", kind="department.unblocked",
                 department=department, summary=f"{department} unblocked", at=now)


def active_block(db, department: str, *, now: datetime | None = None) -> dict | None:
    now = now or _now()
    row = get(db, f"block:{department}")
    if row is None or row["state"] != "active":
        return None
    until = row["body"].get("until")
    if until:
        try:
            if datetime.fromisoformat(until) <= now:
                return None
        except ValueError:
            pass
    return row


def prune_timeline(db, *, keep_days: int = 180, now: datetime | None = None) -> int:
    """Bound the timeline's growth. Called by the orchestrator once a day at most."""
    ensure_tables(db)
    cutoff = (now or _now()) - timedelta(days=keep_days)
    with db.session() as s:
        rows = list(s.scalars(select(TimelineEvent).where(TimelineEvent.at < cutoff)))
        for r in rows:
            s.delete(r)
        return len(rows)
