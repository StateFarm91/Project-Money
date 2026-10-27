# W-PHYSFIX: the physical-sample path, fixed at the root

**Branch:** `claude/w4-PHYSFIX`, cut from `origin/claude/w4-INTEG8-next` (`b0133916`) with
`origin/claude/w4-SAMPLE` (`ef3f4015`) merged in (a fast-forward). Date: 2026-10-27 (UTC).

**Why it matters.** Every first listing now depends on this path. Etsy requires a real photo of
a made sample for a pattern listing, so the first tester's sample is the first real input to
the first-customer gate. The reviewer's defects are the gaps G1-G5 in
`PHYSICAL_SAMPLE_PACKAGES.md` §6, plus the kit errors in its §1.2.

**Nothing external happened.** No tester was contacted, nothing was bought or sent, and no
production database was written. No gate was weakened: every change makes the intake stricter or
more exact, and each gate condition that existed still holds.

**Scope.** The edits stay in the physical-intake, cost and tester-kit modules, plus two small
hooks:
- `quality/physical.py`, `quality/tester_kit.py`, `runtime/release.py` (`handle_physical_record`
  only), `gates/risk_matrix.py` (`owner_action_spec` and one class description);
- `gates/incidents.py`: an optional argument, plus one new method;
- `runtime/pipeline.py` (`handle_certify`): the halt check and one call after the grant;
- `gates/first_customer.py`: `physical_binding` and the two messages in
  `check_gauge_and_size_claims`. `check_etsy_remote_state` and readiness were not touched.

`app/main.py`, `/api/verify`, `publish/pdf.py`, readiness and the policy form are untouched. The
`/api/physical-test` route passes its payload to the job unchanged, so every new field travels
through it without an API edit.

---

## 1. Partial makes are compared against exactly the parts made (G1)

**The defect:**
- `quality.physical.assess` divided the measured yarn by the twin's yarn figure for the whole
  pattern. A swatch, or a single coaster, was refused as `SAMPLE_FACTOR_IMPLAUSIBLE`.
- Two coasters of four passed with a factor of 0.50, and `calibration_from_db` would then have
  halved DK-cotton yardage.
- A related bug: for a pattern with more than one *kind* of component, the whole-pattern
  estimate was the first component's only.

**The fix:**
- **The intake records what was made.** `SampleReport` carries `scope` (`full_make`,
  `component` or `swatch`) and `made`, a map of each component to the number made, for example
  `{"coaster": 2}`.
