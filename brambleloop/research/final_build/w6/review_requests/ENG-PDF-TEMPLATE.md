# Review request — ENG-PDF-TEMPLATE

- **Branch:** `eng/pdf-template` — builder branch; NOT reviewed, NOT integrated, NOT deployed.
- **SHA:** `ac2c2ccb809df907021887f72f63d3433ed03594` (code and tests). The commit that adds this request changes only this file.
- **Merged in:** `origin/claude/w6-INTEG6` (dde3ea62) and `origin/eng/gallery-complete`.
  - Both sides of BUILD_STATE and DECISION_LOG were kept.
  - `autonomy_map.json` was regenerated with `python -m brambleloop.autonomy.map --write`.
- **Decisions:** D-ENG-PDF-TEMPLATE-1 and D-ENG-PDF-TEMPLATE-2 in DECISION_LOG. They implement
  D-OWNER-PDF-TEMPLATE, D-OWNER-PDF-STANDARD, D-OWNER-PDF-LOGO and D-OWNER-SALE-PIPELINE.

## What is built

`publish/pdf_template.py` renders the owner's master template
(`spec/07_Brambleloop_Master_Pattern_Template.pdf`).

### Faithful to the owner's template
- **Canonical logo** on the cover, in every page header and in the thank-you block. The audit
  checks it on the built bytes.
- **Owner banner** on the About page.
- **Gallery:** the 7 slots are filled from the valid listing-set certificate's frames, in
  certificate order. Without a complete gallery the build raises `GalleryAwaiting`.
- **Missing facts block** the build (`TemplateBlocked`, with the section named).
- **No leftovers:** no template placeholder, "ILLUSTRATIVE SLOT" or "MASTER LAYOUT" marker is
  ever printed. The audit reads the placeholder list from the template itself.

### Amigurumi lessons (from the teardowns)
- **Per-component diagram slot:** each piece's profile is drawn from its stitch counts, one
  band per round at gauge, on one scale shared by all pieces. A stuff arrow comes from the
  CIR's own row note. Each is labelled as a diagram, not a photograph.
- **Numbered assembly steps** (A1…An), one per CIR seam. Each has its placement in round
  numbers and a placement diagram with the join's rounds outlined. A seam without `at_round`
  blocks.
- **Eye-options block:**
  - Embroidered eyes are placed between the head's widest rounds.
  - Safety eyes are offered only when the certified materials list them, with the under-3
    warning.
- **Gauge plus a hook range:** the stated hook down to 0.5 mm below it.

### Premium standard on the template
- `pdf_standard.TEMPLATE_EQUIVALENTS` lets each rule accept the template's own heading, by exact
  string. The content each rule requires is unchanged.
- The template refuses customer builds that fail the standard (`PremiumStandardRefused`), as the
  engine does.

### Layout switch
- `runtime.release.PDF_LAYOUT` **stays `"engine"`**. See the switch section below.

## Defects found (please route)

1. **The engine under-reports yarn for every multi-piece pattern.** `cir.twin.build_twin` models
   one component, and `publish.pdf` prints that component's yarn.
   - Example: Harbour Drop-Shoulder Pullover, size M. The engine prints 467–700 m (body only,
     584 m). The whole pattern is 808 m, which is 646–969 m.
   - The ring pillow omits its bottom piece (24.8 m).
   - The template is fixed (`_pattern_yardage`). The engine is NOT, because its consumers
     (listing copy, deliverables, digests) belong to other lanes. The garment size table, which
     reads `grading.yarn_m`, is already correct.
2. **A closed stuffed toy cannot pass child safety.** The twin refuses a width × height for a
   closed shaped piece, and the `age_suitability` statement requires one. Every amigurumi build
   therefore blocks with that named reason. The fix belongs to the child-safety and twin
   owners: for example, let the statement use the circumference that the twin's own
   `size_refusal` says to state.
   - The template's amigurumi layout is exercised by `tests/fixture_amigurumi.py`, a test
     fixture that is never a product, with only that one fact stubbed.
   - No amigurumi proof PNG is committed for that reason.

