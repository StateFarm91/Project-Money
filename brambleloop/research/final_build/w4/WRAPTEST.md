# W4-WRAPTEST: Reading Nook Cable Wrap experiment, one command, proven in dry run

**EXPERIMENT — UNCERTIFIED — NOT FOR PUBLICATION**

Branch `claude/w4-WRAPTEST` (from `origin/claude/w4-VISAUTO`). Both finished branches are merged in,
conflicts resolved in their favour: `origin/claude/w4-VISAUTO` @d767208 and
`origin/claude/w4-FIDELITY` @298e3156. This branch now owns their files.
Production is unchanged (1b21e81, SHADOW). No paid call was made, no key was read, nothing
was deployed or published, and no credential was changed.

## The commands

From `brambleloop/`:

```sh
# dry run (default): stub provider, no network, no key, no spend
.venv/bin/python research/final_build/w4/experiment_wrap/run.py --dry-run

# the paid run (waits on the owner's credential decision)
BRAMBLELOOP_IMAGE_KEY_BFL=... ANTHROPIC_API_KEY=... \
  .venv/bin/python research/final_build/w4/experiment_wrap/run.py --live
```

`--live` reads both keys from the environment only. If either is missing it prints
`REFUSED (no spend, nothing opened)` and exits with code 2 before it creates anything.
Output goes to `research/final_build/w4/experiment_wrap/out/{dry_run,live}/`, or to `--out DIR`.
The approval package is `<out>/approval_package/index.html`.

## 1. Certification (real chain, scratch SHADOW DB)

`gate.certify` is enqueued on the durable `JobQueue` (agent `quality_director`) and run by
`runtime.worker.Worker` against a `Database(..., scratch=True)`. The result:

* **REFUSED**, with the single reason `ERROR UNCALIBRATED_PRIMITIVE: ['cable2x2'] are new
  primitives no sample has calibrated ...`, as expected;
* content hash `335c61ce56587a46cf60db33b3aeb6dbdab0d5404b4c4ab4e7a7453571753a24`, which equals
  `pattern_refs.release_hash_of(cir)`;
* the uncertified US/UK PDFs are rendered twice each with `released_on=2026-10-19` and are
  byte-identical; their hashes are bound into the experiment.

No certificate is written, asserted or fabricated. No `PatternVersion` is created or marked
certified.

**The orchestrator refuses uncertified releases.** Without EXPERIMENT mode,
`image_production.run_stage` stops at `awaiting_certified_pattern`. Without a certified
release, `Flux3Generator`'s default loader raises `GeneratorRefused`. Both are tested.

## 2. EXPERIMENT mode (`src/brambleloop/visual/experiment.py`)

| Guarantee | How | Test |
|---|---|---|
| runs only with `--experiment` semantics and a scratch DB | `inputs["experiment"]` routes `run_stage` through `experiment.context_for`, which requires `db.scratch` (a new attribute set only by `Database(scratch=True)`), an opened experiment for this exact release, and an in-process install. Any of these missing is refused, never silently defaulted. | `test_experiment_is_scratch_only_and_content_bound`, `test_orchestrator_refuses_the_uncertified_release_without_experiment_mode` |
| bound to exact content | `open_experiment` takes the refused certificate's own reading. It refuses a granted certificate, a different content hash, missing US/UK PDF hashes, no reasons, or a budget over CA$5. | same |
| stamped everywhere | `LABEL` is on the binding, every candidate check, the stage records, stored artifacts (`keep` note), the card, the Command Center title, package file names and burnt-in banners. | `test_experiment_candidates_are_never_publishable`, dry-run test |
| never publication | `refuse_if_experiment` runs first in `store.publish`, `etsy_ops.certified_payload`, `etsy_ops.certified_images`, `disclosed_listing.export_images`, `publication_authority.approve`, `activation_authority.approve` and `image_production.approve`. Experiment candidates are forced `publishable=False`, `may_export=False`. | `test_publication_paths_refuse_an_experiment` (store.publish runs through the real queue as `store_operator`) |

The owner's recorded experiment approval stands in for the `image_generation` gate for
**this live experiment only**, bounded by its budget. Every existing ceiling still applies:
the per-gallery spend plan (CA$2.00, 12 calls), `gateway.images.reserve_render`, the
`creative_director` daily ceiling and the monthly ceiling.

## 3. Harness (`research/final_build/w4/experiment_wrap/run.py`)

It drives the real orchestrator stages through `Worker` (`visual.image_production` jobs with
idempotency keys `imgprod:<slug>@<version>@<release>:<stage>[:round]`), using
`Flux3Generator`, which is subclassed only to use the experiment's CIR loader and to tag the
per-role call counter.

