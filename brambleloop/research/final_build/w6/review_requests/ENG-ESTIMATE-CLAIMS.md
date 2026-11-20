# ENG-ESTIMATE-CLAIMS: calculated-estimate path for `gauge_and_size_claims`

Branch `eng/estimate-claims`, from `eng/colourwork` @ b098fcce (production).
**Not merged, not deployed; production unchanged. No PR opened.** No Railway variables or secrets were read.
Everything is measured on fixtures; no production listing was re-run.

- **Tested SHA:** `a6c57d5aac1cd5b0cb90db46f683314fb8262f15`. Commits after it touch only this file and BUILD_STATE.
- **Decision:** D-OWNER-ESTIMATE-CLAIMS in `DECISION_LOG.md`.

## What changed
- **`gates/estimate_claims.py` (new).** With no physical sample, a gauge or size claim passes only if all three hold, on
  every surface: the PDFs (text read back off the bytes), the listing title and description, and the alt text.
  1. **Accuracy.** Every finished-size figure equals a twin dimension within `risk_matrix.DIMENSION_TOLERANCE`, and
     every "N sts x M rows = 10 cm" figure equals the CIR gauge.
  2. **Labelling.** Each size claim carries estimate language ("approx.", "calculated", and similar). The PDFs and
     the listing carry the owner's gauge note verbatim.
  3. **No physical implication.** Nothing says "measures", "measured", "tested", "as pictured", "as shown", "true
     to size", "actual size" or similar. Honest negations are removed before the scan: the note itself, "not yet
     measured" and "rather than measured".
- **`gates/first_customer.py`.** `check_gauge_and_size_claims(..., estimate=...)` takes the estimate path only when
  there is no physical pass: either physical evidence is missing, or the twin is uncalibrated. A pass reads
  `PASS` with a detail starting "ESTIMATE:"; any finding reads `FAIL`.
  - Any child-safety physical test still needed (a stuffed or sewn toy, lovey or amigurumi) gives `UNRESOLVED`;
    estimate wording never waives it.
  - The measured path is untouched; when real physical evidence exists it is read as before.
  - No surfaces, no listing or document refusals also give `UNRESOLVED`, as before.
- **Writers.** When `twin.calibrated` is false:
  - **`publish/pdf.py`:** the cover reads "approx. ...". The at-a-glance row reads "approx. ...: calculated
    finished size (computed, not yet measured on a worked sample)". The gauge section carries the note. The
    schematic labels read "Calculated finished measurements".
  - **`commerce/seo.py`:** the size line reads "approx. ..., calculated finished size at the gauge below", and the
    note follows it.
- **`runtime/release.py`:** `CHAIN_VERSION` is bumped 8 → 9, so stored v8 PDFs and copy go stale and rebuild with
  the estimate wording. Without the bump, the gate would check fresh text while customers got the old files.
- **`autonomy_map.json`:** regenerated; only the timestamp changed.

## Not changed
- Child-safety physical evidence: `child_safety.evaluate` still reports HELD for toys.
- Sample-photo truth (`SAMPLE_PHOTO_REQUIRED` still blocks).
- The listing tester-claim rules.
- The measured path.

## Tests: `tests/test_estimate_claims.py`, 9 OK, 0 FAIL
- **Estimate wording with no sample:** PASS, both through `check_gauge_and_size_claims` and through `gate_product`.
- **Number differs from the twin:** FAIL in the listing, in the PDF, and in the gauge.
- **Wording that implies measurement:** FAIL in the listing, the PDF and the alt text. Honest negations stay PASS.
- **Missing approx. label or note:** FAIL. A surface with no readable claim also FAILs.
- **Child safety:** the amigurumi fixture stays UNRESOLVED, and `child_safety` still reports HELD.
- **Measured path:** unchanged.
- **Mutations:** each one must make a test fail, and each does.
  - Blanking the estimate-language pattern.
  - Replacing `_has_note` with an always-true stub.
  - Blanking the physical-implication pattern.

