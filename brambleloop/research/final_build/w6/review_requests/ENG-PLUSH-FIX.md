# [ENG-PLUSH-FIX] Review request: fixes for the DO NOT SHIP review of 2763340b

- **Branch:** `eng/plush`.
- **Code and test SHA:** `f95e6036bcd9727bdb6467190980d8d32ca0bbb0`. Every later commit on the branch changes only docs (BUILD_STATE, results, and this file).
- **Merged:** `claude/w6-INTEG6` dde3ea62. DECISION_LOG and suite_final_segment were union-resolved, and `autonomy_map.json` was regenerated.
- **Review:** `origin/review-results/plush-2763340b:VERDICT.md`.

## Findings

| Finding | Fix | Test |
|---|---|---|
| H1 vacuity | non-empty asserts before every flagged loop | test_vacuity green |
| H2 final segment | `tests/test_eng_plush.py` is declared in `scripts/suite_final_segment.txt` | test_w4_resume_runner green |
| H3 results | `plush_results.md` has measured counts. The mutation harness requires a green baseline and reports an import or environment error as ERROR, never as KILLED. The survivor is killed. | `test_mutation_harness_reports_an_import_error_as_an_error_not_a_kill`; 65/65 |
| M1 hard parts | eye and nose clauses are an allow-list (they must say embroidered). Materials are an allow-list (MATERIALS_KNOWN: unknown is UNKNOWN). Attachments are an allow-list (ATTACHMENTS_KNOWN: unknown is UNKNOWN). | one generated test per probe (`test_probe_m1_*`, `test_probe_attachment_*`) |
| M2 cords and loops | widened loop, tie and pram words. Chain runs are summed across ops and repeats. | one test per probe (`test_probe_m2_*`) |
| M3 certify | certify passes the catalogue's children's assignment | `test_m3_*` |
| M4 age | AGE_SUITABILITY reads the band. The age text claims small parts only when that check is shown. | `test_m4_*` |
| M5 survivor | direct test | `test_m5_*` |
| L2, L3, L4 | quotes re-read, uncompiled closure is a finding, depicted-piece colours only | `test_l2_*`, `test_l3_*`, `test_l4_*` |

## New in this round: eye options

- `child_safety.eye_options(band, profile)` sets the default to embroidered, and embroidered is the only option allowed.
- A baby or a child under 3 gets the "only option" reading with 0 to 36 months guidance. That covers the under-3 band, a sleep-profile item, no assignment, and an unknown band.
- An older band gets its band label and the US cautionary statement.
- The PDF prints an "Eye options" statement for every face or stuffed item.
- The new text check AGE_GUIDANCE_IN_TEXT fails a document whose eye options print without their age guidance.
- Tests:
  - `test_eye_options_*`
  - `test_the_toy_and_lovey_pdfs_print_the_eye_options_and_age_guidance`, which reads text extracted from real PDFs for under_3 and three_to_six.

## Counts (measured)

- **Suites:** run `20261120T130816Z-22908` at f95e603, tree clean.
  - 30 suites: the review's 27, plus test_vacuity, test_w4_resume_runner, test_garments, test_fastlane and test_s1_fix_size_families.
  - **565 passing, 0 failing.**
- **Mutation:** `scripts/mutate_plush.py` at f95e603. **65 of 65 killed, 0 survived, 0 errored.** The baseline was green.

## Honest state and limits

- Every stuffed or sewn toy is still HELD on PHYSICAL_EVIDENCE. Cushions are still held for the owner's decision (see the owner action in `plush_results.md`).
- `research/benchmarks/TEARDOWN_*.md` is not in this tree or in INTEG6. No claim about competitor safety guidance is made.
- The ENG-PLUSH session's re-run of five timed-out suites was never recorded. They are listed as not run in `plush_results.md`.
