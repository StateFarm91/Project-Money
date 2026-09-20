"""What a flagship gives the buyer beyond the instructions, computed rather than promised.

Requirement 7. A flagship competes as a complete project system, and the requirement lists
what that means: a polished PDF, written instructions, charts, **progress visuals**, a
**print version**, video where useful, yarn substitution and colour guidance, and
version-aware pattern support. It ends on the sentence that decides the rest --
**price the customer outcome rather than page count**.

The PDF, the instructions, the charts, the substitution guidance and the version-aware
support exist. This module is the three pieces that did not, and each is arithmetic on the
pattern rather than a claim about it.

**Progress visuals are milestones, not decoration.** A buyer halfway up a blanket wants to
know whether what is on their hook is what should be on their hook. So the milestones are the
rows where the fabric *changes* -- the foundation established, the first full repeat, the
half, the last repeat -- and each one states what should be true at that point in stitches
and centimetres, which are both things the twin already knows.

**A print version is a claim about a printer, so it is checked against one.** Most home
printers are greyscale, and a chart whose colours differ in hue but not in lightness prints
as one flat block. That is the same measurement `publish/substitution.colourway` makes for
thumbnails, for the same reason, so it is the same code.

**Price is computed from the object, and page count is not an input.** The requirement's
closing sentence is a rule about what may enter the arithmetic, and the honest way to hold a
rule like that is to make the number impossible to derive from the forbidden thing: nothing
here reads a page count, and a test asserts it.
"""
from __future__ import annotations

from dataclasses import dataclass

# What a buyer is paying for, in the order the requirement's own sentence implies: the
# finished object, the work it takes, and what arrives to support it. Page count is
# deliberately absent, and its absence is the requirement.
@dataclass(frozen=True)
class PriceFactor:
    key: str
    what: str
    weight: float


PRICE_FACTORS: tuple[PriceFactor, ...] = (
    PriceFactor("finished_object", "how large the thing they end up with is", 0.40),
    PriceFactor("commitment", "how many hours of their life it asks for", 0.30),
    PriceFactor("support_depth", "charts, substitution guidance and version-aware help", 0.30),
)

# Never an input. Named so that the rule is visible in the module rather than only in a
# docstring, and so the test that enforces it has something to point at.
NEVER_PRICED_ON: tuple[str, ...] = ("page_count", "word_count", "file_size")

# Lightness separation a chart needs to survive a greyscale printer. The same threshold the
# thumbnail check uses, because it is the same failure: two colours that differ in hue and
# not in value merge into one block.
from .substitution import MIN_VALUE_SEPARATION, colourway  # noqa: E402


class ValueStackRefused(ValueError):
    """A value stack asked for where the pattern cannot support one."""


