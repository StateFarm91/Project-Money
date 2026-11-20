# W-VISNEXT2: the staged FLUX method, the Cloudline acceptance harness and the 1K check

Branch `claude/w4-VISNEXT2`. Built on `0beb522` (W-VISNEXT final), then INTEG4 merged in.
Everything below has been proven on stub providers only. No real image or vision call has
been made, no money has been spent, and nothing has been published.

## 1. Stage A: Laura's identity anchor in the reserved outfit

- **New stage.** `identity_anchor` runs in `visual.image_production`, between
  `reserve_outfit` and `lifestyle_generation`.
- **What it makes.** One 1024x1024 *intermediate* image: Laura in the outfit reserved for
  this run. It is built by `creative.flux_prompt.build_identity_anchor` and
  `image_stages.identity_anchor`.
  - The canonical three Laura references always go first.
  - The image is stored with its sha256 and fingerprinted.
  - It is never a gallery frame, never publishable, and never subject to the listing
    image-quality floor.
- **Verdict.** `identity_anchor_verdict` checks identity, body proportions, outfit
  (distinctness and consistency), anatomy, realism and the release binding.
  - **PASS:** the anchor is reused as the fourth identity reference, after the canonical
    three, for every lifestyle and variant frame in the run.
  - **Body-proportion drift:** exactly one correction pass (`PROPORTION_CORRECTION`). If it
    still FAILs, the stage blocks and no further attempts are made.
  - **UNKNOWN:** an identity review card goes to the owner, the run holds at this gate, and
    every image is kept.
- **Owner review.** `resolve_identity_anchor_review` takes one of three answers:
  - `confirmed_same_person`: the anchor may be used as identity context, then the run
    restarts. It never turns any verdict into PASS.
  - `not_laura`: stage A ends.
  - `inconclusive`: the anchor stays held.
- **When stage A is skipped:**
  - there is no Laura in the shot plan;
  - the run is a controlled experiment whose frozen plan has no stage A;
  - the generator does not support the staged method (`ACCEPTS_STAGED_METHOD`).

## 2. Stage D: the variant edits the accepted lifestyle frame

- **Edit base.** `_accepted_lifestyle` picks the run's best LIFESTYLE frame. The frame must
  have no FAILed check and must not have been rejected by the owner.
- **The edit.** `Flux3Generator` passes that frame as the variant's edit base
  (`VARIANT_OF_ROLE`), using the same reserved outfit reference.
- **Judging.** The variant is judged on its own; the edit base is only a generation input.
- **No base, no variant.** If no lifestyle frame is accepted, stage D does not run.

## 3. Cloudline one-command acceptance harness

- **Command:** `research/final_build/w4/cloudline_acceptance/run.py`
  - `--dry-run`: stub provider and stub judges, no network.
  - `--live`: refuses before opening anything if either key is missing from the environment.
- **Definition:** `experiments/definitions/exp-2026-10-21-cloudline-acceptance`. It is a
  pipeline definition with the Cloudline 1.2.0 release hash and the frozen pattern-reference
  and prompt-section fingerprints.
- **Shared cap:** CA$5 for generation, shared with `exp-2026-10-20-wrap-7ref` through
  `shares_cap_with`. Spend is summed across the group, so it is counted once.
- **The 7 steps:**
  1. Certification through the real queue, plus the certified US/UK PDF hashes.
  2. The references are verified against their frozen fingerprints.
  3. FLUX product-only flat lay at 2k.
  4. Fidelity check.
  5. Laura: stage A anchor, then lifestyle, then the stage D variant.
  6. Gallery assembly.
  7. The approval card, carrying the EXPERIMENT banner.
- **Isolation:** the run uses a namespaced run key (`#exp<n>`), so it never mixes with
  ordinary production runs.
- **Dry run, re-proven after the INTEG4 merge:**
  - all 12 stages ran;
  - final state `ready_for_owner_review`;
  - 5 generation calls on the stub;
  - banner "EXPERIMENT — NOT FOR PUBLICATION";
  - publication `not_available`.

## 4. Fidelity at 1K: disproven, so the flat lay stays at 2K

- **Measurement:** the 1K check was run against the corpus of known-good and known-defect
  images.
  - Every known defect was still caught at 1K.
  - 2 of 18 correct images were falsely FAILed: the wrap under JPEG q60, and the coasters
    under a 2 px blur.
- **Decision:** `visual.fidelity.ANCHOR_1K_QUALIFIED = False`.
  - The product flat lay stays at 2048x2048.
  - Only the stage-A identity anchor uses 1K, and the fidelity verifier never judges it.
- **What the risk is:** at 1K the failure is a false FAIL (an extra paid regeneration), not a
  false PASS.

## Tests

`tests/test_w4_visnext2.py` pins the 1K disproof, stage A (PASS, the single correction, and
UNKNOWN going to the owner), stage D, the generator ordering, the harness dry run, the shared
cap, refusal on drift, and the live run's refusal without keys.
