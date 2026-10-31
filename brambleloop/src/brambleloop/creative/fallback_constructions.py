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
PANEL_PAIR = "panel_pair"
TOTE = "tote"
TRIANGLE = "triangle"
REFUSED = "refused"

VESSEL_CATEGORIES = frozenset({"basket"})

# Category -> the construction it would need. None of these is a flat panel.
NEEDS: dict[str, str] = {
    "amigurumi": "shaped pieces worked in the round, stuffed and joined",
    "hat": "a crown worked in the round and graded per head circumference",
    "garment": "a graded garment design (creative.garment_design)",
    "stocking": "a closed tube with a heel and toe",
    "nursery": "several shaped pieces assembled on a hanger",
    "toy": "shaped pieces worked in the round, stuffed and joined",
    "coaster": "a disc worked in joined rounds (products.vessels.build_hexagon_coaster)",
    # Review OPUS2C N3.2: shaped or charted categories the flat route must not take.
    "ornament": "a small shaped or closed piece with a hanging loop",
    "flower": "a motif worked in rounds and joined",
    # `mosaic_blanket` and `graphghan` are deliberately NOT refused here: they are flat
    # fabrics, W-CONCEPT's intake refuses them upstream, publication's colourwork rule
    # (`first_customer.colourwork_findings`) refuses a mosaic claim the fabric cannot make, and
    # test_shadow drafts a raw mosaic concept to prove bad arithmetic dies at the compiler.
}

# Title words that name a shaped, closed or assembled object whatever the category says. The
# assembled forms are launch0's (a flat panel under them promises a make it does not contain).
_SHAPED_WORDS = ("amigurumi", "hat", "beanie", "bonnet", "cardigan", "tee", "sweater",
                 "shawl", "shawlette", "cluster", "egg cosy", "mitten", "sock",
                 # Review OPUS2C N3.2: motif assemblies and shaped beds are not one panel.
                 "granny", "hexagon", "hexie", "bed")


def _shaped_title(title: str) -> str | None:
    from ..products.launch0 import ASSEMBLED_FORMS

    lowered = (title or "").lower()
    for word in tuple(ASSEMBLED_FORMS) + _SHAPED_WORDS:
        if re.search(rf"\b{re.escape(word)}s?\b", lowered):
            return word
    return None


def _several_sizes(*texts: str) -> str | None:
    """The first size promise in a concept's slug, title or rationale (gates.size_claims)."""
    from ..gates import size_claims

    for text in texts:
        words = re.sub(r"[-_]", " ", text or "")
        found = size_claims.claims_in(words)
        if found:
            return found[0]["phrase"]
    return None


def plan(*, category: str, title: str, is_bundle: bool = False, slug: str = "",
         rationale: str = "") -> dict:
    """The construction family a fallback concept is drafted in, and why."""
    if is_bundle:
        return {"family": REFUSED, "needs": "the member releases it collects",
                "why": "a bundle is a collection of other designs, not a design to draft"}
    # Review OPUS2C N3.1: one draft is one release is one size. A concept whose slug, title
    # or premise promises several (a trio, three sizes) is refused, never drafted as one.
    promise = _several_sizes(slug, title, rationale)
    if promise:
        return {"family": REFUSED,
                "needs": "one certified release per size (products.vessels.build_basket per "
                         "BASKET_SIZES), each listed on its own",
                "why": (f"the concept promises several sizes ({promise!r}); one fallback draft "
                        f"is one release of one size")}
    if category in NEEDS:
        return {"family": REFUSED, "needs": NEEDS[category],
                "why": (f"category {category!r} needs {NEEDS[category]}; the fallback drafts "
                        f"flat panels and baskets only")}
    if category in VESSEL_CATEGORIES:
        return {"family": VESSEL, "needs": "", "why": "a basket is worked in the round"}
    if category in TOTE_CATEGORIES or re.search(_TOTE_WORDS, (title or "").lower()):
        rest = re.sub(_TOTE_WORDS, "", (title or "").lower())
        if not _shaped_title(rest):
            return {"family": TOTE, "needs": "",
                    "why": "a tote is a vessel worked in the round with two sewn straps"}
    lowered = (title or "").lower()
    if category in TRIANGLE_CATEGORIES or re.search(_TRIANGLE_WORDS, lowered):
        named = re.search(_STITCH_PATTERN_WORDS, lowered)
        if named:
            return {"family": REFUSED,
                    "needs": f"a {named.group(0)} stitch chart worked on triangle shaping",
                    "why": (f"the title names {named.group(0)!r}, a stitch pattern the plain "
                            f"triangle rule does not chart; drafting it would sell a "
                            f"{named.group(0)} the pattern does not make")}
        return {"family": TRIANGLE, "needs": "",
                "why": "a triangle shawl worked flat from the point, increasing at each end"}
    if (category in PANEL_PAIR_CATEGORIES or re.search(_PANEL_PAIR_WORDS, lowered)) \
            and not _shaped_title(re.sub(_PANEL_PAIR_WORDS, "", lowered)):
        return {"family": PANEL_PAIR, "needs": "",
                "why": "a cushion is a front and a back panel seamed around a pad"}
    word = _shaped_title(title)
    if word:
        return {"family": REFUSED, "needs": f"the construction a {word} is made in",
                "why": (f"the title names a {word!r}, which one flat panel does not make; the "
                        f"fallback refuses rather than drafting a panel under that name")}
    return {"family": FLAT_PANEL, "needs": "", "why": "a flat form"}


