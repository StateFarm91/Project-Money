"""Which single thing failing would end this company, and whether that is a risk yet.

Requirement 29. The rule has two halves and they pull in opposite directions: *do not allow
one SKU, one holiday, one traffic source, one AI provider or one marketplace to become an
existential dependency* -- and *diversify after a channel or product is understood, without
spreading resources so thin that nothing gets enough focus*.

A module that only implemented the first half would tell a company with eleven products and
no customers to open a second marketplace, which is how a pre-revenue business turns its one
real advantage -- focus -- into five half-built ones. So concentration alone is not a finding
here. A dependency becomes *existential* when it is concentrated **and load-bearing**, and
before it carries anything it is a plan.

That distinction is the whole module, and it is why every axis reports three things rather
than one: how concentrated it is, whether it currently carries value, and which of those two
facts decides the verdict.

**Concentration is counted, never estimated.** Each axis reads rows -- products by department,
products by occasion, configured model providers, marketplaces with a listing, recorded
traffic sources. An axis with nothing in it reports `unmeasurable` with the reason rather
than a comfortable zero, because "no traffic source is dominant" is true of a company with no
traffic and is not the sentence anybody should read.

**The uncomfortable ones are real.** Today four of the five axes sit at 100% concentration:
one model provider, one marketplace, one department and one make lane. Three of those are not
yet load-bearing, which is the honest verdict and not an excuse -- the module says which, and
says what would make them count.
"""
from __future__ import annotations

from dataclasses import dataclass

# Above this share of an axis held by one thing, the axis is concentrated. Not a target to
# engineer down: a two-product company is 50% concentrated by arithmetic and that is fine.
CONCENTRATED_ABOVE = 0.60

# Below this many distinct holders, an axis cannot be anything but concentrated, and saying
# so is more useful than a percentage.
TOO_FEW_TO_SPREAD = 2

# The other half of the rule. More live holders than this per validated product and the
# company is spreading a thin thing thinner rather than diversifying something understood.
HOLDERS_PER_PRODUCT_CEILING = 1.0

UNMEASURABLE, PLAN, EXISTENTIAL, SOUND = (
    "unmeasurable", "concentrated_but_not_load_bearing", "existential", "sound")


@dataclass(frozen=True)
class Axis:
    key: str
    what: str
    why_it_ends_the_company: str
    load_bearing_when: str


AXES: tuple[Axis, ...] = (
    Axis("sku", "how much of the catalogue is one product or one department",
         "a catalogue that is one idea fails entirely when that idea stops selling",
         "a product is selling"),
    Axis("occasion", "how much of the catalogue depends on one occasion",
         "a year's revenue arriving in six weeks is a year that can be missed once",
         "an occasion has produced revenue"),
    Axis("traffic_source", "how much of the demand arrives through one route",
         "a channel that changes its ranking overnight takes the whole quarter with it",
         "traffic has been recorded"),
    Axis("ai_provider", "how much of the system's judgement runs on one provider",
         "a provider outage or a price change stops every agent at once",
         "the system depends on model calls to operate"),
    Axis("marketplace", "how much of the business lives on one platform",
         "a policy change or a suspension is the end, and there is no appeal worth having",
         "a listing is live and earning"),
)

AXIS_BY_KEY: dict[str, Axis] = {a.key: a for a in AXES}


def _concentration(holders: dict[str, int | float]) -> dict:
    """The share held by the largest holder, and how many holders there are."""
    total = sum(holders.values())
    if not holders or total <= 0:
        return {"holders": 0, "largest": None, "share": None}
    largest = max(holders.items(), key=lambda kv: kv[1])
    return {"holders": len(holders), "largest": largest[0],
            "share": round(largest[1] / total, 3)}


def assess(axis_key: str, holders: dict[str, int | float], *, load_bearing: bool,
           reason: str = "") -> dict:
    """One axis: how concentrated, whether it carries anything, and what that means.

    The verdict is the point. `existential` requires both concentration and load: a single
    provider the company genuinely runs on is a risk, and a single marketplace it has never
    sold on is a plan. Calling the second one existential would be alarming and wrong, and a
    risk report nobody believes is a risk report nobody reads.
    """
    axis = AXIS_BY_KEY.get(axis_key)
    if axis is None:
        raise KeyError(f"{axis_key!r} is not a dependency axis: {sorted(AXIS_BY_KEY)}")

    counts = _concentration(holders)
    if not counts["holders"]:
        return {
            "axis": axis.key, "what": axis.what, "verdict": UNMEASURABLE,
            "load_bearing": load_bearing, **counts,
            "why": (reason or f"nothing has been recorded on this axis, so whether it is "
                              f"concentrated is unknown -- which is not the same as spread"),
            "would_count_when": axis.load_bearing_when,
        }

    concentrated = (counts["holders"] < TOO_FEW_TO_SPREAD
                    or (counts["share"] or 0) > CONCENTRATED_ABOVE)
    if not concentrated:
        verdict, why = SOUND, (
            f"the largest holder is {counts['share']:.0%} of {counts['holders']}, under "
            f"{CONCENTRATED_ABOVE:.0%}")
    elif load_bearing:
        verdict, why = EXISTENTIAL, (
            f"{counts['largest']!r} holds {counts['share']:.0%} of this axis and the axis "
            f"carries real weight: {axis.why_it_ends_the_company}")
    else:
        verdict, why = PLAN, (
            f"{counts['largest']!r} holds {counts['share']:.0%} of this axis, and the axis "
            f"is not carrying anything yet. Diversifying it now would spread a thin thing "
            f"thinner -- the rule says diversify *after* a channel is understood")
    return {
        "axis": axis.key, "what": axis.what, "verdict": verdict,
        "load_bearing": load_bearing, **counts, "why": why,
        "would_count_when": axis.load_bearing_when,
    }


