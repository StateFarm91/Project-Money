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

CATEGORY_OF: dict[str, str] = {code: row["category"] for code, row in
                               PRODUCT_TRUTH_CODES.items()}
ALL_CODES: frozenset[str] = frozenset(CATEGORY_OF)
