# Independent integration review INTEG5C: claude/w5-INTEG1 a8ce0072..f8bf2782, 2026-11-02

Reviewer: an independent, adversarial, read-only Claude Code session (branch `claude/w5-SECREVIEW-INTEG5C`).
- Scope: the delta after a8ce0072, which INTEG5B already integration-reviewed (SHIP). The delta is
  two commits:
  - **52f9f4b5:** a split integration unit, opus2's pet-bed and stocking delta `55450fc3..a859f6fe`
    applied onto a8ce0072.
  - **f8bf2782:** a test-only change to the `sample_photo` users guard in `test_w4_launchfix`.
- All work ran in a detached scratch worktree of f8bf2782 in the session scratchpad. Each mutation
  was reverted, and the worktree was clean afterwards (`git status --short`: 0 lines).
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
  This report is the only file committed.
- The container lacked `sqlalchemy`/`fastapi`, so `pip install -r brambleloop/requirements.txt` was
  run first. The first run of `test_shadow` stopped at the reviewer's own 900 s timeout after 3 of
  10 tests (rc 124). That run is **not** counted. It was re-run with no tight timeout and a stack
  dump every 10 minutes. The stacks show slow progress, not a hang: PIL image work in
  `handle_launch_plan` → `release_gates.listing_set`. The re-run passed 10/10 in 27.7 min.

## Verdict

**SHIP for certification.** f8bf2782 may go to the one uninterrupted full suite in place of
a8ce0072.
- 52f9f4b5 is a faithful 3-way application of the reviewed product delta. It loses nothing and adds
  nothing.
