"""Whether a concept seeds a family, and whether the buyer still has time to make it.

Requirements 111 and 112 of v1.4.3. They are the same question asked from two directions --
is this idea worth engineering *now* -- and they are both the kind of check that gets skipped
because the concept in front of you is good.

**#111, the multi-product family test.** A strong idea that produces exactly one product is
not a collection, and the way a catalogue discovers this is by shipping the hero, selling it,
and then forcing three derivatives out of it because the season needs depth. The forced
derivative is the failure the requirement names: a mosaic throw does not become a coaster,
it becomes four stitches of a motif nobody can see. So the test runs before engineering and
it runs on structure rather than enthusiasm -- can the *visual idea* survive the size change
each family role demands, and does a quick companion exist so the family has an entry price.

A concept that fails is not refused. A brilliant single product is a legitimate thing to
build; it is simply not a collection seed, and knowing which one you have before engineering
is the entire point.

**#112, make-time against the shopping window.** Creative scoring that ignores how long the
buyer needs treats an ornament and a flagship blanket as the same bet in November. They are
not: by then nobody buying a blanket pattern can finish it, and capacity spent designing one
is capacity spent on a product the customer cannot use this year.

The grading deliberately runs against the *interval* rather than the point estimate, per the
owner's correction: until physical testing produces real maker-speed data, a make-time
estimate is a distribution, and "impossible" means the optimistic bound has passed, not that
a single assumed number did. Everything short of that is high risk with insufficient runway,
which is a different instruction to a department -- it means hurry, not stop.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .concept import Concept

# How large a thing is, which is what decides whether a visual idea still reads on it. Bands
# rather than centimetres because the question is "can you see the motif", and a coaster and
# an ornament fail or pass that together.
TINY, SMALL, MEDIUM_SIZE, LARGE = "tiny", "small", "medium", "large"
SIZE_ORDER: tuple[str, ...] = (TINY, SMALL, MEDIUM_SIZE, LARGE)

FORM_SIZE: dict[str, str] = {
    "coaster": TINY, "ornament": TINY, "toy": TINY, "pouch": TINY,
    "garland": SMALL, "hat": SMALL, "basket": SMALL, "bag": SMALL,
    "stocking": SMALL, "wreath": SMALL, "sphere": SMALL, "cone": SMALL, "tube": SMALL,
    "pillow": MEDIUM_SIZE, "runner": MEDIUM_SIZE, "wall_hanging": MEDIUM_SIZE,
    # A scarf is small to hold and long to look at, and colourwork reads across its length.
    "scarf": MEDIUM_SIZE,
    "round_disc": MEDIUM_SIZE, "flat_panel": MEDIUM_SIZE,
    "rectangle_throw": LARGE, "fitted_garment": LARGE, "draped_garment": LARGE,
}

# The size range across which each construction's visual idea still reads. This is the whole
# mechanism: a construction outside its range does not produce a worse product, it produces a
# product the idea is no longer visible on, which is what "forcing a low-quality derivative"
# means in practice.
CONSTRUCTION_RANGE: dict[str, tuple[str, str]] = {
    # Colourwork needs room. A mosaic motif on a coaster is a handful of stitches wide.
    "mosaic_overlay": (MEDIUM_SIZE, LARGE),
    "tapestry": (SMALL, LARGE),
    # Cables read from a few repeats upward and get lost on something tiny.
    "cable_panel": (SMALL, LARGE),
    # Modular systems need enough units for the system to be the point.
    "modular_panels": (MEDIUM_SIZE, LARGE),
    "granny_square": (SMALL, LARGE),
    "motif_join": (SMALL, LARGE),
    "corner_to_corner": (SMALL, LARGE),
    # Shaping-led constructions are at their best small and become a weekend at large sizes.
    "amigurumi_shaping": (TINY, SMALL),
    "seamless_tube": (TINY, MEDIUM_SIZE),
    "in_the_round": (TINY, LARGE),
    "flat_rows": (TINY, LARGE),
    "side_to_side": (SMALL, LARGE),
    # Garment constructions do not make ornaments.
    "top_down_yoke": (LARGE, LARGE),
    "bottom_up": (MEDIUM_SIZE, LARGE),
}

# Which constructions can physically build each form. Size compatibility alone is not
# enough: an amigurumi-shaped robin and a scarf are both small objects, and no amount of
# increase-and-decrease shaping turns one into the other. Without this, the family test
# invents members -- which is the derivative-forcing it exists to prevent, arrived at by a
# different route.
FORM_CONSTRUCTIONS: dict[str, frozenset[str]] = {
    "coaster": frozenset({"flat_rows", "in_the_round", "granny_square", "motif_join",
                          "corner_to_corner", "tapestry", "mosaic_overlay", "cable_panel"}),
    "ornament": frozenset({"in_the_round", "amigurumi_shaping", "flat_rows", "motif_join",
                           "granny_square", "tapestry"}),
    "garland": frozenset({"motif_join", "granny_square", "in_the_round",
                          "amigurumi_shaping", "flat_rows"}),
    "pouch": frozenset({"flat_rows", "in_the_round", "seamless_tube", "tapestry",
                        "mosaic_overlay", "cable_panel", "granny_square", "motif_join",
                        "corner_to_corner"}),
    "toy": frozenset({"amigurumi_shaping", "in_the_round", "seamless_tube"}),
    "sphere": frozenset({"amigurumi_shaping", "in_the_round"}),
    "pillow": frozenset({"flat_rows", "mosaic_overlay", "tapestry", "cable_panel",
                         "granny_square", "motif_join", "corner_to_corner",
                         "modular_panels", "in_the_round"}),
    "wall_hanging": frozenset({"flat_rows", "tapestry", "mosaic_overlay", "motif_join",
                               "granny_square", "modular_panels", "corner_to_corner"}),
    "runner": frozenset({"flat_rows", "motif_join", "granny_square", "mosaic_overlay",
                         "tapestry", "corner_to_corner", "cable_panel", "side_to_side"}),
    "basket": frozenset({"in_the_round", "seamless_tube", "tapestry", "flat_rows"}),
    "wreath": frozenset({"motif_join", "in_the_round", "amigurumi_shaping",
                         "granny_square"}),
    "hat": frozenset({"in_the_round", "seamless_tube", "top_down_yoke", "cable_panel",
                      "tapestry", "mosaic_overlay", "flat_rows"}),
    "scarf": frozenset({"flat_rows", "side_to_side", "cable_panel", "mosaic_overlay",
                        "tapestry", "corner_to_corner", "motif_join", "granny_square"}),
    "bag": frozenset({"flat_rows", "in_the_round", "seamless_tube", "tapestry",
                      "mosaic_overlay", "granny_square", "motif_join", "corner_to_corner"}),
    "fitted_garment": frozenset({"top_down_yoke", "bottom_up", "seamless_tube",
                                 "cable_panel", "modular_panels"}),
    "draped_garment": frozenset({"flat_rows", "side_to_side", "motif_join", "granny_square",
                                 "modular_panels", "corner_to_corner", "cable_panel"}),
}


# Lane order, shortest first, kept local so this module does not depend on import order.
LANE_ORDER: tuple[str, ...] = ("QUICK", "SHORT", "MEDIUM", "LONG", "FLAGSHIP")


@dataclass(frozen=True)
class Role:
    """One position in a family, the forms that can fill it, and how fast it must be."""

    key: str
    what: str
    forms: tuple[str, ...]
    lane_ceiling: str
    why: str


ROLES: tuple[Role, ...] = (
    Role("quick_companion", "a fast make in the same visual world",
         ("coaster", "ornament", "garland", "pouch", "toy"), "QUICK",
         "the family's entry price: the purchase somebody makes before trusting the hero"),
    Role("giftable_mini", "a small finished object made as a present",
         ("ornament", "toy", "pouch", "sphere"), "SHORT",
         "gift buyers shop by occasion and finish time, not by category"),
    Role("decor_variant", "the same idea somewhere else in the room",
         ("pillow", "wall_hanging", "runner", "basket", "wreath"), "MEDIUM",
         "a room takes more than one object, which is how a hero becomes a set"),
    Role("wearable", "the idea carried onto a person",
         ("hat", "scarf", "bag", "fitted_garment", "draped_garment"), "LONG",
         "wearables reach a buyer who does not decorate and would never see the hero"),
    Role("adjacent_use", "the idea doing a different job",
         ("basket", "bag", "pouch", "runner"), "MEDIUM",
         "a use case the hero cannot serve, which is what stops a family being a recolour"),
)

ROLE_BY_KEY: dict[str, Role] = {r.key: r for r in ROLES}

# How many roles a concept must genuinely support before it is called a family seed. Three
# rather than two because two is a hero and an accessory, which every product has.
MIN_VIABLE_ROLES = 3

# Multipliers applied to a creative score once the shopping window is read. Not a veto:
# a department told "stop" and a department told "hurry" do different things, and only one
# of those is correct when the optimistic bound has not yet passed.
WINDOW_MULTIPLIER: dict[str, float] = {
    "comfortable": 1.0,
    "tight": 0.85,
    "high_risk": 0.45,
    "infeasible": 0.0,
}


class FamilyRefused(ValueError):
    """A family claimed without members, or a window read without a date."""


def _band_index(size: str) -> int:
    return SIZE_ORDER.index(size)


def _reads_at(construction: str, form: str) -> tuple[bool, str]:
    """Whether this construction's visual idea survives being put on this form."""
    size = FORM_SIZE.get(form)
    if size is None:
        return False, f"{form} has no size band, so nothing can be said about it"
    buildable = FORM_CONSTRUCTIONS.get(form)
    if buildable is not None and construction not in buildable:
        return False, (f"a {form} is not built by {construction}; the family member would "
                       f"share the story and none of the making, which is a new product "
                       f"with a borrowed name")
    low, high = CONSTRUCTION_RANGE.get(construction, (TINY, LARGE))
    index = _band_index(size)
    if index < _band_index(low):
        return False, (f"{construction} on a {size} {form} is below the size its motif reads "
                       f"at; the derivative would carry the name and not the idea")
    if index > _band_index(high):
        return False, (f"{construction} on a {size} {form} is above the size it holds "
                       f"together at; the derivative would be a different product wearing "
                       f"the same story")
    return True, f"{construction} reads at {size} scale"


