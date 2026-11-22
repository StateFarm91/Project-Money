# READY-FIXTURE — a genuinely READY release for the draft/activation suites

- **Branch:** `eng/ready-fixture` (from `origin/claude/record-candidate-2` @ 8feb010)
- **Fixture:** `brambleloop/tests/ready_release_fixture.py` (`ready_chain()`, `info()`,
  `assert_taxonomy_recorded()`)
- **Suites restored:** `tests/test_etsy_publish_e2e.py` (package → draft → rollback → adoption →
  refusals) and the draft → activation leg of `tests/test_first_listing_doors.py`.
- **Date:** 2026-11-22 (UTC)

## Problem

Since batch 19f (D-OWNER-SALE-PIPELINE, D-OWNER-GALLERY-COMPLETE), `store.publish` publishes only
a release that is READY for sale. That means a seven-frame certified gallery, both premium PDFs
certified for the release, and a READY listing package. No fixture built such a release, so
`test_etsy_publish_e2e` failed at the first draft (`KeyError: 'etsy_listing_id'`, confirmed on a
clean checkout of the base). `test_first_listing_doors` returned early at the refusal.

## What the fixture does (in order)

1. `test_search_hero_publish._chain()`: `gate.certify` → `assets.build` → `listing.seo` through
   the real handlers, for `cloudline-baby-blanket@1.2.0`.
2. The rehearsal's own `record_simulated_taxonomy` step: the real `listing.taxonomy_refresh` on
   FakeEtsy's seller taxonomy, then the release's `listing.seo`. It runs before the gallery,
   which is the production order (see finding F1).
3. A real `listing.package`, so that the for-sale admission has a package to read.
4. The real for-sale admission, `image_production.sale_admission`, asserted `admitted`. Unlike
   `test_vis_gallery_e2e.run_gallery`, this fixture does not double it.
5. The generated-gallery route: every `image_production` stage on the durable JobQueue.
6. Laura's per-gallery publication approval, recorded through the owner's real path
   (`laura_approval.raise_card`, then `decide` with the owner actor and the step-up asserted).
   That path re-certifies through `gallery_persist.certify_gallery` →
   `release_gates.generated_listing_set`. The fixture does not touch the global
   `canonical.PUBLICATION_APPROVED` override.
7. The result is a valid listing-set certificate with 7 frames for exactly this release.
8. The real `listing.package`, then the real `launch.plan` and every `sale.pipeline` stage:
   admission → gallery → pdf_build → pdf_certify → attach → ready.
   - The premium US and UK editions are rendered in the owner's master template with the
     certified frames.
   - They are certified by `publish.pdf_standard.check` on the stored bytes.
   - The real packager re-assembles the package.
   - `ready_for_sale` is asserted True, and the run reads `READY`.
9. `launch.plan`'s own `store.publish` runs in SHADOW, as the production worker would run it.
   It is refused, nothing is published, and nothing is left pending.

The built database is cached once per process. Each call to `ready_chain()` returns a fresh
copy.

## What is faked (only the external providers, at their seams)

| Provider | Double | Seam |
|---|---|---|
| BFL / FLUX 3 image generation | `test_vis_gallery_e2e.GalleryGenerator`: the **real** `creative.flux3_generator` request builder on its `StubRenderer` (no network, no spend). It returns deterministic listing-size synthetic flat lays of the certified CIR. | `image_production.run_stage(generator=...)`, the slot the worker fills from `resolve_generator` |
| OpenAI vision transport | `test_v6_gallery_e2e.StubVision`: one fixed blind reading per task, consistent with the CIR | the `image_vision` judge transport passed to `candidate_gates.RealJudges(vision=...)` |
| Vision person judges (identity, anatomy, realism, body, outfit) | `test_w4_ownerimg.StubJudges`, each reading labelled `test_double` | `image_production.run_stage(judges=...)` |
| Motif-fidelity vision transport | `test_vis_gallery_e2e._motif_judger` | `candidate_gates.motif_reading(judger=...)`. The verdict itself comes from the real `publish.motif_fidelity.judge`. |
| Etsy HTTP | `tests/fake_etsy.FakeEtsy` (loopback) | `EtsyClient.BASE` / credentials, as before |
| Approved room reference set | `test_v6_gallery_e2e._room_manifest` | `room_references.MANIFEST`, swapped only while the gallery runs |

The real gate code runs on these fake judgements. That covers:
- `visual.fidelity.verify_anchor` and `verify_lifestyle`;
- `candidate_gates.evaluate`;
- the quality floor, campaign consistency and naturalism;
- `gallery_persist.certify_gallery`;
- `release_gates.generated_listing_set` and `release_gates.for_publish`;
- `publish.pdf_standard`, `sale_pipeline.ready_for_sale` and the store.publish gates.

## Disclosed: gates and rules that are still held or doubled

These are not hidden. Each one was held the same way before this change.

1. **#75 listing parity (`pipeline._listing_parity`), the #126 search grid and the Launch-0
   scope gate** are held, as both suites and `test_rehearsal_past_shadow_success._held_gates`
   already held them. Each has its own tests.
   - #75 cannot pass on the merits offline. `parity.assess` needs structural product truth from
     a protected-product or sample proof, and a benchmark blind review. No vision answer can
     supply either.
   - So "fake vision judgements PASS the parity gate" is not achieved for #75. That gate is
     still held.
