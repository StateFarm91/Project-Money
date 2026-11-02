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

def fold_title(title: str | None) -> str:
    """A title as the routing rules read it (review OPUS2L-4): NFKC (fullwidth letters,
    compatibility forms), every Unicode dash (category Pd: U+2010..U+2015, U+2212 and the
    like) as an ASCII hyphen, lower case, whitespace collapsed and stripped. A smart-copy
    "Fair\u2011Isle" is the same claim as "Fair-Isle"."""
    import unicodedata

    text = unicodedata.normalize("NFKC", title or "").replace("\u2019", "'")
    text = "".join("-" if (unicodedata.category(c) == "Pd" or c == "\u2212") else c
                   for c in text)
    return re.sub(r"\s+", " ", text.lower()).strip()


def words_before_head(folded: str, head_re: str) -> list[str] | None:
    """The modifier words before a title's head noun, or None when the head noun is not the
    title's last word. The shared construction-intent rule (reviews OPUS2K-7, OPUS2L-1): a
    route that drafts one plain object drafts it only when every modifier is in that route's
    allowlist, so another product, a size, an audience, a motif, an embellishment or a claim
    is refused whatever it is called -- never matched against a denylist that cannot be
    complete."""
    head = re.search(head_re, folded)
    if not head:
        return None
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", folded[:head.start()])


def modifiers_outside(folded: str, head_re: str, allowed: frozenset) -> list[str]:
    """The modifiers before the head noun that the route's allowlist does not hold.

    Review OPUS2N-1: total, not token-wise. Anything before the head noun that is not an
    ASCII word -- an emoji, a word in another script, a symbol -- yields no token, so it is
    returned as what is left over, never passed as "no unknown word"."""
    head = re.search(head_re, folded)
    if not head:
        return []
    prefix = folded[:head.start()]
    unknown = [w for w in (words_before_head(folded, head_re) or []) if w not in allowed]
    leftover = re.sub(r"[a-z0-9'\s\-]", "", prefix)
    if leftover:
        unknown.append(leftover)
    return unknown


