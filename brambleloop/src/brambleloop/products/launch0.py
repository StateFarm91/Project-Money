"""Launch-0: the smallest catalogue this company can currently defend, and what it rests on.

Research behind the children's half of this: `research/CHILDRENS_CATEGORY.md` (2026-09-24).
The plan itself: `research/LAUNCH0_CATALOGUE.md`.

The owner's rule for this module is one sentence -- *do not manufacture catalogue completion
ahead of Product Truth* -- and the whole design follows from taking it literally. A product is
not in Launch-0 because it would sell. It is in Launch-0 when a CIR exists, compiles clean,
measures the object the title promises, and the deliverable is makeable.

So nothing here asserts that a product is ready. Every readiness claim is **computed from the
CIR at call time** by compiling it and measuring its twin. The assortment is a list of
candidates and a set of gates; `launch0()` is what survives the gates, and it can shrink.

Three gates, and each one exists because a product in the generated catalogue fails it.

**A count in the title has to be backed by pieces in the CIR.** `vessels.py` was written
because "Market Basket Trio" was one flat panel. The same defect is still live in three more
products: `Component.make` exists, the generic builder never sets it, and so "Nordic Star
Ornament Set (6)" is one 7.5 x 11.7 cm rectangle. The gate is generic rather than a list of
those four, because the next product generated from the same builder will fail it the same way.

**A form that needs assembly has to have assembly in the CIR.** A garland is pennants on a
cord. A wall hanging hangs from something. Three products name such a form and carry an empty
`assembly`, which is the same failure one layer along: the CIR is a panel and the name is an
object.

**A fabric claim has to be expressible in the CIR at all.** This is the gate that cost the most
to write and it is the one that matters. `Row.color` is a single value and `Op` has no colour
field, so **the CIR cannot express more than one colour in a row.** Every "mosaic", "overlay"
and "graphghan" product in the catalogue is therefore a one-row stripe with a raised sc/dc
relief -- count-perfect, compiles clean, certifies, and is not the fabric the name describes.
The gate measures the colours actually present per row rather than arguing about what overlay
mosaic means, because the measurement is decidable and the argument is not.

What this module deliberately does not do:

  * It does not fix those products. The root cause is in `cir/**`, which another department
    owns, and a title edited to match a weaker fabric is a merchandising decision somebody
    should make on purpose rather than a side effect of a planning module.
  * It does not carry a demand or velocity score. `intel/childrens.py` refuses those for the
    same reason and a test there asserts the refusal; a number nobody measured sitting beside
    a compiled measurement borrows its credibility.
  * It does not claim calibration. `twin.calibrated` is False catalogue-wide -- nothing has
    been checked against a physically worked sample -- so every finished measurement here is
    arithmetic from a stated gauge, and `product_truth()` says so in the same dict that
    reports the numbers rather than in a footnote.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import date

from ..cir.compiler import compile_cir
from ..cir.model import CIR, Op
from ..cir.twin import build_twin
from ..intel import childrens as ch
from . import builder as flat
from . import vessels

SNAPSHOT_DATE = "2026-09-25"

# ---- evidence labels -------------------------------------------------------
#
# Same vocabulary the children's research uses, for the same reason: a plan that mixes a
# compiled measurement with a hunch and prints them in the same typeface is a plan whose
# reader cannot tell which is which.

SOURCED = "SOURCED"        # a figure read from a cited source, quoted
DERIVED = "DERIVED"        # arithmetic performed here on sourced numbers, shown
ESTIMATED = "ESTIMATED"    # a judgement with no measurement behind it, said so
UNKNOWN = "UNKNOWN"        # not established. Not filled in with a plausible number

LABELS: tuple[str, ...] = (SOURCED, DERIVED, ESTIMATED, UNKNOWN)


# ---- what the CIR can and cannot say --------------------------------------

def per_stitch_colour_expressible() -> bool:
    """Whether the CIR can put two colours in one row.

    Measures: the presence of a colour field on `Op`, which is the only place a per-stitch
    colour could live. Colour is a field of `Row`, so today the answer is no.
    Why: this is measured rather than stated because it is the fact the whole colourwork half
    of the catalogue depends on, and a sentence in a docstring would go stale silently. When
    somebody adds `Op.color`, this flips to True on its own and the gates below re-open
    without anybody editing a list.
    """
    return any(f.name in ("color", "colour") for f in fields(Op))


def per_stitch_reach_down_expressible() -> bool:
    """Whether the CIR can work one stitch into a row other than the one below it.

    Measures: the presence of a per-op row target on `Op`. `Row.into` retargets a whole row,
    which is not the same primitive.
    Why: overlay mosaic is defined by individual stitches reaching past the previous row. With
    no per-op target the technique is not expressible, so a pattern claiming it is claiming a
    fabric no compiled CIR in this repository can specify.
    """
    return any(f.name in ("into", "row_below", "below") for f in fields(Op))


# Fabric claims, and what each one needs to be true. A closed vocabulary on purpose: an
# open-ended claim detector reads "beautiful texture" as a testable promise and then argues
# with prose. These are technique names, which mean something specific.
COLOURWORK_CLAIMS: tuple[str, ...] = (
    "mosaic", "overlay", "graphghan", "colourwork", "colorwork", "intarsia", "tapestry",
    "fair isle", "fairisle",
)

# Stitches that make a relief a reader can feel. `loop` other than "both" counts too: a hdc
# worked in the back loop leaves a bar on the surface, which is the whole point of it.
TEXTURE_STITCHES: frozenset[str] = frozenset((
    "fpdc", "bpdc", "bob", "cable2x2", "cable1x1",
))

# Forms that are more than one piece of fabric by definition, and therefore need `assembly`.
ASSEMBLED_FORMS: tuple[str, ...] = (
    "garland", "bunting", "wall hanging", "mobile", "wreath",
)

# Words that promise more than one finished piece without giving a number.
PLURAL_MARKERS: tuple[str, ...] = (
    "set", "pair", "trio", "duo", "library", "collection", "bundle",
)

_COUNT_WORDS: dict[str, int] = {"pair": 2, "duo": 2, "trio": 3, "quartet": 4}


def title_promise(cir: CIR) -> dict:
    """How many finished pieces the name claims, against how many the CIR makes.

    Measures: a numeral or counting word in the title against the sum of `Component.make`.
    Why: `Component.make` is how the CIR says "work four of these", `vessels.py` uses it, and
    the generic builder in `builder.py` has no field for it -- so a title is currently the only
    place a multiplicity claim lives, and nothing checked it against the pattern.
    """
    lowered = cir.title.lower()
    claimed: int | None = None
    for token in re.findall(r"[a-z]+|\d+", lowered):
        if token.isdigit():
            claimed = max(claimed or 0, int(token))
        elif token in _COUNT_WORDS:
            claimed = max(claimed or 0, _COUNT_WORDS[token])
    plural = [w for w in PLURAL_MARKERS if w in lowered]
    makes = sum(c.make for c in cir.components)

    if claimed is not None:
        backed = makes >= claimed
        why = f"the title claims {claimed} pieces and the CIR makes {makes}"
    elif plural:
        backed = makes > 1
        why = (f"the title says {plural[0]!r}, which promises more than one piece, and the CIR "
               f"makes {makes}")
    else:
        backed = True
        why = "the title makes no multiplicity claim, so there is nothing to contradict"
    return {"claimed": claimed, "plural_markers": tuple(plural), "makes": makes,
            "backed": backed, "why": why}


def assembly_promise(cir: CIR) -> dict:
    """Whether a name that describes an assembled object has assembly behind it.

    Measures: an assembled-form word in the title against the length of `cir.assembly`.
    Why: a garland is pennants joined to a cord. A CIR with one panel and no seams is a panel,
    and the buyer who paid for a garland has to invent the part that makes it one.
    """
    lowered = cir.title.lower()
    named = [f for f in ASSEMBLED_FORMS if f in lowered]
    seams = len(cir.assembly or [])
    pieces = sum(c.make for c in cir.components)
    backed = (not named) or seams > 0 or pieces > 1
    return {"forms_named": tuple(named), "seams": seams, "pieces": pieces, "backed": backed,
            "why": ("the title names no assembled form" if not named else
                    f"the title names {named[0]!r}; the CIR carries {seams} seams and "
                    f"{pieces} pieces")}


def fabric_truth(cir: CIR, twin) -> dict:
    """What the fabric actually does, and whether the name's technique claim is expressible.

    Measures: the maximum number of distinct colours in any single row of the twin, whether any
    relief stitch or non-both loop target is used, and whether the title or designer notes make
    a colourwork claim.
    Why: this is the gate that stops a count-perfect pattern shipping under the name of a
    fabric it does not make. A two-colour picture needs two colours in one row. Every product
    generated by `builder.py` and by `nordic_forest.py` puts one colour on a whole row and
    varies sc against dc within it, which is a stripe with a relief -- so the motif is a
    height difference inside a colour band, not a shape drawn in two colours.
    """
    grid = twin.color_grid()
    colours_per_row = max((len({c for c in row}) for row in grid), default=0)
    loops = {cell for row in twin.loop_grid() for cell in row}
    relief = bool(twin.stitch_types_used & TEXTURE_STITCHES) or bool(loops - {"both"})
    heights = twin.stitch_types_used
    mixed_heights = len(heights) > 1

    text = f"{cir.title} {cir.designer_notes or ''}".lower()
    claims = tuple(c for c in COLOURWORK_CLAIMS if c in text)
    backed = (not claims) or colours_per_row >= 2
    return {
        "max_colours_in_one_row": colours_per_row,
        "colours_declared": sorted((cir.colors or {}).keys()),
        "relief_stitches_used": relief,
        "mixed_stitch_heights": mixed_heights,
        "stitches_used": sorted(heights),
        "colourwork_claims": claims,
        "backed": backed,
        "why": ("no colourwork technique is claimed, so the fabric is whatever the stitches "
                "make" if not claims else
                f"claims {claims[0]!r}; the fabric puts at most {colours_per_row} colour(s) in "
                f"any one row, and a two-colour motif needs two"),
        "cir_can_express_per_stitch_colour": per_stitch_colour_expressible(),
        "cir_can_express_per_stitch_reach_down": per_stitch_reach_down_expressible(),
    }


# ---- the candidate set -----------------------------------------------------

@dataclass(frozen=True)
class PriceBand:
    """A price with the evidence behind the band, or the admission that there is none."""

    low_cad: float
    high_cad: float
    proposed_cad: float
    basis: str            # one of LABELS
    why: str

    def __post_init__(self) -> None:
        if self.basis not in LABELS:
            raise ValueError(f"price basis must be one of {LABELS}: {self.basis!r}")
        if self.low_cad > self.high_cad:
            raise ValueError(f"band is inverted: {self.low_cad} > {self.high_cad}")


@dataclass(frozen=True)
class Variant:
    """One finished size inside one listing, and the builder that makes it."""

    key: str
    label: str
    build: str            # a key into BUILDERS


@dataclass(frozen=True)
class Candidate:
    """A product proposed for Launch-0, described so that the gates can be run on it.

    Note what is absent: any readiness flag. Whether this is publishable is computed, never
    declared, because a declared flag is a thing somebody sets while looking at the wrong
    version of the pattern.
    """

    slug: str
    title: str
    what_it_is: str
    why_at_launch: str
    variants: tuple[Variant, ...]
    pod: str
    price: PriceBand
    disqualifiers: tuple[str, ...]
    aspiration: tuple[str, ...]
    # Children's audience, when the product is for a child. None means "not a children's
    # product", stated rather than left as an omission -- the same discipline as the
    # `over_twelve` age band existing at all.
    subcategory: str | None = None
    audience: str | None = None
    # Statements we commit the deliverable to carrying. Held separately from what it carries
    # today, which is nothing, so the gap is visible instead of assumed away.
    committed_statements: tuple[str, ...] = ()


BUILDERS: dict[str, object] = {
    "basket_small": lambda: vessels.build_basket("small"),
    "basket_medium": lambda: vessels.build_basket("medium"),
    "basket_large": lambda: vessels.build_basket("large"),
    "hexagon_coasters": vessels.build_hexagon_coaster,
    "cloudline_blanket": lambda: flat.for_slug("cloudline-baby-blanket"),
    "harvest_runner": lambda: flat.for_slug("harvest-table-runner"),
}


def cir_for(build_key: str) -> CIR:
    """The CIR a variant names, built fresh.

    Measures: nothing. Why it exists: the registry is a dict of explicit callables rather than
    a dotted string resolved at runtime, so a variant naming a builder that does not exist is a
    KeyError here and not a plausible-looking empty product downstream.
    """
    fn = BUILDERS.get(build_key)
    if fn is None:
        raise KeyError(f"no builder named {build_key!r}; have {sorted(BUILDERS)}")
    return fn()          # type: ignore[operator]


# The observed price evidence, from `radar/market.py`, which recorded it on 2026-09-17 against
# named shops. Quoted rather than re-derived so that the source of a band is one hop away.
_BLANKET_BAND = (8.47, 11.65)
_CLUSTER_BAND = (4.00, 12.00)

_BABY_BLANKET_STATEMENTS = ch.required_statements("baby_blanket", ch.UNDER_3)
_NURSERY_STATEMENTS = ch.required_statements("nursery_decor", ch.UNDER_3)


CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        slug="nursery-nesting-baskets",
        title="Nesting Baskets, three sizes",
        what_it_is=(
            "One pattern, three baskets worked in the round from a flat disc base into "
            "straight walls: 15 cm, 20 cm and 25 cm across at the stated gauge."),
        why_at_launch=(
            "The children's research puts nursery decor first on obligation and "
            "verifiability, not on demand, and a basket is the only nursery-decor object in "
            "this repository that a compiled CIR already makes. The child does not handle it, "
            "nothing is applied to it, and the geometry is the kind `cir.geometry` measures "
            "exactly: the base disc sets how wide, the wall rounds set how tall."),
        variants=(
            Variant("small", "15 cm across, 9 cm tall", "basket_small"),
            Variant("medium", "20 cm across, 16 cm tall", "basket_medium"),
            Variant("large", "25 cm across, 23 cm tall", "basket_large"),
        ),
        pod="home_decor",
        subcategory="nursery_decor",
        audience=ch.UNDER_3,
        committed_statements=_NURSERY_STATEMENTS,
        price=PriceBand(
            *_CLUSTER_BAND, proposed_cad=6.50, basis=SOURCED,
            why=("the band is the CA$4-12 crochet-pattern cluster recorded in "
                 "radar/market.py OBSERVATIONS. A basket-specific observed price is UNKNOWN: "
                 "no profiled shop's basket price was captured, so the proposal sits mid-band "
                 "rather than pretending to a comparable")),
        disqualifiers=(
            "a worked sample whose walls slump at the stated gauge, which would make the "
            "stated height a number rather than a basket",
            "a base disc that does not lie flat, which the increase arithmetic predicts and "
            "only a sample confirms",
            "any decision to add an applied trim, which turns a nursery object the child does "
            "not handle into one that can shed a part",
        ),
        aspiration=(
            "every finished measurement is arithmetic from the stated gauge; twin.calibrated "
            "is False and no basket has been crocheted",
            "the firm cotton gauge that makes a basket stand up is asserted by the CIR and "
            "unverified in fabric",
        ),
    ),
    Candidate(
        slug="cloudline-baby-blanket",
        title="Cloudline Baby Blanket",
        what_it_is=(
            "A 78.8 x 97.2 cm baby blanket in two colours, worked flat. The colour changes "
            "every row and a raised diamond lattice is worked in double crochet against a "
            "single-crochet ground, so the fabric is a one-row stripe with a relief."),
        why_at_launch=(
            "Keepsake and baby blankets are the research's other first-entry sub-category, and "
            "this is the only blanket in the catalogue whose name does not claim a colourwork "
            "fabric the CIR cannot express. Class A geometry, no fitted sizing, no applied "
            "parts, and the largest single make in Launch-0, which is what carries the price."),
        variants=(Variant("one_size", "78.8 x 97.2 cm", "cloudline_blanket"),),
        pod="blankets",
        subcategory="baby_blanket",
        audience=ch.UNDER_3,
        committed_statements=_BABY_BLANKET_STATEMENTS,
        price=PriceBand(
            *_BLANKET_BAND, proposed_cad=7.50, basis=SOURCED,
            why=("the band is the premium mosaic-blanket band observed on HanJanCrochet "
                 "(CA$8.47-11.65) and MJsOffTheHookDesigns (CA$8.47-11.64) in "
                 "radar/market.py. We propose below its floor on purpose: those listings "
                 "advertise PATTERN + VIDEO, which radar/market.py records as table stakes "
                 "rather than a premium, and we have neither a video nor a review history")),
        disqualifiers=(
            "listing copy or imagery that shows a two-colour lattice picture: the fabric is "
            "one colour per row and a render showing otherwise is the motif-fidelity failure "
            "publish/motif_fidelity.py exists to block",
            "the designer note's claim of 'no long floats for small fingers to catch', which "
            "implies a carried-float colourwork fabric this pattern does not make; it has to "
            "be rewritten or removed before the listing goes up",
            "a worked sample whose drape at the stated gauge is stiff enough that the object "
            "is not a baby blanket",
        ),
        aspiration=(
            "78.8 x 97.2 cm is computed from the stated gauge; twin.calibrated is False",
            "none of the safe-sleep and children's statements this product must carry is "
            "rendered by the deliverable chain today -- grep finds no children's statement "
            "anywhere in publish/, cir/ or commerce/",
        ),
    ),
    Candidate(
        slug="hexagon-coaster-set",
        title="Hexagon Coaster Set (4)",
        what_it_is=(
            "Four hexagonal coasters, about 9.6 cm across the points, worked in joined rounds "
            "with the increases stacked at six corners and a contrast round one in from the "
            "edge."),
        why_at_launch=(
            "Not a children's product, and it is in Launch-0 for two jobs neither children's "
            "entry can do. It is the floor of the price ladder, and it is the cheapest honest "
            "way to exercise the whole Etsy listing path end to end -- a four-piece make with "
            "`Component.make` set correctly, a geometry the twin resolves as a disc, and no "
            "safety statement set in the way. Its merchandising value is review velocity and "
            "price structure, not distinctiveness, and saying so is more useful than dressing "
            "it up."),
        variants=(Variant("set_of_four", "4 pieces, 9.6 cm across", "hexagon_coasters"),),
        pod="home_decor",
        price=PriceBand(
            *_CLUSTER_BAND, proposed_cad=4.00, basis=SOURCED,
            why=("the CA$4-12 cluster from radar/market.py OBSERVATIONS, at its floor. "
                 "commerce/pricing.fees shows what this leaves after Etsy's cut, and the "
                 "answer is that this listing earns its place through reviews and cross-sell "
                 "rather than margin")),
        disqualifiers=(
            "a worked sample that does not lie flat, which is the one thing a coaster must do "
            "and the one thing the increase-per-round arithmetic cannot prove",
            "a price that has to rise above the cluster floor to clear fees, since the whole "
            "point of this listing is the bottom of the ladder",
        ),
        aspiration=(
            "9.6 cm across is arithmetic from the stated gauge; twin.calibrated is False",
            "flatness is predicted by the increase rate and unverified in fabric",
        ),
    ),
    # First reserve. Gate-clean and deliberately not in Launch-0: it is the same flat fabric as
    # the blanket, it serves neither the children's entry order nor the price ladder, and small
    # is the feature. Named rather than omitted so that "why only three" has an answer.
    Candidate(
        slug="harvest-table-runner",
        title="Harvest Table Runner",
        what_it_is="A 30 x 124 cm two-colour runner, worked flat with a chevron relief band.",
        why_at_launch=(
            "RESERVE, not launched. It passes every gate and adds no position: it repeats the "
            "blanket's construction, it is not a children's product, and Launch-0 is small on "
            "purpose. It is the first thing to add once there is evidence to add against."),
        variants=(Variant("one_size", "30 x 124 cm", "harvest_runner"),),
        pod="home_decor",
        price=PriceBand(*_CLUSTER_BAND, proposed_cad=5.50, basis=SOURCED,
                        why="the CA$4-12 cluster from radar/market.py OBSERVATIONS"),
        disqualifiers=("nothing measured; it is held back on assortment grounds rather than "
                       "on truth grounds",),
        aspiration=("every measurement is arithmetic from the stated gauge; twin.calibrated "
                    "is False",),
    ),
)

# The slugs Launch-0 actually launches, in listing order. The reserve is in CANDIDATES and not
# here, so the gate results for it are still computed and reported.
LAUNCH0_SLUGS: tuple[str, ...] = (
    "nursery-nesting-baskets", "cloudline-baby-blanket", "hexagon-coaster-set",
)


def candidate(slug: str) -> Candidate:
    for c in CANDIDATES:
        if c.slug == slug:
            return c
    raise KeyError(f"no Launch-0 candidate {slug!r}")


# ---- what is certified, per product ----------------------------------------

def product_truth(cand: Candidate) -> dict:
    """Compile every variant of a candidate and report what is established about it.

    Measures: per variant -- whether the CIR compiles with no errors, how many warnings, the
    finished dimensions its twin computes, and whether that twin is calibrated.
    Why: this is the module's reason to exist. A plan that says "certified" is a sentence; a
    plan that compiles the pattern while you read it is a measurement, and the two differ
    exactly when somebody edits the design and not the plan.
    """
    variants = []
    for v in cand.variants:
        cir = cir_for(v.build)
        result = compile_cir(cir)
        row: dict = {
            "variant": v.key, "label": v.label, "slug": cir.slug, "title": cir.title,
            "compiles": result.ok, "errors": [str(f) for f in result.errors],
            "warnings": [str(f) for f in result.warnings],
            "components": len(cir.components),
            "pieces": sum(c.make for c in cir.components),
            "title_promise": title_promise(cir),
            "assembly_promise": assembly_promise(cir),
        }
        if result.ok:
            twin = build_twin(cir, result)
            row.update({
                "width_cm": twin.width_cm, "height_cm": twin.height_cm,
                "shape": twin.shape, "outline": twin.outline,
                "stitches": twin.stitch_total,
                "calibrated": twin.calibrated,
                "fabric_truth": fabric_truth(cir, twin),
            })
        variants.append(row)

    gates = {
        "compiles_clean": all(v["compiles"] and not v["warnings"] for v in variants),
        "title_promise_backed": all(v["title_promise"]["backed"] for v in variants),
        "assembly_promise_backed": all(v["assembly_promise"]["backed"] for v in variants),
        "fabric_claim_backed": all(v.get("fabric_truth", {}).get("backed", False)
                                   for v in variants),
    }
    calibrated = all(v.get("calibrated") for v in variants)
    return {
        "slug": cand.slug,
        "variants": variants,
        "gates": gates,
        "passes_gates": all(gates.values()),
        "certified": {
            "a_cir_exists": True,
            "compiles_with_no_errors": all(v["compiles"] for v in variants),
            "compiles_with_no_warnings": all(not v["warnings"] for v in variants),
            "finished_measurements_computed": all(v.get("width_cm") is not None
                                                  for v in variants),
            "name_matches_what_the_cir_makes": (gates["title_promise_backed"]
                                                and gates["assembly_promise_backed"]
                                                and gates["fabric_claim_backed"]),
        },
        "aspiration": {
            "physically_calibrated": calibrated,
            "why_not": ("" if calibrated else
                        "twin.calibrated is False: every measurement above is arithmetic from "
                        "the gauge the CIR states, and no sample has been worked. This is the "
                        "largest unmeasured risk in the product and it is the same for every "
                        "item in the catalogue."),
            "stated_by_the_candidate": cand.aspiration,
        },
        "disqualifiers": cand.disqualifiers,
    }


def make_time(cand: Candidate) -> dict:
    """Customer make-hours per variant, for the whole object the buyer receives.

    Measures: `seasonal.leadtime.estimate_for`, which reads `Component.make` from the CIR.
    Why: a twin holds *one* instance of a component however many the pattern says to make, so
    the estimator used to report 1.1 hours for a set of four coasters that takes about four and
    a half -- a quarter of the truth, in the number a listing quotes to a buyer. This function
    used to correct for it locally, on the grounds that `seasonal/**` belonged to another
    department, and the local correction was wrong in its own way: it built a twin for the
    *first* component only and multiplied that by the total piece count, so a body-plus-two-ears
    product had the body counted three times and the ears not at all. Two copies of one value,
    both wrong, is the shape of the defect this codebase keeps meeting. The multiplicity now
    lives in the estimator, `estimate_for` builds one twin per component, and this reports what
    it returns.
    """
    from ..seasonal import leadtime

    rows = []
    for v in cand.variants:
        cir = cir_for(v.build)
        result = compile_cir(cir)
        if not result.ok:                                    # pragma: no cover - gated above
            rows.append({"variant": v.key, "hours": None,
                         "why": "does not compile, so no twin and no estimate"})
            continue
        est = leadtime.estimate_for(cir, result)
        each = ", ".join(f"{c['make']}x {c['component']} at {c['hours_each']} h"
                         for c in est.per_component)
        rows.append({
            "variant": v.key, "pieces": est.pieces,
            "hours_total": est.hours, "lane_total": est.lane,
            "per_component": [dict(c) for c in est.per_component],
            "evidence": est.evidence,
            "why": (f"{est.hours} h for the whole make, from {est.stitches} stitches across "
                    f"{est.pieces} piece(s): {each}"),
        })
    return {"slug": cand.slug, "variants": rows, "label": ESTIMATED,
            "basis": ("derived from the twin's stitch count at an assumed 700 stitches an "
                      "hour. leadtime reports that rate as assumed, not measured, and it stays "
                      "assumed until a sample is worked")}


def launch0() -> list[dict]:
    """The products that are actually in Launch-0, with their measured truth.

    Measures: the gate results for each listed slug.
    Why: a function rather than a constant, so the set can shrink. If a design changes under a
    product until its name stops describing what it makes, that product leaves Launch-0 here
    rather than being carried by a list somebody forgot to edit.
    """
    return [product_truth(candidate(s)) for s in LAUNCH0_SLUGS]


def price_plan(cand: Candidate) -> dict:
    """The candidate's price, put through the pricing module rather than asserted.

    Measures: `commerce.pricing.decide_price` against the observed band, which enforces the
    CA$3.00 floor, refuses a price above the band top while we have no review history, and
    reports what is left after Etsy's fee stack.
    Why: a price typed into a plan is a number somebody liked. A price that survived
    `decide_price` is a number that cleared the floor, the ceiling and the fee arithmetic, and
    the reasons it gives are the ones that belong in the listing decision record.
    """
    from ..commerce import pricing

    band = (cand.price.low_cad, cand.price.high_cad)
    decision = pricing.decide_price(cand.slug, category_band_cad=band,
                                    proposed_cad=cand.price.proposed_cad,
                                    sizes_offered=len(cand.variants))
    return {
        "slug": cand.slug,
        "band_cad": band,
        "band_basis": cand.price.basis,
        "band_why": cand.price.why,
        "proposed_cad": cand.price.proposed_cad,
        "price_cad": decision.price_cad,
        "net_cad_after_fees": decision.net_cad,
        "take_rate": round(decision.take_rate, 4),
        "reasons": decision.reasons,
        "warnings": decision.warnings,
        "held_at_proposal": decision.price_cad == cand.price.proposed_cad,
    }


def launch0_is_all_gate_clean() -> bool:
    """Whether everything listed for launch passes every gate.

    Measures: the conjunction of `passes_gates` over the listed slugs.
    Why: the hard rule, as one boolean. This is the assertion the plan document is allowed to
    make, and it is the only one.
    """
    return all(p["passes_gates"] for p in launch0())


# ---- the children's view ---------------------------------------------------

def childrens_view(cand: Candidate) -> dict:
    """What `intel.childrens` says about a candidate, assessed twice.

    Measures: `childrens.assess` on the candidate as the deliverable stands today (no
    statements written) and as planned (the committed statement set present).
    Why: the two answers are different questions and collapsing them is how a refusal turns
    into a to-do. `as_built` is the honest status of the product now; `as_planned` is what it
    becomes when the statement block exists. Neither is inferred -- both are computed by the
    module that holds the regulations.
    """
    if cand.subcategory is None:
        return {"is_a_childrens_product": False,
                "why": ("stated rather than omitted: this product is not merchandised to a "
                        "child, so no audience constraint attaches to it")}

    sub = ch.SUBCATEGORIES[cand.subcategory]
    required = ch.required_statements(cand.subcategory, cand.audience or ch.UNDER_3)

    def run(stated: tuple[str, ...]) -> dict:
        concept = ch.Concept(subject=cand.title, subcategory=cand.subcategory,
                             audience=cand.audience or ch.UNDER_3,
                             applied_parts=(), stated_statements=stated)
        findings = ch.assess(concept)
        missing = sorted(f.detail for f in findings if f.code == "STATEMENT_MISSING")
        return {
            # Two different questions, kept apart because collapsing them is how a refusal
            # turns into a to-do. `publishable` is "is this subject allowed at all"; a missing
            # statement is a REQUIRE_STATEMENT, so a product can be allowed and not yet
            # shippable, which is exactly the state `as_built` is in.
            "subject_is_allowed": ch.publishable(concept),
            "ready_to_ship": ch.publishable(concept) and not missing,
            "refusals": [f.code for f in findings if f.severity == ch.REFUSE],
            "statements_missing": missing,
            "findings": len(findings),
        }

    return {
        "is_a_childrens_product": True,
        "subcategory": sub.slug,
        "label": sub.label,
        "form_pod": sub.pod,
        "verdict": sub.verdict,
        "why": sub.why,
        "audience": cand.audience,
        "audience_label": ch.AGE_BANDS[cand.audience or ch.UNDER_3].label,
        "required_statements": required,
        "committed_statements": cand.committed_statements,
        "commitment_covers_requirement": set(required) <= set(cand.committed_statements),
        "as_built": run(()),
        "as_planned": run(cand.committed_statements),
        "applied_parts": (),
        "applied_parts_why": (
            "none, by design. Under 36 months a detachable applied part is refused rather "
            "than warned about, so the Brambleloop default is an integral surface: nothing on "
            "any Launch-0 product is held on by friction, a washer or glue."),
    }


def statement_rendering_gap() -> dict:
    """Whether the deliverable chain can print the statements these products must carry.

    Measures: a search of the publishing, CIR and commerce packages for any of the statement
    keys or their distinctive words.
    Why: `required_statements()` computes the obligation and nothing consumes it. A statement
    set that exists only as a list in a planning module is not on the customer's PDF, and the
    gap is worth measuring because it is the one thing standing between these two children's
    products and a publishable deliverable.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    needles = ("safe sleep", "safe_sleep", "supervised", "choking", "unsupervised sleep")
    hits: list[str] = []
    for package in ("publish", "cir", "commerce"):
        for path in sorted((root / package).glob("*.py")):
            text = path.read_text(encoding="utf-8").lower()
            if any(n in text for n in needles):
                hits.append(f"{package}/{path.name}")
    return {
        "searched": ["publish/*.py", "cir/*.py", "commerce/*.py"],
        "needles": needles,
        "files_mentioning_a_statement": hits,
        "can_render_the_statement_set": bool(hits),
        "why": ("the children's statement set is computed by intel.childrens and consumed by "
                "nothing. Until the deliverable renders it, a children's pattern is not "
                "publishable however clean its arithmetic is. publish/pdf.py is owned by the "
                "deliverable department; this is a measurement for them, not an edit."),
    }


