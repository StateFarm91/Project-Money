"""CA$3,000 a month as arithmetic, and the constraint that is actually binding.

Requirements 24, 25, 28. A revenue target is a wish until it is a funnel, and the useful thing
about writing it as a funnel is not the number at the end — it is that only one term in it is
ever the problem, and the company usually works on a different one.

Three ideas, and the first is the one that changes decisions.

**Contribution per visitor, not conversion rate (#24).** A CA$25 pattern converting at 1.6% is
worth more per visitor than a CA$12 pattern converting at 2.5%, and every instinct in
e-commerce says the second is the healthier listing. Optimising conversion rate is optimising
a ratio whose denominator you are also buying. So the first-class metrics here are revenue per
visitor and contribution per visitor, and conversion is reported as an input to them rather
than as a score.

**One decomposition is a plan; three are a choice (#25).** 200 orders at CA$15, 150 at CA$20,
120 at CA$25 — the same CA$3,000 and three different companies. Showing them together makes
the price decision visible as a decision, instead of leaving it implicit in whichever number
somebody wrote down first.

**The constraint is named, and it is one thing (#25, #28).** Traffic, click-through,
conversion, order value, repeat rate, coverage, margin. A weekly review that improves four of
them has improved nothing if the fifth is binding, and the fifth is usually the one nobody
owns. Every rate here is required to come from observation: with nothing observed the module
says which term is unmeasured rather than filling it with a category benchmark, because a
funnel built from benchmarks tells you about the category and nothing about the company.
"""
from __future__ import annotations

from dataclasses import dataclass

# Plausible price points for a premium digital pattern, used to show the target as a choice
# rather than to recommend one.
DECOMPOSITION_PRICES: tuple[float, ...] = (15.0, 20.0, 25.0, 30.0)

# The funnel terms, in the order a visitor moves through them. Order matters: the constraint
# report walks them so the earliest binding term is named, and fixing a later one first is
# work that cannot show up.
TERMS: tuple[tuple[str, str], ...] = (
    ("traffic", "qualified visits reaching the listings at all"),
    ("ctr", "the share of impressions that become visits"),
    ("conversion", "the share of visits that become orders"),
    ("aov", "average order value"),
    ("repeat_rate", "the share of customers who buy again"),
    ("coverage", "whether the catalogue answers enough different demand"),
    ("margin", "contribution left after fees and cost of sale"),
)

TERM_KEYS: tuple[str, ...] = tuple(k for k, _ in TERMS)

# #28's conditional scale rules, as (condition, action). Written as data because the point of
# #28 is that the action follows from the diagnosis rather than from whoever is looking.
SCALE_RULES: tuple[tuple[str, str, str], ...] = (
    ("strong_conversion_low_traffic",
     "conversion is at or above benchmark and traffic is thin",
     "increase distribution: the listing works and nobody is seeing it"),
    ("high_traffic_weak_ctr",
     "impressions are plentiful and few become visits",
     "the thumbnail and the title, not the product"),
    ("strong_ctr_weak_conversion",
     "visits arrive and do not convert",
     "offer, trust and price -- the hero won the click and the listing lost it"),
    ("cac_below_allowable",
     "paid acquisition costs less than the contribution a customer returns",
     "scale gradually, re-measuring allowable CAC as contribution moves"),
    ("rising_defects",
     "support cases or refunds are rising",
     "stop scaling and investigate: scaling a defect multiplies it"),
)

RULES_BY_KEY: dict[str, tuple[str, str]] = {k: (c, a) for k, c, a in SCALE_RULES}

# Category-typical starting points, used only to say how far an observation sits from the
# category -- never to stand in for one.
BENCH_CTR = 0.020
BENCH_CONVERSION = 0.025


class RunRateRefused(ValueError):
    """A funnel built from benchmarks, or a rate asserted without observation."""