- Leaving out f96d7bd2 drops nothing the pet bed or stocking need.
- f8bf2782 removes a false positive from the guard and loses no real detection.
- Every requested suite exits 0.
- No finding blocks shipping. The carried LOW items were already accepted by OPUS2O as follow-ups.

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| INTEG5C-1 | INFO (verified) | **52f9f4b5 is exactly the 3-way result.** It touches the same 6 files as `git diff 55450fc3 a859f6fe -- brambleloop/src brambleloop/tests`, and nothing else. For each file, `git merge-file` (ours = a8ce0072, base = 55450fc3, theirs = a859f6fe) gives 0 conflicts and output **byte-identical** to the file in 52f9f4b5. Of the 6 files, 4 (`fallback_constructions.py`, `test_opus2_draft_constructions.py`, and the two new tests) had no a8ce0072 difference from 55450fc3, so they now equal a859f6fe exactly. For `vessels.py` and `pipeline.py`, the changed lines of `diff a859f6fe→52f9f4b5` hash identically to those of `diff 55450fc3→a8ce0072`. So each file is a859f6fe plus only what a8ce0072 already had: nothing lost, nothing extra. Not touched: the 20-line `COORDINATION.json` change in the full range (outside src/tests, as intended). | `git merge-file -p ours base theirs \| cmp - <(git show 52f9f4b5:F)`; md5 of `git diff -U0 … \| grep '^[-+][^-+]'` |
| INTEG5C-2 | INFO (verified) | **Leaving out f96d7bd2 drops nothing the delta needs.** f96d7bd2 is an ancestor of 55450fc3. It sits inside the base of the reviewed range, so the product delta contains none of its changes by construction. Its PR #3 resolution is already in a8ce0072 as an equivalent union. `publish/release_gates.py` is identical. `publish/withholding.py` has both `QUALITY_REVERIFY` and `PHYSICAL_SIZE_FAILED`, with the order of `KINDS` swapped (no behaviour reads the order). Every name the new code imports resolves on f8bf2782: `launch0.ASSEMBLED_FORMS`, `MOTIF_WORDS`, `PLURAL_MARKERS`, `gates.size_claims.claims_in`, `vessels._disc_rounds`, `base_stitches_for`, `PET_BED_SIZE`, `creative.prototype.gauge_for` and `cir.model.Seam`. No registry or autonomy-map entry is needed: the stocking reuses the `cir.draft` job and adds only an `FC.STOCKING` branch in `handle_cir_draft`. | `git merge-base --is-ancestor f96d7bd2 55450fc3`; `git diff f96d7bd2 a8ce0072 -- publish/`; hasattr probe |
| INTEG5C-3 | INFO (verified) | **The interactions with a8ce0072 are sound.** (1) a8ce0072's `vessels.build_basket` now picks the version per size, with a back-loop first wall only for `DEFINED_EDGE_SIZES = ("small",)`. The pet bed does not go through `build_basket`. It is built by `fallback_constructions.vessel` from `PET_BED_SIZE` (key `pet_bed`) and `_disc_rounds`, so the 1.3.0 small-basket change cannot leak into it. (2) In `handle_cir_draft`, the new `FC.STOCKING` branch sits with the existing VESSEL/COSY/TOTE/TRIANGLE branches. It uses the same lineage/provenance pattern, inside the same `PrototypeRefused`/`ValueError`/`KeyError` refusal handlers and before the same `name_truth` read. a8ce0072's own pipeline changes (`_seed_for(db=…)`, radar score, certify, WORK_KEYS) are in other hunks. (3) End to end on f8bf2782: "Cat Bed" routes to vessel and "Classic Christmas Stocking" to stocking. Each compiles with 0 errors, with `title_promise.backed` True, `name_truth` [], `size_claims.claims_in(title)` [] and `size_claims.launch0_findings()` []. "Dog Bed", "Small Cat Bed", "Bolster Cat Bed", "Mosaic Stocking" and "Striped Stocking" are refused. | `$S/e2e.py`, `F.plan` probe |
| INTEG5C-4 | LOW (carried, known) | **OPUS2O-6 is still present in the integrated tree, as expected.** With a one-colour palette, "Contrast Cuff Christmas Stocking" is drafted, compiles, and is `title_promise`-backed with `name_truth` []. Every row is the single colour (`['forest']`), so no contrast cuff exists. OPUS2O-7 (the unpinned switch to `fold_title`) and OPUS2O-9 (the dead retail citation in `STOCKING_SIZE_SOURCE`) are carried unchanged. OPUS2O ruled all three LOW follow-ups under its SHIP. They are listed here so they are not lost in the merge. | `F.stocking(C(…, colours={one}))` → row colours `['forest']` |
| INTEG5C-5 | INFO | **How the reviews cover the delta.** OPUS2O reviewed only the last increments: 940f70e6..09122165 (pet bed, SHIP) and 0ef8a716..a859f6fe (stocking, SHIP). But it probed the **behaviour of the full heads** (84 pet titles, and 104 stocking titles × 6 categories), and it ran the suites on both heads. The earlier commits in 55450fc3..a859f6fe were reviewed in a chain: d0a7685f/5c7b984a by OPUS2J, 7d220e01 by OPUS2K, the stocking by OPUS2L, and 940f70e6 by OPUS2N. Together these cover every commit 52f9f4b5 carries. Because of INTEG5C-1, the integrated code in all 6 files is exactly the code OPUS2O reviewed at a859f6fe, apart from a8ce0072's own vessels/pipeline lines, which INTEG5B covers. One caveat: OPUS2O's probes ran on the 55450fc3 base, not on a8ce0072. INTEG5C-3 and the suites below cover that gap. | `git log 55450fc3..a859f6fe`; OPUS2O verdict table |
| INTEG5C-6 | INFO (verified) | **f8bf2782 keeps the guard's intent and loses no real detection.** The guard lists every src file that references the `sample_photo` module, so that a new caller of `requirement`/`for_publish` with a stage is seen. On f8bf2782, the only file the substring scan finds and the word scan does not is `publish/pdf.py`, whose 10 hits are all the unrelated `sample_photo_placeholders` kwarg. No file is added. The expected list is unchanged. **Mutants inserted in the live tree (each kills the test):** `from . import sample_photo`, `from .sample_photo import requirement` and `importlib.import_module('brambleloop.publish.sample_photo')` in `pdf.py`, and `from ..publish import sample_photo as _sp` in `products/inventory.py`. **String mutants:** `from X import (a, sample_photo)`, `import ….sample_photo as sp`, `import_module('.sample_photo', pkg)`, `getattr(q, 'sample_photo')`, `q.sample_photo.for_publish(…)` and `… import sample_photo as _sp` all match both scans. **Lost only:** identifiers that contain the name inside a longer word (`sample_photo_placeholders`, `sample_photos`, `_sample_photo`). None of these can name the module. **Missed by both:** a dynamically built name (`'sample_' + 'photo'`), so this is not a regression. The secondary checks on `physical_upgrade.py` (lines 31-35 of the test) are unchanged. | `$S/mut.py`; the live mutants listed |
| INTEG5C-7 | INFO | **a8ce0072 was red on this test.** With 52f9f4b5's copy of `test_w4_launchfix.py` restored, the guard fails on the integrated tree: `pdf.py` appears in `users`. pdf.py had the kwarg already in a8ce0072, so the failure predates this delta. INTEG5B's SHIP for a8ce0072 did not exercise `test_w4_launchfix`. So the full certification suite must run on f8bf2782, not a8ce0072. | restore the 52f9f4b5 test file → `FAIL [… 'brambleloop/publish/pdf.py' …]` |

