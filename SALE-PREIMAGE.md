# SALE-PREIMAGE: sale pipeline pre-image readiness and image admission

Branch `eng/sale-preimage`, based on `origin/claude/w6-release-19h17`. Not released or deployed. The coordinator releases it.

## Evidence (production, 2026-11-22T00:00Z, `sale_pipeline`)

- 31 releases, 3 eligible, 0 with a finished gallery, 0 with certified PDFs, 0 READY.
- CA$6.00 reserved, which is 3 × the CA$2.00 per-listing cap.
- 28 releases in `awaiting_pre_image_readiness`: `child_family` 15, `pdf_structure` 7, `copy_seo` 6.
- 9 image runs in `waiting_for_sale_admission`.

I had no access to production data, only these counts. Each root cause below comes from reading the code and is reproduced by a test. Whether it explains every production row has to be confirmed in production readback. The incident and blocker text now names the real reason, which makes that check possible.

## Root causes and fixes, by reason

### `pre_image:child_family` (15)

**Root cause.** `publish/sale_pipeline.py` `pre_image_readiness` FAILed every release whose children's decision reads `undecided`. That is every product no catalogue entry names, including flat, unstuffed adult throws with no child word anywhere. The publication gates do not do this:
- the renderer (`publish.pdf`) raises the A1-R hold only for child words in the title or slug, or for a closed stuffed form;
- the listing package blocks only on child words in the listing copy;
- `gates.child_safety.applies` decides the safety gate's scope the same way.

These releases already had certified PDFs, so the renderer had judged them outside the children's question. Only the sale gate held them, it added no safety evidence, and it raised no owner card. They waited silently, forever.

**Fix.** New `sale_pipeline.child_audience_screen(cir, listing)`, a deterministic screen. The children's question applies when ANY of these signals is present:
- a catalogue assignment;
- a closed stuffed form (`closed_stuffed_form`; construction that cannot be read counts as stuffed);
- `gates.child_safety.applies` (child words in the title or slug, a stuffed figure, a closing or stuffed piece in rounds, a baby or child garment grading);
- child words in the CIR category;
- child words in the listing title, description or tags.

A pattern or copy that cannot be read counts as a signal. If any signal is present, the old rule applies unchanged: `undecided` FAILs. The FAIL now names the owner decision and the signals. Only `undecided` with no signal at all PASSes, with `decision: "not_applicable"` and the screen recorded on the gate. Assigned and not-for-children decisions are unchanged.

**Child safety is not weakened.** No assignment, exemption or decision is created. Every product with a children's signal still needs an explicit decision. `gates.child_safety`, `publish.pdf` and the listing package are untouched.

**OWNER ACTION REQUIRED, where a signal exists.** A release that still FAILs `child_family` now carries the text "OWNER DECISION: assign it in products.launch0.EXTRA_CHILDRENS_ASSIGNMENTS or record a reasoned exemption in NOT_MERCHANDISED_TO_A_CHILD, bound to this design", with its signals. That is a genuine owner merchandising decision: cost CA$0, about 5 minutes per product. Until it is made, that product does not sell; every other product continues. I cannot say how many of the 15 fall in this group without production data.

**Finding, not changed (needs a decision entry).** `products.launch0._BABY_MONTH_SIZE` matches yarn lengths in listing descriptions, for example "Colour B: about 9-12 m", "18-24 m" and "a 6 m tail", and reads them as baby garment sizes. A colourwork listing whose small accent colour falls on 3, 6, 9, 12, 18 or 24 m therefore reads as child-audience copy, at the listing package as well as here. This is the shared child-safety word reader, so I left it alone. Two possible fixes, both for the coordinator or owner to choose:
- have `commerce.seo.build_description` write "metres";
- narrow the regex to garment context.

### `pre_image:copy_seo` (6)

**Root cause.** `_latest_job` looked for the release's `listing.seo` (and `launch.plan`) job only among the newest 500 DONE jobs of that type, company-wide. W6 fix-only rebuilds re-run `listing.seo` for every product but stop before `launch.plan`. So a release whose copy had been drafted and selected for sale fell out of the `listing.seo` window, while its `launch.plan` was still inside the `launch.plan` window. The result was `selected_for_sale` PASS with `copy_seo` FAIL ("no listing copy and SEO drafted for exactly this release") for good. That matches the evidence: these releases pass `selected_for_sale`, and `launch.plan` is only enqueued by a successful `listing.seo`.

**Fix.** Jobs whose idempotency key is this release's chain key (`<stage>:<slug>:<version>:<release[:12]>`, from `runtime.release.chain_key`) are read first, with no window. The bounded scan remains the fallback for unkeyed jobs. The inputs must still match slug, version and the full release exactly, and the newest matching job still decides, so a later `ok: false` still FAILs. No content check changed. A release whose newest SEO job genuinely failed stays FAIL with its real blocking reason.

### `pre_image:pdf_structure` (7)

**Root cause.** The pre-image PDF structure reading (`pdf_standard.check(..., images="pending")` on the base PDFs) was cached on the run and reused whenever the base PDF hashes matched. It was never tied to the checker. BATCH19D changed `publish/pdf_standard.py` (row-progress diagrams for flat pieces) without bumping `CHECKER_VERSION` (still `pdf_standard/2`). A FAIL issued by the older checker was reused for good, and the release was never re-read.