@dataclass(frozen=True)
class Observed:
    """What is actually known. Every field defaults to unmeasured, which is today's truth."""

    visits: int | None = None
    impressions: int | None = None
    orders: int | None = None
    revenue_cad: float | None = None
    contribution_cad: float | None = None
    repeat_orders: int | None = None
    listings: int | None = None

    @property
    def conversion(self) -> float | None:
        if self.visits and self.orders is not None:
            return self.orders / self.visits
        return None

    @property
    def ctr(self) -> float | None:
        if self.impressions and self.visits is not None:
            return self.visits / self.impressions
        return None

    @property
    def aov_cad(self) -> float | None:
        if self.orders and self.revenue_cad is not None:
            return self.revenue_cad / self.orders
        return None

    @property
    def revenue_per_visitor(self) -> float | None:
        if self.visits and self.revenue_cad is not None:
            return self.revenue_cad / self.visits
        return None

    @property
    def contribution_per_visitor(self) -> float | None:
        if self.visits and self.contribution_cad is not None:
            return self.contribution_cad / self.visits
        return None

    def to_dict(self) -> dict:
        return {
            "visits": self.visits, "impressions": self.impressions, "orders": self.orders,
            "revenue_cad": self.revenue_cad, "contribution_cad": self.contribution_cad,
            "conversion": self.conversion, "ctr": self.ctr, "aov_cad": self.aov_cad,
            "revenue_per_visitor": (round(self.revenue_per_visitor, 4)
                                    if self.revenue_per_visitor is not None else None),
            "contribution_per_visitor": (round(self.contribution_per_visitor, 4)
                                         if self.contribution_per_visitor is not None
                                         else None),
        }


def per_visitor(candidates: list[dict]) -> dict:
    """Rank listings by contribution per visitor, which is the number that decides (#24).

    Each candidate is {slug, price_cad, conversion, contribution_rate}. The ranking routinely
    disagrees with the conversion-rate ranking, and that disagreement is the requirement:
    a CA$25 pattern converting at 1.6% beats a CA$12 pattern converting at 2.5%, and every
    instinct says otherwise because conversion is the number that feels like performance.
    """
    rows = []
    for c in candidates:
        price = float(c["price_cad"])
        conversion = float(c["conversion"])
        contribution_rate = float(c.get("contribution_rate", 1.0))
        rows.append({
            "slug": c["slug"],
            "price_cad": price,
            "conversion": conversion,
            "revenue_per_visitor": round(price * conversion, 4),
            "contribution_per_visitor": round(price * conversion * contribution_rate, 4),
        })
    by_contribution = sorted(rows, key=lambda r: -r["contribution_per_visitor"])
    by_conversion = sorted(rows, key=lambda r: -r["conversion"])
    disagree = ([r["slug"] for r in by_contribution] != [r["slug"] for r in by_conversion])
    return {
        "ranked": by_contribution,
        "best": by_contribution[0]["slug"] if by_contribution else None,
        "conversion_ranking_disagrees": disagree,
        "note": ("Contribution per visitor decides. Optimising conversion rate optimises a "
                 "ratio whose denominator you are also buying, which is why the two "
                 "rankings disagree here and why the conversion one feels right (#24)."
                 if disagree else
                 "both rankings agree, which is the easy case and not the common one"),
    }


def decompose(target_cad: float = 3000.0,
              prices: tuple[float, ...] = DECOMPOSITION_PRICES,
              observed: Observed | None = None) -> dict:
    """The target as funnel arithmetic, at several price points (#25).

    Required visits are derived only from an *observed* conversion rate. With none, the
    orders-and-price half is still arithmetic and the visits half says it is unmeasured --
    filling it from a category benchmark would produce a confident plan about a company that
    does not exist.
    """
    observed = observed or Observed()
    conversion = observed.conversion

    rows = []
    for price in prices:
        orders = target_cad / price
        row = {"price_cad": price, "orders_per_month": round(orders, 1),
               "orders_per_day": round(orders / 30.0, 2)}
        if conversion:
            row["required_visits_per_month"] = int(round(orders / conversion))
            row["required_visits_per_day"] = int(round(orders / conversion / 30.0))
            row["from"] = f"observed conversion of {conversion:.2%}"
        else:
            row["required_visits_per_month"] = None
            row["from"] = ("unmeasured: no conversion has been observed, and a category "
                           "benchmark here would produce a confident plan about a company "
                           "that does not exist")
        rows.append(row)

    return {
        "target_cad_per_month": target_cad,
        "options": rows,
        "conversion_observed": conversion,
        "note": ("The same target at four prices is four different companies. Showing them "
                 "together makes the price decision visible as a decision rather than "
                 "leaving it implicit in whichever number was written down first (#25)."),
    }