def _lane_fits(role: Role, form: str) -> tuple[bool, str]:
    """A role has a speed as well as a shape: a flagship cannot be the quick companion."""
    size = FORM_SIZE.get(form, LARGE)
    # Size is the honest proxy for make time before anything is engineered. A tiny object is
    # a quick make; a large one is not, whatever the brief hopes.
    implied = {TINY: "QUICK", SMALL: "SHORT", MEDIUM_SIZE: "MEDIUM", LARGE: "LONG"}[size]
    if LANE_ORDER.index(implied) <= LANE_ORDER.index(role.lane_ceiling):
        return True, f"a {size} {form} is a {implied.lower()} make"
    return False, (f"a {size} {form} is a {implied.lower()} make, and {role.key} only works "
                   f"at {role.lane_ceiling.lower()} or faster")


def family_test(hero: Concept) -> dict:
    """Can this concept seed a coherent family, or would the family be forced? (#111)

    Run before engineering, because after engineering the answer is always yes: the hero
    exists, the season needs depth, and the derivatives get made whether the idea supports
    them or not.
    """
    viable: list[dict] = []
    blocked: list[dict] = []

    for role in ROLES:
        candidates = []
        reasons = []
        for form in role.forms:
            if form == hero.form:
                # A role filled by the hero's own form is the hero again. A family whose
                # members differ by palette is a recolour with a collection name on it.
                reasons.append(f"{form} is the hero's own form, so it is not a second product")
                continue
            reads, why_reads = _reads_at(hero.construction, form)
            if not reads:
                reasons.append(why_reads)
                continue
            fits, why_fits = _lane_fits(role, form)
            if not fits:
                reasons.append(why_fits)
                continue
            candidates.append({"form": form, "why": f"{why_reads}; {why_fits}"})

        if candidates:
            viable.append({"role": role.key, "what": role.what, "why_it_matters": role.why,
                           "forms": candidates})
        else:
            blocked.append({"role": role.key, "what": role.what,
                            "why_it_matters": role.why,
                            "would_force_a_derivative": reasons})

    has_entry = any(v["role"] == "quick_companion" for v in viable)
    seeds = len(viable) >= MIN_VIABLE_ROLES and has_entry

    # A bundle is derived, never asserted: it exists when two other roles do, because a
    # bundle of one product is the product.
    bundle = len(viable) >= 2

    if seeds:
        verdict = "seeds_a_family"
        note = (f"{len(viable)} roles are supported by the hero's own construction, including "
                f"a quick companion, so the family has an entry price and does not need a "
                f"forced derivative")
    elif not has_entry and len(viable) >= MIN_VIABLE_ROLES:
        verdict = "no_entry_price"
        note = ("the idea carries into enough roles but has no quick make, so every member "
                "costs the buyer the same commitment as the hero. Families are entered at "
                "the cheap end")
    else:
        verdict = "single_product"
        note = ("this is a single product rather than a collection seed, which is a "
                "legitimate thing to build and a bad thing to discover after engineering "
                "three derivatives out of it")

    return {
        "hero": hero.key,
        "construction": hero.construction,
        "verdict": verdict,
        "seeds_a_family": seeds,
        "viable_roles": viable,
        "blocked_roles": blocked,
        "bundle_possible": bundle,
        "minimum_roles": MIN_VIABLE_ROLES,
        "note": note,
    }


