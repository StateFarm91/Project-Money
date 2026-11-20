# Review request — ENG-SALE-PIPELINE

- **Branch:** `eng/sale-pipeline`
- **Head SHA:** `4a47c2af33daa0dd52fe86a2856bcad0d0c36dae`
- **Date (UTC):** 2026-11-20
- **Status:** builder branch. NOT reviewed, NOT integrated, NOT deployed. No PR opened.

## Directives implemented
- D-OWNER-SALE-PIPELINE (HARD RULE)
- D-OWNER-SPEND-ORDER
- D-OWNER-PDF-STANDARD
- D-OWNER-PDF-LOGO
- D-OWNER-PDF-TEMPLATE
- D-OWNER-GALLERY-COMPLETE

New engineering decision: D-ENG-SALE-PIPELINE-1.

## What the chain does

`publish/sale_pipeline.py`, job `sale.pipeline`, entered from `launch.plan`. No owner step.

1. **Admission.** Admission happens only for a certified release that is selected for sale and passes every non-image gate. This includes the pre-image PDF reading.
   - Releases are ordered by expected value, core families first.
   - Admission is bounded in code by the per-listing image cap and the CA$100/month ceiling, with a held reservation.
   - The reservation is released when a release is parked or rejected.
   - `visual.image_production` refuses paid generation for any release that has not been admitted.
2. **Gallery.** The certified 7-photo campaign gallery, as defined in D-OWNER-GALLERY-COMPLETE.
3. **Premium PDFs.** US and UK editions are built in the owner's master template (`publish/pdf_template.build_template_pdf`). They embed the same seven certified frames the listing uploads, so one spend serves both.
4. **PDF certification.** `publish/pdf_standard.check(..., require_template=True)` (checker `pdf_standard/2`) reads the built bytes. It checks:
   - the layout is the owner template;
   - `logo:cover`: a perceptual match to the canonical owner logo as resampled by `publish.pdf._cover_logo`;
   - `slot:gallery7`: exactly the seven certified renditions, in certificate order;
   - the template's own byte audit (page order, header and thank-you logos, no placeholders, no template marker, a count on every row, no uncertified photo);
   - the licence paragraphs;
   - the page range.

   Certificates are bound to this release's `assets.build` hashes.
5. **Attach.** The listing images are attached.
6. **READY.** `store.publish` refuses anything that is not ready for sale. It uploads only the certified premium bytes, and re-reads them against their certificates before the create request.

A stalled release becomes a named-blocker incident. It appears on the board, in Mission Control and in the readback row "sale pipeline (eligible, gallery, PDFs certified, READY, blocked)", which is advisory.

## Merged into this branch
- **`origin/claude/w6-INTEG6` (dde3ea62).** Both sides kept: motif backlog and sale pipeline. Readback evidence now has 20 items.
- **`origin/eng/gallery-complete` (20e81839).** Both DECISION_LOG sides kept.
- **`origin/eng/pdf-template` (309522a3).** Both branches had added `publish/pdf_standard.py`. ENG-PDF-PREMIUM's family-content module is renamed `publish/premium_standard.py`, with its tests in `tests/test_premium_standard.py`. `publish/pdf_standard.py` stays the bytes checker.
- **`autonomy_map.json`** is regenerated: 149 cadences, 182 handlers, 34 agents, 93 follow-on edges.
- **`scripts/suite_final_segment.txt`** keeps both sides: `test_motif_backlog`, `test_sale_pipeline` and `test_sale_pipeline_e2e`.

## Test evidence (`JOBS=6 SUITE_REGISTRY=0 bash run_tests.sh`, Python 3.13)

**Run A: 22 suites at `fd977634`**, record `artifacts/suite_runs/20261120T135246Z-16894.json`.
- 410 passing; 2 suites failing; 0 bytes of temp files leaked.
- Suites in the run:
  - test_pdf_standard, test_premium_standard, test_pdf_template, test_deliverable_qa
  - test_sale_pipeline, test_sale_pipeline_e2e
  - test_w4_ownerimg (35/35), test_w4_readback_evidence (23/23), test_vacuity, test_w4_resume_runner, test_w4_c12_wiring
  - test_motif_backlog, test_owner_gallery_complete, test_visual_factory_e2e
  - test_compiler, test_reverse, test_twin
  - test_search_hero_publish, test_disclosed_certified_upload, test_launch0_listing_truth, test_etsy_readback_observe (38/38), test_cert_publish_gates
- Failure 1: `test_vacuity`, one loop in the merged-in `test_pdf_template.py`. Fixed in `4a47c2af`.
- Failure 2: `test_search_hero_publish::test_certify_assets_seo_grant_publish_creates_exactly_one_draft_with_no_forced_verdict`, blocked with "gallery incomplete: 6 of the 7 required listing photos". **This predates this branch.** It fails the same way on `origin/eng/gallery-complete` (20e81839) as committed; I checked in a separate worktree. It belongs to ENG-GALLERY-FIXTURES.

**Run B: 2 suites at `4a47c2af`** (test_vacuity and test_pdf_template), record `artifacts/suite_runs/20261120T141525Z-4724.json`.
- 34 passing, 0 failing.

**Net at head:** 21 of 22 suites green. The one red suite, test_search_hero_publish, was already red on gallery-complete.

## Tests changed by the merges (reviewer please check)
- **`test_w4_ownerimg`:** the FLUX default-generator test (from INTEG6) now admits the release first. A paid generator runs only for an admitted release (D-OWNER-SPEND-ORDER).
- **`test_motif_backlog` e2e:** the handoff release is blocked by exactly one gallery blocker, the D-OWNER-GALLERY-COMPLETE "6 of 7" one, named. Any other image or gallery gate still fails the test.
- **`test_visual_factory_e2e` b1:** the release has a complete gallery, but no launch decision and a listing package that is not READY. Under the hard rule it is now refused before Etsy. Previously this test published a draft.
  - **Integration item:** there is no longer an end-to-end test of a READY release creating a FakeEtsy draft with read-back through `store.publish`. It needs a fixture that honestly reaches READY: a launch decision, a READY listing package and certified premium PDFs. I did not assert it with a faked READY.
- **`test_etsy_readback_observe`:** the `_publish` fixture calls `_publish_guarded` directly on a synthetic release. It already holds the parity and release gates passing as declared stand-ins. It now also holds `sale_pipeline.certified_premium_pdfs` to its own docs. The real certificate check is covered in test_sale_pipeline and test_sale_pipeline_e2e.
- **`test_pdf_standard`:** engine-layout editions now FAIL on `logo:cover` alone, because the engine cover has no owner logo. With `require_template=True` they also FAIL `layout`.
- **Captions:** in `publish/pdf.py`, the campaign-photo captions go from 8.5pt to 9pt, the brand minimum in `test_deliverable_qa`.

## Known gaps (honest state)
- **Test doubles only.** Everything above is proven with the stub generator and judges, labelled `test_double`. No real gallery, premium PDF, listing, draft or spend exists from this branch. Production counts are UNKNOWN until it is deployed and read.
- **The release chain still defaults to the engine layout** (`runtime.release.PDF_LAYOUT = "engine"`), and engine covers carry no logo. Only template builds can certify. The pre-image reading uses the engine base PDFs for text, schematics and diagrams, with `logo:cover` PENDING there.
- **`test_search_hero_publish`** stays red until ENG-GALLERY-FIXTURES moves it to a 7-frame gallery.
- **Not run here:** the full suite (`THEN_FULL=1`). Other suites that publish through `store.publish` may need the same fixture treatment as above.
