"""Launch success as a multi-signal verdict (F-286).

Launch success requires visibility + clicks + honest conversion + product truth + customer
experience + unit economics -- not merely "live" or "ads running". `verdict(db)` reads each
signal from the record, PASS / FAIL / UNMEASURED, and `success` is True only when all six
PASS. "Live" and "ads running" are reported beside it as context and are never signals.

Thresholds are `growth.portfolio`'s category starting points (MIN_IMPRESSIONS, MIN_CLICKS,
BENCH_CTR, BENCH_CONVERSION, SUPPORT_CASE_RATE_ALARM) and `commerce.benchmarks`'
MIN_ORDERS_FOR_REFUND_RATE -- no new number is invented here.
"""
from __future__ import annotations

PASS = "PASS"
FAIL = "FAIL"
UNMEASURED = "UNMEASURED"
SIGNALS = ("visibility", "clicks", "honest_conversion", "product_truth",
           "customer_experience", "unit_economics")


def _sig(status, why, **extra) -> dict:
    return {"status": status, "why": why, **extra}


def verdict(db) -> dict:
    from sqlalchemy import select

    from ..commerce.benchmarks import MIN_ORDERS_FOR_REFUND_RATE
    from ..core.models import Incident, ListingAsset
    from ..growth.portfolio import (BENCH_CONVERSION, BENCH_CTR, MIN_CLICKS, MIN_IMPRESSIONS,
                                    SUPPORT_CASE_RATE_ALARM)
    from ..scale import leading
    from . import visibility

    stats = visibility.latest_stats(db) or {}
    totals = (stats.get("joined") or {}).get("totals") or {}
    imp, vis = totals.get("impressions"), totals.get("visits")
    facts = leading.dashboard(db)["facts"]
    orders, live = facts["orders"], facts["live_listings"]
    out: dict[str, dict] = {}

    if not live:
        out["visibility"] = _sig(UNMEASURED, "no listing is live")
    elif imp is None:
        out["visibility"] = _sig(UNMEASURED, "no Etsy Stats export ingested")
    else:
        out["visibility"] = _sig(PASS if imp >= MIN_IMPRESSIONS else UNMEASURED,
                                 f"{imp} impressions (floor {MIN_IMPRESSIONS})", value=imp)

    if imp is None or vis is None or imp < MIN_IMPRESSIONS:
        out["clicks"] = _sig(UNMEASURED, "impressions below the floor or not supplied")
    else:
        ctr = vis / imp if imp else 0.0
        out["clicks"] = _sig(PASS if ctr >= BENCH_CTR else FAIL,
                             f"CTR {ctr:.3%} against starting point {BENCH_CTR:.1%}",
                             value=round(ctr, 5))

    if vis is None or vis < MIN_CLICKS:
        out["honest_conversion"] = _sig(UNMEASURED, f"visits {vis} below {MIN_CLICKS}")
    else:
        conv = orders / vis
        # Honest: only countable orders (rc1-ORD2) -- refunded, voided, unreconciled or held
        # orders are not sales, so they never lift the rate.
        refunded = facts.get("refunded", 0)
        out["honest_conversion"] = _sig(
            PASS if conv >= BENCH_CONVERSION else FAIL,
            f"{orders} countable order(s) over {vis} visits = {conv:.2%} (starting point "
            f"{BENCH_CONVERSION:.1%}); refunded/voided orders excluded ({refunded})",
            value=round(conv, 5))

    with db.session() as s:
        halting = [i.id for i in s.scalars(select(Incident).where(
            Incident.resolved == False)) if i.severity in ("P0", "P1")  # noqa: E712
                   or getattr(i, "halts_publication", False)]
        blocked = sorted({a.product_slug for a in s.scalars(select(ListingAsset))
                          if a.blocked_reasons})
    out["product_truth"] = _sig(
        FAIL if (halting or blocked) else PASS,
        (f"open P0/P1 or halting incidents {halting[:5]}; Asset-Truth blocked {blocked[:5]}"
         if (halting or blocked) else "no open P0/P1 incident and no Asset-Truth block"))

    if orders < MIN_ORDERS_FOR_REFUND_RATE:
        out["customer_experience"] = _sig(
            UNMEASURED, f"{orders} order(s) against a floor of {MIN_ORDERS_FOR_REFUND_RATE}")
    else:
        rate = facts["support_cases"] / orders
        out["customer_experience"] = _sig(
            PASS if rate <= SUPPORT_CASE_RATE_ALARM else FAIL,
            f"support cases per order {rate:.3f} (alarm {SUPPORT_CASE_RATE_ALARM})",
            value=round(rate, 4))

    from ..finance import sources

    table = sources.table(db)
    contribution = round(sum(r["contribution_cad"] for r in table["channels"].values()), 2)
    if not table["total_orders"]:
        out["unit_economics"] = _sig(UNMEASURED, "no countable orders")
    else:
        out["unit_economics"] = _sig(PASS if contribution > 0 else FAIL,
                                     f"contribution CA${contribution} over "
                                     f"{table['total_orders']} countable order(s)",
                                     value=contribution)

    success = all(out[k]["status"] == PASS for k in SIGNALS)
    return {"success": success,
            "signals": {k: out[k] for k in SIGNALS},
            "failing": [k for k in SIGNALS if out[k]["status"] == FAIL],
            "unmeasured": [k for k in SIGNALS if out[k]["status"] == UNMEASURED],
            "context_not_signals": {"live_listings": live,
                                    "note": "'live' and 'ads running' are never success"},
            "rule": ("launch success requires visibility, clicks, honest conversion, product "
                     "truth, customer experience and unit economics together (F-286)")}
