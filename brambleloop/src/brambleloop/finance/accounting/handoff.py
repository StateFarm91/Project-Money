"""Human accountant handoff: a self-explanatory export pack (F-916).

`export(db, out_dir, spec)` writes plain CSV/JSON/TXT that a bookkeeper can open without
knowing anything about Brambleloop: the chart of accounts, the full journal with source
references, the trial balance, open and resolved exceptions, statement lines, the tax pack
summary, a notes file explaining the bases and conventions, the questions list, and a
manifest with a SHA-256 for every file. `pack(db, spec)` returns the same content as JSON
without writing files.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from . import accounts as A
from .ledger import to_cad
from .models import AcctJournalEntry, AcctPosting
from .schema import ensure

NOTES = """BRAMBLELOOP STUDIO -- ACCOUNTING HANDOFF NOTES

What the business is: a one-person Canadian publisher of digital crochet patterns sold as
downloads on Etsy. Reporting currency CAD. Original currency is kept on every sale line.

How the books are kept: double-entry, append-only. Every journal entry cites the source row
it came from (source_table / source_id / source_ref). Nothing is edited after posting; a
correction appears as a REVERSAL entry (kind=reversal, reverses_id=<original>) followed by
a new version of the original (entry_key ...:v2). Locked months never change; a late
correction is booked in the next open month and says so in its memo.

Basis labels on every line:
  measured   -- read from a source document (Etsy receipt, Etsy ledger with owner-verified
                mapping, provider bill, bank statement)
  modelled   -- calculated from a published fee schedule or an assumed FX rate, NOT charged
  partial    -- some components read from Etsy's ledger, the rest modelled
  unverified -- read from Etsy's ledger under a type/unit mapping the owner has not verified
  unknown    -- the source did not say
Do not file a modelled, partial, unverified or unknown amount as if it were measured.

Accounts to note:
  1100 Etsy payment account -- a receivable (Etsy holds proceeds until payout), not cash.
  2000 Owner-funded spend payable -- operating costs paid on the owner's card.
  2050 Accrued listing-fee exposure -- modelled; replaced when Etsy's ledger shows the fee.
  No GST/HST liability is booked: the treatment is one of the questions in questions.txt.

UNKNOWN is not zero: where a source is disconnected the figure is blank, never 0.00.
Brambleloop's software cannot file returns, move money, change bank details, borrow or
sign contracts. This pack is preparation for a professional's review.
"""


def _csv(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def pack(db, spec: str, *, now: datetime | None = None) -> dict:
    from . import exceptions as X
    from . import reconciliation, tax_pack, views

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    tp = tax_pack.pack(db, spec, now=now)
    journal = []
    with db.session() as s:
        for e, p in s.execute(select(AcctJournalEntry, AcctPosting)
                              .join(AcctPosting, AcctPosting.entry_id == AcctJournalEntry.id)
                              .where(AcctJournalEntry.period.in_(tp["periods"]))
                              .order_by(AcctJournalEntry.id, AcctPosting.line)):
            journal.append({"entry_id": e.id, "entry_key": e.entry_key, "date":
                            e.at.date().isoformat(), "period": e.period, "kind": e.kind,
                            "reverses_id": e.reverses_id or "", "account": p.account,
                            "account_name": A.BY_CODE[p.account].name,
                            "debit_cad": to_cad(p.debit_micros, 6),
                            "credit_cad": to_cad(p.credit_micros, 6), "basis": p.basis,
                            "currency": p.currency, "amount_original": p.amount_original,
                            "source_table": e.source_table, "source_id": e.source_id,
                            "source_ref": e.source_ref, "product": e.product_slug,
                            "memo": e.memo, "hash": e.hash})
    tbs = {p: views.trial_balance(db, period=p) for p in tp["periods"]}
    exc = X.listing(db, open_only=False)
    files = {
        "chart_of_accounts.csv": _csv(A.chart(), ["code", "name", "type", "statement",
                                                  "cash", "note"]),
        "journal.csv": _csv(journal, list(journal[0]) if journal else
                            ["entry_id", "entry_key", "date", "account", "debit_cad",
                             "credit_cad", "basis", "source_table", "source_id"]),
        "trial_balance.csv": _csv([{"period": p, **r} for p, tb in tbs.items()
                                   for r in tb["rows"]],
                                  ["period", "account", "name", "type", "debit_cad",
                                   "credit_cad"]),
        "exceptions.csv": _csv(exc, ["id", "key", "kind", "severity", "period", "summary",
                                     "resolved", "resolution", "first_seen"]),
        "statement_lines.csv": _csv(reconciliation.statement_lines(db),
                                    ["id", "source", "external_id", "at", "kind",
                                     "reference", "amount_cad", "state", "matched_to",
                                     "duplicate_of"]),
        "tax_summary.json": json.dumps({k: v for k, v in tp.items() if k != "evidence_rows"},
                                       indent=2, default=str),
        "notes.txt": NOTES,
        "questions.txt": "\n\n".join(f"{i + 1}. {q}"
                                     for i, q in enumerate(tp["questions_for_accountant"])),
    }
    manifest = {name: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()}
    return {"spec": spec, "generated_at": now.isoformat(), "files": files,
            "manifest": manifest, "open_exceptions": [x for x in exc if not x["resolved"]],
            "status": tp["status"]}


def export(db, out_dir: str | Path, spec: str, *, now: datetime | None = None) -> dict:
    p = pack(db, spec, now=now)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, body in p["files"].items():
        (out / name).write_bytes(body.encode())  # hashes are of these bytes
    (out / "manifest.json").write_text(json.dumps(
        {"spec": spec, "generated_at": p["generated_at"], "sha256": p["manifest"]},
        indent=2))
    return {"dir": str(out), "files": sorted(list(p["files"]) + ["manifest.json"]),
            "manifest": p["manifest"], "open_exceptions": len(p["open_exceptions"])}
