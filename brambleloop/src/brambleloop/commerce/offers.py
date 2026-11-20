"""The offer is a variable, and a design is not retired on one offer's evidence.

Requirement 13. Every test this company runs is about a design -- the thumbnail, the title,
the object itself -- and the requirement points at the other half: the same design sold six
different ways is six different propositions, and one of them failing says nothing about the
other five. Its last sentence is the one with teeth. *A winning design with a weak offer
should be fixed before being discarded*, which means a retirement decision taken on a single
offer is a decision about the offer wearing the design's name.

That is the whole module. An offer catalogue, the two measurements the requirement asks for,
and a refusal to retire a design nobody has actually tested.

**Contribution per visitor and revenue per buyer answer different questions, and the second
is the one that flatters.** A CA$28 collection bought by three people has a splendid revenue
per buyer and may still be losing to a CA$6 pattern that converts. Both are reported and
neither is reported alone, because whichever one is quoted by itself is the one that was
quoted because it looked better.

**An offer this company cannot deliver is refused before it is priced.** A pattern-plus-video
offer needs a video, and nothing here can make one; a beginner-support package is a promise
about response time, and a promise nobody has the capacity to keep is the most expensive
thing in a listing. Those are named as unavailable rather than quietly priced, because an
offer that cannot be delivered is a refund and a review, not a test.

**A design is retired on the evidence of the designs, never on a single offer's.** The
module requires that the design has been tried in more than one shape, and that those shapes
were genuinely different -- three bundles are one offer tested three times. Where it has not
been, the verdict is that the offer is weak rather than the design, and the next thing to do
is the cheapest offer it has not worn yet.
"""
from __future__ import annotations

from dataclasses import dataclass

from .benchmarks import METRICS

SINGLE = "single_pattern"
VIDEO = "pattern_plus_video"
MINI = "mini_bundle"
COLLECTION = "complete_collection"
BEGINNER = "beginner_support"
SEASONAL = "seasonal_bundle"


@dataclass(frozen=True)
class Offer:
    """One shape the same design can be sold in."""

    key: str
    contains: str
    # What has to exist before this can be delivered. Empty means it can be sold today.
    needs: tuple[str, ...]
    # Roughly how it sits against the single pattern, as a multiple rather than a price: a
    # price belongs to a product and a posture belongs to an offer.
    posture: float
    tests: str


OFFERS: tuple[Offer, ...] = (
    Offer(SINGLE, "the pattern", (), 1.0,
          "whether the design sells at all, which is the only question the others assume"),
    Offer(VIDEO, "the pattern and a worked video", ("video_production",), 1.6,
          "whether the difficulty, rather than the design, was what stopped the purchase"),
    Offer(MINI, "two or three patterns that belong together", (), 2.2,
          "whether the buyer wanted a set rather than an object"),
    Offer(COLLECTION, "the full set, as a body of work", (), 4.0,
          "whether this design is an entry to a collection or the whole of the interest"),
    Offer(BEGINNER, "the pattern, a stitch guide and a stated answer time",
          ("support_capacity",), 1.8,
          "whether the buyer's hesitation was about their own skill"),
    Offer(SEASONAL, "the pattern inside an occasion's set", (), 2.5,
          "whether the occasion was doing the selling"),
)
BY_KEY: dict[str, Offer] = {o.key: o for o in OFFERS}

# Offers that differ only in being a bundle are the same experiment. Grouped so "we tried
# three things" cannot mean three bundles.
FAMILIES: dict[str, str] = {
    SINGLE: "bare", VIDEO: "assisted", BEGINNER: "assisted",
    MINI: "bundled", COLLECTION: "bundled", SEASONAL: "bundled",
}

# What this company can actually deliver today. Both are false, and saying so here is what
# stops an undeliverable offer being priced.
CAPABILITIES: dict[str, str] = {
    "video_production": ("nothing in this system can produce a video, and an offer that "
                         "promises one is a refund"),
    "support_capacity": ("a stated answer time is a promise; nobody has measured what this "
                         "company can answer within, so the promise has no basis"),
}

# A design has to have worn more than one shape before its failure is the design's.
MIN_OFFER_FAMILIES_BEFORE_RETIRING = 2
# And each of those shapes has to have been given enough buyers to mean anything.
MIN_BUYERS_PER_OFFER = 15


class OfferRefused(ValueError):
    """An offer that cannot be delivered, or a design retired on one offer's evidence."""


@dataclass
class Result:
    """What one offer did. `None` is unmeasured, and unmeasured is not zero."""

    design_slug: str
    offer: str
    visitors: int | None = None
    buyers: int | None = None
    revenue_cad: float | None = None
    contribution_cad: float | None = None

    def __post_init__(self) -> None:
        if self.offer not in BY_KEY:
            raise OfferRefused(f"{self.offer!r} is not an offer: {sorted(BY_KEY)}")

    @property
    def family(self) -> str:
        return FAMILIES[self.offer]

    def measures(self) -> dict:
        """The two figures the requirement asks for, together and never one alone."""
        cpv = (self.contribution_cad / self.visitors
               if self.contribution_cad is not None and self.visitors else None)
        rpb = (self.revenue_cad / self.buyers
               if self.revenue_cad is not None and self.buyers else None)
        return {
            "contribution_per_visitor": None if cpv is None else round(cpv, 4),
            "revenue_per_buyer": None if rpb is None else round(rpb, 2),
            "buyers": self.buyers, "visitors": self.visitors,
            "why_both": ("revenue per buyer is the one that flatters: a CA$28 collection "
                         "bought by three people looks magnificent beside a CA$6 pattern "
                         "that converts, and loses to it"),
            "unmeasured": [name for name, value in
                           (("visitors", self.visitors), ("buyers", self.buyers),
                            ("revenue_cad", self.revenue_cad),
                            ("contribution_cad", self.contribution_cad)) if value is None],
        }


