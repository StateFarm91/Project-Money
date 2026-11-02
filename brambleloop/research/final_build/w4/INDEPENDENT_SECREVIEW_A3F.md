# INDEPENDENT SECREVIEW A3F: delta review of origin/opus2/p0-photo-asset-review, 8d98bf4c..c2174947

Subject: `c21749471d000c0baf0c83e5530f7d6a59e89700`. Commits: 637e011f (SHARED W-PHYSFIX:
`lead_with_if_qualifying` takes the photo review lock) and c2174947 (A3D-1..5 fixes). Prior
report: A3D (origin/claude/w5-SECREVIEW-A3D). Mode: read-only. Detached scratch worktrees,
suites run one at a time, no push or deploy. Date 2026-11-02 (UTC).

## Verdict for c2174947: DO NOT SHIP (1 MED, no HIGH)

- **A3D-1 to A3D-5 are fixed for the cases they reproduced.** The q_later case now promotes,
  approves and rejoins the set. The churn stops. Lock failure is a per-frame UNKNOWN. K7, K9
  and K12 are killed.
- **The shared physfix lock does not deadlock.** No session is nested, the lock order is
  consistent, and a contended lock is bounded at the 5 s busy timeout, then UNKNOWN. Postgres
  was not run (UNKNOWN).
- **The hash gate cannot be used to skip a needed re-review.** A frame that is not re-opened
  stays excluded and unapproved.
- **The lock-failure UNKNOWN never approves** (F8 killed, `long_writer` probe).
- **Tests were not weakened.** The test diff is additions only.
- **The branch merges cleanly into INTEG1.** The INTEG1 tip 7c42e706 is an ancestor, so it is
  a fast-forward.
