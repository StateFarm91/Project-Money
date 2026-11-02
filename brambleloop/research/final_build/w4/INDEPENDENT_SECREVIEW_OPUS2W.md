# INDEPENDENT SECREVIEW OPUS2W: A3 fixes for P0-PHOTO-ASSET-REVIEW (origin/opus2/p0-photo-asset-review)

Subject: a14c71d7 (physical_upgrade `_demote_leaders`) and d1f65b61 (S-1, S-2, S-3, S-4, S-5),
delta 5a47cd8e..d1f65b61. Prior review: OPUS2S (origin/claude/w5-SECREVIEW-OPUS2S). Reviewer mode
was read-only: scratch worktrees only, one suite at a time, no deploy, no spend, no Railway.
Date 2026-11-02 (UTC).

## Verdict: DO NOT SHIP (2 MED, no HIGH)

What is fixed:

- **S-1 is fixed.** A withdrawn frame (approved=False, no reasons) is refused when given its
  frame_id (repro A). A near-miss reason string is refused too (A2).
- **The repro-D TOCTOU is refused.** The frame is moved and re-marked between `_checks` and the
  write session, and the review reports `changed=['position']`.
- **The two-qualifying-photo deadlock is gone** (C and C2). No frame is left awaiting, and the
  sweep approves the leader and the supplement.
- **The shared `_demote_leaders` change does not break PHYSFIX or photo-led behaviour.** These
  suites pass: test_physfix 46/46, test_physfix_photo_first 8/8, and
  test_opus2_photo_led_gallery on the merged tree.
- **The S-4 mutants are killed:** M9, M10, M12, M13 and M15.
- **G2 (getattr) and G3 (alias assignment) are killed.**
- **No assertion was removed or weakened.** The test diff adds lines only.
- **No PatternVersion.certificate writes, no publish path and no spend import** (INTEG5B-4 holds).

What is not fixed:

- **S-2 does not meet the integrator's criterion.** No BEGIN IMMEDIATE is taken on SQLite. A real
  two-thread race on a file SQLite database still approves a frame that was moved, and it erases
  the concurrent writer's re-mark (OPUS2W-1).
- **S-3 "nothing stays awaiting forever" is still open** for a photo that does not qualify. The
  author deferred it (OPUS2W-2).
