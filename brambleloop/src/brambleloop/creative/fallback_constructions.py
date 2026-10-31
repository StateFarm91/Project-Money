"""OPUS2-P0: P0-DRAFT-CONSTRUCTIONS -- route a radar fallback draft to a construction it can be.

W-CONCEPT found that the radar draft path (`runtime.pipeline.concept_to_cir`) makes the same
flat striped panel for every concept in a category. Every radar seed that still reaches that
fallback (the rest are engineered designs) is a shaped object: a storage basket, an amigurumi,
a hat, a garment, a shawl, a stocking, a mobile, a cushion or a bundle. A flat panel under
those names is a pattern that does not make the thing it is called.

This module decides, deterministically and before any CIR exists, which construction family a
fallback concept is drafted in:

- ``flat_panel`` -- a flat form; `concept_to_cir` exactly as before.
- ``vessel``     -- a basket: a disc base from a magic ring (`products.vessels` wedge
                    arithmetic), then straight walls worked in joined rounds that carry the
                    concept's own stitch repeat and palette, round for round as the panel
                    carried them row for row.
- ``refused``    -- a form no deterministic fallback rule makes (shaped toys, graded hats and
                    garments, shawls, closed or assembled forms, bundles). It is refused by
                    name with the construction it needs, never drafted as a panel.

The concept's geometry still comes from `concept_geometry` (the lineage check recomputes it);
this module only changes the shape the same stitches are worked into, and records that in the
producer chain so provenance names what actually made the design.
"""
from __future__ import annotations

import math
import re

from ..cir.model import CIR, Component, Material, Op, Repeat, Row

FLAT_PANEL = "flat_panel"
VESSEL = "vessel"
REFUSED = "refused"

VESSEL_CATEGORIES = frozenset({"basket"})

# Category -> the construction it would need. None of these is a flat panel.
NEEDS: dict[str, str] = {
    "amigurumi": "shaped pieces worked in the round, stuffed and joined",
    "hat": "a crown worked in the round and graded per head circumference",
    "garment": "a graded garment design (creative.garment_design)",
    "shawl": "triangle or crescent shaping with planned increases",
    "bag": "a vessel with a strap or handle join",
    "stocking": "a closed tube with a heel and toe",
    "nursery": "several shaped pieces assembled on a hanger",
    "toy": "shaped pieces worked in the round, stuffed and joined",
    "coaster": "a disc worked in joined rounds (products.vessels.build_hexagon_coaster)",
}

# Title words that name a shaped, closed or assembled object whatever the category says. The
# assembled forms are launch0's (a flat panel under them promises a make it does not contain).
_SHAPED_WORDS = ("amigurumi", "hat", "beanie", "bonnet", "cardigan", "tee", "sweater",
                 "shawl", "shawlette", "tote", "bag", "cluster", "egg cosy", "mitten", "sock")


def _shaped_title(title: str) -> str | None:
    from ..products.launch0 import ASSEMBLED_FORMS

    lowered = (title or "").lower()
    for word in tuple(ASSEMBLED_FORMS) + _SHAPED_WORDS:
        if re.search(rf"\b{re.escape(word)}s?\b", lowered):
            return word
    return None


def plan(*, category: str, title: str, is_bundle: bool = False) -> dict:
    """The construction family a fallback concept is drafted in, and why."""
    if is_bundle:
        return {"family": REFUSED, "needs": "the member releases it collects",
                "why": "a bundle is a collection of other designs, not a design to draft"}
    if category in NEEDS:
        return {"family": REFUSED, "needs": NEEDS[category],
                "why": (f"category {category!r} needs {NEEDS[category]}; the fallback drafts "
                        f"flat panels and baskets only")}
    if category in VESSEL_CATEGORIES:
        return {"family": VESSEL, "needs": "", "why": "a basket is worked in the round"}
    word = _shaped_title(title)
    if word:
        return {"family": REFUSED, "needs": f"the construction a {word} is made in",
                "why": (f"the title names a {word!r}, which one flat panel does not make; the "
                        f"fallback refuses rather than drafting a panel under that name")}
    return {"family": FLAT_PANEL, "needs": "", "why": "a flat form"}


# A basket's finished size, chosen from its title, never from the panel width table: the
# panel width is a flat dimension and a basket's is a diameter.
_SIZE_WORDS = (("bread", "small"), ("market", "large"))


def _basket_size(title: str):
    from ..products.vessels import BASKET_SIZES

    lowered = (title or "").lower()
    key = next((k for word, k in _SIZE_WORDS if word in lowered), "medium")
    return next(s for s in BASKET_SIZES if s.key == key)


def vessel(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A basket from the concept's own stitch repeat and palette, worked in joined rounds."""
    from ..creative.prototype import gauge_for
    from ..products.vessels import _disc_rounds, base_stitches_for, hexagon_spans_cm

    gauge = gauge_for(concept.yarn_weight)
    spec = _basket_size(concept.title)
    repeat = [(str(code), int(n)) for code, n in concept.stitch_repeat]
    unit = sum(n for _, n in repeat)
    if unit <= 0:
        raise ValueError(f"{concept.slug}: an empty stitch repeat cannot be worked")
    palette = list(concept.colors)
    if not palette:
        raise ValueError(f"{concept.slug}: a basket needs at least one colour")
    main, accent = palette[0], palette[1 % len(palette)]
    # Six wedges for a flat base, and a whole number of repeats around every wall round.
    step = 6 * unit // math.gcd(6, unit)
    wanted = base_stitches_for(spec.across_cm, gauge)
    base_count = max(step * 2, int(round(wanted / step)) * step)
    rows = _disc_rounds(base_count, main)
    row_cm = 10.0 / gauge.rows_per_10cm
    wall_rounds = max(6, int(round(spec.tall_cm / row_cm)))
    index = rows[-1].index
    for w in range(1, wall_rounds + 1):
        index += 1
        if w % 2 == 0:
            ops = [Repeat([Op(code, n) for code, n in repeat], times=base_count // unit)]
            colour = accent
        else:
            ops = [Op("sc", base_count)]
            colour = main
        rows.append(Row(index=index, ops=ops, declared_count=base_count, color=colour))
    points, flats = hexagon_spans_cm(base_count, gauge)
    return CIR(
        slug=concept.slug,
        title=concept.title,
        version=version,
        construction="joined_rounds",
        risk_class=concept.risk_class,
        colors=dict(concept.colors),
        gauge=gauge,
        materials=[Material(name=f"{concept.yarn_weight} acrylic",
                            yarn_weight=concept.yarn_weight, color_id=p) for p in palette],
        components=[Component(
            name="basket", construction="joined_rounds", rows=rows, foundation=0,
            foundation_kind="magic_ring",
            note=("Worked in one piece from the centre of the base. Work each increase into "
                  "the second stitch of the previous round's increase, so the increases stack "
                  "into six corners and the base is a hexagon."))],
        designer_notes=(f"{concept.category} concept drafted as a vessel: hexagon base of "
                        f"{base_count} sts, {wall_rounds} wall rounds alternating plain "
                        f"single crochet and the concept's {unit}-st repeat"),
        finished_size_note=(
            f"A hexagonal basket about {points:.1f} cm across the points and {flats:.1f} cm "
            f"across the flats, walls about {wall_rounds * row_cm:.0f} cm tall, at the stated "
            f"gauge. Computed, not yet measured on a worked sample."),
        provenance=provenance,
    )


VESSEL_PRIMITIVES = ("creative.fallback_constructions.vessel", "products.vessels._disc_rounds",
                     "products.vessels.base_stitches_for")
