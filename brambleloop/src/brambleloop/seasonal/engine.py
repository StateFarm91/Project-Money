"""A year with many occasions in it, and the constant that says this is a Christmas company.

Requirement 33. Replace the Christmas Strike Team with a permanent 365-day seasonal revenue
engine: an evergreen base, rolling seasonal waves, trend opportunities and breakout
amplification, across three simultaneous horizons, with capacity allocated from scores rather
than from a fixed percentage. The requirement's merge instruction is explicit -- *preserve
Christmas as the current campaign, not the company identity.*

The first thing to say is what is already here. `seasonal.calendar` holds the rolling horizons
and each event's launchable lane, `seasonal.compression` retires lanes and shifts the mix as
an occasion closes, `seasonal.leadtime` turns make-time into a launch date, and
`seasonal.rollforward` moves capacity between occasions on two clocks. None of that is
rebuilt.

The second thing is harder and is the reason this module exists.
`compression.PRIORITY_PROGRAMMES` was `{"Christmas": 0.45}` -- a constant, naming one
occasion, granting it nearly half of engineering capacity permanently, read by five modules.
That *was* the Christmas Strike Team, in code, and no amount of rolling-wave machinery around
it changed what it said. A company whose seasonal strategy is a dict with one festival in it
is a Christmas company that also does other things.

It is now `compression.CURRENT_CAMPAIGN_SEED`, read only through
`compression.priority_shares()`, which returns the scores when any occasion has them and the
seed labelled `current_campaign_seed` when none does. The seed survives because the evidence
does not yet exist: scoring an occasion needs observed demand, visibility and competitive
weakness, and a straight cutover would score every occasion at zero and reserve nothing for
the campaign whose making window is actually open. That is not rigour, it is absence. What
changed is that the owner's decision can no longer be read as a measurement, and the day any
occasion scores, the score wins.

So priority here comes from a score, and the score has no favourites:

**Seven factors, multiplied, because they are conjunctive.** Expected demand, achievable
visibility, contribution potential, time remaining, product fit, competitive weakness and
production feasibility. Multiplied rather than averaged: an occasion with no time remaining
scores zero however strong its demand, and an average would let six good factors carry one
fatal one — which is the same reason `scale.confidence` takes a minimum rather than a mean.

**The evergreen floor is the inverse of the priority floor, and nothing had it.**
`MIN_PRIORITY_SHARE` stops a seasonal programme decaying to a rounding error. Nothing stopped
*evergreen* being squeezed to zero by an aggressive seasonal allocation — and a shop that goes
entirely into Christmas has nothing to sell in February, which is exactly when it needs
something. The floor is enforced before any seasonal share is granted, not checked afterwards.

**A squad that cannot be deactivated is a permanent cost justified once.** The requirement
says they are not permanent token-burning agents, and the only way that stays true is if
standing down is as mechanical as spinning up: a squad deactivates when its score falls below
the alternatives, by arithmetic rather than by anybody noticing.

**Reuse crosses seasons; designs do not.** A validated construction primitive and a commercial
lesson may move from Halloween to Christmas. The motifs, the colourway and the design may not,
and recolouring last October's product is the failure the requirement names by name.

**Emergency mode reallocates and cannot touch a gate.** "Emergency" is the word people use
when they want to skip a step, so the override is scoped to allocation by construction: the
refusal list is explicit, and there is no argument by which a breakout raises it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---- the three horizons ---------------------------------------------------

NOW = "now_monetize"
NEXT = "next_build"
LATER = "later_research"

HORIZONS: tuple[str, ...] = (NOW, NEXT, LATER)

HORIZON_MEANS: dict[str, str] = {
    NOW: "customers are searching for this today, and something is listed to find",
    NEXT: "the shopping and making windows open soon; build and index before they do",
    LATER: "needs engineering, indexing and audience months ahead of the occasion",
}

# Where the boundaries sit, in days to the event. Derived from the lead-time engine's own
# arithmetic rather than chosen: a maker needs the make window plus the indexing ramp, and
# an occasion inside that is one somebody is already shopping for.
NOW_WITHIN_DAYS = 45
NEXT_WITHIN_DAYS = 150


# The seasonal universe, as the requirement lists it. Open at the end on purpose -- "and
# other evidence-backed occasions" is in the requirement, and an occasion that shows up in
# the evidence should not need a code change to be worked.
UNIVERSE: tuple[str, ...] = (
    "Christmas", "winter", "Valentine's", "Easter", "Mother's Day", "Father's Day",
    "weddings", "baby showers", "births/nursery", "graduation", "teacher gifts",
    "spring/garden", "summer/cottage", "Canada Day", "July 4", "back-to-school",
    "fall/autumn", "Halloween", "Canadian Thanksgiving", "U.S. Thanksgiving", "birthdays",
    "housewarming",
)

# Durable categories the evergreen base is made of, per the requirement.
EVERGREEN_CATEGORIES: tuple[str, ...] = (
    "baby", "amigurumi", "blankets", "accessories", "garments", "bags", "gifts",
    "home_decor",
)

# Evergreen never drops to zero. The number is a floor rather than a target: seasonal work
# may take everything above it and nothing below.
EVERGREEN_FLOOR = 0.20

# Below this score an active squad stands down. Stated so that deactivation is arithmetic
# rather than a decision somebody makes in a week when they are busy.
SQUAD_STANDDOWN_SCORE = 0.08

# How far above the category baseline a SKU must run before breakout mode is warranted.
BREAKOUT_MULTIPLE = 3.0


class EngineRefused(ValueError):
    """A score with a missing factor, an allocation below the evergreen floor, or a
    breakout asked to move a gate."""


# ---- the opportunity score ------------------------------------------------

FACTORS: dict[str, str] = {
    "expected_demand": "how many people will be looking, from observation not intuition",
    "achievable_visibility": "whether this shop can actually be found for it",
    "contribution_potential": "what is left after fees, per unit of making time",
    "time_remaining": "whether the work can still reach a buyer in time",
    "product_fit": "whether the catalogue's construction vocabulary covers it",
    "competitive_weakness": "whether the incumbents are beatable on anything that matters",
    "production_feasibility": "whether this shop can make it at all, at this skill level",
}


@dataclass(frozen=True)
class Opportunity:
    """One occasion's score, and the evidence each factor came from."""

    event: str
    days_away: int
    factors: dict[str, float]
    basis: str = ""

    def __post_init__(self) -> None:
        missing = sorted(set(FACTORS) - set(self.factors))
        if missing:
            raise EngineRefused(
                f"{self.event}: {missing} have no value. A factor left out of a product is a "
                f"factor silently set to one, which is the most optimistic possible "
                f"assumption and the one nobody notices making")
        unknown = sorted(set(self.factors) - set(FACTORS))
        if unknown:
            raise EngineRefused(f"{self.event}: {unknown} are not factors: {sorted(FACTORS)}")
        for name, value in self.factors.items():
            if not 0.0 <= value <= 1.0:
                raise EngineRefused(
                    f"{self.event}: {name}={value} is outside 0..1. These multiply, so a "
                    f"value above one lets a single strong factor manufacture a score")

    @property
    def score(self) -> float:
        """Multiplied, not averaged: the factors are conjunctive.

        An occasion with no time remaining scores zero however strong its demand, and an
        average would let six good factors carry one fatal one -- the same reason
        `scale.confidence` takes a minimum over its rungs rather than a mean.
        """
        total = 1.0
        for name in FACTORS:
            total *= self.factors[name]
        return total

    @property
    def horizon(self) -> str:
        if self.days_away <= NOW_WITHIN_DAYS:
            return NOW
        if self.days_away <= NEXT_WITHIN_DAYS:
            return NEXT
        return LATER

    @property
    def binding_factor(self) -> str:
        return min(FACTORS, key=lambda name: self.factors[name])

    def to_dict(self) -> dict:
        return {"event": self.event, "days_away": self.days_away,
                "score": round(self.score, 6), "horizon": self.horizon,
                "horizon_means": HORIZON_MEANS[self.horizon],
                "factors": {k: round(v, 3) for k, v in sorted(self.factors.items())},
                "binding_factor": self.binding_factor,
                "binding_means": FACTORS[self.binding_factor],
                "basis": self.basis}


