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
COSY = "cosy"
TRIANGLE = "triangle"
TAPESTRY = "tapestry"
AMIGURUMI = "amigurumi"
POUCH = "pouch"
REFUSED = "refused"

VESSEL_CATEGORIES = frozenset({"basket"})

# Category -> the construction it would need. None of these is a flat panel.
NEEDS: dict[str, str] = {
    "amigurumi": "shaped pieces worked in the round, stuffed and joined",
    "hat": ("a hat height and negative ease from a published standard: the CYC head "
            "circumference chart (HEAD_CIRCUMFERENCE_CM) publishes circumference only"),
    "garment": "a graded garment design (creative.garment_design)",
    "stocking": "a closed tube with a heel and toe",
    "nursery": "several shaped pieces assembled on a hanger",
    "toy": "shaped pieces worked in the round, stuffed and joined",
    # Review OPUS2E E1: a bag that is not a tote (drawstring, backpack, clutch, crossbody,
    # pouch, sachet, holder) is a different construction; only a titled tote is drafted.
    "bag": ("a bag construction the tote rule does not make (closure, gusset, flap, "
            "drawstring or shaped body)"),
    "coaster": "a disc worked in joined rounds (products.vessels.build_hexagon_coaster)",
    # Review OPUS2C N3.2: shaped or charted categories the flat route must not take.
    "ornament": "a small shaped or closed piece with a hanging loop",
    "flower": "a motif worked in rounds and joined",
    # `mosaic_blanket` and `graphghan` are deliberately NOT refused here: they are flat
    # fabrics, W-CONCEPT's intake refuses them upstream, publication's colourwork rule
    # (`first_customer.colourwork_findings`) refuses a mosaic claim the fabric cannot make, and
    # test_shadow drafts a raw mosaic concept to prove bad arithmetic dies at the compiler.
}

# The Craft Yarn Council head circumference chart, transcribed from the page on the retrieval
# date (cm row; ranges kept, as cir.graded keeps them). It is the ONLY sourced head data in
# this build. It publishes no hat height and no negative ease, so a hat cannot be sized from
# it without inventing two numbers -- and is refused rather than guessed.
HEAD_CHART_URL = "https://www.craftyarncouncil.com/standards/head-circumference-chart"
HEAD_CHART_RETRIEVED = "2026-10-31"
HEAD_CIRCUMFERENCE_CM: dict[str, tuple[float, float]] = {
    "preemie": (23.0, 30.5), "baby": (35.5, 40.5), "toddler": (40.5, 46.0),
    "child": (45.5, 51.0), "tween": (51.0, 56.0), "woman": (53.0, 58.5), "man": (56.0, 61.0),
}
HAT_UNSOURCED = ("hat_height", "negative_ease")