- **The new supplement rule is largely untested** (OPUS2W-3).

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| OPUS2W-1 | MED | **The S-2 criterion is not met.** The checks still run in their own sessions (`_checks`, `qualifying_photos`, `_synthetic_shas`), not in the write transaction. The write session re-reads the frame with `.with_for_update()` and compares a snapshot of the frame's own fields. On SQLite, `with_for_update` is a no-op and no `BEGIN IMMEDIATE` is issued (the codebase's own pattern for this is in `release._serialise_owner_queue` and `gateway.anthropic.budget_lock`). The locked SELECT therefore takes no lock. A writer that commits between that SELECT and the review's flush is overwritten, and the review approves a moved frame and clears the writer's new reasons. The S-2 test only monkeypatches `_checks`, so the change always lands before the locked read. It never exercises the read-to-flush window, and mutant N3 (drop `with_for_update`) survives. Production is Postgres (`core.db.resolve_url` refuses hosted SQLite), and there the row lock should serialise this. That was **not verified** here (UNKNOWN: no Postgres server could be started under the scratchpad path limits). Fix: issue `BEGIN IMMEDIATE` on SQLite file databases in the write session (as `budget_lock` does), and add a thread-race test with a barrier between the locked read and the flush. | repro F (`opus2w_repro.py F`): a `before_flush` barrier in the reviewer thread; the writer thread renumbers and sets `[AWAITING, "re-marked by a concurrent upgrade"]`, approved=False, and commits (`writer finished before A flushed: True`). Result: `approved=True`, `after race: position 2 approved True []`. F2 (re-mark only, no move): `position 1 approved True []`, so the re-mark is lost. |
| OPUS2W-2 | MED (liveness) | **"Nothing stays awaiting forever" is not met.** A photo frame that does not qualify (no owner attestation, or no passed full make) stays AWAITING for every sweep. Because AWAITING is a failing gate reading, it keeps the whole listing set from certifying. E2 shows this hits a set that already has an approved, qualifying leading photo: one tester upload that has not been attested re-blocks the set indefinitely. d1f65b61 says outright that this is left as a product decision. The refusal is named in the sweep output and the audit row (`attestation_binds_release`, `hash_matches_attested_sample`), but the frame never leaves "awaiting". A related case was found by code reading and **not reproduced** (UNKNOWN): a photo attested before its full make passes is appended with `leads_gallery=False`. `lead_with_if_qualifying` runs only from `attest_unedited`, so the photo is never promoted. In a render-led gallery the supplement rule then finds no leader at position 1 and refuses it for good, even after it qualifies. | repro E: `still awaiting: True`. Repro E2: first photo approved; then intake and plan of a photo with no attestation; after 3 sweeps it is refused `['attestation_binds_release','hash_matches_attested_sample']` and still blocks. |
| OPUS2W-3 | LOW | **The new supplement branch of `frame_order_valid` is not pinned.** Replacing the whole branch with `True` is killed, but every sub-condition survives on its own. N6 (`len(leaders)==1` changed to `>=1`) lets two leaders through. N7 (drop "the leader is at position 1"). N9 (drop the contiguous 1..n check). N8 (drop `position > 1`) is equivalent, because (slug, version, position) is unique and the leader holds position 1. Separately, removing `_demote_leaders` from `lead_with_if_qualifying` (P2) survives both test_opus2_photo_asset_review and test_physfix_photo_first. Only the `plan_upgrade` call (P1) is pinned. | mutations table |
| OPUS2W-4 | LOW | **The supplement rule does not check what the leader is.** It needs only "exactly one frame claims `leads_gallery` and it is at position 1"; it does not require that leader to be a PHYSICAL_PRODUCT_PHOTO, let alone an approved or qualifying one. A qualifying photo is approved as a supplement behind a DIGITAL_TWIN_RENDER that claims to lead. Today no writer sets `leads_gallery` on a frame that is not a photo, and `for_publish` re-runs `sample_photo.requirement` (first frame) on its own, so this is defence in depth. | repro G: `approved=True` with the render at position 1 claiming `leads_gallery=True` |
| OPUS2W-5 | LOW | **A frame deleted between the checks and the write is reported as approved.** The write session finds `frame is None`, skips the write, but leaves `out["approved"]=True`. The audit row records `approved: True`, and `sweep` counts it in `approved` and `work_done`. No frame is actually approved, but this is a false record of an approval. Fix: set approved=False with `failed=["frame_gone"]` when the locked read returns None. | repro H: `approved=True frame_approved=None`; audit detail `approved: True` |
| OPUS2W-6 | LOW | **The S-5 guard can still be evaded by an alias on a multi-name import line.** G2 (`getattr(sample_photo,...)`) and G3 (`sp = sample_photo`) are killed. G4 survives: `from . import release_gates, sample_photo as sp` with calls through `sp` and `getattr(sp, "require" "ment")`. The pattern `import\s+[.\w]*sample_photo\s+as\s` does not match after a comma, and the count balances because a docstring or comment mention is counted on both sides. G5 (`importlib.import_module(__package__ + ".sample_" + "photo")`) also survives; a static guard cannot be expected to catch that. Suggest asserting that no `sample_photo\s+as\b` appears anywhere, and counting outside docstrings and comments. | mutations G4, G5 |
| OPUS2W-7 | INFO | **The branch is still not rebased.** It is based on 65df7b93 and does not contain 50937469 (`merge-base --is-ancestor` is false). origin/claude/w5-INTEG1 is now db463142, one commit ahead of 50937469. `git merge-tree --write-tree` against either gives exit 1 with **5** conflicts (OPUS2S had 4; `swarm/orchestrate.py` is new, because INTEG1 added JOB_BANDS next to `assets.photo_review`). All 5 are mechanical (keep both / regenerate). The merged tree passes everything listed below. | merge-tree section |
| OPUS2W-8 | INFO | **Fixes confirmed:** S-1 (A, A2); the D race refused; S-3 for qualifying pairs (C, C2: no frame left awaiting, sweep `refused: []`). The fixture's `listing_set` still reports `blocks_release=True` on C, but only for gates unrelated to asset truth (#65, #66, #80), the same as the base fixture. The test certifies through `_certify_without_touching_approval`. The approval write is still guarded by `all(check is True)`, and UNKNOWN or an exception never approves (M17-class behaviour unchanged). Demoting the leader leaves an approved frame approved with only `leads_gallery` flipped, which is truthful. | repro log |
| OPUS2W-9 | INFO | **OPUS2S-6 is unchanged.** The unlocked check-then-insert of `ListingSetCertificateRecord` in `certificate_step` was acknowledged and not changed. | code |