def milestones(cir, twin) -> dict:
    """The rows where the fabric changes, and what should be true at each.

    A buyer halfway up a blanket is asking one question -- is what is on my hook what should
    be on my hook -- and a progress visual that does not answer it in stitches and
    centimetres is decoration.
    """
    rows = [row for component in cir.components for row in component.rows]
    if not rows:
        raise ValueStackRefused("this pattern has no rows, so it has no progress to show")

    total = len(rows)
    height = twin.height_cm or 0.0
    points = sorted({1, max(1, total // 4), max(1, total // 2),
                     max(1, (total * 3) // 4), total})
    out = []
    for index in points:
        row = rows[index - 1]
        out.append({
            "row": index,
            "share": round(index / total, 3),
            "stitches_in_this_row": row.declared_count,
            "height_so_far_cm": round(height * index / total, 1),
            "colour": row.color,
            "what_should_be_true": (
                f"row {index} of {total}: {row.declared_count} stitches across, about "
                f"{height * index / total:.0f} cm of fabric made"),
        })
    return {
        "milestones": out,
        "rows_total": total,
        "note": ("The rows where the fabric changes, with what should be true at each in "
                 "stitches and centimetres. A maker checking their work needs a number they "
                 "can count, not a picture they can only agree with (#7)."),
    }


def print_safety(cir) -> dict:
    """Whether this pattern's chart survives a greyscale printer.

    Most home printers are greyscale, and a chart whose colours differ in hue but not in
    lightness prints as one flat block -- the pattern becomes unusable on exactly the copy a
    maker props open beside them. Measured with the same code the thumbnail check uses,
    because it is the same failure at a different size.
    """
    colours = [{"role": name, "hex": value} for name, value in (cir.colors or {}).items()]
    reading = colourway(colours)
    if not reading.get("measurable"):
        return {
            "prints": None, "measurable": False,
            "why": reading.get("why", ""),
            "colour_independent_cue": True,
            "note": ("a single-colour pattern has nothing to merge, and the chart carries "
                     "letter cues regardless"),
        }
    return {
        "prints": reading["reads"],
        "measurable": True,
        "weakest_pair": reading["weakest_pair"],
        "minimum_value_separation": MIN_VALUE_SEPARATION,
        # The cue is what makes a chart usable even when the print *does* merge, and it is
        # already rendered. Saying so is the difference between a warning and a dead end.
        "colour_independent_cue": True,
        "why": (reading["why"] + ". The chart carries a letter cue per colour either way, so "
                "a merged print is harder to read rather than impossible"),
    }


def outcome_price(twin, *, make_hours: float, make_lane: str, colours: int,
                  market_median_cad: float) -> dict:
    """A price built from the object the buyer ends up with, never from the page count.

    The requirement's closing sentence is a rule about what may enter the arithmetic. The
    honest way to hold that is to make the number impossible to derive from the forbidden
    thing: no page count reaches this function, so none can reach the price.

    The market median anchors it. Everything else moves it relative to that anchor, because a
    price with no relation to what the department charges is a number this company made up
    about a market it has observed.
    """
    if market_median_cad <= 0:
        raise ValueStackRefused(
            "there is no observed market price to anchor against, and an outcome price with "
            "no anchor is a number invented about a market somebody has already measured")

    area_cm2 = max(1.0, (twin.width_cm or 1.0) * (twin.height_cm or 1.0))
    # Each factor is a multiplier around 1.0, so the anchor stays recognisable and the
    # reasoning stays legible: a bigger object, a longer make and deeper support each move
    # the price, and none of them replaces the market.
    size_factor = min(1.5, max(0.7, (area_cm2 / 3000.0) ** 0.25))
    commitment_factor = min(1.5, max(0.7, (make_hours / 12.0) ** 0.3))
    support_factor = 1.0 + 0.05 * max(0, colours - 1)

    weighted = (PRICE_FACTORS[0].weight * size_factor
                + PRICE_FACTORS[1].weight * commitment_factor
                + PRICE_FACTORS[2].weight * support_factor)
    price = round(market_median_cad * weighted, 2)
    return {
        "price_cad": price,
        "anchor_cad": round(market_median_cad, 2),
        "make_lane": make_lane,
        "factors": {
            "finished_object": round(size_factor, 3),
            "commitment": round(commitment_factor, 3),
            "support_depth": round(support_factor, 3),
        },
        "never_priced_on": list(NEVER_PRICED_ON),
        "why": (f"anchored on the department's observed median of "
                f"CA${market_median_cad:.2f} and moved by the finished object "
                f"({twin.width_cm:.0f} x {twin.height_cm:.0f} cm), the commitment "
                f"({make_hours:g} hours, {make_lane}) and the support depth ({colours} "
                f"colours). Page count is not an input, which is the requirement rather "
                f"than a preference"),
    }


def value_stack(cir, twin, *, make_hours: float, make_lane: str,
                market_median_cad: float) -> dict:
    """Everything a flagship gives the buyer beyond the instructions, in one block."""
    return {
        "progress": milestones(cir, twin),
        "print": print_safety(cir),
        "price": outcome_price(twin, make_hours=make_hours, make_lane=make_lane,
                               colours=len(cir.colors or {}),
                               market_median_cad=market_median_cad),
        "gated": {
            "video": ("a filmed tutorial needs a media capability this company does not "
                      "have. Named rather than promised, because a listing that offers a "
                      "video it cannot make is the plainest kind of misrepresentation"),
        },
    }
