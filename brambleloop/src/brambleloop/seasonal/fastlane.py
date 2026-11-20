"""A shorter queue, never a shorter list of gates.

Requirement 291. When a trend is time-sensitive, technically simple and backed by confident
evidence, it goes down a fast lane with bounded scope. The requirement then spends its second
half on the part that matters: fast does not bypass pattern truth, IP and policy, visual truth
or what the customer was told.

That distinction is easy to write and hard to keep, because every fast lane in every company
begins as a queue-jump and ends as an exemption. The slide is never decided; it happens one
deadline at a time, and each step is defensible on its own. So the exemption is made
structurally impossible rather than discouraged: the gates a fast-lane product must pass are
the same list as every other product's, this module holds no way to shorten it, and a
certificate that skipped one is refused by name.

What the lane actually buys is scope. A fast product is small by construction -- one
component, few colours, a risk class the compiler can verify completely, a technique the
catalogue already uses -- and that is why it can be finished quickly. Nothing about the
checking is faster; there is simply less to check, which is the only honest way to go fast.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..gates.certificate import CANONICAL_STAGES, CONDITIONAL_STAGES
from .calendar import HALF_LIVES, LANE_ORDER, CalendarRefused, check_half_life

# The gates a fast-lane product passes: the release chain's own list, imported rather than
# retyped. A second copy of this list is exactly how the guarantee would quietly stop being
# true -- somebody edits one of them, both still look right, and the lane has an exemption
# nobody decided to give it.
#
# Three stages are conditional on the *product* (geometry on a closed form, asset_truth and
# policy on a listing existing). They stay conditional on the product here and never on the
# lane, which is the distinction the requirement is actually making.
NON_NEGOTIABLE_GATES: tuple[str, ...] = tuple(
    stage for stage in CANONICAL_STAGES if stage not in CONDITIONAL_STAGES)

CONDITIONAL_GATES: tuple[str, ...] = CONDITIONAL_STAGES

# What "technically simple" means, in numbers rather than in judgement.
MAX_COMPONENTS = 1
MAX_COLOURS = 3
MAX_NEW_TECHNIQUES = 0
ALLOWED_RISK_CLASSES: tuple[str, ...] = ("A",)

# The heaviest lane the fast lane will carry. Beyond this the work is not fast whatever the
# trend is doing, and pretending otherwise is how a flagship enters a two-week window.
LANE_CEILING = "SHORT"

# Evidence confidence required before the queue is jumped at all. A fast lane fed by a weak
# signal is a fast way to make something nobody wanted.
CONFIDENT_ABOVE = 0.70


class FastLaneRefused(ValueError):
    """A product too large for the lane, a trend too weak for it, or a gate skipped."""


@dataclass(frozen=True)
class Candidate:
    slug: str
    half_life: str
    make_lane: str
    risk_class: str
    components: int
    colours: int
    new_techniques: int
    # None is UNMEASURED: no scored evidence exists for the trend. It is refused, never read
    # as a confidence of zero or of anything else.
    evidence_confidence: float | None


def admit(candidate: Candidate) -> dict:
    """Decide whether this belongs in the fast lane, and say exactly why when it does not."""
    reasons: list[str] = []

    if candidate.evidence_confidence is None:
        reasons.append(
            "evidence confidence is UNMEASURED: no scored evidence stands behind this trend, "
            "and a fast lane fed by an unmeasured signal is a fast way to make something "
            "nobody wanted")
    elif candidate.evidence_confidence < CONFIDENT_ABOVE:
        reasons.append(
            f"evidence confidence {candidate.evidence_confidence:.2f} is below "
            f"{CONFIDENT_ABOVE:.2f}. A fast lane fed by a weak signal is a fast way to make "
            f"something nobody wanted")

    if candidate.half_life not in HALF_LIVES:
        reasons.append(
            f"{candidate.half_life!r} is not a half-life, and an unclassified trend gets "
            f"whatever effort somebody felt like spending")
    else:
        try:
            check_half_life(candidate.half_life, candidate.make_lane)
        except CalendarRefused as exc:
            reasons.append(str(exc))

    if candidate.make_lane not in LANE_ORDER:
        reasons.append(f"{candidate.make_lane!r} is not a make lane")
    elif LANE_ORDER.index(candidate.make_lane) > LANE_ORDER.index(LANE_CEILING):
        reasons.append(
            f"a {candidate.make_lane} product is not fast whatever the trend is doing; the "
            f"lane carries {LANE_CEILING} and below, and pretending otherwise is how a "
            f"flagship enters a two-week window")

    if candidate.risk_class not in ALLOWED_RISK_CLASSES:
        reasons.append(
            f"risk class {candidate.risk_class} cannot be fully verified by the compiler, "
            f"and the fast lane's whole argument is that there is less to check rather than "
            f"that checking is skipped")

    if candidate.components > MAX_COMPONENTS:
        reasons.append(f"{candidate.components} components against a ceiling of "
                       f"{MAX_COMPONENTS}: assembly is where a quick make stops being quick")
    if candidate.colours > MAX_COLOURS:
        reasons.append(f"{candidate.colours} colours against a ceiling of {MAX_COLOURS}: "
                       f"colour changes are the commonest source of a chart that disagrees "
                       f"with its written instructions")
    if candidate.new_techniques > MAX_NEW_TECHNIQUES:
        reasons.append(
            f"{candidate.new_techniques} technique(s) the catalogue has never used. A new "
            f"technique needs a physical sample, and a sample is the one part of this "
            f"company nobody can hurry")

    return {
        "slug": candidate.slug,
        "admitted": not reasons,
        "reasons": reasons,
        "gates": list(NON_NEGOTIABLE_GATES),
        "conditional_gates": list(CONDITIONAL_GATES),
        "bounds": {"components": MAX_COMPONENTS, "colours": MAX_COLOURS,
                   "new_techniques": MAX_NEW_TECHNIQUES,
                   "risk_classes": list(ALLOWED_RISK_CLASSES),
                   "lane_ceiling": LANE_CEILING},
        "note": ("admitted: the lane shortens the queue and not the gate list. This product "
                 "passes every gate an ordinary product passes; there is simply less of it "
                 "to check"
                 if not reasons else
                 f"{len(reasons)} reason(s) this is not fast-lane work. It may still be "
                 f"built -- through the ordinary queue, at its own pace"),
    }


def check_release(slug: str, *, gates_passed: tuple[str, ...],
                  applicable_conditional: tuple[str, ...] = ()) -> dict:
    """Refuse a fast-lane release that skipped a gate, by name.

    This is the structural half. Every fast lane begins as a queue-jump and ends as an
    exemption, one defensible deadline at a time, and the way to stop that is to make the
    exemption impossible to express rather than discouraged.

    `applicable_conditional` names the product-conditional stages this product was owed --
    a listing means policy and asset truth are owed, a closed form means geometry is. They
    are conditional on the product and never on the lane.
    """
    unknown = [g for g in applicable_conditional if g not in CONDITIONAL_GATES]
    if unknown:
        raise FastLaneRefused(
            f"{unknown} are not conditional stages of the release chain: "
            f"{list(CONDITIONAL_GATES)}")

    required = list(NON_NEGOTIABLE_GATES) + [g for g in CONDITIONAL_GATES
                                             if g in applicable_conditional]
    missing = [gate for gate in required if gate not in set(gates_passed)]
    if missing:
        raise FastLaneRefused(
            f"{slug} came down the fast lane without {missing}. The lane shortens the queue, "
            f"never the gate list: a fast-lane product passes exactly what the ordinary "
            f"chain would have run for the same product")
    return {"slug": slug, "gates": required, "ok": True,
            "note": "every gate the ordinary chain would have run was run on the fast lane"}


def state() -> dict:
    """The lane's rules, for a reader asking what 'fast' is allowed to mean here."""
    return {
        "gates": list(NON_NEGOTIABLE_GATES),
        "conditional_gates": list(CONDITIONAL_GATES),
        "bounds": {"components": MAX_COMPONENTS, "colours": MAX_COLOURS,
                   "new_techniques": MAX_NEW_TECHNIQUES,
                   "risk_classes": list(ALLOWED_RISK_CLASSES),
                   "lane_ceiling": LANE_CEILING,
                   "evidence_confidence_above": CONFIDENT_ABOVE},
        "note": ("What the fast lane buys is scope, never checking. A fast product is small "
                 "by construction -- one component, few colours, a risk class the compiler "
                 "verifies completely -- and that is the only honest way to go fast (#291)."),
    }


