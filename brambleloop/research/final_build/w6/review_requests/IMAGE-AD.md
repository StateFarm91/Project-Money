# IMAGE-AD — IMAGE-E2E findings A (vessel anchor) and D (illustrated PDFs), closed

Branch `eng/image-ad`, cut from `claude/batch19c` 9757c1d, with `origin/eng/image-e2e`
45a012be merged in. The only conflict was in BUILD_STATE, and both entries are kept.

NOT merged and NOT deployed. Production is unchanged. Nothing ran against production, BFL,
OpenAI or Etsy. Laura (`laura-r2-a42aeac7`) is untouched: no canonical asset, registry entry
or publication-approval constant was changed.

## A. A vessel can now pass the FLUX anchor

**Before.** `fidelity.verify_anchor` needs a side view for a vessel. `candidate_gates` read
`cand["side_data"]`, but nothing ever wrote it. So both Launch-0 baskets stopped at the
anchor with UNKNOWN `vessel_views`.

**Fix** (`visual/image_production.py`, `creative/flux3_generator.py`):
- A vessel's anchor is now a pair. In `product_generation`, a vessel release
  (`is_vessel_release`) first renders a new non-frame role, `product_anchor_side`. The
  generator maps that role to `image_stages.product_only(view="side")`, using the existing
  `VESSEL_SIDE_SCENE`. The top-down anchor (`view="top"`) follows.
- The side render is an ordinary `_generate` call, so it counts in all of these:
  - the run cap: `spend_plan.guard` and `_begin_generation` count it in `generation_calls`
    and `spent_cad`;
  - the paid-provider gate's per-gallery and daily caps: the render runs inside the
    generator's `gallery_scope`;
  - the pending-paid-call hold and ledger.
- **Redrive.** The side render has its own replay key (`operation_for(ANCHOR_SIDE_ROLE)`).
  A redriven stage recovers the recorded side view instead of buying it again. When the
  top anchor is already recorded, nothing is rendered at all.
- **Pair storage.** The side bytes ride on the anchor candidate as `side_data`, which the
  verifier reads. Its id and sha256 are stored in the anchor's checks as `_anchor_side`.
- **Reverify.** `reverify` re-reads the side bytes (sha-checked) and keeps `_anchor_side`.
  The pair is therefore judged again as a pair.
- **No side view.** If the side render fails or its bytes are unavailable, the run blocks
  by name. It never buys a top anchor that is bound to come back UNKNOWN.
- `side_view_verdict`: on its own, a side view is only checked for binding and
  decodability. It is never publishable and never a frame. The pair is judged by
  `verify_anchor`.
- `FLUX_MAX_GENERATION_CALLS` is unchanged (20). A vessel's clean run uses 9 calls, not 8.
  A vessel that exhausts every repair round now reaches the run cap one render earlier.
  That is deliberate: the cap is not raised here.

**Also fixed (found while proving A).** The bread basket's chain re-drafts its listing once
after its first package. The package fence reads that as "changed after package review", so
the gallery run parks in `waiting_for_sale_admission`. A readmitted run that parked again
never left that status, so `_SALE_WAITS.count` was not incremented. Every later readmission
then reused the taken `#admitted<n>` key, and the release waited forever. That is exactly
the silent stall D-OWNER-SALE-PIPELINE forbids.
- Fix: `_readmit` records which wait it re-entered.
- A park from that readmission is a new wait (count + 1).
- Two packages during one wait still enqueue only one readmission.

## D. The template is the production PDF layout

- `runtime.release.PDF_LAYOUT = "template"`.
- `pdf_template.build_customer_pdf_with_layout` is the single decision, behind
  `build_customer_pdf`, which `assets.build`, `store.publish` and `commerce.deliverables`
  all call. Under the release default it returns the template document only when all of
  these hold:
  - the release has a complete, valid certified gallery;
  - the document is `customer_ready`;
  - it passes PremiumStandard (`pdf_standard`, enforced inside `build_template_pdf`);
  - it passes the sale checker, `pdf_template.audit(expected_gallery=...)`, on its own
    bytes: page order, logo on the cover, headers and thank-you, the seven certified
    renditions in order, no uncertified photo, no placeholder or template marker, and a
    count on every row.
- **Interim PDF.** Otherwise the engine PDF is built as `engine_interim`, and the build
  says why ("awaiting gallery: …", a template refusal, or the failing checks).
- **Determinism.** The choice depends only on the CIR and the release's certified gallery,
  so every build and re-render site makes the same choice. Test d3 shows the publish-time
  re-render matches the certified hashes.
- **Explicit callers.** A caller passing `layout=` explicitly keeps the old behaviour
  (`GalleryAwaiting` on no gallery; `test_pdf_template` passes unchanged).
