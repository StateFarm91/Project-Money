"""The double-entry journal (F-903): balanced, sealed, append-only, period-aware.

Rules enforced here, in code:

1. **Balanced.** Every entry has at least two lines, every line is one-sided and positive,
   every account is in the chart, and total debits equal total credits *exactly* (integer
   micro-dollars). An unbalanced entry is refused before anything is written.
2. **Immutable.** No function here updates or deletes a posted entry; the ORM listeners in
   `models` refuse it, and `verify_chain` detects a raw-SQL edit by recomputing the seal.
3. **Corrections reverse.** `reverse(entry)` writes the mirror image of an entry, linked by
   `reverses_id`. A source row that changes is corrected by reversal + a new version
   (`posting_rules`), so the history of every number is visible (F-915).
4. **Period integrity.** An entry whose business date falls in a locked period is booked in
   the first open period after it, as a labelled late adjustment; a locked period's figures
   never move (F-910).
5. **Idempotent.** `entry_key` is unique; posting the same key twice returns the first.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from . import accounts
from .models import MICRO, AcctJournalEntry, AcctPeriodLock, AcctPosting
from .schema import ensure

GENESIS = "0" * 64
BASES = ("measured", "modelled", "partial", "unverified", "unknown")


class LedgerRefused(ValueError):
    """An entry that would break double-entry, the chart or period integrity."""


def to_micros(cad: float | int | None) -> int:
    return int(round(float(cad or 0.0) * MICRO))


def to_cad(micros: int, places: int = 2) -> float:
    return round(micros / MICRO, places)


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def period_of(at: datetime) -> str:
    return _aware(at).strftime("%Y-%m")


def next_period(period: str) -> str:
    y, m = (int(x) for x in period.split("-"))
    return f"{y + (m == 12)}-{(m % 12) + 1:02d}"


@contextmanager
def locked(db):
    """Serialise journal writes (the hash chain needs a single predecessor)."""
    from .schema import _SessionDB

    with db.session() as s:
        dialect = s.bind.dialect.name if s.bind is not None else ""
        if isinstance(db, _SessionDB):
            pass  # a caller-owned session: its transaction is the caller's to serialise
        elif dialect == "sqlite":
            s.execute(text("BEGIN IMMEDIATE"))
        elif dialect == "postgresql":
            s.execute(text("SELECT pg_advisory_xact_lock(734543611)"))
        yield s


def locked_periods(session) -> set[str]:
    return set(session.scalars(select(AcctPeriodLock.period)))


def booking_period(session, at: datetime, locks: set[str] | None = None) -> str:
    locks = locked_periods(session) if locks is None else locks
    p = period_of(at)
    while p in locks:
        p = next_period(p)
    return p


def _canon(entry: dict, lines: list[dict], prev_hash: str) -> str:
    body = {k: entry.get(k) for k in ("entry_key", "at", "period", "rule", "source_key",
                                      "source_table", "source_id", "source_ref",
                                      "fingerprint", "kind", "reverses_key", "memo")}
    body["lines"] = [[l["account"], int(l.get("debit_micros", 0)),
                      int(l.get("credit_micros", 0)), l.get("basis", "unknown")]
                     for l in lines]
    body["prev"] = prev_hash
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str)
                          .encode()).hexdigest()


def validate(lines: list[dict]) -> None:
    if len(lines) < 2:
        raise LedgerRefused("a journal entry needs at least two lines")
    dr = cr = 0
    for l in lines:
        if l["account"] not in accounts.BY_CODE:
            raise LedgerRefused(f"account {l['account']!r} is not in the chart of accounts")
        d, c = int(l.get("debit_micros", 0)), int(l.get("credit_micros", 0))
        if d < 0 or c < 0 or (d and c) or not (d or c):
            raise LedgerRefused(f"line {l}: exactly one positive side per line")
        if l.get("basis", "unknown") not in BASES:
            raise LedgerRefused(f"basis {l.get('basis')!r} is not one of {BASES}")
        dr += d
        cr += c
    if dr != cr:
        raise LedgerRefused(f"unbalanced entry: debits {dr} != credits {cr} (micro-CAD)")


def _last_hash(session) -> str:
    row = session.scalar(select(AcctJournalEntry).order_by(AcctJournalEntry.id.desc())
                         .limit(1))
    return row.hash if row is not None else GENESIS


def post_in(session, entry: dict, lines: list[dict], *, locks: set[str] | None = None
            ) -> AcctJournalEntry:
    """Write one balanced entry inside a session that holds the journal lock."""
    validate(lines)
    existing = session.scalar(select(AcctJournalEntry).where(
        AcctJournalEntry.entry_key == entry["entry_key"]))
    if existing is not None:
        return existing
    at = _aware(entry["at"])
    period = booking_period(session, at, locks)
    src_period = period_of(at)
    memo = entry.get("memo", "")
    if period != src_period:
        memo = (f"LATE ADJUSTMENT to locked period {src_period}, booked in {period}. "
                + memo)
    prev = _last_hash(session)
    rec = {**entry, "at": at.isoformat(), "period": period, "memo": memo,
           "source_id": str(entry.get("source_id", "")),
           "source_table": entry.get("source_table", ""),
           "source_ref": entry.get("source_ref", "") or "",
           "fingerprint": entry.get("fingerprint", ""), "kind": entry.get("kind", "original"),
           "reverses_key": entry.get("reverses_key", "")}
    digest = _canon(rec, lines, prev)
    row = AcctJournalEntry(
        entry_key=entry["entry_key"], at=at, period=period, source_period=src_period,
        rule=entry["rule"], source_key=entry["source_key"],
        source_table=entry.get("source_table", ""), source_id=str(entry.get("source_id", "")),
        source_ref=entry.get("source_ref", "") or "", fingerprint=entry.get("fingerprint", ""),
        kind=entry.get("kind", "original"), reverses_id=entry.get("reverses_id"),
        memo=memo, product_slug=entry.get("product_slug", "") or "",
        release=entry.get("release", "") or "", family=entry.get("family", "") or "",
        channel=entry.get("channel", "") or "", department=entry.get("department", "") or "",
        detail={**(entry.get("detail") or {}), "reverses_key": rec["reverses_key"]},
        prev_hash=prev, hash=digest)
    session.add(row)
    session.flush()
    for i, l in enumerate(lines):
        session.add(AcctPosting(
            entry_id=row.id, line=i, account=l["account"],
            debit_micros=int(l.get("debit_micros", 0)),
            credit_micros=int(l.get("credit_micros", 0)), basis=l.get("basis", "unknown"),
            currency=l.get("currency", "CAD") or "CAD",
            amount_original=l.get("amount_original"), memo=(l.get("memo") or "")[:200]))
    session.flush()
    return row


def post(db, entry: dict, lines: list[dict]) -> int:
    db = ensure(db)
    with locked(db) as s:
        return post_in(s, entry, lines).id


def lines_of(session, entry_id: int) -> list[AcctPosting]:
    return list(session.scalars(select(AcctPosting).where(AcctPosting.entry_id == entry_id)
                                .order_by(AcctPosting.line)))


def reverse_in(session, original: AcctJournalEntry, *, why: str,
               locks: set[str] | None = None) -> AcctJournalEntry:
    """The mirror image of `original`, linked to it. Never an edit."""
    if original.kind != "original":
        raise LedgerRefused("only an original entry can be reversed")
    already = session.scalar(select(AcctJournalEntry).where(
        AcctJournalEntry.reverses_id == original.id))
    if already is not None:
        return already
    mirror = [{"account": p.account, "debit_micros": p.credit_micros,
               "credit_micros": p.debit_micros, "basis": p.basis, "currency": p.currency,
               "amount_original": (-p.amount_original if p.amount_original else None),
               "memo": f"reversal of line {p.line}"}
              for p in lines_of(session, original.id)]
    return post_in(session, {
        "entry_key": f"{original.entry_key}:rev", "at": original.at, "rule": original.rule,
        "source_key": original.source_key, "source_table": original.source_table,
        "source_id": original.source_id, "source_ref": original.source_ref,
        "fingerprint": original.fingerprint, "kind": "reversal",
        "reverses_id": original.id, "reverses_key": original.entry_key,
        "memo": f"Reverses entry {original.id} ({original.entry_key}): {why}",
        "product_slug": original.product_slug, "release": original.release,
        "family": original.family, "channel": original.channel,
        "department": original.department, "detail": {"why": why}}, mirror, locks=locks)


def active_entries(session, source_key: str) -> list[AcctJournalEntry]:
    """Originals for `source_key` that have not been reversed."""
    rows = list(session.scalars(select(AcctJournalEntry).where(
        AcctJournalEntry.source_key == source_key).order_by(AcctJournalEntry.id)))
    reversed_ids = {r.reverses_id for r in rows if r.kind == "reversal"}
    return [r for r in rows if r.kind == "original" and r.id not in reversed_ids]


def verify_chain(db) -> dict:
    """Recompute every seal and every balance. A raw-SQL edit or delete breaks it."""
    db = ensure(db)
    problems: list[dict] = []
    n = 0
    with db.session() as s:
        prev = GENESIS
        entries = list(s.scalars(select(AcctJournalEntry).order_by(AcctJournalEntry.id)))
        by_entry: dict[int, list] = {}
        for p in s.scalars(select(AcctPosting).order_by(AcctPosting.entry_id,
                                                        AcctPosting.line)):
            by_entry.setdefault(p.entry_id, []).append(p)
        for e in entries:
            n += 1
            lines = [{"account": p.account, "debit_micros": p.debit_micros,
                      "credit_micros": p.credit_micros, "basis": p.basis}
                     for p in by_entry.get(e.id, [])]
            rec = {"entry_key": e.entry_key, "at": _aware(e.at).isoformat(),
                   "period": e.period, "rule": e.rule, "source_key": e.source_key,
                   "source_table": e.source_table, "source_id": e.source_id,
                   "source_ref": e.source_ref, "fingerprint": e.fingerprint, "kind": e.kind,
                   "reverses_key": (e.detail or {}).get("reverses_key", ""), "memo": e.memo}
            if e.prev_hash != prev:
                problems.append({"entry_id": e.id, "problem": "chain link broken "
                                 "(an entry was deleted or reordered)"})
            if _canon(rec, lines, e.prev_hash) != e.hash:
                problems.append({"entry_id": e.id, "problem": "seal mismatch (entry or "
                                 "its postings were edited after posting)"})
            dr = sum(l["debit_micros"] for l in lines)
            cr = sum(l["credit_micros"] for l in lines)
            if dr != cr or len(lines) < 2:
                problems.append({"entry_id": e.id, "problem": f"unbalanced {dr} != {cr}"})
            prev = e.hash
    return {"ok": not problems, "entries": n, "problems": problems,
            "head": prev}


def balances(session, *, period: str | None = None, periods: set[str] | None = None,
             since: datetime | None = None, until: datetime | None = None,
             upto_period: str | None = None) -> dict[str, dict]:
    """Per-account debit/credit micros, optionally filtered by booking period or date."""
    q = (select(AcctPosting.account, AcctPosting.basis,
                func.sum(AcctPosting.debit_micros), func.sum(AcctPosting.credit_micros))
         .join(AcctJournalEntry, AcctJournalEntry.id == AcctPosting.entry_id))
    if period is not None:
        q = q.where(AcctJournalEntry.period == period)
    if periods is not None:
        q = q.where(AcctJournalEntry.period.in_(sorted(periods)))
    if upto_period is not None:
        q = q.where(AcctJournalEntry.period <= upto_period)
    if since is not None:
        q = q.where(AcctJournalEntry.at >= since)
    if until is not None:
        q = q.where(AcctJournalEntry.at <= until)
    q = q.group_by(AcctPosting.account, AcctPosting.basis)
    out: dict[str, dict] = {}
    for account, basis, dr, cr in session.execute(q):
        a = out.setdefault(account, {"debit": 0, "credit": 0, "by_basis": {}})
        a["debit"] += int(dr or 0)
        a["credit"] += int(cr or 0)
        b = a["by_basis"].setdefault(basis, 0)
        acc = accounts.BY_CODE[account]
        a["by_basis"][basis] = b + (int(dr or 0) - int(cr or 0)) * (1 if acc.normal_debit
                                                                    else -1)
    for code, a in out.items():
        acc = accounts.BY_CODE[code]
        a["balance"] = (a["debit"] - a["credit"]) * (1 if acc.normal_debit else -1)
    return out
