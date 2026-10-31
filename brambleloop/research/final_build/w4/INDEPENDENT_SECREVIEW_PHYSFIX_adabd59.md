# Independent integrity review: W-PHYSFIX `adabd597` (+ PHYSFIX-PHOTO `23efd5dc`)

**Date:** 2026-10-31 (UTC). **Reviewer:** an independent Claude Code session. No PR opened, nothing
pushed except this report and its adversarial test file.

**Subject.**
- `claude/w4-PHYSFIX` @ `adabd597` vs `claude/w4-INTEG8-next` @ `b0133916` (merge base). Main
  commit `74487340`; includes W4-SAMPLE `ef3f4015`.
- `claude/w4-PHYSFIX-PHOTO` @ `23efd5dc`: LAUNCHFIX `0f0306dd` + PHYSFIX + ordering commit `f2a6ea29`.

I read `PHYSFIX.md` and judged the code. (A two-dot diff against the *current*
`origin/claude/w4-INTEG8-next` (`2eeb904b`) shows `COORDINATION.json`,
`BRANCH_OWNERSHIP.md`, `RESTART_CHECKPOINT.md` and `test_w4_owner_queue_race.py` as deleted. That is
only because INTEG8-next moved on after `b0133916`. PHYSFIX itself deletes none of them, as
`git diff b0133916 adabd597` shows.)

## Verdict: **DO NOT SHIP**

Most of the fix is sound. The partial-make accounting, the PARTIAL routing, the one-size-per-sample
rule and the photo-first ordering all hold up under adversarial input. But the new size-halt
exception can be lifted by **relabelling the version only**. Chained with a swatch, which now passes
and counts as the `partial_physical` evidence that meets the first-customer floor, a release whose
size a tester has already proven wrong clears the first-customer gate. The chain changes no
geometry, and the listing then reports the size as "physically proven". A separate bug: the intake
reads the text answer `"no"` to "followed exactly?" as *yes*.

## Findings

| # | Severity | Finding | Introduced by |
|---|---|---|---|
| F1 | **HIGH** | Size halt lifted by a version-only relabel of identical content | PHYSFIX (G4) |
| F2 | **HIGH** | `instructions_followed: "no"` (string) is stored as followed → sample PASSES | pre-existing, left in the rewritten intake |
| F3 | **MEDIUM-HIGH** | A gauge swatch alone "physically proves" a size and meets the coaster/basket first-customer floor | PHYSFIX (made swatches passable) |
| F4 | MEDIUM | Blank "followed exactly?" on the record sheet becomes `True` | pre-existing default, kept in `tester_kit.intake_payload` |
| F5 | LOW | A problem written in `notes` (not `problem_notes`) is WARNING only and the sample passes | design |
| F6 | LOW | Coaster kit measures one coaster; the other three sizes go to free-text `notes`, unchecked | PHYSFIX kit |
| F7 | LOW | `parts_made` docstring says a component sample is partial "even when the pieces add up to the whole", but returns `whole_pattern=True`. The evidence class is still `partial_physical` (verified), so this is a documentation mismatch only | PHYSFIX |

### F1 (HIGH): relabelling the version lifts the size halt and resolves it

`gates/certificate._release_hash` hashes `cir.to_dict()`, which includes `version`. Bumping
`1.2.0` → `1.2.1` with byte-identical geometry and text therefore produces a "different content".
`IncidentTracker.publication_halted(..., content_hash=)` lets it certify, and
`resolve_superseded_release_halts` then **resolves** the P1 incident for the whole product.

The shipped test `test_a_size_mismatch_halts_that_release_and_only_a_corrected_content_lifts_it`
uses only a version bump plus a title suffix as its "corrected content". It therefore encodes this
behaviour instead of catching it: nothing checks that the correction changed anything the size
depends on.

Repro: `test_relabelled_identical_content_does_not_lift_size_halt` (FAILS: certification is
granted and the halt is resolved).

**Fix direction.** Key the release scope on a version-independent geometry/text digest (for
example, the hash of the CIR without `version`, plus the pattern text with the version line
stripped). Or require the superseding content's twin to differ in a stated finished dimension.
Neither path should resolve the incident on certification alone; resolve it when the new content
has its own passed **full make**.

### F2 (HIGH): the string `"no"` for instructions_followed counts as yes

