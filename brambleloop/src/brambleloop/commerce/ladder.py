"""The value ladder, and the discount that quietly removes its bottom rung.

Requirement 233. Free or low-friction content, an entry pattern, a premium single, a mini
bundle, a flagship collection, and then the repeat purchase that makes all of it worth
having. The requirement asks for the ladder to be *engineered* rather than described, which
means two things this module can do today and two it cannot.

What it can do is say where the ladder is broken. A rung with no product on it is not a gap
in a diagram; it is a place a buyer arrives and finds nothing, and the commonest shape is a
catalogue of premium singles with free content pointing at them and nothing in between. The
step between two occupied rungs matters too: a buyer who has spent CA$6 does not next spend
CA$40, and a ladder whose next rung is six times the last one is a ladder with a missing
step wearing a price.

And it can refuse the discount that dismantles it. *Avoid discounts that train customers to
ignore regular pricing* is the requirement's own sentence, and the mechanism is specific: a
price that is on sale a third of the time is not a price, it is a higher number that appears
before the real one. The rules live in `commerce.promotion` and are imported rather than
restated; what this module adds is the per-tier reading, because the damage differs by rung.
Discounting the entry pattern teaches a buyer to wait, which is survivable. Discounting the
flagship collection devalues the only product whose job is to say what this shop is worth,
and no later full price recovers it.

What it cannot do is measure movement between tiers, attach rate, contribution or lifetime
value. Every one of those needs a customer, and there are none. They are reported as
unmeasurable with what they need, because a tier-movement rate computed from zero buyers is
a division this module declines to perform and a number somebody would quote.
"""
from __future__ import annotations

from dataclasses import dataclass

from .promotion import MAX_PROMOTION_DAYS, STEEP_DISCOUNT_ABOVE

FREE = "free_content"
ENTRY = "entry_pattern"
PREMIUM = "premium_single"
MINI = "mini_bundle"
FLAGSHIP = "flagship_collection"
REPEAT = "repeat_purchase"

# In order, because the whole idea is that each rung is reachable from the one below it.
TIERS: tuple[str, ...] = (FREE, ENTRY, PREMIUM, MINI, FLAGSHIP, REPEAT)


@dataclass(frozen=True)
class Tier:
    key: str
    what: str
    asks: str                 # what the buyer has to decide at this rung
    typical_cad: tuple[float, float]


LADDER: tuple[Tier, ...] = (
    Tier(FREE, "a motif, a mini pattern, a tutorial or a tool",
         "nothing but attention, and it must be worth the attention on its own", (0.0, 0.0)),
    Tier(ENTRY, "one small finished object at the lowest honest price",
         "whether this shop's instructions can be followed", (4.0, 6.0)),
    Tier(PREMIUM, "a full pattern with the depth the catalogue is known for",
         "whether the work is worth more than the cheapest thing on the page", (6.0, 14.0)),
    Tier(MINI, "two or three patterns that belong together",
         "whether the set is worth more than the pattern they came for", (12.0, 25.0)),
    Tier(FLAGSHIP, "the full collection, as a body of work",
         "whether this shop is worth committing to", (25.0, 60.0)),
    Tier(REPEAT, "the next season's collection, bought because the last one was good",
         "nothing new: the decision was made by the previous purchase", (0.0, 0.0)),
)
BY_KEY: dict[str, Tier] = {t.key: t for t in LADDER}

# A rung more than this multiple above the one below it is a step a buyer does not take.
MAX_STEP_MULTIPLE = 3.0
# A tier discounted on more than this share of its live days has no regular price left.
DISCOUNT_DAYS_SHARE = 0.33
# The rungs where a discount does lasting damage rather than temporary damage.
NEVER_ROUTINELY_DISCOUNTED: tuple[str, ...] = (FLAGSHIP,)


class LadderRefused(ValueError):
    """A tier nobody named, or a measurement with no buyers behind it."""


def _check(tier: str) -> None:
    if tier not in BY_KEY:
        raise LadderRefused(f"{tier!r} is not a tier: {list(TIERS)}")


def shape(products: list[dict]) -> dict:
    """Which rungs are occupied, where the gaps are, and where the steps are too big.

    Each product is {slug, tier, price_cad}. A rung with nothing on it is a place a buyer
    arrives and finds nothing, which is a different finding from a rung that is merely thin.
    """
    occupied: dict[str, list[dict]] = {t: [] for t in TIERS}
    for product in products:
        _check(product["tier"])
        occupied[product["tier"]].append(product)

    empty = [t for t in TIERS if not occupied[t] and t not in (FREE, REPEAT)]
    # FREE and REPEAT are excluded from the gap list on purpose: free content is #10's
    # subject and a repeat purchase is an outcome rather than a product somebody builds.

    steps = []
    priced = [t for t in TIERS if occupied[t] and BY_KEY[t].typical_cad[1] > 0]
    for lower, upper in zip(priced, priced[1:]):
        low = min(p["price_cad"] for p in occupied[lower])
        high = min(p["price_cad"] for p in occupied[upper])
        multiple = (high / low) if low else None
        steps.append({
            "from": lower, "to": upper,
            "from_cad": round(low, 2), "to_cad": round(high, 2),
            "multiple": None if multiple is None else round(multiple, 2),
            "too_big": bool(multiple and multiple > MAX_STEP_MULTIPLE),
            "why": ("" if not multiple or multiple <= MAX_STEP_MULTIPLE else
                    f"a buyer who has spent CA${low:.2f} does not next spend CA${high:.2f}. "
                    f"A rung {multiple:.1f} times the last one is a missing step wearing a "
                    f"price"),
        })

    return {
        "occupied": {t: len(occupied[t]) for t in TIERS},
        "empty_rungs": empty,
        "steps": steps,
        "climbable": not empty and not any(s["too_big"] for s in steps),
        "note": ("every rung a buyer can arrive on has something on it" if not empty else
                 f"{empty} have nothing on them. A buyer who climbs to one of these arrives "
                 f"and finds nothing, which is not a gap in a diagram"),
    }