def allocate(opportunities: list[Opportunity], *,
             evergreen_floor: float = EVERGREEN_FLOOR) -> dict:
    """Capacity across the occasions and the evergreen base, from scores rather than names.

    The evergreen floor is taken first and seasonal work divides what is left. Taken first
    rather than checked afterwards, because a floor checked afterwards is a floor that gets
    rounded through when the arithmetic is tight, which is exactly when it matters.
    """
    if not 0.0 < evergreen_floor < 1.0:
        raise EngineRefused(
            f"an evergreen floor of {evergreen_floor} is not a floor. Evergreen production "
            f"never drops to zero: a shop entirely inside Christmas has nothing to sell in "
            f"February, which is when it needs something")

    seasonal_pool = 1.0 - evergreen_floor
    total = sum(o.score for o in opportunities)
    shares: dict[str, float] = {}
    if total > 0:
        exact = {o.event: seasonal_pool * o.score / total for o in opportunities}
        shares = {event: round(value, 4) for event, value in exact.items()}
        # Rounding each share independently can push the sum past the pool -- three equal
        # occasions at 0.2667 come to 0.8001 against a pool of 0.8. Small, and it would eat
        # the evergreen floor from above, which is the one number here that must hold. The
        # remainder goes to the largest share, where it is proportionally smallest.
        drift = round(seasonal_pool - sum(shares.values()), 4)
        if drift and shares:
            largest = max(shares, key=lambda e: (shares[e], e))
            shares[largest] = round(shares[largest] + drift, 4)

    granted = round(sum(shares.values()), 4)
    return {
        "evergreen": round(evergreen_floor, 4),
        "evergreen_categories": list(EVERGREEN_CATEGORIES),
        "seasonal": shares,
        "seasonal_granted": granted,
        "unallocated": round(max(0.0, seasonal_pool - granted), 4),
        "by_horizon": {
            h: sorted(o.event for o in opportunities if o.horizon == h) for h in HORIZONS
        },
        "why": ("every share is the occasion's score over the total, inside what is left "
                "after the evergreen floor. No occasion is named in this function, and there "
                "is no argument that raises one" if total > 0 else
                "no occasion scored above zero, so the whole pool stays with evergreen. That "
                "is the correct answer rather than a failure: spreading capacity across "
                "occasions nothing supports is how a year of work produces nothing"),
        "floor_taken_first": (
            "the evergreen floor is subtracted before anything is granted, not checked after. "
            "A floor checked afterwards is one that gets rounded through when the arithmetic "
            "is tight, which is when it matters"),
    }