# ---- seasonality: the counter-seasonal pairing, re-derived -----------------
#
# Wikimedia pageviews, en.wikipedia, `user` agent class, monthly, 2025-09 -> 2026-08, pulled
# 2026-09-24 by the research in `research/CHILDRENS_CATEGORY.md` section 3.1. SOURCED:
# https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Amigurumi/monthly/2025090100/2026083100
# and the same URL with `Baby_shower`. Encyclopaedia reading is a proxy for interest and not
# for purchase intent; it is English Wikipedia, so the population is closest to GLOBAL/US
# rather than CA; and it is one year, n=12. Carried here because the pipeline's order is a
# consequence of it and a sequence whose evidence lives in another document is a sequence
# somebody will reorder.

MONTHS: tuple[str, ...] = (
    "2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
    "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08",
)

PAGEVIEWS: dict[str, tuple[int, ...]] = {
    "Amigurumi": (6247, 6519, 6848, 7676, 6017, 4745, 4636, 4261, 4472, 3997, 4322, 4340),
    "Baby_shower": (11077, 10141, 9026, 6914, 8402, 7492, 8638, 8232, 9441, 9760, 7786, 7325),
}

PAGEVIEWS_SOURCE = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
    "all-access/user/{article}/monthly/2025090100/2026083100")