2. **V1's end-band rule on in-scene frames** stays doubled inside the vision double. The double
   is `test_vis_gallery_e2e.GalleryJudges.product_truth`, reused unchanged.
   - The rule: an anchor's band measurement is never promoted into a scene frame, so
     `craft_texture` is UNKNOWN on a banded blanket's scene frames.
   - The double turns that one dimension into PASS, and only when it is the sole gap.
   - Every other dimension of that fidelity verdict is real.
3. **The sample-photo gate**: the code here grants the owner's D-OWNER-PUBLISH-WITH-RENDERS
   waiver (`sample_photo.publish_with_renders()` is True).
   - The doors test keeps every original SAMPLE_PHOTO_REQUIRED assertion, under `if not waived`.
   - With the waiver, it asserts that the read-back carries no release-gate reason and that the
     first owner grant activates.
   - `test_vis_gallery_e2e` test_3 and test_7a branch the same way.

## Changes to the restored suites (no assertion removed or loosened)

- **Both suites** use `RF.ready_chain(...)` in place of `SH._chain()`. They read back the taxonomy
  step that the fixture recorded (`RF.assert_taxonomy_recorded`: category CHOSEN, search
  certificate PASS). They no longer re-run it after the gallery (F1).
- **test_first_listing_doors:** the 19f early `return` at the refusal is removed, so the whole
  draft → read-back → doors → activation leg runs again. The sample-photo branch is described
  above.
- **test_etsy_publish_e2e:**
  - `_certified_pdfs` now returns the editions certified for sale: the premium US/UK hashes
    whose `pdf_certificates` PASS. A READY release uploads these. The helper also asserts that
    each certificate is bound to the `assets.build` edition of the same terminology, and that
    the stored bytes re-hash to it. The "what arrived is exactly the certified bytes" assertion
    is unchanged.
  - After the rollback, the package fence correctly invalidates the reviewed package ("listing
    or certified release changed after package review"). The real `listing.package` handler
    re-assembles it, and `ready_for_sale` is asserted True before the adoption grant.
  - One extra assertion message (`"etsy_listing_id" in job["outputs"]`) was added.

## Findings (production code, not changed here; for the owning lanes)

- **F1: a `listing.seo` re-run after a certified generated gallery is refused.**
  - Cause: `runtime.release._stored_frames` reads every `ListingAsset` row for the release,
    including the generated-gallery frames that `gallery_persist` files. It passes them to
    `platform_policy.release_assets` as *deterministic* frames, and `FRAME_ROLE` has no
    mapping for `colour_context`.
  - Result: `POLICY_CLASSIFICATION: listing frame role 'colour_context' has no asset-role
    mapping`, and the search certificate drops from PASS to PENDING/REFUSED.
  - Impact: any later taxonomy refresh or SEO re-run on a READY release blocks its
    publication.
  - Mapping the role would hide the misclassification, because generated frames would be
    claimed as deterministic renders. The likely fix is to route generated-gallery assets
    through `generated` or `disclosed`. That is a policy-gate change, so it is left to its
    owner.
  - Repro: build `ready_chain()`, then run `listing.seo` with the original seo job's inputs.
- **F2 (worth checking, not verified):** `launch.rollback.withdraw_draft` rewrites the local
  listing, which invalidates the package, and `withdraw_draft` itself enqueues no
  `listing.package` (checked by grep). A rolled-back READY release stays not-READY until
  something re-packages it. I did not check whether a sweep does that elsewhere. The suite
  re-packages explicitly.

## Suites run

The command:

```
cd brambleloop && JOBS=4 SUITE_REGISTRY=0 SUITES="tests/test_etsy_publish_e2e.py \
  tests/test_first_listing_doors.py tests/test_vacuity.py tests/test_sale_pipeline.py \
  tests/test_sale_pipeline_e2e.py tests/test_sale_preimage.py tests/test_search_hero_publish.py \
  tests/test_rehearsal_past_shadow_success.py tests/test_vis_gallery_e2e.py \
  tests/test_owner_gallery_complete.py tests/test_image_bf.py" bash run_tests.sh
```

The run was on SHA 69e362a with the tree clean at start, using a venv installed from
`requirements.lock` and `requirements-test.lock`. It took 910 s and finished at
2026-11-22T12:00:55Z.

**TOTAL PASSING: 93; suites failing: 1; environment failures: 0.** Run record:
`brambleloop/artifacts/suite_runs/20261122T114545Z-2885.json`.

**Passed (10 suites):**
- test_etsy_publish_e2e (restored: draft, rollback, adoption, refusals)
- test_first_listing_doors (restored: draft through activation)
- test_vacuity
- test_sale_pipeline
- test_sale_pipeline_e2e
- test_sale_preimage
- test_search_hero_publish
- test_vis_gallery_e2e
- test_owner_gallery_complete
- test_image_bf

**Failed (1 suite, already failing before this change):** test_rehearsal_past_shadow_success,
in `test_the_past_shadow_publish_pass_path_creates_exactly_one_draft_under_the_grant`.
- I re-ran it on a clean worktree of `origin/claude/record-candidate-2`, and it fails the same
  way there: `store.publish[past-shadow]` makes 0 creates.
- The cause is the same 19f one. That suite still builds on the non-READY `SH._chain()`, and this
  branch does not modify it.
- The likely next step is to move it onto `RF.ready_chain()`. Because `reh.run_past_shadow`
  re-runs the taxonomy and `listing.seo`, it will need F1 fixed, or the same
  production-order treatment the two restored suites got.