def constraint(observed: Observed, *, target_cad: float = 3000.0,
               refund_rate: float | None = None,
               support_rate: float | None = None) -> dict:
    """Which single term is binding, walked in funnel order (#25, #28).

    Funnel order matters: fixing conversion while nobody is arriving is work that cannot show
    up, and it is the most natural work to choose because the listing is the thing under our
    hand.
    """
    unmeasured = []
    if observed.visits is None:
        unmeasured.append("traffic")
    if observed.ctr is None:
        unmeasured.append("ctr")
    if observed.conversion is None:
        unmeasured.append("conversion")
    if observed.aov_cad is None:
        unmeasured.append("aov")
    if observed.repeat_orders is None:
        unmeasured.append("repeat_rate")

    if unmeasured:
        return {
            "identifiable": False,
            "unmeasured": unmeasured,
            "reason": (f"{len(unmeasured)} of the funnel's terms have never been observed, "
                       f"so the binding one cannot be named. Naming it anyway would pick "
                       f"whichever term somebody has a benchmark for"),
            "observed": observed.to_dict(),
            "target_cad_per_month": target_cad,
        }

    # Defects outrank every commercial term: scaling a defect multiplies it (#28).
    if (refund_rate or 0) > 0.05 or (support_rate or 0) > 0.10:
        return {"identifiable": True, "constraint": "margin",
                "rule": "rising_defects",
                "action": RULES_BY_KEY["rising_defects"][1],
                "observed": observed.to_dict(), "target_cad_per_month": target_cad}

    aov = observed.aov_cad or 0.0
    conversion = observed.conversion or 0.0
    ctr = observed.ctr or 0.0
    needed_orders = target_cad / aov if aov else 0.0
    needed_visits = needed_orders / conversion if conversion else 0.0

    # Funnel order, strictly. Impressions become visits before visits become orders, so a
    # listing that is being shown and not clicked is a click-through problem even though its
    # visit count is also low -- buying more impressions when 99.8% of them bounce is buying
    # more of a broken funnel, and "low traffic" is the diagnosis that would send us there.
    if ctr < BENCH_CTR * 0.5:
        rule = "high_traffic_weak_ctr"
        term = "ctr"
    elif observed.visits and observed.visits < needed_visits * 0.5 \
            and conversion >= BENCH_CONVERSION:
        rule = "strong_conversion_low_traffic"
        term = "traffic"
    elif conversion < BENCH_CONVERSION * 0.5:
        rule = "strong_ctr_weak_conversion"
        term = "conversion"
    elif observed.visits and observed.visits < needed_visits:
        rule = "strong_conversion_low_traffic"
        term = "traffic"
    else:
        rule = "cac_below_allowable"
        term = "coverage"

    return {
        "identifiable": True,
        "constraint": term,
        "meaning": dict(TERMS)[term],
        "rule": rule,
        "condition": RULES_BY_KEY[rule][0],
        "action": RULES_BY_KEY[rule][1],
        "needed_orders_per_month": round(needed_orders, 1),
        "needed_visits_per_month": int(round(needed_visits)) if needed_visits else None,
        "observed": observed.to_dict(),
        "target_cad_per_month": target_cad,
        "note": ("Walked in funnel order, so the earliest binding term is named. Fixing "
                 "conversion while nobody is arriving is work that cannot show up, and it "
                 "is the most natural work to choose because the listing is the thing under "
                 "our hand (#25)."),
    }


def allowable_cac(aov_cad: float, contribution_rate: float, *,
                  payback_orders: float = 1.0) -> dict:
    """What an acquired customer may cost, from contribution rather than from revenue.

    Setting allowable CAC against revenue is how a business buys customers at a loss while
    every top-line number rises.
    """
    if aov_cad <= 0 or not 0 < contribution_rate <= 1:
        raise RunRateRefused("allowable CAC needs a positive order value and a "
                             "contribution rate between 0 and 1")
    contribution = aov_cad * contribution_rate * payback_orders
    return {
        "allowable_cac_cad": round(contribution, 2),
        "aov_cad": aov_cad,
        "contribution_rate": contribution_rate,
        "payback_orders": payback_orders,
        "note": ("Set against contribution, never revenue: allowable CAC from a top line is "
                 "how a business buys customers at a loss while every headline number "
                 "rises."),
    }
