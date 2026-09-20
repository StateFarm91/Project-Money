"""Customisation that does not fork the pattern.

Requirement 254. Controlled customisation where it is technically feasible and commercially
valuable -- colour planners, size selection, initials and names, motif arrangements,
printable variants -- while keeping canonical pattern truth intact, and price-testing the
personalisation rather than giving away expensive complexity.

"Keep canonical pattern truth intact" is the whole constraint, and it has a precise reading
in a system where a pattern is a compiled artefact. Every customisation is one of two things:

- a **presentation** choice, which changes what the buyer is shown and not what the
  instructions say. A colour name, a printable layout, a chosen size from a range the pattern
  already grades. The CIR is untouched, the certificate still covers it, and the twin's
  measurements still hold.
- a **construction** choice, which changes the instructions. A rearranged motif is a
  different chart, a different stitch count and a different fabric at the edges. It is a new
  design wearing the old one's name, and it needs the chain: compile, twin, geometry, write,
  reverse, certificate.

The failure this prevents is specific and it is the one every shop makes: offering "custom
initials" or "your motif arrangement" as a listing option, delivering a hand-edited PDF, and
thereby shipping an uncompiled, unverified pattern under a certified product's name. The
customer has no way to know their copy is the only one nobody checked, and it is the copy
most likely to be wrong, because it is the only one that was edited by hand.

So a construction-level customisation is not refused -- it is routed. It becomes a product,
goes through the chain, and gets its own certificate. What is refused is doing it under the
original's identity.

**Pricing.** The requirement says price-test rather than give away expensive complexity, and
the cost asymmetry is the point: a presentation choice costs nothing per order and may be
included; a construction choice costs a full chain run per order and cannot be, at any volume.
The module names which side of that line each option falls on rather than leaving it to
whoever writes the listing.
"""
from __future__ import annotations

from dataclasses import dataclass

PRESENTATION = "presentation"
CONSTRUCTION = "construction"

# Every customisation the requirement names, and which side of the line it falls on.
OPTIONS: dict[str, dict] = {
    "colour_plan": {
        "level": PRESENTATION,
        "what": "the buyer's own colourway, named in the copy they receive",
        "why": ("colour is a material choice: the instructions, the counts and the finished "
                "size are identical"),
    },
    "size_selection": {
        "level": PRESENTATION,
        "what": "one size from the range the pattern already grades",
        "why": ("the sizes were compiled and measured together; choosing one is choosing "
                "which of the certified columns to print"),
    },
    "printable_variant": {
        "level": PRESENTATION,
        "what": "large print, chart-only, or a no-photograph layout",
        "why": "the same instructions, set differently on the page",
    },
    "initials_or_name": {
        "level": CONSTRUCTION,
        "what": "letters worked into the fabric",
        "why": ("letters are stitches. They change the chart, the counts and the fabric "
                "around them, and a name is a different chart for every buyer"),
    },
    "motif_arrangement": {
        "level": CONSTRUCTION,
        "what": "the buyer's arrangement of the motifs",
        "why": ("a rearranged motif is a different chart, a different stitch count and a "
                "different fabric at the edges"),
    },
    "added_component": {
        "level": CONSTRUCTION,
        "what": "an extra piece the pattern does not include",
        "why": "a component the twin has never measured has no finished size",
    },
}

# What a construction-level option must do before it may be sold. The chain's own stages,
# named rather than restated: this module routes, it does not certify.
NEEDS_THE_CHAIN = ("compile", "twin", "geometry", "write", "reverse", "certificate")


class PersonalisationRefused(ValueError):
    """An option sold under a certificate that does not cover it."""


@dataclass(frozen=True)
class Offer:
    """One customisation offered on one product."""

    product_slug: str
    option: str
    price_cad: float = 0.0
    own_certificate: bool = False      # true when it has been through the chain itself

    def __post_init__(self) -> None:
        if self.option not in OPTIONS:
            raise PersonalisationRefused(
                f"{self.option!r} is not a customisation: {sorted(OPTIONS)}")

    @property
    def level(self) -> str:
        return OPTIONS[self.option]["level"]


def check(offer: Offer) -> dict:
    """Whether this may be sold as it stands, and what it needs if not."""
    spec = OPTIONS[offer.option]
    reasons: list[str] = []

    if offer.level == CONSTRUCTION and not offer.own_certificate:
        reasons.append(
            f"{offer.option} changes the instructions: {spec['why']}. Sold under "
            f"{offer.product_slug}'s certificate it ships an uncompiled, unverified pattern "
            f"under a certified product's name -- and the buyer's copy is the only one "
            f"nobody checked, which is the one most likely to be wrong because it is the "
            f"only one edited by hand")

    if offer.level == PRESENTATION and offer.price_cad > 0:
        reasons.append(
            f"CA${offer.price_cad:.2f} for a presentation choice. It costs nothing per "
            f"order, and charging for it is charging for the listing rather than for work")

    if offer.level == CONSTRUCTION and offer.price_cad <= 0:
        reasons.append(
            "a construction choice costs a full chain run per order. Given away, it is the "
            "expensive complexity this requirement says not to give away")

    return {
        "product_slug": offer.product_slug, "option": offer.option,
        "level": offer.level, "ok": not reasons, "reasons": reasons,
        "what": spec["what"],
        "needs": [] if offer.level == PRESENTATION else list(NEEDS_THE_CHAIN),
        "route": ("sell it" if not reasons else
                  ("route it through the chain as its own product, then sell that"
                   if offer.level == CONSTRUCTION and not offer.own_certificate
                   else "fix the price")),
    }


def catalogue(product_slug: str) -> dict:
    """Everything that could be offered on one product, split by what it costs to honour."""
    free = [k for k, v in OPTIONS.items() if v["level"] == PRESENTATION]
    priced = [k for k, v in OPTIONS.items() if v["level"] == CONSTRUCTION]
    return {
        "product_slug": product_slug,
        "included": free,
        "needs_its_own_certificate": priced,
        "why": ("a presentation choice costs nothing per order and may be included; a "
                "construction choice costs a full chain run per order and cannot be, at any "
                "volume"),
    }


def state() -> dict:
    """The line, and what falls on each side of it."""
    return {
        "levels": {PRESENTATION: "changes what the buyer is shown, not what it says",
                   CONSTRUCTION: "changes the instructions, and is a new design"},
        "options": {k: dict(v) for k, v in OPTIONS.items()},
        "needs_the_chain": list(NEEDS_THE_CHAIN),
        "note": ("Offering custom initials, delivering a hand-edited PDF and selling it under "
                 "a certified product's name ships an uncompiled pattern the buyer cannot "
                 "know is unchecked -- and it is the copy most likely to be wrong, because "
                 "it is the only one edited by hand. Such an option is routed through the "
                 "chain, not refused (#254)."),
    }