- `assets.build` now records `pdf_layout` per edition in `assets.built`. It also records
  `illustrated`, which binds the build to the gallery certificate: the record id, its
  frames in order, the frames each edition embeds, and each edition's rendition hashes.

**Rebuild on certification.** When `visual.image_production` reports `gallery_certified`,
the handler now enqueues `assets.build` with `illustrate: <certificate record id>`,
one job per record (`chain_key("assets", …, "illustrate:<id>")`). That path (`_illustrate`):
- rebuilds only the two PDFs, with the certified frames embedded, and re-certifies them;
- refuses by name, leaving the interim PDF in place, if any of these holds:
  - the asked-for certificate is no longer the valid one;
  - either edition comes back interim;
  - the embedded frames are not the certificate's frames in order;
- stores the PDFs with provenance lineage, and writes an `assets.built` row with the new
  hashes and the binding. `pipeline._certified_pdf_hashes` then returns these hashes, so
  they become the release's certified files;
- re-enqueues `listing.package`.

**The CONTENTS frame is part of the layout decision (`pdf_template._contents_cycle`).**
- The gallery's 7th frame (CONTENTS, "what's included") is a deterministic preview of the
  certified PDF (`launch_imagery._check_contents`), and the template's gallery slot 7 embeds
  that frame.
- A template document whose own preview of the US edition is not the certified CONTENTS
  frame is not accepted. The edition then stays `engine_interim`, with
  `CONTENTS_PREVIEW_STALE` as the reason. Every build and re-render site therefore makes the
  same choice.
- `_illustrate` then records `assets.illustration_refused`, naming the certificate record
  and each edition's reason, and stores nothing. A second check, `_contents_preview_mismatch`
  before storing, is kept as a backstop.
- **This is what happens today for every gallery: see finding G below.**

It does not touch the listing frames, the disclosed set or the price chain. A full rebuild
re-files the disclosed set and re-issues certificates, which would disturb the gallery the
PDFs embed. `assets.build`'s `WORK_KEYS` gain `illustrated`. Its outputs carry no
`pdf_sha256`, so flow_health does not expect a pricing successor.

**READY is stricter.**
- *What the code did before:* `listing_package.assemble` was READY with ANY PDFs certified
  for the release, the engine PDF included. Nothing checked that the PDFs had images. That
  contradicts D-OWNER-PDF-STANDARD ("The PDFs have images") and D-OWNER-SALE-PIPELINE
  ("both premium illustrated PDFs certified for this release").
- *New blockers* (`pdf_illustration_blockers`):
  - `PDF_NOT_ILLUSTRATED`, unless every edition of the newest build for exactly this
    release is the template;
  - `PDF_GALLERY_STALE`, unless its binding names the valid certificate's frames in order.
- *Binding rule:* the binding compares frames, not record ids. A certificate re-issued for
  identical frames changes no embedded byte. This is not hypothetical: the basket's rebuild
  re-files its disclosed set as a new record with the same frames.
- *Admission:* both blockers are tagged `image`. The missing gallery is what keeps the
  PDFs un-illustrated, so they do not stop sale admission for images. Otherwise the gallery
  could never be bought, and the PDF could never be illustrated.
- The Production Inventory stage `premium_pdf_completed` was **not** changed: it is still
  reached by any certified PDF. Its definition is read by many surfaces and was out of
  scope. READY, the sale gate, is the strict one. Follow-up: make the inventory label say
  "interim" for an engine PDF.

**Consequence to know.** A product whose *disclosed* deterministic set is itself a complete
7-frame certificate (D-OWNER-GALLERY-COMPLETE; the bread basket is one) gets a template PDF
at its ordinary `assets.build`. That PDF embeds those certified, disclosed renders, labelled
as renderings. That is the template's rule ("the certified gallery"). When a FLUX gallery
later certifies, `illustrate` rebuilds the PDFs with it.

## Tests

New suite: `tests/test_image_ad.py`. Its test doubles:
- the stub BFL transport from `test_image_e2e_worker`. For vessel requests it answers with
  the CIR's own top or side render (`test_v2_vessel_fidelity`), chosen from the request's
  scene text;
- `GalleryJudges`. The basket's craft reading uses `test_w4_fidelity.PASSING_JUDGE`
  (plain crochet, no edging), since the basket has no edging;
- the Laura publication double.

The tests:
- **a1.** The bread basket, driven by the real Worker, reaches a PASS `vessel_anchor` (sides
  6/6, palette, wall bands, rim, craft). The anchor names the side view it was judged with.
- **a2.** Every BFL submit has one cost entry. There is one side render per anchor attempt,
  each paid. Run calls, per-gallery spend and daily spend are within the caps.
- **a3.** With the gallery cap at 1, the side view is bought and the top anchor is refused
  by name. No pending hold remains.
- **a4.** With the daily cap at 2 (the probe plus the side view), the top anchor is refused
  naming `daily_image_cap`.