def _swing(series) -> dict:
    values = list(series)
    peak, trough = max(values), min(values)
    return {
        "mean": round(sum(values) / len(values), 1),
        "peak_over_trough": round(peak / trough, 3),
        "peak_month": MONTHS[values.index(peak)],
        "trough_month": MONTHS[values.index(trough)],
    }


def seasonality(amigurumi_share: float = 0.5) -> dict:
    """The swing of each series, and of a portfolio that holds both.

    Measures: peak/trough ratio of each series, and of a mean-normalised blend at the given
    weight.
    Why: the research measured that the two series are counter-seasonal -- amigurumi's annual
    maximum lands in the same month as baby-shower's annual minimum -- and asserted that a
    portfolio holding both should be flatter. That is arithmetic, so it is done here rather
    than believed. Normalising each series to its own mean before blending is the point: the
    two have different absolute levels and a raw sum would weight baby-shower 1.6x simply for
    being the more-read article, which is not a portfolio decision anybody made.
    """
    if not 0.0 <= amigurumi_share <= 1.0:
        raise ValueError(f"share must be between 0 and 1: {amigurumi_share}")
    per_series = {name: _swing(s) for name, s in PAGEVIEWS.items()}

    def normalised(name: str) -> list[float]:
        s = PAGEVIEWS[name]
        mean = sum(s) / len(s)
        return [v / mean for v in s]

    ami, baby = normalised("Amigurumi"), normalised("Baby_shower")
    blend = [amigurumi_share * a + (1 - amigurumi_share) * b for a, b in zip(ami, baby)]
    blended = _swing(blend)

    worst = max(v["peak_over_trough"] for v in per_series.values())
    best_single = min(v["peak_over_trough"] for v in per_series.values())
    return {
        "series": per_series,
        "source": PAGEVIEWS_SOURCE,
        "label": SOURCED,
        "amigurumi_share": amigurumi_share,
        "blended": blended,
        "blend_label": DERIVED,
        "counter_seasonal": (per_series["Amigurumi"]["peak_month"]
                            == per_series["Baby_shower"]["trough_month"]),
        "flatter_than_either_alone": blended["peak_over_trough"] < best_single,
        "why": (f"amigurumi alone swings {per_series['Amigurumi']['peak_over_trough']}x and "
                f"baby-occasion alone {per_series['Baby_shower']['peak_over_trough']}x; a "
                f"{amigurumi_share:.0%}/{1 - amigurumi_share:.0%} blend swings "
                f"{blended['peak_over_trough']}x, which is flatter than either, because the "
                f"one peaks in the month the other troughs. The worst single-category swing "
                f"available is {worst}x."),
        "caveats": (
            "pageviews are a proxy for interest, not for purchase intent",
            "en.wikipedia, so the population is closest to GLOBAL/US rather than CA",
            "one year, n=12, and no confidence interval is claimed",
        ),
    }


