"""ENG-FAMILIES: route a researched concept to the construction engine that really makes it.

The gap this closes. `radar.intake` admitted a research concept only when it was a flat
rows panel (`SUPPORTED_CONSTRUCTIONS = ("flat_rows",)`), although `cir.draft` already drafts
radar concepts through `creative.fallback_constructions.plan` into several verified engines:
a basket worked in joined rounds (`vessel`), a charted two-colour tapestry basket
(`tapestry_basket`), a cushion's two seamed panels (`panel_pair`). So a researched basket was
refused at intake while the very same title from the static POOL drafted, compiled and
certified as a basket.

This module is the single answer to "which engine makes this concept, and may it be built",
and it holds no routing rule of its own. The route is whatever `fallback_constructions.plan`
-- the function `cir.draft` itself calls -- returns for the concept's category and title.
What this adds is two checks around it:

* **No mislabelling.** The concept *declares* a form and a construction (closed vocabulary,
  `creative.concept`). The declaration must name the family the draft path will actually
  build. A concept that declares a tapestry basket whose title the draft path would build as
  a plain striped vessel, or a basket whose category drafts a flat panel, is held, never
  drafted as something it does not say.
* **Verified families only.** Each family carries the status its evidence earns
  (`FAMILIES`): `verified` (a research-derived, non-catalogue concept compiles, builds its
  twin, reverse-compiles, passes Product Truth's size check and is granted certification,
  pinned by a named test), `physical_gate` (all of that computes clean and certification
  withholds only for the physical sample the risk class requires -- the existing sample path
  carries it), `partial` (an engine exists but the chain does not certify it, or no pinned
  research-derived proof exists yet) or `none` (no engine). Only `verified` and
  `physical_gate` are admitted.

Everything else is HELD with `construction_unsupported:<family>` as the first words of the
reason, so `products.production_inventory` can show it as a construction hold. A held concept
is never flattened into a panel.

Children's products are not routed around: intake's `_children_reasons` pre-check, and the
`childrens_decision` / `small_parts` gates at PDF build, read the concept's category and
title, which routing never changes. No baby or nursery item routes to a shaped family here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import fallback_constructions as FC

VERIFIED, PHYSICAL_GATE, PARTIAL, NONE = "verified", "physical_gate", "partial", "none"
ADMITTED_STATUSES = frozenset({VERIFIED, PHYSICAL_GATE})
HOLD_PREFIX = "construction_unsupported:"


@dataclass(frozen=True)
class Family:
    key: str
    engine: str                 # the builder `cir.draft` calls for this family
    status: str
    proof: str                  # the test that pins the status, or "" when none does
    sizes: tuple[str, ...]      # the size keys the engine binds from a title
    size_source: str            # where those sizes come from, honestly
    gaps: str


PROOF = "tests/test_eng_families.py"

FAMILIES: dict[str, Family] = {f.key: f for f in (
    Family(FC.FLAT_PANEL, "runtime.pipeline.concept_to_cir", VERIFIED,
           f"{PROOF}::test_a_research_flat_runner_certifies_end_to_end",
           ("per-category template",),
           "runtime.pipeline._GEOMETRY / _TITLE_GEOMETRY; size classes from "
           "creative.size_truth (Craft Yarn Council blanket sizes, pillow forms)",
           "plain sc/dc stripes only: no charted motif, no texture stitch"),
    Family(FC.VESSEL, "creative.fallback_constructions.vessel", VERIFIED,
           f"{PROOF}::test_a_research_basket_routes_to_the_vessel_engine_and_certifies",
           ("small", "medium", "large"),
           "products.vessels.BASKET_SIZES (house design sizes, no published standard)",
           "striped walls only; one size per release; pet bed is cat-size only"),
    Family(FC.TAPESTRY, "creative.fallback_constructions.tapestry_basket", VERIFIED,
           f"{PROOF}::test_a_research_tapestry_basket_routes_to_its_chart_and_certifies",
           ("small", "medium", "large"),
           "products.vessels.BASKET_SIZES (house design sizes, no published standard)",
           "two charts (diamond, check), two colours; motif words outside the allowlist refuse"),
    Family(FC.PANEL_PAIR, "creative.fallback_constructions.panel_pair", PHYSICAL_GATE,
           f"{PROOF}::test_a_research_cushion_is_physical_gated_not_flattened",
           ("per-category template",),
           "creative.size_truth PILLOW_FORMS (standard pillow-form sizes)",
           "certification withholds for the risk class C physical sample"),
    Family(FC.POUCH, "creative.fallback_constructions.pouch", PARTIAL, "",
           ("one size",), "fallback_constructions.POUCH_ACROSS_CM (design choice)",
           "certification refuses ASSET_COLOR_ABSENT: the pouch works one palette colour "
           "while its hero asset depicts two"),
    Family(FC.TOTE, "creative.fallback_constructions.tote", PARTIAL, "",
           ("small", "medium", "large"), "products.vessels.BASKET_SIZES",
           "no research-derived concept is pinned through certification yet"),
    Family(FC.COSY, "creative.fallback_constructions.cosy", PARTIAL, "",
           ("one size",), "fallback_constructions.EGG_AROUND_CM (a measured egg)",
           "no research-derived concept is pinned through certification yet"),
    Family(FC.STOCKING, "creative.fallback_constructions.stocking", PARTIAL, "",
           ("one size",), "fallback_constructions.STOCKING_SIZE_SOURCE (design choice)",
           "no research-derived concept is pinned through certification yet"),
    Family(FC.TRIANGLE, "creative.fallback_constructions.triangle", PARTIAL, "",
           ("one size",), "fallback_constructions.SHAWL_WINGSPAN_CM (design choice)",
           "no research-derived concept is pinned through certification yet"),
)}

# Families with no engine on the radar draft path. Named, so a hold says what is missing.
UNBUILT: dict[str, str] = {
    "amigurumi": "spiral rounds with sculpted increases and decreases; the radar draft path "
                 "has no shaped-form engine",
    "mosaic": "overlay mosaic needs stitches that reach past the previous row or round; no "
              "radar engine charts them",
    "graphghan": "a charted picture worked in rows; the radar template drafts plain stripes",
    "cable": "post-stitch crossings; no radar engine works them (B-080)",
    "motif": "motifs worked in rounds and joined; no radar engine joins motifs",
    "c2c": "diagonal tile increases and decreases; no radar engine works them",
    "side_to_side": "a lengthwise foundation; no radar engine authors it",
    "modular": "several shaped panels and an assembly; no radar engine assembles them",
    "garment": "a graded garment from body tables; only the creative tournament path "
               "(creative.garment_design) builds one",
    "ornament": "a closed or shaped small piece; no radar engine makes it",
    "hat": "a fitted crown and brim; the sourced head chart lacks height and ease",
    "flower": "a motif worked in rounds; no radar engine makes it",
    "seasonal_decor": "garlands, shapes and ornaments; no radar engine makes them",
}


# H1 (ENG-FAMILIES review): a title or premise can NAME a construction or feature the drafted
# engine does not build. The plan reads the category and a few head nouns; it never reads
# "granny", "cable" or "lid", so a "Granny Square Basket" drafted as the plain striped vessel
# and certified under a name it does not make. One shared vocabulary, read for EVERY admitted
# family: (feature, regex over the folded text, families the word is honest for).
NAMED_FEATURES: tuple[tuple[str, str, frozenset], ...] = (
    ("granny_square", r"\bgranny\b|\bafghan squares?\b|\bsquare motifs?\b", frozenset()),
    ("cable", r"\bcables?\b|\bcabled\b", frozenset()),
    ("bobble", r"\bbobbles?\b|\bpopcorn\b|\bpuff(?:s|ed)?\b|\bnubby\b", frozenset()),
    ("waffle_stitch", r"\bwaffles?\b|\bbasket[- ]?weave\b|\btextured?\b|\bribbed\b|"
                      r"\bribbing\b|\bwoven\b|\bcluster\b|\bshell stitch\b|\bcrocodile\b",
     frozenset()),
    ("lid", r"\blids?\b|\blidded\b|\bcovered\b|\blidded\b|\bzipp?(?:er|ered)?\b|"
            r"\bbuttons?\b|\bclosures?\b|\bflaps?\b", frozenset()),
    ("handles", r"\bhandles?\b|\bhandled\b|\bstraps?\b", frozenset({FC.TOTE})),
    ("amigurumi_features", r"\bamigurumi\b|\bears?\b|\btails?\b|\bwhiskers?\b|\bfaces?\b|"
                           r"\bsnouts?\b|\beyes?\b|\bpaws?\b|\bhorns?\b|\bwings?\b|"
                           r"\bplush\b|\bstuffed\b", frozenset()),
    ("trim", r"\bfring(?:e|ed)\b|\btassels?\b|\bpom[- ]?poms?\b|\bruffles?\b|\bfrills?\b|"
             r"\bscallop(?:s|ed)?\b|\bpicots?\b|\blace\b|\blacy\b|\bfilet\b|"
             r"\bapplique\b|\bappliqu\u00e9d?\b|\bembroider(?:y|ed)\b|\bbeaded\b|"
             r"\bsequin(?:s|ned)?\b", frozenset()),
    ("lining_pocket", r"\blin(?:ed|ing)\b|\bpockets?\b|\bpadded\b|\bquilted\b|"
                      r"\bfelted\b|\bstiffened\b|\bwired\b|\breinforced\b", frozenset()),
    ("motif_assembly", r"\bhexie\b|\bhexagon (?:motifs?|squares?|tiles?)\b|\bflowers?\b|"
                       r"\bfloral\b|\bpatchwork\b|\bmotif (?:join|panel)\b|\bjoined\b",
     frozenset()),
    ("colourwork", r"\bintarsia\b|\bfair[- ]?isle\b|\bjacquard\b|\bmosaic\b|\bc2c\b|"
                   r"\bcorner[- ]to[- ]corner\b|\bgraph ?gh?an\b|\bpixel\b|\bcharted\b",
     frozenset()),
    ("garment_or_wearable", r"\b(?:hat|beanie|cardigan|sweater|sock|mitten|cowl)s?\b", frozenset()),
)


def named_feature(text: str, family: str = "") -> tuple[str, str] | None:
    """The first construction or feature a title/premise names that `family`'s engine does not
    build, as (feature, matched word); None when it names none."""
    folded = FC.fold_title(text)
    for feature, rx, honest_for in NAMED_FEATURES:
        if family in honest_for:
            continue
        hit = re.search(rx, folded)
        if hit:
            return feature, hit.group(0)
    return None

# Declared construction -> the family label it names when no engine route applies.
_CONSTRUCTION_LABEL: dict[str, str] = {
    "amigurumi_shaping": "amigurumi", "mosaic_overlay": "mosaic", "cable_panel": "cable",
    "granny_square": "motif", "motif_join": "motif", "corner_to_corner": "c2c",
    "side_to_side": "side_to_side", "modular_panels": "modular", "top_down_yoke": "garment",
    "bottom_up": "garment", "tapestry": FC.TAPESTRY,
}
# Declared form -> the family label, for round constructions whose family is the object.
_FORM_LABEL: dict[str, str] = {
    "basket": FC.VESSEL, "pouch": FC.POUCH, "bag": FC.TOTE, "tube": FC.COSY,
    "stocking": FC.STOCKING, "draped_garment": FC.TRIANGLE, "toy": "amigurumi",
    "sphere": "amigurumi", "cone": "amigurumi", "ornament": "ornament", "hat": "hat",
    "fitted_garment": "garment", "wreath": "ornament", "garland": "seasonal_decor",
}
_ROUND = frozenset({"in_the_round", "seamless_tube"})


def declared_family(form: str, construction: str) -> str | None:
    """The family a concept's declared (form, construction) names, or None for flat rows
    (whose family is decided by its category: a flat panel or a seamed panel pair)."""
    if construction == "flat_rows":
        if form == "draped_garment":
            return FC.TRIANGLE
        if form == "stocking":
            return FC.STOCKING
        return None
    if construction == "tapestry":
        return FC.TAPESTRY
    if construction in _ROUND:
        return _FORM_LABEL.get(form, f"{form}_in_the_round")
    return _CONSTRUCTION_LABEL.get(construction, construction)


def _hold(family: str, why: str) -> dict:
    return {"admitted": False, "family": family, "status": status_of(family),
            "reason": f"{HOLD_PREFIX}{family} -- {why}"}


def status_of(family: str) -> str:
    f = FAMILIES.get(family)
    return f.status if f is not None else NONE


def hold_family(reason: str) -> str | None:
    """The family a `construction_unsupported:<family>` reason names, else None."""
    text = str(reason or "")
    if not text.startswith(HOLD_PREFIX):
        return None
    return text[len(HOLD_PREFIX):].split(" ", 1)[0] or None


# Every (family, category) pair the router admits, and the test that certifies it (or, for
# the physical-gated family, proves it is refused only for the physical sample). Admitting a
# pair means certifying one; a pair without a proof here is a hole `tests/test_eng_families.py`
# finds by sweeping the router.
_FLAT = f"{PROOF}::test_every_admitted_flat_category_certifies_end_to_end"
PAIR_PROOFS: dict[tuple[str, str], str] = {
    **{(FC.FLAT_PANEL, c): _FLAT for c in ("blanket", "baby", "runner", "placemat", "dishcloth",
                                           "wall_decor", "pet", "scarf")},
    (FC.VESSEL, "basket"): FAMILIES[FC.VESSEL].proof,
    (FC.TAPESTRY, "basket"): FAMILIES[FC.TAPESTRY].proof,
    (FC.PANEL_PAIR, "pillow"): FAMILIES[FC.PANEL_PAIR].proof,
}

# M1 (ENG-FAMILIES review): families admitted only for these categories. A pet bed drafts as
# the vessel but its twin height (11.4 cm) disagrees with the 10 cm its note states, so it is
# deterministically refused at certify (TWIN_DIMENSION_IMPLAUSIBLE). Held until it certifies.
HELD_CATEGORIES: dict[tuple[str, str], str] = {
    (FC.VESSEL, "pet"): ("pet_bed", "a pet bed drafts as the vessel but does not certify: its "
                                    "stated 10 cm differs from the twin's 11.4 cm "
                                    "(TWIN_DIMENSION_IMPLAUSIBLE); held until the sizing is "
                                    "corrected and proven"),
}


def route(*, category: str, title: str, form: str, construction: str, slug: str = "",
          rationale: str = "", premise: str = "") -> dict:
    """Which verified engine drafts this concept, or the named construction hold.

    Returns {"admitted", "family", "status", "reason"}; `reason` is "" when admitted and
    starts with `construction_unsupported:<family>` when held."""
    from ..radar import intake

    declared = declared_family(form, construction)
    if declared is None:
        # Flat rows: the category's template decides, and the form must be what that flat
        # panel honestly is (intake.SUPPORTED_FORMS, unchanged).
        if category not in intake.SUPPORTED_FORMS:
            label = category if category in UNBUILT else FC.FLAT_PANEL
            why = intake.UNSUPPORTED_CATEGORY_WHY.get(
                category, "no `concept_geometry` template row exists for it")
            return _hold(label, f"category {category!r} is not drafted as a flat rows panel: "
                                f"{why}. Flat categories: {sorted(intake.SUPPORTED_FORMS)}")
        if form not in intake.SUPPORTED_FORMS[category]:
            return _hold(FC.FLAT_PANEL, f"form {form!r} is not what a flat rows {category} "
                                        f"panel is (allowed "
                                        f"{list(intake.SUPPORTED_FORMS[category])})")
    elif declared not in FAMILIES:
        why = UNBUILT.get(declared) or intake.CONSTRUCTION_WHY.get(
            construction, "no engine on the radar draft path builds it")
        return _hold(declared, f"declared {construction!r} {form!r}: {why}")

    plan = FC.plan(category=category, title=title, slug=slug, rationale=rationale)
    family = plan["family"]
    if family == FC.REFUSED:
        label = declared or str(hold_family(draft_hold(category, title)))
        return _hold(label, f"the {label} engine refuses this title: {plan['why']}"
                            + (f" (needs {plan['needs']})" if plan.get("needs") else ""))
    if declared is not None and family != declared:
        return _hold(declared, f"the concept declares {construction!r} {form!r} ({declared}) "
                               f"but its category {category!r} and title draft a {family}; "
                               f"drafting it would mislabel the product")
    if declared is None and family not in (FC.FLAT_PANEL, FC.PANEL_PAIR):
        return _hold(family, f"the concept declares flat rows but its category {category!r} "
                             f"and title draft a {family}")
    status = status_of(family)
    if status not in ADMITTED_STATUSES:
        f = FAMILIES.get(family)
        return _hold(family, f"the {family} engine is {status}, not verified end to end"
                             + (f": {f.gaps}" if f is not None else ""))
    if (family, category) in HELD_CATEGORIES:
        label, why = HELD_CATEGORIES[(family, category)]
        return _hold(label, why)
    # H1: the title and the premise must not name what the drafted engine does not build.
    # (Each is read on its own so a word cannot straddle the join.)
    for source, text in (("title", title), ("premise", premise)):
        named = named_feature(text, family)
        if named is not None:
            feature, word = named
            return _hold(feature, f"the {source} names {word!r} ({feature}), which the {family} "
                                  f"engine does not build; drafting it would sell a {word} the "
                                  f"pattern does not make")
    return {"admitted": True, "family": family, "status": status, "reason": ""}


def family_table() -> list[dict]:
    """Every family, its engine, status, proving test, sizes and gaps (for the report)."""
    rows = [{"family": f.key, "engine": f.engine, "status": f.status, "proof": f.proof,
             "sizes": list(f.sizes), "size_source": f.size_source, "gaps": f.gaps}
            for f in FAMILIES.values()]
    rows += [{"family": k, "engine": "", "status": NONE, "proof": "", "sizes": [],
              "size_source": "", "gaps": why} for k, why in UNBUILT.items()]
    return rows


_CATEGORY_LABEL: dict[str, str] = {
    "basket": FC.VESSEL, "pillow": FC.PANEL_PAIR, "wedding": FC.PANEL_PAIR,
    "shawl": FC.TRIANGLE, "stocking": FC.STOCKING, "mosaic_blanket": "mosaic",
}


def draft_hold(category: str | None, title: str | None, construction: str | None = None) -> str:
    """The `construction_unsupported:<family>` label `cir.draft` records when the draft path
    refuses a concept's construction, so the inventory names the same family intake would."""
    import re

    cat = str(category or "")
    folded = FC.fold_title(title)
    if cat in FC.VESSEL_CATEGORIES and FC.tapestry_route(title) is not None:
        family = FC.TAPESTRY
    elif cat in FC.POUCH_CATEGORIES and re.search(r"\bdrawstring\b", folded):
        family = FC.POUCH
    elif cat in FC.TOTE_CATEGORIES and re.search(FC._TOTE_WORDS, folded):
        family = FC.TOTE
    elif cat in FC.PET_CATEGORIES:
        family = FC.VESSEL if re.search(FC._PET_BED_HEAD, folded) else FC.FLAT_PANEL
    elif construction and construction not in (FC.REFUSED, FC.FLAT_PANEL):
        family = construction
    else:
        from ..radar.intake import SUPPORTED_FORMS

        family = _CATEGORY_LABEL.get(cat) or (FC.FLAT_PANEL if cat in SUPPORTED_FORMS or not cat
                                              else cat)
    return f"{HOLD_PREFIX}{family}"