- **The blocker is A3F-1 (MED, liveness, the same class as A3D-1).** Suppose a photo frame
  already leads (position 1, `leads_gallery=True`) and is then held as not qualifying. The
  promotion guard still counts it as "a photograph leads", so a qualifying photo on file is
  never moved first. The excluded leader also keeps position 1, so `listing_set` adds
  `frame set (#65): no_hero`. The listing can then never satisfy SAMPLE_PHOTO_REQUIRED, and
  nothing heals itself. It fails closed.

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| A3F-1 | MED (liveness) | **An excluded leading photo blocks promotion of a qualifying photo, for good.** `_promote_if_leaderless` sets `photo_leads` from any PHOTO frame with `leads_gallery is True`, including one carrying the `photo not qualifying:` reason, which `_frames` excludes. Promotion is also attempted only for frames re-opened from NOT_QUALIFYING, never for a qualifying supplement that was AWAITING and then approved. The excluded leader stays at position 1 with `leads_gallery=True`. The set `_frames` certifies has no position-1 frame (`no_hero`), and its first image is not a photo. `awaiting_frames` is empty afterwards, so no sweep acts again. Trigger: the leading photo lapses (bytes lost, attestation or hash mismatch, rights removed) before its review, while another qualifying photo is on file. Owner workaround: re-attesting the qualifying photo calls `lead_with_if_qualifying`, which moves it first. The A3D-1 fix assumed "a set already led by a photograph". Fix: count only non-excluded leaders in `photo_leads`. When the review marks a leader NOT_QUALIFYING, demote it (`leads_gallery=False`, move it behind). Or have the sweep promote the first qualifying photo whenever the effective first frame of `_frames` is not a photo. Add a test for each shape. | `a3f_probe excluded_leader2` (two attested qualifying photos; the leading one's attestation removed before review): end state is frame 5 at pos 1, `leads True`, `photo not qualifying: ...`, excluded; frame 4 at pos 2, approved supplement. `_frames` positions are [2,3,4,5]. Real `listing_set` reasons include `frame set (#65): no_hero`. `qualifying photos on file: [photo 1]`. Later sweeps review 0 frames. `excluded_leader_b_held` (leader lapses; second photo held, then qualifies by a later full make): the second photo is approved as a supplement at **position 5, behind the renders**. Certified first image: "is not the unedited sample photograph". |
| A3F-2 | LOW | **A photo frame at position 1 without `leads_gallery` loops forever.** When the photo is filed into a release with no other frames (appended, `leads=False`, so position 1) and qualifies later, `lead_with_if_qualifying` takes the `frames[0] is mine[0]` early return, returns True and never sets `leads_gallery=True`. The review then takes the supplement branch and fails `frame_order_valid` (`position > 1`). The A3D-1 branch resets the frame to AWAITING, and every hourly sweep re-reviews it and writes an audit row, forever. `attest_unedited` hits the same early return. It fails closed. Fix: in the early return, set `leads_gallery=True` and `[AWAITING]` when the first frame is the photo but not marked as leading. | `a3f_probe pos1_no_lead`: sweeps 0, 1 and 2 each give `reviewed=1 approved=0 refused=[frame 1: ['frame_order_valid']]`. |
| A3F-3 | LOW | **A3D-2 is fixed only for the writer it named.** `lead_with_if_qualifying` now takes the lock (F6 killed). Two other writers of `approved` and `blocked_reasons` still read without the lock and write after the review commits: `release_gates._recheck_listing_certificates`, which invalidates (`approved=False` plus a prepended reason), and the `runtime.release` asset writer (`row.approved = not reasons`). The stale-copy pattern (SQLAlchemy does not send `approved=False` when the loaded value was False) can still leave `approved=True` beside a blocking reason until the next review. Gates read the reasons, so release stays blocked. Code reading only for those two writers; not reproduced with them. | The generic-writer probe `race_move` still ends `(4, 999, PHOTO, approved True, ..., [AWAITING, 're-marked by a concurrent upgrade'])`. Its writer takes no lock, as a stand-in. |
| A3F-4 | INFO | **Mutant F5 survives** (promote without requiring the NOT_QUALIFYING reason). This is nearly equivalent: promoting an AWAITING photo in a set no photo leads is still guarded by `_leads_gallery`. | mutants table |
| A3F-5 | INFO | **The test count in the claim is wrong.** The author says "23/23 with 6 new tests". `test_opus2_photo_asset_review` has 18 tests at c2174947, 7 of them new, and all 18 pass. | suite log |
| A3F-6 | INFO | **The OperationalError catch wraps all of `_review_frame`.** Any OperationalError, not only lock contention, is reported as `UNKNOWN: write lock not taken`. The label is misleading, but it always refuses (it fails closed). `_leads_gallery` in `lead_with_if_qualifying` is still read before the lock. A lapse in that window puts a non-qualifying photo first, but the review then marks it terminal and it is excluded (`promote_race_lapse`: approved 0, requirement "no unedited photograph ... on file"), so it fails closed. | code reading; probe |

## Adversarial checks

| Check | Result |
|---|---|
| q_later (A3D-1 repro) | Sweep 0 gives `approved=1`. The frame ends at pos 1, `leads True`, approved, `[]`, and is in the set. Sweeps 1 and 2 review 0 frames. The final frame state is identical to the normal attested baseline. Certifying those frames with every gate passed satisfies `requirement`. End-to-end activation in the fixture is blocked identically in the baseline by unrelated fixture gates (job_purpose_mismatch, mobile QA, gallery quality). |
| Promotion never puts a non-photo or non-qualifying frame first | `lead_with_if_qualifying` moves only a PHYSICAL_PRODUCT_PHOTO frame whose sha is the photo's, and only after `_leads_gallery` (the gate's own predicate). A forged render carrying `physical_photo_id` and a NOT_QUALIFYING reason is never re-opened (`awaiting_frames` filters on the class) or moved (`non_photo_pid`). The lapse race fails closed (A3F-6). |
| Physfix lock: deadlock and nesting | `attest_unedited` closes its session before calling `lead_with_if_qualifying`. `_promote_if_leaderless` closes its read session before the call. The sweep runs promotion and then review sequentially. No session is opened inside a lock-holding session that writes: `_checks` only reads, through other connections, in WAL. Postgres: both writers take the advisory lock first. `plan_upgrade` takes row locks but never asks for the advisory lock, so there is no cycle. SQLite contention is bounded at 5 s and becomes UNKNOWN (`long_writer`: sweep returned in 5.0 s with `UNKNOWN: write lock not taken (OperationalError)`). |
| Hash-gated re-open | Re-open requires `photo_id == pid` and the frame sha to equal the qualifying entry's sha. A frame that is not re-opened keeps `approved=False` and stays excluded. It can never be approved, since the hash check would fail. A frame with no sha is never re-opened. No path skips a review that could lead to approval. `churn`: sweeps 1 and 2 review 0 frames, the audit rows stay at 1, and no certificate records are written. |
| Lock-failure UNKNOWN | It returns `approved False` and writes nothing. F8 (lock failure reported approved) is killed. |
| Test diff 8d98bf4c..c2174947 | Only `+` lines. No assertion was removed or weakened. |

