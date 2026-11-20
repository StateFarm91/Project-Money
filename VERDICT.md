VERDICT: DO NOT SHIP ac1239f899749cb0175151b5a1e1454b90048fc7

Unit origin/eng/catalogue @ ac1239f8, delta over cafd6917, merged onto origin/claude/w6-INTEG3 @ 39b92619.

## Blocking findings
1. **Merge is not clean (3 conflicts).** `sw.js` (VERSION line/comments), `products/production_inventory.py`
   (`load_records` return dict: base adds `construction_holds*`, unit adds the shared snapshot block after it) and
   `scripts/suite_final_segment.txt`. I resolved them mechanically keeping both sides (sw.js v36, both dict keys, both
   helper blocks, both suite lists). The unit must be rebased by its author; my resolution is not what ships.
2. **test_v11_pwa_static fails on the merged tree**: `structure: static bundle under 400 KB: 400556` (limit 400_000).
   Base static bundle = 386,737 B; unit alone = 398,186 B; combined = 400,556 B. Each side passes alone, the integration
   breaks the budget. Needs a trim (or an owner-decided budget change) before merge.

## Prior findings
- **H1 FIXED.** `catalogue.py:174` now compares to `listing_state.PUBLISHED`; test_w4_adopt_manual_listing passes (19).
  Mutation (`PUBLISHED` -> `"publishedX"`): test_w4_adopt_manual_listing still passes (it does not catch this);
  test_eng_catalogue_fix1 FAILS (killed). So H1 is covered, but by fix1, not by w4_adopt.
- **M1 FIXED, thin margin.** Cold uncached `catalogue.view`, 600 products / 70k jobs / 150k audits: 0.97 s on the merged tree
  (was 2.92 s). Test asserts `< BOUND_SECONDS = 1.0` (the file's comment says ~0.85 s measured). Mutation (reintroduce a
  per-call scan of all jobs in `_jobs_for`): 2.79 s, test FAILS (killed). 0.97 vs 1.0 is within noise on a slower
  runner, so expect flakiness.
- **M2 FIXED.** `test_500_concurrent_cold_readers_single_flight_one_load_no_errors`: 500 readers, all OK, no errors,
  `load_records` x1 (1.98 s). Mutation (remove the post-lock re-check in catalogue `_index` plus the snapshot TTL check):
  test hung until my 400 s timeout (killed, as a hang rather than an assertion). Removing only the snapshot-layer check
  is NOT caught (the catalogue-layer single-flight alone suffices), so that layer is redundant for this test.
- Correctness (distinct counts, nothing cached across owners): test_eng_catalogue, _agents, _fix1 all pass. I did not
  write extra cross-owner probes beyond what those suites assert.
- sw.js VERSION = `cc-shell-v36` (after conflict resolution). 
- autonomy_map.json: test_v11_autonomy_timeline (generated-from-live-wiring check) passes; no regeneration needed.

## Suites (merged tree, `JOBS=4 SUITE_REGISTRY=0`)
TOTAL PASSING 470; suites failing: 1.
test_eng_catalogue 13/0, test_eng_catalogue_agents 10/0, test_eng_catalogue_fix1 9/0, test_eng_catalogue_perf 3/0,
test_s4_p0_board 0 failed, test_v11_pwa_browser 0 failed, test_v11_pwa_static 84 passed / **1 failed** (bundle size),
test_w5_inventory 0 failed, test_w4_adopt_manual_listing 0 failed, test_w4_resume_runner 0 failed,
test_v11_autonomy_timeline 0 failing, test_vacuity 0 failed.

## Caveat
The worktree had no `.venv`; I built one with `pip install --no-deps -r requirements-test.lock` plus an unhashed
`pip install -r requirements.txt` (lock hash mode failed on an unpinned h11), so dependency versions may differ from the
lock. No secrets read; no production calls.