# ---- the pipeline ----------------------------------------------------------
#
# Held in a separate structure from CANDIDATES on purpose. A pipeline entry has no CIR, and the
# single easiest way to manufacture catalogue completion is to keep aspirations in the same
# list as products and let a later reader lose track of which column meant what.

@dataclass(frozen=True)
class PipelineEntry:
    """Something we intend to build, with the reason it is not in Launch-0."""

    slug: str
    title: str
    wave: int
    subcategory: str | None
    what_it_is: str
    why_this_position: str
    blocked_on: tuple[str, ...]
    owner_of_the_blocker: str
    # The event this is timed against, when it is timed against one at all.
    event: str = ""
    event_date: str = ""
    make_hours: float = 0.0


PIPELINE: tuple[PipelineEntry, ...] = (
    PipelineEntry(
        slug="catalogue-hygiene",
        title="Retire or rename the eleven CIRs whose names their patterns do not make",
        wave=1,
        subcategory=None,
        what_it_is=(
            "Eleven CIRs fail a gate in this module: winter-village-graphghan, "
            "autumn-oak-mosaic-throw and mosaic-placemat-pair claim a colourwork fabric the "
            "CIR cannot express; nordic-star-ornaments, mosaic-placemat-pair and "
            "pressed-flower-motifs claim a piece count the CIR does not make; spooky-garland, "
            "valentine-heart-garland and cottage-wall-hanging name an assembled object with no "
            "assembly. The three nordic_forest sizes fail the colourwork gate too."),
        why_this_position=(
            "First, and before any new product, because these are the reason the catalogue "
            "looks larger than it is. Every one of them compiles clean and certifies, which is "
            "precisely why a name-versus-fabric gate had to exist."),
        blocked_on=("a merchandising decision: rename to what the fabric does, or hold the "
                    "product until the CIR can express the fabric",),
        owner_of_the_blocker="product planning, with the visual department on the renders",
    ),
    PipelineEntry(
        slug="per-stitch-colour",
        title="Per-stitch colour in the CIR",
        wave=1,
        subcategory=None,
        what_it_is=(
            "`Row.color` is one value per row and `Op` has no colour field, so no compiled "
            "pattern in this repository can put two colours in one row. That single absence "
            "rules out mosaic, overlay mosaic, graphghan, intarsia, tapestry crochet and any "
            "keepsake blanket with a name or a date worked into it."),
        why_this_position=(
            "It is the highest-value unbuilt capability in the product, measured by what it "
            "unblocks: the entire colourwork half of the intended catalogue, and the "
            "keepsake sub-category the research identified as having the audience's highest "
            "price tolerance."),
        blocked_on=("`cir/**` is owned by another department and this module does not edit it",),
        owner_of_the_blocker="whoever owns cir/model.py, compiler.py, twin.py and writer.py",
    ),
    PipelineEntry(
        slug="keepsake-milestone-blanket",
        title="Milestone and keepsake baby blanket",
        wave=2,
        subcategory="keepsake_blanket",
        what_it_is=(
            "A blanket with a name, a birth date or monthly milestone markers worked in. The "
            "research's highest-price-tolerance children's sub-category and a LEAD verdict in "
            "intel.childrens."),
        why_this_position=(
            "Second rather than first because it needs two things that do not exist: per-stitch "
            "colour, and a validated glyph set. `products/motifs.LIBRARY` holds eight motifs "
            "and no alphabet or numerals, so a name cannot be charted at all today."),
        blocked_on=(
            "per-stitch colour in the CIR (see per-stitch-colour)",
            "an alphabet and numeral motif set validated at blanket gauge and density",
            "personalisation.py routes a construction-level customisation to its own compile "
            "and certificate, which means a named blanket is a product per name -- the "
            "economics of that need deciding before it is built, not after",
        ),
        owner_of_the_blocker="cir/** for the colour primitive; product planning for the glyphs",
        event="baby_shower_season",
        event_date="2027-09-01",
    ),
    PipelineEntry(
        slug="amigurumi-lovey-embroidered-face",
        title="Lovey with an embroidered face",
        wave=2,
        subcategory="lovey",
        what_it_is=(
            "A small soft comforter: a head worked in the round from a magic ring with "
            "increase and decrease shaping, an integral embroidered face, and a small "
            "blanket-weight body. No safety eyes, no applied parts, nothing held on by a "
            "washer."),
        why_this_position=(
            "The counter-seasonal half of the portfolio, and it is genuinely buildable: "
            "`vessels.py` already works discs and walls in the round from a magic ring, and "
            "`cir.stitches` carries inc, dec, dc_inc and dc_dec, so sphere shaping needs no new "
            "primitive. An embroidered face needs no primitive at all -- it is a finishing "
            "instruction, which is exactly why the research made it the default rather than a "
            "caveat."),
        blocked_on=(
            "a stuffing-containment check: intel.childrens names construction integrity as a "
            "required statement and nothing measures whether the stated gauge is tight enough "
            "that stuffing cannot migrate through the fabric",
            "the children's statement block in the deliverable (see statement_rendering_gap)",
        ),
        owner_of_the_blocker="product planning can build the CIR; publish/** owns the statements",
        event="december_gifting",
        event_date="2026-12-15",
        make_hours=5.0,
    ),
    PipelineEntry(
        slug="baby-wearables",
        title="Baby and child hats, booties and mittens",
        wave=3,
        subcategory="baby_wearables",
        what_it_is=(
            "Sub-four-hour makes graded by head circumference. A BUILD verdict in "
            "intel.childrens and the fastest review accumulator available to us."),
        why_this_position=(
            "Third because grading needs a table we do not carry: intel.childrens holds the "
            "CYC chest measurements and head circumference is a different published chart. "
            "Cheap to unblock and not yet done, so it is honest to put it behind the lovey."),
        blocked_on=("the CYC head-circumference table, read and landed as data with its source",),
        owner_of_the_blocker="product planning",
    ),
    PipelineEntry(
        slug="childrens-fitted-garments",
        title="Children's cardigans, dresses and sweaters",
        wave=4,
        subcategory="childrens_garment",
        what_it_is=(
            "Graded fitted garments for 3 months to 16 years. A CAREFUL verdict in "
            "intel.childrens: the CYC tables make grading arithmetic, and fit is not "
            "verifiable by compiler."),
        why_this_position=(
            "Last, which is where the research puts it and where the repository's own Class C "
            "verifiability model puts it. It is the only sub-category here whose correctness "
            "genuinely requires physical test-crocheting in every size."),
        blocked_on=(
            "physical samples, which twin.calibrated being False makes a prerequisite rather "
            "than a nicety",
            "the drawstring rule, which intel.childrens.assess already enforces: no neck or "
            "hood tie on children's upper outerwear 2T-12, and no toggle or knot on a waist "
            "tie's free end",
        ),
        owner_of_the_blocker="quality/physical.py plus an owner action to crochet samples",
    ),
)

