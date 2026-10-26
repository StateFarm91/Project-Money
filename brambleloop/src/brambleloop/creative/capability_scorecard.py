"""Build 2 #94 Creativity Capability Scorecard -- the complete measurement, over time.

"Track creative capability over time using blinded human/agent benchmark comparisons, concept
diversity, novelty distance, desirability scores, percentage of concepts surviving the
tournament, market CTR/conversion, winner rate and repeated-theme fatigue. The objective is
demonstrable improvement in idea quality, not simply more generated ideas."

`tournament.scorecard`, `tournament.theme_fatigue`, `tournament.novelty` and `creative.blinded`
each measured one thing at one moment. `scorecard(db)` combines every named measure, per UTC
month and as a trend, from the rows the company already writes:

* tournaments (`creative.tournament` audit rows): fields generated, survival share;
* blinded human/agent comparison and DESIRABILITY (`creative.blinded` rows): the blinded
  same-pod win rate, counted only when the run was valid (enough pairs, no position bias);
* NOVELTY DISTANCE: each period's newly created products against every product that existed
  before them (`concept.nearest`), mean and minimum;
* CONCEPT DIVERSITY and REPEATED-THEME FATIGUE: `theme_fatigue` over the cumulative catalogue
  at the end of each period;
* MARKET CTR and CONVERSION per concept, combined over all periods (`listing_outcomes`):
  CTR = visits / impressions, conversion = orders / visits;
* WINNER RATE: of concepts with enough measured impressions, the share with a sale.

Anything with no evidence is UNMEASURED -- never 0. `objective` compares idea quality with idea
volume, so more ideas with flat quality reads as what it is. Read-only, deterministic, CA$0.
"""
from __future__ import annotations

UNMEASURED = "UNMEASURED"
# A concept's market numbers count only once it has been seen this often; below that a CTR is
# a coin toss. Winner = at least one sale. Both are this module's own floors (no row states
# figures), recorded so they can be argued with.
MIN_IMPRESSIONS = 200
WINNER_MIN_ORDERS = 1


def _month(at) -> str:
    return at.strftime("%Y-%m") if at is not None else "undated"


def _rate(num, den):
    return round(num / den, 4) if den else UNMEASURED


def _mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 4) if xs else UNMEASURED


def _trend(series: list) -> str:
    known = [x for x in series if isinstance(x, (int, float))]
    if len(known) < 2:
        return "insufficient history"
    first, last = known[0], known[-1]
    if abs(last - first) < 0.02:
        return "flat"
    return "improving" if last > first else "declining"