# ---- squads that stand down -----------------------------------------------

ACTIVE = "active"
STAND_DOWN = "stand_down"
NOT_WARRANTED = "not_warranted"


def squad_state(opportunity: Opportunity, *, currently_active: bool,
                alternatives: list[Opportunity]) -> dict:
    """Whether a squad should exist, by arithmetic rather than by somebody remembering.

    The requirement's phrase is that squads are *not permanent token-burning agents*, and the
    only way that stays true is if standing down is as mechanical as spinning up.
    """
    best_alternative = max((o.score for o in alternatives if o.event != opportunity.event),
                           default=0.0)
    score = opportunity.score

    if currently_active and (score < SQUAD_STANDDOWN_SCORE or score < best_alternative):
        return {"state": STAND_DOWN, "event": opportunity.event, "score": round(score, 6),
                "best_alternative": round(best_alternative, 6),
                "why": (f"{opportunity.event} scores {score:.4f}; the stand-down threshold is "
                        f"{SQUAD_STANDDOWN_SCORE} and the best alternative scores "
                        f"{best_alternative:.4f}. A squad that cannot be deactivated is a "
                        f"permanent cost justified once, and the deactivation has to be "
                        f"arithmetic because nobody stands a team down in a busy week")}
    if not currently_active and score >= SQUAD_STANDDOWN_SCORE and score >= best_alternative:
        return {"state": ACTIVE, "event": opportunity.event, "score": round(score, 6),
                "why": f"{opportunity.event} is the strongest opportunity above the threshold"}
    if currently_active:
        return {"state": ACTIVE, "event": opportunity.event, "score": round(score, 6),
                "why": "still the best use of this capacity"}
    return {"state": NOT_WARRANTED, "event": opportunity.event, "score": round(score, 6),
            "binding": opportunity.binding_factor,
            "why": (f"{opportunity.event} does not warrant a squad: its binding factor is "
                    f"{opportunity.binding_factor} ({FACTORS[opportunity.binding_factor]})")}


# ---- reuse across seasons, without cloning --------------------------------

REUSABLE: dict[str, str] = {
    "construction_primitive": "a validated way of building something -- a low-sew join, a "
                              "flat-to-round transition, a seamless edge",
    "production_tooling": "a chart generator, a size-card layout, a test harness",
    "commercial_lesson": "something the market taught: low-sew minis convert, size cards "
                         "reduce support questions",
}

NEVER_REUSABLE: dict[str, str] = {
    "motifs": "what is depicted. A recoloured Halloween cat is a Halloween cat",
    "colourway": "the palette is most of what makes a design look like another one",
    "design": "the thing itself, which is the failure the requirement names by name",
    "listing_copy": "reused copy makes two products look like one product twice",
}


def may_reuse(kind: str, *, from_season: str, to_season: str) -> dict:
    """What may cross from one season to another, and what may not."""
    if from_season == to_season:
        raise EngineRefused("reuse is a question about crossing seasons")
    if kind in NEVER_REUSABLE:
        return {"may_reuse": False, "kind": kind,
                "why": (f"{NEVER_REUSABLE[kind]}. A successful Halloween product can teach "
                        f"this shop that low-sew mini amigurumi converts, and that insight "
                        f"can inform a Christmas concept -- recolouring the same design is "
                        f"not that insight, it is the product again")}
    if kind in REUSABLE:
        return {"may_reuse": True, "kind": kind,
                "why": f"{REUSABLE[kind]}: it is how something was built, not what it was"}
    raise EngineRefused(
        f"{kind!r} is neither reusable nor protected: {sorted(REUSABLE)} may cross, "
        f"{sorted(NEVER_REUSABLE)} may not. An unclassified thing would cross by default, "
        f"and the default is the one that matters")