def report(db) -> dict:
    """Every axis, read from rows, with the two halves of #29 both applied."""
    from sqlalchemy import select

    from ..core.models import LedgerEntry, Listing, Product
    from ..creative.audit import catalogue_concepts
    from ..gateway.model_gateway import available_providers

    with db.session() as s:
        products = list(s.scalars(select(Product)))
        listings = list(s.scalars(select(Listing)))
        earning = bool(s.scalar(select(LedgerEntry.id).limit(1)))

    concepts = catalogue_concepts()
    by_pod: dict[str, int] = {}
    by_occasion: dict[str, int] = {}
    for concept in concepts:
        by_pod[concept.pod] = by_pod.get(concept.pod, 0) + 1
        by_occasion[concept.occasion] = by_occasion.get(concept.occasion, 0) + 1

    providers = {name: 1 for name in available_providers()}
    # A marketplace counts once a listing exists for it, drafted or live. Etsy is the only
    # integration this company has, so this reads one by construction today -- and saying so
    # from a count rather than from a constant is what makes it change by itself later.
    marketplaces: dict[str, int] = {}
    if listings:
        marketplaces["etsy"] = len(listings)

    axes = [
        assess("sku", by_pod, load_bearing=earning),
        assess("occasion", by_occasion, load_bearing=earning),
        assess("traffic_source", {}, load_bearing=False,
               reason=("no traffic has been recorded, because nothing is published. An "
                       "empty traffic mix is not a diversified one")),
        # The one axis that is load-bearing today. Nothing in this system operates without
        # model calls, and there is exactly one provider configured.
        assess("ai_provider", providers, load_bearing=True,
               reason=("no model provider is configured, so nothing in this system that "
                       "needs judgement can run at all. That is a different state from a "
                       "diversified one and a worse one")),
        assess("marketplace", marketplaces, load_bearing=earning),
    ]

    live = [a for a in axes if a["verdict"] == EXISTENTIAL]
    plans = [a for a in axes if a["verdict"] == PLAN]

    # The counter-rule, checked rather than remembered. Diversifying an axis before the
    # catalogue can carry it is the failure the requirement's second clause names.
    validated = len(products)
    spread = sum(a["holders"] or 0 for a in axes)
    # With no validated product the ratio is undefined, and returning False for it would
    # read as "the spread is fine" for a company carrying seven holders and nothing to put
    # on them -- the most spread-too-thin a company can be. Undefined is reported as
    # undefined, which is the rule this module applies to every other absent number.
    too_thin = (None if not validated
                else spread / validated > HOLDERS_PER_PRODUCT_CEILING)

    return {
        "axes": axes,
        "existential": [a["axis"] for a in live],
        "not_load_bearing_yet": [a["axis"] for a in plans],
        "unmeasurable": [a["axis"] for a in axes if a["verdict"] == UNMEASURABLE],
        "focus": {
            "validated_products": validated,
            "distinct_holders_across_axes": spread,
            "spread_too_thin": too_thin,
            "ceiling": HOLDERS_PER_PRODUCT_CEILING,
            "why": (
                f"no validated product exists, so holders-per-product is undefined. "
                f"{spread} holders and nothing to carry on them is not a spread that is "
                f"fine, it is a spread that has not been tested" if too_thin is None else
                "more distinct holders than validated products means the company is "
                "spreading a thin thing thinner rather than diversifying something it "
                "understands, which is the half of #29 that a concentration report usually "
                "forgets" if too_thin else
                "the spread the company carries is within what its catalogue supports"),
        },
        "note": ("Concentration alone is not a finding. A dependency is existential when it "
                 "is concentrated *and* load-bearing; before it carries anything it is a "
                 "plan, and telling a pre-revenue company to open a second marketplace is "
                 "how its one real advantage becomes five half-built ones (#29)."),
    }
