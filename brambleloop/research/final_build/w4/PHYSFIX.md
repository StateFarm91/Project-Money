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

> **Superseded in part by §10 F1:** the halt is now keyed on the version-independent design digest, and a passed full make of a different design lifts it. Certification no longer does.

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
| `KIT_MANIFEST.json` | `9e192bfdc95f125b4fd0373ea0bcc1e5c6e085711997dddbe1fed8a196ba2cbb` |
| `hexagon-coaster-set-1.2.0-TEST.pdf` (unchanged) | `7d10fc229525b650a3a2d77171c36842a9c46abab4213157a04cedafb4739909` |
| `hexagon-coaster-set-1.2.0-RECORD-SHEET.pdf` (was `892484a8…`) | `7c40361dfa4e171617c52f749691d8e7b386c7e39dd783e0f8a03f650e8cc6df` |
| `KIT_MANIFEST_hexagon-coaster-set.json` | `d56e25f949f48faa9b48095034762ce0c15d5d0e40da03d74cc0d75fcadecb83` |

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

| Suite | Result | Run |
|---|---|---|
| `test_physfix.py` | 17/17 | r3, final code |
| `test_physical.py` | 18/18 | r3, final code |
| `test_w4_gatesb.py` | 10/10 | r3, final code |
| `test_shadow.py` | 10/10 | r3, final code |
| `test_risk_matrix.py` | 17/17 | r2; rerun on the final code on `claude/w4-PHYSFIX-PHOTO` |
| `test_physical_record_blocked.py` | 5/5 | r2; rerun on `-PHOTO` |
| `test_first_customer_gate.py` | 12/12 | r2; rerun on `-PHOTO` |
| `test_launch0_listing_truth.py` | 14/14 | r2 |
| `test_eligibility.py` | 34/34 | r2 |
| `test_gates.py` | 44/44 | r2 |
| `test_acceptance_gates.py` | 23/23 | r2 |
| `test_w4_listready.py` | 31/31 | r2 |
| `test_artefacts.py` | 23/23 | r2 |

r2 ran before the last two edits: the base-sits-flat rule and the kit's photo steps. The suites
those edits touch were rerun in r3, or on `-PHOTO` (see §9). r2 and later runs used the shared
`testslot.sh` gate.

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

## 9. Photo-first gallery ordering (`claude/w4-PHYSFIX-PHOTO`, on top of `claude/w4-LAUNCHFIX`)

**The problem:** W4-LAUNCHFIX's `publish/sample_photo.py` gate requires the certified gallery's
**first** frame to be the unedited sample photo of a passed full make of this release.
`physical_upgrade.plan_upgrade` appended the photo frame last, so the gate could never be
satisfied.

**The fix.** The branch is LAUNCHFIX (`0f0306dd`) with this branch merged in, plus one commit.
It is built there because it needs LAUNCHFIX's `sample_photo.py` and `intake(unedited=)`.
- **Which photo leads.** `plan_upgrade` puts the photo at position 1 when all of these hold:
  - it was attested unedited at intake, and is not marked edited or AI-processed;
  - its `physical_test_id` is a passed, completed full make of the same slug@version.
- **Everything else** keeps its relative order behind the photo: renders, charts and the PDF
  preview. The certificate still labels each one.
- **Renumbering is two-phase,** because the slot `(slug, version, position)` is unique. A moved
  photo's recorded `frame_position` is kept true.
- **Any other photo** is appended last, as before.
- **Re-certification works as before:**
  - the new frame is unapproved until asset truth has run;
  - the moved frame set supersedes the old listing-set certificate by its hashes;
  - the content binding is re-checked by `sample_photo` at publication.

**Tests:** `tests/test_physfix_photo_first.py`, 4 tests.
- A completed upgrade puts the photo at position 1, followed by hero, chart and pattern preview
  in their old order. The gate refuses before re-certification. After a certificate is issued
  through the real `release_gates.certificate_step`, the gate accepts. The per-frame gate
  readings in this test are supplied.
