# CERTFIX-1 — review request

- **Branch:** `certfix/1`, cut from `claude/w6-INTEG8-wip` (511a8c6).
- **Fix SHA:** `63f06bfca125db706372fc59dfb4b0d07a8360a3`. This file is committed on top of it.
- **Validation run:** `20261120T230421Z-5923`, `JOBS=4 SUITE_REGISTRY=0`, 22 suites, tree clean, HEAD unmoved.
  - Interpreter: `.venv/bin/python`, Python 3.11, the production Dockerfile's version, built from `requirements.lock` +
    `requirements-test.lock` with `--require-hashes`.
  - Result: TOTAL PASSING 266, suites failing 0, duration 1380 s.
- **Status:** NOT deployed. Production unchanged.

## Per-suite results (run 20261120T230421Z-5923)

| Suite | OK | FAIL |
|---|---|---|
| test_r2_autonomy_useful_work | 6 | 0 |
| test_swarm_runtime | 10 | 0 |
| test_cert_wiring | 16 | 0 (drain 1238 s suite time; limit 1525 s) |
| test_platform | 22 | 0 |
| test_v11_cc_views | 14 | 0 |
| test_w4_wire1_routes | 6 | 0 |
| test_w4_close6_timeline | 3 | 0 |
| test_fastlane | 14 | 0 |
| test_w5_a9_package_event | 8 | 0 |
| test_w4_contracts | 8 | 0 |
| test_w4_fmbatch1_contracts | 5 | 0 |
| test_w4_prodready_deps | 3 | 0 |
| test_deploy | 32 | 0 (no native abort) |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |
| also run: test_eng_supply 17, test_lanes 26, test_personalisation 12, test_w4_ccgap_pdfium 3, test_w3_decision_index 3, test_v11_autonomy_timeline 6, test_w4_c12_wiring 4 | | 0 |

No assertion was weakened, and no test was skipped or quarantined. Test edits:

- `test_w4_fmbatch1_contracts`: the pins moved together with their declarations, as the test demands.
- `test_w4_ccgap_pdfium`: a new regression test.

## Fixes, by suite

- **test_r2_autonomy_useful_work / test_swarm_runtime.** `improve.self_tune` declares `WORK_KEYS = ("work_done",)` and
  band `exploration` (like every other `improve.*`).
  - `trials_judged` and `loops_closed` are standing counts that include "wait" verdicts, so they are not declared as work.
- **test_fastlane.** `child_safety` is in `certificate.CANONICAL_STAGES`, in chain order before `confidence`, and in
  `CONDITIONAL_STAGES`, because the chain runs it only when `child_safety.applies`.
  - `commerce.lanes.applicable_gates` owes the stage from a new `Profile.child_safety`. Production fills it from
    `child_safety.applies(cir)`.
  - Unread (`None`) owes it for any closed form, so the read fails closed.
- **test_platform (ops.continuity "no such table: radar_concepts").** Some tables are created by their handler on first
  use, e.g. `radar.intake._ensure`. Once that module is imported, its table is in `Base.metadata` but may not exist yet in
  the database.
  - `continuity.export` and `counts_by_table` now treat such a table as empty, which is exact. The restore creates it.
  - The source is still never written.
- **test_w4_contracts / test_w4_fmbatch1_contracts / test_w4_wire1_routes.**
  - ENG-PLUSH and ENG-COLOURWORK changed the CIR without a bump: `Chart`, `Component.chart/stuff_at_round/closes`, and
    Seam `'surface'`. The CIR goes v2 -> v3 with a CHANGELOG entry and the pins are regenerated. `quality_ops` and
    `engineering_ops` re-pin to v3. They read none of the new fields.
  - ENG-IMPROVE added `GET /api/readback/ecrs` without a row. Both changes are declared in `ops/CONTRACT_CHANGES.md`.
  - `test_w4_prodready_deps` already passed with the lockfile venv. The onnxruntime failure in dde3ea62 came from the
    system-interpreter environment.
- **test_v11_cc_views.** The autonomy `learning` section now carries the envelope (status, sources, basis, reason when
  UNKNOWN). With it fixed, the next failure was insights `benchmark_shopping`, which lacked `basis`. Both are fixed.