def available(offer_key: str) -> dict:
    """Whether this offer can be delivered today, and what it waits on if not."""
    if offer_key not in BY_KEY:
        raise OfferRefused(f"{offer_key!r} is not an offer: {sorted(BY_KEY)}")
    offer = BY_KEY[offer_key]
    missing = [n for n in offer.needs if n in CAPABILITIES]
    return {
        "offer": offer_key, "available": not missing,
        "needs": list(offer.needs),
        "why": ("; ".join(CAPABILITIES[n] for n in missing) if missing else
                "nothing outside this system is needed to deliver it"),
        "tests": offer.tests,
    }


def ladder(design_slug: str) -> dict:
    """The offers this design could wear, cheapest first, with what each one would test."""
    rows = []
    for offer in OFFERS:
        state = available(offer.key)
        rows.append({"offer": offer.key, "contains": offer.contains,
                     "posture_vs_single": offer.posture, "family": FAMILIES[offer.key],
                     "tests": offer.tests, "available": state["available"],
                     "why": state["why"]})
    return {"design": design_slug, "offers": rows,
            "deliverable_today": [r["offer"] for r in rows if r["available"]]}


def compare(results: list[Result]) -> dict:
    """The offers this design has worn, and which one is actually ahead.

    Ordered by contribution per visitor, because that is the figure a cost can be set
    against. Any offer whose figures are not measured is listed rather than ranked -- an
    unmeasured offer ranks last in any sort that treats None as zero, which is how the best
    offer nobody measured gets discarded.
    """
    ranked, unranked = [], []
    for r in results:
        m = r.measures()
        row = {"offer": r.offer, "family": r.family, **m}
        (ranked if m["contribution_per_visitor"] is not None else unranked).append(row)
    ranked.sort(key=lambda row: -row["contribution_per_visitor"])
    return {
        "ranked": ranked, "unmeasured": unranked,
        "best": ranked[0]["offer"] if ranked else None,
        "ordered_by": ("contribution per visitor, the only one of the two that can be set "
                       "against a cost"),
        "note": ("no offer here carries enough to be ranked, which is not the same as every "
                 "offer performing equally" if not ranked else ""),
    }


def may_retire(design_slug: str, results: list[Result]) -> dict:
    """Whether a design may be discarded, or whether only its offer has been tested.

    The requirement's own sentence, made mechanical. A design tried once, in one shape, has
    been tested as an offer; discarding it is a judgement about a price and a package that
    has acquired the design's name.
    """
    mine = [r for r in results if r.design_slug == design_slug]
    tried = {r.offer for r in mine}
    families = {r.family for r in mine}
    thin = sorted({r.offer for r in mine
                   if (r.buyers or 0) < MIN_BUYERS_PER_OFFER})

    reasons: list[str] = []
    if len(families) < MIN_OFFER_FAMILIES_BEFORE_RETIRING:
        reasons.append(
            f"tried in {len(families)} offer family ({sorted(families) or 'none'}) against a "
            f"floor of {MIN_OFFER_FAMILIES_BEFORE_RETIRING}. Three bundles are one offer "
            f"tested three times, so the families rather than the count decide")
    if thin:
        reasons.append(
            f"{thin} had fewer than {MIN_BUYERS_PER_OFFER} buyers, so what failed there is "
            f"not established. An offer nobody bought enough of did not lose; it did not run")

    untried = [o.key for o in OFFERS if o.key not in tried and available(o.key)["available"]]
    cheapest = min((BY_KEY[k] for k in untried), key=lambda o: o.posture, default=None)
    return {
        "design": design_slug,
        "may_retire": not reasons,
        "reasons": reasons,
        "tried": sorted(tried), "families": sorted(families),
        "untried_and_deliverable": untried,
        "try_next": (None if cheapest is None else
                     {"offer": cheapest.key, "tests": cheapest.tests}),
        "note": ("the design has worn more than one shape and can be judged as a design"
                 if not reasons else
                 "this is a verdict about an offer that has acquired the design's name. Fix "
                 "the offer before discarding the design"),
    }


def state() -> dict:
    """The offer catalogue, what each tests, and what may not be delivered today."""
    return {
        "offers": [{"offer": o.key, "contains": o.contains, "family": FAMILIES[o.key],
                    "posture_vs_single": o.posture, "tests": o.tests,
                    "available": available(o.key)["available"],
                    "why": available(o.key)["why"]} for o in OFFERS],
        "measures": ["contribution_per_visitor", "revenue_per_buyer"],
        "measure_definitions": {
            "contribution_per_visitor": METRICS["contribution_per_visitor"]["why"],
            "revenue_per_buyer": ("what a buyer spent, which is the figure that flatters a "
                                  "collection nobody buys"),
        },
        "floors": {"offer_families_before_retiring": MIN_OFFER_FAMILIES_BEFORE_RETIRING,
                   "buyers_per_offer": MIN_BUYERS_PER_OFFER},
        "note": ("The same design sold six ways is six propositions, and one failing says "
                 "nothing about the other five. A design tried in one shape has been tested "
                 "as an offer, so retiring it is a verdict about a price and a package "
                 "wearing the design's name (#13)."),
    }
