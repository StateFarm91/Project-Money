# Review b19-a — base b098fcce (production Batch 17)

Reviewed 2026-11-20 UTC by an independent reviewer. I opened no PRs and read no secrets or Railway variables.

| Unit | Head | Verdict |
|---|---|---|
| A | eng/sale-pipeline @ 1294b143 | **BLOCK** |
| B | eng/garment-2 @ a93888f0 | **SHIP** |

## Unit A: eng/sale-pipeline — BLOCK

### Merge onto b098fcce

Eight files conflict:

- `BUILD_STATE.md`, `DECISION_LOG.md`, `suite_final_segment.txt`: keep both sides.
- `sw.js`: the conflict is in comments only. Keep HEAD (v43).
- `autonomy_map.json`: regenerate it with `python -m brambleloop.autonomy.map --write`. The result is 150 cadences, 183 handlers and 95 edges.
- `ops/readback.py` and `test_w4_readback_evidence.py`: keep both the daily_ledger row and the sale_pipeline row. There are now **21** items, and both rows are advisory.
- `publish/pdf_standard.py`: take the branch side, which is the new D-OWNER-PDF-STANDARD bytes checker. You must also port the base's ENG-PLUSH fix into `publish/premium_standard.py`, because the rename hides it. That fix is `_LABEL = re.compile(r"(?<![Aa]fter )\b(Rows?|Rnds?)...`. Without the port, "Stuff after Rnd 16:" regresses. With the port, `test_eng_plush` passes.

### Tests

The merged run (JOBS=4, 24 suites) passed 466 tests with **1 suite failing**. The suites were:

- the unit's own suites: sale_pipeline, sale_pipeline_e2e, pdf_standard, pdf_template, premium_standard, owner_gallery_complete;
- the suites the branch modified;
- eng_plush, vacuity, w4_resume_runner, compiler, twin, reverse and w4_c12_wiring.

### Mutations

| Mutation | Result |
|---|---|
| `_gallery7`: `ok = True` | KILLED: `test_sale_pipeline_e2e::test_the_checker_fails_a_wrong_logo...` fails. |
| `_finish`: `verdict = FAIL if FAIL in statuses else PASS`, so UNKNOWN folds into PASS | **SURVIVED** `test_pdf_standard` (14 OK), `test_sale_pipeline` (17 OK) and `test_sale_pipeline_e2e` (7 OK). |

### Findings

1. **HIGH — the branch head has a red suite.**
   - `tests/test_search_hero_publish.py::test_certify_assets_seo_grant_publish_creates_exactly_one_draft_with_no_forced_verdict` fails on the unmerged 1294b143 and on the merge. The error is "listing-set certificate 1 names 6 of the 7 required listing photos (D-OWNER-GALLERY-COMPLETE)".
   - On b098fcce the test passes (4/4).
   - The review request's "0 failed" is therefore not true for this suite.
   - **Fix:** make the fixture's certified set reach `CAMPAIGN_MIN_FRAMES` (7), as 6c33484 did for the other fixtures. For example, add the missing gallery supplements before `certify`. Keep a separate assertion that a 6-frame set is blocked.
2. **MEDIUM — the core rule "UNKNOWN is never PASS" has no test that would catch it breaking.**
   - The mutant above survives every suite in the unit.
   - `test_no_expectation_is_unknown_never_pass` cannot catch it, because the engine cover's logo FAIL hides the UNKNOWN, and an unreadable PDF returns early without reaching `_finish`.
   - **Fix:** add a test whose checks are all PASS except one UNKNOWN, and assert both `verdict == "UNKNOWN"` and `pdf_certificates(...)["both_pass"] is False`. For example, build the template edition with `expected=None` so that `slot:gallery7` is UNKNOWN, or make `_cover_logo_check` raise.
3. **MEDIUM — a certificate is not bound to the checker that issued it.**
   - `sale_pipeline.pdf_certificates` matches on slug, version, release, terminology and pdf_sha256 only.
   - `PdfCertificate.checker` and `standard_sha256` are stored but never compared.
   - So a PASS issued by an older, weaker checker, such as one from before the logo and gallery7 checks, still counts toward READY and toward the listing package.
   - **Fix:** in the lookup, require `PdfCertificate.checker == PS.CHECKER_VERSION` and `PdfCertificate.standard_sha256 == (PS.standard_sha256() or "")`. A mismatch yields UNKNOWN, which makes the sweep re-certify.
