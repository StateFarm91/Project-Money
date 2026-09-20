"""Where the week goes, and why the default is not more engineering.

Requirement 30. After core engineering stabilises, the mature allocation is roughly 30%
product and QA, 30% market intelligence and product selection, 30% distribution and growth,
and 10% infrastructure and operations, adjusted to whatever is currently binding.

The requirement states the failure it is preventing, and it is worth repeating in the words
it uses: *endless technical polishing starving distribution*. That is not a risk this system
is unusually exposed to -- it is the one it is most exposed to. Engineering work is always
available, always visible, always finishes, and never requires anybody outside this company
to do anything. Distribution requires an audience that does not exist yet, and every hour
spent on it can be defensibly deferred until the thing being distributed is better. A shop
can be improved indefinitely and shown to nobody, and at no point does a week feel wasted.

So the module makes three commitments.

**The mature mix is the default, not the reward.** The natural default for a system with no
audience is to do more engineering, because engineering is the work that is here. That is
exactly the slide, so the mix arrives as a number rather than as whatever was easiest to
pick up.

**Distribution has a floor that a bottleneck cannot cross.** A tilt may move work toward the
binding constraint and may not take distribution below its floor, because the week that
starves distribution always has a reason and the reasons are always good.

**An unmeasured bottleneck is not a bottleneck.** `scale.runrate.constraint()` says when it
cannot identify the binding term, and this module does not tilt on a guess. Guessing here
does not produce a random answer: it produces whichever term somebody has a benchmark for,
which in practice is the one nearest the code.

Before core engineering stabilises the mature mix is wrong, and saying so is not a loophole.
A system whose release chain is still moving cannot distribute anything safely, and this
module reads that condition from `commerce.lanes.qa_stable` -- the same evidence #5 reads,
imported rather than restated, because two definitions of "stable" is one definition and one
excuse.
"""
from __future__ import annotations

from ..commerce.lanes import qa_stable  # noqa: F401  (re-exported for callers)

PRODUCT_QA = "product_qa"
MARKET_INTELLIGENCE = "market_intelligence"
DISTRIBUTION = "distribution"
INFRASTRUCTURE = "infrastructure"

FUNCTIONS: dict[str, str] = {
    PRODUCT_QA: "designing, compiling, testing and certifying the patterns themselves",
    MARKET_INTELLIGENCE: "what to make next, for whom, at what price, in what shape",
    DISTRIBUTION: "listings, search, owned surfaces, creators, email -- being findable",
    INFRASTRUCTURE: "the platform, the deployment, the cost ceilings, the operator tools",
}

# The requirement's own numbers.
MATURE_MIX: dict[str, float] = {
    PRODUCT_QA: 0.30, MARKET_INTELLIGENCE: 0.30, DISTRIBUTION: 0.30, INFRASTRUCTURE: 0.10,
}

# Before the release chain is steady, this is the honest shape and it is not a failure --
# with one exception that is the whole requirement. Distribution keeps its floor during the
# build too. The first draft here had it at 15%, below the floor this module enforces
# everywhere else, with a docstring claiming the build mix respected it; that is precisely
# the slide, written by the module that exists to stop it, and the floor is the reason it
# was caught rather than shipped.
BUILD_MIX: dict[str, float] = {
    PRODUCT_QA: 0.45, MARKET_INTELLIGENCE: 0.20, DISTRIBUTION: 0.20, INFRASTRUCTURE: 0.15,
}

# Floors no tilt may cross. Distribution's is the one the requirement is about; the others
# exist so a tilt toward distribution cannot hollow out the thing being distributed.
FLOORS: dict[str, float] = {
    PRODUCT_QA: 0.15, MARKET_INTELLIGENCE: 0.15, DISTRIBUTION: 0.20, INFRASTRUCTURE: 0.05,
}
# And a ceiling on the work that is always available and always defensible.
INFRASTRUCTURE_CEILING = 0.25

# How much one bottleneck may move. Enough to matter in a week, not enough to become a
# different company by Thursday.
TILT_SHARE = 0.10

# Which function can actually move each binding term, and why it is that one. Written down
# because the tempting mapping is "whatever we were going to do anyway".
TILT_FOR: dict[str, tuple[str, str]] = {
    "traffic": (DISTRIBUTION, "nobody is arriving, and no amount of pattern work changes "
                              "that"),
    "ctr": (DISTRIBUTION, "being chosen in a feed of forty similar thumbnails is "
                          "distribution work, whatever it feels like"),
    "conversion": (PRODUCT_QA, "people are arriving and leaving: what the page promises and "
                               "whether the product visibly backs it"),
    "aov": (MARKET_INTELLIGENCE, "what is being sold and in what shape, which is a "
                                 "selection question before it is a pricing one"),
    "repeat_rate": (PRODUCT_QA, "a second purchase is a verdict on the first one, and it is "
                                "passed after the pattern is used rather than bought"),
    "margin": (PRODUCT_QA, "a defect is a quality problem before it is a cost, and scaling "
                           "one multiplies it"),
    "product_coverage": (MARKET_INTELLIGENCE, "there is not enough to sell, which is a "
                                              "selection question"),
}


class AllocationRefused(ValueError):
    """A mix that starves a function, or a tilt toward a bottleneck nobody measured."""


