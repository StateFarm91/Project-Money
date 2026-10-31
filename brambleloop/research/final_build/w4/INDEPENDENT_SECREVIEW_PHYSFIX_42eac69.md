# Independent integrity review: W-PHYSFIX `eede7394` / PHYSFIX-PHOTO `42eac691`

**Date:** 2026-10-31 (UTC). **Reviewer:** an independent Claude Code session. No PR was opened.
Nothing was pushed except this report and its probe file,
`secreview_physfix_42eac69_probes.py`, to `claude/w4-SECREVIEW-PHYSFIX-42eac69`.

**Subject.** This is a delta review against the prior review (`INDEPENDENT_SECREVIEW_PHYSFIX_adabd59.md`, F1–F7).
- `git diff adabd597..origin/claude/w4-PHYSFIX`: 18 files.
- `git diff 23efd5dc..42eac691`: the same diff, plus a `readiness.py` wording change and
  `test_physfix_photo_first` fixture/test additions.

## Verdict: **DO NOT SHIP** (narrowly)

F2–F7 are fixed at the root. Each fix has discriminating tests, and mutating a fix makes a test fail
(table below). No gate was relaxed.

F1 is fixed for the case that was reported: a version-only relabel now stays halted. But
the new "design digest" is a hash of the **whole CIR minus `version`**, so it still covers fields
that do not affect the finished size. A change to the title, a trailing space in the title, an
edit to `designer_notes`, or reordering the `materials` list each produces a "different design".
That change:

1. certifies past an open size halt; and
2. lets a second make of the **identical geometry** resolve the P1. This defeats the fix's own
   rule that "a sample of the halted design never resolves its own halt".

The author's own test encodes this. In `test_physfix`,
`test_a_size_mismatch_halts_that_design_and_only_a_proven_correction_lifts_it` uses
`fixed.title = fixed.title + " (revised)"  # a different design` as its correction.

## Findings

| # | Severity | Finding |
|---|---|---|
| R1 | **MEDIUM-HIGH** | The design digest covers non-geometric fields. A retitle, whitespace, notes or list-order change certifies past a size halt, and an identical-geometry re-make then resolves it |
| R2 | LOW | Test gap: the fail-closed rule for a halt with no digest is not covered by any author test (mutation survives); the R-probe covers it |
| R3 | LOW | `piece_measurements[*].height_cm` that is not a number (for example the string `"8.3"` via the raw API) is skipped silently, not refused. Width is strict |
| R4 | INFO | Halts opened before this change carry no `design_digest`, so they now read as product-wide and clear only by hand. This fails closed, which is correct, but the owner should know |

### R1 (MEDIUM-HIGH): cosmetic changes count as a different design

`quality/physical.design_digest` hashes `cir.to_dict()` without `version`, plus the US pattern text
with the version string replaced. `to_dict()` keys are `assembly, authored, colors, components,
construction, designer_notes, finished_size_note, gauge, materials, provenance, risk_class, slug,
title`. Of these, `title`, `designer_notes`, `finished_size_note`, `provenance`, `authored`,
colour *names*, and the order of `materials` do not change the made object.

Direct check: with `_basket_medium()`, the digest is **equal** when only the version changes. It
is **different** after `title += " "`, and different after `materials` is reversed.

Repro (run from `brambleloop/` on 42eac691):
`PYTHONPATH=src:tests python research/final_build/w4/secreview_physfix_42eac69_probes.py`

| Probe | Result |
|---|---|
| `test_title_only_change_does_not_certify_past_a_size_halt` | **FAIL**: certified (`granted=True`) |
| `test_trailing_space_in_title_does_not_certify_past_a_size_halt` | **FAIL**: certified |
| `test_designer_notes_change_does_not_certify_past_a_size_halt` | **FAIL**: certified |
| `test_a_second_make_of_the_same_geometry_never_lifts_the_halt` | **FAIL**: `size_halts_lifted` non-empty, P1 resolved |
| `test_control_version_only_relabel_stays_halted` | OK |
| `test_control_certification_alone_never_resolves` | OK |
| `test_control_halt_without_digest_blocks_every_design_of_the_product` | OK |
| `test_control_halt_on_one_product_does_not_halt_another` | OK |

