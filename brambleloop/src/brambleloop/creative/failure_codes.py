"""Shared failure taxonomy for generated product images (one constant, imported, never copied).

Coordinated between W-FLUXAPI (generation, prompts, references) and W-OWNERIMG (candidate gates,
learning records). W-OWNERIMG's `visual.candidate_gates.FAILURE_CATEGORY` names the coarse
category per check (for example `product_truth -> "product_fidelity"`). The codes here are the
fine-grained reasons inside a category: a learning record stores the code, and its category is
`CATEGORY_OF[code]`.

The four product-truth codes come from the owner's first manual FLUX 3 test (reading-nook-cable-
wrap v0.1.0, 2026-10-19, `research/final_build/w4/flux_experiments/2026-10-19_reading_nook_cable_
wrap/RECORD.json`). Each one names the prompt negative or stage rule that now targets it.
"""
from __future__ import annotations

PRODUCT_FIDELITY = "product_fidelity"        # = candidate_gates.FAILURE_CATEGORY["product_truth"]

INVENTED_END_BAND_TREATMENT = "INVENTED_END_BAND_TREATMENT"
INVENTED_EDGING = "INVENTED_EDGING"
WRONG_CRAFT_TEXTURE = "WRONG_CRAFT_TEXTURE"
UNVERIFIABLE_COUNT = "UNVERIFIABLE_COUNT"

PRODUCT_TRUTH_CODES: dict[str, dict] = {
    INVENTED_END_BAND_TREATMENT: {
        "category": PRODUCT_FIDELITY,
        "meaning": "end bands rendered with a treatment the pattern does not have (ribbing, "
                   "stripes, contrast rows)",
        "countered_by": "prompt negative 'end bands exactly as declared' "
                        "(pattern_refs.fabric_facts end_bands)"},
    INVENTED_EDGING: {
        "category": PRODUCT_FIDELITY,
        "meaning": "an edging, border, rib, fringe or trim the pattern does not declare",
        "countered_by": "prompt negative 'no edging unless declared' (fabric_facts edging)"},
    WRONG_CRAFT_TEXTURE: {
        "category": PRODUCT_FIDELITY,
        "meaning": "the fabric reads as another craft or stitch (knitting, rope cables, "
                   "stockinette) instead of the declared crochet stitches",
        "countered_by": "the stitch-texture reference (pattern_refs 'texture') and the "
                        "'crochet, not knitting' negative"},
    UNVERIFIABLE_COUNT: {
        "category": PRODUCT_FIDELITY,
        "meaning": "motif or cable count and spacing cannot be verified (folds, crops, "
                   "occlusion)",
        "countered_by": "product-only flat lay first; its fidelity verdict gates lifestyle "
                        "(image_stages.lifestyle)"},
}

# W-FIDELITY's measured codes (visual.fidelity), folded into the one constant (W4-WRAPTEST).
WRONG_ASPECT_RATIO = "WRONG_ASPECT_RATIO"
OFF_PALETTE_COLOUR = "OFF_PALETTE_COLOUR"
WRONG_COLOUR_LAYOUT = "WRONG_COLOUR_LAYOUT"
WRONG_REPEAT_COUNT = "WRONG_REPEAT_COUNT"
WRONG_PIECE_COUNT = "WRONG_PIECE_COUNT"
OWNER_RECORD_CODES: frozenset[str] = frozenset({INVENTED_END_BAND_TREATMENT, INVENTED_EDGING,
                                                WRONG_CRAFT_TEXTURE, UNVERIFIABLE_COUNT})
MEASURED_CODES: dict[str, dict] = {
    WRONG_ASPECT_RATIO: {
        "category": PRODUCT_FIDELITY,
        "meaning": "the unfolded piece's long/short ratio differs from the digital twin's "
                   "finished centimetres beyond tolerance",
        "countered_by": "the layout reference at true proportion (pattern_refs 'layout')"},
    OFF_PALETTE_COLOUR: {
        "category": PRODUCT_FIDELITY,
        "meaning": "a colour the certified palette does not declare (added or substituted)",
        "countered_by": "prompt negative 'colours not in the certified palette' "
                        "(pattern_refs.PROHIBITED_ADDITIONS)"},
    WRONG_COLOUR_LAYOUT: {
        "category": PRODUCT_FIDELITY,
        "meaning": "colour bands, stripes or colour changes are not where the pattern puts "
                   "them, or a declared colour is missing",
        "countered_by": "prompt negative 'colour changes anywhere except ...' "
                        "(pattern_refs.negatives)"},
    WRONG_REPEAT_COUNT: {
        "category": PRODUCT_FIDELITY,
        "meaning": "a measurable count of motif repeats or cable columns differs from the CIR",
        "countered_by": "prompt negative on cable/motif count (pattern_refs.negatives)"},
    WRONG_PIECE_COUNT: {
        "category": PRODUCT_FIDELITY,
        "meaning": "more or fewer pieces than the CIR makes",
        "countered_by": "prohibited addition 'extra or missing pieces'"},
}
PRODUCT_TRUTH_CODES.update(MEASURED_CODES)

# The owner's wardrobe-diversity fix (2026-10-19). FLUX carried the canonical references'
# beige trousers and ivory top into lifestyle frames, and outfits differed only by the shirt.
WARDROBE = "wardrobe"
WARDROBE_REPETITION = "WARDROBE_REPETITION"
REFERENCE_CLOTHING_CARRYOVER = "REFERENCE_CLOTHING_CARRYOVER"

WARDROBE_CODES: dict[str, dict] = {
    WARDROBE_REPETITION: {
        "category": WARDROBE,
        "meaning": "the complete outfit is too similar to another listing's (or to the "
                   "reference clothing): visual.wardrobe.similarity >= MAX_SIMILARITY",
        "countered_by": "re-pick the outfit (visual.styling, the old one excluded) and "
                        "regenerate"},
    REFERENCE_CLOTHING_CARRYOVER: {
        "category": WARDROBE,
        "meaning": "the image shows clothing from the canonical reference images (beige "
                   "trousers, ivory/cream top, tan sandals) instead of the reserved outfit",
        "countered_by": "the replace-all-clothing identity prompt and the reference-clothing "
                        "negatives, strengthened on repair"},
}

# Product Truth codes (what a fidelity verdict may carry; `image_stages.fidelity_verdict`).
CATEGORY_OF: dict[str, str] = {code: row["category"] for code, row in
                               PRODUCT_TRUTH_CODES.items()}
ALL_CODES: frozenset[str] = frozenset(CATEGORY_OF)
# Wardrobe codes (outfit checks; never on a product-only fidelity verdict) and the union every
# learning record and the repair router read.
WARDROBE_CATEGORY_OF: dict[str, str] = {code: row["category"] for code, row in
                                        WARDROBE_CODES.items()}
WARDROBE_ALL_CODES: frozenset[str] = frozenset(WARDROBE_CATEGORY_OF)
EVERY_CODE: frozenset[str] = ALL_CODES | WARDROBE_ALL_CODES