`runtime/release.py` `handle_physical_record`:
`instructions_followed=bool(i.get("instructions_followed", True))`. `/api/physical-test` passes the
raw JSON through, so `"no"` (or `"false"`, `"0"`) is truthy. No `SAMPLE_DEVIATED` finding is raised.
The row is `passed=True`, it binds as evidence, and it can calibrate.

PHYSFIX added a strict `_flag()` parser for `lies_flat` / `holds_shape` in the same function but
did not apply it here. A missing answer also defaults to `True`.

Repro: `test_instructions_followed_no_as_text_is_not_a_pass` (FAILS: stored `passed=True` with no
findings). Fix: `_flag("instructions_followed")`, and refuse `None`.

### F3 (MEDIUM-HIGH): a swatch proves a size and satisfies the first-customer gate

A gauge swatch now PASSes as `partial_physical`. Before PHYSFIX it was effectively refused as
`SAMPLE_FACTOR_IMPLAUSIBLE`.

- `risk_matrix.first_customer_requirement` takes `partial_physical` as the floor for Class A/B.
  So a swatch alone meets the coaster set's first-customer requirement, although the coaster kit
  states the product's one physical claim is "it lies flat" and a swatch records no flatness. The
  same holds for the Class B medium basket.
- `quality.physical.size_coverage` reports a size as **`proven`** whenever any passed sample binds,
  so a swatch makes the first-customer evidence text say "physically proven sizes: ['small']".
  `PARTIAL_PHYSICAL`'s own description says it cannot prove "whole-object size". That is a
  Product Truth misstatement.

Repros, both FAIL:
- `test_a_swatch_alone_does_not_prove_a_size`
- `test_a_swatch_alone_does_not_clear_coaster_first_customer`

**Fix direction.** `size_coverage` should count only made pieces with `size_agrees is True`. The
risk matrix spec allows swatch partial evidence for Class B gauge risk, so whether a swatch should
meet the *first-customer* floor is the owner's policy call. At minimum the gate must not describe
it as size proof.

**Chained with F1:** `test_chain_relabel_then_swatch_clears_first_customer_with_known_wrong_size`
FAILS. The steps are:
1. A full make of `market-basket-medium@1.2.0` measures 40 cm, so the size is FAIL and a P1 halt
   opens.
2. Re-certifying the same geometry as 1.2.1 is granted, and the halt is resolved.
3. A swatch on 1.2.1 passes.
4. `first_customer.met == True` and nothing halts. The release's size is known to be wrong.

### F4 (MEDIUM): a blank sheet answer becomes "followed"

`tester_kit.intake_payload` skips blank fields and then does
`payload.setdefault("instructions_followed", True)`. That contradicts its own docstring: "a field
left blank is left out, so the intake decides". Repro: `test_blank_followed_answer_on_sheet_is_not_read_as_yes`
(FAILS).

### F5 / F6 / F7 (LOW)

- **F5.** Free-text `notes` raise only a WARNING. A tester who writes a problem under notes rather
  than in the problems box gets an auto-pass. Repro: `test_problem_written_in_notes_only_still_passes`
  (FAILS). Consider routing any non-measurement note text to REVIEW.
- **F6.** The coaster sheet compares the size of one ("furthest") coaster only. The other three go
  to `notes` and are never compared.
- **F7.** Documentation mismatch only; see the table.

## Answers to the six questions

1. **Can a partial make count as whole, or distort calibration? No, apart from F1/F3's
   size-proof side effects.**
   - `full_make` with `made` short of the whole is refused. A multi-piece `full_make` with no
     `made` is refused, and so is an unscoped measured sample of 2 of 4
     (`test_partial_make_cannot_be_forced_full_with_measurement_and_no_scope` OK).
   - `record()` refuses to stamp a non-whole make as anything but `partial_physical`.
   - `estimate_for_parts` scales per-component twins by count/make, so 2 of 4 coasters gives the
     true factor 1.0.
   - A swatch has `factor=None` and never calibrates.
   - A component that covers the whole set is still `partial_physical`
     (`test_component_covering_whole_set_is_still_partial_class` OK).
   - Residual: a 1-coaster component PASS does calibrate DK cotton. That is mathematically correct
     but noisy at a 1 g scale resolution (LOW, not filed).
