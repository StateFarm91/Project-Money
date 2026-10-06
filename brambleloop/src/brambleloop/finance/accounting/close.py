"""Month-end close: a repeatable checklist and a period lock (F-910).

`checklist(db, period)` runs every step and says, per step, `pass`, `warn` or `block`.
`lock_period` writes the lock only when nothing blocks; the lock records the trial balance
hash so the closed figures can be re-verified later. There is no unlock: after a period is
locked, a correction is booked in the first open period as a labelled late adjustment
(`ledger.post_in`), so a closed month's figures never move.

Blocking steps: posting, statement matching and anomaly detection ran just before the
checklist (`refresh`, audit H1); the month has ended; the order source is measured *and
fresh* (STALE blocks, audit M4); every statement line dated in the period is matched;
every source row is posted; the journal chain verifies; the trial balance
balances; no held/unreconciled orders, unmatched statement lines, duplicates or anomalies
remain open for the period. Warnings (closable, but said in the owner summary): modelled or
unverified fees, operating costs of non-measured basis, no bank source (cash basis cannot
be reconciled).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select

from . import exceptions as X
from . import health as H
from .ledger import period_of, verify_chain
from .models import AcctException, AcctPeriodLock, AcctStatementLine
from .schema import ensure


class CloseRefused(RuntimeError):
    pass


def _tb_hash(tb: dict) -> str:
    return hashlib.sha256(json.dumps(tb["rows"], sort_keys=True).encode()).hexdigest()


def _period_bounds(period: str) -> tuple[datetime, datetime]:
    y, m = (int(x) for x in period.split("-"))
    return (datetime(y, m, 1, tzinfo=timezone.utc),
            datetime(y + (m == 12), (m % 12) + 1, 1, tzinfo=timezone.utc))


def _open_statement_lines(s, period: str) -> list:
    """Statement lines dated in `period` that are not matched (and not a refused duplicate)."""
    start, end = _period_bounds(period)
    return list(s.scalars(select(AcctStatementLine).where(
        AcctStatementLine.at >= start, AcctStatementLine.at < end,
        AcctStatementLine.state.notin_(("matched", "duplicate")))))


def refresh_books(db, *, now: datetime | None = None) -> dict:
    """Bring the books to the sources' truth before a close decision (audit H1): post,
    match statements, post what matching settled, and run every anomaly detector, so an
    unmatched line or an anomaly is an open exception *before* the checklist reads them."""
    from . import anomalies, posting_rules, reconciliation

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    posted = posting_rules.post_all(db, now=now)
    matched = reconciliation.match(db, now=now)
    posted2 = posting_rules.post_all(db, now=now)
    found = anomalies.detect(db, now=now)
    return {"posting": posted, "matching": matched, "posting_after_match": posted2,
            "anomalies": {"findings": len(found["findings"]), "opened": found["opened"]}}


def checklist(db, period: str, *, now: datetime | None = None,
              refresh: bool = True) -> dict:
    """Every close step for `period`. With `refresh` (the default) the checklist first runs
    posting, statement matching and anomaly detection itself (`refresh_books`), so it never
    reads a stale exception list; `refresh=False` is for a caller that has just done so
    (the Accountant cycle). Either way, statement lines in the period that are not matched
    block, read straight from `acct_statement_lines`."""
    from . import posting_rules, views

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    steps: list[dict] = []
    refreshed = None
    if refresh:
        try:
            refreshed = refresh_books(db, now=now)
        except Exception as exc:  # noqa: BLE001 - a failed refresh blocks; never assumed clean
            refreshed = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    def step(name, outcome, why, evidence=None):
        steps.append({"step": name, "outcome": outcome, "why": why,
                      "evidence": evidence or {}})

    with db.session() as s:
        locked = s.scalar(select(AcctPeriodLock).where(AcctPeriodLock.period == period))
    if locked is not None:
        step("period_open", "block", f"{period} is already locked")
    step("period_ended", "pass" if period < period_of(now) else "block",
         f"{period} has ended" if period < period_of(now) else
         f"{period} has not ended (now {period_of(now)})")
    hl = H.reading(db, now=now)
    o = hl["sources"]["orders"]
    if refreshed is not None and "error" in refreshed:
        step("refresh", "block", "posting / matching / anomaly detection failed: "
             + refreshed["error"])
    elif refreshed is not None:
        step("refresh", "pass", "posted, matched and scanned for anomalies just now",
             refreshed)
    # A STALE order source is not a complete one (audit M4): orders read days ago say
    # nothing about the sales since, so the month cannot be closed on them.
    step("source_completeness", "pass" if o["state"] == H.MEASURED else "block",
         "order source measured" if o["state"] == H.MEASURED else
         f"order source {o['state']}: {o['why']}", o)
    b = hl["sources"]["bank"]
    step("bank_source", "pass" if b["state"] == H.MEASURED else "warn",
         "bank statements imported" if b["state"] == H.MEASURED else b["why"])
    up = posting_rules.unposted(db)
    step("ledger_posted", "pass" if not up["count"] else "block",
         "every source row is posted at its current truth" if not up["count"] else
         f"{up['count']} source row(s) not yet posted", up)
    ch = verify_chain(db)
    step("chain_integrity", "pass" if ch["ok"] else "block",
         "journal hash chain verifies" if ch["ok"] else "journal chain broken",
         {"problems": ch["problems"][:5]})
    tb = views.trial_balance(db, period=period)
    step("trial_balance", "pass" if tb["balanced"] else "block",
         f"debits {tb['total_debit_cad']} = credits {tb['total_credit_cad']}"
         if tb["balanced"] else "trial balance does not balance")
    with db.session() as s:
        lines = _open_statement_lines(s, period)
        open_lines = [{"id": l.id, "source": l.source, "kind": l.kind,
                       "external_id": l.external_id, "state": l.state} for l in lines]
    step("statement_lines", "pass" if not open_lines else "block",
         "every statement line in the period is matched" if not open_lines else
         f"{len(open_lines)} statement line(s) in {period} are not matched",
         {"lines": open_lines[:20]})
    open_x = X.listing(db, period=period)
    blocking = [x for x in open_x if not x["kind"].startswith("anomaly:")]
    anomalies = [x for x in open_x if x["kind"].startswith("anomaly:")]
    step("reconciliation_exceptions", "pass" if not blocking else "block",
         "no open reconciliation exceptions" if not blocking else
         f"{len(blocking)} open: " + "; ".join(sorted({x['kind'] for x in blocking})),
         {"keys": [x["key"] for x in blocking][:20]})
    step("anomalies", "pass" if not anomalies else "block",
         "no open anomalies" if not anomalies else
         f"{len(anomalies)} open anomaly(ies) need a resolution",
         {"keys": [x["key"] for x in anomalies][:20]})
    acc = views.accrual(db, period=period, health=hl)
    fees_est = acc["estimated_components"]["fees"]
    step("revenue_fees_refunds", "warn" if fees_est else "pass",
         ("fees include non-measured amounts " + json.dumps(fees_est)) if fees_est else
         "revenue, refunds and fees are measured", {
             "gross": acc["accrual_gross_sales_cad"], "refunds": acc["accrual_refunds_cad"],
             "fees": acc["accrual_platform_fees_cad"]})
    op_est = acc["estimated_components"]["operating"]
    step("expenses", "warn" if op_est else "pass",
         ("operating costs include non-measured amounts " + json.dumps(op_est)) if op_est
         else "operating costs are measured", acc["operating_by_basis_cad"])
    step("tax_reserve", "pass" if acc["accrual_tax_reserve_cad"] is not None else "block",
         f"sales-tax reserve CA${acc['accrual_tax_reserve_cad']} computed (management "
         f"reserve; treatment for the accountant)" if acc["accrual_tax_reserve_cad"]
         is not None else "tax reserve UNKNOWN (sales unknown)")
    blocks = [x for x in steps if x["outcome"] == "block"]
    warns = [x for x in steps if x["outcome"] == "warn"]
    summary = (f"{period}: " + ("READY TO CLOSE" if not blocks else
                                f"NOT CLOSABLE ({len(blocks)} blocking step(s): "
                                + ", ".join(x['step'] for x in blocks) + ")")
               + (f"; {len(warns)} warning(s): " + ", ".join(x["step"] for x in warns)
                  if warns else "")
               + (f". Gross CA${acc['accrual_gross_sales_cad']}, net profit after reserve "
                  f"CA${acc['accrual_net_profit_cad']} (accrual)." if
                  acc["accrual_gross_sales_cad"] is not None else
                  ". Revenue UNKNOWN."))
    return {"period": period, "closable": not blocks, "locked": locked is not None,
            "steps": steps, "owner_summary": summary,
            "trial_balance_hash": _tb_hash(tb)}


def lock_period(db, period: str, *, by: str, now: datetime | None = None) -> dict:
    """Lock `period` -- irreversibly -- only when a *refreshed* checklist passes.

    The checklist runs posting, matching and anomaly detection first (audit H1). The lock
    row is then written inside the journal lock, after re-reading in that same transaction
    that nothing moved since the checklist: no unmatched statement line, no open exception
    for the period, no unposted source row, and the trial balance hash the checklist saw.
    """
    from . import posting_rules, views
    from .ledger import locked

    cl = checklist(db, period, now=now, refresh=True)
    if not cl["closable"]:
        raise CloseRefused(cl["owner_summary"])
    db = ensure(db)
    if posting_rules.unposted(db)["count"]:
        raise CloseRefused(f"{period}: source rows changed after the checklist; re-run it")
    tb = views.trial_balance(db, period=period)
    want = _tb_hash(tb)
    if want != cl["trial_balance_hash"]:
        raise CloseRefused(f"{period}: the trial balance moved after the checklist; re-run it")
    with locked(db) as s:
        if s.scalar(select(AcctPeriodLock).where(AcctPeriodLock.period == period)):
            raise CloseRefused(f"{period} is already locked")
        if _open_statement_lines(s, period):
            raise CloseRefused(f"{period}: a statement line arrived after the checklist")
        if s.scalar(select(AcctException.id).where(
                AcctException.period == period,
                AcctException.resolved == False)) is not None:  # noqa: E712
            raise CloseRefused(f"{period}: an exception opened after the checklist")
        s.add(AcctPeriodLock(period=period, locked_by=by[:64],
                             trial_balance_hash=want,
                             checklist={"steps": cl["steps"],
                                        "owner_summary": cl["owner_summary"]},
                             locked_at=now or datetime.now(timezone.utc)))
    return {"period": period, "locked": True, "trial_balance_hash": want,
            "owner_summary": cl["owner_summary"]}


def verify_lock(db, period: str) -> dict:
    """Recompute a locked period's trial balance hash: closed figures must not have moved."""
    from . import views

    db = ensure(db)
    with db.session() as s:
        row = s.scalar(select(AcctPeriodLock).where(AcctPeriodLock.period == period))
        if row is None:
            return {"period": period, "locked": False}
        want = row.trial_balance_hash
    got = _tb_hash(views.trial_balance(db, period=period))
    return {"period": period, "locked": True, "intact": got == want}


def status(db, *, now: datetime | None = None) -> dict:
    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        locks = sorted(s.scalars(select(AcctPeriodLock.period)))
    from .ledger import next_period

    y, m = (int(x) for x in period_of(now).split("-"))
    prev = f"{y - (m == 1)}-{12 if m == 1 else m - 1:02d}"
    return {"locked_periods": locks, "last_locked": locks[-1] if locks else None,
            "previous_period": prev, "previous_period_locked": prev in locks,
            "current_period": period_of(now), "next_after_last_lock":
            next_period(locks[-1]) if locks else None}