| # | role | source |
|---|---|---|
| 1 | hero: Laura wearing the wrap | FLUX (`lifestyle`, 3 canonical Laura refs + 4 pattern refs + flat lay = 8 inputs) |
| 2 | product-only full flat lay | FLUX (`product_anchor`), generated first; fidelity-gated |
| 3 | cable/texture close-up | deterministic `disclosed_render.detail`. A FLUX close-up of a cable cannot be verified stitch by stitch, so it is not bought. |
| 4 | Laura back view, drape | FLUX (`angle`, a Laura role with its own pose brief) |
| 5 | size/fit | deterministic `disclosed_render.scale` (computed size only; no Laura scale claim) |
| 6 | materials/construction | deterministic `gallery_frames.MATERIALS` |
| 7 | digital download contents | deterministic `contents_frame` from the uncertified US PDF |

Paid roles never draw text cards; every text frame is deterministic.

* **Outfit and scene** are automatic: `styling.select` (W-VISAUTO's wardrobe) with the owner's
  earlier wrap outfit added to `used_outfits`, then refused until distinct from the canonical
  clothing (ivory top, beige trousers) and the earlier outfit (brown top, cream trousers, tan
  boots, gold necklace). No outerwear is worn over the wrap. In the dry run the result was a
  dusty-rose knit cardigan with dark jeans (exact garments in `evidence.json`).
* **Fidelity gate**: W-FIDELITY's deterministic `visual.fidelity` verifier, via
  `RealJudges.product_truth`, measured against the experiment's uncertified CIR (a
  `fidelity_reading` hook for experiment bindings). Its blind craft and consistency questions
  go to a Claude vision judge reserved against the experiment budget. UNKNOWN stops the run;
  it is never PASS.
* **Stop early**: a hard flat-lay FAIL whose codes have no routable repair directive blocks at
  once, after 1 FLUX call. A routable FAIL (for example `WRONG_CRAFT_TEXTURE`) gets exactly one
  corrected retry carrying the repair negatives.
* **Budget**: `ExperimentBudget(cap=CA$5.00)` is reserved before every FLUX and vision call
  (`BudgetedRenderer`, `ExperimentVision`). Each call is also reserved through
  `anthropic.check_budget_cad` / `reserve_render`. There are at most 2 FLUX attempts per role,
  counting transient retries. Every call uses the 2k tier (2048×2048); actual px and format
  are recorded. An output under 2000 px stops all further paid calls; nothing is upscaled. A
  failed call is billed at its reservation, never at zero.
* **Listing draft**: built with `commerce.seo.build_title/build_description`,
  `commerce.search.build_query_set/choose_tags/listing_attributes`,
  `commerce.pricing.decide_price` and `commerce.category.for_product`. It states DIGITAL PATTERN
  and that it is not a finished item. It includes an AI-imagery disclosure, size and yardage
  as computed (no sample made or measured), US/UK PDFs with hashes, alt text for every frame,
  and download instructions. A physical-claim scan must be empty. **The Etsy taxonomy is
  BLOCKED**: the scratch DB has no taxonomy snapshot, and production's reading is not
  available read-only from here without credentials.
* **Owner view**: `approval_package/index.html` is a static page with no external requests.
  It holds the images in order (stamped display copies), the listing as a customer would read
  it, the PDFs linked, per-gate results, unknowns and blockers, costs, attempts and the
  timeline. It shows three separate decisions: visual approval, technical certification
  (REFUSED) and publication authorization (not available). The card is also created through
  `app.command_center.notifications.listing → refresh → image_production.notification_candidates`
  in the scratch DB.
* **Autonomy evidence**: `timeline.json` records every stage and job with job ids,
  idempotency keys, input/output sha256, cost and status. There are no owner actions between
  start and card.

## 3a. FIDELITY follow-ups (folded in, tested in `test_w4_wraptest.py`)

* **Measured codes are shared.** `WRONG_ASPECT_RATIO`, `OFF_PALETTE_COLOUR`,
  `WRONG_COLOUR_LAYOUT`, `WRONG_REPEAT_COUNT` and `WRONG_PIECE_COUNT` are now in
  `creative.failure_codes.PRODUCT_TRUTH_CODES`, as `MEASURED_CODES`.
  * `visual.fidelity.LOCAL_CODES` and its five constants are views of that constant.
  * `OWNER_RECORD_CODES` keeps the owner's original four.
  * `repair_routes.ROUTES` routes all five as prompt negatives.
  * `image_stages.fidelity_verdict` accepts them, through `failure_codes.ALL_CODES`.
  * Test pins were updated in `test_w4_fluxtexture`, `test_w4_fidelity` and
    `test_w4_flux3generator`.