def _tournaments(db) -> dict[str, dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    out: dict[str, dict] = {}
    with db.session() as s:
        for at, d in s.execute(select(AuditLog.at, AuditLog.detail).where(
                AuditLog.action == "creative.tournament")).all():
            d = d or {}
            gen = int(((d.get("field") or {}).get("generated")) or 0)
            if gen <= 0:
                continue
            surv = d.get("survivors")
            p = out.setdefault(_month(at), {"generated": 0, "survived": 0, "tournaments": 0})
            p["generated"] += gen
            p["survived"] += len(surv) if isinstance(surv, list) else 0
            p["tournaments"] += 1
    return out


def _blinded(db) -> dict[str, dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    out: dict[str, dict] = {}
    with db.session() as s:
        for at, d in s.execute(select(AuditLog.at, AuditLog.detail).where(
                AuditLog.action == "creative.blinded")).all():
            d = d or {}
            t = d.get("tally") if isinstance(d.get("tally"), dict) else d
            p = out.setdefault(_month(at), {"runs": 0, "valid_runs": 0, "judged": 0,
                                            "ours": 0})
            p["runs"] += 1
            if t.get("valid") and isinstance(t.get("judged"), int):
                p["valid_runs"] += 1
                p["judged"] += t["judged"]
                p["ours"] += int(t.get("ours") or 0)
    return out


def _concepts_by_month(db) -> list[tuple[str, object]]:
    from sqlalchemy import select

    from ..core.models import Product
    from .audit import catalogue_concepts

    by_key = {c.key: c for c in catalogue_concepts()}
    with db.session() as s:
        rows = s.execute(select(Product.slug, Product.created_at).order_by(
            Product.created_at, Product.id)).all()
    return [(_month(at), by_key[slug]) for slug, at in rows if slug in by_key]


def _market(db) -> dict:
    from sqlalchemy import select

    from ..core.models import ListingOutcome

    per: dict[str, dict] = {}
    with db.session() as s:
        for slug, period, imp, vis, orders in s.execute(select(
                ListingOutcome.product_slug, ListingOutcome.period_start,
                ListingOutcome.impressions, ListingOutcome.visits,
                ListingOutcome.orders)).all():
            p = per.setdefault(slug, {"impressions": 0, "visits": 0, "orders": 0,
                                      "orders_known": False, "periods": set()})
            p["impressions"] += int(imp or 0)
            p["visits"] += int(vis or 0)
            if orders is not None:
                p["orders"] += int(orders)
                p["orders_known"] = True
            p["periods"].add(period)
    concepts = {}
    for slug, p in sorted(per.items()):
        enough = p["impressions"] >= MIN_IMPRESSIONS
        concepts[slug] = {
            "periods": len(p["periods"]), "impressions": p["impressions"],
            "visits": p["visits"],
            "ctr": _rate(p["visits"], p["impressions"]) if enough else UNMEASURED,
            "conversion": (_rate(p["orders"], p["visits"])
                           if enough and p["orders_known"] and p["visits"] else UNMEASURED),
            "orders": p["orders"] if p["orders_known"] else UNMEASURED,
            "winner": ((p["orders"] >= WINNER_MIN_ORDERS) if enough and p["orders_known"]
                       else UNMEASURED)}
    judged = [c for c in concepts.values() if c["winner"] != UNMEASURED]
    return {"concepts": concepts,
            "winner_rate": (_rate(sum(1 for c in judged if c["winner"]), len(judged))
                            if judged else UNMEASURED),
            "concepts_with_market_evidence": len(judged),
            "min_impressions": MIN_IMPRESSIONS}


def scorecard(db) -> dict:
    from .concept import nearest
    from .tournament import theme_fatigue

    tourn, blind = _tournaments(db), _blinded(db)
    dated = _concepts_by_month(db)
    months = sorted({m for m in tourn} | {m for m in blind} | {m for m, _ in dated})
    periods, seen = [], []
    for m in months:
        new = [c for mm, c in dated if mm == m]
        dists = []
        for c in new:
            _other, gap = nearest(c, seen) if seen else (None, None)
            if gap is not None and _other is not None:
                dists.append(gap)
        seen.extend(new)
        fat = theme_fatigue(seen) if seen else None
        t = tourn.get(m) or {}
        b = blind.get(m) or {}
        periods.append({
            "period": m,
            "concepts_new": len(new),
            "novelty_mean": _mean(dists), "novelty_min": (round(min(dists), 4) if dists
                                                          else UNMEASURED),
            "diversity_distinct_pods": (fat["by_field"]["pod"]["distinct"] if fat
                                        else UNMEASURED),
            "fatigued_fields": [f["field"] for f in fat["fatigued"]] if fat else UNMEASURED,
            "fatigue_share": (round(len(fat["fatigued"]) / len(fat["by_field"]), 4) if fat
                              else UNMEASURED),
            "tournaments": t.get("tournaments", 0),
            "survival_rate": _rate(t.get("survived", 0), t.get("generated", 0)),
            "blinded_runs": b.get("runs", 0),
            "desirability_win_rate": (_rate(b["ours"], b["judged"]) if b.get("judged")
                                      else UNMEASURED),
        })
    market = _market(db)

    def series(k):
        return [p[k] for p in periods]

    quality = {"novelty_mean": _trend(series("novelty_mean")),
               "desirability_win_rate": _trend(series("desirability_win_rate")),
               "survival_rate": _trend(series("survival_rate")),
               # fewer fatigued fields is better: invert for the direction
               "fatigue_share": {"improving": "declining", "declining": "improving"}.get(
                   _trend(series("fatigue_share")), _trend(series("fatigue_share")))}
    volume = _trend([float(p["concepts_new"]) for p in periods])
    improving = [k for k, v in quality.items() if v == "improving"]
    declining = [k for k, v in quality.items() if v == "declining"]
    return {
        "periods": periods,
        "market": market,
        "trends": {"quality": quality, "volume": volume},
        "objective": {
            "improving": improving, "declining": declining,
            "verdict": ("UNMEASURED" if all(v == "insufficient history" for v in
                                            quality.values())
                        else "quality improving" if improving and not declining
                        else "more ideas, not better ideas" if volume == "improving"
                        and not improving else "mixed"),
            "rule": "idea quality, not idea volume (#94)"},
        "pending_market_evidence": (
            market["concepts_with_market_evidence"] == 0),
        "writes": 0,
    }