4. **MEDIUM (PLAUSIBLE) — a certificate is not bound to the current gallery.**
   - The certificate records `gallery_record_id`, but neither `pdf_certificates` nor `ready_for_sale` compares it with the gallery that `gallery_reading` now certifies.
   - Suppose the gallery is re-certified and the chain stalls before `pdf_build` rebuilds. The old premium PDFs, holding the superseded photos, then still satisfy `both_pass`, while `gallery_reading` reports the new set as complete.
   - **Fix:** require `row.gallery_record_id == <current certified listing-set record id>` in `pdf_certificates`.
5. **LOW — a flapping gate resets the stall clock.**
   - `_admission` moves AWAITING_ADMISSION to AWAITING_PRE_IMAGE and back whenever one readiness reading flips, for example a transient UNKNOWN gate.
   - Each state change sets `progressed_at` in `_update`.
   - So an eligible release whose gate flaps never reaches `STALL_AFTER[AWAITING_ADMISSION]` and never becomes an incident.
   - **Fix:** count progress only on forward moves through `STATES`, for example with an `_ORDER` index. Alternatively, keep `progressed_at` when a run returns to a state it held earlier within the bound.

### What I checked and found correct

- The bytes checker reads the built PDF: the cover logo is matched perceptually against `_cover_logo()`, and the 7 gallery slots are checked in certificate order.
- The template path checks sections and page order through `pdf_template.audit` (`page_order` and `stitch_counts`).
- READY requires all four: a certified pattern, the complete gallery, both premium certificates bound to the release's base PDFs, and the listing package READY with no blockers. Any exception is not ready.
- Spend fails closed. `image_production._spend_admitted` returns False when unreadable, and only a generator with `paid is False`, an experiment or a controlled run bypasses it. Admission is ordered by core family and then EV, within the per-listing cap and the month ceiling, and the reservation is released on park or reject.
- A stall becomes a named P2 incident through `sale_pipeline_ops`.

## Unit B: eng/garment-2 — SHIP

### Merge onto b098fcce

The only conflict is `autonomy_map.json`. Regenerating it gives 149 cadences, 181 handlers and 96 edges.

### Tests

| Run | Result |
|---|---|
| Unit run: eng_garment2, eng_families, vacuity, w4_resume_runner, compiler, twin, reverse, w4_c12_wiring | 170 passing, 0 suites failing |
| Wider run (15 suites): garments, garment_design, eng_garment, cert_grading, assembly, the three size-truth suites, family, benchmark_garment, opus2_family_membership, w4_f454_agents, motif_backlog, eng_plush, s1_fix_size_families | 203 passing; only `test_s1_fix_size_families` fails |

- In `test_s1_fix_size_families`, two tests fail: the Large Tapestry case and Baby Lovey. They fail identically on b098fcce, so the failures were already there.
- `test_eng_plush` passes after the merge. The review request lists it as a pre-existing failure, but that was only true on the branch's older cut point.

### Mutation

I changed `graded.py` so that negative ease was accepted on any stretch measure regardless of the limit. It was **KILLED**: `test_a_stretch_fit_takes_bounded_negative_ease_and_nothing_else_does` fails with "{'head': -6.0} accepted".

### What I checked and found correct

- Each size is certified on its own: `certificate.certify` runs per size, followed by `wearable_fit.evaluate`. Per size, that runs:
  - compile, twin, stitch, shaping, section and seam checks;
  - the family gates.

  Across sizes, it checks strict rise of the primary measure and of yarn, and checks that every size uses the same steps.
- All 12 engines have pinned concept-to-PDF proofs, and `test_every_admitted_wearable_pair_has_a_pinned_proof` asserts it.
- The sources are CYC charts and ISO 216 via Wikipedia, with access dates. No competitor text, charts or URLs appear in the diff.

### Findings

1. **LOW — the foot-chart child-safety ages are not lower bounds.**
   - In `cir/graded.FOOT_MONTHS`, "Baby 0-4" is 6 months and "Toddler 5-9" is 24 months.
   - The comment promises the youngest wearable age, but US 0–4 is worn from birth and US 5 from about 12 months.
   - These sizes are held or unused today, so nothing ships incorrectly yet.
   - **Fix:** set them to 0 and 12 (or cite the source row) before any baby or toddler sock or slipper size is admitted.
2. **INFO — an integration risk with unit A, not verified.**
   - Wearables render through `publish.wearable_pdf`.
   - Once unit A lands, READY requires the owner master template (`require_template=True`).
   - Confirm that `pdf_template.build_customer_pdf` renders graded wearable CIRs. If it does not, garment releases will fail closed and park in `pdfs_built` or `pdf_standard_fail`.