- **a5.** Redriving `product_generation` and `fidelity_gate` buys nothing twice (same
  submits as the clean run).
- **a6.** `reverify` re-judges the stored pair: still PASS, `_anchor_side` kept. The same
  top view without its side is UNKNOWN.
- **d1.** Before the gallery is certified, the engine PDF is `engine_interim` ("awaiting
  gallery"), `illustrated` is None, and the package carries an image-tagged
  `PDF_NOT_ILLUSTRATED` and is not READY.
- **d2.** The certified 7-frame blanket gallery triggers `assets.build{illustrate: record}`,
  one job, on the valid certificate record and release. The template build passes
  PremiumStandard and the sale checker. The layout decision then refuses both editions by
  name (`CONTENTS_PREVIEW_STALE`, finding G). The refusal names the certificate record, and
  the newest certified build is still the interim one.
- **d3.** The package is not READY and carries an image-tagged `PDF_NOT_ILLUSTRATED`. The
  certified PDFs and every re-render agree (no PDF_HASH_DRIFT): `deliverables` and the
  `store.publish`-style re-render, with and without the Laura double.
- **d4.** The READY rule, given an illustrated build on record (the refused build's binding
  filed as that job's `assets.built`), accepts it for the certificate's frames in order,
  including a re-issued record with the same frames. It rejects different frames and a
  missing gallery as stale.

The `test_image_e2e_worker` helper gains `seed=False`, used by the basket sweep.

## Results
- **Targeted runner** (run `20261121T025359Z-3957`, dirty tree on 451a2a0's parent work,
  JOBS=3, SUITE_REGISTRY=0), 11 suites, **194 passing, 0 failing**:
  - test_pdf_template, test_pdf_standard, test_pdf_diagrams;
  - test_owner_gallery_complete, test_w5_v0_paid_provider_gate;
  - test_compiler, test_vacuity;
  - test_opus2_listing_package, test_w5_a9_package_event;
  - test_v2_vessel_fidelity, test_w4_flux3generator.
- **Direct runs** (`.venv` py3.13 from the lock files):
  - test_image_ad: a1–a6 OK and d1–d4 OK, in separate invocations. The d tests and
    test_pdf_template (31 OK) ran on the final code. The a tests ran before the CONTENTS
    change, which does not touch the anchor path.
  - test_w3_decision_index: OK after regenerating the index for D-IMAGE-AD.
- **test_image_e2e_worker:** 7/7 OK directly before the readmit fix. It was re-run through
  the runner and directly on the final code; those results are added below if they finish
  before the push.
- **Not run:** the full suite. A single runner invocation covering test_image_e2e_worker and
  test_image_ad was not completed by the deadline: they take about 25 and about 45 minutes.
- **Mutation check:** not run as separate mutants. Each fix was found by a test failing
  first:
  - the basket blocked at `vessel_views`;
  - the readmission key collided;
  - `PDF_GALLERY_STALE` was raised on a re-issued record;
  - PDF_HASH_DRIFT appeared after the illustrated store (finding G).

## G (new, OPEN): the CONTENTS frame and the illustrated PDF form a cycle

This was found by test d3. A first version of `_illustrate` stored the illustrated PDFs. The
publish-time re-render then came out as the interim engine PDF, which raised
`PDF_HASH_DRIFT`. The cause is the CONTENTS frame:
- the certified gallery's CONTENTS frame previews the interim PDF;
- once the illustrated PDF is the certified file, that frame no longer exports
  ("bytes are not the preview of the certified PDF");
- `gallery_from_release` then raises GalleryAwaiting, so every re-render falls back to
  the engine PDF.

Storing the PDFs would have left the release in this state:
- a gallery that cannot be exported;
- `store.publish` refusing on hash drift;
- a listing image showing a document the buyer does not get.

So `_illustrate` now refuses before storing (fail closed, consistent). The interim PDF stays
certified, and the package stays not READY with `PDF_NOT_ILLUSTRATED`.

The way out needs the image pipeline and was not built here:
1. after the illustrated build, re-make the CONTENTS frame from the illustrated PDF
   (deterministic, CA$0);
2. re-certify the gallery with it;
3. illustrate again.

The template's previewed pages must not show gallery slot 7. Then the second iteration's
preview equals the first's, and the cycle closes in two steps. Until then **no release
reaches READY**. That is the correct reading of D-OWNER-PDF-STANDARD, but it means
D-OWNER-SALE-PIPELINE step 2 is still not met end to end.

## Not done / open
- IMAGE-E2E findings B (Laura publication approval: an owner decision), C (coaster stub
  pixels) and F (the first-customer `imagery` area judges a generated 7-frame certificate as
  the 3-frame disclosed set) are unchanged.
- The basket gallery beyond the anchor was not driven to certification here. The stub
  pixels for its scene frames are a flat lay, not a basket.
- Inventory label for the interim PDF (above).