## Prior findings status

| ID | Status at c2174947 |
|---|---|
| A3D-1 (MED liveness) | **Fixed for the reproduced case** (q_later; F1 and F3 killed). **Residual: A3F-1 (MED)**, a leading photo that is excluded. |
| A3D-2 (LOW stale approved) | **Fixed for `lead_with_if_qualifying`** (F6 killed). Residual: A3F-3 (LOW), the other unlocked writers. |
| A3D-3 (LOW churn) | **Fixed** (`churn`; F2 killed). A separate churn source remains: A3F-2. |
| A3D-4 (LOW mutants survive) | **Fixed**: K7, K9 and K12 are killed, and the re-open-from-terminal branch is now tested. |
| A3D-5 (LOW sweep raises) | **Fixed** (`long_writer`; F7 killed). |
| A3D-6 (Postgres) | Still UNKNOWN (not run). |
| A3D-7 (`_stored_frames` include excluded frames) | Unchanged; not re-reviewed. |
| A3D-8 (wrong SHA in the commit message) | Not applicable to this delta. |

## Mutants (scratch worktree a3fmut, restored after each; `git status` clean afterwards; suite test_opus2_photo_asset_review)

| Mutant | Result |
|---|---|
| K7 UNKNOWN may be terminal | KILLED |
| K9 `_reviewable` AWAITING only | KILLED |
| K12 re-approval keeps the NOT_QUALIFYING reason | KILLED |
| K4 re-open without the qualifying and hash check | KILLED |
| F1 remove promotion (`_promote_if_leaderless`) | KILLED |
| F2 remove the hash gate in `awaiting_frames` | KILLED |
| F3 remove the A3D-1 reopened-awaiting branch | KILLED |
| F4 promote even when a photo leads | KILLED |
| F5 promote without requiring the NOT_QUALIFYING reason | **SURVIVED** (A3F-4, nearly equivalent) |
| F6 remove `_lock` from `lead_with_if_qualifying` (physfix) | KILLED |
| F7 remove the OperationalError catch | KILLED |
| F8 lock failure reported approved | KILLED |
| F9 reopened frame reset without AWAITING | KILLED |

12 of 13 are killed.

## Suites (venv-integ4, worktree at c2174947, run one at a time)

| Suite | Result |
|---|---|
| test_opus2_photo_asset_review | PASS (18/18) |
| test_physfix_photo_first | PASS (8/8) |
| test_physfix | PASS (48/48) |
| test_w4_launchfix | PASS (32 passed, 0 failed) |
| test_opus2_photo_led_gallery | PASS (0 failed) |
| test_cert_publish_gates | PASS (0 failed) |
| test_swarm_runtime | PASS (10 OK, 0 failed) |
| test_shadow | **UNKNOWN**: hit the 2400 s timeout (rc=124) under heavy load from other agents' runs (load average about 7). It reached 5 OK and 0 FAIL before the timeout. |

## Merge

`git merge-tree --write-tree origin/claude/w5-INTEG1 c2174947` gives a clean result (tree
6cfafd76). The INTEG1 tip 7c42e706 is an ancestor of c2174947, so the merge is a fast-forward.

## Artefacts

Probes: `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a3f-probe/a3f_probe.py`
(reuses `a3d-probe/a3d_probe.py`). Mutants: `.../scratchpad/a3f-probe/a3f_mut.py`. Logs:
`.../scratchpad/a3f-probe/logs/`.