**Impact.**
- **Certificate.** A design a tester measured wrong (40 cm against the stated size) gets a granted
  certificate under a new title. `gate.certify` is the only publication path that reads the halt
  (the other caller is `release_recovery`). After the grant, the pipeline moves on: lanes,
  collections and listing-set rechecks.
- **First customer.** The first-customer floor still blocks this release until it has its own
  size-proving sample.
- **Conflicting measurements.** That sample is a second make of the same geometry reporting the
  twin's size. It both proves the size and silently resolves the P1, so two measurements of one
  design that disagree are settled automatically for the passing one, never by the owner.
- **Effort.** This needs a real (or mis-entered) second make, so it is less severe than the
  original F1. But a title edit is the most routine change the pipeline makes.

**Fix direction.**
- **Option 1.** Digest only what determines the made object: `components` (rows, ops, make
  counts), `gauge`, `construction`, `assembly`, `grading`/`configuration`, and material weight
  and fibre (not names). Canonicalise list order where order is not meaningful.
- **Option 2 (more robust).** Store the halted twin's predicted finished dimensions in
  `release_scope`, and treat an incoming design as different only if its twin's stated dimensions
  differ.
- **Either way.** A passing make whose geometry matches the halted design should route to owner
  review, not resolve the P1.

## F2–F7: fixed at the root

Each fix was mutated in a scratch worktree, and the named tests were run. "KILLED" means a test
failed under the mutation, which is the desired result.

| Fix | Mutation | Result | Killing test(s) |
|---|---|---|---|
| F1 | digest keeps `version` | KILLED | physfix size-mismatch test; adversarial relabel |
| F1 | scoped halt never blocks certify | KILLED | same |
| F1 | own design lifts own halt | KILLED | `test_a_passing_sample_of_the_halted_design_never_lifts_its_own_halt` |
| F1 | any sample (swatch/partial) lifts | KILLED | physfix size-mismatch test |
| F1 | digest-less halt not fail-closed | **SURVIVED** (author suites) | caught only by this review's control probe → R2 |
| F2 | `bool(i.get("instructions_followed", True))` restored | KILLED | `test_followed_exactly_must_be_a_real_yes_or_no`; adversarial F2 |
| F2 | `assess` treats unrecorded as answered | SURVIVED | equivalent: `None` falls to `SAMPLE_DEVIATED`, which still blocks, and the intake refuses `None` first. Defence in depth, no gap |
| F4 | `setdefault("instructions_followed", True)` restored | KILLED | same F2 test; adversarial blank-sheet |
| F3 | first-customer `met = class_met` | KILLED | physfix swatch test; adversarial coaster; `test_risk_matrix` tier test |
| F3 | `size_coverage` proven = bound | KILLED | physfix swatch test; adversarial swatch-proves-size |
| F3 | `size_proof` = outcome PASS only | KILLED | physfix swatch test; adversarial coaster |
| F3 | legacy row always proof | KILLED | `test_launch0_listing_truth` no-sample test |
| F5 | notes back to WARNING | KILLED | physfix notes; adversarial notes; `test_physical` notes |
| F6 | `_assess_pieces` skipped | KILLED | `test_every_coaster_is_measured_in_a_checked_field` |
| F6 | piece count not enforced | KILLED | same |
| F6 | per-piece size not compared | KILLED | same |
| F6 | kit maps coaster 1 to `notes` | KILLED | only by the byte-identical kit rebuild (weak, but present) |
| F7 | docstring | fixed | `test_parts_made_says_whole_but_a_component_stays_partial` asserts it |