**Removed or weakened assertions: none.**
- **52f9f4b5:** the only test lines removed are in `test_opus2_draft_constructions.py`. "Cat Bed" is
  taken out of the N3.2 refused list and is now asserted `VESSEL and != FLAT_PANEL`. That is the
  reviewed a859f6fe change, and the flat-route ban it protects is kept.
- **f8bf2782:** the predicate is narrowed only by the false positive above. The expected list is unchanged.

## Suites (f8bf2782, one at a time, `PYTHONPATH=src:tests python3 tests/<suite>.py` from `brambleloop/`)

| Suite | Result |
|---|---|
| test_opus2_pet_bed | rc 0, 7 OK, 0 failed |
| test_opus2_stocking | rc 0, 7 OK, 0 failed |
| test_opus2_draft_constructions | rc 0, 18 OK, 0 failed |
| test_fallback_draft_provenance | rc 0, 1 OK |
| test_opus2_size_claims | rc 0, 13 OK, 0 failed |
| test_launch0 | rc 0, 52 OK |
| test_w4_launchfix | rc 0, 32 passed, 0 failed |
| test_vacuity | rc 0, 8 OK |
| test_shadow | rc 0, 10/10 OK (re-run 07:05:24Z–07:33:03Z; the first run stopped at the reviewer's 900 s timeout after 3/10 and is not counted) |

The full suite was not run, as instructed. Nothing is UNKNOWN.

## Commands

```
git fetch origin claude/w5-INTEG1 opus2/p0-stocking claude/w5-SECREVIEW-INTEG5B
git diff --name-only a8ce0072 52f9f4b5
git diff --stat 55450fc3 a859f6fe -- brambleloop/src brambleloop/tests
for F in <6 files>: git merge-file -p ours(a8ce0072) base(55450fc3) theirs(a859f6fe) | cmp - <(git show 52f9f4b5:F)
diff <(git diff -U0 55450fc3 a8ce0072 -- F | grep '^[-+][^-+]') <(git diff -U0 a859f6fe 52f9f4b5 -- F | grep '^[-+][^-+]')
git merge-base --is-ancestor f96d7bd2 55450fc3
git diff f96d7bd2 a8ce0072 -- brambleloop/src/brambleloop/publish/{withholding,release_gates}.py brambleloop/src/brambleloop/products/vessels.py
git worktree add --detach $S/wt f8bf2782
python3 $S/mut.py $S/wt/brambleloop      # old vs new users predicate + string mutants
# live mutants: append an import line to publish/pdf.py or products/inventory.py, run
#   test_img_stage_only_activation_asks_for_the_activation_stage_and_nothing_internal_does, restore
python3 $S/e2e.py                         # plan/compile/title_promise/name_truth/size_claims probe
PYTHONPATH=src:tests python3 tests/<suite>.py   # each suite above, one at a time
```
