"""Bank / Etsy / processor reconciliation (F-904) and agreement with the books (F-902).

**Statements.** `import_statement` stores external statement lines (a bank statement, Etsy's
payment-account ledger, a processor report) exactly once each: a replay of the same
`(source, external_id)` changes nothing. A line that repeats an existing line's economics
under a *different* id -- same source, kind, reference and amount within
`DUPLICATE_WINDOW` -- is a **duplicate**: it is kept as evidence, marked `duplicate`, never
matched and never posted, and an exception is opened. That is the section 95 test: an
injected duplicate fee, payment or refund is detected and not double counted.

**Matching.** `match` pairs each line with what it should correspond to:

* bank `deposit`  <-> Etsy `payout` (equal and opposite amount within `PAYOUT_WINDOW`);
* bank `charge`   <-> a cost row carrying the same provider charge id;
* bank `owner_contribution` -- self-evidencing, matched to the owner's equity;
* Etsy `fee` / `refund` / `payment` -> the order(s) of the receipt or transaction they
  reference (or, for a listing fee, the booked listing-fee ledger row).

What does not match stays `unmatched` and opens an exception. After matching, each
receipt's charged fees and refunds are compared with what the books hold for its orders; a
difference is a `fee_mismatch` / `refund_mismatch` exception. Nothing here adjusts a figure.

**Books agreement.** `compare_with_books` reads `finance.books.Books.profit_and_loss` and
the journal's accrual view over the same window and explains every difference. Where they
differ, **the ledger wins** (duplicates, unreconciled orders and the books' discount
double-subtraction are the known causes); the comparison names the cause per metric.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from . import exceptions as X
from .ledger import period_of, to_cad, to_micros
from .models import AcctStatementLine
from .schema import ensure

SOURCES = {"bank": ("deposit", "charge", "owner_contribution", "balance", "interest"),
           "etsy_ledger": ("payout", "fee", "refund", "payment"),
           "processor": ("payment", "fee", "refund", "payout")}
DUPLICATE_WINDOW = timedelta(days=3)
PAYOUT_WINDOW = timedelta(days=7)
TOLERANCE_MICROS = 5_000  # half a cent


class StatementRefused(ValueError):
    pass


def _aware(at):
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _cad(line: dict) -> tuple[int, float | None, str, dict]:
    currency = (line.get("currency") or "CAD").upper()
    amount = float(line["amount"])
    if currency == "CAD":
        return to_micros(amount), None, "CAD", {}
    from .. import currency as fx

    conv = fx.to_reporting(fx.Money(abs(amount), currency), fx.assumed_rate(_aware(line["at"]).date()))
    cad = conv["reporting"]["amount"] * (1 if amount >= 0 else -1)
    return to_micros(cad), amount, currency, {"fx": conv["rate"]}


def import_statement(db, source: str, lines: list[dict], *,
                     now: datetime | None = None) -> dict:
    if source not in SOURCES:
        raise StatementRefused(f"unknown statement source {source!r}; one of {sorted(SOURCES)}")
    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    out = {"imported": 0, "replayed": 0, "duplicates": [], "source": source}
    with db.session() as s:
        for raw in lines:
            ext = str(raw.get("external_id") or "").strip()
            kind = str(raw.get("kind") or "").strip().lower()
            if not ext:
                raise StatementRefused("a statement line needs its own external_id")
            if kind not in SOURCES[source]:
                raise StatementRefused(f"{source} line kind {kind!r} not in {SOURCES[source]}")
            if s.scalar(select(AcctStatementLine.id).where(
                    AcctStatementLine.source == source,
                    AcctStatementLine.external_id == ext)) is not None:
                out["replayed"] += 1
                continue
            micros, original, currency, extra = _cad(raw)
            at = _aware(raw["at"])
            ref = str(raw.get("reference") or "").strip()
            desc = str(raw.get("description") or "")
            row = AcctStatementLine(source=source, external_id=ext, at=at, kind=kind,
                                    reference=ref, amount_micros=micros, currency=currency,
                                    amount_original=original, description=desc,
                                    imported_at=now, state="unmatched",
                                    detail={**extra, "raw": {k: raw[k] for k in raw
                                                             if k != "at"}})
            twin = None
            if ref or desc:
                for c in s.scalars(select(AcctStatementLine).where(
                        AcctStatementLine.source == source, AcctStatementLine.kind == kind,
                        AcctStatementLine.amount_micros == micros,
                        AcctStatementLine.state != "duplicate")):
                    same_ref = (c.reference == ref) if ref else (c.description == desc)
                    if same_ref and abs(_aware(c.at) - at) <= DUPLICATE_WINDOW:
                        twin = c
                        break
            if twin is not None:
                row.state = "duplicate"
                row.duplicate_of = twin.id
            s.add(row)
            s.flush()
            out["imported"] += 1
            if twin is not None:
                X.open_in(s, key=f"dup:stmt:{row.id}", kind="duplicate_statement_line",
                          severity="high", period=period_of(at), now=now,
                          summary=(f"{source} {kind} {ext} ({to_cad(micros)} CAD, ref {ref or desc!r}) "
                                   f"repeats line {twin.external_id}; kept as evidence, not "
                                   f"matched or posted -- no double counting"),
                          evidence={"line": row.id, "duplicate_of": twin.id,
                                    "external_ids": [twin.external_id, ext],
                                    "amount_cad": to_cad(micros), "reference": ref})
                out["duplicates"].append(row.id)
    return out


def _orders_for(orders, ref: str) -> list:
    return [o for o in orders
            if str((o.detail or {}).get("receipt_id") or "") == ref
            or o.external_ref.rsplit(":", 1)[-1] == ref or o.external_ref == ref]


def match(db, *, now: datetime | None = None) -> dict:
    from ...core.models import CostEntry, LedgerEntry, Order
    from .posting_rules import CHARGE_ID_KEYS

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    report = {"matched": 0, "unmatched": 0, "duplicates": 0, "mismatches": 0}
    with db.session() as s:
        lines = list(s.scalars(select(AcctStatementLine).order_by(AcctStatementLine.id)))
        report["duplicates"] = sum(1 for l in lines if l.state == "duplicate")
        live = [l for l in lines if l.state != "duplicate"]
        orders = list(s.scalars(select(Order)))
        charges = {}
        for c in s.scalars(select(CostEntry)):
            d = c.detail or {}
            for k in CHARGE_ID_KEYS:
                if d.get(k):
                    charges.setdefault(str(d[k]), c.id)
        listing_rows = {e.external_id: e.id for e in s.scalars(select(LedgerEntry).where(
            LedgerEntry.source == "etsy_listing_ledger"))}
        payouts = [l for l in live if l.source in ("etsy_ledger", "processor")
                   and l.kind == "payout"]
        for l in live:
            if l.state == "matched":
                continue
            target = ""
            if l.source == "bank" and l.kind == "deposit":
                p = next((p for p in payouts if p.state == "unmatched"
                          and abs(p.amount_micros + l.amount_micros) <= TOLERANCE_MICROS
                          and abs(_aware(p.at) - _aware(l.at)) <= PAYOUT_WINDOW), None)
                if p is not None:
                    p.state, p.matched_to = "matched", f"stmt:{l.id}"
                    target = f"stmt:{p.id}"
                    report["matched"] += 1
            elif l.source == "bank" and l.kind == "owner_contribution":
                target = "equity:owner"
            elif l.source == "bank" and l.kind == "charge":
                if l.reference in charges:
                    target = f"cost_entries:{charges[l.reference]}"
            elif l.source == "bank" and l.kind == "balance":
                target = "balance:snapshot"
            elif l.kind in ("fee", "refund", "payment"):
                hit = _orders_for(orders, l.reference)
                if hit:
                    target = "orders:" + ",".join(o.external_ref for o in hit)
                elif l.external_id in listing_rows:
                    target = f"ledger:{listing_rows[l.external_id]}"
            if target:
                l.state, l.matched_to = "matched", target
                report["matched"] += 1
        for l in live:
            if l.state == "unmatched" and not (l.kind == "payout"
                                               and now - _aware(l.at) <= PAYOUT_WINDOW):
                report["unmatched"] += 1
                X.open_in(s, key=f"unmatched:stmt:{l.id}", kind="unmatched_statement_line",
                          period=period_of(l.at), now=now,
                          severity="high" if l.kind in ("deposit", "payout") else "medium",
                          summary=(f"{l.source} {l.kind} {l.external_id} "
                                   f"({to_cad(l.amount_micros)} CAD, ref {l.reference!r}) "
                                   f"matches nothing in the books"),
                          evidence={"line": l.id, "external_id": l.external_id,
                                    "amount_cad": to_cad(l.amount_micros)})
        # Per-receipt fee and refund comparison.
        by_ref: dict[tuple, int] = {}
        for l in live:
            if l.state == "matched" and l.kind in ("fee", "refund") and l.matched_to.startswith(
                    "orders:"):
                by_ref[(l.kind, l.matched_to)] = by_ref.get((l.kind, l.matched_to), 0) + \
                    abs(l.amount_micros)
        ledger_by_ref = {e.evidence_ref: e for e in s.scalars(select(LedgerEntry).where(
            LedgerEntry.category == "sale"))}
        from .. import reconcile

        for (kind, target), stmt_micros in by_ref.items():
            refs = target.split(":", 1)[1].split(",")
            group = [o for o in orders if o.external_ref in refs]
            if kind == "fee":
                if not all((o.fees_basis or "") in reconcile.LEDGER_FEE_BASES for o in group):
                    continue  # books still hold the modelled fee; nothing to compare yet
                booked = sum(to_micros((ledger_by_ref.get(o.external_ref).fees_cad
                                        if ledger_by_ref.get(o.external_ref) else o.fees_cad))
                             for o in group)
            else:
                booked = sum(to_micros(ledger_by_ref[o.external_ref].refunds_cad
                                       if o.external_ref in ledger_by_ref else 0)
                             for o in group)
            if abs(booked - stmt_micros) > TOLERANCE_MICROS:
                report["mismatches"] += 1
                X.open_in(s, key=f"{kind}_mismatch:{target}"[:200], kind=f"{kind}_mismatch",
                          period=period_of(group[0].at) if group else "", now=now,
                          severity="high",
                          summary=(f"{kind}s booked for {', '.join(refs)} are "
                                   f"{to_cad(booked)} CAD but the statement shows "
                                   f"{to_cad(stmt_micros)} CAD (non-duplicate lines)"),
                          evidence={"orders": refs, "booked_cad": to_cad(booked, 4),
                                    "statement_cad": to_cad(stmt_micros, 4)})
    return report


def statement_lines(db, *, state: str | None = None) -> list[dict]:
    db = ensure(db)
    with db.session() as s:
        q = select(AcctStatementLine).order_by(AcctStatementLine.id)
        if state:
            q = q.where(AcctStatementLine.state == state)
        return [{"id": l.id, "source": l.source, "external_id": l.external_id,
                 "at": _aware(l.at).isoformat(), "kind": l.kind, "reference": l.reference,
                 "amount_cad": to_cad(l.amount_micros, 4), "state": l.state,
                 "matched_to": l.matched_to, "duplicate_of": l.duplicate_of}
                for l in s.scalars(q)]


def import_etsy_ledger(db, entries, *, now: datetime | None = None) -> dict:
    """Etsy payment-account ledger entries (Etsy's shape) -> statement lines.

    Uses `finance.reconcile.normalise` / `classify` so the type mapping is the one the order
    fees use; unclassified entries are skipped and counted, never guessed.
    """
    from .. import reconcile

    norm = reconcile.normalise(entries)
    lines, skipped = [], 0
    for e in norm:
        kind = ("fee" if e["kind"] in reconcile.FEE_KINDS else
                "refund" if e["kind"] == "refund" else
                "payout" if e.get("ledger_type", "").lower() in ("disbursement", "payout",
                                                                  "deposit") else None)
        if kind is None:
            skipped += 1
            continue
        lines.append({"external_id": str(e["entry_id"]), "at": e.get("at") or now
                      or datetime.now(timezone.utc), "kind": kind,
                      "reference": str(e.get("reference_id") or ""),
                      # `charge` is positive for money leaving the shop's Etsy balance.
                      "amount": -float(e["charge"]),
                      "currency": e.get("currency") or "CAD",
                      "description": e.get("ledger_type", "")})
    out = import_statement(db, "etsy_ledger", lines, now=now)
    out["unclassified_skipped"] = skipped
    return out


def compare_with_books(db, *, since: datetime | None = None,
                       until: datetime | None = None) -> dict:
    """The journal vs `finance.books` over one window. The ledger wins; causes are named."""
    from ...core.models import LedgerEntry
    from ..books import Books
    from . import views
    from .models import AcctException

    db = ensure(db)
    until = until or datetime.now(timezone.utc)
    since = since or (until - timedelta(days=30))
    pl = Books(db).profit_and_loss(since=since, until=until)
    acc = views.accrual(db, since=since, until=until)
    m = acc["_micros"]
    pairs = {
        "gross_sales_cad": (pl.gross_sales_cad, m["gross"]),
        "refunds_cad": (pl.refunds_cad, m["refunds"]),
        "platform_fees_cad": (pl.platform_fees_cad, m["fees"]),
        "net_sales_cad": (pl.net_sales_cad, m["net_sales"]),
        "operating_costs_cad": (pl.operating_costs_cad, m["operating"] + m["discounts"]),
        "tax_reserve_cad": (pl.tax_reserve_cad, m["reserve"]),
    }
    metrics = {}
    for k, (books_v, ledger_m) in pairs.items():
        diff = round(float(books_v) - to_cad(ledger_m, 4), 4)
        metrics[k] = {"books": round(float(books_v), 4), "ledger": to_cad(ledger_m, 4),
                      "books_minus_ledger": diff, "agree": abs(diff) <= 0.01}
    causes = []
    with db.session() as s:
        dup_rows = [x for x in s.scalars(select(AcctException).where(
            AcctException.kind.in_(("duplicate_source_row", "unreconciled_order"))))]
        for x in dup_rows:
            ev = x.evidence or {}
            row = s.get(LedgerEntry, ev.get("row")) if ev.get("row") else None
            if x.key.startswith("dup:cost:"):
                continue  # books sum cost rows too; listed below if amounts differ
            if row is not None and since <= _aware(row.at) <= _aware(until):
                causes.append({"cause": x.kind, "ledger_row": row.id,
                               "gross_cad": row.gross_cad, "fees_cad": row.fees_cad,
                               "refunds_cad": row.refunds_cad,
                               "why": ("the books sum this row; the ledger refuses it ("
                                       + x.summary + ")")})
        cost_dups = [x for x in dup_rows if x.key.startswith("dup:cost:")]
        for x in cost_dups:
            causes.append({"cause": "duplicate_cost_charge", "cost_row": x.evidence.get("row"),
                           "amount_cad": x.evidence.get("amount_cad"),
                           "why": "the books sum every cost row; the ledger posts a "
                                  "provider charge id once"})
    if m["discounts"]:
        causes.append({"cause": "books_discount_double_subtraction",
                       "why": ("finance.books subtracts a discount row from net sales AND "
                               "counts it in operating costs; the ledger books it once, as "
                               "contra-revenue (4200). FLAGGED for books.py")})
    agree = all(v["agree"] for v in metrics.values())
    return {"since": since.isoformat(), "until": until.isoformat(), "agree": agree,
            "metrics": metrics, "explained_by": causes,
            "verdict": ("books and ledger agree" if agree else
                        "they differ; the LEDGER is the source of truth and books.py is "
                        "flagged for the causes listed"),
            "books_sales_reading": pl.sales_reading,
            "ledger_sales_reading": acc["sales_reading"]}