FLAT_PANEL = "flat_panel"
VESSEL = "vessel"
PANEL_PAIR = "panel_pair"
TOTE = "tote"
COSY = "cosy"
TRIANGLE = "triangle"
STOCKING = "stocking"
TAPESTRY = "tapestry"
POUCH = "pouch"
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
    if category in POUCH_CATEGORIES and re.search(r"\bdrawstring\b", fold_title(title)):
        # P0 construction breadth (bags and accessories): a plain drawstring pouch is a small
        # round vessel with an eyelet round and a threaded chain cord.
        return pouch_route(title)
    titled_tote = bool(re.search(_TOTE_WORDS, (title or "").lower()))
    if category in NEEDS and not (category == "bag" and titled_tote) and category != "stocking":
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
    if category in PET_CATEGORIES and re.search(_PET_BED_HEAD, fold_title(title)):
        lowered_p = fold_title(title)       # OPUS2L-4: Unicode dashes and forms folded
        # OPUS2J J-12: one release is one bed.
        if re.search(_MULTIPLE_WORDS, lowered_p) or re.search(r"\b(?:beds|baskets|nests)\b",
                                                                lowered_p):
            return {"family": REFUSED,
                    "needs": "one certified release per finished bed, each listed on its own",
                    "why": "the title promises more than one bed; one draft is one bed"}
        # OPUS2J J-10: the one sourced size is a cat's (products.vessels.PET_BED_SIZE).
        other = re.search(_PET_BED_OTHER_ANIMALS, lowered_p)
        if other:
            return {"family": REFUSED,
                    "needs": (f"a sourced bed size for {other.group(0)!r}: only an adult cat's "
                              f"is sourced (products.vessels.PET_BED_SIZE_SOURCE)"),
                    "why": f"the title names {other.group(0)!r}, which the cat-sized bed does not fit"}
        sized = re.search(_PET_BED_SIZE_WORDS, lowered_p)
        if sized:
            return {"family": REFUSED,
                    "needs": "a second sourced bed size; the fallback has one",
                    "why": f"the title names a size ({sized.group(0)!r}) the one design size is not"}
        # OPUS2K K-7 (the second half of J-9): an allowlist, not a denylist. Every word before
        # the head noun must be a plain cat/pet word, so another animal, a size, a feature or a
        # different object is refused whatever it is called.
        # The shared construction-intent rule (fold_title / modifiers_outside).
        unknown = modifiers_outside(lowered_p, _PET_BED_HEAD, _PET_BED_ALLOWED_WORDS)
        if unknown:
            return {"family": REFUSED,
                    "needs": (f"the construction or sourced size {' '.join(unknown)!r} names; "
                              f"only a plain cat or pet basket bed is drafted"),
                    "why": (f"the title names {' '.join(unknown)!r}, which the plain cat-sized "
                            f"basket bed does not make")}
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
    lowered_s = fold_title(title)
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
        # Review OPUS2L-1/-2/-3/-5: an allowlist, not a denylist. Every word before "stocking"
        # must be a plain Christmas-stocking word; another product ("Wine Bottle Stocking"),
        # hosiery or a medical claim ("Compression Stocking"), a size or audience ("Baby
        # Stocking"), a motif, an embellishment or a count is refused whatever it is called.
        # The one contrast band the stocking does make is the four-row cuff (accent colour),
        # so "Contrast Cuff" names it truly. OPUS2Q-5: it is one solid band, so "Stripe(d)
        # Cuff" is not admitted (it names stripes the cuff does not have).
        banded = re.sub(r"\b(?:contrast|contrasting) cuff\b", "cuff", lowered_s)
        unknown = modifiers_outside(banded, _STOCKING_HEAD, _STOCKING_ALLOWED_WORDS)
        if unknown:
            return {"family": REFUSED,
                    "needs": (f"the construction, size or sourced claim {' '.join(unknown)!r} "
                              f"names; only a plain Christmas stocking is drafted"),
                    "why": (f"the title names {' '.join(unknown)!r}, which the one plain "
                            f"two-panel stocking does not make")}
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
# Review OPUS2L-1: the only words a plain stocking title may carry before "stocking". Style
# and occasion words only; no size, audience, colour pattern, motif, material or count.
CUFF_MIN_DELTA_E = 10.0           # OPUS2Q-4: CIE76; below it two colours read as one


def _lab(hex_colour: str) -> tuple[float, float, float]:
    """sRGB hex to CIE L*a*b* (D65)."""
    h = hex_colour.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    x = (0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]) / 0.95047
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    z = (0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]) / 1.08883
    f = [v ** (1 / 3) if v > 0.008856 else 7.787 * v + 16 / 116 for v in (x, y, z)]
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


def delta_e(a: str, b: str) -> float:
    """CIE76 colour difference between two hex colours."""
    la, lb = _lab(a), _lab(b)
    return sum((p - q) ** 2 for p, q in zip(la, lb)) ** 0.5


_STOCKING_ALLOWED_WORDS = frozenset({
    "christmas", "xmas", "holiday", "festive", "classic", "traditional", "fireside", "cosy",
    "cozy", "plain", "simple", "crochet", "crocheted", "everyday", "hanging", "modern",
    # OPUS2O-6: no "solid": a two-colour stocking always has a contrast cuff.
    "minimalist", "seasonal", "winter", "cuff",
})
_STOCKING_NOT_PLAIN = (r"(?:[&+]|\b(?:and|with|mosaic|fair[- ]?isle|tapestry|colou?rwork|"
                       r"intarsia|graphghan|personali[sz]ed|monogram(?:med)?|name|initials?|"
                       r"cable[sd]?|bobble[sd]?|lace|lacy|pom[- ]?poms?|fur|faux|cuffed|"
                       r"appliqu[eé]|mini|tiny|small|medium|large|giant|jumbo|xl|oversized?)\b)")
