"""Learning from the best shops without becoming one of them.

Requirements 215, 219, 220 and 227. Brambleloop may enter the same generic arena as an elite
competitor and must design something substantively original there. The elite panel is more
than one seller, so a specialist learns best-of-breed rather than overfitting to one shop's
aesthetic. When a benchmark materially improves, relevant standards are re-evaluated and the
Improvement Department records which changed and why. And the sentence the other three rest
on: *no agent may treat "match MJs" as the final creative objective* -- the benchmark is a
commercial quality floor and a source of evidence, not a ceiling.

`intel.observe` already enumerates the catalogue, `intel.pods` already routes listings to
specialists, and `commerce.benchmarks` already refuses a comparison across incomparable
cells. What none of them holds is the thing #227 is actually worried about, and it is a
failure of aggregation rather than of any single decision.

**An organisation that benchmarks continuously converges on the benchmark.** Every individual
decision to match is defensible -- they are good, this is what good looks like, we should be
at least this good -- and the sum of a year of defensible decisions is a shop that looks like
a copy of a shop. There is no moment where somebody decides to become derivative. So a
concept whose entire justification is parity is refused: matching is the floor, and clearing
a floor is not a reason to ship something. Entering the arena is permitted; "the same but
ours" is not.

**A standard may be raised by a competitor and never lowered by one.** When a benchmark
improves, the bar moves up. When a benchmark gets worse, nothing happens -- a standard
lowered because a competitor slipped is a race to the bottom with a paper trail, and it is
the more tempting move because it is free and shows up as an improvement in every metric
about hitting standards.

**A panel of one is not a panel.** MJs is the anchor and the requirement says so, but a
mechanism seen in one shop is a mechanism from one shop; it becomes a standard when it
appears across sellers. That is what stops best-of-breed from meaning best-of-MJs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# The anchor the owner named. Named once, here, so that "the panel" never quietly means it.
ANCHOR = "MJs"

# A panel needs more than the anchor before it can teach best-of-breed rather than
# best-of-one-shop.
MIN_PANEL_MEMBERS = 3

# How many distinct sellers must show a mechanism before it is a mechanism rather than one
# shop's habit. Two, not three: a second independent seller is what separates a pattern from
# a preference, and demanding three would leave most real mechanisms unlearnable.
MIN_SELLERS_FOR_MECHANISM = 2


class PanelRefused(ValueError):
    """A panel of one, a standard lowered by a competitor, or parity offered as a reason."""


@dataclass(frozen=True)
class Member:
    """One shop on the elite panel, with what it is on it for."""

    seller_ref: str
    categories: tuple[str, ...]
    added_on: date
    is_anchor: bool = False
    removed_on: date | None = None

    def __post_init__(self) -> None:
        if not self.seller_ref.strip():
            raise PanelRefused("a panel member names the seller it refers to")
        if not self.categories:
            raise PanelRefused(
                f"{self.seller_ref}: a member with no categories teaches nothing in "
                f"particular, and a panel that is just a list of good shops cannot answer "
                f"which of them a cardigan specialist should read")

    def active_on(self, day: date) -> bool:
        return self.added_on <= day and (self.removed_on is None or self.removed_on > day)


def panel_state(members: list[Member], *, on: date, category: str = "") -> dict:
    """Who is teaching today, and whether that is enough to be a panel at all."""
    active = [m for m in members if m.active_on(on)]
    if category:
        active = [m for m in active if category in m.categories]
    anchors = [m for m in active if m.is_anchor]
    enough = len(active) >= MIN_PANEL_MEMBERS

    return {
        "on": on.isoformat(), "category": category or "all",
        "members": sorted(m.seller_ref for m in active),
        "anchor": [m.seller_ref for m in anchors],
        "count": len(active), "minimum": MIN_PANEL_MEMBERS,
        "is_a_panel": enough,
        "why": (f"{len(active)} sellers teaching" if enough else
                f"{len(active)} of {MIN_PANEL_MEMBERS}. A panel of one is one shop's "
                f"aesthetic with a formal name, and {ANCHOR} is the anchor rather than the "
                f"only teacher -- learning best-of-breed from a single seller is learning "
                f"best-of-that-seller"),
        "changing": ("a panel is maintained rather than chosen once: members join and leave "
                     "as categories and quality move, which is why membership carries dates"),
    }


def mechanism_is_learnable(*, mechanism: str, seen_in: tuple[str, ...]) -> dict:
    """Whether a mechanism seen in the wild may become a standard here."""
    sellers = sorted({s for s in seen_in if s.strip()})
    if len(sellers) >= MIN_SELLERS_FOR_MECHANISM:
        return {"learnable": True, "mechanism": mechanism, "sellers": sellers,
                "why": (f"seen in {len(sellers)} sellers, so it is a mechanism rather than "
                        f"one shop's habit")}
    return {"learnable": False, "mechanism": mechanism, "sellers": sellers,
            "why": (f"seen in {len(sellers)} seller(s). One shop doing something is a "
                    f"preference; {MIN_SELLERS_FOR_MECHANISM} independent sellers doing it "
                    f"is a pattern, and the difference is what stops best-of-breed meaning "
                    f"best-of-{ANCHOR}"),
            "what_would_settle_it": "observing it in one more seller's catalogue"}


# ---- the bar moves up ------------------------------------------------------

RAISED = "raised"
UNCHANGED = "unchanged"
REFUSED_LOWERING = "refused_lowering"


@dataclass(frozen=True)
class StandardChange:
    """A proposed change to one of this shop's own standards, and what prompted it."""

    standard: str
    from_value: float
    to_value: float
    higher_is_better: bool
    prompted_by: str            # the benchmark observation that prompted it
    because: str = ""

    def __post_init__(self) -> None:
        if not self.prompted_by.strip():
            raise PanelRefused(
                f"{self.standard}: name the observation that prompted this. The Improvement "
                f"Department records which standards changed and why, and 'we reviewed it' "
                f"is not a why anybody can re-examine")


