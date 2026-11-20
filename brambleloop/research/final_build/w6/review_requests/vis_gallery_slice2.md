# [ENG-VIS-GALLERY] slice 2 — review request

Branch `eng/vis-gallery`, on top of slice 1 (d9f392f). It is not integrated and not deployed.

## What changed
| Area | File | Change |
|---|---|---|
| Recovery first | `visual/gallery_recovery.py` (new) | Before a slot's first generation, prior `image_candidates` of the same product, version, release, listing and role are re-judged under the route (`candidate_gates.evaluate` with `route`). Selection rules: paid first, then newest; at most 3 per slot; Laura and outfit must match; no experiment images; no negative decisions; the bytes are re-hashed. Only a technical PASS is recovered. It is recorded as `method="recovered"` with `cost_cad=0.0`, and `_recovered` names the source candidate, its run and its original cost. A retried job reuses the recovered row (`already`) and never buys a new image. Each attempt is noted in the run's `_recovery`. This does not overlap `publish.motif_backlog` (eng/motif-backlog), which covers owned and model photography renders filed in the audit log. |
| Run hook | `visual/image_production.py` | `gen_roles` tries `already`, then `recover`, then `_generate`, on route runs only (no recovery inside repair rounds). On a route run, `owner_card` calls `gallery_persist.certify_gallery` (`_certify_route`), so certification is automatic and the owner's look is never asked. |
| Trigger | `runtime/release.py` | `assets.build` also triggers the FLUX-gallery run, beside the campaign run. Both are shadow-safe: a closed `image_generation` gate blocks them before any paid call. |
| CIR references | `visual/gallery_persist.py` | New frame gate `cir_references`. The frame must have been conditioned on exactly the release's deterministic CIR reference renders (`creative.pattern_refs`: layout, texture, detail, rules), in order, as the run prepared them. Otherwise it reads FAIL, with ENG-VIS-FLUX as owner. |

## Proof
- `test_vis_gallery_e2e::test_6`: on the certified chain, the FLUX run recovers `lifestyle` and `size` from the campaign run's images (same sha256, cost 0, motif re-judged), and buys nothing for them. `colour_context` (Laura differs) is generated instead.
- `test_vis_gallery_gates::test_frame_matrix_requires_the_release_cir_references_in_order`.
- Mutants: `cir references not checked` and `recovery ignores Laura` (e2e) are both killed. See slice 3.

## Notes
- Recovery re-judging uses the production judges, through their reserved vision calls. No image-provider call is made.
- A gallery-run attempt that is recovered still counts as an attempt (`_attempts` counts rows). This is conservative.