STOCKING_PRIMITIVES = ("creative.fallback_constructions.stocking",)
# Review OPUS2L-7 / OPUS2O-9: the size is a stated design choice, not a sourced standard. No
# published standard stocking size was found (2026-11-02), and the retail listing once cited
# for scale no longer resolves, so no figure is quoted. The listing states the computed size,
# never a measured or standard one.
STOCKING_SIZE_SOURCE = "design choice; no published standard stocking size found"
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
    # OPUS2O-6 / OPUS2Q-4: a "Contrast Cuff" title is true only when the cuff is a second
    # colour a buyer can see: at least CUFF_MIN_DELTA_E apart (which also reads one hex in two
    # cases, or under two names, as one colour).
    if re.search(r"\b(?:contrast|contrasting) cuff\b", fold_title(concept.title)):
        hexes = [str(concept.colors[c]) for c in palette[:2]]
        if len(hexes) < 2 or delta_e(hexes[0], hexes[1]) < CUFF_MIN_DELTA_E:
            raise ValueError(f"{concept.slug}: the title promises a contrast cuff and the "
                             f"palette's first two colours are not visibly different, so the "
                             f"cuff would read as the body colour")
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
                   "sole and toe, leaving the cuff (the foundation edges) open. Because both "
                   "panels face the same way, the back panel's wrong side shows on the "
                   "outside; in single crochet worked in turned rows the two sides look "
                   "nearly alike.")),
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
# OPUS2J J-9: the bed word must be the head noun (the title's last word), so a "Pet Bed Liner"
# or a "Basket Weave Pet Mat" is never drafted as a basket; and the other objects and features
# a bed title can name are refused by name.
_PET_BED_HEAD = r"\b(?:bed|beds|basket|baskets|nest|nests)$"
_PET_BED_NOT_PLAIN = (r"(?:[&+]|\b(?:and|with|bolster(?:ed)?|cushion(?:ed)?|pillow|padded|"
                      r"stuffed|donut|doughnut|cave|igloo|hood(?:ed)?|tent|cuddler|liner|"
                      r"blanket|mat|cover|pad|topper|hammock|toy|heated|waterproof|"
                      r"orthop(?:a)?edic|window|raised|weave|woven|elevated|bunk|canopy)\b)")
_PET_BED_ALLOWED_WORDS = frozenset({
    # OPUS2N-2: no "round": the bed is a hexagon (its size note says so).
    "cat", "cats", "kitten", "kitty", "pet", "cosy", "cozy", "snug", "basket",
    "crochet", "crocheted", "simple", "classic", "everyday", "soft", "nest", "cat's",
})
_PET_BED_OTHER_ANIMALS = (r"\b(?:dog|dogs|puppy|puppies|pup|hound|great dane|labrador|"
                          r"hamster|rabbit|bunny|guinea pig|ferret|bird|parrot|rat|mouse|"
                          r"chinchilla|hedgehog|reptile|tortoise)\b")
_PET_BED_SIZE_WORDS = (r"\b(?:tiny|mini|small|medium|large|giant|big|xl|xxl|extra[- ]large|"
                       r"jumbo|oversized?|petite)\b")


PET_BED_SOURCE_NOTE = "published cat-bed sizing guidance (an adult cat, about 40-50 cm inside)"


def _pet_bed_size():
    from ..products.vessels import PET_BED_SIZE

    return PET_BED_SIZE


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
            f"gauge. Computed, not yet measured on a worked sample."
            + (f" Sized to {PET_BED_SOURCE_NOTE}." if pet_bed else "")),
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