## Proofs

`research/final_build/w6/pdf_template_proofs/` contains:
- the contact sheets;
- the 14 template-versus-render page comparisons (coasters US);
- `manifest.json`.

All images are test doubles, and every page is marked NOT CUSTOMER-READY.

| Family | Product | Pages (US/UK) | Template audit | Premium standard (test-double gallery) |
|---|---|---|---|---|
| home décor | hexagon-coaster-set | 20 / 20 | PASS | only `cover` (hero labelled TEST DOUBLE) |
| baby | cloudline-baby-blanket | 25 / 25 | PASS | only `cover` |
| garment | harbour-drop-shoulder-pullover-m | 27 / 27 | PASS | only `cover` |
| pillow | bobble-floor-pillow | 17 / 17 | PASS | only `cover` |
| blanket | winter-village-graphghan | 19 / 19 | PASS | only `cover` |

With a gallery labelled as renders, all 10 editions are `customer_ready` with zero premium
failures (`test_every_proof_family_meets_the_premium_standard_with_a_rendered_gallery`).

## Test counts

Clean run on `ac2c2cc`, `PDF_LAYOUT = "engine"`: **16 suites, 290 tests, 0 failures**.

| Suite | Passed / total |
|---|---|
| test_pdf_template | 31 / 31 |
| test_pdf_premium | 27 / 27 |
| test_pdf_standard | 23 / 23 |
| test_pdf_layout_bounds | 3 / 3 |
| test_deliverable_qa | 61 / 61 |
| test_layout_qa | 16 / 16 |
| test_asset_manifest | 8 / 8 |
| test_w4_ccgap_pdfium | 2 / 2 |
| test_w4_firstsale_deliverables | 6 / 6 |
| test_certification | 12 / 12 |
| test_cert_publish_gates | 18 / 18 |
| test_vacuity | 8 / 8 |
| test_w4_resume_runner | 40 / 40 |
| test_compiler | 9 / 9 |
| test_reverse | 18 / 18 |
| test_twin | 8 / 8 |

The same suites under `PDF_LAYOUT = "template"`, run in a separate worktree:
- **Unchanged:** asset_manifest, certification, deliverable_qa, layout_qa, pdf_layout_bounds,
  pdf_premium, pdf_standard and w4_ccgap_pdfium. Their counts are identical to the engine run.
- **test_w4_firstsale_deliverables:** 2 / 6 pass.
- **test_cert_publish_gates:** 8 / 18 pass.

Every template-only failure is `GalleryAwaiting`: `assets.build` dies because no listing-set
certificate exists yet. See the next section.

Note: `test_vacuity` flagged 4 loops. Three were in `test_pdf_template.py` and one was in
`test_owner_gallery_complete.py` (from the gallery-complete merge). Each now has a
non-emptiness guard.

## Why `PDF_LAYOUT` is not flipped

Under `"template"`, `test_cert_publish_gates` fails 10 of 18. Every one of those fails because `assets.build` dies with `GalleryAwaiting`. `test_w4_firstsale_deliverables` also fails 4 of 6 with `GalleryAwaiting`:
- `test_drifting_rerender_is_refused_never_served`
- `test_kept_bytes_survive_a_redeploy`
- `test_purchase_to_download_rehearsal`
- `test_rerender_must_be_byte_identical_then_kept`

Those tests certify and re-render a release that has no listing-set certificate. The template
correctly refuses a PDF without a certified gallery (D-OWNER-SALE-PIPELINE). Flipping the switch
needs two changes:
1. the pipeline must certify the gallery before it certifies the PDF;
2. those fixtures must carry a certified gallery.

Both belong to the pipeline and integrator lanes. Every other suite measured passes identically
under both layouts.
