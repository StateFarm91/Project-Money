# Independent integrity review: W-PHYSFIX `29378b85` / PHYSFIX-PHOTO `89eef1ec`

**Date:** 2026-10-31 (UTC). **Reviewer:** an independent Claude Code session. No PR was opened.
The only things pushed are this report and its probe file
(`secreview_physfix_89eef1e_probes.py`), to `claude/w4-SECREVIEW-PHYSFIX-89eef1e`.

**Subject.** A delta review against `INDEPENDENT_SECREVIEW_PHYSFIX_42eac69.md` (R1–R4). Two diffs:
- `git diff 210aa9f8...89eef1ec`: the branch against `claude/w4-INTEG8-next`.
- `git diff 42eac691..89eef1ec`: the non-merge commits are `292eae6`, `9173a94`, `bd633a9` and `29378b8`.

## Verdict: **DO NOT SHIP**

R1 is fixed for every case the previous review reported:
- title, whitespace, notes, colour names, `materials` order, component names, metres;
- the digest moves for each real geometry change probed;
- a same-geometry second make now opens an owner conflict action instead of resolving the halt;
- a halt with no digest fails closed.

But the digest still hashes the CIR's **notation**, not the stitches it compiles to, and it does not normalise
case or number type. A pure notation change (writing `[inc] x6` out as six `inc`s), or upper-casing the
gauge yarn weight, still has two effects:
1. it certifies past an open size halt;
2. a passing make of that copy **lifts the original halt**. This is the R1 failure again, through a
   different door.

The photo-first ordering is sound. The tester-independence check never runs on the only production
intake, and its denylist accepts close relatives (R6). No gate was relaxed.

## Findings

| # | Severity | Finding |
|---|---|---|
| R5 | **MEDIUM-HIGH** | Notation and representation changes alter the design digest. Identical stitches certify past a size halt, and their make lifts it |
| R6 | **MEDIUM** | `record_agreement` independence/qualification is opt-in. `/api/tester/agreement` never passes the fields, and the denylist accepts "my husband", "my mom" and similar |
| R7 | LOW | The basket kit's owner-card `max_cost_cad` (CA$59.65, from the risk matrix) is below what the tester call promises (CA$65.90) and below the CA$66.00 all-inclusive ceiling. No code reads `ceiling_all_inclusive_cad` |
| R8 | LOW | `design_geometry` reads `body["graded"]`, but `CIR.to_dict()` writes `grading`, so the "size set" part of the digest is always `None`. This fails safe (over-halts), but the docstring claims coverage that does not exist |
| R9 | INFO | Observation measurements accept `NaN` (`v <= 0` is False for NaN; Python `json` parses `NaN`). These fields are observational only and not gating |
| R10 | INFO | The `test_w4_launchfix` call allowlist regex (`sample_photo\.(\w+)\(`) would not see a `from .sample_photo import requirement` alias. The current source has no such import; the assertion is legitimate |

### R5 (MEDIUM-HIGH): the digest hashes notation, not stitches

`quality/physical.design_geometry` canonicalises the *CIR tree*: it drops cosmetic keys, strips strings
and keeps everything else verbatim. Three equivalences are therefore not recognised:

- **Repeat vs expanded ops.** `Repeat([inc], times=6)` and six `Op("inc")` compile to the same row.
  So do `Op("sc", 3)` and three `Op("sc", 1)`. All of them hash differently.
- **Case.** `gauge.yarn_weight` "medium" vs "MEDIUM" hash differently. `materials[].yarn_weight` is
  lower-cased; the gauge's is not, and the CIR accepts either.
- **Number type.** `stitches_per_10cm: 13` vs `13.0` hash differently (`json.dumps` keeps the int/float
  distinction). The raw API JSON reaches this path through `CIR.from_dict`.

Repro, run from `brambleloop/` on 89eef1ec:
`PYTHONPATH=src:tests python research/final_build/w4/secreview_physfix_89eef1e_probes.py`

| Probe | Result |
|---|---|
| `test_expanded_repeat_is_the_same_design` | **FAIL**: digest differs |
| `test_expanded_repeat_does_not_certify_past_a_size_halt` | **FAIL**: `granted=True` |
| `test_expanded_repeat_make_does_not_lift_the_halt` | **FAIL**: `size_halts_lifted` non-empty, P1 resolved |
| `test_gauge_yarn_weight_case_is_the_same_design` | **FAIL**: digest differs |
| `test_gauge_case_does_not_certify_past_a_size_halt` | **FAIL**: `granted=True` |
| `test_int_and_float_gauge_are_the_same_design` | **FAIL**: digest differs |
| `test_control_same_geometry_second_make_routes_to_owner_and_stays_halted` | OK: `owner_review=physical_size_conflict:…`, still halted |
| `test_control_a_real_geometry_change_is_a_different_design` | OK |

**Geometry sensitivity (no misses found).** Each of these real geometry changes alters the digest, or the
CIR stops compiling, which reads as `None` and fails closed:
- `make`, `turning_chain`, `skips`, `foundation`;
- gauge stitches and hook;
- yarn weight, op `loop`;
- dropping a seam;
- component `gauge`, `work_direction`.

