# INTEG3: integration release candidate on `claude/w4-INTEG2` (2026-10-12)

Integrator: W-INTEG. Worktree: `.claude/worktrees/W4-INTEG2`, branch `claude/w4-INTEG2`.
Starting head: 28ba6df. No deploy, no Etsy action, no spend, no production write. SHADOW is unchanged.
Production reads were GETs only: `/health`, `/api/verify`, `/api/build`, `/api/build2`,
`/api/status` and `/api/queue/dead`, saved under `evidence_BOARD/*_20261012T1856Z.json` and
`evidence_INTEG3/`.

## 0. Production lineage was missing from INTEG2

INTEG2 at 28ba6df did **not** contain the deployed hotfix 7bbbe72: neither LAURAFIX (bounded
briefing reply, grouped incidents) nor ETSYSHOPID (shop binding). A candidate built from it
would have regressed production. I merged 7bbbe72 first, in e7e2ccf.

- For the LAURA1/LAURAFIX files, INTEG2 was byte-identical to their common base 5ad94dd, so the
  production side was taken.
- For `rebuild_graph.py`, `durable.py` and FINHEALTH_FIX.md, INTEG2 already carried the
  equivalent fixes, so INTEG2's side was kept.
- For DECISION_LOG and DEPLOYED_HISTORY, the INTEG2 side was kept, and every production line
  is present.

## 1. Production defects

Source: production `/api/verify` on 7bbbe72, `no_unexpected_dead_letters_in_24h`. The first
dead letters appeared at 18:01-18:08Z, after the hotfix. BUILD_STATE's earlier "15:01-15:16Z
under c498888, pre-hotfix" is wrong: these defects are present in deployed 7bbbe72.

I copied `tests/test_w4_integ3_defects.py` onto 7bbbe72. **11 of its 13 tests fail there**
(`evidence_INTEG3/`); all 13 pass on the final tree.

| Defect | Root cause | Fix | Regression test |
|---|---|---|---|
| a. `radar.score` `KeyError: 'slug'` (×2) | The Intelligence charter consumes `CoverageGap` with `radar.score`. The orchestrator's handoff mission, and Laura's follow-on, enqueue it with `{"handoff": …}` and no concept. The handler read `inputs["slug"]`. | `pipeline._score_coverage_handoff`: with no slug, it scores the open gap queue. Each gap's named `product_slug` concept, otherwise the concepts its pod routes (`Pod.matches`, the same rule `intel.observe` uses), gets an ordinary per-slug `radar.score` keyed `score:<slug>:<date>`. A gap with no concept is reported, never scored as 0. **W4-B2CLOSE fixed this independently**; the two are now one implementation (B2CLOSE's product_slug mapping plus INTEG3's pod routing), and both test sets are kept. | `test_a_coverage_handoff_radar_score_completes_and_fans_out_per_concept`, `test_a_closed_gap_is_not_scored_and_a_named_product_wins_over_pod_routing`, `test_a_concept_already_queued_today_is_not_queued_twice`, `test_a_concept_radar_score_is_unchanged`; B2CLOSE `test_195_radar_score_without_a_slug…` |
| b. `ops.policy_watch` `StringDataRightTruncation varchar(40)` | `policy_knowledge.seed_snapshots` writes version `"<read_on>:search_engine_excerpt_of_official_page"`, which is 49 characters, into `policy_snapshots.version VARCHAR(40)`. SQLite never enforces the limit. | **Migration, not truncation.** The model is now `String(120)`. The new `core.migrate.widen` runs inside `create_all` on Postgres: strict VARCHAR widenings only, never a narrowing, and SQLite is skipped. `record_snapshot` refuses a version longer than `VERSION_MAX` instead of clipping it. B2CLOSE's alternative (`fit_version`: head plus digest, full label kept in `detail`) was dropped so there is one implementation. Its test now asserts that the label is stored verbatim. | `test_the_seeded_policy_versions_fit_the_column…`, `test_an_overlong_policy_version_is_refused_not_truncated`, `test_the_widening_migration_never_narrows_and_skips_sqlite`, `test_policy_watch_runs_to_done`. **Postgres 16 reproduction** (`evidence_INTEG3/pg_repro.py` and `pg_repro_output.txt`): on VARCHAR(40) the exact production error occurs; `create_all` then widens `VARCHAR(40) -> VARCHAR(120)` and the seed succeeds (7 rows, max 49). A second `create_all` makes no change. |
| c. `ops.offsite_archive` `EphemeralStorageRefused` | The DB URL *is* bound; this is not the archive's database. The upload and the read-back succeed. The **restore proof** then opens a throwaway SQLite file without `scratch=True`, and the hosted guard (`REQUIRE_POSTGRES=1`) refuses every SQLite URL. `continuity` already had the exemption; `offsite.archive` did not. B2CLOSE made the identical fix. Also found on the same path: the "configured and failing" branch built `Incident(kind=…, severity="high")`. `kind` is not a column, and the NOT NULL `signature` was missing, so a real archive failure would have dead-lettered instead of opening an incident. | `scratch=True` on the restore-proof DB. The failure incident is now `severity="P1"`, `signature="offsite_archive_failed"`, opened once and counted on repeat. | `test_the_restore_proof_runs_where_postgres_is_required` (and it proves the guard still refuses ordinary SQLite); `test_a_configured_archive_failure_opens_one_incident_instead_of_dead_lettering` |
| d-L1. Two mandatory incidents with the same job type and error class share a headline | `briefing.incident_root` groups by job type and error class. | First attempt: put the signature in the key. That **broke** `test_w4_laurafix_truncation`, which requires different signatures with one root cause to group (its 1,000-incident bound). Final fix: the grouping is unchanged, and each group counts its distinct normalised signatures. The record reads "N occurrences **across K distinct incident signatures**", so a second root cause is never hidden. | `test_l1_a_group_that_merges_different_incidents_says_so`; laurafix 8/8; laura1_briefing OK |
| d-L2. Shop lookup repeats while unbound | `ensure_credentials` ran `resolve` (1-2 Etsy GETs) on every client build. | Bounded backoff from the module's own audit rows, shared across processes: `min(60 s × 2^(n-1), 3600 s)` after n consecutive unresolved attempts. A success resets it, and elapsed time is clamped at 0 for clock skew. | `test_l2_an_unresolved_shop_binding_backs_off_and_a_success_resets_it`; `test_w4_etsy_shop_binding` OK |
| d-I2. Stale `@3` comment | `agents/registry.py` | Names `gateway.laura_briefing.PROMPT.ref` (`@4`). | `test_i2_the_registry_names_the_live_briefing_prompt` |