2. **Auto-pass with flat/shape false or missing, or with problem notes? No.** Missing → ERROR and
   refused at intake. False → REVIEW → PARTIAL, `passed=False`, an owner action, and no calibration
   (`usable_for_calibration` excludes REVIEW). Verified by `test_lies_flat_false_with_holds_shape_true_on_coaster_is_partial`
   and `test_partial_outcome_never_calibrates_even_with_off_factor`, both OK. The exceptions are F2
   (deviation read as followed) and F5 (problems in `notes`). The path with no CIR skips shape
   checks, but the only production caller always passes the CIR.
3. **Size halt.**
   - It does not halt unrelated products (`test_size_halt_does_not_halt_another_product` OK): the
     incident carries `product_slug`, and `open_incidents` filters by it except for
     `systemic-halt:%`. Non-certify publication paths still see it product-wide until it is
     resolved, which is the intended direction.
   - If the content hash is unknown, `release_scope()` returns `{}` and the halt stays
     product-wide (fails closed).
   - The exception can be abused (F1). A different *product* cannot lift it, because
     `resolve_superseded_release_halts` filters by slug.
4. **`covers_size`: No.** `size` must equal this release's size or slug. A comma list, or a
   non-string such as a list, is an ERROR. `compatible_variants` and `sizes` are refused, and
   binding goes by content hash per size (`test_a_sample_claiming_another_or_several_sizes_is_refused`
   OK). The defect is F3: *what* counts as proving the one size.
5. **Photo-first: No bypass found.** `_leads_gallery` requires all of:
   - `detail.unedited is True` (strict, so the string `"true"` does not count), and neither
     `edited` nor `ai_processed`;
   - the photo's own `physical_test_id` with `passed is True`, `completed_at` set, and the same
     slug and version;
   - `physical_class_of == full_physical_make`.

   A PARTIAL row (`passed=False`), a swatch or component (`partial_physical`) and another
   release's row are all excluded. Content-hash binding is re-checked at publication by
   `publish.sample_photo._bound_full_makes`. Residual (LOW): a legacy unstamped row reads as a full
   make by `physical_class_of`, so a pre-PHYSFIX row that was really 2 of 4 coasters could lead.
   It would still face the publication-time content check.
6. **Changed tests: no weakening of an existing guarantee, with one caveat.**
   - **Fixtures.** They add `holds_shape=True` and `scope="full_make"`, which the new rules
     require. `test_physical_record_blocked` adds a 9.5 cm width for a sphere whose twin cannot
     compare it, so the size is not falsified there. That gap is pre-existing.
   - **Size-halt test.** It was strengthened: the old `or incidents[0].severity` was a tautology,
     and the test now asserts exactly one halting P1.
   - **Unscoped-swatch test.** It now asserts that an unscoped sample is refused (stricter) and
     still asserts that Class C stays blocked. It newly pins `passed is True` for a swatch, which
     encodes the behaviour behind F3.
   - **Caveat.** The *new* `test_physfix` size-halt test treats a version + title relabel as a
     correction. It encodes F1.

## Suite runs (`PYTHONPATH=src:tests nice -n 19 python tests/<f>`, one at a time)

All exit 0, with no failures:
- PHYSFIX `adabd597`:
  - `test_physfix`: 17/17
  - `test_physical`: 18 OK
  - `test_physical_record_blocked`: exit 0
  - `test_risk_matrix`: exit 0
- PHOTO `23efd5dc`:
  - `test_physfix_photo_first`: 4/4
  - `test_physfix`: 17/17
  - `test_w4_launchfix`: 22 passed, 0 failed

The shipped suites are green. The findings come only from the adversarial tests below.

Adversarial file: `brambleloop/research/final_build/w4/secreview_physfix_adversarial_tests.py`.
Copy it to `brambleloop/tests/` on a PHYSFIX checkout to run it. Result on `adabd597`: **5/12
pass**. The 7 failures are F1, F1+F3 chain, F2, F3 ×2, F4 and F5. Each test asserts the safe
behaviour.

## Required before SHIP

1. **F1.** Make the release scope version-independent, and resolve the halt only when the
   superseding content has its own passed full make with `size_agrees is True`. Replace the
   relabel-based test with one that proves a relabel stays halted.
2. **F2/F4.** Parse `instructions_followed` strictly and refuse it when missing.
3. **F3.** `size_coverage.proven` should count only made pieces whose size agreed. The owner
   should rule whether a swatch may meet the first-customer floor for a product whose claim is
   flatness or finished size.