# ---------------------------------------------------------------------------
# #112: make-time against the shopping window


def window_fit(concept: Concept, *, days_to_event: int, samples: int = 0,
               skill: str = "intermediate", today: date | None = None) -> dict:
    """Grade a concept's make lane against the time the buyer actually has left.

    Graded against the interval, not a point estimate: 'impossible' means the optimistic
    bound has passed. Everything short of that is a runway problem, and a department told to
    hurry does something useful where a department told to stop does nothing.
    """
    from ..seasonal.calendar import lane_feasibility

    if days_to_event < 0:
        raise FamilyRefused("days_to_event is negative; the window has closed and a fit "
                            "cannot be graded against a date that has passed")

    lanes = {row["lane"]: row for row in lane_feasibility(days_to_event, skill,
                                                          samples=samples, today=today)}
    row = lanes.get(concept.make_lane)
    if row is None:
        raise FamilyRefused(f"{concept.key}: unknown make lane {concept.make_lane!r}")

    verdict = row["verdict"]
    return {
        "concept": concept.key,
        "make_lane": concept.make_lane,
        "days_to_event": days_to_event,
        "verdict": verdict,
        "meaning": row["meaning"],
        "score_multiplier": WINDOW_MULTIPLIER[verdict],
        "latest_optimistic_launch": row["latest_optimistic_launch"],
        "calibrated": samples > 0,
        "note": ("make-time is uncalibrated: no maker has been timed, so the interval is "
                 "wide on purpose and a verdict of infeasible is reached only when even the "
                 "optimistic bound has passed" if samples == 0 else
                 f"graded against an interval narrowed by {samples} recorded physical "
                 f"test(s)"),
    }