Security review I1 (binding not tied to a grant) was optional hardening and was not done; it
is listed as INFO.

## 2. Merged and rejected branches

| Branch@sha | Decision | Evidence and reason |
|---|---|---|
| production 7bbbe72 (HOTFIX1) | **merged** | See §0. |
| SWARMCONTROL@b352b34 | **merged** | I read the full diff (F-457 ownership manifests, F-470 resource reading with UNKNOWN when unreadable, F-473 cooperative preemption, lease-fenced, un-counted requeue). test_w4_swarmcontrol, test_swarm and test_swarm_runtime are OK. |
| CCNOTIFY@9e1aeec | **merged + fixed** | F-897 deadlines and commercial events, in-app only (the external channel stays CASL-gated). Its test had two vacuous loops (`test_vacuity` FAIL). I added non-emptiness assertions, which strengthens the test. test_w4_ccnotify, test_w4_ccux and test_cert_dashboard are OK. |
| ETSYREVIEW@8df180c, B2MOAT@4625075, PRICEFIX@4e0b908, SIZEINTENT@8ccf9a6 | **merged** | Each branch's code was already on INTEG2; these tips are checkpoint notes only. Their test files (etsyreview, b2moat, size_shape_intent) are OK on the final tree. |
| PRIVLAURA@7bb1da5 | **merged** | Defaults verified in code: `BRAMBLELOOP_LAURA_PRIVATE_REGISTER` must be exactly "1"; `…_DAILY_CAD` unset or invalid reads as 0.0, which refuses before reservation (`SPEND_UNAUTHORISED`); `enabled` also needs the provider and the private key. My own testslot runs: all 6 test_w4_pl_*, all 6 test_w3_priv_* and all 21 test_w3_laura_* are OK, plus test_w4_laura1_budget, test_w3_spend_laura_phrase and test_w4_secfix_insights_private. LAURA-PRIVATE-REGISTER is on the board as a `tracked` row, class **blocked_owner / TRACKED-OPEN**: not complete. It needs OA-PL-1..4, an approved deploy and the class-B soak. D-W4-PL-2 (expanded register) is an open decision, not a defect. Not activated anywhere. |
| VISFIX@9f59663 (with IMGFIX, DISCLOSEDQA, HEROTOURNEY) | **merged** | Adversarial check of the 340 px change: the expected piece count is `cir.components[0].make`, taken from the **CIR**, for rounds and for single-component flat pieces. The old flat path used the renderer's `layout.copies`, so the check is now *more* independent of the renderer. Thresholds and the piece counter are unchanged. test_launch 28/28 (was 15 FAIL on 28ba6df), cost_governance OK, imgfix, disclosedqa and herotourney OK. |
| B2CLOSE@2190561 | **merged** (conflicts resolved) | See §1 a-c for the single implementation per defect. #61 is PROVEN in the ledger. test_w4_b2close2 11/11, test_w4_b2_build2_ledger ALL OK, test_cert_listing_frames OK. |
| FMCLOSE@013c2e3 | **rejected (for now)** | `test_v11_accounting_reconciliation::test_payout_matches_bank_deposit_and_unmatched_lines_become_exceptions` **fails on FMCLOSE's own tip** (013c2e3, run in an isolated worktree) and passes on clean 28ba6df. The payout/bank reconciliation now also reports order lines 70001-70004 as statement lines. `test_v11_accounting_controller` was fixed at 013c2e3. **Needs:** fix the reconciliation change, or justify it without editing that test's expectation, then rerun the set. Security notes for its review: `POST /api/etsy/webhook` is public by design (HMAC-SHA256, 300 s skew, 503 with no secret). INFO: every refused unauthenticated delivery writes an audit row (unbounded), and the body is read before the 64 KiB check. |
| SWARMQUEUES@aab7a55 | not merged (WIP) | Breaks 3 test_swarm_runtime backlog tests (feed_idle/backlog_order) and 2 of its own. Needs: restore ceiling-skip and idempotency semantics, then the regression set. |
| HYGIENE@c977f6d | not merged (WIP) | No test has completed. Needs: test_w4_hygiene, test_run_tests_script, test_w3_tmp_hygiene and test_spend_governance, then the regression set; drop WIP. |
| AESTHETIC@68247ca | not merged (WIP) | Fails 1 own test (`test_the_fallback_facet_map_carries_it_and_still_maps`); regression set partly unrun. |
| B2ASSETS@cf42b23 | not merged (WIP) | F-527 is partial; regression set not run. |
| CCFINST@450a468 | not merged (WIP) | F-620 code is done; reruns and the regression set have not run on its merged head. |
| CCMKTLAB@d51df29 | not merged (WIP) | F-684; its own test rerun, ccall, v11_cc_views, pwa_static and the regression set have not run. |
| STITCHFAM@c8f1602 | not merged (WIP) | F-759 registry is unwired and untested. |
| SETCONSIST@41f72ee | not merged | F-746; reports only test_parity. Needs the required regression set and a merge onto the current INTEG2. |
| DRIFTMARGIN@a9fb6de | not merged | F-218; required set not reported (only vacuity). |
| UPGRADECMP@8b24bbc | not merged | F-738; required set not reported (only vacuity). |

