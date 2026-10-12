"""F-620 Command Center Finance: one owner statement, month-to-date beside year-to-date.

Criterion (registry F-620, quoted): "Show MTD/YTD sales, refunds, Etsy fees, free ad credit,
cash ad spend, AI/infrastructure/software expenses, contribution profit, margin, tax reserve,
payout/cash position, unreconciled items and monthly-close status."

Every figure is read from an existing producer and keeps that producer's reading:

* sales, refunds, Etsy fees, contribution, tax reserve, cash and expected payout come from the
  Accountant (`finance.accounting.dashboard.summary`, windows `mtd` and `ytd`);
* AI / infrastructure / software spend comes from the accrual income statement's
  per-account split (`finance.accounting.views.accrual`) -- recorded cost rows, so they read
  RECORDED, never "measured" sales-grade money;
* free ad credit is the credit wallet's `ads_credit` rows (`finance.credits.wallet`); with no
  ad credit recorded it is UNKNOWN (an unrecorded credit is not a zero credit);
* cash ad spend is recorded advertising spend, less nothing when no ad credit is recorded (the
  wallet's own rule: all recorded spend is cash exposure), and ESTIMATED when a credit exists
  because the provider's draw order is assumed;
* margin is contribution / net sales, only when both are known and net sales is positive;
* unreconciled items are the Accountant's open exceptions; monthly-close status is
  `finance.accounting.close.status`.

A figure the source cannot give is UNKNOWN with the reason -- never CA$0.00. It writes nothing of its
own and changes no ceiling; the only write is the Accountant's idempotent posting refresh,
the same one the Money tab's accounting section already runs.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .providers import envelope, unknown

WINDOWS = ("mtd", "ytd")
_STATE = {"measured": "MEASURED", "estimated": "ESTIMATED", "derived": "ESTIMATED",
          "lower_bound": "ESTIMATED", "stale": "STALE", "unknown": "UNKNOWN"}
AI_ACCOUNTS = ("AI model & API", "Image generation & rendering")
INFRA_ACCOUNTS = ("Hosting & software",)
ADS_ACCOUNT = "Advertising"


def _money(value, state: str, why: str = "") -> dict:
    """A money cell. Anything not known is value None + UNKNOWN/STALE, never 0.0."""
    st = state if value is not None else ("STALE" if state == "STALE" else "UNKNOWN")
    return {"value_cad": None if st in ("UNKNOWN", "STALE") else round(float(value), 2),
            "state": st, "why": why or ""}


def _item(summ: dict, metric: str) -> dict | None:
    return next((i for i in summ.get("items") or [] if i.get("metric") == metric), None)


def _from_summary(summ: dict, metric: str, *, recorded: bool = False) -> dict:
    it = _item(summ, metric)
    if it is None:
        return _money(None, "UNKNOWN", summ.get("reason") or "the accountant did not report it")
    state = _STATE.get(str(it.get("reading") or "UNKNOWN").lower(), "UNKNOWN")
    if recorded and state == "MEASURED":
        state = "RECORDED"
    return _money(it.get("value_cad"), state, it.get("why") or "")


def _by_account(acc: dict, names, est: bool) -> dict:
    by = acc.get("accrual_operating_by_account_cad") or {}
    total = sum(float(by.get(n) or 0.0) for n in names)
    return _money(total, "ESTIMATED" if est else "RECORDED",
                  "recorded cost rows booked to " + ", ".join(names))


def _ads_credit(wallet: dict) -> tuple[dict, float]:
    rows = [r for p in (wallet.get("providers") or {}).values() for r in p.get("credits") or []
            if r.get("kind") == "ads_credit"]
    if not rows:
        return (_money(None, "UNKNOWN",
                       "no ad credit is recorded in the credit wallet (finance.credits); an "
                       "unrecorded credit is not a zero credit"), 0.0)
    left = sum(float(r.get("estimated_left_cad") or 0.0) for r in rows)
    drawn = sum(float(r.get("estimated_drawn_cad") or 0.0) for r in rows)
    why = (f"{len(rows)} ad credit grant(s); {wallet.get('draw_assumption') or ''}").strip()
    if any(r.get("expiry_basis") == "UNKNOWN" for r in rows):
        why += "; at least one expiry is UNKNOWN"
    return _money(left, "ESTIMATED", why), drawn


def _window_figures(db, window: str, now: datetime, wallet: dict) -> dict:
    from ...finance.accounting import dashboard, views

    summ = dashboard.summary(db, window=window, now=now, refresh=(window == WINDOWS[0]))
    if summ.get("status") == "UNKNOWN" and not summ.get("items"):
        reason = summ.get("reason") or "accountant summary unavailable"
        return {"_status": "UNKNOWN", "_reason": reason, "_label": window}
    w = dashboard._window(window, now)
    acc = views.accrual(db, **{k: w[k] for k in ("period", "since", "until") if k in w})
    op_est = bool((acc.get("estimated_components") or {}).get("operating"))
    by = acc.get("accrual_operating_by_account_cad") or {}

    contribution = _from_summary(summ, "contribution")
    net = _from_summary(summ, "net_sales")
    if contribution["value_cad"] is not None and net["value_cad"] and net["value_cad"] > 0:
        margin = {"value": round(contribution["value_cad"] / net["value_cad"], 4),
                  "state": ("ESTIMATED" if "ESTIMATED" in (contribution["state"], net["state"])
                            else "MEASURED"), "why": "contribution / net sales"}
    else:
        margin = {"value": None, "state": "UNKNOWN",
                  "why": ("net sales is not a known positive figure: "
                          + (net["why"] or net["state"]))}

    credit, credit_drawn = _ads_credit(wallet)
    ads_recorded = float(by.get(ADS_ACCOUNT) or 0.0)
    if credit["state"] == "UNKNOWN":
        cash_ads = _money(ads_recorded, "RECORDED",
                          "recorded advertising spend; no ad credit is recorded, so all of it "
                          "is treated as cash (finance.credits rule)")
    else:
        cash_ads = _money(max(0.0, ads_recorded - credit_drawn), "ESTIMATED",
                          f"recorded advertising spend CA${ads_recorded:.2f} less the ad "
                          f"credit estimated drawn CA${credit_drawn:.2f} (all time; draw "
                          f"order assumed)")
    exc = summ.get("exceptions") or {}
    return {
        "_status": summ.get("status") or "UNKNOWN", "_reason": summ.get("reason") or "",
        "_label": summ.get("window") or window,
        "gross_sales": _from_summary(summ, "gross_sales"),
        "refunds": _from_summary(summ, "refunds"),
        "net_sales": net,
        "etsy_fees": _from_summary(summ, "fees"),
        "free_ad_credit": credit,
        "cash_ad_spend": cash_ads,
        "ai_spend": _by_account(acc, AI_ACCOUNTS, op_est),
        "infra_software_spend": _by_account(acc, INFRA_ACCOUNTS, op_est),
        "operating_spend": _from_summary(summ, "operating_spend", recorded=True),
        "contribution": contribution,
        "margin": margin,
        "tax_reserve": _from_summary(summ, "tax_reserve"),
        "cash": _from_summary(summ, "cash"),
        "expected_payout": _from_summary(summ, "expected_payout"),
        "unreconciled": {"value": (int(exc["open"]) if isinstance(exc.get("open"), int)
                                   else None),
                         "state": "MEASURED" if isinstance(exc.get("open"), int) else "UNKNOWN",
                         "why": summ.get("reconciliation_health") or ""},
        "_close": summ.get("close") or {},
    }


ROWS = (
    ("gross_sales", "Sales (gross)", "money"),
    ("refunds", "Refunds", "money"),
    ("net_sales", "Net sales", "money"),
    ("etsy_fees", "Etsy fees", "money"),
    ("free_ad_credit", "Free ad credit left", "money"),
    ("cash_ad_spend", "Cash ad spend", "money"),
    ("ai_spend", "AI & image spend", "money"),
    ("infra_software_spend", "Infrastructure & software", "money"),
    ("operating_spend", "All operating spend", "money"),
    ("contribution", "Contribution profit", "money"),
    ("margin", "Contribution margin", "ratio"),
    ("tax_reserve", "Tax reserve", "money"),
    ("cash", "Cash in bank", "money"),
    ("expected_payout", "Etsy balance (expected payout)", "money"),
    ("unreconciled", "Unreconciled items", "count"),
)


def _close_row(close: dict) -> dict:
    if not close or close.get("error"):
        return {"metric": "monthly_close", "label": "Monthly close", "kind": "status",
                "value": None, "state": "UNKNOWN",
                "why": f"close status unreadable: {close.get('error') if close else 'absent'}"}
    prev = close.get("previous_period")
    locked = bool(close.get("previous_period_locked"))
    return {"metric": "monthly_close", "label": "Monthly close", "kind": "status",
            "value": (f"{prev} closed" if locked else f"{prev} not closed"),
            "state": "MEASURED", "previous_period": prev, "previous_period_locked": locked,
            "last_locked": close.get("last_locked"),
            "current_period": close.get("current_period"),
            "why": "finance.accounting.close.status: a closed month is a locked period"}


def statement(db, *, now: datetime | None = None) -> dict:
    """The F-620 statement: one row per required line, MTD and YTD side by side."""
    from ...finance import credits

    now = now or datetime.now(timezone.utc)
    try:
        wallet = credits.wallet(db, now=now)
    except Exception as exc:  # noqa: BLE001 - an unreadable wallet is UNKNOWN credit
        wallet = {"providers": {}, "why_empty": f"wallet unreadable: {type(exc).__name__}"}
    cols = {w: _window_figures(db, w, now, wallet) for w in WINDOWS}
    if all(c["_status"] == "UNKNOWN" and "gross_sales" not in c for c in cols.values()):
        return unknown("; ".join(f"{w}: {c['_reason']}" for w, c in cols.items())[:600],
                       "command_center.finance_statement",
                       ["finance.accounting.dashboard.summary"])
    items = []
    for key, label, kind in ROWS:
        row = {"metric": key, "label": label, "kind": kind}
        for w in WINDOWS:
            cell = cols[w].get(key)
            row[w] = cell if cell is not None else {"value_cad": None, "state": "UNKNOWN",
                                                   "why": cols[w].get("_reason") or ""}
        items.append(row)
    items.append(_close_row(cols["mtd"].get("_close") or cols["ytd"].get("_close") or {}))
    statuses = [c["_status"] for c in cols.values()]
    status = ("BLOCKED" if "BLOCKED" in statuses else
              "OK" if all(s == "OK" for s in statuses) else
              "UNKNOWN" if all(s == "UNKNOWN" for s in statuses) else "DEGRADED")
    reason = "; ".join(f"{w}: {cols[w]['_reason']}" for w in WINDOWS if cols[w]["_reason"])
    return envelope(status, items,
                    ["finance.accounting.dashboard.summary(mtd,ytd)",
                     "finance.accounting.views.accrual", "finance.credits.wallet",
                     "finance.accounting.close.status"],
                    basis=("measured" if status == "OK" else
                           "unknown" if status == "UNKNOWN" else "estimated"),
                    reason=reason[:1200] or None,
                    provider="command_center.finance_statement",
                    as_of=now.isoformat(),
                    columns={w: cols[w]["_label"] for w in WINDOWS})