# A cushion or pillow cover: two identical panels of the concept's own repeat, joined on three
# edges and closed over the pad on the fourth. Matching panels make every seam's two edges the
# same length by construction, which is what the assembly check measures.
PANEL_PAIR_CATEGORIES = frozenset({"pillow", "wedding"})
_PANEL_PAIR_WORDS = r"\b(?:cushion|pillow)s?\b"
PANEL_PAIR_PRIMITIVES = ("creative.fallback_constructions.panel_pair",)


def panel_pair(panel: CIR) -> CIR:
    """Front and back from one flat-panel CIR, with the seams that make it a cushion."""
    import dataclasses

    from ..cir.model import Seam

    if len(panel.components) != 1:
        raise ValueError(f"{panel.slug}: a panel pair is built from exactly one panel")
    body = panel.components[0]
    front = dataclasses.replace(body, name="front", make=1)
    back = dataclasses.replace(body, name="back", make=1)
    assembly = [Seam("whipstitch", "front", "back", edge_a=e, edge_b=e,
                     note=f"Hold the panels wrong sides together and whipstitch the {e} edges.")
                for e in ("left", "top", "right")]
    assembly.append(Seam("whipstitch", "front", "back", edge_a="bottom", edge_b="bottom",
                         stuff_before_closing=True,
                         note="Insert the cushion pad, then whipstitch the bottom edges closed."))
    return dataclasses.replace(
        panel, components=[front, back], assembly=assembly,
        designer_notes=(f"{panel.designer_notes}; drafted as a cushion cover: front and back "
                        f"panels, seamed on all four edges around a pad"))


# A triangle shawl, worked flat from the point: three single crochet on a three-chain
# foundation, then an increase at each end of every row. Plain fabric in two-row stripes (every
# change falls at the same edge, so the resting colour is carried up that edge). A title that
# names a stitch pattern is refused, because plain single crochet is not lattice, lace or cable.
TRIANGLE_CATEGORIES = frozenset({"shawl"})
_TRIANGLE_WORDS = r"\b(?:shawl|shawlette|triangle scarf|kerchief)s?\b"
_STITCH_PATTERN_WORDS = (r"\b(?:lattice|lace|lacy|mosaic|cable[sd]?|bobble[sd]?|granny|"
                         r"chevron|ripple|waffle|shell|puff|popcorn|star|diamond|tulip|"
                         r"fair ?isle|tapestry|filet)\b")
TRIANGLE_PRIMITIVES = ("creative.fallback_constructions.triangle",)
SHAWL_WINGSPAN_CM = 150.0