def move_bar(change: StandardChange) -> dict:
    """Raise a standard when a benchmark improves; never lower one because it slipped."""
    delta = change.to_value - change.from_value
    stricter = delta > 0 if change.higher_is_better else delta < 0

    if delta == 0:
        return {"outcome": UNCHANGED, "standard": change.standard,
                "why": "the proposed value is the current one"}
    if stricter:
        return {
            "outcome": RAISED, "standard": change.standard,
            "from": change.from_value, "to": change.to_value,
            "prompted_by": change.prompted_by, "because": change.because,
            "why": (f"{change.standard} moves from {change.from_value} to "
                    f"{change.to_value}: the competitive bar is dynamic and this is it "
                    f"moving up"),
        }
    return {
        "outcome": REFUSED_LOWERING, "standard": change.standard,
        "from": change.from_value, "to": change.to_value,
        "prompted_by": change.prompted_by,
        "why": (f"{change.standard} would move from {change.from_value} to "
                f"{change.to_value}, which is looser. A standard may be raised by a "
                f"competitor and never lowered by one: lowering because somebody else "
                f"slipped is a race to the bottom with a paper trail, and it is the more "
                f"tempting move because it is free and shows up as an improvement in every "
                f"metric about hitting standards"),
        "if_the_standard_is_genuinely_wrong": (
            "that is a decision about this shop, made on this shop's evidence, and it does "
            "not travel through a benchmark observation"),
    }


# ---- the floor is not the ceiling -----------------------------------------

# What a concept can offer beyond parity. Closed: an open list lets "better" be the
# justification, and better is what everybody thinks they are doing.
SUPERIORITY_AXES: dict[str, str] = {
    "product_engineering": "it is built better -- construction, fit, durability, sizing",
    "usability": "it is easier to work from -- clearer charts, better sequencing, fewer stalls",
    "creativity": "it is a thing nobody is making, not a better version of a thing",
    "customer_experience": "what happens around the purchase is better",
    "styling": "it looks like something this shop made, and that is a reason to buy it",
    "value": "more is included, or the same is included for materially less effort",
}

PARITY = "parity"


@dataclass(frozen=True)
class ArenaEntry:
    """A decision to make something in an arena an elite seller already occupies."""

    arena: str
    benchmark_ref: str
    what_makes_theirs_work: str
    axes: tuple[str, ...]
    how: str = ""

    def __post_init__(self) -> None:
        if not self.what_makes_theirs_work.strip():
            raise PanelRefused(
                f"{self.arena}: say what makes the benchmark compelling. Entering an arena "
                f"without knowing why the incumbent wins there is entering it blind, and #215 "
                f"asks agents to identify that first")
        unknown = sorted(set(self.axes) - set(SUPERIORITY_AXES) - {PARITY})
        if unknown:
            raise PanelRefused(
                f"{self.arena}: {unknown} are not axes: {sorted(SUPERIORITY_AXES)}. An open "
                f"list lets 'better' be the justification, and better is what everybody "
                f"thinks they are doing")