- **test_w4_close6_timeline / test_w5_a9_package_event / test_cert_wiring.** The ENG-SUPPLY chain-end refill is
  narrowed; see **D-CERTFIX1-SUPPLY-REFILL**.
  - `Worker._supply_after` refills only when its own registry runs `supply.admit`. A private-registry worker's refill
    could only dead-letter, and it showed up as an uncaused story in the timeline.
  - `supply.after_chain_job` does not refill when two or more slots are open after the end, because one was already free.
  - The full-WIP case D-ENG-DEMAND-SUPPLY relies on is unchanged, and test_eng_supply passes unchanged.
  - Before this, one release's chain in a9 seeded and packaged all 8 Launch-0 releases.
- **test_cert_wiring drain: no job type loops.** I measured the live drain DB:
  - All 13 refills were legitimate last-chain-job ends.
  - The drain builds the whole fresh-company supply: 8 Launch-0 releases plus the static-pool offers from the day's
    radar scan. Per-product cost is about 70 s: `assets.build` 28 s, `store.publish` 18 s and `listing.package` 15 s. The
    last two rebuild both customer PDFs in `first_customer._documents` by design (the gates run before the SHADOW
    refusal).
  - The cert runs also lost `ops.continuity` to a dead letter, which is fixed above.
  - Now it drains in about 1240 s here. **Risk for the reviewer:** that is about 81% of the 1525 s owner limit at
    JOBS=4 on 4 cores. The cert host at JOBS=8 measured about 2.5x slower per job, so it may still exceed the limit there.
  - I did not raise the limit; it is an owner decision (D-W4-CERTWIRING-LIMIT). If it fails on the cert host, the honest
    next steps are:
    - a scoped performance change, e.g. memoising `build_pattern_pdf` per (CIR fingerprint, terminology, code version)
      within a gate evaluation;
    - or an owner decision on the limit.
- **test_deploy (`bad_variant_access` abort): NOT environment-only. It is a real shutdown race, now fixed.**
  - Command Center refresh threads are daemons and can be inside a PDFium render at interpreter exit.
  - At exit, `weakref.finalize`'s exit function (pypdfium2 objects close through finalizers) and then pypdfium2's
    `atexit(destroy_lib)` closed the live document and page under the render and destroyed the library.
  - Evidence:
    - It aborted in dde3ea62 but not b098fcce: same python3.13 and same pypdfium2 5.13.0 (the locked version).
    - A standalone repro with no hook crashed 1/15 runs on 3.11 and 2/15 on 3.13 (SIGSEGV in `FPDF_RenderPageBitmap`).
  - Fix: `contents_frame._pdfium()` creates a finalizer first, so `weakref.finalize` registers its exit function, and then
    registers an exit hook. atexit is LIFO, so the hook runs before both.
    - The hook takes `PDFIUM_LOCK`, which waits for the in-flight render to close its objects, and never releases it.
  - Result: 0/40 crashes across 3.11 and 3.13.
  - New test `test_a_render_in_flight_at_interpreter_exit_finishes_before_pdfium_is_destroyed`: three daemon threads
    render the real pattern PDF continuously at exit, six runs.
    - It FAILS against the unfixed module (SIGSEGV, rc -11) and passes fixed.

## Not in scope / still failing elsewhere in the cert lists (not touched)

test_cert_design, test_cert_parity_copy, test_cert_rebuild_chain, test_eng_catalogue_perf, test_final_closure_matrix,
test_opus2_size_claims, test_physfix, test_provenance_write_path, test_r5_research_2/3/4, test_s1_*, test_shadow,
test_w3_tmp_hygiene, test_w4_fmbatch1_adoptions/drift/licenses, test_w6_listing_chain_e2e, test_ws2_*, test_ws4_7_postgres,
test_ws4_stage_a_withdrawal, test_codex_v1_*.

- **test_w3_decision_index** now passes: the index was regenerated with the two new decision entries.
- **autonomy_map.json:** regenerating it changed only the timestamp, so it was not committed. Its counts match the live
  build.
- **No clock-sensitive suite was added.**