- **`physical.parts_made(cir, scope, made)` is the single rule:**
  - a **full make** is every component, `make` times each. A pattern of more than one piece must
    state `made`. A `made` short of the whole is refused ("a partial make is recorded with scope
    component, never as the whole pattern").
  - a **component** sample names its pieces, each between 1 and that component's `make`. It is
    always partial evidence (`whole_pattern` is recorded).
  - a **swatch** makes no pieces.
- **`physical.estimate_for_parts`** gives the estimate for exactly the pieces made: each
  component's twin yardage ÷ `make` × the count made. `assess` compares against that figure.
- **A swatch is gauge evidence only.** It must report stitches and rows per 10 cm. These are
  checked against the CIR gauge at the same 12% as size (`GAUGE_DISAGREEMENT`).
  - It never has a factor and never calibrates.
  - It may not carry finished measurements.
- **Defence in depth:**
  - `record()` refuses to stamp a non-whole sample with any class other than `partial_physical`.
  - The handler refuses a sample that has neither a scope nor a finished measurement. The
    legacy inference ("no measurement means partial") compared an unknown set of parts against
    the whole pattern.
  - An incomplete or self-contradictory record (scope invalid, shape unanswered, swatch gauge
    missing, measured piece unnamed, wrong size) is refused before anything is stored.
- **Unchanged:**
  - The first-customer requirement is still class-based: `first_customer_requirement` needs
    `partial_physical`, or `full_physical_make` where the risk class needs it.
  - The binding rules (`bind_physical_evidence`) are unchanged.

## 2. What is priced is what the intake accepts (G1/G2 pricing)

- `risk_matrix.owner_action_spec` keeps its prices: CA$32.40 for a swatch, and
  make-hours × 1.3 for a full make.
- The partial offer is now explicitly a **gauge swatch** (`scope swatch`: stitches and rows per
  10 cm, hook, ball band and grams; **no finished measurements**). The intake accepts it, as
  section 1 describes.
- The old "(or the named component)" is removed, because a component make would need its own
  pieces named and priced.
- The full-make offer now names everything the intake requires: which pieces were made (all of
  them), finished measurements, lies flat or holds shape, and any problem.
- Each spec now returns `intake: {scope, fields, evidence_class}`. The fields come from
  `quality.physical.SCOPE_FIELDS`, the same table the intake is written against.
- A test builds the payload from the offered fields alone and runs it through
  `physical.record`. It is accepted and passes as `partial_physical`.

## 3. Flatness, shape and the tester's problem notes (G3)

**New protocol fields:**
- `lies_flat` is required when the sample includes a flat piece (`flat_rows`, or a round piece
  whose twin shape is `disc`).
- `holds_shape` is required when it includes a three-dimensional piece (any other round shape:
  vessel, sphere and so on).
- `problem_notes` is the tester's free text about anything wrong.

**Outcomes** (`SampleAssessment.outcome`):
- **PASS**: no ERROR or REVIEW finding, plus a factor for a made piece, or an agreeing gauge
  for a swatch. Only a PASS sets `PhysicalTest.passed`, binds as evidence and calibrates.
- **PARTIAL**: any of `SAMPLE_NOT_FLAT`, `SAMPLE_SHAPE_NOT_HELD` or `SAMPLE_PROBLEM_REPORTED`
  (severity `REVIEW`). The row is stored with `passed=False`, binds nothing and calibrates
  nothing (`usable_for_calibration` excludes REVIEW).
  - The handler opens an owner action, `physical_review:{slug}@{version}:{row}`, that names the
    problem. It does this once per row and audits `physical.owner_review`.
  - No software path promotes a PARTIAL to a PASS. The owner decides between a pattern fix
    (a new release, then a re-test) and a repeat sample.
- **FAIL**: an ERROR finding, or a size outside tolerance. Stored, and binds nothing.
- **The shape answer is required.** A made piece with no answer is refused at intake
  (`SAMPLE_SHAPE_UNRECORDED`).
- **The general `notes` field is unchanged:** a WARNING, which does not block. Problems now have
  their own field, and the kits map the sheet's "anything unclear or wrong" box to
  `problem_notes`.

## 4. A size mismatch halts that release (G4): behaviour changed to match the description

The docstring said that a size disagreement "halts its publication". The code filed one P2
`DefectReport`, and `IncidentTracker` halts only at 3 reports. I made the behaviour match the
description, scoped as the spec requires:

- **The handler opens one P1 incident with `halts_publication=True`**
  (`open_or_restate`, signature `physical-size:{slug}@{version}:{hash16}`).
  - Its detail carries `release_scope: {slug, version, content_hash}`.
  - Every existing publication reader honours the halt: `gate.certify`,
    `release_gates.staleness`, `retry_hold_reason`, `commerce.lanes` and the others.
  - One report is enough.
- **Spec basis:**
  - Acceptance Tests: "P0/P1 incident can halt publication workflow".
  - F-168: "Block affected publication scope rather than whole company".
  - F-078: evidence and its invalidation are bound to the exact content.
- **The affected scope is that release's content.** Halts in this codebase are keyed by product
  slug, so a plain slug-wide halt would also refuse `gate.certify` for the *corrected* release.
  That deadlock could be cleared only by hand. So:
  - `IncidentTracker.publication_halted(slug, content_hash=...)` is passed a content only by
    `handle_certify`. It lifts **only** halts that are release-scoped to a *different* content.
    Any product-wide halt still refuses, and every other caller is unchanged.
  - When a corrected content is certified, `resolve_superseded_release_halts` resolves the old
    release's halt and audits `physical.size_halt_superseded`.
  - The corrected content binds none of the old sample (F-078), so it still needs its own sample
    before any first customer.
- The first-customer block (`gauge_and_size_claims` UNRESOLVED) still applies independently.

## 5. Kits (G2 and the record sheet): regenerated through one builder

- **One builder.** `quality.tester_kit` now holds a `KITS` table (`basket_small`,
  `hexagon_coasters`). `build(out_dir, key)` builds either kit, and
  `intake_payload(sheet, content_hash=..., key=...)` maps either sheet.
  - `research/final_build/w4/tester_kit_coaster.py` no longer swaps module constants. It builds
    each kit twice, refuses to write if the two builds differ, then writes the kit. `--check`
    compares against the committed kits.
- **The re-weigh step.** Both protocols' swatch step ends: "then RE-WEIGH each ball and use that
  as its start weight, so the swatch's yarn is not counted as project yarn". The grams step says
  "re-weighed start minus end".
- **No step is cut off.** The record sheet wraps each step at 110 characters, never splitting a
  word or a hyphenated path. The old `[:118]` truncation is gone. The basket's step 3 now prints
  in full.
- **New sheet fields:**
  - pieces made, in `made.<component>`;
  - the swatch's stitches and rounds as numbers;
  - "holds its shape?" for the basket, or "all four lie flat?" for the coasters;
  - the problems box, mapped to `problem_notes`.
- **Payload and manifest.** The payload carries `scope`, `size` and `made`. The manifest records
  `pieces`, `covers_size` and the outcomes. A disc's manifest names `across_points` and
  `across_flats` only, with no "wall_height".
- **Cost check.** `build` recomputes the quoted ceiling with `owner_action_spec` and refuses to
  build if the static figure disagrees: CA$59.65 for the basket, CA$92.03 for the coasters.

**Digests.** Each kit was rebuilt twice and both builds were identical. The TEST.pdf digests and
content hashes are unchanged. The record sheets changed.

| File | sha256 |
|---|---|
| `market-basket-small-1.2.0-TEST.pdf` (unchanged) | `a724cbae5d58ff469a991668d257f54dce57c7e0d0437bcb323ecca2bfb72b0c` |
| `market-basket-small-1.2.0-RECORD-SHEET.pdf` (was `335fd7aa…`) | `ed68e9409f0d9aa9332c48f9784a9280c173925f8b555cd3ade2e48053023e42` |
| `KIT_MANIFEST.json` | `95f4befaa7cd16c9f3f93862017994eabb2573f084d868c30a04379b5b8df0ff` |
| `hexagon-coaster-set-1.2.0-TEST.pdf` (unchanged) | `7d10fc229525b650a3a2d77171c36842a9c46abab4213157a04cedafb4739909` |
| `hexagon-coaster-set-1.2.0-RECORD-SHEET.pdf` (was `892484a8…`) | `ded8995eba32060f6d3559d735934fb84b9e206310a495f3b0a01607ee4e2b17` |
| `KIT_MANIFEST_hexagon-coaster-set.json` | `6a43f3f7b9fc536985a40c9ce774a51317229ec9e930b244d7093efe98759cf8` |

Content hashes (unchanged):
- basket: `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991`
- coasters: `3754ed17a63b790dc2c04b0f744de3fad34e5893ca69c0ff9f0c7cb41090937b`

**Owner-approval kit (coordinator request, same day).** The basket kit was also given:
- a "base sits flat?" field: a "no" routes to PARTIAL even on a vessel;
- Etsy's unedited-photo shot list, with the hero as the first shot, per `ETSY_IMAGE_COMPLIANCE.md`
  §5.1 (the coaster kit got its §5.2 list);
- the positioning "kitchen and home; small size only".

The approval summary, with costs, measurements, turnaround and the failure path, is
`tester_kit/BASKET_KIT_FOR_OWNER_APPROVAL.md`.

**Open:** the test PDF (the customer PDF) still prints a children's/nursery safety block on
pages 7–8. It comes from `launch0.childrens_assignment` (`nursery-nesting-baskets`), and only the
LISTING1 source correction can remove it. The PDF is not patched by hand.

## 6. A sample covers exactly one size (G5)

- **What a sample covers.** `physical.size_identity(cir)` gives the one size a sample covers:
  the release, plus its Launch-0 variant key or graded size, for example `small` in
  `nursery-nesting-baskets`. It is stored on every row as `covers_size`.
- **What the intake refuses:**
  - `compatible_variants` and `sizes`;
  - a `size` naming another size, or several sizes.
- **Unchanged:** `bind_physical_evidence` still accepts a declared compatible variant from other
  sources, and nothing invents coverage.
- **What the first-customer evidence shows.** `physical.size_coverage(db, cir)` binds every size
  of the listing on its own. `first_customer.physical_binding` returns it, and
  `check_gauge_and_size_claims` states it in both PASS and UNRESOLVED. For example, a passed
  small basket reads "physically proven sizes of nursery-nesting-baskets: ['small'], not proven:
  ['medium', 'large'] (a sample covers exactly one size)". The medium variant stays UNRESOLVED.
- **The kit.** Each record sheet prints "This sheet covers exactly one size (…)".

---

## 7. Tests

**New suite: `tests/test_physfix.py`, 17 tests.** On the old code (`ef3f4015`), the original 16
all fail; the 17th, the owner-kit wording test, was added later. On this branch, all 17 pass.

| Fix | Tests |
|---|---|
| 1 | `test_two_coasters_of_four_never_pass_as_the_whole_set`, `test_two_coasters_recorded_as_a_component_give_the_true_factor_and_partial_class`, `test_one_coaster_is_accepted_against_one_coasters_estimate`, `test_a_swatch_is_gauge_evidence_only_and_never_yardage`, `test_a_swatch_off_gauge_fails_and_a_swatch_with_finished_sizes_is_refused`, `test_a_sample_with_no_scope_and_no_measurement_is_refused_not_guessed` |
| 2 | `test_the_priced_partial_offer_is_a_make_the_intake_accepts` |
| 3 | `test_a_coaster_that_does_not_lie_flat_goes_to_the_owner_as_partial`, `test_a_basket_that_collapses_or_a_recorded_problem_never_auto_passes`, `test_a_made_piece_without_its_shape_answer_is_refused` |
| 4 | `test_a_size_mismatch_halts_that_release_and_only_a_corrected_content_lifts_it` |
| 5 | `test_the_basket_kit_asks_for_the_unedited_hero_and_carries_no_nursery_wording`, `test_both_kits_say_reweigh_after_the_swatch_and_print_every_step_whole` (reads the committed PDFs), `test_both_kits_rebuild_byte_identical_from_the_one_builder`, `test_a_filled_coaster_sheet_reaches_the_intake_and_routes_not_flat_to_the_owner` |
| 6 | `test_a_sample_proves_one_size_and_the_first_customer_evidence_says_which`, `test_a_sample_claiming_another_or_several_sizes_is_refused` |

**Existing tests that changed, and why:**
- **`test_physical.py`:**
  - The basket fixtures now record `holds_shape=True`, because the shape answer is now required.
  - `test_a_sample_that_disagrees_about_size_halts_the_product` used to accept
    `publication_halted(...) or incidents[0].severity`. It now asserts the halt and a single P1.
    The test is stricter.
- **`test_physical_record_blocked.py`:** the sphere sample states `scope: full_make`, a finished
  measurement and `holds_shape`.
- **`test_risk_matrix.py`:**
  - The full-make payload adds `holds_shape`.
  - The test of a swatch with no scope is now
    `test_runtime_swatch_is_recorded_partial_and_does_not_unblock_class_c`. It asserts that the
    unscoped sample is refused, and that a declared swatch is partial, passed, has no factor and
    still does not unblock Class C.

**Run results:** each suite was run one at a time, `nice -n 19`, with
`PYTHONPATH=src:tests`, checking free disk first. The full suite was not run.

RESULTS_PLACEHOLDER

## 8. Not done here, and why

- **`launch/readiness.PHYSICAL_SAMPLE` action text** still lists only "grams, ball band, hook,
  finished measurements". It is a dormant owner request, not the tester's sheet, and readiness
  belongs to W-LAUNCHFIX. A tester working from that text alone would be asked at intake for
  the shape answer. **Suggested one-line follow-up:** add "whether it holds its shape, and any
  problem".
- **No owner override promotes a PARTIAL to a PASS.** F-077 says the system cannot mark a test
  passed without external evidence. A PARTIAL is cleared by a corrected release or a repeat
  sample.
- **`BUILD_STATE.md` was not edited**, to avoid a conflict with the integrating branch. This
  file is the record.
