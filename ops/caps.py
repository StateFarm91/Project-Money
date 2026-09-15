#!/usr/bin/env python3
"""Single source of truth for money caps (CAD). Every function that creates or raises a budget must call
`assert_within_cap(track, requested_increase)` which reads actual spend from the ledger first.
Usage: python3 ops/caps.py            -> prints caps and spend-to-date per track
       python3 ops/caps.py check B 50 -> exit 0 if a CA$50 increase for track B is allowed, 2 if not"""
import csv, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "finance" / "FINANCIAL_LEDGER.csv"
TOTAL_BANKROLL = 1000.00
CAPS = {  # MASTER_STRATEGY allocations; change only via DECISION_LOG
    "A": {"ads": 200.00, "total": 240.00},  # Track A: Etsy setup + listing fees + ads (planning figure 190; hard guard 240)
    "B": {"ads_stage1": 150.00, "ads_stage2": 250.00, "ads": 400.00, "tools": 120.00, "total": 520.00},
}
RESERVE_MIN = 290.00

def spend_by_track():
    """Sum actual expenses (all categories) by track, matched on the business_product_channel column prefix 'A:' or 'B:'."""
    out = {"A": {"ads": 0.0, "total": 0.0}, "B": {"ads": 0.0, "total": 0.0}, "other": 0.0}
    if not LEDGER.exists(): return out
    for r in csv.DictReader(LEDGER.open()):
        ch = (r.get("business_product_channel") or "").strip()
        track = ch[:1] if ch[:2] in ("A:", "B:") else None
        exp = sum(float(r.get(k) or 0) for k in ("expense_cad", "platform_payment_fees_cad", "advertising_cad", "refunds_chargebacks_cad"))
        ads = float(r.get("advertising_cad") or 0)
        if track: out[track]["total"] += exp; out[track]["ads"] += ads
        else: out["other"] += exp
    return out

def assert_within_cap(track, requested_increase, kind="ads"):
    """Raise ValueError if adding `requested_increase` CAD of `kind` spend to `track` would exceed its cap or the bankroll."""
    s = spend_by_track(); cap = CAPS[track]
    if kind == "ads" and s[track]["ads"] + requested_increase > cap["ads"] + 1e-9:
        raise ValueError(f"track {track} ads cap {cap['ads']:.2f} would be exceeded: spent {s[track]['ads']:.2f} + {requested_increase:.2f}")
    if s[track]["total"] + requested_increase > cap["total"] + 1e-9:
        raise ValueError(f"track {track} total cap {cap['total']:.2f} would be exceeded: spent {s[track]['total']:.2f} + {requested_increase:.2f}")
    all_spend = s["A"]["total"] + s["B"]["total"] + s["other"]
    if all_spend + requested_increase > TOTAL_BANKROLL - RESERVE_MIN + 1e-9:
        raise ValueError(f"reserve floor {RESERVE_MIN:.2f} would be breached: spent {all_spend:.2f} + {requested_increase:.2f} > {TOTAL_BANKROLL - RESERVE_MIN:.2f}")
    return True

if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "check":
        try: assert_within_cap(sys.argv[2], float(sys.argv[3])); print("allowed"); sys.exit(0)
        except ValueError as e: print("refused:", e); sys.exit(2)
    s = spend_by_track()
    for t in ("A", "B"): print(f"track {t}: spent total {s[t]['total']:.2f} (ads {s[t]['ads']:.2f}) / caps {CAPS[t]}")
    print(f"other spend {s['other']:.2f}; bankroll {TOTAL_BANKROLL:.2f}; reserve floor {RESERVE_MIN:.2f}")