## Suites
Run serially or in small batches on a 4-core container under load. "exit 124" means the run.sh 1500 s cap
was hit; those suites were rerun alone with a 3000 s cap.

**Required by the brief: all green.**

| suite | OK | FAIL |
|---|---|---|
| test_estimate_claims (new) | 9 | 0 |
| test_first_customer_gate | 12 | 0 |
| test_cert_publish_gates (release gates) | 18 | 0 |
| test_w4_cap1_gates_intact | 5 | 0 |
| test_launch0_listing_truth | 14 | 0 |
| test_k8_listing_estate | 9 | 0 |
| test_pdf_standard | 23 | 0 |
| test_pdf_premium | 27 | 0 |
| test_pdf_layout_bounds | 3 | 0 |
| test_deliverable_qa | 61 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |

**Wider set: green.**

| suite | OK | FAIL |
|---|---|---|
| test_compiler | 9 | 0 |
| test_reverse | 18 | 0 |
| test_twin | 8 | 0 |
| test_eligibility | 34 | 0 |
| test_friction | 19 | 0 |
| test_eng_plush | 25 | 0 |
| test_provenance_backfill | 12 | 0 |
| test_opus2_chain_deadends | 18 | 0 |
| test_w4_placemat_reprice | 4 | 0 |
| test_cert_commerce | 14 | 0 |
| test_risk_matrix | 17 | 0 |
| test_eng_stale_rebuild_loop | 20 | 0 |

**Failures, each compared against base b098fcce.**

| suite | this branch | base | note |
|---|---|---|---|
| test_w6_listing_chain_e2e | 3 OK / 3 FAIL | test_a ×2 and test_b fail identically ("stages ran N times") | test_c updated: `gauge_and_size_claims` no longer blocks; the remaining blockers are `etsy_remote_state` and `SAMPLE_PHOTO_REQUIRED` |
| test_cert_rebuild_chain | 8 OK / 3 FAIL | 8 OK / 3 FAIL, the same two tests | already failing on base |
| test_opus2_size_claims | 12 OK / 1 FAIL | the same graded 9-sizes test fails | already failing on base |
| test_physfix | 47 OK / 1 FAIL | `basket_small` kit rebuild fails identically | committed tester kits are a record of what testers were sent; not touched |
| test_platform | 21 OK / 1 FAIL (`no such table: radar_concepts` in the cadence survival test) | the same test fails identically when run alone on base (`no such table: radar_concepts`); the full base suite run hit the 30-min background limit before reaching it | unrelated to this change |
| test_product_run | 3 OK / 0 FAIL, then timed out at 3000 s | not run | **incomplete, not a pass** |

## Honest gaps
- **Spec PDF.** `spec/07_Brambleloop_Master_Pattern_Template.pdf` is not in the repository on any branch I checked.
  The decision quotes the template text as given in the brief (spec 07, pp. 3–4) and says so.
- **Blocking instruction.** `cir/writer.py`'s "Block to ..." instruction feeds the release hash, so I left it
  alone. The checker treats blocking instructions as instructions, not claims, but still checks their figures
  against the twin.
- **Uneven strictness.** When physical evidence is present but at an unmet tier, the result stays UNRESOLVED,
  while a product with no sample at all can PASS on estimates. This is deliberate (a partial physical record is
  not ignored), but the reviewer should confirm it.
- **Production.** No production listing was re-run. The chain e2e on fixtures is the end-to-end evidence that
  produced PDFs and copy clear `gauge_and_size_claims` as ESTIMATE. Production listings stay blocked on
  `SAMPLE_PHOTO_REQUIRED` and `etsy_remote_state`, which this change does not touch.
- **Rebuild.** CHAIN_VERSION 9 forces the stale-rebuild loop to regenerate every v8 PDF and listing on deploy.
