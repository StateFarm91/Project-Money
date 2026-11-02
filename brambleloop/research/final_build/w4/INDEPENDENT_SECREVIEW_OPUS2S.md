# INDEPENDENT SECREVIEW OPUS2S: P0-PHOTO-ASSET-REVIEW (origin/opus2/p0-photo-asset-review)

Subject: c056028d (publish/photo_asset_review.py, runtime/photo_review_ops.py, wiring) and
5a47cd8e (swarm band, test_w4_launchfix sample_photo users guard). Base 65df7b93. Reviewer
mode: read-only, scratch worktrees only, one suite at a time. Date 2026-11-02 (UTC).

## Verdict: DO NOT SHIP (changes required; no HIGH)

The core design is sound. The approval predicate is deterministic and makes no model call. It
reuses the publication gate's own predicate, `sample_photo.qualifying_photos`, which binds slug,
version, the owner's Command Center attestation of the exact SHA, the intake attestation, the
rights basis, a passed full make bound to this release's content, bytes in the store and "not
system-made". Both UNKNOWN and exceptions mean refusal. A render, whether labelled as a render
or relabelled as a photo, was refused in every attempt. No publish path, spend, owner-authority
change or SHADOW change is involved. `for_publish` still runs `sample_photo.requirement`
independently, and the owner veto and withholding are enforced there.

