"""Financial anomaly detection, escalated with evidence (F-911).

Each detector returns findings and opens an `acct_exceptions` row (kind `anomaly:<type>`)
so the finding survives the run, blocks the month-end close until resolved, and reaches the
owner's Money view and the Finance work queue. Detectors refuse to fire without a baseline
where a baseline is needed (the spend-spike detector is `finance.governor.anomaly`, reused).

* `duplicate_charge`      -- cost rows that look like the same provider call twice (same
  agent/provider/model/purpose/amount within a minute, no charge id to tell them apart).
  Exact duplicates (same charge id, same statement economics) are refused at posting /
  import and are already exceptions.
* `unexpected_fee_rate`   -- a ledger-read fee far from the fee schedule's model.
* `missing_deposit`       -- an Etsy payout with no bank deposit after the payout window,
  when a bank source exists.
* `refund_anomaly`        -- refunds above the paid-media alarm rate, or above the sale.
* `spend_spike`           -- `finance.governor.anomaly` says today is a spike.
* `margin_deterioration`  -- contribution margin fell by more than `MARGIN_DROP` month on
  month, with enough orders on both sides to say so.
* `reconciliation_drift`  -- the ledger and the books disagree, the journal chain does not
  verify, or the bank balance snapshot differs from account 1000.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from . import accounts as A
from . import exceptions as X
from .ledger import balances, period_of, to_cad, to_micros, verify_chain
from .models import AcctStatementLine
from .schema import ensure

DUP_WINDOW = timedelta(seconds=60)
DUP_MIN_CAD = 0.50
FEE_RATE_TOLERANCE = 0.5      # +/-50% of the modelled fee ...
FEE_RATE_FLOOR_CAD = 0.25     # ... and at least this many dollars apart
MARGIN_DROP = 0.10
MIN_ORDERS_FOR_RATES = 5


def _aware(at):
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _prev_period(p: str) -> str:
    y, m = (int(x) for x in p.split("-"))
    return f"{y - (m == 1)}-{12 if m == 1 else m - 1:02d}"


def detect(db, *, now: datetime | None = None, include_books: bool = True) -> dict:
    from ...core.models import CostEntry, LedgerEntry, Order
    from ...commerce.paid_media import REFUND_RATE_ALARM
    from ...commerce.pricing import fees as model_fees
    from .. import governor, reconcile
    from . import health as H

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    found: list[dict] = []
    hl = H.reading(db, now=now)
    with db.session() as s:
        # duplicate_charge (near duplicates without a charge id)
        costs = sorted(s.scalars(select(CostEntry).where(CostEntry.amount_cad >= DUP_MIN_CAD)),
                       key=lambda c: (_aware(c.at), c.id))
        last: dict[tuple, CostEntry] = {}
        for c in costs:
            k = (c.agent, c.provider, c.model, c.purpose, round(c.amount_cad, 6), c.kind)
            prev = last.get(k)
            if prev is not None and _aware(c.at) - _aware(prev.at) <= DUP_WINDOW:
                found.append({"type": "duplicate_charge", "key": f"anomaly:dupcharge:{c.id}",
                              "severity": "medium", "period": period_of(c.at),
                              "summary": (f"cost rows {prev.id} and {c.id} look like the "
                                          f"same {c.provider or c.kind} charge "
                                          f"(CA${c.amount_cad:.2f}) within a minute; both "
                                          f"are posted until a human confirms"),
                              "evidence": {"rows": [prev.id, c.id], "amount_cad": c.amount_cad}})
            last[k] = c
        # unexpected_fee_rate
        for o in s.scalars(select(Order)):
            if (o.fees_basis or "") not in reconcile.LEDGER_FEE_BASES or not o.price_cad:
                continue
            if o.offsite_ad_attributed:
                continue  # an Offsite Ads fee explains a higher rate
            expected = model_fees(float(o.price_cad)).total_fees
            actual = float(o.fees_cad or 0.0)
            if abs(actual - expected) > max(FEE_RATE_FLOOR_CAD, FEE_RATE_TOLERANCE * expected):
                found.append({"type": "unexpected_fee_rate",
                              "key": f"anomaly:feerate:{o.external_ref}",
                              "severity": "medium", "period": period_of(o.at),
                              "summary": (f"order {o.external_ref}: charged fees "
                                          f"CA${actual:.2f} vs modelled CA${expected:.2f} on "
                                          f"a CA${o.price_cad:.2f} sale"),
                              "evidence": {"order": o.external_ref, "fees_cad": actual,
                                           "modelled_cad": expected, "price_cad": o.price_cad,
                                           "fees_basis": o.fees_basis}})
        # missing_deposit
        if hl["cash_known"]:
            from .reconciliation import PAYOUT_WINDOW

            for p in s.scalars(select(AcctStatementLine).where(
                    AcctStatementLine.kind == "payout",
                    AcctStatementLine.state == "unmatched")):
                if now - _aware(p.at) > PAYOUT_WINDOW:
                    found.append({"type": "missing_deposit", "key": f"anomaly:deposit:{p.id}",
                                  "severity": "high", "period": period_of(p.at),
                                  "summary": (f"Etsy payout {p.external_id} of "
                                              f"CA${-to_cad(p.amount_micros):.2f} has no bank "
                                              f"deposit after {PAYOUT_WINDOW.days} days"),
                                  "evidence": {"line": p.id, "external_id": p.external_id}})
        # refund_anomaly
        by_period: dict[str, dict] = {}
        for e in s.scalars(select(LedgerEntry).where(LedgerEntry.category == "sale")):
            g = by_period.setdefault(period_of(e.at), {"gross": 0.0, "refunds": 0.0, "n": 0})
            g["gross"] += e.gross_cad
            g["refunds"] += e.refunds_cad
            g["n"] += 1
            if e.refunds_cad > e.gross_cad + 0.005:
                found.append({"type": "refund_anomaly", "key": f"anomaly:refund_over:{e.id}",
                              "severity": "high", "period": period_of(e.at),
                              "summary": (f"ledger row {e.id}: refund CA${e.refunds_cad:.2f} "
                                          f"exceeds the sale CA${e.gross_cad:.2f}"),
                              "evidence": {"row": e.id}})
        for p, g in by_period.items():
            if g["n"] >= MIN_ORDERS_FOR_RATES and g["gross"] > 0 and \
                    g["refunds"] / g["gross"] > REFUND_RATE_ALARM:
                found.append({"type": "refund_anomaly", "key": f"anomaly:refund_rate:{p}",
                              "severity": "high", "period": p,
                              "summary": (f"{p}: refunds are {g['refunds'] / g['gross']:.0%} "
                                          f"of gross over {g['n']} sales (alarm "
                                          f"{REFUND_RATE_ALARM:.0%})"),
                              "evidence": {k: round(v, 2) for k, v in g.items()}})
        # margin_deterioration
        cur = period_of(now)
        prev = _prev_period(cur)

        def margin(period):
            b = balances(s, period=period)
            g = (b.get(A.SALES) or {}).get("balance", 0)
            if g <= 0:
                return None
            net = g - (b.get(A.REFUNDS) or {}).get("balance", 0) - \
                (b.get(A.MARKETPLACE_FEES) or {}).get("balance", 0) - \
                (b.get(A.ADS) or {}).get("balance", 0)
            return net / g
        if by_period.get(cur, {}).get("n", 0) >= MIN_ORDERS_FOR_RATES and \
                by_period.get(prev, {}).get("n", 0) >= MIN_ORDERS_FOR_RATES:
            mc, mp = margin(cur), margin(prev)
            if mc is not None and mp is not None and mp - mc > MARGIN_DROP:
                found.append({"type": "margin_deterioration", "key": f"anomaly:margin:{cur}",
                              "severity": "medium", "period": cur,
                              "summary": (f"contribution margin fell from {mp:.0%} ({prev}) "
                                          f"to {mc:.0%} ({cur})"),
                              "evidence": {"current": round(mc, 4), "previous": round(mp, 4)}})
        # reconciliation drift: bank snapshot vs ledger
        snap = s.scalar(select(AcctStatementLine).where(
            AcctStatementLine.source == "bank", AcctStatementLine.kind == "balance")
            .order_by(AcctStatementLine.at.desc()).limit(1))
        if snap is not None:
            b = balances(s, until=_aware(snap.at))
            led = (b.get(A.BANK) or {}).get("balance", 0)
            if abs(led - snap.amount_micros) > 5_000:
                found.append({"type": "reconciliation_drift", "key": f"anomaly:bankbal:{snap.id}",
                              "severity": "high", "period": period_of(snap.at),
                              "summary": (f"bank statement balance CA${to_cad(snap.amount_micros)} "
                                          f"vs ledger bank account CA${to_cad(led)}"),
                              "evidence": {"statement_line": snap.id,
                                           "statement_cad": to_cad(snap.amount_micros),
                                           "ledger_cad": to_cad(led)}})
    # spend spike (reused detector)
    try:
        sp = governor.anomaly(db, now=now)
    except Exception:  # noqa: BLE001
        sp = {"measurable": False}
    if sp.get("measurable") and sp.get("spike"):
        found.append({"type": "spend_spike", "key": f"anomaly:spike:{now.date().isoformat()}",
                      "severity": "medium", "period": period_of(now),
                      "summary": "operating spend spike: " + sp.get("why", ""),
                      "evidence": sp})
    chain = verify_chain(db)
    if not chain["ok"]:
        found.append({"type": "reconciliation_drift", "key": f"anomaly:chain:{chain['head'][:16]}",
                      "severity": "high", "period": period_of(now),
                      "summary": "the journal hash chain does not verify: "
                                 + "; ".join(p["problem"] for p in chain["problems"][:3]),
                      "evidence": chain})
    if include_books:
        from .reconciliation import compare_with_books

        try:
            cmp = compare_with_books(db, until=now)
        except Exception as exc:  # noqa: BLE001
            cmp = {"agree": True, "error": type(exc).__name__}
        unexplained = [k for k, v in cmp.get("metrics", {}).items() if not v["agree"]]
        if unexplained and not cmp.get("explained_by"):
            found.append({"type": "reconciliation_drift",
                          "key": f"anomaly:books:{period_of(now)}:{','.join(unexplained)}",
                          "severity": "high", "period": period_of(now),
                          "summary": "ledger and books disagree with no known cause on "
                                     + ", ".join(unexplained),
                          "evidence": cmp})
    opened = 0
    with db.session() as s:
        for f in found:
            _, created = X.open_in(s, key=f["key"][:200], kind=f"anomaly:{f['type']}",
                                   summary=f["summary"], evidence=f["evidence"],
                                   period=f["period"], severity=f["severity"], now=now)
            opened += int(created)
    return {"findings": found, "opened": opened, "spend_spike_detector": {
        k: sp.get(k) for k in ("measurable", "why", "days_of_history") if k in sp}}