Every cosmetic change in R1's list now leaves the digest unchanged, and so does a component rename.

**Impact.** This is the same as R1:
- **Certificate.** The pattern a tester measured at the wrong size is certified again.
- **Halt lifted.** A second make of the same stitches that reports the stated size resolves the P1
  automatically (`resolve_halts_disproved_by`). It is not routed to the owner as a conflict.

The first-customer floor still requires a size-proving sample of the new content. The case change
is an easy accident to make. The repeat expansion is a routine rewrite a writer or an editor might
perform.

**Fix direction.**
- Hash what the compiler produces, not the CIR tree. For example, per piece: `make`, the compiled
  per-row stitch sequence or the per-row stitch counts with `into`/skips/turning chains/loop targets,
  and the topology fingerprint `cir.topology` already computes.
- Normalise case for every vocabulary string.
- Coerce numbers to float.
- Add the three probes above as regressions.

### R6 (MEDIUM): tester independence is opt-in and leaky

- `record_agreement` runs `independence_problems` only when `relationship` or `qualification` is not
  `None`.
- The only production caller is `app/main.py:1520` (`POST /api/tester/agreement`). It passes neither
  field: even a body that contains them is dropped. So **every agreement recorded in production skips
  the check**, and the result counts toward the `tester_roster` gate.
- Where the check does run, it is a substring denylist. Each of these is **accepted**:
  `"my husband"`, `"his wife"`, `"my mom"`, `"my brother"`, `"my boyfriend"`, `"my daughter"`,
  `"cousin"`, `"close friend"`, `"coworker"`, `"I live with Jacob"`, `"none."`.
- Repro: `PYTHONPATH=src python -c "from brambleloop.quality.tester_programme import independence_problems as f; print(f('my husband'))"`
  prints `[]`.

This is not acceptable as is, because tester independence is the owner's stated term:
- **Required fields.** Require both fields for new agreements: the API returns 400 when they are
  missing, and `record_agreement` refuses `None`. Legacy rows stay as they are, flagged
  `independence_undeclared`.
- **Allowlist.** Invert the check: accept only an explicit `none` (normalised: strip punctuation), and
  route any other declaration to an owner action rather than judging it by keyword.

### R7 (LOW): two cost figures for one kit

`tester_kit.KIT["max_cost_cad"] = 59.65` is the figure the owner card quotes. `build` recomputes it from
`risk_matrix.owner_action_spec` and enforces it. The tester call promises CA$65.90, which is above the
quoted ceiling. `ceiling_all_inclusive_cad` (66.00) and `testers: 1` are read only by
`test_physfix`; no spend path enforces them. Owner-approved spend should be one figure, enforced in
code, and at least equal to what is promised.

### Photo ordering (verified, no finding)

- `_leads_gallery` calls `sample_photo.qualifying_photos` (the gate's own predicate) for the photo's
  own slug@version. It returns True only if that `photo_id` is in `qualifying`. An exception reads as
  "does not lead".
- `plan_upgrade` puts the frame first only when this check passes. Otherwise the frame goes last, as
  before.
- `attest_unedited` → `lead_with_if_qualifying`:
  - it is re-gated by the same predicate;
  - it touches only `ListingAsset` rows of that slug@version, and only moves the frame whose `sha256`
    is the photo's;
  - it marks the moved frame unapproved, and the reorder supersedes the listing-set certificate by
    fingerprint.

  So it cannot promote an unqualified photo or write outside its scope.
- The updated `test_w4_launchfix` assertion is narrower than before: physical_upgrade may call only
  `qualifying_photos` and may pass no `stage=`. That is legitimate (see R10 for the regex limit).

### No gate relaxed (verified)

- `first_customer_requirement` now also needs `size_proven`. The removed assertion "Class A + swatch
  meets" is a tightening (F3).
- `certificate.bind_physical_evidence` adds `size_proven`.
- `risk_matrix` and `readiness` changes are wording plus intake fields only.
- Risk-matrix tests now iterate `LAUNCH0_SLUGS + HELD_FOR_VERIFICATION`, so the medium basket's
  Class B assertions still run.
- Vacuity fix `bd633a9` asserts that the twin estimate is non-empty.
- Kit observation fields are typed:
  - `base_edge` must be in `BASE_EDGES`, and "rounded" requires `wall_vertical_from_rnd`;
  - yes/no answers are strict;
  - cm values must be positive numbers;
  - malformed values give an ERROR finding, not a stored value. NaN is the exception (R9).

## Suites (run individually, `PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

| Suite | Result |
|---|---|
| test_physfix | 27/27 passed |
| test_secreview_physfix_adversarial | 12/12 passed |
| test_secreview_physfix_42eac69_probes | 8/8 passed |
| test_risk_matrix | all OK (rc=0, 103 s) |
| test_w4_launchfix | 32 passed, 0 failed |
| test_physfix_photo_first | 8/8 passed |
| test_vacuity | all OK (rc=0) |
| test_first_customer_gate | 12 passing, 0 failing |
| test_launch0_listing_truth | all OK (rc=0, 220 s) |

The author's suites are green, but they do not cover R5–R7. The new probe file fails 6 of 8, by design: each failure is a finding.