- A renders-only gallery is refused.
- A photo not attested unedited does not lead and does not satisfy the gate.
- A photo with no passed full make behind it does not lead.

**Against the old ordering** (detached `1d915053`), the main test fails, with the photo at
position 4. The three guard tests pass there too, as intended.

**Remaining gap (not in this lane): the Launch-0 galleries are disclosed-render sets**,
certified by `release_gates` → `listing_set.certify_disclosed`. That path explicitly refuses a
mixed set: "the disclosed-render certificate does not cover ListingAsset frames; a mixed set is
not certified here". A disclosed set also has no slot for a camera photo. So for a Launch-0
listing, the photo-first gallery the gate needs also requires a mixed or photo-led variant of
`certify_disclosed`. This change makes the ListingAsset path correct; the disclosed path is a
gallery-pipeline change for its owner.

## 10. Independent review fixes (SECREVIEW of `adabd597` / `23efd5dc`: DO NOT SHIP → fixed)

The review is `INDEPENDENT_SECREVIEW_PHYSFIX_adabd59.md` on
`claude/w4-SECREVIEW-PHYSFIX-adabd59`. Each finding is fixed at the root and has its own
regression test. The reviewer's 12 adversarial probes are adopted as
`tests/test_secreview_physfix_adversarial.py`. They passed 5/12 on `adabd597` and pass 12/12
now. The only change to them: their swatch payloads answer "followed exactly?", which is now
required.

- **F1 (HIGH). A relabel no longer lifts a size halt.**
  - The halt is keyed on `quality.physical.design_digest`: the CIR without its version, plus the
    pattern text with the version string removed. A version-only relabel has the same digest, so
    `gate.certify` stays halted.
  - Certification no longer resolves anything. `resolve_superseded_release_halts` is removed.
  - `IncidentTracker.resolve_halts_disproved_by` resolves a halt only when `physical.record`
    stores a passed full make of a *different* design, with `size_proof` (its size agreed). A
    passing sample of the halted design never lifts its own halt.
  - A halt with no digest on file is product-wide (fails closed).
  - Tests: `test_a_size_mismatch_halts_that_design_and_only_a_proven_correction_lifts_it`, which
    replaces the relabel-based test; `test_a_passing_sample_of_the_halted_design_never_lifts_its_own_halt`;
    and the adversarial `test_relabelled_identical_content_does_not_lift_size_halt` and chain test.
- **F2 (HIGH) and F4 (MEDIUM). "Followed exactly?" is parsed strictly.**
  - Accepted: a real bool, or exactly yes, y, true, no, n or false.
  - Blank, missing or anything else (for example "0", "nope", 1) is refused at intake.
  - `SampleReport.instructions_followed` defaults to None, which raises `SAMPLE_FOLLOWED_UNRECORDED`
    (ERROR).
  - `tester_kit.intake_payload` no longer defaults it to True. Its yes/no parser is exact rather
    than reading the first letter.
  - Tests: `test_followed_exactly_must_be_a_real_yes_or_no`, plus the two adversarial probes.
- **F3 (MEDIUM-HIGH). A swatch is gauge evidence only.**
  - Each row is stamped `size_proof`: a PASS of made pieces whose size agreed.
  - `bind_physical_evidence` returns `size_proven`.
  - `size_coverage.proven` counts only size proof. A swatch is listed as `gauge_only`.
  - `first_customer_requirement.met` needs a size proof as well as the class.
  - A swatch still binds as `partial_physical`, so readiness' Class B gauge requirement is
    unchanged. The swatch cost offer now says it does not meet the first-customer floor.
  - Legacy rows count as size proof only if their size was compared and agreed and they were
    not a swatch.
  - `test_risk_matrix.test_first_customer_tier_requires_the_class_its_risk_needs` used to assert
    that a swatch met the Class A floor. It now asserts that it does not, and that made pieces
    with a size proof do. This makes the test stricter.
  - Tests: `test_a_swatch_never_proves_a_size_or_meets_the_first_customer_floor`, plus two
    adversarial probes.