def may_enter(entry: ArenaEntry) -> dict:
    """Whether this arena entry is a product or a copy.

    Entering is permitted and the requirement insists on it: do not restrict Brambleloop
    merely because an elite competitor also sells cardigans. What is refused is entering with
    nothing to offer but parity.
    """
    beyond = sorted(set(entry.axes) - {PARITY})
    if not beyond:
        return {
            "may_enter": False, "arena": entry.arena, "axes": list(entry.axes),
            "why": (f"the only thing offered is parity. Matching is the floor, and clearing "
                    f"a floor is not a reason to ship something -- an organisation that "
                    f"benchmarks continuously converges on the benchmark, one defensible "
                    f"decision at a time, and there is no moment where anybody decides to "
                    f"become derivative"),
            "what_would_allow_it": sorted(SUPERIORITY_AXES),
        }
    if not entry.how.strip():
        return {"may_enter": False, "arena": entry.arena, "axes": beyond,
                "why": (f"{beyond} named and not explained. An axis without a mechanism is "
                        f"an intention, and intentions do not survive contact with a design "
                        f"review")}
    return {
        "may_enter": True, "arena": entry.arena, "axes": beyond,
        "beyond_parity": {axis: SUPERIORITY_AXES[axis] for axis in beyond},
        "why": (f"a generic arena is open to anybody and this entry offers {beyond} beyond "
                f"matching. #215 is explicit that sharing an arena with an elite seller is "
                f"not a reason to stay out of it"),
    }


def ceiling_check(*, objective: str) -> dict:
    """Refuse an objective that names matching as the goal (#227)."""
    lowered = (objective or "").strip().lower()
    if not lowered:
        raise PanelRefused("an objective nobody stated cannot be checked against anything")
    matching = ("match ", "matching ", "parity with", "as good as", "equal to",
                "on par with", "catch up to", "same as", "keep up with")
    # Who the matching is *with*. A standard matched against this shop's own last release is
    # ordinary consistency; matched against a competitor it is the ceiling #227 forbids.
    competitors = (ANCHOR.lower(), "benchmark", "competitor", "the leader", "elite seller",
                   "the incumbent")
    hit = next((phrase for phrase in matching if phrase in lowered), None)
    target = next((who for who in competitors if who in lowered), None)
    if hit and target:
        return {"permitted": False, "objective": objective, "matched": hit,
                "against": target,
                "why": (f"{hit!r} makes the benchmark the destination. It is a commercial "
                        f"quality floor and a source of market evidence; the creative "
                        f"department still has to look for white space, new product forms "
                        f"and stronger customer value beyond what the benchmark offers")}
    return {"permitted": True, "objective": objective,
            "why": ("the objective does not name matching a competitor as the goal. Matching "
                    "this shop's own last release is ordinary consistency and is not what "
                    "#227 is about")}


def state() -> dict:
    """The panel, the bar, and the floor that is not a ceiling."""
    return {
        "requirements": [215, 219, 220, 227],
        "anchor": ANCHOR,
        "min_panel_members": MIN_PANEL_MEMBERS,
        "min_sellers_for_mechanism": MIN_SELLERS_FOR_MECHANISM,
        "superiority_axes": dict(SUPERIORITY_AXES),
        "refuses": [
            "a panel below its minimum, which is one shop's aesthetic with a formal name",
            "a mechanism promoted to a standard from a single seller",
            "a standard lowered because a competitor got worse",
            "a standard change with no observation behind it",
            "an arena entry offering nothing but parity",
            "an axis named without a mechanism",
            "an objective that names matching the benchmark as the goal",
        ],
        "note": ("the failure #227 guards is one of aggregation, not of any single decision. "
                 "Every individual choice to match is defensible -- they are good, this is "
                 "what good looks like -- and a year of defensible choices is a shop that "
                 "looks like a copy of a shop. Nobody ever decides to become derivative"),
    }
