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
STOCKING = "stocking"
REFUSED = "refused"

VESSEL_CATEGORIES = frozenset({"basket"})

# Category -> the construction it would need. None of these is a flat panel.
NEEDS: dict[str, str] = {
    "amigurumi": "shaped pieces worked in the round, stuffed and joined",
    "hat": ("a hat height and negative ease from a published standard: the CYC head "
            "circumference chart (HEAD_CIRCUMFERENCE_CM) publishes circumference only"),
    "garment": "a graded garment design (creative.garment_design)",
    # A stocking whose title the plain two-panel rule cannot back (colourwork, a name, a
    # second object, another size) is refused in `plan` with its own reason.
    "stocking": "a stocking construction the two-panel rule does not make",
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
    titled_tote = bool(re.search(_TOTE_WORDS, (title or "").lower()))
    if category in NEEDS and not (category == "bag" and titled_tote) and category != "stocking":
        return {"family": REFUSED, "needs": NEEDS[category],
                "why": (f"category {category!r} needs {NEEDS[category]}; the fallback drafts "
                        f"flat panels and baskets only")}
    if category in VESSEL_CATEGORIES:
        return {"family": VESSEL, "needs": "", "why": "a basket is worked in the round"}
    if category in PET_CATEGORIES and re.search(_PET_BED_WORDS, (title or "").lower()):
        lowered_p = (title or "").lower()
        shaped = re.search(_PET_BED_NOT_PLAIN, lowered_p)
        if shaped:
            return {"family": REFUSED,
                    "needs": (f"the construction a {shaped.group(0).strip()!r} bed needs (a "
                              f"stuffed bolster, a padded base, a hood or a larger measured "
                              f"size), worked and joined as its own pieces"),
                    "why": (f"the title names {shaped.group(0).strip()!r}, which the plain "
                            f"low-walled basket bed does not make")}
        return {"family": VESSEL, "needs": "",
                "why": "a pet basket bed is a wide vessel with a low wall, worked in the round"}
    lowered_s = (title or "").lower().strip()
    stocking_head = re.search(_STOCKING_HEAD, lowered_s)
    if category == "stocking" and not stocking_head:
        # OPUS2J J-13: the category alone never makes a stocking out of another product.
        return {"family": REFUSED,
                "needs": "a stocking title, or the construction the title names",
                "why": (f"category 'stocking' but the title {title!r} names another product; "
                        f"the stocking rule drafts only a stocking")}
    if stocking_head:
        rest = re.sub(_STOCKING_WORDS, "", lowered_s)
        # OPUS2J J-14: one release is one stocking; a motif word the plain stocking does not
        # carry is refused (the fallback declares no motif, so name_truth cannot back it).
        if re.search(r"\bstockings\b", lowered_s):
            return {"family": REFUSED,
                    "needs": "one certified release per finished stocking, each listed on its own",
                    "why": "the title promises more than one stocking; one draft is one stocking"}
        from ..products.launch0 import MOTIF_WORDS

        motif = next((w for w in re.findall(r"[a-z]+", rest) if w in MOTIF_WORDS), None)
        if motif:
            return {"family": REFUSED,
                    "needs": f"a charted {motif!r} motif on the stocking (a declared motif)",
                    "why": (f"the title names the motif {motif!r}, which the plain stocking "
                            f"does not carry")}
        extra = re.search(_STOCKING_NOT_PLAIN, rest)
        if extra:
            return {"family": REFUSED,
                    "needs": (f"the construction a {extra.group(0).strip()!r} stocking needs "
                              f"(per-stitch colourwork, lettering, a second object, a cuff in "
                              f"another stitch or another size)"),
                    "why": (f"the title names {extra.group(0).strip()!r}, which the plain "
                            f"two-panel stocking does not make")}
        if re.search(_MULTIPLE_WORDS, lowered_s):
            return {"family": REFUSED,
                    "needs": "one certified release per finished stocking, each listed on its own",
                    "why": "the title promises more than one stocking; one draft is one stocking"}
        return {"family": STOCKING, "needs": "",
                "why": "a stocking is two L-shaped panels worked flat and seamed around"}
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


# A stocking: two identical L-shaped panels worked flat from the cuff down, held wrong sides
# together and whipstitched around the leg, heel, sole and toe, open at the cuff, with a
# chain hanging loop sewn inside the heel-side top corner. The foot extends by a chain at the
# end of the heel row (the compiler counts a chain into open air as new fabric), and the sole
# rounds off by a decrease at each end of the last rows. One design size; the listing states
# the computed dimensions, never a measured one.
_STOCKING_WORDS = r"\bstockings?\b"
# OPUS2J J-13: "stocking" must be the head noun (the title's last word), so "Stocking Stitch
# Blanket", "Stocking Garland", "Stocking Holder", "Stocking Cap" and "Stocking Tote" are never
# drafted as a stocking.
_STOCKING_HEAD = r"\bstockings?$"
_STOCKING_NOT_PLAIN = (r"(?:[&+]|\b(?:and|with|mosaic|fair[- ]?isle|tapestry|colou?rwork|"
                       r"intarsia|graphghan|personali[sz]ed|monogram(?:med)?|name|initials?|"
                       r"cable[sd]?|bobble[sd]?|lace|lacy|pom[- ]?poms?|fur|faux|cuffed|"
                       r"appliqu[eé]|mini|tiny|small|medium|large|giant|jumbo|xl|oversized?)\b)")
STOCKING_PRIMITIVES = ("creative.fallback_constructions.stocking",)
STOCKING_LEG_W_CM = 14.0
STOCKING_LEG_L_CM = 26.0
STOCKING_FOOT_L_CM = 22.0
STOCKING_FOOT_H_CM = 10.0
STOCKING_SOLE_ROWS = 4
STOCKING_LOOP_CHAINS = 15


def stocking(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A Christmas stocking: two L-shaped panels from the cuff down, seamed, with a loop."""
    import dataclasses

    from ..cir.model import Seam
    from ..creative.prototype import gauge_for

    gauge = gauge_for(concept.yarn_weight)
    palette = list(concept.colors)
    if not palette:
        raise ValueError(f"{concept.slug}: a stocking needs at least one colour")
    per_cm = gauge.stitches_per_10cm / 10.0
    rows_per_cm = gauge.rows_per_10cm / 10.0
    leg_w = max(10, int(round(STOCKING_LEG_W_CM * per_cm)))
    foot_w = max(leg_w + 6, int(round(STOCKING_FOOT_L_CM * per_cm)))
    extend = foot_w - leg_w
    leg_rows = max(10, int(round(STOCKING_LEG_L_CM * rows_per_cm)))
    if leg_rows % 2:
        leg_rows += 1                     # the heel chain ends an even row (the heel edge)
    foot_rows = max(STOCKING_SOLE_ROWS + 4, int(round(STOCKING_FOOT_H_CM * rows_per_cm)))
    main, accent = palette[0], palette[1 % len(palette)]
    rows: list[Row] = []
    index = 0

    def colour_for(i: int) -> str:
        return accent if i <= 4 else main          # a four-row cuff band, then the body

    for i in range(1, leg_rows + 1):
        index += 1
        if i == leg_rows:
            rows.append(Row(index=index, ops=[Op("sc", leg_w), Op("ch", extend)],
                            declared_count=foot_w, turning_chain=1, color=colour_for(i),
                            note="chain across for the foot"))
        else:
            rows.append(Row(index=index, ops=[Op("sc", leg_w)], declared_count=leg_w,
                            turning_chain=1, color=colour_for(i)))
    count = foot_w
    plain_foot = foot_rows - STOCKING_SOLE_ROWS
    for j in range(1, foot_rows + 1):
        index += 1
        if j == 1:
            rows.append(Row(index=index, ops=[Op("sc", extend), Op("sc", leg_w)],
                            declared_count=count, turning_chain=1, color=main,
                            note="work into each chain, then across the leg"))
        elif j <= plain_foot:
            rows.append(Row(index=index, ops=[Op("sc", count)], declared_count=count,
                            turning_chain=1, color=main))
        else:
            rows.append(Row(index=index, ops=[Op("dec"), Op("sc", count - 4), Op("dec")],
                            declared_count=count - 2, turning_chain=1, color=main,
                            note="round the heel and toe"))
            count -= 2
    panel = Component(
        name="front", construction="flat_rows", rows=rows, foundation=leg_w,
        foundation_kind="chain",
        note=("Worked flat from the cuff down. The last leg row chains across for the foot; "
              "the last rows decrease at both ends to round the heel and toe."))
    back = dataclasses.replace(panel, name="back")
    loop = Component(
        name="hanging loop", construction="flat_rows", foundation=STOCKING_LOOP_CHAINS,
        foundation_kind="chain",
        rows=[Row(index=1, ops=[Op("sc", STOCKING_LOOP_CHAINS)],
                  declared_count=STOCKING_LOOP_CHAINS, color=accent)],
        note="A short strip folded in half into a loop.")
    assembly = [
        Seam("whipstitch", "front", "back", edge_a="perimeter", edge_b="perimeter",
             at_round=1, spans_rounds=len(rows),
             note=("Place the back on the front with the same side facing up, so the feet point "
                   "the same way and the edges match, and whipstitch around the leg, heel, "
                   "sole and toe, leaving the cuff (the foundation edges) open.")),
        Seam("whipstitch", "hanging loop", "back", edge_a="bottom", edge_b="top",
             at_round=1, spans_rounds=1,
             note="Fold the loop in half and sew both ends inside the heel-side top corner."),
    ]
    width_cm = foot_w / per_cm
    leg_cm = leg_rows / rows_per_cm
    foot_cm = foot_rows / rows_per_cm
    return CIR(
        slug=concept.slug, title=concept.title, version=version, construction="flat_rows",
        risk_class=concept.risk_class, colors=dict(concept.colors), gauge=gauge,
        materials=[Material(name=f"{concept.yarn_weight} acrylic",
                            yarn_weight=concept.yarn_weight, color_id=p)
                   for p in dict.fromkeys([main, accent])],
        components=[panel, back, loop], assembly=assembly,
        designer_notes=(f"{concept.category} concept drafted as a two-panel stocking: a "
                        f"{leg_w}-st leg of {leg_rows} rows with a four-row cuff band, a "
                        f"{extend}-ch heel extension to a {foot_w}-st foot of {foot_rows} rows, "
                        f"the last {STOCKING_SOLE_ROWS} rounding the sole"),
        finished_size_note=(
            f"A stocking about {leg_w / per_cm:.0f} cm wide at the cuff, "
            f"{leg_cm + foot_cm:.0f} cm from cuff to sole and {width_cm:.0f} cm from heel to "
            f"toe, at the stated gauge. Computed, not yet measured on a worked sample."),
        provenance=provenance,
    )


# A basket's finished size, chosen from its title, never from the panel width table: the
# panel width is a flat dimension and a basket's is a diameter.
_SIZE_WORDS = (("bread", "small"), ("market", "large"))


# OPUS2: a pet basket bed is the same hexagon vessel, wide and low: one design size, stated in
# the listing as the compiled diameter (never a pet's size). Padded, bolstered, hooded or
# large-dog beds are a different construction and are refused by name in `plan`.
PET_CATEGORIES = frozenset({"pet"})
_PET_BED_WORDS = r"\b(?:bed|beds|basket|nest)\b"
_PET_BED_NOT_PLAIN = (r"(?:[&+]|\b(?:and|with|bolster(?:ed)?|cushion(?:ed)?|pillow|padded|"
                      r"stuffed|donut|doughnut|cave|igloo|hood(?:ed)?|tent|cuddler|large|"
                      r"giant|xl|xxl|extra[- ]large|big)\b)")


def _pet_bed_size():
    from ..products.vessels import BasketSize

    return BasketSize("pet_bed", "pet basket bed", across_cm=45.0, tall_cm=10.0)


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
    pet_bed = size == "pet_bed" or (size is None and concept.category in PET_CATEGORIES)
    spec = (_pet_bed_size() if pet_bed
            else next(s for s in BASKET_SIZES if s.key == size) if size
            else _basket_size(concept.title))
    thing = "pet basket bed" if pet_bed else "basket"
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
            name="bed" if pet_bed else "basket", construction="joined_rounds", rows=rows,
            foundation=0,
            foundation_kind="magic_ring",
            note=("Worked in one piece from the centre of the base. Work each increase into "
                  "the second stitch of the previous round's increase, so the increases stack "
                  "into six corners and the base is a hexagon."))],
        designer_notes=(f"{concept.category} concept drafted as a vessel: hexagon base of "
                        f"{base_count} sts, {wall_rounds} wall rounds alternating plain "
                        f"single crochet and the concept's {unit}-st repeat"),
        finished_size_note=(
            f"A hexagonal {thing} about {points:.1f} cm across the points and {flats:.1f} cm "
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