TAPESTRY_CHARTS: dict[str, tuple[str, ...]] = {
    # "X" is the contrast colour, "." the main; read right to left like every round.
    "diamond": ("..XX..", ".XXXX.", "XX..XX", "XX..XX", ".XXXX.", "..XX.."),
    "check": ("XXX...", "XXX...", "XXX...", "...XXX", "...XXX", "...XXX"),
}
TAPESTRY_DEFAULT_CHART = "diamond"
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
    # OPUS2N-2: no "round": the base is a hexagon, as the size note says.
    "hexagon", "hexagonal", "geometric", "modern", "classic", "simple", "everyday",
    "cosy", "cozy", "small", "medium", "large", "catch-all", "catchall", "shelf",
    *[w for w, chart in _TAPESTRY_CHART_WORDS.items() if chart],
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
    prefix = folded[:head.start()]
    before = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", prefix)
    unknown = [w for w in before if w not in _TAPESTRY_ALLOWED_WORDS]
    # OPUS2N-1: the allowlist is total. An emoji, a word in another script or a symbol yields
    # no ASCII token; it is refused by what is left over, never passed as "nothing unknown".
    leftover = re.sub(r"[a-z0-9\s\-]", "", prefix)
    if leftover:
        unknown.append(leftover)
    if unknown:
        return {"family": REFUSED,
                "needs": (f"the motif, size or construction {' '.join(unknown)!r} names; only "
                          f"a charted two-colour tapestry basket "
                          f"({', '.join(sorted(TAPESTRY_CHARTS))}) is drafted"),
                "why": (f"the title names {' '.join(unknown)!r}, which the tapestry basket "
                        f"charts do not make")}
    # OPUS2N-4: one chart and one size per release; a second is never silently dropped.
    charts = {_TAPESTRY_CHART_WORDS[w] for w in before if _TAPESTRY_CHART_WORDS.get(w)}
    sizes = {k for w, k in _TAPESTRY_SIZE_WORDS if w in before}
    if len(charts) > 1 or len(sizes) > 1:
        named = sorted(charts) if len(charts) > 1 else sorted(sizes)
        return {"family": REFUSED,
                "needs": "one certified release per chart and per size, each listed on its own",
                "why": (f"the title names {' and '.join(named)}; one tapestry basket carries "
                        f"one chart at one size")}
    return {"family": TAPESTRY, "needs": "",
            "why": "a tapestry basket is single crochet in joined rounds, two colours carried"}


def _tapestry_chart(title: str) -> str:
    words = re.findall(r"[a-z]+", fold_title(title))
    chosen = [_TAPESTRY_CHART_WORDS[w] for w in words if _TAPESTRY_CHART_WORDS.get(w)]
    return chosen[0] if chosen else TAPESTRY_DEFAULT_CHART


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