def check_discount(tier: str, *, full_price_cad: float, promo_price_cad: float,
                   days_discounted: int, days_live: int) -> dict:
    """Whether this discount trains the buyer to ignore the price.

    The depth and duration rules are `commerce.promotion`'s, imported rather than restated.
    What is added here is that the damage differs by rung.
    """
    _check(tier)
    if full_price_cad <= 0 or days_live <= 0:
        raise LadderRefused("a discount needs a full price and a period it was live in")

    depth = 1 - (promo_price_cad / full_price_cad)
    share = days_discounted / days_live
    reasons: list[str] = []

    if share > DISCOUNT_DAYS_SHARE:
        reasons.append(
            f"discounted on {share:.0%} of its live days. A price that is on sale a third of "
            f"the time is not a price, it is a higher number that appears before the real "
            f"one, and the buyer learns to wait")
    if days_discounted > MAX_PROMOTION_DAYS:
        reasons.append(f"{days_discounted} days against a ceiling of {MAX_PROMOTION_DAYS}: "
                       f"past that it is the price")
    if depth > STEEP_DISCOUNT_ABOVE:
        reasons.append(f"{depth:.0%} off, against {STEEP_DISCOUNT_ABOVE:.0%}. A discount "
                       f"this deep says the full price was the invention")
    if tier in NEVER_ROUTINELY_DISCOUNTED and days_discounted > 0:
        reasons.append(
            f"the {tier} is the one product whose job is to say what this shop is worth. "
            f"Discounting it devalues that claim, and no later full price recovers it")

    return {"tier": tier, "ok": not reasons, "reasons": reasons,
            "depth": round(depth, 3), "share_of_days": round(share, 3),
            "ceilings": {"days": MAX_PROMOTION_DAYS, "depth": STEEP_DISCOUNT_ABOVE,
                         "share_of_days": DISCOUNT_DAYS_SHARE}}


def movement(cohorts: list[dict]) -> dict:
    """How buyers move between rungs, or why that cannot be said.

    Each cohort is {from_tier, to_tier, buyers, moved}. With no buyers the rate is a
    division this module declines to perform, because the number would be quoted.
    """
    rows = []
    for cohort in cohorts:
        _check(cohort["from_tier"])
        _check(cohort["to_tier"])
        buyers = int(cohort["buyers"])
        moved = int(cohort["moved"])
        if moved > buyers:
            raise LadderRefused(
                f"{moved} moved out of {buyers} buyers, which is a counting fault rather "
                f"than a remarkable ladder")
        rows.append({"from": cohort["from_tier"], "to": cohort["to_tier"],
                     "buyers": buyers, "moved": moved,
                     "rate": round(moved / buyers, 4) if buyers else None,
                     "why": "" if buyers else "no buyer has ever stood on this rung"})

    measured = [r for r in rows if r["rate"] is not None]
    return {
        "movements": rows, "measured": len(measured), "of": len(rows),
        "weakest": (min(measured, key=lambda r: r["rate"])["from"] if measured else None),
        "note": ("nothing has been measured: no customer exists, so tier movement, attach "
                 "rate, contribution and lifetime value are all unmeasurable rather than "
                 "zero. The ladder's shape and its discount discipline are what can be "
                 "engineered today, and both are" if not measured else ""),
    }


def lifetime_value(buyers: list[dict]) -> dict:
    """Contribution per buyer over their whole relationship, or what it needs."""
    if not buyers:
        return {"measurable": False, "buyers": 0,
                "why": ("lifetime value needs a lifetime, which needs a second purchase. "
                        "A figure computed from first purchases is an average order value "
                        "with a longer name"),
                "needs": ["repeat purchases"]}
    repeat = [b for b in buyers if int(b.get("orders", 0)) > 1]
    if not repeat:
        return {"measurable": False, "buyers": len(buyers), "repeat_buyers": 0,
                "why": ("every buyer has bought once, so this is an average order value with "
                        "a longer name rather than a lifetime value"),
                "needs": ["a second purchase by somebody"]}
    total = sum(float(b.get("contribution_cad", 0.0)) for b in buyers)
    return {"measurable": True, "buyers": len(buyers), "repeat_buyers": len(repeat),
            "contribution_per_buyer_cad": round(total / len(buyers), 2)}


def state() -> dict:
    """The rungs, the steps between them, and what a discount is allowed to do."""
    return {
        "tiers": [{"tier": t.key, "what": t.what, "asks": t.asks,
                   "typical_cad": list(t.typical_cad)} for t in LADDER],
        "max_step_multiple": MAX_STEP_MULTIPLE,
        "discount": {"max_days": MAX_PROMOTION_DAYS,
                     "max_depth": STEEP_DISCOUNT_ABOVE,
                     "max_share_of_days": DISCOUNT_DAYS_SHARE,
                     "never_routinely_discounted": list(NEVER_ROUTINELY_DISCOUNTED)},
        "unmeasurable_today": ["tier movement", "attach rate", "contribution",
                               "lifetime value"],
        "note": ("A price that is on sale a third of the time is not a price, it is a higher "
                 "number that appears before the real one. The flagship is the one product "
                 "whose job is to say what this shop is worth, so discounting it devalues "
                 "the claim and no later full price recovers it (#233)."),
    }
