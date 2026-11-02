# INDEPENDENT SECREVIEW A3D: delta review of origin/opus2/p0-photo-asset-review, d1f65b61..8d98bf4c

Subject commits: 6316d5c4 (merge of INTEG1), e6a1ef82 (I-A3-NONQUALIFYING-PHOTO in
`publish/release_gates.py`) and 8d98bf4c (fixes for OPUS2W W-1..W-6). Prior report: OPUS2W
(origin/claude/w5-SECREVIEW-OPUS2W). Mode: read-only. Scratch worktrees only, suites run one at a
time (two overlapped briefly, see Suites), no push, no deploy. Date 2026-11-02 (UTC).

## Verdict for 8d98bf4c: DO NOT SHIP (1 MED, no HIGH)

- **W-1 is fixed on SQLite.** The lock is taken on the write session's own connection, and a real
  file-SQLite race no longer approves a moved frame. Postgres is UNKNOWN (not run).
- **W-2 is fixed for its stated case.** A photo that does not qualify no longer holds the set
  hostage, and the exclusion cannot be used to certify a set that should fail closed. The
  activation gate still refuses without a qualifying lead photo.
- **W-3 to W-6 are fixed.**
- **The merge is correct**, and the branch merges into INTEG1 with no conflicts.
- **The blocker is A3D-1 (MED, liveness).** The re-open path does not do what the commit says for a
  photo that qualifies later through something other than `attest_unedited`, such as a full make
  that becomes bound later or a binding that failed to read when the upgrade was planned. That
  photo is re-reviewed every sweep, never promoted, and stays excluded under a stale reason. The
  listing then fails `SAMPLE_PHOTO_REQUIRED` at activation forever, even though a qualifying photo
  is on file. This fails closed (nothing unsafe is published), but it is the same liveness class
  as OPUS2W-2, which gated the last verdict.

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| A3D-1 | MED (liveness) | **A photo that qualifies later without a fresh owner attestation is stuck.** `plan_upgrade` appends it last with `leads_gallery=False`. The review gives it the terminal reason. When the photo later qualifies, `awaiting_frames` re-opens it, but the review then fails only `frame_order_valid`: the supplement rule needs a photo leader, and there is none. That failure is not a qualifying check, so the `else` branch writes nothing. The frame keeps its stale `photo not qualifying: attestation_binds_release, ...` reason and stays out of the set. It is re-reviewed and audited on every hourly sweep. `lead_with_if_qualifying` runs only from `attest_unedited`, so the photo is never promoted. `sample_photo.requirement` stays unsatisfied ("the qualifying photograph is not in a valid listing-set certificate"). The 8d98bf4c message says the sweep re-opens it on "a later attestation or passed make", but only the attestation path works. A realistic trigger: `_bound_full_makes` raises while the upgrade is planned (`binding unreadable`), so `_leads_gallery` is False, and later the binding reads. Fix: when a re-opened photo qualifies and is not first, promote it (`lead_with_if_qualifying`) before reviewing, or reset it to AWAITING. Add a test that re-opens without `attest_unedited`. | `a3d_probe.qualifies_later_without_attest` (log `q_later.log`). `qualifying_photos` is hidden at plan time and at the first review, then restored. Three sweeps each give `refused=[{'frame_id': 4, 'failed': ['frame_order_valid']}]`. The frame is `(4, pos 4, PHOTO, approved False, leads False, ['photo not qualifying: attestation_binds_release, hash_matches_attested_sample, frame_order_valid'])`, `in set: False`, `requirement satisfied: False`. |
| A3D-2 | LOW | **A concurrent writer can leave `approved=True` beside blocking reasons.** The review itself is now correct (see W-1). A writer that reads the frame while the review holds the lock, then writes after the review commits, works from a stale copy. SQLAlchemy sends only the columns that changed from what it loaded. `approved=False` equals the stale value, so it is never written, and the frame ends up `approved=True` with `[AWAITING, ...]`. `lead_with_if_qualifying` (`frame.approved = False` plus AWAITING) is such a writer. Gates read the reasons, so release stays blocked. Readers of the `approved` flag alone (`measure_impact` live_since, `launch.readiness` approved_frames, `our_competitive_reading` gallery_images) see an approval that does not exist until the next sweep re-reviews the frame. On a refusal, the review never resets the stale flag. Suggest that the review always writes `frame.approved = not reasons` when reasons are present, or that writers lock the frame row. The same thing happens on Postgres (unlocked SELECT, then a blocked UPDATE). | `race_move` (log `race.log`): the writer sets position 999, `approved=False` and the re-mark, starting mid-checks. Final state: `(4, 999, PHOTO, approved True, leads True, [AWAITING, 're-marked by a concurrent upgrade'])`. The writer's reasons and position are kept, but its `approved=False` is lost. |
| A3D-3 | LOW | **Sweep churn on a permanently mismatched frame.** If the photo qualifies but the frame's hash is not the photo's (swapped bytes), `awaiting_frames` re-opens the frame on every sweep. Each time the review re-marks it, writes an audit row and runs `listing_set(..., issue=True)`, so one hourly recomputation per such frame continues indefinitely. | `swapped_hash_churn` (log `w2.log`): sweeps 0, 1 and 2 each give `reviewed=1 not_q=[4]`, and the audit rows go 1, 2, 3. |
| A3D-4 | LOW | **The re-open branch and the UNKNOWN exclusion are untested.** Three mutants survive test_opus2_photo_asset_review: K7 (UNKNOWN checks may become terminal), K9 (`_reviewable` ignores the NOT_QUALIFYING state) and K12 (re-approval keeps the NOT_QUALIFYING reason). The W-2 test re-opens only through `attest_unedited`, and that resets the reasons to `[AWAITING]`, so the branch that reviews and clears a NOT_QUALIFYING frame never runs in the tests. On real code the branch works: a leader whose bytes vanished and came back is re-opened and approved (`bytes_lapse.log`: `reopen after restore: True`, `sweep: 1 []`, frame approved with `[]`). K7 matters for fail-closed: under it, an unreadable record (`qualifying_photos` raising) would be marked terminal and dropped from the set rather than held awaiting. Real code holds it awaiting (`unknown`: reasons `[AWAITING]`). | mutants table |
| A3D-5 | LOW | **`_lock` is outside the review's try.** If another connection holds the SQLite write lock longer than the busy timeout (5 s), `BEGIN IMMEDIATE` raises `OperationalError` out of `review_frame`, and `sweep` stops without reviewing the remaining frames. This fails closed, and the job retries next cadence. | `long_writer` (log `long_writer.log`): `sweep RAISED OperationalError ... database is locked [SQL: BEGIN IMMEDIATE]`, after 5.0 s. |
| A3D-6 | INFO (UNKNOWN) | **Postgres serialisation was not verified.** On Postgres the advisory xact lock (`0x0B2A3F07`) serialises reviews only against each other, because no other writer takes that key. Protection from writers comes from the `SELECT ... FOR UPDATE` row lock on the frame, which is now taken before the checks in the same transaction. That covers every writer that updates this frame (`_renumber` touches every frame in the set). It does not cover a write that changes only a sibling, such as a leader's claims or class. The snapshot compare that S-2 had was removed. Not run: Postgres 16 is installed, but the data directory under the scratchpad is unreachable for the `postgres` user (`/tmp/claude-0` is 0700 root). | code reading |
| A3D-7 | INFO | **The exclusion covers only `release_gates._frames`.** `runtime.release._stored_frames` and `frame_review_state` (#61) still bind to every stored ListingAsset, the excluded photo included. That is not new for photo frames (any added photo changes the stored set), and it was not reproduced. | code reading |
| A3D-8 | INFO | **The 8d98bf4c message names the wrong INTEG1 SHA.** It says "INTEG1 db463142 merged (6316d5c4)", but 6316d5c4's second parent is 7c42e706. That is a descendant of db463142 and is the current INTEG1 tip. | `git show -s --format=%P 6316d5c4` |

## W-1 verification (real SQLite file, WAL, engine from `core.db`)

- **The lock is on the right connection.** `_lock(s, db)` runs `BEGIN IMMEDIATE` on the write
  session `s`, the same connection that later flushes the approval, and before the
  `with_for_update` read and `_checks`. Python 3.11 pysqlite in legacy transaction mode emits no
  implicit BEGIN before a non-DML statement, so the explicit BEGIN IMMEDIATE takes effect. `_checks`
  reads through other connections; WAL readers are not blocked, and those reads see committed
  state while no writer can commit.
- **`race_move` (real code):** the writer starts mid-checks, waits, and finishes after the review
  (`order=['review_done','writer_done']`). The review approved the frame at position 1, which was
  the committed state while it held the lock. The writer's move and re-mark land after it and are
  not overwritten. The residual is A3D-2.
- **`race_move --nolock` (lock mutant):** the writer finishes inside the window, and the review
  approves the moved frame (`pos 999, approved True, []`) and erases the re-mark. This reproduces
  OPUS2W-1 with the lock removed, so the probe is sensitive.
- **`race_upgrade` (the real `plan_upgrade` of a second attested photo as the writer):** the
  writer waits. The final state is consistent: the new photo leads, AWAITING; the reviewed frame
  is approved, at position 2, demoted.
- **`race_delete`:** the review approves while the frame exists, then the writer deletes it. With
  the lock removed, the review crashes with `StaleDataError`.
- **`gone` (frame deleted before the review):** `approved=False failed=['frame_gone']`, and the
  audit row records `approved: False`.

## W-2 abuse checks

| Case | Result |
|---|---|
| The leading photo stops qualifying before review (attestation removed) | Terminal reason; `_frames` positions become [2, 3, 4]; `listing_set` blocks; `requirement` is not satisfied; `for_publish(stage=activation)` blocks with SAMPLE_PHOTO_REQUIRED. Fails closed. |
| The only frame is a photo that does not qualify | `_frames` is `[]`; `listing_set` blocks with "no listing frames are on file", and no certificate is issued. Fails closed. |
| A photo-led set with zero qualifying photos | `requirement` reasons "no unedited photograph ..." and the activation gate refuses. Fails closed. |
| Any check UNKNOWN (an exception) | Stays AWAITING, not terminal. Correct, but untested (K7, A3D-4). |
| Re-open after the bytes are restored (leader) | Re-opened and approved. Correct. |
| Re-open after a later attestation | Works, through `lead_with_if_qualifying` (the test case). |
| Re-open after the photo qualifies by another route | **Stuck** (A3D-1). |
| Other `_frames` callers (`listing_set`, `_frame_bytes`, `_recheck_listing_certificates`) | Only rows carrying the new prefix are dropped, and only `review_frame` writes that prefix, on PHYSICAL_PRODUCT_PHOTO frames. Existing callers behave the same when no frame carries it. test_cert_publish_gates and test_opus2_photo_led_gallery pass. |

## W-3 to W-6

- **W-3:** N6, N7 and N9 are now killed (K13, K14, K15).
- **W-4:** the leader-class check is killed (K10).
- **W-5:** `frame_gone` is killed (K11), and the probe confirms the audit is truthful.
- **W-6:** the launchfix guard now refuses any `sample_photo\s+as\b` and counts mentions in code
  only, using tokenize and ast. G3, G4, G6 (parenthesised multi-line alias) and G8 (`vars(...)`)
  are killed. G7 (`__import__` with a computed name) survives, the same class as OPUS2W G5, which
  is beyond a static guard.
- **The launchfix guard is not weakened.** The `reached`, `getattr(sample_photo`, `from ... import`
  and `requirement(`/`stage=` assertions are unchanged. The old raw-text count (docstring mentions
  included) is replaced by a stricter count over code only. The only relaxations are that a bare
  attribute access is counted without needing `(`, and more than one plain import is allowed. The
  attribute set must still be exactly {qualifying_photos, _synthetic_shas}.

## Test diff (d1f65b61..8d98bf4c)

No assertion was weakened without a matching decision.

- **`test_every_check_fails_closed`:** "AWAITING in reasons" is now conditional. The
  qualifying-check failures must carry the terminal reason (I-A3-NONQUALIFYING-PHOTO), and the
  others must still be AWAITING. The assertion is equally strict under the new decision.
- **S-1 test:** `"not awaiting" in changed` becomes `failed == ["not awaiting asset-truth review"]`,
  which is equivalent.
- **The S-2 snapshot test was deleted along with the snapshot code it tested.** It is replaced by a
  real thread race (it covers position and blocked_reasons; the sha256 and claims variants are no
  longer exercised, which is equivalent under the lock). Three new tests were added: W-1, W-2 and
  W-3/4/5.

## Prior findings status

| ID | Status at 8d98bf4c |
|---|---|
| OPUS2W-1 (MED, SQLite race) | **Fixed on SQLite** (`race_move`; the lock mutant K1 and the deferred-BEGIN mutant K2 are killed). Postgres UNKNOWN (A3D-6). Residual is A3D-2 (LOW). |
| OPUS2W-2 (MED, stays awaiting forever) | **Fixed for the stated case** (excluded, never holds the set hostage). The related case OPUS2W-2 marked UNKNOWN is now **reproduced as A3D-1 (MED)**. |
| OPUS2W-3 (LOW, supplement rule unpinned) | Fixed: N6, N7 and N9 are killed. P2 (`_demote_leaders` in `lead_with_if_qualifying`) was not re-run (that code is unchanged in this delta): UNKNOWN. |
| OPUS2W-4 (LOW, leader class) | Fixed (K10 killed). |
| OPUS2W-5 (LOW, frame_gone reported approved) | Fixed (K11 killed, probe `gone`). |
| OPUS2W-6 (LOW, guard alias) | Fixed (G4, G6 killed); G7 is out of reach of a static guard. |
| OPUS2W-7 (INFO, not rebased) | Fixed: the branch contains the INTEG1 tip 7c42e706. |
| OPUS2W-9 / OPUS2S-6 (unlocked certificate check-then-insert) | Unchanged in this delta (not re-reviewed). |
| OPUS2S-1 | Still holds (S-1 test, K8 killed). |
| OPUS2S-2 | Superseded by the W-1 lock (see above). |
| OPUS2S-3 | Two-photo case still passes (S-3 test). Supplement rule tightened (W-4). |
| OPUS2S-4 | Mutants still killed (K16 class guard, plus the suite). |
| OPUS2S-5 | Strengthened (W-6). |

## Mutants (scratch worktree a3d-mut, restored after each; `git status` clean afterwards)

| Mutant | Suite | Result |
|---|---|---|
| K1 remove `_lock` | photo_asset_review | KILLED ("the writer committed inside the review's window") |
| K2 `BEGIN` (deferred) instead of `BEGIN IMMEDIATE` | photo_asset_review | KILLED |
| K3 `_frames` keeps non-qualifying frames | photo_asset_review | KILLED |
| K4 re-open without the qualifying check | photo_asset_review | KILLED |
| K5 never terminal | photo_asset_review | KILLED |
| K6 terminal on any failure | photo_asset_review | KILLED |
| K7 UNKNOWN may be terminal | photo_asset_review | **SURVIVED** (A3D-4) |
| K8 `_reviewable` always True | photo_asset_review | KILLED |
| K9 `_reviewable` AWAITING only | photo_asset_review | **SURVIVED** (A3D-4) |
| K10 a render may lead a supplement (W-4) | photo_asset_review | KILLED |
| K11 frame_gone reported approved | photo_asset_review | KILLED |
| K12 re-approval keeps the NOT_QUALIFYING reason | photo_asset_review | **SURVIVED** (A3D-4) |
| K13 N6 `>=1` leaders | photo_asset_review | KILLED |
| K14 N7 leader anywhere | photo_asset_review | KILLED |
| K15 N9 no contiguous check | photo_asset_review | KILLED |
| K16 asset_class guard removed (non-photo reviewed as photo) | photo_asset_review | KILLED |
| G3 `sp = sample_photo` | w4_launchfix | KILLED |
| G4 `from . import release_gates, sample_photo as sp` + getattr | w4_launchfix | KILLED |
| G6 parenthesised multi-line alias | w4_launchfix | KILLED |
| G7 `__import__(computed name).requirement` | w4_launchfix | survived (beyond a static guard) |
| G8 `vars(sample_photo)['requirement']` | w4_launchfix | KILLED |

## Suites (venv-integ4, worktree at 8d98bf4c)

| Suite | Result |
|---|---|
| test_opus2_photo_asset_review | exit 0, 0 failed (25 s) |
| test_w4_launchfix | exit 0, 32 passed (86 s) |
| test_physfix_photo_first | exit 0, 8/8 |
| test_cert_publish_gates | exit 0, 0 failed (96 s) |
| test_swarm_runtime | exit 0 |
| test_eligibility | exit 0 |
| test_mobile | exit 0 |
| test_opus2_photo_led_gallery | exit 0, 0 failed (633 s) |
| test_physfix | exit 0, 48/48 (740 s) |

The first mutant batch overlapped the tail of test_physfix for a few minutes; both passed or
behaved as expected. That batch was stopped by its 600 s background limit after K11. K12 to K16
and the guard mutants were re-run separately.

## Merge (6316d5c4) and merge readiness

- **The conflict resolution is correct.** `git show --remerge-diff 6316d5c4` lists 5 conflicted
  files. Diffed against the INTEG1 parent 7c42e706, the result is INTEG1 plus the branch's
  additions only:
  - COORDINATION.json equals INTEG1's plus the OPUS2-PHOTO-ASSET-REVIEW claim. The OPUS2M
    verdict, the 04:30Z observation and the OPUS2N in-flight entry were absent from INTEG1 and
    are absent from the result too, which follows the integrator. The file is valid JSON.
  - `pipeline.py` and `orchestrate.py` keep both sides.
  - `autonomy_map.json` was regenerated (cadences 138, handlers 170, follow_on_edges 84).
  - `test_w4_launchfix.py` keeps both sides.
  - `registry.py`, `classes.py` and `OPUS2_INTEGRATION_QUEUE.md` carry the branch's own hunks
    unchanged; INTEG1 did not touch the queue file.
- **Merge readiness:** `git merge-tree --write-tree origin/claude/w5-INTEG1 8d98bf4c` exits 0 with
  tree 67230ecf: **0 conflicts**. INTEG1 (7c42e706) is an ancestor of 8d98bf4c, so the merge is
  a fast-forward.

## Artefacts

- **Probes:** /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a3d-probe/a3d_probe.py
  (race_move, race_upgrade, race_delete, gone, long_writer, lapses, only_photo, churn, unknown,
  q_later, bytes_lapse; `--nolock` gives the lock mutant).
- **Mutation runner:** /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a3d-probe/a3d_mut.py
- **Logs:** /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a3d-probe/logs/
- **Worktrees:** a3d and a3d-mut were removed after the review.
