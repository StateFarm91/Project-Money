"""The Marketplace Insights query budgeter: information-gain arithmetic with nothing to spend on (#37).

#37 asks that a scarce first-party research resource be allocated by *expected information
gain* -- the highest-uncertainty, highest-value micro-markets first -- that every query and
result be stored so nothing is re-queried, and that an Etsy Plus upgrade be an owner-approved
decision taken only when expected value exceeds cost.

The resource does not exist yet. Marketplace Insights has no endpoint in Etsy's OpenAPI
document (`intel.etsy_surfaces` records the absence) and the rendered-page route is a browser
this company has not bought. The note beside #37 said the arithmetic was buildable before the
source, and tracked it as owed. This pays it.

What is here is arithmetic and a recommendation. What is not here, by construction, is a
purchase: `may_buy_insights` returns a recommendation with the evidence that produced it and
`purchased: False`, and there is no code path that changes that. The owner gate stays.

The two inputs are things this company already measures:

  uncertainty   `1 - confidence` from `radar.arbitrage.score_observed`, where confidence is
                the share of a micro-market's scoring weight that has been measured. A pod
                scored on 52% of its weight is 48% unknown, and that is what a query buys.
  prior queries `Keyword` rows already held for the pod's vocabulary -- the snapshot store
                #37 asks for, read so a keyword already snapshotted is worth less to ask again.

  gain = uncertainty × value / (1 + prior_queries)

where value is the pod's relative score (what is known so far about how good the market is),
so a pod that is both promising and unknown ranks first and a pod that is well-measured or
poor ranks last. The whole thing is labelled: every number carries what it was computed from,
and where nothing has been scored the budgeter says so instead of ranking from nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..gateway.anthropic import USD_TO_CAD as ASSUMED_USD_CAD

# Etsy Plus, the upgrade #37 names, at its published USD 10 a month converted at the one
# assumed rate the gateway already labels an assumption -- read from there rather than
# restated, because a rate restated in a second place is a rate that drifts. The owner
# decides with the real figure in front of them.
ETSY_PLUS_USD_PER_MONTH = 10.0
ETSY_PLUS_CAD_PER_MONTH = round(ETSY_PLUS_USD_PER_MONTH * ASSUMED_USD_CAD, 2)

# How many Insights queries a month of access would be spent on. A planning constant rather
# than a product fact: it sizes the allocation and is reported beside every recommendation.
QUERIES_PER_MONTH = 40

# What resolving one unit of uncertainty about one micro-market is taken to be worth, as a
# share of that market's observed median price. Deliberately small and labelled; the
# recommendation is `insufficient_evidence` unless real scores exist to multiply it against.
VALUE_PER_RESOLVED_UNIT_SHARE = 0.5

BUY = "buy"
DO_NOT_BUY = "do_not_buy"
INSUFFICIENT = "insufficient_evidence"


class BudgetRefused(ValueError):
    """An allocation asked to spend a resource that does not exist, or to rank from nothing."""


@dataclass(frozen=True)
class Gain:
    pod: str
    confidence: float
    uncertainty: float
    value: float
    prior_queries: int
    gain: float

    def to_dict(self) -> dict:
        return {"pod": self.pod, "confidence": self.confidence,
                "uncertainty": self.uncertainty, "value": self.value,
                "prior_queries": self.prior_queries, "gain": self.gain}


def information_gain(*, confidence: float, value: float, prior_queries: int) -> float:
    """The arithmetic, on its own so it can be read and tested without a database."""
    if not 0.0 <= confidence <= 1.0:
        raise BudgetRefused(f"confidence {confidence!r} is outside 0..1")
    if not 0.0 <= value <= 1.0:
        raise BudgetRefused(f"value {value!r} is outside 0..1")
    if prior_queries < 0:
        raise BudgetRefused("a negative query count is not a count")
    return round((1.0 - confidence) * value / (1 + int(prior_queries)), 4)


def prior_queries(db) -> dict[str, int]:
    """Keyword snapshots already held, counted against the pod whose vocabulary they match.

    This is the "store every query/result snapshot" half of #37 read back: a keyword already
    snapshotted is one whose answer is on file, and asking it again is the waste the
    requirement names. Counted by pod keyword match, and a phrase matching no pod counts for
    none of them rather than for all of them.
    """
    from sqlalchemy import select

    from ..core.models import Keyword
    from . import pods

    from ..core.models import InsightsSnapshot

    counts = {pod.key: 0 for pod in pods.PODS}
    with db.session() as s:
        phrases = [str(row.phrase or "") for row in s.scalars(select(Keyword))]
        # Owner-recorded Marketplace Insights snapshots (#236) are the query store #37
        # names, and a keyword already read there is one whose answer is on file.
        phrases += [str(row.keyword or "") for row in s.scalars(select(InsightsSnapshot))]
    for phrase in phrases:
        routed = pods.route(phrase)
        if routed in counts:
            counts[routed] += 1
    return counts


def keyword_plan(db, allocation: dict[str, int]) -> dict:
    """Which keywords each pod's share would be spent on, skipping ones already recorded.

    A keyword with a recent owner-recorded Insights snapshot is on file, so it is skipped
    rather than asked again (#37). Candidates are the pod's own form vocabulary, most
    specific first -- the same words the market map routes by.
    """
    from . import insights, pods

    done = insights.queried_keywords(db)
    plan: dict[str, dict] = {}
    for pod_key, share in allocation.items():
        pod = pods.BY_KEY.get(pod_key)
        if pod is None or share <= 0:
            continue
        candidates = [f"crochet {kw} pattern" for kw in pod.keywords]
        skipped = [k for k in candidates if k in done or k.split(" ", 1)[1].rsplit(" ", 1)[0]
                   in done]
        fresh = [k for k in candidates if k not in skipped]
        plan[pod_key] = {"ask": fresh[:share], "skipped_already_recorded": skipped}
    return {"by_pod": plan, "already_recorded": sorted(done),
            "basis": insights.BASIS}


def allocate(db, *, queries: int = QUERIES_PER_MONTH, benchmark_key: str = "") -> dict:
    """Rank micro-markets by expected information gain and share a query budget across them.

    Nothing is queried: there is nothing to query. The allocation is what a month of access
    would be spent on, and it is reported so the owner's decision has a plan attached.
    """
    from ..radar import arbitrage

    scored = arbitrage.score_observed(db, benchmark_key=benchmark_key)
    if not scored.get("measurable"):
        return {
            "allocatable": False,
            "reason": scored.get("reason", "no department has been scored"),
            "queries": int(queries),
            "gains": [],
            "allocation": {},
            "note": ("nothing has been scored, so uncertainty cannot be ranked. A budget "
                     "allocated from nothing would be spent on whatever came first"),
        }

    priors = prior_queries(db)
    gains: list[Gain] = []
    for card in scored["scored"]:
        pod = card["market"]
        confidence = float(card["confidence"])
        value = float(card["score"] if card["score"] is not None else 0.0)
        prior = int(priors.get(pod, 0))
        gains.append(Gain(pod, confidence, round(1.0 - confidence, 4), round(value, 4),
                          prior, information_gain(confidence=confidence, value=value,
                                                  prior_queries=prior)))
    gains.sort(key=lambda g: (-g.gain, g.pod))

    total = sum(g.gain for g in gains)
    allocation: dict[str, int] = {}
    if total > 0:
        remaining = int(queries)
        for g in gains:
            share = int(round(queries * g.gain / total))
            allocation[g.pod] = min(share, remaining)
            remaining -= allocation[g.pod]
        # Rounding leaves a remainder; it goes where the gain is highest, never nowhere.
        if remaining > 0 and gains:
            allocation[gains[0].pod] += remaining
    return {
        "allocatable": True,
        "queries": int(queries),
        "gains": [g.to_dict() for g in gains],
        "allocation": allocation,
        "keywords": keyword_plan(db, allocation),
        "first": gains[0].pod if gains else None,
        "formula": "gain = (1 - confidence) x value / (1 + prior_queries)",
        "inputs": {"confidence": "radar.arbitrage.score_observed, share of weight measured",
                   "value": "the same card's relative score",
                   "prior_queries": ("Keyword rows and owner-recorded Insights snapshots "
                                     "routed to the pod's vocabulary")},
        "departments_too_thin_to_score": scored.get("departments_too_thin_to_score", []),
        "note": ("Highest-uncertainty, highest-value first (#37). Nothing here queries "
                 "anything: Marketplace Insights has no sanctioned endpoint and no browser "
                 "has been bought, so this is the plan a month of access would follow"),
    }


def may_buy_insights(db, *, monthly_cost_cad: float = ETSY_PLUS_CAD_PER_MONTH,
                     queries: int = QUERIES_PER_MONTH, benchmark_key: str = "") -> dict:
    """Whether the upgrade #37 names is worth recommending. A recommendation, never a purchase.

    Expected value is the sum over ranked markets of the uncertainty a month's queries would
    resolve, priced at a labelled share of each market's observed median price. It is an
    estimate built from assumptions that are printed beside it, and the answer is one of
    three words. `purchased` is always False and there is no argument that changes it.
    """
    from ..radar import arbitrage

    plan = allocate(db, queries=queries, benchmark_key=benchmark_key)
    base = {
        "purchased": False,
        "owner_gate": ("Etsy Plus is consequential spend and an account change. The owner "
                       "approves it or it does not happen; this module cannot buy it"),
        "monthly_cost_cad": round(float(monthly_cost_cad), 2),
        "cost_basis": (f"USD {ETSY_PLUS_USD_PER_MONTH:.2f} a month at an assumed "
                       f"{ASSUMED_USD_CAD} CAD/USD" if monthly_cost_cad == ETSY_PLUS_CAD_PER_MONTH
                       else "supplied by the caller"),
        "allocation": plan,
    }
    if not plan["allocatable"]:
        return {**base, "recommendation": INSUFFICIENT,
                "expected_value_cad": None,
                "why": plan["reason"],
                "evidence": {"scored_departments": 0}}

    scored = arbitrage.score_observed(db, benchmark_key=benchmark_key)
    prices = {card["market"]: (card.get("observed") or {}).get("median_price_cad")
              for card in scored["scored"]}
    lines = []
    value_cad = 0.0
    for g in plan["gains"]:
        price = prices.get(g["pod"])
        share = plan["allocation"].get(g["pod"], 0)
        if price is None or share == 0:
            lines.append({**g, "queries": share, "median_price_cad": price, "value_cad": 0.0})
            continue
        # Each query resolves gain-worth of uncertainty; the pot is one resolved unit per
        # market valued at a share of its median price, spread over its queries.
        resolved = min(1.0, g["gain"] * share)
        line_value = round(resolved * float(price) * VALUE_PER_RESOLVED_UNIT_SHARE, 2)
        value_cad += line_value
        lines.append({**g, "queries": share, "median_price_cad": price,
                      "value_cad": line_value})
    value_cad = round(value_cad, 2)
    if value_cad <= 0:
        recommendation = INSUFFICIENT
        why = ("the scored departments carry no observed price to value a resolved "
               "uncertainty against, so expected value cannot be computed")
    elif value_cad > monthly_cost_cad:
        recommendation = BUY
        why = (f"expected value CA${value_cad:.2f} exceeds CA${monthly_cost_cad:.2f} a "
               f"month under the printed assumptions; recommend the owner approve one month "
               f"and re-run this after the snapshots are stored")
    else:
        recommendation = DO_NOT_BUY
        why = (f"expected value CA${value_cad:.2f} does not exceed CA${monthly_cost_cad:.2f} "
               f"a month; the uncertainty this would resolve is not worth the subscription yet")
    return {
        **base,
        "recommendation": recommendation,
        "expected_value_cad": value_cad,
        "why": why,
        "evidence": {
            "scored_departments": len(lines),
            "lines": lines,
            "value_per_resolved_unit_share": VALUE_PER_RESOLVED_UNIT_SHARE,
            "queries_per_month": int(queries),
            "formula": ("value = sum over markets of min(1, gain x queries) x "
                        "median_price_cad x value_per_resolved_unit_share"),
        },
        "assumptions": [
            "Etsy Plus price and the USD/CAD rate are assumptions, printed above",
            "value per resolved unit is a planning share, not a measurement",
            "confidence is the share of scoring weight measured, from one benchmark catalogue",
        ],
    }
