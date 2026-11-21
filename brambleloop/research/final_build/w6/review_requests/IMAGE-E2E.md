# IMAGE-E2E — the worker, unaided, from a production-like DB to a certified 7-photo gallery

Branch `eng/image-e2e`, cut from `claude/batch19-fixers` 8204c93. NOT merged, NOT deployed.
Production is unchanged. Nothing ran against production, BFL, OpenAI or Etsy. No Railway
variable was read.

## What the test does

`tests/test_image_e2e_worker.py`. It starts from a production-like database, built with the real
handlers: `gate.certify`, then `assets.build` (certified US/UK PDFs), then `listing.seo`, for the
Launch-0 `cloudline-baby-blanket`. It applies D-OWNER-APPROVE-ALL with the real
`ops.owner_directives.apply`, which creates exactly the two activations. It then seeds only what
production's own triggers enqueue: the `listing.package` event and `ops.capability_probes`. After
that, one real `Worker` claims every job until the queue is empty. Nothing is called by hand.

The chain it drove:

    listing.package -> sale admission (D-MAIN-IMAGE-ADMISSION) -> visual.image_production
    (generated_gallery route; 12 stages) -> owner_card -> certify_gallery -> listing_set
    certificate (7 frames) -> listing.package refreshed

**Real code:**
- the queue and the worker, including the worker's provenance check;
- the capability probe, which opens `image_generation`;
- the paid-provider gate: activation, per-gallery and daily caps, ledger and paid-call replay;
- `images.generate`: reserve, send, store, bill;
- the FLUX 3 request builder and stages;
- every image-production stage, gallery certification, the listing set, the listing package and
  sale admission.

**Test doubles (labelled):**
- the BFL HTTP transport. It uses the recorded response shapes. The delivered pixels are a
  synthetic flat lay of the certified CIR.
- the vision judges: `RealJudges` is replaced by the `GalleryJudges` that every gallery e2e uses.
- Laura's per-image publication approval (see finding B).
- the network: proxies are unset for the run.

## Tests (7)
1. The worker alone produces a valid listing-set certificate naming the 7 campaign frames, in
   order (DESIRE … CONTENTS). `lifecycle._complete_gallery` is True. Every BFL submit has
   exactly one CostEntry.
2. After certification, the listing package is re-assembled for this release. It no longer
   carries "gallery incomplete" or any `certified_frames` blocker. Only the publish-time gates
   and SAMPLE_PHOTO_REQUIRED remain, and both still block publishing.
3. Ceilings hold:
   - run spend ≤ min(activation per-gallery CA$2.50, `MAX_SPEND_CAD_PER_GALLERY` CA$2.00);
   - calls ≤ `FLUX_MAX_GENERATION_CALLS`;
   - total spend ≤ the CA$5 daily activation ceiling;
   - spend > 0, so the paid path really ran.
4. Per-gallery ceiling bites. With `BRAMBLELOOP_IMAGE_GALLERY_CAP=3`, at most 3 gallery
   renders are made. The run blocks with the gate's reason, not "unresolved cost". No pending
   hold remains and the gallery is not complete.
5. Redrive mid-run. Every generation stage is redriven after it completes: the same job goes
   back to PENDING, and a duplicate job with the same inputs is enqueued. The finished gallery
   makes exactly as many BFL submits as the clean run. No paid call repeats.
6. Without the Laura double, the worker generates and verifies, then holds. There is no
   certificate, the `laura_publication` blocker is named, and no extra paid call is made.
7. Daily ceiling bites. With `BRAMBLELOOP_IMAGE_DAILY_CAP=3`, at most 3 images are made that day
   (the probe included). The run blocks naming `daily_image_cap`, with no pending hold.

## Handoffs found broken, and fixed (each pinned by a test above)
1. **owner_card dead-lettered: no gallery could ever be certified by the worker.**
   - What happened: `gallery_persist.write_frames` wrote each frame's `visual_truth`
     provenance as `source="backfilled"` with no `job_id`. The worker's provenance check
     (`assert_instrumented`) refused the job: "wrote 6 derived artefact(s) with no
     lineage-complete provenance row from this job".
   - Why no test saw it: every existing test called `certify_gallery` outside a worker.
   - Fix: inside a job (`paid_calls.current_job_id()`), the row is `recorded` with that job's
     id. A direct call is unchanged. Test 1.
2. **The listing package stayed stale after certification.** Nothing re-ran `listing.package`,
   so the package kept saying "gallery incomplete: certificate names 6 of 7" until the
   six-hourly sweep. Fix: `handle_image_production` enqueues the `listing.package` event for the
   release when a stage reports `gallery_certified`. It is idempotent per run and restart epoch,
   with internal writes only. Test 2.