# ---- breakout mode, which cannot touch a gate ------------------------------

# What a breakout may move. Everything else is outside its authority by construction rather
# than by policy, because "emergency" is the word people use when they want to skip a step.
BREAKOUT_MAY_MOVE: tuple[str, ...] = (
    "capacity_allocation", "content_priority", "bundle_candidates", "distribution_effort",
)

BREAKOUT_MAY_NEVER_MOVE: tuple[str, ...] = (
    "quality_gate", "asset_truth", "policy_gate", "release_gate", "physical_test",
    "spend_ceiling", "shadow_mode",
)


def breakout(*, sku: str, velocity: float, baseline: float,
             requests: tuple[str, ...] = ()) -> dict:
    """Whether a SKU warrants emergency allocation, and what that may not reach."""
    forbidden = sorted(set(requests) & set(BREAKOUT_MAY_NEVER_MOVE))
    if forbidden:
        raise EngineRefused(
            f"{sku}: a breakout asked to move {forbidden}. QA gates remain non-bypassable, "
            f"and 'emergency' is the word people use when they want to skip a step -- which "
            f"is why this is a refusal rather than an approval step somebody can grant")
    unknown = sorted(set(requests) - set(BREAKOUT_MAY_MOVE))
    if unknown:
        raise EngineRefused(
            f"{sku}: {unknown} are outside a breakout's authority: {list(BREAKOUT_MAY_MOVE)}")

    if baseline <= 0:
        return {"breakout": False, "sku": sku,
                "why": ("no category baseline to exceed. A first product has nothing to run "
                        "three times faster than, and calling it a breakout would make every "
                        "first product an emergency")}
    multiple = velocity / baseline
    warranted = multiple >= BREAKOUT_MULTIPLE
    return {
        "breakout": warranted, "sku": sku, "multiple": round(multiple, 2),
        "threshold": BREAKOUT_MULTIPLE,
        "may_move": list(BREAKOUT_MAY_MOVE),
        "may_never_move": list(BREAKOUT_MAY_NEVER_MOVE),
        "why": (f"{multiple:.1f}x the category baseline, above {BREAKOUT_MULTIPLE}x. "
                f"Allocation moves; nothing else does"
                if warranted else
                f"{multiple:.1f}x the baseline, below {BREAKOUT_MULTIPLE}x. A product doing "
                f"slightly better than usual is a product doing slightly better than usual"),
        "exit": ("when the multiple normalises. An emergency mode with no exit condition is "
                 "the new normal allocation, renamed"),
    }


def state() -> dict:
    """The engine, and the constant it exists to replace."""
    return {
        "requirement": 33,
        "horizons": [{"horizon": h, "means": HORIZON_MEANS[h]} for h in HORIZONS],
        "universe": list(UNIVERSE),
        "factors": dict(FACTORS),
        "evergreen_floor": EVERGREEN_FLOOR,
        "evergreen_categories": list(EVERGREEN_CATEGORIES),
        "reusable": dict(REUSABLE),
        "never_reusable": dict(NEVER_REUSABLE),
        "breakout_may_never_move": list(BREAKOUT_MAY_NEVER_MOVE),
        "builds_on": {
            "seasonal.calendar": "rolling horizons and each event's launchable lane",
            "seasonal.compression": "lane retirement and the mix as an occasion closes",
            "seasonal.leadtime": "make-time to launch date, as an interval",
            "seasonal.rollforward": "moving capacity between occasions on two clocks",
        },
        "refuses": [
            "a score with a missing factor, which is a factor silently set to one",
            "a factor above one, which lets a single strong term manufacture a score",
            "an evergreen floor of zero",
            "a squad that stays active below the stand-down threshold",
            "a design, motif, colourway or listing copy crossing seasons",
            "a breakout asking to move a quality, policy, release or spend gate",
        ],
        "replaced": (
            "compression.PRIORITY_PROGRAMMES was a constant naming one occasion and granting "
            "it nearly half of engineering capacity permanently, read by five modules -- the "
            "Christmas Strike Team in code, and what this requirement's merge instruction "
            "says to replace. All five call sites now read compression.priority_shares(), "
            "which returns scores when any occasion has them and the seed labelled "
            "`current_campaign_seed` when none does"),
        "seed_remains_and_says_so": (
            "scoring needs observed demand, visibility and competitive weakness, and this "
            "shop has none of those. A straight cutover would score every occasion at zero "
            "and reserve nothing for the campaign whose making window is open, which is not "
            "rigour but absence. So the owner's named campaign survives as a seed that "
            "cannot be mistaken for a measurement, and the score wins the day there is one"),
    }