The problem is the approval write. It is not bound to the checks that justified it. The write
happens in a separate session with no re-read and no row lock (OPUS2S-2). It also approves a
frame that does not carry the "awaiting" reason (OPUS2S-1). Both are cheap to fix, and this
code grants a publication-gating approval, so they should be fixed before merge. The liveness
gap OPUS2S-3 means the P0 is only partly solved.

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| OPUS2S-1 | MED | `review_frame` does not require `AWAITING` to be in `frame.blocked_reasons` before it approves. Take a frame with `approved=False, blocked_reasons=[]`, which `release_gates.listing_set` reads as "withdrawn or invalidated; must be rebuilt and re-checked". Given its id, the review sets `approved=True`. The hourly sweep only selects awaiting frames, but the job takes `inputs.frame_id` for any frame, so the precondition is only a property of the sweep. Fix: refuse (or no-op) unless `AWAITING in blocked_reasons`, checked inside the write session. | repro A in `opus2s_repro.py`: `[A withdrawn-no-reason] approved=True`, then `frame.approved after review: True` |
| OPUS2S-2 | MED | TOCTOU: the checks are read in session 1 (plus `qualifying_photos`/`_synthetic_shas` sessions). The write in session 2 re-fetches the frame by id and clears `AWAITING` without re-verifying sha, position, asset_class or claims, and without `with_for_update`. A concurrent `plan_upgrade` or `lead_with_if_qualifying` can commit in between. If that writer re-marks the frame awaiting or moves it, the review clears the fresh reason and approves on stale checks. Publication is still protected by `sample_photo.requirement` in `for_publish`, so this is not HIGH. Fix: in the write session, lock the frame row and re-assert that sha, position, asset_class, claims and blocked_reasons equal what was checked; otherwise refuse and leave it for the next sweep. | repro D: after the race, `position 2 approved True []`, and a fresh review now says `['frame_order_valid']` |
| OPUS2S-3 | MED (liveness) | A second qualifying photo of the same release deadlocks. `plan_upgrade` puts photo 2 first with `leads_gallery=True`, and photo 1 (already approved) moves to position 2 still claiming `leads_gallery=True`. The review then refuses photo 2 for good (`leaders != [frame]`) and it stays AWAITING, and `_classify(AWAITING)` is a failing gate, so the listing set never certifies. Likewise, any non-qualifying photo frame appended last (for example a tester photo without a full make) stays AWAITING forever and blocks the whole set. Neither case is new, but both mean "a photo-led set can certify" holds only for exactly one photo frame. Fix options: clear `leads_gallery` on demoted frames in `plan_upgrade`/`_renumber`, and give non-leading supplementary photo frames a defined disposition. | repro C: `[(5, 1, True, False, [AWAITING]), (4, 2, True, True, [])]`, `failed=['frame_order_valid']`, `awaiting forever: [5]`. Repro E: non-qualifying appended photo is `still awaiting: True` |
| OPUS2S-4 | LOW | Test gaps (mutation survivors that are not equivalent): the sole-leader rule (M9), the positions 1..n rule (M10), provenance=="camera" (M12) and the generated-frame clause (M13). Each can be deleted with all 5 tests green. The explicit `asset_class != PHOTO_CLASS` guard (M15) also survives. In practice that guard is backed by `_synthetic_shas` and `qualifying_photos`, which refuse any SHA held by a non-photo ListingAsset row, but it is the guard behind the "never approve a render as a photo" claim, and no test isolates it. | mutations table below |
| OPUS2S-5 | LOW | The new `test_w4_launchfix` guard for photo_asset_review is weaker than the existing physical_upgrade guard. It checks `"requirement(" not in src` and `sample_photo\.(\w+)\(`, so `getattr(sample_photo, "requirement")(...)` passes it (G2). The physical_upgrade guard's `sample_photo\W+(\w+)` pattern would catch that. Rebinding the module to an alias (G3) passes both. Suggest reusing the `sample_photo\W+(\w+)` assertion for par_src. | G1 direct call: KILLED; G2 getattr: survives; G3 alias: survives |
| OPUS2S-6 | LOW | Two concurrent reviews, or a review racing another `listing_set(issue=True)` caller, can each insert a `ListingSetCertificateRecord(state="valid")` for the same frame hashes. The check-then-insert in `certificate_step` is unlocked. This is the existing listing_set behaviour, not new, but the new job adds a caller. The frame write itself is idempotent (repro B). | code: `release_gates.certificate_step` (current lookup, then `s.add(rec)`) |
| OPUS2S-7 | INFO | INTEG5B-4 (PatternVersion.certificate races): no interaction found. The review and `listing_set` write only `ListingAsset` and `ListingSetCertificateRecord`. `PatternVersion.certificate` is written by pipeline, release and withholding, which this code does not call. | grep of `.certificate =` writers |
| OPUS2S-8 | INFO | Registration is consistent. Checked: worker CADENCES (hourly, agent asset_truth); pipeline WORK_KEYS `("work_done",)` and the handler import; registry asset_truth allowed_job_types; authority class TEST, not gated (same as gate.asset_truth); swarm band proven_winner; charters department `visual`; autonomy_map regenerated (138/170/34/84 on the merged tree). `retention.unknown_read_actions()` is `[]` on the merged tree: `gate.photo_asset_reviewed` is written, not read by name, so it is prunable by horizon (newest row kept). No LLM, gateway or spend import. | python check on the merged tree |
| OPUS2S-9 | INFO | The owner veto (#228) is not consulted by the review: photo frames get only the AWAITING reason from `plan_upgrade`. It is still enforced in `release_gates.for_publish` and `withholding`, so publication is not bypassed. Once approved, a frame is never re-reviewed if its binding later changes, but `for_publish` re-runs `qualifying_photos` through `requirement`. | code reading |
| OPUS2S-10 | INFO | The test_w4_launchfix edit is compatible with W5-INTEG1 f8bf2782 (whole-word `\bsample_photo\b`). photo_asset_review.py matches as a whole word and is listed, and the resolved merge keeps both `import re as _re0` and `import re as _re_par`. No assertion was removed or weakened in either commit (test diff is additions only). COORDINATION.json still says `"state": "claimed"`. | merged-tree launchfix run |

The requirement checklist (UNKNOWN never counts as PASS):

| Requirement | Result |
|---|---|
| Render as photo | Refused (repro and test) |
| Other slug or version | Refused: `qualifying_photos` filters on slug and rejects `pver != version` |
| Hash mismatch or swapped bytes | Refused (test) |
| Edited or replaced file | Refused: `bytes_on_file` re-hashes, and attestation SHA must equal photo SHA |
| Stale attestation after a new version | Refused: frames are per version and the photo must name that version. No revocation path exists, so revocation is not applicable |
| Disclosure-free claim | Refused (test) |
| Missing or unreadable record | Refused as UNKNOWN (test) |
| No LLM | PASS |
| Audit row on approval and refusal | PASS |
| Re-certification through `listing_set(issue=True)` | PASS |
| Approve ONLY when all checks hold at write time | FAIL (OPUS2S-1, OPUS2S-2) |

## Mutations (photo_asset_review.py and release.py, scratch worktree, `git checkout -- .` after each)

Killer suite: tests/test_opus2_photo_asset_review.py.

| Mutation | Result | Note |
|---|---|---|
| M1 all -> any | KILLED | |
| M2 `is True` -> truthy (UNKNOWN strings) | KILLED | |
| M3 binding drops `entry is not None` | KILLED | |
| M4 binding drops slug/version equality | survived | equivalent: qualifying filters slug and rejects other versions |
| M5 hash check -> True | KILLED | |
| M6 hash drops bytes_on_file | survived | equivalent: qualifying requires bytes |
| M7 hash drops frame==photo==attested | survived | equivalent: entry.sha == frame and qualifying requires attested == photo (commit says so) |
| M8 order drops position==1 | KILLED | |
| M9 order drops sole-leader | **survived** | OPUS2S-4 (and see OPUS2S-3) |
| M10 order drops 1..n | **survived** | OPUS2S-4 |
| M11 claims drops allow-list | KILLED | |
| M12 claims drops provenance camera | **survived** | OPUS2S-4 |
| M13 claims drops generated | **survived** | OPUS2S-4 |
| M14 claims drops synthetic | survived | equivalent: qualifying rejects synthetic SHAs |
| M15 drops asset_class guard | survived | equivalent in practice (`_synthetic_shas`), untested directly |
| M16 clears all reasons | KILLED | |
| M17 exception approves | KILLED | |
| M18 no audit row | KILLED | |
| M19 upgrade does not enqueue review | KILLED | |
| M20 sweep takes non-awaiting frames | KILLED | |
| G1 par calls `sample_photo.requirement(` | KILLED (test_w4_launchfix) | |
| G2 par calls `getattr(sample_photo,"requirement")(` | survived | OPUS2S-5 |
| G3 par aliases module then calls | survived | OPUS2S-5 (physical_upgrade guard shares the gap) |

## Test runs (venv-integ4, one suite at a time)

Branch worktree (origin/opus2/p0-photo-asset-review @ 5a47cd8e):

| Suite | Result |
|---|---|
| test_opus2_photo_asset_review | 5/5, exit 0 |
| test_physfix_photo_first | 8/8, exit 0 |
| test_w4_launchfix | 32 passed, exit 0 |
| test_cert_publish_gates | 0 failed, exit 0 |
| test_vacuity | exit 0 |
| test_swarm_runtime | exit 0 |
| test_opus2_photo_led_gallery | not on this branch (exists only on w5-INTEG1); run on the merged tree |

Merged tree (w5-INTEG1 4af3418f + branch, conflicts resolved in scratch):

| Suite | Result |
|---|---|
| test_opus2_photo_led_gallery | 0 failed, exit 0 |
| test_opus2_photo_asset_review | 5/5, exit 0 |
| test_w4_launchfix | 32 passed, exit 0 (both guards active) |
| test_physfix_photo_first | 8/8, exit 0 |
| test_w4_c12_wiring | exit 0 (committed map counts == live after regeneration) |
| test_swarm_runtime | **exit 1** |

The test_swarm_runtime failure is `test_every_runnable_job_type_has_a_band_decided_rather_than_defaulted`.
The unbanded jobs it reports are `chain.successors`, `improve.commercial_lessons`,
`intel.scan_evidence`, `learning.knowledge_gaps` and `listing.package`. None of them is
`assets.photo_review`, and none of them has a JOB_BANDS entry on origin/claude/w5-INTEG1
itself (grep count 0). The failure comes from w5-INTEG1, not this branch, and it is not counted
as a PASS for that suite.

## merge-tree

`git merge-tree --write-tree origin/claude/w5-INTEG1 origin/opus2/p0-photo-asset-review` gives
exit 1 with 4 conflicts, all mechanical:

| File | Conflict | Resolution |
|---|---|---|
| COORDINATION.json | both sides edited the claims list | take both entries |
| brambleloop/src/brambleloop/autonomy/autonomy_map.json | generated_at and counts | regenerate with `python -m brambleloop.autonomy.map --write ...`, which gives 138/170/34/84 |
| brambleloop/src/brambleloop/runtime/pipeline.py | adjacent ops imports (listing_package_ops vs photo_review_ops) | keep both |
| brambleloop/tests/test_w4_launchfix.py | `import re as _re0` (INTEG1 whole-word) vs `import re as _re_par` | keep both; the guard is not weakened |

Auto-merged cleanly: registry.py, classes.py, release.py, worker.py, orchestrate.py.

## Commands

```
git -C /home/user/Project-Money fetch origin opus2/p0-photo-asset-review claude/w5-INTEG1
git -C /home/user/Project-Money worktree add --detach <scratch>/opus2s origin/opus2/p0-photo-asset-review
git show c056028d 5a47cd8e
cd <scratch>/opus2s/brambleloop && PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/<suite>.py
PYTHONPATH=src:tests .../python <scratch>/opus2s_repro.py          # repros A-E
.../python <scratch>/opus2s_mut.py                                  # M1-M20
git merge-tree --write-tree origin/claude/w5-INTEG1 origin/opus2/p0-photo-asset-review
git worktree add --detach <scratch>/opus2s-merge origin/claude/w5-INTEG1; git merge --no-commit --no-ff origin/opus2/p0-photo-asset-review
```

Scratch scripts: /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/opus2s_repro.py
and /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/opus2s_mut.py.
Logs: /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/opus2s-logs/.
The scratch worktrees were removed after the review.