# Sub-categories we do not publish instructions for, resolved from the module that holds the
# reasons rather than restated here. Kept as a function because the source of truth is theirs.


def never_published() -> tuple[dict, ...]:
    """The children's sub-categories whose patterns we refuse, and why, from intel.childrens.

    Measures: the sub-categories whose verdict is NEVER or AVOID.
    Why: a pipeline that lists only what we will build reads as though everything else is
    merely later. These are not later.
    """
    out = []
    for sub in ch.SUBCATEGORIES.values():
        if sub.verdict in (ch.NEVER, ch.AVOID):
            out.append({"slug": sub.slug, "label": sub.label, "verdict": sub.verdict,
                        "why": sub.why, "constraints": sub.constraints})
    return tuple(out)


def pipeline_is_not_catalogue() -> bool:
    """Whether any pipeline entry has leaked into the launch set.

    Measures: the intersection of pipeline slugs and candidate slugs.
    Why: the hard rule's failure mode has a shape. Somebody adds a promising aspiration to the
    product list "so it is not forgotten", and three weeks later it is in a listing draft. The
    two structures are separate types and this asserts they stay separate populations.
    """
    return not ({e.slug for e in PIPELINE} & {c.slug for c in CANDIDATES})


def pipeline_plan(today: date | None = None) -> list[dict]:
    """The pipeline in order, with a launch date computed for the entries that have an event.

    Measures: `seasonal.leadtime.compile_launch` for each entry that names an event date and a
    make time -- the backward chain from the event through the customer's own crochet hours.
    Why: the sequence is the deliverable, and the interesting part of a seasonal sequence is
    the date by which the work must already be finished. That date is arithmetic over stated
    assumptions, every one of which leadtime reports as assumed rather than measured.
    """
    from ..seasonal import leadtime

    today = today or date.today()
    out = []
    for entry in sorted(PIPELINE, key=lambda e: (e.wave, e.slug)):
        row = {
            "slug": entry.slug, "title": entry.title, "wave": entry.wave,
            "subcategory": entry.subcategory, "what_it_is": entry.what_it_is,
            "why_this_position": entry.why_this_position,
            "blocked_on": entry.blocked_on,
            "owner_of_the_blocker": entry.owner_of_the_blocker,
            "has_a_cir": False,
        }
        if entry.subcategory:
            sub = ch.SUBCATEGORIES[entry.subcategory]
            row["childrens_verdict"] = sub.verdict
            row["required_statements"] = ch.required_statements(entry.subcategory, ch.UNDER_3)
        if entry.event_date and entry.make_hours:
            plan = leadtime.compile_launch(
                entry.event, date.fromisoformat(entry.event_date),
                make_hours=entry.make_hours)
            row["launch_timing"] = {
                "event": entry.event, "event_date": entry.event_date,
                "lane": plan.lane,
                "latest_effective_launch": plan.latest_effective_launch.isoformat(),
                "preferred_launch": plan.preferred_launch.isoformat(),
                "work_must_start_by": plan.work_must_start_by.isoformat(),
                "status": plan.status(today),
                "recommendation": plan.recommendation(today),
                "every_assumption_measured": plan.assumptions.fully_measured,
            }
        out.append(row)
    return out