**Fix.** Each reading records `checker`, made of `CHECKER_VERSION`, the standard's hash and a hash of the checker's source (`structure_checker()`). A cached reading is reused only when the PDF hashes and the checker are both identical. A reading without a checker, or a checker that cannot be identified, is re-read. A real FAIL from the current checker on the same PDFs is still reused and still FAILs.

**What may remain.** If a base engine PDF genuinely FAILs the current standard, the fresh reading says so with the failed checks (`why`). The fix for that is a rebuild of `assets.build` for that release, which this branch does not trigger.

### 3 eligible releases with no finished gallery, and 9 runs in `waiting_for_sale_admission`

**What admission is gated on.** It is NOT the per-listing cap: CA$6.00 is held for the 3 eligible releases, within the cap and the month ceiling. A paid stage runs only when both spend admissions hold:
1. the sale pipeline's reservation (`spend_admitted`);
2. the vis-gallery `sale_admission`, which reads the recorded listing package for exactly this release. Every blocker in it must be an image blocker, an allow-listed publish-time area, or the sample photo (already image-tagged).

A publication halt (`halted (#173): ...` from `release_gates.staleness`) is a non-image `for_publish` reason, so it parks the FLUX run in `waiting_for_sale_admission`. The same applies to any other non-image package blocker the pre-image subset does not read.

**Root cause (code).** Once parked, nothing re-entered the run:
- `runtime/sale_pipeline_ops.start_images` treated a run in `waiting_for_sale_admission` as "in_progress" and enqueued nothing;
- the sale pipeline's gallery stage, re-driven by the sweep, reported only `gallery_in_production`, with no reason;
- only the six-hourly `listing.package` sweep could re-enter the run, and only if the package had been recomputed clean.

**Fix.**
- `start_images` now sends a parked FLUX run through the existing admission point, `image_production.admit_for_sale`. That re-checks `sale_admission` and re-enters at the first stage once per wait, under its existing `#admitted<n>` idempotency key. If admission still refuses, the run stays parked.
- The gallery stage, for an image run in a non-spending wait, names blocker `image_sale_admission` with the wait's recorded reason, for example the halt. While the reservation is held, it asks `start_images` to re-enter the run. Stall incidents therefore name the real blocker instead of "gallery_in_production".

**Spend safety.** No new spend path:
- every FLUX stage still re-checks both admissions before doing anything;
- a re-entered stage with a paid generator and no reservation makes 0 generator calls (tested);
- paid generation keeps its per-operation input hash (`operation_for`), and re-entry keys are deduplicated by the durable queue.

**DECISION NEEDED (coordinator or owner), if the halt is the cause.** If production readback shows the 3 eligible runs' `image_sale_admission` reason is `halted (#173)`, they stay parked by design: the halt is a non-image listing gate under D-OWNER-SPEND-ORDER. Admitting image spend through a company-wide staleness halt, as was done for the marketing rebuild, would be a gate change that needs its own decision entry. I did not make it.

## Tests

New suite `brambleloop/tests/test_sale_preimage.py`, 16 tests. On the old code 12 FAIL, and the 4 that pass are the guards that must not move. On the fix all 16 PASS:
- **child_family:**
  - no signal → `not_applicable` PASS;
  - child title words, child words in the copy, or "0-3m" in the copy → still FAIL;
  - a stuffed form → FAIL;
  - unreadable pattern or copy → signal;
  - an assigned product is unchanged.
- **copy_seo:**
  - the release's SEO job is found behind 505 newer jobs;
  - exact inputs still decide, the newest wins (`ok: false` → FAIL), another release with the same 12-character prefix is not matched, and unkeyed jobs are still found.
- **pdf_structure:**
  - a reading from another checker, or with no checker, is re-read;
  - same checker and same PDFs → reused, a real FAIL included;
  - changed PDFs → re-read.
- **Admission:**
  - an admitted release's parked FLUX run is re-entered through `admit_for_sale` once per wait (one idempotency key);
  - it stays parked when `sale_admission` refuses;
  - the gallery stage names `image_sale_admission` with the wait reason, and re-enters only while the reservation is held;
  - a re-entered paid stage with no reservation makes 0 generator calls.

## Suites run

Command: `cd brambleloop && JOBS=4 SUITE_REGISTRY=0 SUITES="..." bash run_tests.sh`

**Batch 1** (run record `20261122T002416Z-1203`, at SHA f60e4ab, tree clean, 11 suites): **TOTAL PASSING 227, suites failing 0.** Suites: test_sale_preimage, test_sale_pipeline, test_sale_pipeline_e2e, test_image_ad, test_pdf_standard, test_w4_ownerimg, test_w5_v0_paid_provider_gate, test_vacuity, test_search_hero_publish, test_etsy_readback_observe, test_w4_readback_evidence.

**Batch 2** (slow end-to-end): test_vis_gallery_e2e, test_visual_factory_e2e. BATCH2_PLACEHOLDER

Not run: the full suite. This branch is not release-eligible until the coordinator's full run passes.