## Requirement checklist (UNKNOWN never counts as PASS)

| Criterion | Result |
|---|---|
| S-1 approve only frames carrying the exact awaiting reason | PASS (A, A2; N1 killed) |
| S-2 one transaction, row lock (Postgres `with_for_update`; SQLite BEGIN IMMEDIATE), re-check inside | **FAIL on SQLite** (OPUS2W-1, repro F); Postgres UNKNOWN (not run) |
| S-2 forced race never approves a moved frame | **FAIL** (F: moved frame approved) |
| S-3 two qualifying photos certify or give a named refusal | PASS for the asset-truth stage (C, C2) |
| S-3 nothing stays awaiting forever | **FAIL** (OPUS2W-2, E/E2) |
| S-3 shared physical_upgrade change keeps PHYSFIX and photo-led behaviour | PASS (test_physfix 46/46, test_physfix_photo_first 8/8, test_opus2_photo_led_gallery on the merged tree) |
| S-4 sole-leader, 1..n, camera, generated mutants killed | PASS (M9, M10, M12, M13, M15 killed) |
| S-5 guard catches getattr and module aliases | PARTIAL (G2, G3 killed; G4 import-line alias survives) |
| Never approves a render or a wrong-release photo | PASS (unchanged checks; the class guard M15 is now pinned) |
| Fail closed on UNKNOWN | PASS (unchanged), except OPUS2W-5 misreporting |
| No publish or spend; INTEG5B-4 | PASS (diff grep: no `.certificate =`, PatternVersion, gateway or publish call) |
| No removed or weakened assertions | PASS (test diff is additions only) |

## Mutations (scratch worktree, restored after each)

| Mutant | Suite | Result |
|---|---|---|
| N1 S-1 drop the AWAITING-in-reasons check | photo_asset_review | KILLED |
| N2 S-2 drop the snapshot compare | photo_asset_review | KILLED |
| N3 S-2 drop `with_for_update` | photo_asset_review | **SURVIVED** (no real race test; OPUS2W-1) |
| N4 S-2 compare ignores blocked_reasons | photo_asset_review | KILLED |
| N5 S-2 compare ignores position | photo_asset_review | KILLED |
| N6 supplement `len(leaders)==1` -> `>=1` | photo_asset_review | **SURVIVED** |
| N7 supplement drops leader-at-1 | photo_asset_review | **SURVIVED** |
| N8 supplement drops position>1 | photo_asset_review | survived (equivalent: unique position) |
| N9 supplement drops contiguous | photo_asset_review | **SURVIVED** |
| N10 supplement branch -> True | photo_asset_review | KILLED |
| M9 leader drops sole-leader | photo_asset_review | KILLED |
| M10 leader drops 1..n | photo_asset_review | KILLED |
| M12 drop provenance camera | photo_asset_review | KILLED |
| M13 drop generated | photo_asset_review | KILLED |
| M15 drop asset_class guard | photo_asset_review | KILLED |
| P1 plan_upgrade without `_demote_leaders` | photo_asset_review | KILLED |
| P2 lead_with_if_qualifying without `_demote_leaders` | photo_asset_review | **SURVIVED** |
| P1b / P2b same, against test_physfix_photo_first | physfix_photo_first | survived (that suite does not cover demotion; it shows the change is neutral to it) |
| G2 `getattr(sample_photo, "requirement")` | w4_launchfix | KILLED |
| G3 `sp = sample_photo` then getattr | w4_launchfix | KILLED |
| G4 `from . import release_gates, sample_photo as sp` + getattr via sp | w4_launchfix | **SURVIVED** |
| G5 importlib with a computed module name | w4_launchfix | survived (out of reach of a static guard) |

