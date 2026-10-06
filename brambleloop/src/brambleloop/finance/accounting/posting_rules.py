"""Posting rules: the durable sources -> the journal, idempotently (F-902, F-903).

The journal is never typed into. `post_all` reads the rows the rest of the company already
writes and derives, for each, the entry it *should* produce:

* `ledger` rows (`commerce.orders_ingest` sales, `finance.listing_costs` Etsy listing fees)
  -> rule `ledger_row`. A sale is posted only when its order's money is in the books
  (`orders_ingest.in_books`: countable or voided). A held or unreconciled order has UNKNOWN
  revenue and is not posted; it is an exception instead. Hand-entered rows with no order are
  posted with the basis their row states.
* `cost_entries` rows (model/API, image, hosting, ads, testing, benchmark ...)
  -> rule `cost_entry`, debiting the expense account for the kind and crediting the owner-
  funded payable (or the accrued listing-fee exposure for a listing-fee reservation). A
  listing-fee budget mirror whose Etsy ledger row exists is skipped: the ledger row is the
  charge, the mirror is a budget copy of it (the same rule `Books` applies).
* matched `acct_statement_lines` bank lines -> rule `bank_line` (payout deposits, owner
  contributions, provider charges paid from the bank).

`spend_reservations` are commitments, not expenses: they are read by `cash` as committed
spend and never posted.

**Corrections.** Each source row has a `source_key`. If its derived entry differs from the
active one (a refund arrived, a fee went from modelled to measured, a basis was revoked),
the active entry is *reversed* and a new version posted. If a row stops qualifying (an
order became held), its entry is reversed. If a row disappears, nothing is reversed
silently: an exception `source_row_missing` is opened.

**Duplicates are refused, not summed.** A second `ledger` row for the same external object,
or a second cost row carrying the same provider charge id, is not posted; an exception
`duplicate_source_row` is opened with both rows as evidence.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select

from . import accounts as A
from . import exceptions as X
from .ledger import active_entries, locked, locked_periods, period_of, post_in, reverse_in, to_micros
from .models import AcctJournalEntry, AcctStatementLine
from .schema import ensure

RULE_LEDGER, RULE_COST, RULE_BANK = "ledger_row", "cost_entry", "bank_line"
CHARGE_ID_KEYS = ("charge_id", "invoice_id", "provider_charge_id", "external_id",
                  "request_id")


def _basis(value: str | None) -> str:
    v = (value or "unknown").strip().lower()
    if v == "unverified_mapping":
        return "unverified"
    return v if v in ("measured", "modelled", "partial", "unverified", "unknown") else "unknown"


def _fp(lines: list[dict], dims: dict) -> str:
    return hashlib.sha256(json.dumps({"l": lines, "d": dims}, sort_keys=True,
                                     default=str).encode()).hexdigest()


def _pair(dr: str, cr: str, micros: int, basis: str, memo: str, *, currency: str = "CAD",
          original: float | None = None) -> list[dict]:
    if micros == 0:
        return []
    if micros < 0:
        dr, cr, micros = cr, dr, -micros
    return [{"account": dr, "debit_micros": micros, "credit_micros": 0, "basis": basis,
             "memo": memo, "currency": currency, "amount_original": original},
            {"account": cr, "debit_micros": 0, "credit_micros": micros, "basis": basis,
             "memo": memo, "currency": currency, "amount_original": original}]


# ---------------------------------------------------------------------------
# Desired entries per source family


def _ledger_desired(s, held: frozenset, now: datetime) -> tuple[dict, list[dict], set]:
    """source_key -> (entry, lines) for `ledger` rows; plus duplicates and exclusions."""
    from ...commerce import orders_ingest
    from ...core.models import LedgerEntry, Order
    from ...finance.sources import channel

    desired: dict[str, tuple[dict, list[dict]]] = {}
    issues: list[dict] = []
    present: set[str] = set()
    orders = {o.external_ref: o for o in s.scalars(select(Order))}
    seen: dict[tuple, int] = {}
    for e in s.scalars(select(LedgerEntry).order_by(LedgerEntry.id)):
        key = f"ledger:{e.id}"
        present.add(key)
        ident = None
        if e.source and e.external_id:
            ident = (e.category, e.source, e.external_id)
        elif e.evidence_ref:
            ident = (e.category, "evidence", e.evidence_ref)
        if ident is not None:
            if ident in seen:
                issues.append({"kind": "duplicate_source_row", "source_key": key,
                               "key": f"dup:ledger:{e.id}",
                               "summary": (f"ledger row {e.id} repeats ledger row "
                                           f"{seen[ident]} ({ident[1]} {ident[2]}); not "
                                           f"posted, so it is not double counted"),
                               "evidence": {"row": e.id, "first_row": seen[ident],
                                            "identity": list(ident),
                                            "gross_cad": e.gross_cad, "fees_cad": e.fees_cad,
                                            "refunds_cad": e.refunds_cad,
                                            "expense_cad": e.expense_cad},
                               "period": period_of(e.at), "severity": "high"})
                continue
            seen[ident] = e.id
        order = orders.get(e.evidence_ref) or orders.get(e.external_id)
        if e.category == "sale" and (e.evidence_ref in held or e.external_id in held):
            issues.append({"kind": "held_order", "source_key": key,
                           "key": f"held:{e.evidence_ref or e.external_id}",
                           "summary": (f"sale {e.evidence_ref} is held by the order ingest "
                                       f"with UNKNOWN CAD value; not posted"),
                           "evidence": {"row": e.id, "ref": e.evidence_ref},
                           "period": period_of(e.at), "severity": "high", "exclude": True})
            continue
        if e.category == "sale" and order is not None and not orders_ingest.in_books(order, held):
            issues.append({"kind": "unreconciled_order", "source_key": key,
                           "key": f"unreconciled:{order.external_ref}",
                           "summary": (f"order {order.external_ref} is "
                                       f"{orders_ingest.standing(order, held)}: revenue is "
                                       f"UNKNOWN, so its ledger row is not posted"),
                           "evidence": {"row": e.id, "order": order.id,
                                        "standing": orders_ingest.standing(order, held)},
                           "period": period_of(e.at), "severity": "high", "exclude": True})
            continue
        gross_basis = _basis(e.basis)
        fee_basis = _basis(e.fees_basis)
        if (gross_basis == "measured" and (e.currency or "CAD").upper() != "CAD"
                and not (order is not None and order.fx_measured)):
            # The receipt's amount is measured; its CAD value used an ASSUMED rate.
            gross_basis = "modelled"
        etsy = (e.source or "").startswith("etsy") or e.category == "sale"
        lines: list[dict] = []
        lines += _pair(A.ETSY_RECEIVABLE, A.SALES, to_micros(e.gross_cad), gross_basis,
                       "gross sale", currency=e.currency, original=e.amount_original)
        lines += _pair(A.REFUNDS, A.ETSY_RECEIVABLE, to_micros(e.refunds_cad), gross_basis,
                       "refund")
        lines += _pair(A.MARKETPLACE_FEES, A.ETSY_RECEIVABLE, to_micros(e.fees_cad),
                       fee_basis, "marketplace fees")
        if e.expense_cad:
            if e.category == "discount":
                dr = A.DISCOUNTS
            elif e.classification == "listing_fee":
                dr = A.LISTING_FEES
            else:
                dr = A.OTHER_EXPENSE
            cr = A.ETSY_RECEIVABLE if etsy else A.OWNER_PAYABLE
            lines += _pair(dr, cr, to_micros(e.expense_cad), gross_basis,
                           e.classification or e.category, currency=e.currency,
                           original=e.amount_original if not e.gross_cad else None)
        if not lines:
            continue
        dims = {"product_slug": order.product_slug if order else "",
                "release": (f"{order.product_slug}@{order.version}" if order and order.version
                            else (order.product_slug if order else "")),
                "family": order.category if order else "",
                "channel": channel(order.acquisition_source) if order else "",
                "department": "commerce"}
        desired[key] = ({"rule": RULE_LEDGER, "source_key": key, "source_table": "ledger",
                         "source_id": e.id, "source_ref": e.evidence_ref or e.external_id,
                         "at": e.at, "memo": f"{e.category}: {e.description}"[:300],
                         "detail": {"category": e.category, "order_id": order.id if order
                                    else None, "reconciliation_state":
                                    e.reconciliation_state, "fees_basis": fee_basis,
                                    "gross_basis": gross_basis},
                         **dims}, lines)
    return desired, issues, present


def _cost_desired(s) -> tuple[dict, list[dict], set]:
    from ...core.models import CostEntry, LedgerEntry
    from ..listing_costs import cost_basis

    desired: dict[str, tuple[dict, list[dict]]] = {}
    issues: list[dict] = []
    present: set[str] = set()
    ledger_events = {(e.source, e.external_id) for e in s.scalars(select(LedgerEntry))
                     if e.source and e.external_id}
    seen: dict[tuple, int] = {}
    for c in s.scalars(select(CostEntry).order_by(CostEntry.id)):
        key = f"cost:{c.id}"
        present.add(key)
        detail = c.detail or {}
        if (c.kind == "etsy_listing_fee_actual" and detail.get("role") == "budget_mirror"
                and (detail.get("ledger_source"), detail.get("ledger_external_id"))
                in ledger_events):
            continue
        charge = next((str(detail[k]) for k in CHARGE_ID_KEYS if detail.get(k)), "")
        if charge:
            ident = (c.kind, c.provider or "", charge)
            if ident in seen:
                issues.append({"kind": "duplicate_source_row", "source_key": key,
                               "key": f"dup:cost:{c.id}",
                               "summary": (f"cost row {c.id} repeats provider charge "
                                           f"{charge} already booked from cost row "
                                           f"{seen[ident]}; not posted"),
                               "evidence": {"row": c.id, "first_row": seen[ident],
                                            "charge_id": charge, "amount_cad": c.amount_cad,
                                            "provider": c.provider, "kind": c.kind},
                               "period": period_of(c.at), "severity": "high"})
                continue
            seen[ident] = c.id
        basis = _basis(cost_basis(c))
        dr = A.account_for_cost_kind(c.kind)
        if c.kind == "etsy_listing_fee":
            cr = A.ACCRUED_LISTING
        elif c.kind == "etsy_listing_fee_actual":
            cr = A.ETSY_RECEIVABLE
        else:
            cr = A.OWNER_PAYABLE
        lines = _pair(dr, cr, to_micros(c.amount_cad), basis,
                      f"{c.kind} {c.provider}/{c.model}".strip()[:200])
        if not lines:
            continue
        version = str(detail.get("version") or detail.get("release") or "")
        desired[key] = ({"rule": RULE_COST, "source_key": key, "source_table": "cost_entries",
                         "source_id": c.id, "source_ref": charge or f"cost_entries:{c.id}",
                         "at": c.at,
                         "memo": f"{c.kind} by {c.agent} for {c.purpose or 'unstated purpose'}",
                         "product_slug": c.product_slug or "",
                         "release": (f"{c.product_slug}@{version}" if c.product_slug and version
                                     else c.product_slug or ""),
                         "family": "", "channel": str(detail.get("channel") or ""),
                         "department": c.department or "",
                         "detail": {"kind": c.kind, "agent": c.agent, "provider": c.provider,
                                    "model": c.model, "purpose": c.purpose,
                                    "estimated_cad": c.estimated_cad, "basis": basis,
                                    "job_id": c.job_id}}, lines)
    return desired, issues, present


def _bank_desired(s) -> tuple[dict, list[dict], set]:
    desired: dict[str, tuple[dict, list[dict]]] = {}
    present: set[str] = set()
    for l in s.scalars(select(AcctStatementLine).where(AcctStatementLine.source == "bank")
                       .order_by(AcctStatementLine.id)):
        key = f"stmt:{l.id}"
        present.add(key)
        if l.state != "matched":
            continue
        if l.kind == "deposit":
            lines = _pair(A.BANK, A.ETSY_RECEIVABLE, l.amount_micros, "measured",
                          "Etsy payout deposited")
        elif l.kind == "owner_contribution":
            lines = _pair(A.BANK, A.OWNER_EQUITY, l.amount_micros, "measured",
                          "owner contribution")
        elif l.kind == "charge":
            lines = _pair(A.OWNER_PAYABLE, A.BANK, -l.amount_micros, "measured",
                          "provider charge paid from bank")
        else:
            continue
        if not lines:
            continue
        desired[key] = ({"rule": RULE_BANK, "source_key": key,
                         "source_table": "acct_statement_lines", "source_id": l.id,
                         "source_ref": f"bank:{l.external_id}", "at": l.at,
                         "memo": f"bank {l.kind}: {l.description}"[:300],
                         "detail": {"matched_to": l.matched_to}}, lines)
    return desired, [], present


# ---------------------------------------------------------------------------


def post_all(db, *, now: datetime | None = None) -> dict:
    """Bring the journal to the sources' current truth. Idempotent."""
    from ...commerce import orders_ingest

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    held = frozenset(h["ref"] for h in orders_ingest.held(db))
    report = {"posted": 0, "reversed": 0, "unchanged": 0, "duplicates": 0,
              "excluded": 0, "missing_sources": 0, "exceptions_opened": 0}
    with locked(db) as s:
        locks = locked_periods(s)
        desired: dict = {}
        issues: list[dict] = []
        present: set[str] = set()
        for fn in (lambda: _ledger_desired(s, held, now), lambda: _cost_desired(s),
                   lambda: _bank_desired(s)):
            d, i, p = fn()
            desired.update(d)
            issues.extend(i)
            present |= p
        excluded = {i["source_key"] for i in issues}
        for i in issues:
            _, created = X.open_in(s, key=i["key"], kind=i["kind"], summary=i["summary"],
                                   evidence=i["evidence"], period=i["period"],
                                   severity=i["severity"], now=now)
            report["exceptions_opened"] += int(created)
            report["duplicates" if i["kind"] == "duplicate_source_row" else "excluded"] += 1
        # Existing source keys in the journal.
        known = {k for (k,) in s.execute(select(AcctJournalEntry.source_key).distinct())}
        for source_key in sorted(known | set(desired), key=_order_key):
            active = active_entries(s, source_key)
            want = desired.get(source_key)
            if want is None:
                if not active:
                    continue
                if source_key in excluded:
                    for a in active:
                        reverse_in(s, a, why="source row no longer qualifies (duplicate, "
                                   "held or unreconciled)", locks=locks)
                        report["reversed"] += 1
                elif source_key not in present:
                    _, created = X.open_in(
                        s, key=f"missing:{source_key}", kind="source_row_missing",
                        summary=(f"{source_key} was posted but its source row is gone; the "
                                 f"entry is kept and needs a human decision"),
                        evidence={"entries": [a.id for a in active]},
                        period=active[0].period, severity="high", now=now)
                    report["missing_sources"] += 1
                    report["exceptions_opened"] += int(created)
                else:
                    # Present but now produces no entry (e.g. amounts went to zero).
                    for a in active:
                        reverse_in(s, a, why="source row now produces no amount", locks=locks)
                        report["reversed"] += 1
                continue
            entry, lines = want
            dims = {k: entry.get(k, "") for k in ("product_slug", "release", "family",
                                                  "channel", "department")}
            canon = [[l["account"], l["debit_micros"], l["credit_micros"], l["basis"]]
                     for l in lines]
            fp = _fp(canon, {**dims, "at": entry["at"].isoformat() if entry["at"] else ""})
            if len(active) == 1 and active[0].fingerprint == fp:
                report["unchanged"] += 1
                continue
            for a in active:
                reverse_in(s, a, why="source row changed; superseded by a new version",
                           locks=locks)
                report["reversed"] += 1
            n = len([1 for _ in s.scalars(select(AcctJournalEntry.id).where(
                AcctJournalEntry.source_key == source_key,
                AcctJournalEntry.kind == "original"))]) + 1
            post_in(s, {**entry, "entry_key": f"{source_key}:v{n}", "fingerprint": fp,
                        "kind": "original"}, lines, locks=locks)
            report["posted"] += 1
    return report


def _order_key(k: str):
    fam, _, n = k.partition(":")
    return (fam, int(n) if n.isdigit() else 0)


def unposted(db) -> dict:
    """Source rows whose current truth is not yet in the journal (close check)."""
    from ...commerce import orders_ingest

    db = ensure(db)
    held = frozenset(h["ref"] for h in orders_ingest.held(db))
    now = datetime.now(timezone.utc)
    with db.session() as s:
        desired = {}
        for fn in (lambda: _ledger_desired(s, held, now), lambda: _cost_desired(s),
                   lambda: _bank_desired(s)):
            desired.update(fn()[0])
        stale = []
        for key, (entry, lines) in desired.items():
            dims = {k: entry.get(k, "") for k in ("product_slug", "release", "family",
                                                  "channel", "department")}
            canon = [[l["account"], l["debit_micros"], l["credit_micros"], l["basis"]]
                     for l in lines]
            fp = _fp(canon, {**dims, "at": entry["at"].isoformat() if entry["at"] else ""})
            active = active_entries(s, key)
            if not (len(active) == 1 and active[0].fingerprint == fp):
                stale.append(key)
    return {"count": len(stale), "source_keys": stale[:50]}
