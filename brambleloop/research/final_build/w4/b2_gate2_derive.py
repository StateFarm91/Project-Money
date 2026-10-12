"""Derive the eight W4-B2GATES data-gate readings from read-only production GETs.

Usage: PYTHONPATH=src python research/final_build/w4/b2_gate2_derive.py
Reads evidence_B2GATE2/*_2026-10-11.json (public GETs of production at 0417f35) and writes
evidence_B2GATE2/derived_data_gates_2026-10-11.json for build2_ledger.py's second argument.

Production's deployed code (0417f35) predates the data gates, so /api/build does not report
them. Each reading below is taken from the production endpoint that serves the same record the
gate's checker reads, and says which. `lead_lag_series` is computed by loading production's
own culture series (GET /api/culture findings) into a scratch database and calling the
repository's `culture.radar.lead_lag` on every signal -- the gate's own function.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EV = HERE / "evidence_B2GATE2"
DAY = "2026-10-11"
COMMIT = "0417f35"


def _load(name: str) -> dict:
    return json.loads((EV / f"{name}_{DAY}.json").read_text(encoding="utf-8"))


def _check(name: str, check: str) -> dict:
    v = _load("prod_verify")
    return next(c for c in v["checks"] if c["check"] == check)["evidence"]


def lead_lag_from_production() -> dict:
    from brambleloop.core.db import Database
    from brambleloop.culture import radar

    culture = _load("prod_culture")
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/culture.sqlite")
    db.create_all()
    out = {}
    for f in culture["findings"]["findings"]:
        sig = f["signal"]
        for p in (f.get("momentum") or {}).get("series") or []:
            radar.observe(db, sig, channel=p["channel"], interest=float(p["interest"]),
                          competitor_listings=int(p.get("listings") or 0),
                          observed_on=p["on"], source="production /api/culture")
        out[sig] = {"now": radar.lead_lag(db, sig),
                    "served_by_production": f.get("lead_lag")}
    return out


def main() -> None:
    src = lambda what: f"derived from production GET {what} (read-only, {COMMIT}, {DAY})"  # noqa: E731
    pub = _check(None, "nothing_published")
    rev = _check(None, "no_revenue_claimed")
    cl = _load("prod_creative_learning")
    learning = _load("prod_learning")
    harvest = _load("prod_season_harvest")
    domains = {d["domain"]: d["observations"] for d in learning["radar"]["watched"]}
    ll = lead_lag_from_production()
    measurable = sorted(s for s, v in ll.items() if v["now"].get("measurable"))
    plateau = {s: v["now"]["plateau"] for s, v in ll.items() if v["now"].get("plateau")}
    prod_said = sorted(s for s, v in ll.items() if (v["served_by_production"] or {}).get("measurable"))
    gates = {
        "listing_traffic": {"open": False, "source": src(
            f"/api/verify nothing_published (listings_with_etsy_id "
            f"{pub['listings_with_etsy_id']}) and /api/creative-learning style.status "
            f"{cl['style']['status']}: no ListingOutcome with visits")},
        "style_outcomes": {"open": False, "source": src(
            f"/api/creative-learning: style.by_style {cl['style']['by_style'] or '{}'}, "
            f"status {cl['style']['status']}")},
        "concept_outcomes": {"open": False, "source": src(
            f"/api/creative-learning concepts_with_outcomes "
            f"{cl['concepts']['concepts_with_outcomes']}; /api/verify ledger_entries "
            f"{rev['ledger_entries']}")},
        "market_outcomes": {"open": False, "source": src(
            f"/api/verify: listings_with_etsy_id {pub['listings_with_etsy_id']}, revenue_cad "
            f"{rev['revenue_cad']}, ledger_entries {rev['ledger_entries']}")},
        "learning_sources": {"open": False, "source": src(
            f"/api/learning: customer_pain observations {domains.get('customer_pain', 0)}, "
            f"techniques observations {domains.get('techniques', 0)} (unobserved): half met")},
        "lead_lag_series": {"open": bool(measurable), "source": src(
            f"/api/culture series, re-run through culture.radar.lead_lag at this commit: "
            f"measurable for {measurable or 'no signal'}; production at {COMMIT} served "
            f"lead_lag measurable for {prod_said}, each on a plateau "
            f"({ {k: (v['value'], v['from'], v['to']) for k, v in plateau.items()} })")},
        "seasonal_orders": {"open": False, "source": src(
            f"/api/verify ledger_entries {rev['ledger_entries']}, revenue_cad "
            f"{rev['revenue_cad']}: no countable order")},
        "season_harvest": {"open": False, "source": src(
            "/api/season-harvest: every event "
            + ", ".join(sorted({v['status'] for v in harvest['events'].values()})))},
    }
    out = {"_note": __doc__.strip().splitlines()[0], "commit": COMMIT, "read": DAY,
           "gates": gates, "lead_lag_detail": ll}
    (EV / f"derived_data_gates_{DAY}.json").write_text(json.dumps(out, indent=1, default=str)
                                                       + "\n", encoding="utf-8")
    print(json.dumps({k: v["open"] for k, v in gates.items()}))
    print("lead_lag now measurable:", measurable, "| production served measurable:", prod_said)


if __name__ == "__main__":
    main()