## Test runs (venv-integ4, one suite at a time)

Branch worktree (origin/opus2/p0-photo-asset-review @ d1f65b61):

| Suite | Result |
|---|---|
| test_opus2_photo_asset_review | 0 failed, exit 0 (21s) |
| test_physfix_photo_first | 8/8, exit 0 |
| test_physfix (slow, once) | 46/46, exit 0 (95s) |
| test_w4_launchfix | 32 passed, exit 0 |
| test_cert_publish_gates | 0 failed, exit 0 |
| test_vacuity | exit 0 |
| test_swarm_runtime | exit 0 |

Merged tree (origin/claude/w5-INTEG1 db463142 + branch, conflicts resolved in scratch, autonomy
map regenerated: cadences 138, handlers 170, agents 34, follow_on_edges 84):

| Suite | Result |
|---|---|
| test_opus2_photo_asset_review | 0 failed, exit 0 |
| test_physfix_photo_first | 8/8, exit 0 |
| test_opus2_photo_led_gallery | 0 failed, exit 0 (526s) |
| test_w4_launchfix | 32 passed, exit 0 (INTEG1 whole-word guard and the OPUS2S-5 guard both active) |
| test_swarm_runtime | exit 0 (the OPUS2S-era INTEG1 failure is fixed in db463142) |

## merge-tree

`git merge-tree --write-tree origin/claude/w5-INTEG1 origin/opus2/p0-photo-asset-review`
(INTEG1 = db463142, which contains 50937469) gave exit 1 and tree 22027e35. The result is the same
against 50937469 directly. The branch does **not** contain 50937469, so the requested rebase
was not done.

| File | Conflict | Resolution used |
|---|---|---|
| COORDINATION.json | both sides edited the claims list | keep INTEG1's entries, append OPUS2-PHOTO-ASSET-REVIEW (valid JSON) |
| brambleloop/src/brambleloop/autonomy/autonomy_map.json | generated_at and counts | regenerate with `python -m brambleloop.autonomy.map --write` |
| brambleloop/src/brambleloop/runtime/pipeline.py | adjacent ops imports (listing_package_ops vs photo_review_ops) | keep both |
| brambleloop/src/brambleloop/swarm/orchestrate.py | JOB_BANDS: INTEG1's 5 opus2 bands vs `assets.photo_review` | keep both |
| brambleloop/tests/test_w4_launchfix.py | `import re as _re0` (whole-word) vs `import re as _re_par` | keep both; no guard weakened |

Auto-merged: registry.py, classes.py, release.py, worker.py.

## Commands

```
git -C /home/user/Project-Money fetch origin
git -C /home/user/Project-Money worktree add --detach <scratch>/opus2w-br origin/opus2/p0-photo-asset-review
git diff 5a47cd8e..d1f65b61
cd <scratch>/opus2w-br/brambleloop && PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/<suite>.py
PYTHONPATH=src:tests .../python <scratch>/opus2w_repro.py [A C D E E2 F F2 G H]
.../python <scratch>/opus2w_mut.py
git merge-tree --write-tree --name-only origin/claude/w5-INTEG1 origin/opus2/p0-photo-asset-review
git merge-base --is-ancestor 50937469 origin/opus2/p0-photo-asset-review   # false
git worktree add --detach <scratch>/opus2w-merge origin/claude/w5-INTEG1; git merge --no-commit --no-ff origin/opus2/p0-photo-asset-review
```

Scripts: /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/opus2w_repro.py
and /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/opus2w_mut.py.
Logs: /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/opus2w-logs/.
The scratch worktrees were removed after the review.