def shift_capacity(concepts: list[Concept], *, days_to_event: int, samples: int = 0,
                   skill: str = "intermediate", today: date | None = None) -> dict:
    """Move late-window creative capacity toward the makes a buyer can still finish (#112).

    The failure this prevents is not designing the wrong thing. It is continuing to design
    the right thing three weeks too late, which looks like productivity the whole time.
    """
    from ..seasonal.calendar import lane_feasibility

    graded = [window_fit(c, days_to_event=days_to_event, samples=samples, skill=skill,
                         today=today) for c in concepts]

    keep = [g for g in graded if g["verdict"] in ("comfortable", "tight")]
    hurry = [g for g in graded if g["verdict"] == "high_risk"]
    stand_down = [g for g in graded if g["verdict"] == "infeasible"]

    lanes = lane_feasibility(days_to_event, skill, samples=samples, today=today)
    still_open = [row["lane"] for row in lanes
                  if row["verdict"] in ("comfortable", "tight")]
    heaviest = still_open[-1] if still_open else None

    return {
        "days_to_event": days_to_event,
        "continue": keep,
        "hurry": hurry,
        "stand_down": stand_down,
        "new_work_should_be_no_heavier_than": heaviest,
        "calibrated": samples > 0,
        "note": (
            "no lane is still comfortable or tight, so new work for this event should start "
            "in the next season rather than this one" if heaviest is None else
            f"new concepts for this event should be {heaviest.lower()} makes or faster. "
            f"{len(stand_down)} concept(s) are past the point where any plausible maker "
            f"finishes; {len(hurry)} have insufficient runway rather than none, which means "
            f"hurry rather than stop"),
    }