def check_mix(mix: dict[str, float]) -> dict:
    """Every reason this allocation may not be run. Empty means it may."""
    unknown = sorted(set(mix) - set(FUNCTIONS))
    if unknown:
        raise AllocationRefused(f"{unknown} are not functions: {sorted(FUNCTIONS)}")

    reasons: list[str] = []
    total = sum(mix.get(f, 0.0) for f in FUNCTIONS)
    if abs(total - 1.0) > 1e-9:
        reasons.append(f"the shares total {total:.2f} rather than 1.00, so this is not an "
                       f"allocation of a week")
    for function, floor in FLOORS.items():
        share = mix.get(function, 0.0)
        if share < floor - 1e-9:
            reasons.append(
                f"{function} at {share:.0%} against a floor of {floor:.0%}"
                + (". This is the requirement's own failure: engineering work is always "
                   "available and always defensible, and a shop can be improved "
                   "indefinitely and shown to nobody"
                   if function == DISTRIBUTION else ""))
    if mix.get(INFRASTRUCTURE, 0.0) > INFRASTRUCTURE_CEILING + 1e-9:
        reasons.append(
            f"infrastructure at {mix[INFRASTRUCTURE]:.0%} against a ceiling of "
            f"{INFRASTRUCTURE_CEILING:.0%}: the platform is how the work happens and is not "
            f"the work")
    return {"mix": {f: round(mix.get(f, 0.0), 4) for f in FUNCTIONS},
            "ok": not reasons, "reasons": reasons,
            "floors": dict(FLOORS), "infrastructure_ceiling": INFRASTRUCTURE_CEILING}


def _tilt(base: dict[str, float], toward: str) -> dict[str, float]:
    """Move `TILT_SHARE` into one function, taking it from whoever can spare it."""
    mix = dict(base)
    owed = TILT_SHARE
    # Take from the largest surpluses first, so the tilt costs the function that is furthest
    # from its floor rather than the one that happens to be listed first.
    donors = sorted((f for f in FUNCTIONS if f != toward),
                    key=lambda f: -(mix[f] - FLOORS[f]))
    for function in donors:
        spare = max(0.0, mix[function] - FLOORS[function])
        take = min(spare, owed)
        mix[function] -= take
        owed -= take
        if owed <= 1e-9:
            break
    mix[toward] += TILT_SHARE - owed
    return {f: round(v, 4) for f, v in mix.items()}


def allocate(*, qa: dict, constraint: dict | None = None) -> dict:
    """This period's allocation, and the reasoning that produced it.

    `qa` is the verdict from `commerce.lanes.qa_stable` and `constraint` the verdict from
    `scale.runrate.constraint`, both passed as the evidence they are rather than as flags.
    """
    if not isinstance(qa, dict) or "stable" not in qa:
        raise AllocationRefused(
            "allocate() needs the verdict from qa_stable(), not a flag: 'after core "
            "engineering stabilizes' is a condition about evidence")

    if not qa["stable"]:
        return {
            "mix": dict(BUILD_MIX), "phase": "build",
            "mature_mix_applies": False,
            "why": qa["reasons"],
            "note": ("the release chain is still moving, so the mature mix is not yet the "
                     "right shape and saying so is not a loophole: a system that cannot "
                     "certify reliably cannot distribute safely. The build mix still holds "
                     "distribution above its floor, because the thing this requirement "
                     "prevents starts during the build"),
        }

    base = dict(MATURE_MIX)
    if constraint is None or not constraint.get("identifiable"):
        return {
            "mix": base, "phase": "mature", "mature_mix_applies": True,
            "tilted_toward": None,
            "why": ((constraint or {}).get("reason")
                    or "no constraint verdict was supplied, and a bottleneck nobody "
                       "measured is not a bottleneck"),
            "note": ("the mature mix, untilted. Guessing the bottleneck does not produce a "
                     "random answer -- it produces whichever term somebody has a benchmark "
                     "for, which is the one nearest the code"),
        }

    term = constraint.get("constraint", "")
    if term not in TILT_FOR:
        raise AllocationRefused(
            f"{term!r} is not a term this allocation knows how to move: "
            f"{sorted(TILT_FOR)}. A tilt toward an unmapped constraint is a tilt toward "
            f"whatever we were going to do anyway")

    toward, because = TILT_FOR[term]
    mix = _tilt(base, toward)
    verdict = check_mix(mix)
    if not verdict["ok"]:  # pragma: no cover - the floors make this unreachable today
        raise AllocationRefused("; ".join(verdict["reasons"]))
    return {
        "mix": mix, "phase": "mature", "mature_mix_applies": True,
        "constraint": term, "tilted_toward": toward, "because": because,
        "moved": TILT_SHARE,
        "note": (f"{TILT_SHARE:.0%} moved toward {toward} for the binding term {term!r}. "
                 f"No floor was crossed: a tilt may follow the constraint and may not "
                 f"starve a function, because the week that starves distribution always has "
                 f"a reason and the reasons are always good"),
    }


def state() -> dict:
    """The mix, the floors, and what each function is."""
    return {
        "functions": dict(FUNCTIONS),
        "mature_mix": dict(MATURE_MIX),
        "build_mix": dict(BUILD_MIX),
        "floors": dict(FLOORS),
        "infrastructure_ceiling": INFRASTRUCTURE_CEILING,
        "tilt_share": TILT_SHARE,
        "tilt_map": {term: {"toward": toward, "because": why}
                     for term, (toward, why) in TILT_FOR.items()},
        "note": ("Engineering work is always available, always visible and never requires "
                 "anybody outside this company, so it is the default unless a number says "
                 "otherwise. Distribution has a floor no bottleneck may cross, and an "
                 "unmeasured bottleneck is not a bottleneck (#30)."),
    }
