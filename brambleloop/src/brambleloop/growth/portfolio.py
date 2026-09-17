"""Portfolio, reviews and product mortality (Master Plan section 12).

Section 12 classifies every SKU and gives each class an intervention. The diagnostic table is
the useful part and it is worth stating plainly, because it is the difference between fixing a
listing and rewriting a pattern that was never the problem:

  high impressions / low clicks   -> the hero or the title, not the product
  high clicks / low conversion    -> the offer, the trust signals or the price
  low impressions / high conversion -> a distribution problem; the product is fine
  high sales / high support       -> a quality emergency, whatever the revenue says

The classifier's most important behaviour is refusing to classify. Every SKU currently has
zero impressions, zero clicks and zero orders, and a system that reads that as
CONVERSION_PROBLEM would retire a catalogue that has simply never been shown to anyone.
`classify` therefore returns NO_EVIDENCE until a SKU has been seen enough times to say
anything, and the intervention ladder for NO_EVIDENCE is "wait, and get it in front of
people".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# Classes from section 12, plus the one the plan implies and does not name.
STAR = "STAR"
PROMISING = "PROMISING"
SEO_PROBLEM = "SEO_PROBLEM"
CONVERSION_PROBLEM = "CONVERSION_PROBLEM"
QUALITY_PROBLEM = "QUALITY_PROBLEM"
SEASONAL = "SEASONAL"
REWORK = "REWORK"
RETIRE = "RETIRE"
NO_EVIDENCE = "NO_EVIDENCE"

# Below these, a rate is not a rate. Thirty clicks and one order is not a 3.3% conversion, it
# is one order.
MIN_IMPRESSIONS = 300
MIN_CLICKS = 40

# Category-typical benchmarks for a digital pattern listing. Starting points to be replaced by
# our own observed distribution once there is one.
BENCH_CTR = 0.020
BENCH_CONVERSION = 0.025
SUPPORT_CASE_RATE_ALARM = 0.08     # cases per order


@dataclass
class SkuMetrics:
    slug: str
    impressions: int = 0
    clicks: int = 0
    orders: int = 0
    revenue_cad: float = 0.0
    refunds: int = 0
    support_cases: int = 0
    open_p1_incidents: int = 0
    favourites: int = 0
    season: str | None = None
    window_open: bool = True
    days_live: int = 0

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0

    @property
    def conversion(self) -> float:
        return self.orders / self.clicks if self.clicks else 0.0

    @property
    def support_rate(self) -> float:
        return self.support_cases / self.orders if self.orders else 0.0

    @property
    def refund_rate(self) -> float:
        return self.refunds / self.orders if self.orders else 0.0


@dataclass
class Classification:
    slug: str
    label: str
    reason: str
    interventions: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"slug": self.slug, "label": self.label, "reason": self.reason,
                "interventions": list(self.interventions), "evidence": dict(self.evidence)}


# Section 12's intervention ladders. Ordered: cheapest and most reversible first, so a SKU is
# never retired before the things that cost nothing have been tried.
LADDERS: dict[str, list[str]] = {
    STAR: [
        "build the matching products the demand implies (Winner Amplification, section 5)",
        "add sizes and colourways to the same validated pattern",
        "bundle it with its collection siblings",
        "only then consider bounded paid discovery",
    ],
    PROMISING: [
        "improve the hero and re-measure at search-grid scale",
        "close the biggest reachable query gaps in the tag set",
        "add the frames the listing is missing",
    ],
    SEO_PROBLEM: [
        "rewrite the title around the reachable queries, not the head term",
        "respend the thirteen tag slots on distinct concepts",
        "fill every structured attribute — they are a filter buyers actually use",
        "publish the article and pins; indexing takes weeks, not days",
    ],
    CONVERSION_PROBLEM: [
        "the hero won the click and the rest of the listing lost it: check frames 2-4",
        "state the finished size and the hours honestly and early",
        "re-read the price against contribution per visitor, not against the shelf",
        "check the first two lines of the description on a phone",
    ],
    QUALITY_PROBLEM: [
        "stop selling it — a quality emergency outranks its revenue",
        "reproduce the defect through the compiler, not through opinion",
        "fix the CIR, re-validate, re-certify, increment the version",
        "re-issue to everyone who bought it, then reopen",
    ],
    SEASONAL: [
        "leave it live; its window is simply closed",
        "schedule the next window's content now, while the evidence is fresh",
        "do not read out-of-window numbers as a product problem",
    ],
    REWORK: [
        "the listing has been tried; the product itself is the variable now",
        "re-engineer sizing, colourway or construction from the CIR",
        "re-release as a new version rather than editing in place",
    ],
    RETIRE: [
        "stop spending attention on it",
        "keep it listed if it costs nothing, delist if it dilutes the grid",
        "record why, so the next portfolio does not rebuild the same SKU",
    ],
    NO_EVIDENCE: [
        "do nothing to the product: it has not been seen enough to judge",
        "get it in front of people — indexing, content, collection cross-sell",
        "re-assess once it has real impressions",
    ],
}


def classify(m: SkuMetrics, *, today: date | None = None) -> Classification:
    """Diagnose one SKU. Refuses to diagnose what it cannot see."""
    ev = {"impressions": m.impressions, "clicks": m.clicks, "orders": m.orders,
          "ctr": round(m.ctr, 5), "conversion": round(m.conversion, 5),
          "support_rate": round(m.support_rate, 4), "refund_rate": round(m.refund_rate, 4),
          "days_live": m.days_live}

    # A quality emergency outranks every commercial signal, including a good one.
    if m.open_p1_incidents > 0:
        return Classification(m.slug, QUALITY_PROBLEM,
                              f"{m.open_p1_incidents} open P1 incident(s): a quality "
                              f"emergency outranks whatever the revenue is doing",
                              LADDERS[QUALITY_PROBLEM], ev)
    if m.orders >= 10 and m.support_rate >= SUPPORT_CASE_RATE_ALARM:
        return Classification(m.slug, QUALITY_PROBLEM,
                              f"{m.support_rate:.0%} of orders generate a support case; high "
                              f"sales with high support is a quality problem wearing a "
                              f"revenue costume",
                              LADDERS[QUALITY_PROBLEM], ev)

    if m.impressions < MIN_IMPRESSIONS:
        return Classification(
            m.slug, NO_EVIDENCE,
            f"{m.impressions} impressions is below {MIN_IMPRESSIONS}; nothing can be "
            f"concluded, and concluding anyway is how a catalogue that was never shown to "
            f"anyone gets retired for underperforming",
            LADDERS[NO_EVIDENCE], ev)

    if m.season and not m.window_open:
        return Classification(m.slug, SEASONAL,
                              "its buying window is closed; out-of-window numbers are not a "
                              "product problem",
                              LADDERS[SEASONAL], ev)

    # High impressions, low clicks -> the hero or the title.
    if m.ctr < BENCH_CTR * 0.5:
        return Classification(
            m.slug, SEO_PROBLEM,
            f"{m.ctr:.2%} click-through against a {BENCH_CTR:.1%} benchmark on "
            f"{m.impressions} impressions: it is being shown and not chosen, which is the "
            f"hero and the title rather than the product",
            LADDERS[SEO_PROBLEM], ev)

    if m.clicks < MIN_CLICKS:
        return Classification(m.slug, NO_EVIDENCE,
                              f"{m.clicks} clicks is too few to read a conversion rate from",
                              LADDERS[NO_EVIDENCE], ev)

    # Clicks are healthy; what happens after the click?
    if m.conversion < BENCH_CONVERSION * 0.4:
        label = REWORK if m.days_live > 120 else CONVERSION_PROBLEM
        return Classification(
            m.slug, label,
            f"{m.conversion:.2%} conversion on {m.clicks} clicks: the hero won the click and "
            f"the listing lost it"
            + (" — and it has had long enough that the product itself is now the variable"
               if label == REWORK else ""),
            LADDERS[label], ev)

    if m.ctr >= BENCH_CTR and m.conversion >= BENCH_CONVERSION:
        if m.orders >= 25:
            return Classification(m.slug, STAR,
                                  f"{m.orders} orders at {m.conversion:.1%} conversion: this "
                                  f"is where the next products should come from",
                                  LADDERS[STAR], ev)
        return Classification(m.slug, PROMISING,
                              f"both rates are at or above benchmark on {m.orders} orders; "
                              f"worth pushing before it is worth copying",
                              LADDERS[PROMISING], ev)

    if m.days_live > 180 and m.orders <= 2:
        return Classification(m.slug, RETIRE,
                              f"{m.days_live} days live and {m.orders} orders after the "
                              f"listing interventions have been tried",
                              LADDERS[RETIRE], ev)

    return Classification(m.slug, PROMISING,
                          "mixed signals, nothing broken; keep improving the listing",
                          LADDERS[PROMISING], ev)


@dataclass
class PortfolioVerdict:
    as_of: str
    evidence_available: bool
    classifications: list[Classification]
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"as_of": self.as_of, "evidence_available": self.evidence_available,
                "classifications": [c.to_dict() for c in self.classifications],
                "actions": list(self.actions),
                "summary": self.summary()}

    def summary(self) -> dict:
        out: dict[str, int] = {}
        for c in self.classifications:
            out[c.label] = out.get(c.label, 0) + 1
        return out


def review_portfolio(metrics: list[SkuMetrics], *, today: date | None = None
                     ) -> PortfolioVerdict:
    """Classify the catalogue and say what to do next.

    Capital allocation (section 15) follows from this and not the other way round: attention
    goes to STARs and to the SEO/conversion problems that are cheap to fix, and away from
    products that have had their interventions and not responded.
    """
    today = today or date.today()
    classifications = [classify(m, today=today) for m in metrics]
    have_evidence = any(c.label != NO_EVIDENCE for c in classifications)

    actions: list[str] = []
    if not have_evidence:
        actions.append(
            "No SKU has enough impressions to classify. The correct action is distribution, "
            "not product changes: nothing is underperforming, because nothing has been shown "
            "to anyone yet.")
    else:
        stars = [c.slug for c in classifications if c.label == STAR]
        quality = [c.slug for c in classifications if c.label == QUALITY_PROBLEM]
        if quality:
            actions.append(f"Quality first: {quality} — these outrank every commercial signal.")
        if stars:
            actions.append(f"Amplify {stars}: build the matching products, sizes and bundles "
                           f"the demand implies before spending on anything new.")
        seo = [c.slug for c in classifications if c.label == SEO_PROBLEM]
        if seo:
            actions.append(f"Listing work on {seo}: being shown and not chosen is the "
                           f"cheapest problem on this list to fix.")
    return PortfolioVerdict(as_of=today.isoformat(), evidence_available=have_evidence,
                            classifications=classifications, actions=actions)