def triangle(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A corner-to-point triangle shawl in the concept's palette, sized by its wingspan."""
    from ..creative.prototype import gauge_for

    gauge = gauge_for(concept.yarn_weight)
    palette = list(concept.colors)
    if not palette:
        raise ValueError(f"{concept.slug}: a shawl needs at least one colour")
    # The last row's count is 3 + 2 * (rows - 1); choose the row count whose last row is
    # nearest the wingspan at stitch gauge.
    wanted = SHAWL_WINGSPAN_CM * gauge.stitches_per_10cm / 10.0
    n_rows = max(10, int(round((wanted - 3) / 2)) + 1)
    rows = [Row(index=1, ops=[Op("sc", 3)], declared_count=3, turning_chain=1,
                color=palette[0])]
    count = 3
    for i in range(2, n_rows + 1):
        rows.append(Row(index=i, ops=[Op("inc"), Op("sc", count - 2), Op("inc")],
                        declared_count=count + 2, turning_chain=1,
                        color=palette[((i - 1) // 2) % len(palette)]))
        count += 2
    wingspan = count * 10.0 / gauge.stitches_per_10cm
    depth = n_rows * 10.0 / gauge.rows_per_10cm
    return CIR(
        slug=concept.slug, title=concept.title, version=version, construction="flat_rows",
        risk_class=concept.risk_class, colors=dict(concept.colors), gauge=gauge,
        materials=[Material(name=f"{concept.yarn_weight} acrylic",
                            yarn_weight=concept.yarn_weight, color_id=p) for p in palette],
        components=[Component(
            name="shawl", construction="flat_rows", rows=rows, foundation=3,
            foundation_kind="chain",
            note=("Worked flat from the point. Increase in the first and last stitch of every "
                  "row; the colour changes every two rows at the same edge, so carry the "
                  "resting colour loosely up that edge."))],
        designer_notes=(f"{concept.category} concept drafted as a triangle shawl: {n_rows} "
                        f"rows from a 3-stitch point to {count} stitches, plain single "
                        f"crochet in two-row stripes"),
        finished_size_note=(
            f"A triangle about {wingspan:.0f} cm along the top edge and {depth:.0f} cm from "
            f"the top edge to the point, at the stated gauge. Computed, not yet measured on a "
            f"worked sample."),
        provenance=provenance,
    )


# A basket's finished size, chosen from its title, never from the panel width table: the
# panel width is a flat dimension and a basket's is a diameter.
_SIZE_WORDS = (("bread", "small"), ("market", "large"))


def _basket_size(title: str):
    from ..products.vessels import BASKET_SIZES

    lowered = (title or "").lower()
    key = next((k for word, k in _SIZE_WORDS if word in lowered), "medium")
    return next(s for s in BASKET_SIZES if s.key == key)


def vessel(concept, *, version: str = "1.0.0", provenance=None, size: str | None = None) -> CIR:
    """A basket from the concept's own stitch repeat and palette, worked in joined rounds."""
    from ..creative.prototype import gauge_for
    from ..products.vessels import (BASKET_SIZES, _disc_rounds, base_stitches_for,
                                    hexagon_spans_cm)

    gauge = gauge_for(concept.yarn_weight)
    spec = (next(s for s in BASKET_SIZES if s.key == size) if size
            else _basket_size(concept.title))
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


# A tote: the large vessel, plus two straps sewn to its top round. Each strap end is sewn
# across `STRAP_STITCHES` stitches of the rim (`stitches_from_centre`, which `cir.assembly`
# measures on a piece worked in rounds), so every join's two lengths are compared. Ends sit at
# the eighth points of the rim: one strap on the front half, its mirror on the back.
TOTE_CATEGORIES = frozenset({"bag"})
_TOTE_WORDS = r"\b(?:tote|bag|market bag|shopper)s?\b"
STRAP_STITCHES = 6
STRAP_CM = 50.0
TOTE_PRIMITIVES = ("creative.fallback_constructions.tote", "products.vessels._disc_rounds",
                   "products.vessels.base_stitches_for", "cir.assembly._placed_on_round_cm")


def tote(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A tote bag: a large vessel in the concept's repeat and palette, with two sewn straps."""
    import dataclasses

    from ..cir.model import Seam

    body_cir = vessel(concept, version=version, provenance=provenance, size="large")
    body = body_cir.components[0]
    n = body.rows[-1].declared_count
    top = body.rows[-1].index
    colour = body.rows[0].color
    gauge = body_cir.gauge
    strap_rows = max(20, int(round(STRAP_CM * gauge.rows_per_10cm / 10.0)))
    strap = Component(
        name="strap", construction="flat_rows", foundation=STRAP_STITCHES,
        foundation_kind="chain", make=2, grain="up",
        rows=[Row(index=i, ops=[Op("sc", STRAP_STITCHES)], declared_count=STRAP_STITCHES,
                  color=colour, turning_chain=1) for i in range(1, strap_rows + 1)],
        note=(f"Make 2. Chain {STRAP_STITCHES + 1}, then {strap_rows} rows of "
              f"{STRAP_STITCHES} single crochet: a strap about "
              f"{strap_rows * 10.0 / gauge.rows_per_10cm:.0f} cm long."))
    half = STRAP_STITCHES // 2
    first, second = n // 8, 3 * n // 8      # the front half's eighth points
    assembly = [
        Seam("whipstitch", "strap", "basket", edge_a="bottom", edge_b="top", at_round=top,
             stitches_from_centre=half, mirrored=True,
             note=(f"Centre the strap's first end over stitch {first} of round {top}, "
                   f"counting from the round's join; the second strap's first end goes over "
                   f"stitch {first + n // 2}")),
        Seam("whipstitch", "strap", "basket", edge_a="top", edge_b="top", at_round=top,
             stitches_from_centre=half, mirrored=True,
             note=(f"Without twisting the strap, centre its other end over stitch {second} "
                   f"of round {top}; the second strap's other end goes over stitch "
                   f"{second + n // 2}")),
    ]
    return dataclasses.replace(
        body_cir, components=[body, strap], assembly=assembly,
        designer_notes=(f"{body_cir.designer_notes}; drafted as a tote: two "
                        f"{STRAP_STITCHES}-stitch straps sewn across {STRAP_STITCHES} "
                        f"stitches of the top round at its eighth points"))


VESSEL_PRIMITIVES = ("creative.fallback_constructions.vessel", "products.vessels._disc_rounds",
                     "products.vessels.base_stitches_for")
