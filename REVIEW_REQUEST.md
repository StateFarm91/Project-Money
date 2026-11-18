# REVIEW_REQUEST — `eng/a3-photo-fix` (base 3928ba00, opus2/a3-photo-asset-review)

Owner requirement: a genuine owner-attested sample photo must be able to become the certified
gallery leader of a PUBLISHED listing and keep its authority across rebuilds.

Each finding has a regression test that fails on 3928ba00 and passes here (verified by
swapping the old source file back in and re-running the test).

## N1 (MEDIUM) — PG photo-fence suite reported only SKIP

- **Finding:** without `A3_TEST_POSTGRES_URL`, `tests/test_a3_postgres_photo_fence.py` printed
  SKIP and exited 0, which `run_tests.sh` counts as SUITE REPORTED NO PASSES = failing.
- **Fix:** the W6 `_disposable_cluster` pattern from `test_codex_v0_postgres.py`: with no URL
  and a local PG toolchain, a fresh loopback cluster with an empty `codex_photo_test` DB is
  made for the run and destroyed after. A supplied URL is used as is. SKIP only when no
  toolchain exists. Standard sys.path header added too.
- **Test:** the suite itself under `run_tests.sh` with no env var: before = SKIP / no passes,
  now = 3 OK (PostgreSQL 16).

## L1 (LOW) — photo positions read before the lock

- **Finding:** `runtime/release._persist_frames` read photo positions before taking the photo
  review lock; a `plan_upgrade`/`lead_with_if_qualifying` shift committed in between made the
  build aim its hero render at a slot a photograph had moved into ("not placed", dropped).
- **Fix:** the lock is taken first and positions are read inside the write transaction. It is
  taken for every gallery (a photo can arrive between any read and the write); it is the same
  lock every photo-frame writer takes.
- **Test:** `test_w6_fix_only_rebuild::test_l1_photo_positions_are_read_under_the_lock_so_a_concurrent_shift_drops_no_render`
  injects a committed reorder (second photo to slot 1, everything shifted) at the build's
  lock call. Old: hero render placed at 2 onto the moved photo → not placed. New: renders at
  3..N+2, no `listing.frame_photo_kept`.

## L2 (LOW, important for the physical-sample plan) — #61 blocked every photo-led listing

- **Finding:** `frame_review_state` compared the #61 review's builder-position hashes with the
  stored position map, which never matches after `plan_upgrade` puts the photo first, so
  pipeline publish check #61 refused every photo-led listing and
  `publication_authority` parity read the frame review as not reviewed.
- **Fix:** for a gallery holding a `PHYSICAL_PRODUCT_PHOTO`, `frame_review_state` binds the
  reviewed bytes to the stored **non-photo** frames in order (bytes + relative order, so a
  changed render still fails), and clears each photo only by its own deterministic
  asset-truth approval (`photo_asset_review`). A photo still awaiting review holds #61 by
  name; a NOT-QUALIFYING photo (excluded from the uploaded set) is not counted. Galleries
  without a photo are unchanged.
- **Test:** `test_cert_listing_frames::test_l2_a_photo_led_listing_passes_the_61_publish_check_and_keeps_it_across_a_rebuild`
  — the basket release through real `assets.build` (vision stubbed clear, no provider), a
  passed full make, intake + owner attestation, `plan_upgrade`, the photo review sweep,
  `pipeline._listing_parity` (the publish path's #61 check), `publication_authority._parity`,
  then a rebuild; finally a changed render byte fails. Old: fails at the first post-upgrade
  read with "the stored frame bytes differ from the ones reviewed".
- Not claimed: that the whole publication authority reads PASS for this fixture — only that
  the #61 frame-review component no longer blocks a photo-led listing.

## L3 (LOW) — pre-shift certificate invalidation by old positions

- **Finding:** `release_gates.recheck` resolved an invalidated certificate's frames by recorded
  positions; after the shift, slot 1 is the (just approved) photo → back to awaiting, and the
  render shifted past the old range kept its approval under a revoked certificate.
- **Fix:** frames are resolved by their certified sha256 (preferring the recorded slot);
  a legacy record with no hash falls back to the slot. Marking logic moved unchanged into
  `_mark_invalidated`.
- **Test:** `test_opus2_photo_asset_review::test_l3_a_pre_shift_certificate_is_revoked_by_its_bytes_not_its_old_slots`.
  Old: photo goes back to awaiting. New: photo stays approved, all three renders (at 2..4)
  carry LISTING_SET_INVALIDATED.

## L4 (LOW) — a render overwrote an AI_LIFESTYLE_CONCEPT slot

- **Fix:** concept positions are reserved like photo positions when mapping renders, and a
  render never replaces a concept row (recorded "not placed" if it would).
- **Test:** `test_w6_fix_only_rebuild::test_l4_a_render_never_overwrites_a_generated_concept_slot`
  (concept at 3 between shifted renders). Old: concept overwritten. New: concept intact,
  renders at 2,4..N+2.

## Suites run

(run in progress — counts added in the next commit)

## PostgreSQL

PostgreSQL 16 installed in this container; `test_a3_postgres_photo_fence` ran on a disposable
cluster: 3 OK.

## Merge note (not merged)

`git merge-tree` vs `origin/claude/w6-INTEG1`: mechanical conflict in
`brambleloop/scripts/suite_final_segment.txt` (both sides append lines: keep all) and also in
`brambleloop/src/brambleloop/autonomy/autonomy_map.json` (generated file, `generated_at`
differs: regenerate). Both already conflict at base 3928ba00; this branch touches neither.
`release.py`, `pipeline.py` auto-merge. INTEG1 was not merged into this branch.

## Final SHA

(added in the next commit)
