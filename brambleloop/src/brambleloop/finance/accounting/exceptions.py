"""Accounting exceptions: differences and anomalies awaiting a resolution (F-904, F-911).

An exception is opened idempotently by key, keeps its evidence, and is closed only by an
explicit resolution with a note. Nothing here adjusts a figure: the ledger excludes what it
cannot book truthfully and the exception says why.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from .models import AcctException
from .schema import ensure

SEVERITIES = ("low", "medium", "high")


def open_in(session, *, key: str, kind: str, summary: str, evidence: dict | None = None,
            period: str = "", severity: str = "medium",
            now: datetime | None = None) -> tuple[AcctException, bool]:
    now = now or datetime.now(timezone.utc)
    row = session.scalar(select(AcctException).where(AcctException.key == key))
    if row is not None:
        row.last_seen = now
        if not row.resolved:
            row.summary = summary
            row.evidence = dict(evidence or {})
        return row, False
    row = AcctException(key=key[:200], kind=kind, severity=severity if severity in SEVERITIES
                        else "medium", period=period, summary=summary,
                        evidence=dict(evidence or {}), first_seen=now, last_seen=now)
    session.add(row)
    session.flush()
    return row, True


def open_exception(db, **kw) -> dict:
    db = ensure(db)
    with db.session() as s:
        row, created = open_in(s, **kw)
        return {"id": row.id, "key": row.key, "created": created}


def resolve(db, key: str, *, resolution: str, by: str) -> dict:
    """Close an exception with a stated resolution. A blank resolution is refused."""
    if len((resolution or "").strip()) < 10:
        raise ValueError("an exception is resolved with an explanation, not a click")
    db = ensure(db)
    with db.session() as s:
        row = s.scalar(select(AcctException).where(AcctException.key == key))
        if row is None:
            raise KeyError(key)
        if row.resolved:
            return {"key": key, "changed": False}
        row.resolved = True
        row.resolved_at = datetime.now(timezone.utc)
        row.resolution = f"{by}: {resolution.strip()}"
        return {"key": key, "changed": True}


def listing(db, *, open_only: bool = True, period: str | None = None,
            kind: str | None = None) -> list[dict]:
    db = ensure(db)
    with db.session() as s:
        q = select(AcctException).order_by(AcctException.id)
        if open_only:
            q = q.where(AcctException.resolved == False)  # noqa: E712
        if period:
            q = q.where(AcctException.period == period)
        if kind:
            q = q.where(AcctException.kind == kind)
        return [{"id": r.id, "key": r.key, "kind": r.kind, "severity": r.severity,
                 "period": r.period, "summary": r.summary, "evidence": r.evidence,
                 "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                 "resolved": r.resolved, "resolution": r.resolution}
                for r in s.scalars(q)]
