# Independent review: U5 A3 photo/gallery gap recovery, `codex/a3-gallery-gap-recovery` @ 84085fa8

- **Target:** `claude/w6-INTEG1` @ 5913931f.
- **Merge-base:** 7c42e706.
- **Subsumes:** opus2 `p0-photo-asset-review` c2174947 (#23), `codex/a3-photo-recovery` 0ace3808 (#37) and `codex/a3-fencing-followup` c888769b.
- **Size:** 22 files, +2072/-20.
- **Reviewed:** 2026-11-07 UTC, in a trial merge in a throwaway worktree. The worktrees, the local PostgreSQL cluster and the mutant copies have been removed.

## Verdict: **DO NOT SHIP**

The core review is sound. It makes no model call and no paid call. It changes no thresholds and leaves SHADOW and Etsy alone, and every UNKNOWN is a refusal. Fifteen of the 18 mutants on its guards are killed or covered. Three things block it:

1. **The merge turns the suite red.** `test_w4_launchfix` has 2 FAILs on the merge and on the head alone. The same test passes 32/32 on w6-INTEG1.
2. **Direct writers bypass the fence, as #126 says. This is now reproduced.** Three cases:
   - Rebuild path (fix-only and targeted rebuilds): `assets.build` overwrites an approved photo frame.
   - Recheck path: `release_gates.recheck` strands a photo-led gallery for good.
   - PostgreSQL: unlocked evidence sources commit while the review lock is held.
3. **The branch says not to integrate it.** Its own handoffs say "DO NOT INTEGRATE until issuance and evidence writers share an independently reviewed fence" and "Do not integrate until those independent blockers close". Nothing in this review closes those blockers.

Every failure I found fails closed: no frame becomes publishable and no certified frame list is returned. The problems are liveness, evidence loss, DB state that misleads readers who bypass the fence, and a red suite. I found no fail-open in the gallery or photo gates themselves. One fail-open-on-exception guard in the consumer has no test (F6).

## Findings

### MED

**F1 (MED, regression, test suite red): `test_w4_launchfix` fails 2 of 32.**
- The failing tests are `test_img_refuses_unbound_other_release_edited_or_not_first_photos` and `test_img_a_bound_unedited_first_sample_photo_passes_this_gate_only`.
- Base w6-INTEG1 passes 32/32, the head alone fails 2, and the trial merge fails 2.
- **Cause:** the `_photo_fixture` helper (`tests/test_w4_launchfix.py:565`) writes a `ListingSetCertificateRecord` directly, with no `ListingAsset` photo row. The new consumer fence (`etsy_ops.certified_frames`, `runtime/etsy_ops.py:550-586` → `photo_certificate_current`) now refuses it with "photo frame or evidence no longer matches the certificate".
- The refusal is the intended behaviour, but the branch edited this test file without fixing the fixture. The codex handoff admits "the full launchfix regression was interrupted ... not a pass".
- **Fix:** have the fixture create the photo `ListingAsset` through intake, attest, `plan_upgrade` and `review_frame`, or seed an approved photo row that passes `_checks`. Do not relax the fence.

**F2 (MED, direct writer bypasses the fence, reproduced): `assets.build` → `_persist_frames` overwrites an approved, certified photo frame.**
- **Where:** `runtime/release.py:2789-2818`.
- The writer upserts by position. It takes no `_lock`, does not invalidate the certificate, and does not check `asset_class`.
- **Probe:** sweep approves the photo leader, then a valid photo-led certificate is issued, then `_persist_frames` runs with 3 rebuilt renders.
- **Result:**
  - Row id 4 changes from `PHYSICAL_PRODUCT_PHOTO` at position 1 to `RENDER`. It stays approved=True and its `physical_photo_id` is gone.
  - The certificate record stays `state='valid'`.
  - `certified_frames` refuses (fails closed).
  - The sweep reports `reviewed: 0`, so nobody is told.
- The `PhysicalPhoto` keeps `state='upgrade_queued'`, so `plan_upgrade` answers "already upgraded" and the photo can never be put back without manual DB work.
- **Reachability:** every targeted rebuild, and the W6 FIX-ONLY rebuild already on w6-INTEG1 (`handle_assets_build` runs `_persist_frames` unconditionally at `release.py:577`).
- The writer is older than A3. A3 is what creates approved photo rows that this writer now silently destroys.
- **Fix:**
  - `_persist_frames` skips or refuses rows whose `asset_class == PHYSICAL_PRODUCT_PHOTO`, and renders take positions after the photo frames.
  - Or it takes `photo_asset_review._lock` and calls `_invalidate_photo_certificates` in the same transaction.

**F3 (MED, liveness, reproduced): `release_gates.recheck` permanently strands a photo-led gallery.**
- **Where:** `publish/release_gates.py:1131-1172`.
- On a routine `POLICY_VERSION` bump (or a claims change), `recheck` sets approved=False on every certified frame and prepends `LISTING_SET_INVALIDATED: ...`. It takes no photo lock.
- That reason is neither `AWAITING` nor `NOT_QUALIFYING`, so `_reviewable()` is False, and `_reopen_stale_approved_photos` only scans approved frames. Nothing in `src` ever clears `LISTING_SET_INVALIDATED`.
- **Probe:** approved leader, then certificate, then recheck with a new policy version. Two sweeps afterwards both return `reviewed: 0`. The frame stays `[LISTING_SET_INVALIDATED ...]`, and re-certification is refused: "photo frame or evidence changed before certificate review".
- Render frames recover through a rebuild. Photo frames do not; worse, a rebuild destroys them (F2).
- **Fix:** have `recheck` re-mark photo frames `[AWAITING] + others` under `_lock`, or have `_reviewable` and `awaiting_frames` treat `LISTING_SET_INVALIDATED` on a photo frame as reviewable. Add a test for it.

**F4 (MED, the #126 gap confirmed on real PostgreSQL 16): phantom inserts and unlocked evidence writers cross the held fence.**
- **Setup:** I held `_lock` + `photo_snapshot_current` (True) in one session and ran writers with `lock_timeout = 250ms` in another.
- **All three of these committed while the lock was held:**
  - `PatternVersion.certified=False` (UPDATE on an evidence source `qualifying_photos` reads but `_lock_photo_sources` does not lock).
  - An INSERT of `ArtefactProvenance(sha256=<photo>, provider, model)`, which disqualifies the photo as generated.
  - An INSERT of a sibling `ListingAsset` with `leads_gallery: True`.
- After commit, a fresh `photo_snapshot_current` returns False. So the issuing transaction can record a certificate from a stale snapshot, and the consumer re-check (`certified_frames`) has the same window, followed by the unfenced interval after its read.
- **Also outside the fence:**
  - `plan_upgrade` (`physical_upgrade.py:134-200`): renumbers and demotes frames without `_lock` or certificate invalidation.
  - `gallery_persist.py:135` (inserts).
  - `_persist_frames` (F2) and `recheck` (F3).
- The PG test in the branch, `test_a3_postgres_photo_fence.py`, covers only UPDATEs to `PhysicalPhoto` and `PhysicalTest`. It passes.
- **Mitigation today:** SHADOW mode with no Etsy publishing, plus the consumer re-check.
- **Fix:** every writer of `ListingAsset` for a release, `PhysicalPhoto`, `PhysicalTest`, `PatternVersion.certified`/`cir_json`, `ArtefactProvenance` and disclosed sets takes the photo advisory lock (or a per-release lock key), or issuance moves to SERIALIZABLE. Add one PG test for each source.

**F5 (MED, test gap on a load-bearing guard): removing certificate invalidation entirely survives (M9).**
- `_invalidate_photo_certificates` (`photo_asset_review.py:140-155`) can become a no-op and every A3 test still passes. `test_revoked_supplement_invalidates_certificate_even_if_reissue_fails` claims it "cannot leave the old certificate valid", but it asserts only that `certified_frames` refuses, and the consumer fence refuses regardless.
- **Why it matters:** these readers trust `ListingSetCertificateRecord.state == "valid"` without the photo fence:
  - `brand/storefront_preview.py:261`, `_certified_hero` (would preview a revoked photo as the hero);
  - `growth/ads_readiness.py:468`;
  - `gates/first_customer.py:544`;
  - `store_foundation/image_review.py:216`;
  - `commerce/search_evidence.py:111`.
- **Fix:** assert `state == "invalidated"` in that test and in the sweep and recheck paths, or route those readers through `certified_frames`.

### LOW

**F6 (LOW, fail-open guard with no test): M14 survives.**
- In `etsy_ops.certified_frames` (`runtime/etsy_ops.py:576-582`), `except Exception: current = False` can be flipped to `True` and every test still passes. No test injects an exception there.
- **Fix:** add one test that patches `photo_certificate_current` to raise.

**F7 (LOW, tests that never run as a script): `tests/test_codex_a3_excluded_gap.py` has no `if __name__ == "__main__":` block and no `_tmp.install()` of its own.**
- Run as a plain script, as the repository conventions say, it executes 0 tests and exits 0. That reads as a false PASS.
- With a runner, all 3 tests pass.
- No A3 test imports pytest.

**F8 (LOW): the `NOT_QUALIFYING` exclusion in `release_gates._frames` covers every asset class.**
- **Where:** `publish/release_gates.py:210-226`. Any frame whose reason starts with "photo not qualifying: " drops out of the listing set instead of blocking it.
- `photo_snapshot_current` and `photo_certificate_current` restrict the same filter to `PHOTO_CLASS`.
- **Fix:** restrict this filter to `PHOTO_CLASS` as well.

**F9 (LOW, liveness): the sweep loop has no exception guard around `review_frame`.**
- **Where:** `photo_asset_review.py:523`. `review_frame` catches only `OperationalError`, so any other exception (for example an `IntegrityError` from `_renumber` inside `_park_excluded_supplements`) aborts the whole sweep for every release. It fails closed.
- On PostgreSQL, a NOWAIT `LockNotAvailable` in `_park_excluded_supplements` rolls back the whole review transaction, including the terminal hold. The frame stays `AWAITING`, which is fail-closed, and is retried next sweep.

**F10 (LOW, inherited from base, not A3): the committed `autonomy_map.json` is stale on w6-INTEG1.**
- On base, `test_v11_autonomy_timeline` and `test_w4_c12_wiring` fail: the map records 83 follow-on edges against 85 live (the 2 support-defect edges).
- The merge inherits this (84 against 86).
- Regenerating the map with the command in step 3 of the recipe fixed `test_w4_c12_wiring` on the merge: rc=0. I did not re-run `test_v11_autonomy_timeline` after regenerating.

**F11 (LOW, effectively equivalent mutants): M4, M13 and M15 survive.**
- M4: other paths already cover it. The identity tuple includes approved and blocked_reasons, and the per-frame gates read `AWAITING` as a failure.
- M13: `listing_set` refuses duplicate positions anyway.
- M15: `lead_with_if_qualifying` keeps independent holds (M16 is killed), so the only behavioural change is a reorder.
- No action needed. They are listed for completeness.

### Checked and clean

- **Paid generation and V0:** no gateway, provider, image-generation, spend or threshold code anywhere in the diff. The photo review is CA$0 and deterministic.
- `test_w5_v0_paid_provider_gate` passes 52/52 on the merge.
- **Thresholds:** none changed. The only numeric change is the autonomy map's `generated_at`.
- **Laura assets:** no diff touches laura-r2-a42aeac7. No images were added.
- **SHADOW and Etsy:** untouched.
- **Support-defect withholding:** independent of A3. It lives on the `PatternVersion` certificate and is enforced at publication, and `photo_asset_review` never touches `PatternVersion`. `test_w6_support_defect_incident` passes.
- **Fix-only rebuild:** its listing and launch guards work on the merge (`test_w6_fix_only_rebuild` passes 0 failures). Its `assets.build` stage is a fence bypass (F2).
- **Authority:** `assets.photo_review` is class `_T` (test), GREEN, under the asset_truth agent. Its band is `proven_winner`, and `test_swarm_runtime` passes.
- **launchfix allowlist:** the `sample_photo` user list was extended by one guarded entry, `photo_asset_review`, which may call only `qualifying_photos` and `_synthetic_shas`. That is acceptable.

## Prior-finding status

| Finding | Source | Status on 84085fa8 |
|---|---|---|
| A3D-1 (MED liveness: a photo that qualifies later is never promoted, stale reason) | c2174947 | **Fixed.** `test_review_a3d1_*` pass. The `NOT_QUALIFYING` exclusion is pinned by M12, which is killed. |
| A3D-2 (`lead_with` takes the review lock) | 637e011f | **Fixed.** M17 killed. |
| A3D-3 (re-open only for the frame's own bytes) | c2174947 | **Fixed.** M18 killed. |
| A3D-4 (tests for the re-open branch) | c2174947 | **Fixed.** M11 killed (K7). |
| A3D-5 (a lock not taken is a per-frame UNKNOWN) | c2174947 | **Fixed.** Test passes. |
| OPUS2W-1..6, OPUS2S-1..5 | 8d98bf4c, d1f65b61 | Their tests pass. M10 and M16 killed. |
| A3F (an excluded first photo blocks forever; position-one churn) | codex #37 | **Fixed.** `test_excluded_photo_leader_*` and `test_position_one_*` pass. M6, M7 and M8 killed. |
| A3F-3 (race with unlocked writers) | codex handoff | **Open.** Reproduced as F2, F3 and F4. |
| #126 / integration map "does not cover phantom/direct writers" | INTEGRATION_MAP_20261107 U5 | **Confirmed open.** F4 on PG; F2 and F3 on SQLite. |
| Codex handoff: "full launchfix regression ... not a pass" | 0ace3808/c888769b | **Confirmed failing.** F1. |
| OPUS2 queue Q15 "DO NOT SHIP, blocked on A3D-1" | OPUS2_INTEGRATION_QUEUE | A3D-1 is resolved; the new blockers are F1-F5. |

## Conflict recipe (trial merge of 84085fa8 into w6-INTEG1 5913931f)

1. Run `git merge --no-ff 84085fa8`. The only conflict is **`COORDINATION.json`**:
   - HEAD adds `CODEX-A7-FRESHNESS-FIX`.
   - The branch adds `OPUS2-PHOTO-ASSET-REVIEW`, `CODEX-A3-PHOTO-RECOVERY` and `CODEX-A3-EXCLUDED-GALLERY-GAP`.
2. Resolve `COORDINATION.json` as a union: keep the HEAD object, close it with `},{`, then the three branch objects. Check it with `python3 -c "import json;json.load(open('COORDINATION.json'))"`.
3. `release_gates.py` merges cleanly, because w6-INTEG1 has not changed it since the merge-base.
   - The integration order with A6 and A9 still matters. Whichever unit lands second must keep the four `_lock(s, db)` + `photo_*_current` guards at the review and issuance blocks of `_record_certificate` (~1055 and ~1083) and `certificate_step` (~1187 and ~1238), and the `_frames` filter at ~221.
   - `registry.py`, `pipeline.py`, `release.py`, `worker.py`, `etsy_ops.py`, `autonomy_map.json`, `authority/classes.py` and `orchestrate.py` all auto-merge.
   - Regenerate the autonomy map: `cd brambleloop && PYTHONPATH=src python -m brambleloop.autonomy.map --write src/brambleloop/autonomy/autonomy_map.json`. This gives 86 edges and adds `support/defects.py:escalate`, which fixes the inherited F10.
4. Before shipping, fix F1 (the fixture), and at minimum F2 and F3 (photo-aware `_persist_frames` and `recheck`). Add an `if __name__ == "__main__":` block to `test_codex_a3_excluded_gap.py` (F7), and a cert-state assertion and an exception-injection test (F5, F6). F4 needs the shared-fence design the branch's own DNI note asks for.

## Test table (trial merge; venv-integ4; plain scripts; PYTHONPATH=src:tests)

These are the results of the second, clean run in a dedicated directory. The first run's logs were in a shared scratchpad.

| Test | Result |
|---|---|
| test_opus2_photo_asset_review | PASS, 29/29 |
| test_codex_a3_disclosed_race | PASS, 2/2 |
| test_codex_a3_excluded_gap | Plain script: **0 tests run** (F7). With a runner: PASS 3/3 |
| test_a3_postgres_photo_fence (real PG 16, disposable local cluster) | PASS |
| test_w4_launchfix | **FAIL**, 30 passed, 2 failed (base w6-INTEG1: 32/32) |
| test_w5_v0_paid_provider_gate | PASS, 52/52 |
| test_w6_fix_only_rebuild | PASS, 0 failures |
| test_w6_support_defect_incident | PASS, 0 failures |
| test_opus2_photo_led_gallery | PASS |
| test_physfix_photo_first | PASS, 8/8 |
| test_cert_publish_gates | PASS |
| test_physfix* | PASS, 48/48 (first run only) |
| test_secreview_physfix_adversarial* | PASS, 12/12 (first run only) |
| test_w4_visual_gallery_frames* | PASS, 10/10 (first run only) |
| test_w4_visual_certified_gallery* | PASS, 7/7 (first run only) |
| test_w4_f454_agents* | PASS (first run only) |
| test_swarm_runtime* | PASS (first run only) |
| test_w4_c12_wiring / test_v11_autonomy_timeline | FAIL, inherited from base (F10). c12_wiring passes after regenerating the map; timeline not re-run after regenerating |

\* These ran in the same trial worktree but only in the first run. The A6 reviewer's interference that was reported to me affected mutant directories and the jsonl results file, not worktree test runs. I count these results but did not repeat them.

Probes I wrote, beyond the test suite (scratchpad `probe_recheck.py`, `probe_persist.py`, `probe_pg_phantom.py`):

| Probe | Result |
|---|---|
| F3: `recheck` strands a photo-led gallery | Reproduced |
| F2: `_persist_frames` overwrites the photo frame | Reproduced |
| F4: three writers cross the PG fence | Reproduced |

## Mutant table (clean rerun only)

All mutants were rerun in isolated copies (`/home/user/bl-runs/mut-rvA3U5/m{i}`, recreated from the trial merge for every mutant). Results are in `scratchpad/rvA3U5/verify.out` and `verify2.out`.

Kill set: test_opus2_photo_asset_review, test_codex_a3_disclosed_race and excluded_gap (with a runner). M5 was also run against the PG fence test.

The A6 reviewer reported that its process ran my first-run script and recreated `mut-a3/m0..m5`. Those first-run results are discarded. They differed from the clean run: M5 appeared killed by the gap tests, which was interference.

| # | Mutant (file) | Result | Killed by |
|---|---|---|---|
| M1 | consumer refusal off (etsy_ops.certified_frames) | KILLED | disclosed_race |
| M2 | `_record_certificate` photo recheck off (release_gates ×2) | KILLED | disclosed_race |
| M3 | `certificate_step` photo snapshot off (release_gates ×2) | KILLED | opus2: revocation_during_certificate_issue |
| M4 | `photo_snapshot_current` ignores approval/holds | SURVIVED | effectively equivalent (F11) |
| M5 | `_lock_photo_sources` no-op | SURVIVED on SQLite; **KILLED on PG** | test_a3_postgres_photo_fence ("PhysicalPhoto writer crossed the held lock") |
| M6 | park ignores leader approval/holds | KILLED | gap: owner_held_leader |
| M7 | park ignores prior contiguity | KILLED | gap: preexisting_malformed_order |
| M8 | no stale-approved recheck | KILLED | opus2 ×3, gap |
| M9 | certificate invalidation no-op | **SURVIVED** | F5 |
| M10 | withdrawn guard off (`lead_with_if_qualifying`) | KILLED | opus2: withdrawn_photo |
| M11 | UNKNOWN may become terminal | KILLED | opus2: a3d4_k7, unreadable_photo_evidence |
| M12 | listing set keeps `NOT_QUALIFYING` | KILLED | opus2 ×3 |
| M13 | duplicate photo keys accepted | SURVIVED | effectively equivalent (F11) |
| M14 | consumer exception → current=True | **SURVIVED** | F6, fail-open guard with no test |
| M15 | recovery accepts held candidates | SURVIVED | mitigated downstream (F11) |
| M16 | promotion drops independent holds | KILLED | opus2: never_clears_owner_hold |
| M17 | `lead_with` takes no review lock | KILLED | opus2: a3d2 |
| M18 | reopen ignores own-bytes hash | KILLED | opus2: a3d3 |

**Totals:** 13 killed (one only on PG), 5 survived. Of the 5, 2 are real test gaps (M9, M14) and 3 are effectively equivalent (M4, M13, M15).

## Cleanup

- The worktrees `wt-rv-a3`, `wt-rv-a3-base` and `wt-rv-a3-head` were removed with `git worktree remove --force` and pruned.
- The local PG cluster was stopped and deleted.
- `mut-a3` and `mut-rvA3U5` were deleted.
- The main checkout was not touched. I made no commits and no pushes, used no network to paid providers and printed no secrets.
