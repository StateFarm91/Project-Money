# FIRST-LISTING — eng/first-listing (2026-11-22)

Branch `eng/first-listing`, from `origin/claude/w6-release-19h17` (e1ff7be). **Not merged, not deployed. No PR.**
Production is unchanged. I read no production rows; the only production input is the 00:00Z evidence in the brief.
`ops/rebuild_graph.py` and `_targeted_rebuild` are untouched.

## Which release

**Recommended first listing: `hexagon-coaster-set`** (fallback: `housewarming-key-basket`). The reasons:
- It is a non-baby product, so it has no child-facing risk.
- It is flat, not a vessel, so it needs no side-view anchor.
- It already has a manual listing package (`research/final_build/w4/manual_listings/`).
- It is the CIR the rollback fix was reproduced on.

**Every fix below is systemic**, so it helps all eight Launch-0 releases. None of them is closer to publishable on
`attributes` or `category`: all share one Etsy node, *Patterns & Blueprints*. **Unverified:** production evidence was
given only for cloudline-baby-blanket@1.2.0. Read the other releases' `first_listing_readiness` rows after the next
deploy to confirm the choice.

## Section by section (cloudline-baby-blanket@1.2.0)

| Section | Root cause found | Fix on this branch | After a deploy |
|---|---|---|---|
| **search: attributes** | Code defect, and it hit **every** Launch-0 release. Etsy returns custom-variation properties (Size, Dimensions, Fabric, Width, …) with `supports_attributes: false`. `category._decide` read each of them as UNDECIDED, so the schema was never `complete`. The test fixture set every flag to true, which is why no test caught it. | `commerce/category.py` `_variation_only`. Only Etsy's explicit boolean `False` sets a property aside. A required property, a missing or non-boolean flag, and an attribute-capable property with no rule all still refuse. | The stored search certificate changes only when `listing.seo` re-runs for the release. A chain rebuild does that; there is no automatic trigger for an Etsy-schema reading. |
| **search: hero** | Downstream of listing_set: hero needs frame 1 `may_export`. | None needed. | Passes once listing_set passes. |
| **parity: hero unjudged** | Code defect. The disclosed hero's blind review ran only when the render set was first *made*. A reused set (same version and CIR fingerprint) returned early. A set first built while `image_vision` was closed, or whose review call failed, was therefore never described, and HERO stayed unjudged for the life of the release. Approving openai-vision changed nothing. | `runtime/release.py` `_review_reused_hero`: the next `assets.build` reviews a reused hero that has no successful review of those exact bytes. A failed review stays unjudged, and bytes already described are never paid for again. | Needs `image_vision` open and a funded vision route. See owner item 2. |
| **parity: competitive_blind_review FAIL** | Not a defect. With the 3-frame disclosed set the product is behind on gallery depth and shot variety, and on video if most benchmarks have video. | None. The gate is not weakened. | A 7-frame FLUX gallery fixes depth and variety. Video alone (1 behind) is under `MATERIAL_BEHIND=2`. |
| **parity: frame_review_done false** | Not a defect. `assets.build` → `_review_frames` (#61) runs on every build, but needs `image_vision` open and a working describer. | None. | Same as parity hero. |
| **listing_set: certificate invalid, 0/3 may export** | The 3 frames are the disclosed render set: no FLUX gallery selection (`images.generated_gallery_selected`) exists. In the disclosed path `may_export` is set-wide, so any one reason blocks all 3. **Stall:** the listing is `withdrawn`, so `products.lifecycle.derive` reads the product RETIRED, and `image_production.admit_for_sale` refuses RETIRED. The paid FLUX run is therefore never admitted. | Not changed here. A `withdrawn` listing goes back to `draft` only when `listing.seo` re-drafts it, which is the chain re-run that incident 380's lane owns. The other route, reading "withdrawn and never on Etsy" as not RETIRED, would change spend admission broadly. I left it for review rather than slip it in. | Once the chain re-drafts the listing, admission runs, the paid FLUX gallery runs within the approved CA$2.50/gallery ceiling, `gallery_persist.certify_gallery` certifies 7 frames, and the certificate becomes valid. |
| **certification: withheld** | Granted, release matching, withheld. The evidence emitted only a boolean, so the cause was not measurable from outside. Likely kind: `competitive_standard` (#220). It is written by `for_publish` → `withholding.reconcile`, and the bars come from benchmark scans (`gallery_images` = highest benchmark gallery size, `video_in_gallery` = 1 once two sellers show video). Both bars are only ever raised, never lowered. | `ops/publication_authority._certification` and `production_evidence._section_diagnostics` now emit `withheld_kinds`, using the fixed vocabulary `withholding.KINDS`. They also emit `competitive_now`: each bar, our reading and the verdict, as numbers only. The gate is unchanged: withheld is still FAIL. | The next evidence reading names the kind. If it is `video_in_gallery` (no video path exists) or a `gallery_images` bar above 7, it can never pass without an owner decision. See owner item 3. |
| **rollback: deliverables_restorable** | Code defect. `deliverables.secure_release` (the daily keeper) secured the newest build of any release. `rollback.rehearse` checks the build bound to the release on file. After a rebuild without a release, or a re-certification, the keeper kept the wrong PDFs. Railway's disk is wiped on every redeploy, so the drill found the bound PDFs "neither on disk nor held in Postgres". Reproduced on the real coaster CIR. | `commerce/deliverables.py`: the keeper secures exactly the drill's set, the release-bound PDFs (re-rendered only if byte-identical) plus the valid certificate's frames. | Passes on the next daily `launch.readiness` for a release whose bound build re-renders byte-identically. A set that cannot be reproduced still FAILs. |
| disclosure, policy | PASS | — | — |

UNKNOWN is never PASS anywhere above, and no gate was weakened. Copy rules are unchanged:
`sample_photo.copy_problems` still refuses any claim of a made, tested or hand-made sample, and FLUX frames carry no
visible label (D-OWNER-PUBLISH-WITH-RENDERS).

## Tests

All new suites fail on the old code where noted and pass with the fix:
- `tests/test_first_listing_fix.py` (4): the withheld kinds and competitive bars are named, out-of-vocabulary text is
  dropped, and the gate still FAILs.
- `tests/test_search_attributes_variation_properties.py` (6): all six Launch-0 categories. Fails on the old code.
- `tests/test_hero_review_reused_set.py` (2): fails without the fix.
- `tests/test_rollback_restore_set.py` (3): the main case fails on the old code with the production symptom
  `missing_on_disk: [6eb2a74f6c71, e9a96104988b]`.

Touched and overlap suites were run with
`PY=python3 JOBS=3 SUITE_REGISTRY=0 SUITES="..." bash run_tests.sh`, including `test_vacuity.py`. Results are in the
final hand-back. This is a targeted run, not a full-suite certification.

## OWNER ACTION REQUIRED

1. **Signed first-publication approval for the chosen release.** Mission Control → Approvals →
   `publication.approve` for `hexagon-coaster-set@<certified version>`, after the packet shows every gated section
   PASS. It needs a passphrase and TOTP step-up.
   - **Why:** the signed publication grant and the owner's separate publishing approval are unchanged by
     D-OWNER-PUBLISH-WITH-RENDERS. Activation (`store.activate`) is a second grant.
   - **Cost:** CA$0 to approve. The Etsy listing fee is about US$0.20, inside the existing cap.
   - **Time:** about 3 minutes per grant.
   - **If it waits:** no listing goes live, even once every gate passes.
2. **Confirm the vision route is funded for hero and frame review.** On Railway, check `BRAMBLELOOP_MODEL_ROUTES`.
   - **Why:** `inspect.describe_image` uses the `asset_inspection` route, which defaults to the Anthropic vendor unless
     the route says `asset_inspection=openai`. openai-vision is wired automatically only as the identity second judge.
     If the default vendor is unfunded or not approved, hero and frame review fail even with the fix. Setting the
     route to openai uses the already-approved `openai-vision:vision` (CA$1/gallery, CA$2/day). It is a config change
     inside an existing approval, not new spend authority.
   - **Cost:** inside the approved ceilings.
   - **Time:** about 2 minutes.
   - **If it waits:** parity HERO and frame_review stay unjudged.
3. **Only if the next evidence shows `withheld_kinds: ["competitive_standard"]` with `video_in_gallery` below, or a
   `gallery_images` bar above 7:** a ruling on that competitive bar.
   - **Why:** the system raises bars and never lowers them by design. No video production path exists, so that bar
     cannot be met in code. The ruling is either "listings ship without video" (a decision about this shop) or
     "commission video".
   - **Cost:** CA$0 for the ruling.
   - **Time:** about 5 minutes.
   - **If it waits:** certification stays withheld for every release.
4. **Approve the deploy of this branch** (per-SHA, after review) once incident 380's lane has landed.
   - **Cost:** CA$0.
   - **Time:** about 2 minutes.
   - **If it waits:** none of the fixes reach Railway.

Nothing here needs KYC, banking or a physical action.