The parsers are now strict. `_flag` accepts a real bool or exactly yes/y/true or no/n/false. It
refuses ints and other strings, and blank means unanswered, which is refused.
`tester_kit._yes_no` no longer guesses from the first letter.

## Fixture changes: legitimate

- **`test_secreview_physfix_adversarial`.** It is identical to my original
  `secreview_physfix_adversarial_tests.py`, apart from a header and
  `"instructions_followed": True` added to the three swatch payloads. That addition is required:
  without it the intake now refuses the swatch. `test_a_swatch_alone_does_not_prove_a_size` would
  then pass trivially, and the coaster probe would fail at `_rows(db)` for the wrong reason. The
  change makes the probes test what they were written to test. No assertion was weakened.
- **`test_physfix._inputs`.** It now answers "followed?" and gives one `piece_measurements` entry
  per piece for a component made more than once. Both are new intake requirements. No assertion
  was weakened.
- **`test_risk_matrix`.** `assert first_customer_requirement(m_a, swatch)["met"]` became `not met`,
  and a positive case with `size_proven` was added. This tightens the test. The other two edits
  only add `instructions_followed: True`.
- **`test_launch0_listing_truth`.** It adds an intermediate assertion: a bound sample with no size
  comparison leaves `gauge_and_size_claims` UNRESOLVED. The clearing sample now carries
  `size_agrees: True`. This tightens the test, and it is the legacy-row rule in
  `physical_evidence_rows`.
- **`test_physical`, `test_physical_record_blocked`, `test_physfix_photo_first`.** These add
  `instructions_followed: True`. The notes test is inverted to the new REVIEW behaviour
  (tightened). `photo_first` adds a wording test for the readiness request.

## Nothing relaxed; Class B readiness and swatches

- No threshold, tolerance or class floor was lowered.
- `requirement_status` (readiness / Gate D) is unchanged, so a bound `partial_physical` still meets
  Class B. **That is correct.** The risk-matrix spec text says "Class B needs a partial physical
  test (a gauge swatch or a component) of this exact content", and Class B is gauge risk, which a
  swatch measures.
- The swatch's limit is now enforced where it belongs. It is never `size_proof`, never "proven" in
  `size_coverage`, and never meets the first-customer floor. `owner_action_spec` now says so to
  the owner.
- The `readiness.py` change is wording only: it asks for the answers the intake requires.

## Suites (PHOTO 42eac691, one at a time, `PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

All exit 0, with no failures: `test_physfix` 23/23, `test_secreview_physfix_adversarial` 12/12,
`test_physical` 18/18, `test_risk_matrix` 17/17, `test_first_customer_gate` 12/12,
`test_launch0_listing_truth` 14/14, `test_physfix_photo_first` 5/5, `test_w4_launchfix` 22/22.
The suites are green, but R1 is not caught by any of them: the shipped test asserts the cosmetic
change as the intended behaviour. This review's probes: 4/8 pass (the 4 R1 probes fail).

## Answers to the brief

1. **F1.**
   - **Trivial changes to an identical design:** a version relabel no longer evades. A title
     change, whitespace in a free-text field, notes, metadata, or reordering the `materials`
     list **does evade** (R1).
   - **Dict key order:** it does not matter, because the hash uses `sort_keys`.
   - **Clearing a halt:** besides manual resolution, the only automated path is a passed whole
     full make, with `size_proof`, of a design whose digest differs. Because of R1, "differs" can
     be cosmetic.
   - **A halt with no digest:** blocks every design of the product and is never auto-resolved
     (control probe OK).
   - **Other products:** a halt on one product never halts another (OK).
2. **F2–F6:** fixed at the root, with discriminating tests (mutation table above). F2b is an
   equivalent mutant, and R2 is a test gap only.
3. **Fixtures:** legitimate. Every change either supplies a newly required answer or tightens an
   assertion.
4. **Nothing relaxed:** confirmed. A swatch meeting Class B readiness is correct per spec, and it
   no longer leaks into size proof or the first-customer floor.
