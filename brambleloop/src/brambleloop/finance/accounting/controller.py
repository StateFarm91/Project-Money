"""The Accountant agent: a senior controller's cycle, in code (F-901).

Standards it holds, each enforced by the module named:

* **Evidence first** -- every number comes from a source row through a posting rule
  (`posting_rules`); nothing is typed into the journal.
* **Conservative** -- modelled is labelled modelled, unknown stays unknown (`views`,
  `health`); a reserve is never counted as ours (`cash`).
* **Reconciled** -- statements are matched, duplicates refused, differences become
  exceptions (`reconciliation`), and the journal is compared with the books every cycle.
* **Audit-ready** -- an append-only, sealed journal with reversing corrections (`ledger`);
  month-end close with locks (`close`); a handoff pack a human can read (`handoff`).
* **Explicit about unknowns** -- the owner's Money view says UNKNOWN with the reason
  (`dashboard`).
* **Within authority** -- it cannot file, pay, move money, borrow or sign (`guardrails`);
  it challenges spend but never approves it on budget alone (`policy`).

`run_cycle(db)` is the handler an orchestrator calls (see `dashboard.next_work`). It is
idempotent: run twice, it posts nothing new the second time.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from .schema import ensure

CYCLE_KIND = "finance.accounting.cycle"
PERSONA = {
    "role": "Accountant / senior controller",
    "principles": ["evidence first", "conservative", "reconciled", "audit-ready",
                   "explicit about unknowns", "never exceeds authority"],
    "may": ["post derived journal entries", "reconcile statements", "open exceptions",
            "detect anomalies", "run and lock month-end close when every check passes",
            "challenge and block spend proposals", "prepare tax and handoff packs"],
    "may_not": ["file taxes", "move or pay money", "change bank details", "borrow",
                "sign contracts", "make regulated professional representations",
                "approve spend on budget availability alone"],
}


def run_cycle(db, *, now: datetime | None = None) -> dict:
    from . import anomalies, posting_rules, reconciliation
    from . import close as close_mod
    from ...core.models import OperatingReading

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    posted = posting_rules.post_all(db, now=now)
    matched = reconciliation.match(db, now=now)
    posted_after_match = posting_rules.post_all(db, now=now)
    found = anomalies.detect(db, now=now)
    st = close_mod.status(db, now=now)
    # The cycle has just matched, posted and detected: the checklist need not refresh again.
    cl = close_mod.checklist(db, st["previous_period"], now=now, refresh=False) \
        if not st["previous_period_locked"] else None
    from .ledger import record_anchor

    anchor = record_anchor(db, now=now)
    report = {"at": now.isoformat(), "posting": posted, "matching": matched,
              "posting_after_match": posted_after_match,
              "anomalies": {"findings": len(found["findings"]), "opened": found["opened"]},
              "close": {"period": st["previous_period"],
                        "closable": cl["closable"] if cl else None,
                        "summary": cl["owner_summary"] if cl else "already locked"},
              "chain_anchor": anchor}
    with db.session() as s:
        key = now.date().isoformat()
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == CYCLE_KIND,
                                                      OperatingReading.period_key == key))
        if row is None:
            s.add(OperatingReading(kind=CYCLE_KIND, period_key=key, at=now, payload=report))
        else:
            row.payload = report
            row.at = now
    return report


def last_run(db):
    from ...core.models import OperatingReading

    db = ensure(db)
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == CYCLE_KIND)
                       .order_by(OperatingReading.at.desc()).limit(1))
        if row is None or row.at is None:
            return None
        return row.at if row.at.tzinfo else row.at.replace(tzinfo=timezone.utc)