- **F5. Notes go to the owner.** Any free-text `notes` is now a REVIEW finding, so the sample is
  PARTIAL and the owner reviews it. `test_physical`'s notes test now asserts PARTIAL, which is
  stricter. Both kits moved their measurement lines out of `notes` into checked fields.
  - Tests: `test_a_problem_written_in_notes_goes_to_the_owner`, plus the adversarial probe.
- **F6. Every coaster is a checked measurement.**
  - `piece_measurements` holds one entry per made piece, and each is compared with its
    component's twin at 12%.
  - It is required wherever a component is made more than once. A count mismatch is refused
    (`SAMPLE_PIECES_UNMEASURED`).
  - The coaster sheet has eight checked boxes (points and flats for coasters 1–4).
  - The basket's across-the-flats is now a checked field (`measured_flats_cm`).
  - Tests: `test_every_coaster_is_measured_in_a_checked_field` (three measured is refused; one
    wrong coaster fails the set), and the coaster sheet test.
- **F7. The `parts_made` docstring now matches the code.** A component covering the whole set
  returns "whole pattern? = True" and is still recorded `partial_physical`.
  - Test: `test_parts_made_says_whole_but_a_component_stays_partial`.

**Kits rebuilt:**
- The basket TEST.pdf, the basket record sheet and both content hashes are unchanged.
- New coaster record sheet: `7c40361dfa4e171617c52f749691d8e7b386c7e39dd783e0f8a03f650e8cc6df`.
- New manifests: basket `9e192bfdc95f125b4fd0373ea0bcc1e5c6e085711997dddbe1fed8a196ba2cbb`,
  coaster `d56e25f949f48faa9b48095034762ce0c15d5d0e40da03d74cc0d75fcadecb83`.

**Runs after the review fixes** (each via `testslot.sh`, one at a time, on `claude/w4-PHYSFIX`):

| Suite | Result |
|---|---|
| `test_physfix` | 23/23 |
| `test_secreview_physfix_adversarial` | 12/12 |
| `test_physical` | 18/18 |
| `test_physical_record_blocked` | 5/5 |
| `test_risk_matrix` | 17/17 |
| `test_w4_gatesb` | 10/10 |
| `test_first_customer_gate` | 12/12 |
| `test_launch0_listing_truth` | 14/14 |
| `test_gates` | 44/44 |
| `test_artefacts` | 23/23 |
| `test_w4_listready` | 31/31 |
| `test_eligibility` | 34/34 |
| `test_acceptance_gates` | 23/23 |

`test_launch0_listing_truth` had one failure on the first run. Its fixture row carried no size
comparison and was expected to clear the size gate, which is exactly the F3 gap. The fixture now
records `size_agrees: True`. A new step in that test asserts that a bound row with no size
comparison stays UNRESOLVED.

## 11. Delta review (`INDEPENDENT_SECREVIEW_PHYSFIX_42eac69.md`), kit additions, tester terms, Batch 4 base

**Base:** `claude/w4-INTEG8-next` `210aa9f8` is merged in, which brings LISTING1, LAUNCHFIX `8c14dbf2` and ADOPT. The kits were rebuilt on it.
- The basket TEST.pdf no longer carries the children's/nursery block. It is now 7 pages,
  `e4bc8ad3…`.
- The content hash is unchanged (`1ddde587…`).
- The trial reconcile of `test_physfix`'s size-coverage test (`b9ab2ee0`) is applied:
  `hexagonal-bread-basket` is a one-size listing.