# ---- the whole picture -----------------------------------------------------

def excluded_from_launch0() -> list[dict]:
    """Every product with a CIR that is not in Launch-0, and the measured reason.

    Measures: the gates, run over the whole generated catalogue, the nordic_forest sizes and
    the vessel family.
    Why: the exclusions are the load-bearing part of a small assortment. Listing three products
    without saying what was left out and on what evidence is indistinguishable from having only
    built three, and the difference matters: these fourteen exist, compile and certify.
    """
    from . import nordic_forest

    everything: dict[str, object] = {}
    for slug in flat.CATALOGUE:
        everything[slug] = (lambda s=slug: flat.for_slug(s))
    for size in nordic_forest.SIZES:
        everything[f"nordic-forest-{size}"] = (lambda s=size: nordic_forest.build(s))
    for size in ("small", "medium", "large"):
        everything[f"market-basket-{size}"] = (lambda s=size: vessels.build_basket(s))
    everything["hexagon-coaster-set"] = vessels.build_hexagon_coaster

    launched: set[str] = set()
    for slug in LAUNCH0_SLUGS:
        for v in candidate(slug).variants:
            launched.add(cir_for(v.build).slug)

    out = []
    for key, make in sorted(everything.items()):
        cir = make()                                    # type: ignore[operator]
        result = compile_cir(cir)
        if not result.ok:
            out.append({"key": key, "title": cir.title, "compiles": False,
                        "reasons": [str(f) for f in result.errors]})
            continue
        twin = build_twin(cir, result)
        t, a, f = title_promise(cir), assembly_promise(cir), fabric_truth(cir, twin)
        reasons = []
        if not t["backed"]:
            reasons.append(f"title promise: {t['why']}")
        if not a["backed"]:
            reasons.append(f"assembly promise: {a['why']}")
        if not f["backed"]:
            reasons.append(f"fabric claim: {f['why']}")
        row = {"key": key, "slug": cir.slug, "title": cir.title, "compiles": True,
               "in_launch0": cir.slug in launched, "gate_reasons": reasons,
               "gate_clean": not reasons}
        if cir.slug not in launched and not reasons:
            row["held_back_on"] = ("assortment, not truth: it passes every gate and adds no "
                                  "position Launch-0 needs")
        out.append(row)
    return out


