"""Tax-ready evidence pack: GST/HST-ready summaries for a human accountant (F-909).

**Preparation only.** Nothing here files, remits, registers or elects anything, and there is
no code path that could (F-917). The pack states what the books hold, by period, in CAD,
with every figure linked to the journal entries and source rows behind it, and lists the
questions whose answers are *jurisdictional or accounting judgments* -- the agent does not
invent the treatment.

Jurisdiction: Canada; reporting currency CAD; original currency kept per line.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from . import accounts as A
from . import health as H
from .ledger import to_cad
from .models import AcctJournalEntry, AcctPosting
from .schema import ensure

QUESTIONS = (
    "GST/HST registration: is the business registered? Confirm whether it is a small "
    "supplier (worldwide taxable supplies of CA$30,000 or less over four consecutive "
    "calendar quarters -- threshold to be confirmed by the accountant) and whether voluntary "
    "registration is advisable.",
    "Marketplace collection: for digital pattern sales through Etsy, does Etsy collect and "
    "remit GST/HST (or provincial sales tax) on the shop's behalf for Canadian buyers, and "
    "what does that mean for this shop's own reporting?",
    "Place of supply: how are digital downloads sold to buyers outside Canada (mostly USD) "
    "treated -- zero-rated exports, or outside the scope?",
    "Input tax credits: which expenses (Etsy fees, model/API and image providers billed from "
    "outside Canada, hosting) are eligible for ITCs, and is self-assessment required on "
    "imported digital services?",
    "Foreign exchange: USD sales are normalised at an ASSUMED rate until settlement "
    "statements exist. Which rate policy should the books use (transaction-date Bank of "
    "Canada rate, settlement rate)?",
    "Owner-funded spend: operating costs are paid on the owner's card and booked as a "
    "payable to the owner (account 2000). How should these be documented and repaid?",
    "Income tax: is the business a sole proprietorship (T2125) or incorporated? The 30% "
    "income-tax set-aside is a management estimate only.",
)


def _periods(spec: str) -> list[str]:
    spec = spec.strip()
    if len(spec) == 4 and spec.isdigit():
        return [f"{spec}-{m:02d}" for m in range(1, 13)]
    if "-Q" in spec.upper():
        y, q = spec.upper().split("-Q")
        q = int(q)
        return [f"{y}-{m:02d}" for m in range(3 * q - 2, 3 * q + 1)]
    return [spec]


def pack(db, spec: str, *, now: datetime | None = None) -> dict:
    """`spec` is a month (2026-10), a quarter (2026-Q4) or a year (2026)."""
    from ..books import TAX_RESERVE_RATE

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    periods = _periods(spec)
    hl = H.reading(db, now=now)
    rows = []
    totals: dict[str, int] = {}
    by_currency: dict[str, dict] = {}
    by_basis: dict[str, dict] = {}
    with db.session() as s:
        q = (select(AcctJournalEntry, AcctPosting)
             .join(AcctPosting, AcctPosting.entry_id == AcctJournalEntry.id)
             .where(AcctJournalEntry.period.in_(periods))
             .order_by(AcctJournalEntry.id, AcctPosting.line))
        for e, p in s.execute(q):
            acc = A.BY_CODE[p.account]
            if acc.statement != "income_statement":
                continue
            signed = (p.debit_micros - p.credit_micros) * (1 if acc.normal_debit else -1)
            totals[p.account] = totals.get(p.account, 0) + signed
            bb = by_basis.setdefault(acc.name, {})
            bb[p.basis] = bb.get(p.basis, 0) + signed
            if p.account == A.SALES:
                c = by_currency.setdefault(p.currency or "CAD",
                                           {"cad": 0, "original": 0.0, "lines": 0})
                c["cad"] += signed
                c["original"] += float(p.amount_original or 0.0) * (1 if signed >= 0 else -1)
                c["lines"] += 1
            rows.append({"entry_id": e.id, "entry_key": e.entry_key, "period": e.period,
                         "date": e.at.date().isoformat(), "account": p.account,
                         "account_name": acc.name, "amount_cad": to_cad(signed, 4),
                         "basis": p.basis, "currency": p.currency,
                         "amount_original": p.amount_original, "kind": e.kind,
                         "source_table": e.source_table, "source_id": e.source_id,
                         "source_ref": e.source_ref, "memo": e.memo[:120]})
    g = totals.get(A.SALES, 0)
    r = totals.get(A.REFUNDS, 0)
    d = totals.get(A.DISCOUNTS, 0)
    net = g - r - d
    sales_known = hl["sources"]["orders"]["state"] in (H.MEASURED, H.STALE) or bool(g)
    warnings = list(hl["warnings"])
    if any(k != "measured" for v in by_basis.values() for k in v):
        warnings.append("some amounts are modelled, partial, unverified or of unknown basis; "
                        "they are labelled per line and must not be filed as measured")
    return {
        "spec": spec, "periods": periods, "jurisdiction": "Canada", "currency": "CAD",
        "prepared_at": now.isoformat(),
        "status": "PREPARED ONLY -- NOT FILED. Brambleloop has no filing capability.",
        "sales_reading": H.figure_reading(hl["sources"]["orders"]["state"], bool(g)),
        "summary_cad": {
            "gross_sales": to_cad(g) if sales_known else None,
            "refunds": to_cad(r) if sales_known else None,
            "discounts": to_cad(d) if sales_known else None,
            "net_sales": to_cad(net) if sales_known else None,
            "marketplace_fees": to_cad(totals.get(A.MARKETPLACE_FEES, 0)),
            "listing_fees": to_cad(totals.get(A.LISTING_FEES, 0)),
            "operating_expenses_by_account": {A.BY_CODE[c].name: to_cad(v, 4)
                                              for c, v in totals.items()
                                              if c in A.OPERATING_ACCOUNTS and v},
        },
        "sales_by_original_currency": {k: {"cad": to_cad(v["cad"]),
                                           "original": round(v["original"], 2),
                                           "lines": v["lines"]}
                                       for k, v in by_currency.items()},
        "by_basis_cad": {k: {b: to_cad(v, 4) for b, v in m.items() if v}
                         for k, m in by_basis.items()},
        "gst_hst": {
            "sales_tax_reserve_cad": (to_cad(int(round(max(0, net) * TAX_RESERVE_RATE)))
                                      if sales_known else None),
            "reserve_rate": TAX_RESERVE_RATE,
            "collected_cad": None,
            "collected_why": ("UNKNOWN: receipts read so far carry item prices; whether "
                              "GST/HST was charged to the buyer and by whom (Etsy or the "
                              "shop) is a question below, not an assumption"),
            "itc_candidates_cad": to_cad(sum(v for c, v in totals.items()
                                             if c in A.EXPENSE_ACCOUNTS), 4),
            "itc_note": "candidates only; eligibility is the accountant's judgment",
        },
        "questions_for_accountant": list(QUESTIONS),
        "warnings": warnings,
        "evidence_rows": rows,
    }