**Findings and fixes:**
- **R1 (MED-HIGH): the digest now covers geometry only.**
  - `quality.physical.design_geometry` keeps only what decides the made object:
    - per piece: construction, foundation, quantity, holds/resumes and grain;
    - per row: stitch ops and counts, `into`, skips and turning chains, in working order;
    - the gauge (stitches and rows, stitch type, hook, yarn weight, chain gauge);
    - yarn weights and fibres, as a sorted set;
    - assembly, the size set and the represented variant.
  - Labels, notes, colours, whitespace, provenance and piece order are dropped. `design_digest`
    hashes the result.
  - A passing make of the *same* geometry as an open halt now opens an owner action,
    `physical_size_conflict:*`, and never resolves the halt.
  - Tests:
    - `test_the_design_digest_is_geometry_only`;
    - `test_a_size_mismatch_halts_that_design_and_only_a_proven_correction_lifts_it`, whose
      correction is now a real extra wall round, with title, whitespace, notes and
      materials-order negatives;
    - `test_a_passing_sample_of_the_halted_design_never_lifts_its_own_halt`, which now also
      covers the conflict routing and a retitle;
    - the reviewer's 8 probes, adopted unchanged as
      `tests/test_secreview_physfix_42eac69_probes.py`.
- **R2: a halt with no digest fails closed.** Covered by the adopted probe
  `test_control_halt_without_digest_blocks_every_design_of_the_product`.
- **R3: piece heights are typed.** A string, a negative or a bool is refused.
  - Test: `test_a_piece_height_that_is_not_a_number_is_refused`.
- **R4 (info): older halts read product-wide.** Halts opened before this change carry no digest,
  so they block the whole product and clear only by hand. This fails closed, as designed.

**Kit additions** (construction review §5):
- The wall height method is printed and stored: outside, from the flat table to the top of the
  rim, at the middle of a flat side.
- New fields:
  - `inside_depth_cm` (optional);
  - `base_edge`: crisp or rounded. If rounded, `wall_vertical_from_rnd` is required;
  - `corners_at_rim` (yes/no);
  - `rim_across_points_cm`;
  - `rnd11_height_cm` (optional).
- All are typed, and a malformed entry is refused at intake.
- Test: `test_the_basket_records_the_construction_review_observations`.

**Tester terms:**
- **One tester.** Both calls ask for exactly ONE.
- **Independence:** not the owner, not a member of the owner's household or family, no
  financial interest, and any relationship declared.
- **Qualification:** a photo or link to a finished piece worked in joined rounds.
- **Intake form:** `relationship` and `qualification` fields. `record_agreement` refuses a
  non-independent or unqualified tester when they are supplied.
- **Payment:**
  - The tester receives CA$65.90 (coasters: CA$99.96), paid in full by a fee-free transfer.
  - The ceilings are all-inclusive: CA$66.00 for the basket, CA$100.00 for the coasters.
  - The approval doc gives the arithmetic, and the higher figure (about CA$68.11) for a
    card-processor method.
- **Generated by the builder:** `OUTREACH.md` and `OUTREACH_hexagon-coaster-set.md` are now
  written by `tester_kit.build` through `tester_programme.outreach_markdown`.
- Test: `test_tester_terms_one_independent_qualified_tester_and_an_all_inclusive_ceiling`.

**Combined-tree fixes:**
- **`test_risk_matrix`.** It reads the held basket family through
  `launch0.HELD_FOR_VERIFICATION`, so every Class B assertion about the medium basket is kept.
- **`test_physfix`.** The one-coaster estimate test now asserts the twin's yarn is non-empty
  before its loop (`test_vacuity`).
