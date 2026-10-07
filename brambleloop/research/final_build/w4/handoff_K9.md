# handoff_K9 — Final Master cluster K9 (pattern Product Truth, graded garments)

Branch: claude/w4-K9 (latest pushed SHA: see `git log -1 origin/claude/w4-K9`).
Tests: tests/test_k9_graded_truth.py (8 tests), tests/test_k9_rows.py (continuation rows). Run:
`cd brambleloop && TMPDIR=/home/user/bl-tmp-K9 PYTHONPATH=src /home/user/Project-Money/brambleloop/.venv/bin/python tests/test_k9_graded_truth.py`

## Rows -> status -> evidence
| Row | Status | Evidence |
|---|---|---|
| F-362 | PROVEN | intel/childrens `measurements_govern_fit` statement; publish/pdf `graded_childrens_assignment` (CYC child sizes -> age band; 14/16 = over 12); test_a_childs_graded_garment_says_measurements_not_age_govern_fit |
| F-750 | PROVEN | Component.work_direction/feature (model.py), cir/topology.py (construction_steps, fingerprint, topology_problems) wired in gates/certificate.certify (TOPOLOGY_INCONSISTENT); writer prints direction; reverse.compare REVERSE_DIRECTION; test_work_direction_is_written_read_back_and_held_to_the_rows |
| F-761 | PROVEN | publish/pdf package_requirements/package_missing; build_pattern_pdf refuses an incomplete package; test_a_graded_pdf_prints_its_size_chart_fit_care_and_is_complete |
| F-762 | PROVEN | CIR.grading size matrix (body/intended/built cm, stitches, rows, yarn_m per size) built by cir/graded; test_every_graded_size_carries_the_whole_size_matrix (yardage monotonic) |
| F-763 | PROVEN | FitIntent.character vs FIT_EASE_BANDS_CM; PDF prints fit + ease table; gates/policy FIT_CLAIMS mismatch refused; test_a_fit_word_must_match_the_stated_ease |
| F-768 | PROVEN | gates/certificate.grading_findings (cir/graded.grading_problems) in certify; test_certify_recomputes_the_size_and_rechecks_the_family |
| F-770 | PROVEN | publish/pdf support_scope printed in Terms and support (supported vs outside-support modifications); asserted in the graded PDF test |
| F-777 | PROVEN | gates/policy claim_findings in check_listing (care/pilling/allergy/speed/reversible untraceable, fit, size-count); test_each_untraceable_claim_word_is_refused. Found + fixed a real defect: creative/certification.listing_for titled garments "Fitted Garment" (a category, not a fit) |
| F-794 | PROVEN | GradedDesign carries benchmarks_consulted into Provenance; test_a_benchmark_informed_graded_garment_needs_its_ledger |
| F-363 | OPEN-DEFECT | next: derive applied parts/ties/closures from CIR (Component.feature button_band/hood + notions) into childrens.Concept; opening-circumference checks |
| F-751 | OPEN-DEFECT | next: star-stitch eye/leg/base anchor model in cir/stitches |
| F-753 | OPEN-DEFECT | next: per-region gauge (F-754) + deterministic apparent-gauge image measure (visual lane) |
| F-755 | OPEN-DEFECT | next: promote research/bench2 all-size parser into teardown/reader.py |
| F-756 | OPEN-DEFECT | next: reconcile stated measurement table vs counts x gauge -> CONFLICT/UNKNOWN |
| F-779 | PROVEN | commerce/listing_tests ListingVariant + activate_variant/variant_findings: check_listing vs CIR (fit, size coverage, untraceable claims) + truth_drift vs certified control (difficulty, materials, construction, stitch appearance, deliverables) + undeclared-field change + uncertified thumbnail/hero refused; tests/test_k9_rows.py test_a_listing_variant_may_not_distort_product_truth. No variant-serving runtime path exists (no Etsy writes); see wiring request |
| F-784, F-795 | PROVEN | gates/originality.similarity_review already compares wording/numeric/features/construction vs both code benchmarks + DB teardown fingerprints, wired in certify + release_gates.originality_gate (store.publish). Added the missing presentation dimension: originality.presentation_review (64-bit dHash of each listing frame vs every manifest image read via teardown.library.retrieve as quality_director for `similarity_review`), material -> SIMILARITY_ESCALATED ERROR, none -> SIMILARITY_UNMEASURED warning; wired in release_gates.originality_gate via _frame_bytes (publish lane: surgical edit, please keep). test_presentation_is_a_similarity_dimension_read_from_the_library |
| F-792 | PROVEN | gates/spec_freeze.py: certify freezes a competitor-informed CIR (audit_log `originality.spec_freeze`: fingerprint, writer_inputs, excluded_from_writer) before write_pattern; findings: SPEC_NOT_FROZEN / SPEC_CHANGED_AFTER_FREEZE (same slug@version, different CIR) / WRITER_CONTEXT_NOT_INDEPENDENT (write_pattern params + cir/writer.py imports checked by AST: no teardown/intel/research/benchmark/gateway/radar); wired in gates/certificate.certify; test_a_competitor_informed_spec_is_frozen_before_the_writer_runs |

## Other changes
- Graded releases re-pinned (procedure in tests/data/release_fingerprints.tsv): harbour 1.2.0->1.3.0, pebble 1.1.0->1.2.0; creative/garment_design SC_WORSTED 1.2.0, DC_DK 1.1.0.
- publish/pdf `_tiled_chart_art` skips tiles with no fabric (ragged shaped rows) -- pebble PDFs raised "twin with no cells".
- creative/certification.listing_for: `fitted_garment` form rendered as "garment" (owner lane CREATIVE: surgical edit, please keep).

## Tests run (all green)
test_k9_graded_truth, test_release_versions, test_graded, test_cert_grading, test_garments, test_garment_design, test_childrens, test_gates, test_reverse, test_cir_roundtrip, test_specification, test_originality, test_certification, test_commerce, test_vacuity, test_secret_scan, test_reachability, test_w3_tmp_hygiene , test_cert_commerce, test_deliverable_qa, test_launch0, test_cert_design, test_schematic

## Wiring requests
- CC/commerce: any future path that serves a listing-test treatment (API or Etsy write) must call `commerce.listing_tests.activate_variant` with the certified control, the release CIR and the certified frame ids, and refuse when `activated` is False (F-779).
- B2/FM lane: flip ledger rows above to their statuses (this lane does not own *ledger*).