3. **A ceiling refusal was reported as a billing mystery.**
   - What happened: when the paid-provider gate refused a render before any network I/O (a
     per-gallery or daily cap, or no activation), `_generate` left the `_pending_paid_call`
     hold in place. The next call then blocked the run with "prior paid image call has an
     unresolved cost; review required".
   - Fix: a `PaidCallRefused` anywhere in the exception chain means nothing was billed, so the
     hold is released and the run stops naming the gate's code and reason. Any other provider
     error still keeps the hold (fail closed). Tests 4 and 7.

## Found, NOT fixed (open; named so nobody reads the green test as covering them)
A. **Vessels cannot pass the anchor on the FLUX route.** This covers the
   `housewarming-key-basket` and `hexagonal-bread-basket` Launch-0 baskets.
   - `fidelity.verify_anchor` needs a side view for a vessel. It returns UNKNOWN `vessel_views`
     without one.
   - `candidate_gates` reads `cand["side_data"]`, but nothing in `src/` ever writes it.
     `image_stages.product_only(view="side")` exists, and the generator never calls it.
   - Reproduced: the basket run blocks after one anchor render: "product fidelity cannot be
     verified … UNKNOWN on ['vessel_views']". Spend stops there.
   - Fixing it needs a second paid anchor render per vessel, counted in the caps, and the side
     bytes kept through recovery and reverify. It was not done in this slice.
   - This is why the test uses the blanket.
B. **Laura publication approval has no production path.**
   - `canonical.PUBLICATION_APPROVED` is an empty code constant. Every Laura frame (lifestyle,
     size) reads `laura_publication` UNMEASURED, so **no gallery with Laura can be certified in
     production today.**
   - Test 6 proves the worker holds safely there.
   - This is the owner's decision, not engineering's. D-OWNER-APPROVE-ALL explicitly touches
     nothing but the two activations, and Laura is locked. OWNER ACTION REQUIRED, or an owner
     decision on an approval route (a per-image step-up approval card).
C. **Coaster anchor with stub pixels.** `hexagon-coaster-set` fails INVENTED_EDGING three times
   on the synthetic flat lay. This is a limit of the stub pixels, not evidence about real FLUX
   output. Not investigated further.
D. **PDFs are not rebuilt with the gallery.** `runtime.release.PDF_LAYOUT` is still `"engine"`.
   The template layout that embeds the certified gallery (D-OWNER-PDF-TEMPLATE) is not live, so
   the engine PDF does not consume the certificate. D-OWNER-SALE-PIPELINE step 2 ("PDFs with
   those images embedded") is therefore not met by any code path yet. Not changed here.
F. **The first-customer `imagery` gate rejects the generated gallery.**
   - The refreshed package (fix 2) carries `FIRST_CUSTOMER_BLOCKING: imagery: FAIL --
     certificate N covers 0 frame(s) that are not exactly the 3 disclosed frame(s) on file`.
     The area still judges the listing as the 3-frame disclosed set, so a generated 7-frame
     certificate can never pass it.
   - It does not stop image admission: it only appears once the gallery exists. It does block
     publishing.
   - Not fixed. Test 2 pins the refresh and leaves this out of its assertions.
E. The vision side is doubled at the judge level, not at the OpenAI transport. The
   `openai-vision:vision` activation is applied, but no vision request is exercised.

## Results
- **Runner.** Run `20261121T005954Z-2496`, py3.13 venv from `requirements.lock` plus the test
  lock:

      JOBS=4 SUITE_REGISTRY=0 SUITES="test_image_e2e_worker test_owner_gallery_complete
      test_w5_v0_paid_provider_gate test_owner_directive_approve_all test_vacuity
      test_vis_gallery_e2e test_eng_vis_flux"

  - PASS: test_owner_gallery_complete, test_owner_directive_approve_all and test_vacuity.
  - test_image_e2e_worker: tests 1, 3, 5 and 7 OK in that run. Tests 2, 4 and 6 failed on
    three test-side assertions:
    - test 2 asserted the `imagery` blocker away (it is real; finding F);
    - test 4 bounded `generation_calls`, which counts the refused attempt;
    - test 6 assumed no valid certificate, but the 6-frame disclosed one stays valid.
  - All three were corrected and re-run after the runner on the final code: test 2 OK, test 4 OK
    (the run blocks naming `gallery_image_cap`), test 6 OK. So all 7 pass, but not in a single
    runner invocation.
- **Pre-existing failures, identical on clean base 8204c93** (worktree run with the same venv):
  - `test_eng_vis_flux` test_open_motif_recoveries_block_a_replacement;
  - `test_vis_gallery_e2e` test_10, test_12 and test_13. The key basket's `etsy_remote_state`
    blocker no longer carries its `publish_time` tag, so the basket is not admitted. That is
    one more reason the basket is not the fixture here.
  - `test_w5_v0_paid_provider_gate` test_key_without_activation_a_render_and_a_paid_production_generator_are_refused:
    the run parks in `waiting_for_sale_admission` before the gate it expects.

  Not caused by this branch, and not fixed here.
- **Mutation check.** Not run as separate mutants. Each of the three fixes was found by this
  test failing first, before the fix: owner_card DEAD, a stale package, "unresolved cost".