* **Layout rows are drawn at their compiled heights.** `pattern_refs._render_layout` now uses
  `_weighted_rows` on flat pieces: each row is drawn at its compiled height from
  `render_verification.expected_model`, as in `test_w4_fidelity._weighted_rows`.
  * `VERSION` is now `pattern-refs/3.1.0`.
  * Cloudline's end band, measured against the compiled heights, went from 1.30x to 0.97x.
  * The wrap's band equals W-FIDELITY's model of it.
* **Flat-lay surface.** `image_stages.flat_lay_surface` picks the first mid-tone surface that is
  at least 25 CIE ΔE from every palette colour. It tries taupe #7A746C first, then a list of
  fallbacks, and refuses if none is far enough.
  * The prompt names the surface hex and the distance rule, and the words "neutral surface"
    are gone.
  * Every catalogue palette resolves to taupe; a taupe palette gets terracotta.
* **Effect on the experiment.**
  * A wrong-product flat lay now gets one bounded correction that carries the
    measured-code negatives.
  * "Stop early" now fires only on unroutable failures, such as an output under 2000 px.
  * The experiment never re-rolls a failure that regeneration cannot change.

## 4. Dry run (stub provider)

`--dry-run` completed unattended:

* run state `ready_for_owner_review`;
* Command Center card `EXPERIMENT — UNCERTIFIED — NOT FOR PUBLICATION: gallery ready for your
  look: reading-nook-cable-wrap`;
* 3 stub FLUX calls (2048×2048 PNG, each labelled STUB in its pixels, its file name and its
  provider field), CA$0.00 spent, 0 vision calls;
* stub judges, each reading `STUB judge (dry run): no image was judged`;
* every publication path refused with the label;
* 7 gallery frames.

The package is committed at `research/final_build/w4/experiment_wrap/out/dry_run/approval_package/`.

## 5. Expected live cost

Published prices: FLUX 3 at 2k is US$0.100 per image, which is CA$0.1399 at the repo rate
1.3986. A Claude vision call is about CA$0.03–0.06 (Sonnet 5, 2–3 images, padded estimate
reserved).

| path | FLUX calls | vision calls | CA$ |
|---|---|---|---|
| flat lay fails hard, no correction (stop early) | 1 | 1 | ≈0.18 |
| flat lay UNKNOWN (verifier cannot see it) | 1 | 1 | ≈0.18 |
| live path as rehearsed offline (3 FLUX, 6 vision readings) | 3 | 6 | 0.64 |
| worst case (2 attempts on each of 3 roles, every vision call) | 6 | ≈12 | ≈1.4 |

The gallery spend plan caps generation at CA$2.00; the experiment's hard cap is CA$5.00.

## 6. Owner manual FLUX experiments (learning only)

`flux_experiments/2026-10-19_owner_manual_batch2/RECORD.json` holds 5 files (copied, with
sha256 and pixel size). All are `owner_manual`, and none is proof of product accuracy:

* scarf waffle texture: `WRONG_CRAFT_TEXTURE`; the wardrobe was distinct;
* sage cardigan with cream trousers carried over: `REFERENCE_CLOTHING_CARRYOVER`;
* ivory tank and beige trousers: canonical clothing;
* Cloudline flat-lay side border: `INVENTED_EDGING` suspected;
* identity tests with clothing carryover.

One discrepancy is recorded rather than re-labelled: the owner described `4a71d592` as the
sage-cardigan image, but its bytes show the ivory-tank frame.

## 7. Still missing

1. **The paid run.** It needs both keys in the environment of the process that runs it, and
   the BFL credit balance is UNKNOWN (402 on 2026-09-21).
2. **Whether real FLUX flat lays pass W-FIDELITY's verifier** is unmeasured. If it reads
   UNKNOWN (for example, the wrap cannot be isolated), the run truthfully stops at the
   fidelity gate after one image, and no Laura image is generated.
3. **Etsy taxonomy for "wrap"** is BLOCKED (no snapshot in the scratch DB).
4. **The hero (LIFESTYLE job) cannot reach technical PASS under today's gates.**
   `compose.lifestyle_evidence` treats pattern-derived references as informational, not
   photographic, and FAILs them. A generated LIFESTYLE image therefore always fails Product
   Truth. In the offline rehearsal of the live path, the run ended
   `blocked(lifestyle: FAIL (product_truth))` with its card delivered and every image shown.
   The experiment does not buy a re-roll, because regeneration cannot change that result.
   Only a photographic reference (a made sample) or an owner policy decision changes it.
   The back view (ANGLE job) is not subject to that check.
5. **Certification** remains refused until a physical calibration sample of `cable2x2`
   exists. Nothing here can or does change that.