- **PHOTO: lead-photo rule.** `plan_upgrade` decides the lead photo with
  `publish.sample_photo.qualifying_photos`, the gate's own predicate, not a copy of it.
  - That predicate includes the owner's Command Center attestation (LAUNCHFIX F-7).
  - `attest_unedited` moves an already-planned photo to the front if it now qualifies.
  - Tests:
    - `test_unedited_at_intake_but_not_owner_attested_is_never_put_first`;
    - `test_owner_attestation_after_planning_moves_the_photo_to_the_front`;
    - `test_the_ordering_predicate_is_the_gates_own`;
    - `test_w4_launchfix` now lists `physical_upgrade` as a user of `sample_photo`, and asserts
      it calls only `qualifying_photos`, never `requirement`, and passes no stage.

**Not done:**
- **W-PDF1's 1.2.1 has not landed.** It is on `claude/w4-PDF1` and not integrated. When it lands,
  the basket content hash changes (W-PDF1's own kit build shows `9251c2ec…`). The kit must then
  be rebuilt and rebound by the same builder.

**Final runs** (via `testslot.sh`, one at a time, after merging `210aa9f8`):

| Suite | PHYSFIX | PHOTO |
|---|---|---|
| `test_vacuity` | 8/8 | 8/8 |
| `test_physfix` | 27/27 | 27/27 |
| `test_secreview_physfix_adversarial` | 12/12 | 12/12 |
| `test_secreview_physfix_42eac69_probes` | 8/8 | 8/8 |
| `test_risk_matrix` | 17/17 | 17/17 |
| `test_w4_launchfix` | 32/32 | 32/32 |
| `test_physical` | 18/18 | not run |
| `test_physical_record_blocked` | 5/5 | not run |
| `test_w4_gatesb` | 10/10 | not run |
| `test_first_customer_gate` | 12/12 | not run |
| `test_launch0_listing_truth` | 14/14 | not run |
| `test_gates` | 44/44 | not run |
| `test_artefacts` | 23/23 | not run |
| `test_w4_listready` | 31/31 | not run |
| `test_eligibility` | 34/34 | not run |
| `test_w4_adopt_manual_listing` | 19/19 | not run |
| `test_physfix_photo_first` | not run | 8/8 |
| `test_fb2_i_repairs` | not run | 7/7 |
| `test_cert_intel_wave2` | not run | 15/15 |
| `test_w4_ownerimg` | not run | 35/35 |
| `test_search_hero_publish` | not run | 4/4 |

## 12. Delta review 2 (`INDEPENDENT_SECREVIEW_PHYSFIX_89eef1e.md`)

- **R5 (MED-HIGH): the digest now comes from the compiled stitches and the twin.**
  - `design_geometry` reads the compiler's resolved rows, with every stitch expanded singly
    (stitch, loop, span), the worked-into, consumed, produced and remainder counts, and turning
    chains. It also reads each piece's twin shape and dimensions, rounded to 0.1 cm.
  - Repeat notation is therefore invisible: `[inc] x6` gives the same digest as six `inc`.
  - Vocabulary is lower-cased, and numbers are floats (5 and 5.0 give the same digest).
  - Component names inside holds/resumes/assembly become canonical piece positions.
  - Tests:
    - `test_the_design_digest_reads_compiled_stitches_not_notation` covers expansion, case,
      int vs float, and the reverse: a loop change, a stitch change and a quantity change each
      move the digest, and an uncompilable mutation reads as None, which fails closed.
    - The reviewer's 8 probes are adopted as `tests/test_secreview_physfix_89eef1e_probes.py`.
      The only change is the path line.
- **R6 (MED): tester independence is mandatory.**
  - `record_agreement` requires `relationship` and `qualification` on every new agreement.
  - `relationship` is an allow-list: "none" or "acquaintance (declared)", normalised for case and
    punctuation. Every other declaration is refused.
  - The declaration is stored on the permission.
  - `/api/tester/agreement` (`app/main.py`) passes both fields. A missing or disallowed one
    returns 400.
  - Tests:
    - `test_tester_terms_…` refuses husband, wife, mom, brother, boyfriend, daughter, cousin,
      close friend, coworker, "I live with Jacob", contractor, employee, shares, partner,
      household member, blank and None.
    - `test_every_production_tester_intake_passes_the_tester_terms` is an AST scan of every src
      caller.
    - `test_w4_b2gates` posts to the route without each field and with "my husband", "my mom"
      and "coworker", and gets 400 each time.
    - `test_w4_gatesb` fixtures now pass the terms.
  - Agreements recorded before this change carry no `independence` block.
- **R7 (LOW): one cost figure per kit.**
  - `tester_kit.KIT["max_cost_cad"]` is now the single all-inclusive figure: CA$66.00 for the
    basket, CA$100.00 for the coasters. The duplicate field is removed.
  - `build` checks two things and refuses on either:
    - that the tester call states the promised amount (fee at the risk-matrix rate plus 2 whole
      balls: CA$65.90 / CA$99.96);
    - that the one figure covers both that promise and the risk matrix's per-metre ceiling.
  - The `ops.owner_queue` `tester_outreach` card now states and carries the same figure. The
    separate 8-hour estimate is removed.
  - Test: `test_one_cost_figure_per_kit_everywhere_it_is_stated` covers the owner card, the
    gate-clearance card, the approval doc's OWNER ACTION row, the call and both manifests.
- **R8: the size set is read from `grading`,** the key `CIR.to_dict` writes.
- **R9: non-finite measurements are refused.**
  - Every measured number must be finite, otherwise the intake raises `SAMPLE_MEASUREMENT_INVALID`
    and the record is refused.
  - This covers more than the observation fields: a NaN width, gauge or grams would have
    compared as "agreeing".
- **R10:** the PHOTO branch's `test_w4_launchfix` also refuses aliased imports out of
  `sample_photo`.

**R9 test:** `test_a_non_finite_measurement_is_refused` refuses each of these: a NaN width, an
infinite flats span, a NaN observation, NaN hours, NaN grams, and a NaN swatch gauge.

**Runs** (via `testslot.sh`, one at a time; PHYSFIX at `32e3533d` + this test, which includes
`origin/claude/w4-INTEG8-next` `d55a3020`):

| Suite | PHYSFIX | PHOTO |
|---|---|---|
| `test_vacuity` | 8/8 | 8/8 |
| `test_physfix` | 31/31 | 30/30 (before the NaN test; rerun after the merge) |
| `test_secreview_physfix_adversarial` | 12/12 | 12/12 |
| `test_secreview_physfix_42eac69_probes` | 8/8 | 8/8 |
| `test_secreview_physfix_89eef1e_probes` | 8/8 | 8/8 |
| `test_risk_matrix` | 17/17 | 17/17 |
| `test_w4_b2gates` | 12/12 | 12/12 |
| `test_w4_launchfix` | 32/32 | 32/32 |
| `test_physical` | 18/18 | not run |
| `test_physical_record_blocked` | 5/5 | not run |
| `test_w4_gatesb` | 10/10 | not run |
| `test_w3_k7_owner_queue` | 10/10 | not run |
| `test_w4_owner_actions` | 6/6 | not run |
| `test_w4_owner_queue_race` | 2/2 | not run |
| `test_first_customer_gate` | 12/12 | not run |
| `test_launch0_listing_truth` | 14/14 | not run |
| `test_gates` | 44/44 | not run |
| `test_artefacts` | 23/23 | not run |
| `test_w4_listready` | 31/31 | not run |
| `test_eligibility` | 34/34 | not run |
| `test_w4_adopt_manual_listing` | 19/19 | not run |
| `test_physfix_photo_first` | not run | 8/8 |
| `test_fb2_i_repairs` | not run | 7/7 |
| `test_cert_intel_wave2` | not run | 15/15 |
| `test_w4_ownerimg` | not run | 35/35 |
| `test_search_hero_publish` | not run | 4/4 |

`test_w4_owner_queue_race` failed once (1/2) under machine contention. The failing check was
`etsy_surface:*` requests queued twice by concurrent passes, which none of this work touches. A
solo rerun passed 2/2.

## 13. Delta review 3 (`INDEPENDENT_SECREVIEW_PHYSFIX_3e542a1.md`)

- **R11: hold names no longer affect the digest.**
  - A hold's geometry stays in its piece's content: the row, the count and the stitch offset.
    Its name is dropped.
  - Every hold name becomes a position (`piece#i/hold#j`), and a `resumes` that names a hold is
    written as that position. Assembly references are mapped the same way.
- **R14: `Row.into` is back in the digest,** as `into_offset` (row index minus target; 1 is the
  default previous row). Renumbering rows does not change it.
  - Test for R11 and R14: `test_a_hold_rename_is_the_same_design_and_into_is_geometry`.
    - The reviewer's two-piece repro gives the same digest after a hold rename.
    - A real hold change still moves it (and still compiles).
    - Working round 15 into round 13 of the medium basket moves it.
- **R12: every sample is bound to an independent agreed tester.**
  - `quality.physical.record` (the only writer of `PhysicalTest`) refuses a sample unless
    `tester_programme.independent_agreement(tester_ref)` finds a `tester_agreement` permission
    that passed the allow-list, with qualification evidence. The agreement is stamped on the row.
  - There is no default tester: `handle_physical_record` no longer uses `"owner"`.
  - An explicit `owner_made: true` is stored as non-evidence: never passed, `size_proof` false,
    binds nothing, calibrates nothing, never lifts a halt. A size mismatch on it still halts,
    which fails closed.
  - `executor._physical_proof_available` ignores owner-made rows.
  - `_tester_recruited` counts a `tester_agreement` permission only if it passed the allow-list.
    Agreements recorded before the allow-list no longer count. Other permission kinds count as
    before.
  - Test: `test_a_sample_is_evidence_only_from_an_independent_agreed_tester`. It covers no ref,
    an empty ref, "owner", an unknown ref, a pre-allow-list agreement, the owner-made path, and
    the gate readings.
  - Test fixtures now agree their testers through `record_agreement`.
- **R13 and R17: the stale figures are gone from the committed packets.**
  - `gate_clearance_business.py` was re-run. Its diff touches only the tester lane: the figure,
    the protocol, the records, the call and the kit digests.
  - The new `owner/patch_tester_outreach.py` rewrites only the `tester_outreach` decision and its
    `physical_proof` detail, in `OWNER_ACTIONS.{json,md}` and the Command Center snapshot, from
    `owner_queue` and the regenerated clearance. The go-live batch total goes from CA$651.00 to
    CA$532.00.
  - `build_owner_docs.py` was not re-run, because it would rewrite other lanes' items from
    vendored readings.
  - `launch/readiness.PHYSICAL_SAMPLE` now reads `tester_kit.KIT["max_cost_cad"]` and names the
    small-basket kit. The 8-hour CA$185 formula is gone.
  - The `tester_kit` docstring no longer calls CA$59.65 a ceiling.
- **R15: the ceiling is checked from above.** `tester_kit.APPROVED_CEILING_CAD` holds the
  approved figures (66.00 and 100.00). A `max_cost_cad` above its approved figure refuses the
  build.
- **R16: the qualification must be a link or a stored photo.** It must be an http(s) link with a
  real host, or a stored photo reference (`photo:<sha256>` or a bare SHA-256). "." and
  "https://x" are refused.
  - Test: `test_qualification_evidence_must_be_a_link_or_a_stored_photo`.
- Test for R13, R15 and R17: `test_the_kit_ceiling_is_checked_from_above_and_no_stale_figure_remains`
  (a 10x ceiling refuses each kit, and none of the five committed files contains CA$185 or
  59.65).
- **Combined-tree fix.** `test_executor.test_tester_roster_counts_agreement_not_prospects` stores
  a permission as a plain string. `_tester_recruited` now handles non-dict permissions as before.

## 14. Delta review 4 (`INDEPENDENT_SECREVIEW_PHYSFIX_e3fd0b0.md`)

- **R18: list order no longer reaches the digest.**
  - Each piece's holds are sorted by geometry (row, offset, count) before they get `hold#j`
    positions.
  - After `resumes` is filled in, the piece list is sorted again by full content, so it is a
    multiset. Swapping a left and a right sleeve, or listing the holds in another order, gives
    the same digest.
  - Real changes still move it.
  - Test: `test_hold_order_and_identical_piece_order_are_not_the_design`, built on the
    reviewer's probes 2–4 plus two reverse checks.
- **R19: owner-made rows are never testers.** `quality.testers.from_db` and `plan` skip
  `owner_made` rows and the ref "owner". Test:
  `test_an_owner_made_row_is_never_a_tester_in_the_roster_or_plan`.
- **R20: only an independent agreement opens `tester_roster`.**
  - `_tester_recruited` counts only a `tester_agreement` dict that passed the allow-list with
    qualification evidence.
  - A string permission, another kind of permission, a pre-allow-list agreement and
    `delivered > 0` no longer count.
  - The gate's description, and the owner packet's evidence for `tester_outreach` (via
    `patch_tester_outreach.py`), say so.
  - `test_executor.test_tester_roster_counts_agreement_not_prospects` now asserts all four are
    refused and that an agreement recorded through `record_agreement` opens the gate. This makes
    the test stricter.
- **R21: the last stale cost line is gone.** The listing package's last "CA$59.65" alternative
  is removed, and the stale-figure test now covers that file.

## 15. Delta review 5 (`INDEPENDENT_SECREVIEW_PHYSFIX_81b3e45.md`): the fail-closed interim

- **R22/R23: designs with holds now fail closed instead of being canonicalised.** Positional
  labels for holds and resumes could not yet be canonicalised in both directions: a cosmetic
  reorder of identical holding pieces moved the digest (R22), and the multiset re-sort from
  `5f7ee773` mapped a real change onto another design (R23). So:
  - **The 5f7ee773 piece re-sort is reverted.** The hold-order sort stays; the reviewer found
    it sound.
  - **`design_digest` returns None for any design with holds or resumes**
    (`_HOLD_DIGEST_INTERIM`). A size halt on such a design therefore carries no digest. That
    makes it product-wide: it halts every certification of the product, and no make lifts it.
    This is the same rule as for a halt with no digest. No Launch-0 CIR has holds.
  - **The real fix is future work,** marked `TODO(physfix-holds)` in `design_digest`. It needs
    a canonical tree (AHU) encoding of the resume forest, and refusing resume cycles (R25)
    first.
  - Test: `test_designs_with_holds_are_halted_product_wide_until_holds_are_canonical` covers:
    - the reviewer's R22 P1/P2 reorders and the R23 D1/D2′ pair, all with no digest;
    - a halt with no digest halts every incoming digest, and no make resolves it;
    - a design with no holds keeps its digest and its scoped behaviour.
  - The R11 test now asserts None for hold designs, and that `design_geometry` is still
    rename-invariant.
- **R24: an owner make is never counted as a tester's.** An owner-made row is filed under
  `tester_ref="owner"` whatever ref was passed, and `growth_ops.creators_reading` skips
  owner-made rows (`testers._counts_as_tester`).
  - Test: `test_an_owner_make_under_a_testers_ref_is_filed_as_owner_and_never_counted`.
- **The optional R20 gap is closed:** a `tester_agreement` whose qualification is "." no longer
  opens `tester_roster` (added to `test_executor`).
- **Not done:**
  - R25 (the compiler accepting a self-resume): hold designs are fail-closed for halts in the
    meantime.
  - R26 (Info: the vendored `owner/gate_clearance_business.json` input still says 59.65; it is
    overwritten on patch, and not owner-facing).
