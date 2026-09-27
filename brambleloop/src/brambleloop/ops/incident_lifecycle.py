"""Incidents close when their condition stops holding, and they say what closed them.

Production on 2026-09-26 held seventeen open incidents. Every detector in this system knew
how to *open* a row -- "if the condition is true and no open row carries this signature, add
one" -- and almost none knew how to close it. So the rows accumulated: a product that had
missed its window stayed "at risk", a health signal that recovered stayed "bad for three
sweeps", and a stall whose ready work was later parked stayed stalled. A channel where nothing
ever closes is a channel nobody reads, and a row that is still open is indistinguishable from
one somebody is still worried about.

Two rules, applied by every detector that imports this module:

**A condition that still holds is restated, not re-raised.** The open row's `detail.last_seen`
moves forward and its report count increments, so "this has been true since Tuesday and was
still true an hour ago" is one row rather than a new one per run.

**A condition that no longer holds is resolved with evidence.** `detail.resolution` says in
words what changed, `detail.resolved_at` says when, and `detail.last_seen` says when it was
last observed true. A resolution without evidence would be a checkbox, and a checkbox on an
incident is how the next one gets ignored.

The signature is the identity. Detectors that used to omit the thing that made a condition
unique -- the event's year, the event itself -- opened one row per day because yesterday's
signature never matched today's; a signature that names what the condition is *about* is what
lets `reconcile` recognise the same condition across runs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from ..core.models import Incident

# Incidents resolved this recently still show on the incident page, because the question an
# operator asks after a red row disappears is "what closed it", and a row that vanishes
# answers nothing.
RESOLVED_VISIBLE_HOURS = 24


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def kind_of(signature: str) -> str:
    """The detector family a signature belongs to: everything before the first colon."""
    return signature.split(":", 1)[0]


def _restate(incident: Incident, now: datetime | None = None,
             detail: dict | None = None) -> None:
    """Move the open row's last-seen forward. A JSON column is replaced, never mutated in
    place, because SQLAlchemy does not see an in-place change."""
    merged = dict(incident.detail or {})
    if detail:
        merged.update(detail)
    merged["last_seen"] = _now_iso(now)
    incident.detail = merged
    incident.report_count = int(incident.report_count or 1) + 1


def open_or_restate(session, *, signature: str, severity: str, summary: str,
                    detail: dict | None = None, product_slug: str | None = None,
                    halts_publication: bool = False,
                    now: datetime | None = None) -> tuple[Incident, bool]:
    """Raise a condition once and restate it while it holds.

    Returns the row and whether it was newly opened. The open row's `detail` is refreshed
    with the caller's latest reading so that the page shows what is true now rather than what
    was true the day the row opened; `first_seen` is kept from the original.
    """
    from sqlalchemy import select

    existing = session.scalar(select(Incident).where(
        Incident.signature == signature, Incident.resolved == False))  # noqa: E712
    if existing is not None:
        _restate(existing, now, detail)
        return existing, False
    stamped = dict(detail or {})
    stamped.setdefault("first_seen", _now_iso(now))
    stamped["last_seen"] = _now_iso(now)
    row = Incident(severity=severity, signature=signature, summary=summary[:2000],
                   product_slug=product_slug, halts_publication=halts_publication,
                   detail=stamped)
    session.add(row)
    session.flush()
    return row, True


def reconcile(session, signature_prefix: str, still_true: Callable[[Incident], bool], *,
              resolution: str | Callable[[Incident], str],
              now: datetime | None = None) -> dict:
    """Resolve every open incident under the prefix whose condition no longer holds.

    `still_true(incident)` is the detector's own current reading of that row's condition.
    Rows it says are still true have `detail.last_seen` restated; rows it says are false are
    resolved, with `resolution` (a string, or a function of the row for a per-row sentence)
    written into `detail.resolution` and the time into `detail.resolved_at`.

    Returns the signatures it resolved and the ones it left open, so a handler can put both
    in its audit record: a reconciliation that reports nothing is one nobody can check.
    """
    from sqlalchemy import select

    # LIKE narrows in SQL; `startswith` makes it exact, because `_` and `%` in a prefix
    # ("seasonal.at_risk:") are LIKE wildcards and would otherwise match their neighbours.
    rows = [row for row in session.scalars(select(Incident).where(
        Incident.signature.like(f"{signature_prefix}%"),
        Incident.resolved == False))  # noqa: E712
        if row.signature.startswith(signature_prefix)]
    resolved, kept = [], []
    for row in rows:
        if still_true(row):
            _restate(row, now)
            kept.append(row.signature)
            continue
        text = resolution(row) if callable(resolution) else resolution
        if not str(text or "").strip():
            raise ValueError(
                f"refusing to resolve {row.signature!r} without a resolution: a closed "
                f"incident that does not say what closed it is a checkbox")
        merged = dict(row.detail or {})
        merged["resolution"] = str(text)
        merged["resolved_at"] = _now_iso(now)
        merged.setdefault("last_seen", merged.get("first_seen") or row.at.isoformat())
        row.detail = merged
        row.resolved = True
        resolved.append(row.signature)
    return {"prefix": signature_prefix, "resolved": resolved, "still_open": kept}


def resolve_signatures(session, signatures: Iterable[str], *, resolution: str,
                       now: datetime | None = None) -> list[str]:
    """Resolve specific open rows with one stated reason. A convenience over `reconcile` for
    the case where the detector already knows exactly which rows stopped being true."""
    from sqlalchemy import select

    wanted = set(signatures)
    if not wanted:
        return []
    if not str(resolution or "").strip():
        raise ValueError("refusing to resolve without a resolution")
    # Only the named rows are touched. Going through `reconcile` with an empty prefix would
    # restate every other open incident in the table as a side effect.
    resolved = []
    for row in session.scalars(select(Incident).where(
            Incident.signature.in_(sorted(wanted)),
            Incident.resolved == False)):  # noqa: E712
        merged = dict(row.detail or {})
        merged["resolution"] = str(resolution)
        merged["resolved_at"] = _now_iso(now)
        merged.setdefault("last_seen", merged.get("first_seen") or row.at.isoformat())
        row.detail = merged
        row.resolved = True
        resolved.append(row.signature)
    return resolved


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _row(incident: Incident) -> dict:
    detail = incident.detail or {}
    return {
        "id": incident.id,
        "signature": incident.signature,
        "kind": kind_of(incident.signature),
        "severity": incident.severity,
        "product_slug": incident.product_slug,
        "summary": incident.summary,
        "halts_publication": bool(incident.halts_publication),
        "report_count": int(incident.report_count or 1),
        "opened_at": _aware(incident.at).isoformat(),
        "first_seen": detail.get("first_seen"),
        "last_seen": detail.get("last_seen"),
        "resolved": bool(incident.resolved),
        "resolved_at": detail.get("resolved_at"),
        "resolution": detail.get("resolution"),
    }


def snapshot(session, *, now: datetime | None = None,
             resolved_within_hours: int = RESOLVED_VISIBLE_HOURS) -> dict:
    """Open incidents and recently resolved ones, grouped by detector family.

    Resolved rows are selected by `detail.resolved_at`, which only this module writes; a row
    closed by hand or by older code that set `resolved` without saying why has no timestamp
    and is listed under `resolved_without_evidence` so the omission is visible rather than
    hidden by a filter.
    """
    from sqlalchemy import select

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=resolved_within_hours)

    open_rows = [_row(i) for i in session.scalars(
        select(Incident).where(Incident.resolved == False)  # noqa: E712
        .order_by(Incident.severity, Incident.at.desc()))]
    # The resolved set is bounded by the row's own `at` first, in SQL, so this never walks
    # the whole history: a row resolved in the last day was opened at most however long the
    # longest-lived condition ran, and a generous SQL bound keeps the Python filter small.
    candidates = list(session.scalars(
        select(Incident).where(Incident.resolved == True)  # noqa: E712
        .order_by(Incident.id.desc()).limit(500)))
    recently, without_evidence = [], 0
    for incident in candidates:
        stamp = (incident.detail or {}).get("resolved_at")
        if not stamp:
            without_evidence += 1
            continue
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            without_evidence += 1
            continue
        if _aware(when) >= since:
            recently.append(_row(incident))

    by_kind: dict[str, dict] = {}
    for row in open_rows:
        by_kind.setdefault(row["kind"], {"open": [], "resolved": []})["open"].append(row)
    for row in recently:
        by_kind.setdefault(row["kind"], {"open": [], "resolved": []})["resolved"].append(row)

    return {
        "as_of": now.isoformat(),
        "open_total": len(open_rows),
        "resolved_last_hours": resolved_within_hours,
        "resolved_recently_total": len(recently),
        "resolved_without_evidence_in_sample": without_evidence,
        "by_kind": {kind: by_kind[kind] for kind in sorted(by_kind)},
        "note": ("An incident closes when its condition stops holding and says what closed "
                 "it (detail.resolution, detail.resolved_at). A row that only says "
                 "'resolved' is counted under resolved_without_evidence rather than shown "
                 "as closed with a reason it does not have."),
    }
