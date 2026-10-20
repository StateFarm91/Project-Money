# The owner's manual FLUX 3 method compared with the code (W-VISNEXT, 2026-10-20)

Every manual step is mapped to the file and function that does it. For each step this note
says what is identical, what differs and why, and what stays untested until a live run.
Nothing below has run against a paid provider. The keys are not present in this environment.

## Baseline: six references in one shot (the method to reproduce first)

| Manual step | Code | Identical | Differs (why) | Untested until live |
|---|---|---|---|---|
| Send the 3 canonical Laura references first | `creative/image_stages.py:six_reference_lifestyle` → `laura_references` | Same three files, checked by byte sha256 (a42aeac7, afe6191f, f32bac68), always positions 1–3 | Code refuses any substitute or any reordering; the manual dashboard does not check | Whether the provider honours the order |
| Add the 3 product references (layout, stitch structure, construction rules) | `six_reference_lifestyle` with `research/.../experiment_wrap/baseline_six.py:owner_references` (owner's exact files, checked against RECORD.json) or `auto_references` (`pattern_refs`) | `owner` mode sends the owner's committed bytes (3f737a08, 10d013b8, 3638b3a5) | `auto` mode sends the generated equivalents, so the two can be compared | How the auto references compare with the owner's, visually |
| A detailed prompt | `creative/flux_prompt.build` (identity v2, clothing replaced, product rules, negatives) | Same prompt sections the owner's prompt carries | The prompt is generated, versioned and hashed. The stitch-structure image stands in for both "texture" and "detail" (an alias), because the owner sends one image for both | The visible prompt prefix is the only part of the owner's prompt on record (RECORD.json: prompt MISSING) |
| Save the result | `baseline_six.run_baseline` | Image, ordered reference sha256 values, prompt text, receipt and cost, per attempt | Labelled EXPERIMENT/UNCERTIFIED; never publishable | The real receipt fields and cost |
| Judge the result | `baseline_six.default_verifier` → `visual/fidelity.verify_lifestyle` + `visual/vision_judges.Adapters` | The owner judged by eye | Code judges with blind, code-compared vision questions. The anchor check reads UNKNOWN because this method has no flat lay | Whether the vision judges agree with the owner's eye |
| Try again after a defect | `baseline_six.classify` + `repair_routes.route` | A targeted fix such as "no edging" | At most 2 retries in the whole baseline, only for routed prompt-negative codes; UNKNOWN is never retried | Whether the negatives fix the defect |

Run it with one line, once the keys are in the environment:

```
BRAMBLELOOP_IMAGE_KEY_BFL=… ANTHROPIC_API_KEY=… .venv/bin/python research/final_build/w4/experiment_wrap/run.py --live --baseline-six-ref
```

That sends the owner's files first, then the auto references. The dry run (`--dry-run --baseline-six-ref`) is proven in
`tests/test_w4_baseline_six.py`.

## The production path: the same seven-reference recipe as a controlled experiment

`experiments/controlled.py` reproduces the frozen seven-reference plan (`exp-2026-10-20-wrap-7ref`): the six above plus the
crochet-texture reference.

- It runs from the Command Center behind the owner session and step-up (`EXPERIMENTS.md`).
- The references and the frozen prompt are verified by sha256 before any spend.
- There are two caps: CA$5 for generation and CA$1 for vision.
- The output is labelled EXPERIMENT and can never publish.

## The staged method, stages A to D (the owner's later sequence)

| Stage | Manual | Code today | Status |
|---|---|---|---|
| A. Laura identity anchor in the listing's outfit | The 3 canonical references and a detailed identity prompt make an identity candidate; one proportion pass | No dedicated stage. The canonical 3 lead every Laura call (`campaign_references`); identity and body checks are `vision_judges.identity_check` / `body_check`. An UNKNOWN goes to review and is never passed | **Not built:** the per-listing identity-anchor image and its reuse as a supplementary reference. The supplementary slot exists (`outfit` / `supplementary` in `campaign_references`) |
| B. Product: 3 pattern PNGs, then a flat lay | `pattern_refs` give layout, texture, detail and rules; then a flat lay | `image_stages.product_only`; `visual/fidelity.verify_anchor` gates it (stage 4 of `image_production`) | Built. The flat lay is fidelity-gated. A 1K flat lay is not proven against the verifier, so it is kept at 2K |
| C. Lifestyle: anchor, face, flat lay, plus the canonical 3 | References are the Laura candidate, the canonical face and the flat lay; the canonical 3 always come first | `image_stages.lifestyle`: the canonical 3, the product 4, `product_candidate` (the flat lay), then `outfit` (approved outfit reference, now sent: `flux3_generator._outfit_reference`), within 10 | Built, except for the stage-A identity anchor (see A) |
| D. Variants: edit the accepted lifestyle image | Edit the accepted image (outfit or pose) | `image_stages.variant` edits a base candidate (`images[]`), with the outfit wording carried | Built at stage level. **Not wired:** the orchestrator does not yet pick "the accepted lifestyle frame" as the base |
| Preserve intermediates | Kept on the owner's machine | Every candidate is a stored artifact with prompt, references, receipt and cost (`image_production.record_candidate`); a restart re-verifies stored bytes rather than regenerating (`restart`/`reverify`) | Built |
| Gating: a reviewer is unavailable | Owner judged | The vision gate closed or unfunded gives UNKNOWN; the run stops at that gate and completed images are kept | Built |

## Cost: 1K versus 2K

- The owner used 1K by hand.
- Listing frames stay at 2K. Etsy needs ≥2000 px, and nothing is upscaled.
- Intermediate-only frames (an identity anchor, a flat lay) could use 1K only if the fidelity verifier is proven at that size. That has not been tested, so 2K is kept.