# Title words that name a shaped, closed or assembled object whatever the category says. The
# assembled forms are launch0's (a flat panel under them promises a make it does not contain).
_SHAPED_WORDS = ("amigurumi", "hat", "beanie", "bonnet", "cardigan", "tee", "sweater",
                 "shawl", "shawlette", "cluster", "mitten", "sock", "bag",
                 # Review OPUS2E E1/E4: bag forms and cosy characters the plain rules lack.
                 "drawstring", "holder", "backpack", "clutch", "crossbody", "pouch", "sachet",
                 "bean bag", "diaper", "purse", "wallet",
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


def _colour_count_free(text: str) -> str:
    """'Two-Colour Basket' names two colours, not two baskets: the size-claim count reads a
    number word before a vessel noun, so the colour count is renamed before that check. Only
    when no plural vessel noun is present -- "Two Colour Baskets" is still two baskets."""
    t = text or ""
    if re.search(r"\b(?:baskets|bowls|bins|totes|bags|pots|buckets|trays)\b", t, re.I):
        return t
    return re.sub(r"\btwo[- _]?(?:colou?r(?:ed)?|tone[d]?)\b", "bicolour", t, flags=re.I)


def plan(*, category: str, title: str, is_bundle: bool = False, slug: str = "",
         rationale: str = "") -> dict:
    """The construction family a fallback concept is drafted in, and why."""
    if is_bundle:
        return {"family": REFUSED, "needs": "the member releases it collects",
                "why": "a bundle is a collection of other designs, not a design to draft"}
    # Review OPUS2C N3.1: one draft is one release is one size. A concept whose slug, title
    # or premise promises several (a trio, three sizes) is refused, never drafted as one.
    promise = _several_sizes(_colour_count_free(slug), _colour_count_free(title), rationale)
    if promise:
        return {"family": REFUSED,
                "needs": "one certified release per size (products.vessels.build_basket per "
                         "BASKET_SIZES), each listed on its own",
                "why": (f"the concept promises several sizes ({promise!r}); one fallback draft "
                        f"is one release of one size")}
    if category == "amigurumi":
        # P0 construction breadth (owner directive 2026-11-01 section 3C): a plain ball-body
        # bear or bunny is drafted as shaped rounds, stuffed and joined; any other animal,
        # character, size, count or feature is refused by name.
        return amigurumi_route(title)
    if category in POUCH_CATEGORIES and re.search(r"\bdrawstring\b", fold_title(title)):
        # P0 construction breadth (bags and accessories): a plain drawstring pouch is a small
        # round vessel with an eyelet round and a threaded chain cord.
        return pouch_route(title)
    titled_tote = bool(re.search(_TOTE_WORDS, (title or "").lower()))
    if category in NEEDS and not (category == "bag" and titled_tote):
        return {"family": REFUSED, "needs": NEEDS[category],
                "why": (f"category {category!r} needs {NEEDS[category]}; the fallback drafts "
                        f"flat panels and baskets only")}
    if category in VESSEL_CATEGORIES:
        # P0 construction breadth (colourwork products): a basket whose title claims a
        # colourwork technique is drafted as that technique or refused by name -- never the
        # plain striped vessel under a colourwork name.
        coloured = tapestry_route(title)
        if coloured is not None:
            return coloured
        return {"family": VESSEL, "needs": "", "why": "a basket is worked in the round"}
    if re.search(_EGG_COSY_WORDS, (title or "").lower()):
        rest = re.sub(_EGG_COSY_WORDS, "", (title or "").lower())
        extra = re.search(_COSY_NOT_PLAIN, rest)
        if extra:
            return {"family": REFUSED,
                    "needs": (f"the construction a {extra.group(0).strip()!r} cosy needs "
                              f"(appliqué pieces, a texture stitch, colourwork, or a second "
                              f"object)"),
                    "why": (f"the title names {extra.group(0).strip()!r}, which a plain "
                            f"single-crochet cup does not make")}
        if not _shaped_title(rest):
            return {"family": COSY, "needs": "",
                    "why": "an egg cosy is a small cup worked from the crown down"}
    if re.search(_TOTE_WORDS, (title or "").lower()):
        lowered_t = (title or "").lower()
        rest = re.sub(r"\bbags?\b", "", re.sub(_TOTE_WORDS, "", lowered_t))
        # Review OPUS2E E1: one tote is one finished object. Its straps are parts, so no
        # count, plural or "set" may be backed by them: such a title is refused here.
        many = re.search(_MULTIPLE_WORDS, lowered_t)
        if many:
            return {"family": REFUSED,
                    "needs": "one certified release per finished bag, each listed on its own",
                    "why": (f"the title promises more than one bag ({many.group(0)!r}); one "
                            f"tote draft is one bag, and its straps are not pieces")}
        extra = re.search(_TOTE_NOT_PLAIN, rest)
        if extra:
            return {"family": REFUSED,
                    "needs": (f"the construction {extra.group(0).strip()!r} needs (a second "
                              f"object, a pocket, a closure or a lining) as its own pieces"),
                    "why": (f"the title names {extra.group(0).strip()!r}, which the plain "
                            f"one-piece tote with two straps does not make")}
        oversize = re.search(_TOTE_SIZE_UNSUPPORTED, lowered_t)
        if oversize:
            return {"family": REFUSED,
                    "needs": "a vessel size beyond products.vessels.BASKET_SIZES, measured",
                    "why": (f"the title promises {oversize.group(0)!r}; the tote is drafted "
                            f"only at the three measured vessel sizes")}
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
TOTE_CATEGORIES = frozenset({"bag"})     # the category alone never routes to a tote (E1)
_TOTE_WORDS = r"\b(?:tote|market bag|shopper)s?\b"
_MULTIPLE_WORDS = (r"\b(?:\d+|two|three|four|five|six|pair|trio|set|duo|totes|bags|"
                   r"shoppers|x\s*\d+|bundle|collection|double|family|mother|daughter|twins?|"
                   r"matching)\b")
# Review OPUS2EF2 EF2-1: a second object or a construction feature the plain tote does not
# have (a pocket, a zip, a lining, a reversible body) is refused, never dropped silently.
_TOTE_NOT_PLAIN = (r"(?:[&+]|\b(?:and|with|pockets?|zip|zips|zipper|zippered|zipped|lined|"
                   r"lining|reversible|gusset(?:ed)?|flap|button|buttoned|magnetic|clasp)\b)")
# Review OPUS2E E1 / EF2-3: a size word on the title is honoured, never overridden by "large";
# a size word beyond the three vessel sizes is refused rather than drafted at another size.
_TOTE_SIZE_WORDS = (("small", "small"), ("mini", "small"), ("tiny", "small"),
                    ("petite", "small"), ("medium", "medium"), ("large", "large"),
                    ("big", "large"))
_TOTE_SIZE_UNSUPPORTED = r"\b(?:jumbo|giant|huge|oversized?|xl|xxl|extra[- ]large)\b"
STRAP_STITCHES = 6
STRAP_CM = 50.0
TOTE_PRIMITIVES = ("creative.fallback_constructions.tote", "products.vessels._disc_rounds",
                   "products.vessels.base_stitches_for", "cir.assembly._placed_on_round_cm")


def tote(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A tote bag: a large vessel in the concept's repeat and palette, with two sewn straps."""
    import dataclasses

    from ..cir.model import Seam

    lowered = (concept.title or "").lower()
    size = next((key for word, key in _TOTE_SIZE_WORDS if re.search(rf"\b{word}\b", lowered)),
                "large")
    body_cir = vessel(concept, version=version, provenance=provenance, size=size)
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


# An egg cosy: a cup worked from the crown down -- a magic-ring disc, then straight rounds --
# sized to sit over an egg whose widest girth is taken as EGG_AROUND_CM. That figure is a
# stated DESIGN ASSUMPTION, not a sourced or measured one: no egg measurement is on file, so
# the finished-size note says so and a physical test confirms the fit. Plain single crochet in two-round stripes of the concept's palette:
# the concept's stitch repeat would force a stitch count that slips off the egg, so it is not
# used, and nothing claims it is. A "set" makes four.
_EGG_COSY_WORDS = r"\begg\s+co(?:s|z)(?:y|ies)\b"
# Review OPUS2E E4: characters need appliqué pieces, "and <object>" is a second design, and a
# named texture is a stitch the plain cup does not contain.
_COSY_NOT_PLAIN = (r"(?:[&+]|\b(?:bunny|bunnies|rabbit|chick|chicks|owl|face|bear|fox|cat|"
                   r"duck|lamb|hen|chicken|penguin|animal|character|and|with|bobble|cable|"
                   r"puff|popcorn|lace|shell|textured?|stripes?|striped|pom[- ]?poms?|tassels?|"
                   r"colou?r[- ]?block|two[- ]tone|fair[- ]isle|mosaic|tapestry|basket)\b)")
# Review OPUS2E E3: the girth is never undershot; a yarn whose next whole wedge overshoots it
# by more than this is refused rather than drafted loose.
COSY_MAX_EASE = 0.15
EGG_AROUND_CM = 13.8
COSY_TALL_CM = 6.0
COSY_SET = 4
COSY_PRIMITIVES = ("creative.fallback_constructions.cosy", "products.vessels._disc_rounds")


def cosy(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A set of egg cosies in the concept's palette, worked from the crown down."""
    from ..creative.prototype import gauge_for
    from ..products.launch0 import PLURAL_MARKERS
    from ..products.vessels import _disc_rounds

    gauge = gauge_for(concept.yarn_weight)
    palette = list(concept.colors)
    if not palette:
        raise ValueError(f"{concept.slug}: a cosy needs at least one colour")
    # Review OPUS2E E3: the first whole wedge of six AT OR ABOVE the girth (never below it),
    # and refused if that overshoots the girth by more than COSY_MAX_EASE.
    import math as _math

    count = max(12, _math.ceil(EGG_AROUND_CM * gauge.stitches_per_10cm / 10.0 / 6) * 6)
    around_cm = count * 10.0 / gauge.stitches_per_10cm
    if around_cm > EGG_AROUND_CM * (1 + COSY_MAX_EASE):
        raise ValueError(
            f"{concept.slug}: at {concept.yarn_weight} gauge the nearest flat crown is "
            f"{around_cm:.1f} cm around, more than {COSY_MAX_EASE:.0%} over the egg's "
            f"{EGG_AROUND_CM} cm; a cosy that loose is not drafted")
    rows = _disc_rounds(count, palette[0])
    row_cm = 10.0 / gauge.rows_per_10cm
    wall_rounds = max(4, int(round(COSY_TALL_CM / row_cm)))
    index = rows[-1].index
    for w in range(1, wall_rounds + 1):
        index += 1
        rows.append(Row(index=index, ops=[Op("sc", count)], declared_count=count,
                        color=palette[((w - 1) // 2) % len(palette)]))
    lowered = (concept.title or "").lower()
    make = COSY_SET if (re.search(r"\bcos(?:ies)\b|\bcoz(?:ies)\b", lowered)
                        or any(re.search(rf"\b{m}\b", lowered) for m in PLURAL_MARKERS)) else 1
    around = count * 10.0 / gauge.stitches_per_10cm
    return CIR(
        slug=concept.slug, title=concept.title, version=version, construction="joined_rounds",
        risk_class=concept.risk_class, colors=dict(concept.colors), gauge=gauge,
        materials=[Material(name=f"{concept.yarn_weight} acrylic",
                            yarn_weight=concept.yarn_weight, color_id=p) for p in palette],
        components=[Component(
            name="cosy", construction="joined_rounds", rows=rows, foundation=0,
            foundation_kind="magic_ring", make=make,
            note=(f"Make {make}. Worked from the crown down: increase to {count} stitches, "
                  f"then {wall_rounds} straight rounds, changing colour every two rounds."))],
        designer_notes=(f"{concept.category} concept drafted as {make} egg cosies: a "
                        f"{count}-stitch crown and {wall_rounds} straight rounds of plain "
                        f"single crochet; the concept's stitch repeat is not used"),
        finished_size_note=(
            f"About {around:.1f} cm around and {wall_rounds * row_cm:.1f} cm tall at the "
            f"stated gauge, designed for an egg about {EGG_AROUND_CM} cm around its widest "
            f"point (an assumed size, not a measured one). Computed, not yet measured on a "
            f"worked sample."),
        provenance=provenance)


VESSEL_PRIMITIVES = ("creative.fallback_constructions.vessel", "products.vessels._disc_rounds",
                     "products.vessels.base_stitches_for")


# ---------------------------------------------------------------------------------------
# Tapestry crochet baskets (P0 construction breadth, owner directive 2026-11-01 section 3A).
#
# Tapestry crochet: single crochet worked in joined rounds, the colour not in use laid along
# the top of the previous round and worked over, so every stitch is one colour and the
# carried strand is hidden inside the fabric. The CIR expresses it with `Op.color` (P0-CIR-
# COLOURWORK): each op names the yarn it is worked in; the twin paints the chart, charges the
# carried strand to yardage (`twin.CARRY_FACTOR`) and `launch0.fabric_truth` judges the name
# by `technique_backed("tapestry", ...)`. The charts below are original geometric repeats,
# six stitches wide so they tile any base count the hexagon base makes (a multiple of six).
# Only tapestry is drafted. Mosaic and graphghan need stitches that reach past the previous
# round, intarsia needs bobbins with no carried strand, and fair isle / stranded / jacquard
# name a floated technique; none is what this fabric is, so each is refused by name.

def fold_title(title: str | None) -> str:
    """A title as the routing rules read it: NFKC, every Unicode dash (category Pd) as an
    ASCII hyphen, lower case, whitespace collapsed and stripped."""
    import unicodedata

    text = unicodedata.normalize("NFKC", title or "")
    text = "".join("-" if (unicodedata.category(c) == "Pd" or c == "\u2212") else c
                   for c in text)
    return re.sub(r"\s+", " ", text.lower()).strip()


TAPESTRY_CHARTS: dict[str, tuple[str, ...]] = {
    # "X" is the contrast colour, "." the main; read right to left like every round.
    "diamond": ("..XX..", ".XXXX.", "XX..XX", "XX..XX", ".XXXX.", "..XX.."),
    "check": ("XXX...", "XXX...", "XXX...", "...XXX", "...XXX", "...XXX"),
}
TAPESTRY_DEFAULT_CHART = "diamond"
# The motif library (products.motifs, original validated grids) is a source of tapestry
# charts too: each grid is widened to two stitches per cell (a one-stitch contrast is a dot,
# not a motif: COLOURWORK_MIN_RUN) and admitted only if launch0's own tapestry rule backs the
# widened chart. Words name the library motif they back (launch0.MOTIF_DECLARATIONS).
LIBRARY_CHART_WORDS: dict[str, str] = {
    "fir": "fir-and-star", "firs": "fir-and-star", "tree": "fir-and-star",
    "trees": "fir-and-star", "forest": "fir-and-star", "star": "fir-and-star",
    "stars": "fir-and-star", "lattice": "diamond-lattice", "chevron": "chevron-band",
    "chevrons": "chevron-band", "basketweave": "basketweave", "heart": "heart-row",
    "hearts": "heart-row", "pumpkin": "pumpkin-row", "pumpkins": "pumpkin-row",
    "tulip": "tulip-trellis", "tulips": "tulip-trellis", "flower": "tulip-trellis",
    "flowers": "tulip-trellis", "floral": "tulip-trellis",
}
_TAPESTRY_CHART_WORDS = {"diamond": "diamond", "diamonds": "diamond", "argyle": None,
                         "check": "check", "checked": "check", "checker": "check",
                         "checkerboard": "check", "chequer": "check", "chequered": "check",
                         "chequerboard": "check"}
_TAPESTRY_HEAD = r"\bbasket$"
_TAPESTRY_CLAIM = (r"\b(?:tapestry|colou?r ?work|two[- ]?(?:colou?r(?:ed)?|tone[d]?)|"
                   r"bi[- ]?colou?r(?:ed)?)\b")
_COLOURWORK_NOT_TAPESTRY = (
    (r"\b(?:mosaic|overlay)\b", "stitches that reach past the previous round (overlay "
                                 "mosaic), which no CIR expresses yet"),
    (r"\b(?:graph ?gh?an|c2c|corner[- ]to[- ]corner)\b", "a charted picture worked as a "
                                                       "graphghan, not a basket wall"),
    (r"\b(?:intarsia|duplicate[- ]stitch(?:ed)?)\b", "separate colour blocks with no "
                                                   "carried strand (bobbins), not modelled"),
    (r"\b(?:fair[- ]?isle|stranded|jacquard)\b", "a floated stranded technique; this "
                                                     "fabric carries the strand inside the "
                                                     "stitches, which is tapestry"),
    (r"\b(?:three|four|multi|tri)[- ]?colou?r(?:ed)?\b", "more than two colours in a round; "
                                                       "the charts are two-colour"),
)
_TAPESTRY_ALLOWED_WORDS = frozenset({
    "tapestry", "colourwork", "colorwork", "colour", "color", "work", "two", "tone", "toned",
    "two-colour", "two-color", "two-coloured", "two-colored", "two-tone", "two-toned",
    "bicolour", "bicolor", "bi-colour", "bi-color", "crochet", "crocheted", "storage",
    "round", "hexagon", "hexagonal", "geometric", "modern", "classic", "simple", "everyday",
    "cosy", "cozy", "small", "medium", "large", "catch-all", "catchall", "shelf",
    *[w for w, chart in _TAPESTRY_CHART_WORDS.items() if chart], *LIBRARY_CHART_WORDS,
})
_TAPESTRY_SIZE_WORDS = (("small", "small"), ("medium", "medium"), ("large", "large"))
TAPESTRY_PLAIN_BELOW = 2        # plain main-colour rounds below the chart band
TAPESTRY_PLAIN_RIM = 2          # plain main-colour rounds at the rim
TAPESTRY_PRIMITIVES = ("creative.fallback_constructions.tapestry_basket",
                       "products.vessels._disc_rounds", "products.vessels.base_stitches_for")


def tapestry_route(title: str | None) -> dict | None:
    """The route for a basket title that claims colourwork: None when it claims none."""
    folded = fold_title(title)
    # Only a tapestry / two-colour claim changes the route. Any other colourwork name keeps
    # the existing flow: drafted as the plain vessel, and refused at publication by
    # `launch0.fabric_truth` / `first_customer.colourwork_findings`, which the draft records
    # (test_opus2_draft_constructions pins that for "Nordic Forest Mosaic Storage Basket").
    if not re.search(_TAPESTRY_CLAIM, folded):
        return None
    for rx, needs in _COLOURWORK_NOT_TAPESTRY:
        hit = re.search(rx, folded)
        if hit:
            return {"family": REFUSED, "needs": needs,
                    "why": (f"the title claims {hit.group(0)!r}; the fallback drafts tapestry "
                            f"crochet only, and {hit.group(0)!r} is not that fabric")}
    counted = re.sub(r"\btwo[- ]?(?:colou?r(?:ed)?|tone[d]?)\b", " ", folded)
    if re.search(r"\bbaskets\b", folded) or re.search(_MULTIPLE_WORDS, counted):
        return {"family": REFUSED,
                "needs": "one certified release per basket, each listed on its own",
                "why": "the title promises more than one basket; one draft is one basket"}
    head = re.search(_TAPESTRY_HEAD, folded)
    if not head:
        return {"family": REFUSED, "needs": "a tapestry basket title, or the construction the "
                                            "title names",
                "why": (f"the title {title!r} claims colourwork but its head noun is not "
                        f"'basket'; only a tapestry basket is drafted")}
    before = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", folded[:head.start()])
    unknown = [w for w in before if w not in _TAPESTRY_ALLOWED_WORDS]
    if unknown:
        return {"family": REFUSED,
                "needs": (f"the motif, size or construction {' '.join(unknown)!r} names; only "
                          f"a charted two-colour tapestry basket "
                          f"({', '.join(sorted(TAPESTRY_CHARTS))}) is drafted"),
                "why": (f"the title names {' '.join(unknown)!r}, which the tapestry basket "
                        f"charts do not make")}
    return {"family": TAPESTRY, "needs": "",
            "why": "a tapestry basket is single crochet in joined rounds, two colours carried"}


def _chart_word(word: str) -> str | None:
    return _TAPESTRY_CHART_WORDS.get(word) or LIBRARY_CHART_WORDS.get(word)


def library_chart(slug: str) -> tuple[str, ...]:
    """A library motif widened to two stitches per cell, as a tapestry chart ("X" contrast)."""
    from ..products import motifs

    m = motifs.get(slug)
    return tuple("".join(("X" if c == "1" else ".") * 2 for c in row) for row in m.grid)


def _chart_backed(chart: tuple[str, ...]) -> bool:
    from ..products.launch0 import colourwork_motif, technique_backed

    grid = [["c" if c == "X" else "m" for c in line * 3] for line in chart]
    return technique_backed("tapestry", colourwork_motif(grid))[0]


def tapestry_charts() -> dict[str, tuple[str, ...]]:
    """Every chart a tapestry basket may carry: the built-ins and each library motif whose
    widened chart the tapestry rule backs (computed, never assumed)."""
    out = dict(TAPESTRY_CHARTS)
    for slug in sorted(set(LIBRARY_CHART_WORDS.values())):
        chart = library_chart(slug)
        if _chart_backed(chart):
            out[slug] = chart
    return out


def _tapestry_chart(title: str, slug: str = "") -> str:
    """The chart a brief names, or -- when it names none -- one chosen deterministically from
    the backed charts by the concept's own key, so different briefs get different designs."""
    words = re.findall(r"[a-z]+", fold_title(title))
    chosen = [_chart_word(w) for w in words if _chart_word(w)]
    if chosen:
        return chosen[0]
    if not slug:
        return TAPESTRY_DEFAULT_CHART
    import hashlib

    plain = sorted(c for c in tapestry_charts() if c in TAPESTRY_CHARTS or c in {
        "basketweave", "chevron-band", "diamond-lattice"})        # no figurative motif unasked
    return plain[int(hashlib.sha256(slug.encode()).hexdigest(), 16) % len(plain)]


def tapestry_motif_primitive(chart_name: str) -> str | None:
    """The provenance primitive that declares a library motif worked as tapestry."""
    return None if chart_name in TAPESTRY_CHARTS else f"products.motifs:{chart_name}:tapestry"


def _adjust_round(from_count: int, to_count: int) -> list:
    """One round from `from_count` to `to_count` stitches, the increases (or decreases) spread
    evenly round it by cir.shaping.distribute, so the wall takes a chart's whole repeats."""
    from ..cir.shaping import distribute

    if to_count == from_count:
        return [Op("sc", from_count)]
    ops: list = []
    if to_count > from_count:
        marks = distribute(to_count - from_count, from_count)       # incs per stitch
        for m in marks:
            ops.append(Op("inc") if m else Op("sc", 1))
    else:
        pairs = from_count - to_count                                # each dec eats 2 -> 1
        singles = from_count - 2 * pairs
        marks = distribute(pairs, pairs + singles)
        for m in marks:
            ops.append(Op("dec") if m else Op("sc", 1))
    merged: list = []
    for op in ops:
        if merged and merged[-1].stitch == op.stitch == "sc":
            merged[-1] = Op("sc", merged[-1].count + op.count)
        else:
            merged.append(op)
    return merged


def _chart_ops(line: str, contrast: str, repeats: int) -> list:
    runs: list = []
    for cell in line:
        colour = contrast if cell == "X" else None
        if runs and runs[-1][0] == colour:
            runs[-1][1] += 1
        else:
            runs.append([colour, 1])
    return [Repeat([Op("sc", n, color=c) if c else Op("sc", n) for c, n in runs],
                   times=repeats)]


def tapestry_basket(concept, *, version: str = "1.0.0", provenance=None,
                    chart: str | None = None, size: str | None = None) -> CIR:
    """A hexagon-based basket whose wall is a charted two-colour tapestry band.

    `chart` and `size` come from a construction request; without them the title decides."""
    from ..creative.prototype import gauge_for
    from ..products.vessels import (BASKET_SIZES, _disc_rounds, base_stitches_for,
                                    hexagon_spans_cm)

    colours = list(dict.fromkeys(concept.colors))
    if len(colours) < 2 or len({concept.colors[c] for c in colours[:2]}) < 2:
        raise ValueError(f"{concept.slug}: tapestry needs two distinct colours, the concept "
                         f"declares {len(colours)}")
    main, contrast = colours[0], colours[1]
    folded = fold_title(concept.title)
    key = size or next((k for word, k in _TAPESTRY_SIZE_WORDS
                        if re.search(rf"\b{word}\b", folded)), "medium")
    spec = next(s for s in BASKET_SIZES if s.key == key)
    gauge = gauge_for(concept.yarn_weight)
    chart_name = chart or _tapestry_chart(concept.title, concept.slug)
    charts = tapestry_charts()
    if chart_name not in charts:
        raise ValueError(f"{concept.slug}: the {chart_name!r} chart is not a backed tapestry "
                         f"chart")
    chart = charts[chart_name]
    width = len(chart[0])
    wanted = base_stitches_for(spec.across_cm, gauge)
    base_count = max(12, int(round(wanted / 6)) * 6)        # six stacked increases
    wall_count = max(width * 2, int(round(base_count / width)) * width)
    rows = _disc_rounds(base_count, main)
    row_cm = 10.0 / gauge.rows_per_10cm
    wall_rounds = max(TAPESTRY_PLAIN_BELOW + TAPESTRY_PLAIN_RIM + len(chart),
                      int(round(spec.tall_cm / row_cm)))
    band = wall_rounds - TAPESTRY_PLAIN_BELOW - TAPESTRY_PLAIN_RIM
    band -= band % len(chart)                           # whole chart repeats only
    below = (wall_rounds - band - TAPESTRY_PLAIN_RIM)
    index = rows[-1].index
    band_rows: list[int] = []
    if band < len(chart):
        raise ValueError(f"{concept.slug}: the {chart_name!r} chart is {len(chart)} rounds "
                         f"tall and the {key} wall has room for {band}")
    for w in range(wall_rounds):
        index += 1
        if w == 0:
            # The first wall round takes the stitch count to whole chart repeats.
            ops = _adjust_round(base_count, wall_count)
        elif below <= w < below + band:
            line = chart[(w - below) % len(chart)]
            ops = _chart_ops(line, contrast, wall_count // width)
            band_rows.append(index)
        else:
            ops = [Op("sc", wall_count)]
        rows.append(Row(index=index, ops=ops, declared_count=wall_count, color=main))
    points, flats = hexagon_spans_cm(base_count, gauge)
    return CIR(
        slug=concept.slug, title=concept.title, version=version,
        construction="joined_rounds", risk_class=concept.risk_class,
        colors=dict(concept.colors), gauge=gauge,
        materials=[Material(name=f"{concept.yarn_weight} acrylic",
                            yarn_weight=concept.yarn_weight, color_id=c)
                   for c in (main, contrast)],
        components=[Component(
            name="basket", construction="joined_rounds", rows=rows, foundation=0,
            foundation_kind="magic_ring",
            note=(f"Worked in one piece from the centre of the base. Work each increase into "
                  f"the second stitch of the previous round's increase, so the base is a "
                  f"hexagon. Rounds {band_rows[0]}-{band_rows[-1]} are tapestry crochet: "
                  f"lay the colour not in use along the top of the round and work over it, "
                  f"and change colour in the last yarn-over of the stitch before. Tapestry "
                  f"single crochet in rounds leans slightly in the working direction, so the "
                  f"chart's columns spiral a little; that is the fabric, not an error."))],
        designer_notes=(f"{concept.category} concept drafted as a tapestry crochet basket: "
                        f"hexagon base of {base_count} sts, {wall_rounds} wall rounds, of "
                        f"which rounds {band_rows[0]}-{band_rows[-1]} carry the {width}-st "
                        f"{chart_name} chart in {main} and {contrast}"),
        finished_size_note=(
            f"A hexagonal tapestry basket about {points:.1f} cm across the points and "
            f"{flats:.1f} cm across the flats, walls about {wall_rounds * row_cm:.0f} cm tall, "
            f"at the stated gauge. Computed, not yet measured on a worked sample."),
        provenance=provenance,
    )


# ---------------------------------------------------------------------------------------
# Amigurumi: a ball-body animal (P0 construction breadth, owner directive 2026-11-01 3C).
#
# A body, a base and two ears. The body is worked from the top of the head down in single
# crochet in joined rounds: staggered increases to a circle of AMI_BODY_STITCHES (never
# stacked, so it is round, not a hexagon), plain rounds, then staggered decreases to an
# AMI_BASE_STITCHES opening, which a flat base disc of the same count closes after stuffing
# (a stitch-for-stitch join, so the toy sits). Each ear is a small piece
# in rounds, flattened and sewn across a stated number of stitches of a stated body round,
# so `cir.assembly` measures every join. Eyes and nose are embroidered with yarn; the pattern
# makes no toy-safety claim of any kind -- that is the children's-products decision
# (`launch0.childrens_decision`), not a drafting rule. A stuffed closed form is risk class C
# (`gates.risk_matrix`): its finished shape is known only from a full physical make, so the
# size note states the circumference the stitch counts make and refuses a height.
AMI_BODY_STITCHES = 36
AMI_PLAIN_ROUNDS = 7
AMI_BASE_STITCHES = 18            # the open bottom, closed by a flat base disc so it sits
AMI_EAR_ROUND = 5                 # the body round the ears are sewn to (30 sts)
AMI_ANIMALS: dict[str, dict] = {
    # ear: (stitches in the ring, rounds of increase, plain rounds after) and the flat width
    "bear": {"ring": 6, "inc_rounds": 1, "plain": 2, "flat_sts": 6,
             "note": "a round ear: flatten the cup so its opening closes into a straight edge"},
    "bunny": {"ring": 4, "inc_rounds": 1, "plain": 8, "flat_sts": 4,
              "note": "a long ear: flatten the tube so its opening closes into a straight edge"},
}
_AMI_SYNONYMS = {"teddy": "bear", "rabbit": "bunny", "bunny": "bunny", "bear": "bear"}
_AMI_ALLOWED_WORDS = frozenset({"amigurumi", "crochet", "crocheted", "ball", "round",
                                "simple", "classic", "cosy", "cozy", "plush", "teddy"})
AMIGURUMI_PRIMITIVES = ("creative.fallback_constructions.amigurumi",
                        "products.moment_candidates._disc",
                        "products.moment_candidates._decrease_to",
                        "cir.assembly._placed_on_round_cm")


def amigurumi_route(title: str | None) -> dict:
    folded = fold_title(title)
    if re.search(_MULTIPLE_WORDS, folded) or re.search(
            r"\b(?:bears|bunnies|rabbits|teddies|animals|friends)\b", folded):
        return {"family": REFUSED, "needs": "one certified release per toy, each listed alone",
                "why": "the title promises more than one toy; one draft is one toy"}
    words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", folded)
    animals = [w for w in words if w in _AMI_SYNONYMS and w != "teddy"]
    if not animals or words[-1] not in (*_AMI_SYNONYMS, "amigurumi", "plush"):
        return {"family": REFUSED, "needs": NEEDS["amigurumi"] + " (a ball-body bear or bunny "
                                                                "is the one fallback form)",
                "why": (f"the title {title!r} names a shape the fallback does not make; only a "
                        f"plain ball-body {' or '.join(sorted(AMI_ANIMALS))} is drafted")}
    unknown = [w for w in words if w not in _AMI_ALLOWED_WORDS and w not in _AMI_SYNONYMS]
    kinds = {_AMI_SYNONYMS[w] for w in animals}
    if unknown or len(kinds) > 1 or ("teddy" in words and kinds != {"bear"}):
        named = " ".join(unknown) or " and ".join(sorted(kinds))
        return {"family": REFUSED,
                "needs": (f"the shape, feature or size {named!r} names (its own pieces, "
                          f"placements and a physical sample); only a plain ball-body bear or "
                          f"bunny is drafted"),
                "why": f"the title names {named!r}, which the ball-body toy does not make"}
    return {"family": AMIGURUMI, "needs": "", "kind": kinds.pop(),
            "why": "a ball-body toy is shaped rounds, stuffed and closed, with sewn ears"}


def amigurumi(concept, *, version: str = "1.0.0", provenance=None,
              kind: str | None = None) -> CIR:
    """A stuffed ball-body bear or bunny: one body in rounds and two placed ears.

    `kind` comes from a construction request (the brief's motif); without one the radar
    title route decides it."""
    from ..cir.model import Seam
    from ..creative.prototype import gauge_for
    from ..products.moment_candidates import _decrease_to, _disc, _Rows

    if kind is None:
        route = amigurumi_route(concept.title)
        if route["family"] != AMIGURUMI:
            raise ValueError(f"{concept.slug}: {route['why']}")
        kind = route["kind"]
    if kind not in AMI_ANIMALS:
        raise ValueError(f"{concept.slug}: no ball-body shape for {kind!r}")
    ear_spec = AMI_ANIMALS[kind]
    palette = list(dict.fromkeys(concept.colors))
    if not palette:
        raise ValueError(f"{concept.slug}: a toy needs at least one colour")
    main = palette[0]
    gauge = gauge_for(concept.yarn_weight)

    body = _Rows()
    _disc(body, AMI_BODY_STITCHES, main)
    widest = body.last
    for _ in range(AMI_PLAIN_ROUNDS):
        body.add([Op("sc", AMI_BODY_STITCHES)], AMI_BODY_STITCHES, main)
    _decrease_to(body, AMI_BODY_STITCHES, AMI_BASE_STITCHES, main)
    body.rows[0].note = "work tightly, so the stuffing will not show between stitches"
    last = body.last
    base = _Rows()
    _disc(base, AMI_BASE_STITCHES, main)
    ear_round_count = next(r.declared_count for r in body.rows if r.index == AMI_EAR_ROUND)
    flat = ear_spec["flat_sts"]
    gap = flat
    back = ear_round_count - 2 * flat - gap

    ear = _Rows()
    ring = ear_spec["ring"]
    ear.add([Op("sc", ring)], ring, main)
    count = ring
    for _ in range(ear_spec["inc_rounds"]):
        body_ops = [Op("sc", 1), Op("inc")] if count // ring == 2 else [Op("inc")]
        count += ring
        ear.add([Repeat(body_ops, times=ring)], count, main)
    for _ in range(ear_spec["plain"]):
        ear.add([Op("sc", count)], count, main)
    if count != 2 * flat:
        raise ValueError(f"{kind} ear: {count} sts does not flatten to {flat} across")

    components = [
        Component(name="body", construction="joined_rounds", rows=body.rows, foundation=0,
                  foundation_kind="magic_ring",
                  note="Worked from the top of the head down, open at the bottom."),
        Component(name="base", construction="joined_rounds", rows=base.rows, foundation=0,
                  foundation_kind="magic_ring",
                  note="A flat disc that closes the bottom, so the toy sits up."),
        Component(name="ear", construction="joined_rounds", rows=ear.rows, foundation=0,
                  foundation_kind="magic_ring", make=2,
                  note=f"Make 2. Unstuffed: {ear_spec['note']}."),
    ]
    embroidery = ("Embroider the eyes and nose with a scrap of dark yarn on rounds "
                  f"{widest + 2}-{widest + 4}, centred under the gap between the ears.")
    assembly = [
        Seam("whipstitch", "base", "body", edge_a="top", edge_b="bottom",
             stuff_before_closing=True, at_round=last, spans_rounds=1,
             note=(f"Stuff the body firmly with fibrefill, then whipstitch the base's last "
                   f"round to the body's last round stitch for stitch ({AMI_BASE_STITCHES} "
                   f"sts each), topping up the stuffing before the last few stitches")),
        Seam("whipstitch", "ear", "body", edge_a="top", edge_b="top",
             at_round=AMI_EAR_ROUND, spans_rounds=1, stitches_from_centre=flat // 2,
             note=(f"Sew each flattened ear across {flat} sts of round {AMI_EAR_ROUND} "
                   f"({ear_round_count} sts): ear {flat} sts, {gap} sts between the ears at "
                   f"the front, ear {flat} sts, then {back} sts at the back. "
                   + embroidery)),
    ]
    around = AMI_BODY_STITCHES / gauge.stitches_per_10cm * 10.0
    return CIR(
        slug=concept.slug, title=concept.title, version=version,
        construction="joined_rounds", risk_class="C",
        colors=dict(concept.colors), gauge=gauge,
        materials=[Material(name=f"{concept.yarn_weight} acrylic",
                            yarn_weight=concept.yarn_weight, color_id=main),
                   Material(name="polyester fibrefill"),
                   Material(name="dark yarn scrap for the embroidered eyes and nose")],
        components=components, assembly=assembly,
        designer_notes=(f"{concept.category} concept drafted as a ball-body {kind}: a "
                        f"{AMI_BODY_STITCHES}-st body in rounds, stuffed and closed by a "
                        f"{AMI_BASE_STITCHES}-st base, two "
                        f"{kind} ears sewn to round {AMI_EAR_ROUND}. {embroidery}"),
        finished_size_note=(
            f"The body is about {around:.0f} cm around its widest round at the stated gauge. "
            f"Computed from the stitch counts, not yet measured on a worked sample; its "
            f"height depends on the stuffing and is measured on the sample."),
        provenance=provenance,
    )


# ---------------------------------------------------------------------------------------
# A drawstring pouch (P0 construction breadth: bags and accessories).
#
# A round base (staggered increases, so a circle), straight walls in sc joined rounds, one
# eyelet round of "sc, ch 2, sk 2" a few rounds below the rim, and a chain cord with a slip
# stitch in each chain, threaded in and out of the eyelets. `cir.assembly` measures the
# thread join: the cord's girth against one eyelet's inside (THREAD_ROOM), so a cord that
# cannot pass is a mismatch, not a photograph. One design size, computed from the gauge.
POUCH_CATEGORIES = frozenset({"bag", "accessory", "accessories"})
POUCH_ACROSS_CM = 12.0
POUCH_TALL_CM = 15.0
POUCH_EYELET_REPEAT = (4, 2)       # sc, then a ch-2 bridging 2 skipped sts
POUCH_RIM_ROUNDS = 2               # plain rounds above the eyelet round
POUCH_TIE_CM = 20.0                # free cord at each end, for the bow
_POUCH_HEAD = r"\b(?:pouch|bag)$"
_POUCH_ALLOWED_WORDS = frozenset({"drawstring", "crochet", "crocheted", "simple", "classic",
                                  "everyday", "round", "project", "gift", "cosy", "cozy"})
POUCH_PRIMITIVES = ("creative.fallback_constructions.pouch",
                    "products.moment_candidates._disc", "cir.assembly._thread_join")


def pouch_route(title: str | None) -> dict:
    folded = fold_title(title)
    if re.search(_MULTIPLE_WORDS, folded) or re.search(r"\b(?:pouches)\b", folded):
        return {"family": REFUSED, "needs": "one certified release per pouch, each listed alone",
                "why": "the title promises more than one pouch; one draft is one pouch"}
    head = re.search(_POUCH_HEAD, folded)
    if not head:
        return {"family": REFUSED, "needs": NEEDS["bag"],
                "why": (f"the title {title!r} names a drawstring form other than a plain "
                        f"pouch; only a drawstring pouch or bag is drafted")}
    before = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", folded[:head.start()])
    unknown = [w for w in before if w not in _POUCH_ALLOWED_WORDS]
    if unknown:
        return {"family": REFUSED,
                "needs": (f"the construction, size or feature {' '.join(unknown)!r} names; "
                          f"only a plain drawstring pouch is drafted"),
                "why": f"the title names {' '.join(unknown)!r}, which the plain pouch does not make"}
    return {"family": POUCH, "needs": "",
            "why": "a drawstring pouch is a round vessel with an eyelet round and a cord"}


def pouch(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    from ..cir.model import Seam
    from ..creative.prototype import gauge_for
    from ..products.moment_candidates import _disc, _Rows

    palette = list(dict.fromkeys(concept.colors))
    if not palette:
        raise ValueError(f"{concept.slug}: a pouch needs at least one colour")
    main = palette[0]
    cord_colour = palette[1] if len(palette) > 1 else main
    gauge = gauge_for(concept.yarn_weight)
    sc_n, gap = POUCH_EYELET_REPEAT
    unit = sc_n + gap
    step = 6 * unit // math.gcd(6, unit)
    around = math.pi * POUCH_ACROSS_CM * gauge.stitches_per_10cm / 10.0
    n = max(step * 2, int(round(around / step)) * step)
    rows = _Rows()
    _disc(rows, n, main)
    base_end = rows.last
    row_cm = 10.0 / gauge.rows_per_10cm
    walls = max(POUCH_RIM_ROUNDS + 4, int(round(POUCH_TALL_CM / row_cm)))
    for _ in range(walls - POUCH_RIM_ROUNDS - 1):
        rows.add([Op("sc", n)], n, main)
    eyelets = n // unit
    rows.add([Repeat([Op("sc", sc_n), Op("ch", gap, spans=gap), Op("sk", gap)],
                     times=eyelets)], n, main,
             note=f"{eyelets} eyelets; work the next round's sts into each ch-{gap} space")
    eyelet_round = rows.last
    for _ in range(POUCH_RIM_ROUNDS):
        rows.add([Op("sc", n)], n, main)
    circumference = n / gauge.stitches_per_10cm * 10.0
    cord_cm = circumference + 2 * POUCH_TIE_CM
    cord_n = int(round(cord_cm * gauge.stitches_per_10cm / 10.0))
    cord = Component(name="cord", construction="flat_rows", foundation=cord_n,
                     foundation_kind="chain",
                     rows=[Row(index=1, ops=[Op("slst", cord_n)], declared_count=cord_n,
                               color=cord_colour, turning_chain=1)],
                     note=f"A chain of {cord_n} with a slip stitch in each: the cord.")
    body = Component(name="pouch", construction="joined_rounds", rows=rows.rows, foundation=0,
                     foundation_kind="magic_ring",
                     note=(f"Rounds 1-{base_end} are the base; the walls rise straight from "
                           f"round {base_end + 1}."))
    return CIR(
        slug=concept.slug, title=concept.title, version=version,
        construction="joined_rounds", risk_class=concept.risk_class,
        colors=dict(concept.colors), gauge=gauge,
        materials=[Material(name=f"{concept.yarn_weight} acrylic",
                            yarn_weight=concept.yarn_weight, color_id=c)
                   for c in dict.fromkeys([main, cord_colour])],
        components=[body, cord],
        assembly=[Seam("thread", "cord", "pouch", edge_a="left", edge_b="opening",
                       at_round=eyelet_round, spans_rounds=1,
                       note=(f"Weave the cord in and out of the {eyelets} eyelets of round "
                             f"{eyelet_round}, starting and ending at the same eyelet, and "
                             f"knot each end; pull both ends to close the pouch."))],
        designer_notes=(f"{concept.category} concept drafted as a drawstring pouch: a {n}-st "
                        f"round base, {walls} wall rounds with {eyelets} eyelets in round "
                        f"{eyelet_round}, and a {cord_n}-ch cord"),
        finished_size_note=(
            f"A round pouch about {n / gauge.stitches_per_10cm * 10.0 / math.pi:.0f} cm across "
            f"and {walls * row_cm:.0f} cm tall at the stated gauge, with a cord about "
            f"{cord_cm:.0f} cm long. Computed, not yet measured on a worked sample."),
        provenance=provenance,
    )