def tapestry_basket(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A hexagon-based basket whose wall is a charted two-colour tapestry band."""
    from ..creative.prototype import gauge_for
    from ..products.vessels import (BASKET_SIZES, _disc_rounds, base_stitches_for,
                                    hexagon_spans_cm)

    colours = list(dict.fromkeys(concept.colors))
    if len(colours) < 2 or len({concept.colors[c] for c in colours[:2]}) < 2:
        raise ValueError(f"{concept.slug}: tapestry needs two distinct colours, the concept "
                         f"declares {len(colours)}")
    main, contrast = colours[0], colours[1]
    folded = fold_title(concept.title)
    key = next((k for word, k in _TAPESTRY_SIZE_WORDS if re.search(rf"\b{word}\b", folded)),
               "medium")
    spec = next(s for s in BASKET_SIZES if s.key == key)
    gauge = gauge_for(concept.yarn_weight)
    chart_name = _tapestry_chart(concept.title)
    chart = TAPESTRY_CHARTS[chart_name]
    width = len(chart[0])
    wanted = base_stitches_for(spec.across_cm, gauge)
    base_count = max(width * 4, int(round(wanted / width)) * width)
    base_count -= base_count % 6                        # six stacked increases
    rows = _disc_rounds(base_count, main)
    row_cm = 10.0 / gauge.rows_per_10cm
    wall_rounds = max(TAPESTRY_PLAIN_BELOW + TAPESTRY_PLAIN_RIM + len(chart),
                      int(round(spec.tall_cm / row_cm)))
    band = wall_rounds - TAPESTRY_PLAIN_BELOW - TAPESTRY_PLAIN_RIM
    band -= band % len(chart)                           # whole chart repeats only
    below = (wall_rounds - band - TAPESTRY_PLAIN_RIM)
    index = rows[-1].index
    band_rows: list[int] = []
    for w in range(wall_rounds):
        index += 1
        if below <= w < below + band:
            line = chart[(w - below) % len(chart)]
            ops = _chart_ops(line, contrast, base_count // width)
            band_rows.append(index)
        else:
            ops = [Op("sc", base_count)]
        rows.append(Row(index=index, ops=ops, declared_count=base_count, color=main))
    # OPUS2P-9: the join and the cut are said where the maker reaches them, not only in
    # Finishing.
    by_index = {r.index: r for r in rows}
    if band_rows:
        by_index[band_rows[0]].note = f"join {contrast} at the start of this round"
        if band_rows[-1] < rows[-1].index:
            by_index[band_rows[-1]].note = f"cut {contrast} after this round and fasten it off"
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
POUCH_MIN_EYELETS = 6              # OPUS2P-5: fewer and a drawstring does not gather
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
    leftover = re.sub(r"[a-z0-9'\s\-]", "", folded[:head.start()])     # OPUS2N-1: total
    if leftover:
        unknown.append(leftover)
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
    # OPUS2P-5: an even number of eyelets (both cord ends then come out of two neighbouring
    # eyelets on the outside) and at least POUCH_MIN_EYELETS, so the pouch gathers.
    step = 6 * (2 * unit) // math.gcd(6, 2 * unit)
    around = math.pi * POUCH_ACROSS_CM * gauge.stitches_per_10cm / 10.0
    n = max(step, int(round(around / step)) * step)
    if n // unit < POUCH_MIN_EYELETS:
        raise ValueError(f"{concept.slug}: at {concept.yarn_weight} gauge the pouch has "
                         f"{n // unit} eyelets, fewer than the {POUCH_MIN_EYELETS} a drawstring "
                         f"needs to gather")
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
             note=(f"{eyelets} eyelets; on the next round work {gap} sc into each ch-{gap} "
                   f"space"))
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
        materials=([Material(name=f"{concept.yarn_weight} acrylic ({main}) for the pouch",
                             yarn_weight=concept.yarn_weight, color_id=main)]
                   + ([Material(name=f"{concept.yarn_weight} acrylic ({cord_colour}) for the cord",
                                yarn_weight=concept.yarn_weight, color_id=cord_colour)]
                      if cord_colour != main else [])),
        components=[body, cord],
        assembly=[Seam("thread", "cord", "pouch", edge_a="left", edge_b="opening",
                       at_round=eyelet_round, spans_rounds=1,
                       note=(f"Weave the cord in and out of the {eyelets} eyelets of round "
                             f"{eyelet_round}, starting from the outside, so both ends come out "
                             f"of two neighbouring eyelets on the outside; knot each end and "
                             f"pull both to close the pouch."))],
        designer_notes=(f"{concept.category} concept drafted as a drawstring pouch: a {n}-st "
                        f"round base, {walls} wall rounds with {eyelets} eyelets in round "
                        f"{eyelet_round}, and a {cord_n}-ch cord"),
        finished_size_note=(
            f"A round pouch about {n / gauge.stitches_per_10cm * 10.0 / math.pi:.0f} cm across "
            f"and {walls * row_cm:.0f} cm tall at the stated gauge, with a cord about "
            f"{cord_cm:.0f} cm long. Computed, not yet measured on a worked sample."),
        provenance=provenance,
    )