# ---------------------------------------------------------------------------
# #290 at runtime: every observed trend gets a half-life, and the half-life caps its lane.

# A culture domain's prior half-life. A prior, labelled as one on every classification: the
# observed recurrence below overrides it, because a trend seen again a year later is a
# recurring season whatever domain it started in.
DOMAIN_HALF_LIFE: dict[str, str] = {
    "meme": "flash",
    "internet_moment": "flash",
    "viral_aesthetic": "flash",
    "film": "short_seasonal",
    "television": "short_seasonal",
    "music": "short_seasonal",
    "celebrity_aesthetic": "short_seasonal",
    "sports_culture": "short_seasonal",
    "seasonal_tradition": "recurring_seasonal",
    "nostalgia_era": "multi_season_fashion",
}


def classify_half_life(*, domain: str, recurring: bool = False,
                       season: str | None = None, evergreen: bool = False) -> dict:
    """The half-life class of one trend or product, with its basis and its lane ceiling."""
    if recurring:
        half_life, basis = "recurring_seasonal", "observed_recurrence"
    elif evergreen:
        half_life, basis = "evergreen", "evergreen_product"
    elif season:
        half_life, basis = "recurring_seasonal", f"calendar_event:{season}"
    elif domain in DOMAIN_HALF_LIFE:
        half_life, basis = DOMAIN_HALF_LIFE[domain], f"domain_prior:{domain}"
    else:
        raise FastLaneRefused(
            f"{domain!r} has no half-life prior and no observed recurrence. An unclassified "
            f"trend gets whatever effort somebody felt like spending, so it is refused")
    return {"half_life": half_life, "basis": basis,
            "lane_ceiling": HALF_LIVES[half_life],
            "note": ("estimated from the domain's prior until the trend is seen again"
                     if basis.startswith("domain_prior") else "")}