def report(today: date | None = None) -> dict:
    """Everything this module knows, computed.

    Measures: all of the above.
    Why: one call that the plan document and any later session can diff against. A planning
    document whose numbers were typed by hand goes stale the first time a design changes; one
    whose numbers come from here goes stale visibly.
    """
    return {
        "snapshot": SNAPSHOT_DATE,
        "launch0": launch0(),
        "launch0_is_all_gate_clean": launch0_is_all_gate_clean(),
        "childrens": {s: childrens_view(candidate(s)) for s in LAUNCH0_SLUGS},
        "prices": [price_plan(candidate(s)) for s in LAUNCH0_SLUGS],
        "make_time": [make_time(candidate(s)) for s in LAUNCH0_SLUGS],
        "statement_rendering_gap": statement_rendering_gap(),
        "seasonality": seasonality(),
        "pipeline": pipeline_plan(today),
        "pipeline_is_not_catalogue": pipeline_is_not_catalogue(),
        "never_published": never_published(),
        "excluded": excluded_from_launch0(),
        "cir_capability": {
            "per_stitch_colour": per_stitch_colour_expressible(),
            "per_stitch_reach_down": per_stitch_reach_down_expressible(),
            "why_it_matters": ("with neither, a colourwork or mosaic fabric is not "
                               "expressible, so a pattern claiming one is claiming a fabric no "
                               "compiled CIR here can specify"),
        },
        "calibration": {
            "any_product_calibrated": False,
            "why": ("twin.calibrated is False catalogue-wide. Every finished measurement in "
                    "this report is arithmetic from a stated gauge and none has been checked "
                    "against a worked sample."),
        },
    }