## 3. Regression set (testslot, N=3)

Results on the final tree (integ3-cand4, now INTEG2), compared with clean INTEG2 28ba6df:

| Test | 28ba6df | Final tree |
|---|---|---|
| test_vacuity | OK | OK (rerun after the last test edits) |
| test_launch | **15 FAIL** (hero 340 px) | OK |
| test_cost_governance_wave2 | **1 FAIL** (mkdtemp in visual/*) | OK |
| test_search_hero_publish | OK | OK |
| test_cert_listing_frames | OK | OK |
| test_v11_autonomy_timeline | **1 FAIL** (map 57 vs 58) | OK (map regenerated on the final tree: 59 edges) |

Also OK on the final tree:

- test_w4_integ3_defects, test_w4_b2close2, test_w4_b2_build2_ledger
- test_radar, test_offsite, test_platform_policy, test_policy_knowledge
- test_w4_autonomy_idle_departments, test_w4_archive_priority, test_w4_auditfix_migrate
- test_w4_swarmcontrol, test_swarm_runtime, test_w4_ccnotify
- test_w4_imgfix, test_w4_disclosedqa, test_w4_herotourney
- test_w4_pl_reply, test_w4_pl_budget, test_w4_pl_leak
- test_w4_laura1_briefing, test_w4_laurafix_truncation, test_w4_etsy_shop_binding, test_w3_laura_cc_talk

PRIV/Laura full set: 35/35 OK on the pre-VISFIX candidate. Two notes on that run:

- test_w4_laurafix_truncation failed there because of my first L1 attempt. It is fixed, and the
  fix was rerun on the final tree.
- Of the 12 FMCLOSE shared-file suites, the 10 others passed there, along with route_auth,
  customer_data_auth, money_truth and cert_orders.

No full suite was run.

## 4. Requirement rows whose status verifiably changed

The board and prelaunch scope were regenerated from fresh production GETs (7bbbe72, 18:56Z).

- **verified_complete: unchanged** (Build 2: 215; FM launch-critical: 362). No row was closed,
  because closure needs the code deployed and production evidence.
- **Build 2 #61**: OPEN-DEFECT → **PROVEN** in the ledger (B2CLOSE). Board class:
  blocked_engineering → implemented_unverified. Needs a deploy.
- **Build 2 #195** (24 h off-device window): its only unmet condition is
  `no_unexpected_dead_letters`. All three dead letters now have fixes, with regression tests
  that fail on 7bbbe72. Verifying it needs a deploy and 24 h without dead letters. It stays
  blocked_engineering.
- **Production gates now OPEN**: etsy_shop, etsy_api, transactions_r and benchmark_observation.
  The Etsy binding works in production. That moved 2 Build 2 rows (#11, #12) and about 20 FM rows
  from blocked_owner to blocked_engineering. This is unparked work, not a closure.
- **FMCLOSE rows** (F-283, F-501, F-512, F-558, F-570, F-574, F-575, F-590, F-595, F-657,
  F-682) read `in_progress` on the board because the branch is active and unmerged. They are not
  closed.
- **SWARMCONTROL** F-457/F-470/F-473 and **CCNOTIFY** F-897 code is merged but not deployed, so
  the board does not count it as complete.
- **LAURA-PRIVATE-REGISTER**: a new tracked row, blocked_owner (TRACKED-OPEN).

## 5. Before a release candidate

1. Run a full suite on the INTEG2 head. Only the focused sets above have run.
2. Fix and merge FMCLOSE, or leave it out of the release.
3. Get owner approval for the deploy. On deploy, `migrate.widen` alters `policy_snapshots.version`
   to VARCHAR(120). This is a metadata-only widening, run inside `create_all`.
4. After the deploy, check `/api/verify` for no new dead letters of radar.score, policy_watch or
   offsite_archive, then hold 24 h for #195.

## 6. Candidate freeze 1: claude/final-candidate-056398c, full suite FAILED (16 of 629 suites)

Run 20261012T201528Z-25244, with REQUIRE_CLEAN=1, JOBS=3 and the .venv python, under a SIG_DFL launcher:

- 8470 tests passing; 16 suites failing; run record `failed`;
- 1 tmp leak (test_w4_pl_continuity).

Every cause was fixed on INTEG2. No test or gate was weakened.

| Failing suite(s) | Cause | Fix |
|---|---|---|
| test_w3_tmp_hygiene; tmp leak in test_w4_pl_continuity | test_w4_fmgate_catalogue_filters (from INTEG2) and test_w4_pl_continuity (from PRIVLAURA) created temp files without `_tmp.install()`. scripts/w4_learn_loops_proof.py had no cleanup path. | Sandbox installed in both tests; `atexit` rmtree added to the script (17aaa58). |
| test_w4_autonomy_idle_departments, b2close2, b2gate2, b2moat, b2vision, copy, marketintel | These suites pass, but print `ok`/`PASS` lines. The harness counts `^OK`, so each was recorded as "SUITE REPORTED NO PASSES". | Each runner now prints `OK   <name>` per passing test. Assertions unchanged. |
| test_w3_decision_index, test_w4_cc_snapshots, and test_w4_board (card snapshot) | Generated artefacts were stale after the merges. | Regenerated `decision_index.json`, the CC snapshots, the board and the prelaunch scope. |
| test_w4_board `root_causes_count_the_rows_they_unblock` | The board's root causes now count the tracked LAURA-PRIVATE-REGISTER row, but the test summed only Build 2 and FM rows. | The test sums all rows, including tracked ones, and asserts the tracked row is present. The equality is kept. |
| test_v11_autonomy_recovery | Failed already on clean 28ba6df; it is a W4-AUTONOMY regression. A reclaimed `autonomy.orchestrate` tick whose `now` trails the wall clock read the missions its own first attempt had just queued as "waiting". It therefore queued a second set: 22 jobs instead of 11. | `generators.actionable`: a job that was due when it was created was never deferred, so it counts as actionable. Parked jobs, whose `run_after` is beyond creation plus the grace period, are still "waiting". test_v11_autonomy_recovery, orchestrator, overnight, kpis, timeline and w4_autonomy_idle_departments all pass. |
| test_cert_dashboard (legacy-row merge), test_w4_owner_actions (production-nine) | Caused by B2CLOSE marking Build 2 #61 `covered` and removing its `parked_on: image_vision`. #61 was the only row parked on image_vision. So image_vision, and the `model_credits` owner action aliased to it, unblocked no Build 2 row, and the owner inbox stopped asking to fund the model. Two existing acceptance tests fail on that. | **#61's closure is held for the next release.** The row is restored to partial and parked on image_vision, with a dated note. The ledger was regenerated with B2CLOSE's own inputs. Build 2 #61 therefore reads OPEN-DEFECT again: the gate is open and the work is unparked. The row's owner must update those tests' example gate before the closure ships. |
| test_deploy (FK on launch.readiness delete), test_db_backup_housekeep (gpg quick-gen-key exit 2) | Pass alone on INTEG2, and pass on 28ba6df. These look like load or order flakes. | None. Watched in the next full run. |
