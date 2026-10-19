# INTEG3 (2026-10-19): release candidate cd7e7dc on top of production 1b21e81

Integrator: W-INTEG3. Worktree `.claude/worktrees/W4-INTEG3`, branch `claude/w4-INTEG3`, created from
`origin/claude/w4-INTEG2` 9c3812b. Production: 1b21e81 (= a25a377 + release record), SHADOW.
No deploy, no production write, no spend. Production contact: none (local Postgres only).

**Candidate: `cd7e7dc8483b90347b73de4c1e104a6965ee59b2`, branch `claude/final-candidate-cd7e7dc`.**
(`claude/final-candidate-5f18d11` was frozen first and is SUPERSEDED: BRANDRULE arrived after the
freeze, see §2.)

## 1. Merges (in order, one implementation per defect)

| # | Branch @ head | Merge commit | Conflicts and resolution |
|---|---|---|---|
| 1 | w4-REL2 @ c314c36 (webhook M1/L1/L2, I2/I3, spend B1-B5) | c591529 | none |
| 2 | w4-PLACT @ 6c9d177 (laura_private budget, D-W4-PL-3, status prerequisites) | 20d8b69 | none (gateway/anthropic.py auto-merged with REL2) |
| 3 | w4-BOARD @ e6ee1aa (recount, closures, generator fixes) | 88e91da | `creative/reference.py`: **REL2's B4 fix kept** (canonical; also records refused readings), BOARD's duplicate dropped. `test_w4_board_close.py:174` `test_b195_...` passes unchanged against REL2's implementation. Board files: placeholder, regenerated once (§3). |
| 4 | w4-VISREF @ 8eab43b (compose.py glue, tests, VISREF.md, owner PDF) | e969eb3 | none |
| - | INTEG3 FX fix | c8c4abc | §4 |
| - | INTEG3 boot tables | 93431f8 | §6 |
| 5 | w4-PRODREADY @ 9b25797 (B1 contract-3 legibility, B2 taxonomy, ornament/placemat Product Truth, scipy lock, #61) | 5b16704 | Polled 14:45-16:06Z; head moved fb32507 -> bdd8968 -> 9b25797 (15:42Z), then stable 24 min; PRODREADY.md second pass reports B1, B2 and the motif fixes. `DECISION_LOG.md`: both appended sections kept, no line removed. Generated board/ledger/scope/card files: placeholder, regenerated (§3). |
| - | Regeneration | 5f18d11 | §3 |
| 6 | w4-BRANDRULE @ 75d3bd1 (D-W4-LAURA-OUTFIT, records only; coordinator addition) | cd7e7dc | `DECISION_LOG.md` append-only, both kept; `src/brambleloop/core/decision_index.json` regenerated (26 ids), `test_w3_decision_index` 3/3. |

## 2. Why the candidate was refrozen (5f18d11 -> cd7e7dc)

BRANDRULE arrived while the 5f18d11 suite was half way. "Records commit, no refreeze" was not
possible without breaking something: D-W4-LAURA-OUTFIT is a heading, so `decision_index.json`
(under `src/`) must change for `test_w3_decision_index` to stay green, and any `src/` change in
the records commit breaks the release record's `source_tree_sha256` (deploy_guard `check` and
the boot guard compare it). The 5f18d11 run (20261019T162018Z-22556) was stopped with SIGTERM
(record `interrupted`), BRANDRULE was merged on INTEG3 and the candidate refrozen at cd7e7dc.
The delta 5f18d11..cd7e7dc is DECISION_LOG.md (+26 lines) and decision_index.json (+1 id): no code.

## 3. Regeneration (once, after all merges)

With the fresh venv: `build2_ledger.py evidence_BOARD/prod_api_build_20261019T1249Z.json`
(PROVEN 229, OPEN-DEFECT 2: #11, #12), `aggregate.py`, `fm_ledger.py` (no change),
`completion_board_final.py`, `prelaunch_scope.py`, CC snapshots, `decision_index`.

Generator defect found and fixed (`completion_board_final.py`, unfinished-row branch):
BOARD's rule makes a production module edited since the deploy "not deployed". The
`exists and deployed is False` branch then promoted OPEN rows F-144 (app/main.py, edited by
REL2) and F-718 (core/db.py, edited by INTEG3) to implemented_unverified, so the board's
launch-critical done count (367) exceeded the ledger's COMPLETE (365) and `test_w4_board`
failed. Now an unfinished row is implemented_unverified only when its module is new (absent
from production). The test was not changed.

Effect of BOARD's rule on this candidate (honest, by design): Build 2 production_verified
reads 117 and dev_proven_not_deployed 107, because many verified rows name modules this release
edits; they return to verified after the deploy is read back.

`test_w4_prodready_contract3::test_the_honest_frames_still_verify_pass` gained a
non-emptiness assertion before its loop (test_vacuity).

## 4. FX reference rate

`core/fx.py` was 1/0.715 = 1.3986 CAD/USD, labelled an assumption (not a DECISION_LOG policy).
Now `ASSUMED_CAD_PER_USD = 1.4154` (Bank of Canada, 2026-10-16), USD/CAD derived. USD-priced
calls reserve ~1.2% more CAD (conservative). No ceiling, cap or limit changed: all are CAD
and none reads the rate (asserted). Labels in `routing.FX_NOTE` and `listing_costs` derive
from the constant. Tests: `tests/test_w4_integ3_fx.py` (4); `test_model_access` pin 0.715 -> 1.4154.
FX-dependent suites passed: model_access, v11_wiring, currency, fee_schedule, cert_commerce,
gateway, model_provider, w4_spenda_k5a, w4_finhealth, insights_budget.

## 5. Fresh venv

`/home/user/bl-runs/venv-integ3`: Python 3.11.17, `pip install --no-deps --require-hashes -r
requirements.lock` (lock identical to the merged one, sha256 d7b9a8e6...), plus test-only
httpx 0.28.1, httpcore 1.0.9, certifi 2026.10.18 (not in the lock). `pip freeze` = lock pins + those
3. `pip check` clean. test_dependency_lock, test_w4_prodready_deps, test_cert_dependencies,
test_dependency, test_w3_supply_chain, test_w4_fm2_lock_boot_guard: all pass. (The old `.venv`
had drifted on 20 distributions, e.g. SQLAlchemy 2.1.5, pillow 13; it was left in place.)

## 6. New DB tables and migration

| table | from | created |
|---|---|---|
| `etsy_webhook_refusals` (reason PK, count, last_status, first_at, last_at, last_audit_epoch) | REL2 M1 | at boot (`etsy_webhooks` is imported in `Database.create_all`) and on first use |
| `prospecting_brief_cursors` (event, pod, form PK, offset, updated_at) | REL2 B3 | REL2 created it only lazily (`__table__.create(checkfirst=True)`, not atomic across processes). INTEG3 registers `creative.prospecting` in `Database.create_all`, so boot creates it. |

Proof on a local throwaway PostgreSQL 16.15 (`evidence_INTEG3/rc_pg_boot_output.txt`,
scripts `rc_pg_boot.py`, `rc_pg_exercise.py`): schema built by production 1b21e81 code = 129
tables, neither new table; candidate boot `create_all` -> 131 tables, exactly the two new ones,
`apply_migrations` changes `[]` (no column change on any existing table); second boot no-op;
both tables exercised (counter upsert 5 bad_signature + 1 `other`, 2 sampled audit rows, summary
aggregates; brief offset 0 -> 3 -> 5; reserved word `offset` quoted). Test:
`tests/test_w4_integ3_boot_tables.py` (2). Purely additive: rollback to 1b21e81 ignores the tables.

## 7. Full suite, guard, rollback, security: pending (see next update)

---

# Earlier integration record (2026-10-12/13, candidate a25a377), kept verbatim

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

## 7. Freeze 2 (59675ef): 2 of 629 suites failed (8532 tests passing); freeze 3

| Suite | Root cause (proved) | Fix |
|---|---|---|
| test_db_backup_housekeep, offsite round trip | gpg-agent's socket sits in GNUPGHOME. Under run_tests.sh the per-suite TMPDIR pushes the socket path past the Unix limit of about 107 bytes. Reproduced with a TMPDIR of harness length. The test passes alone and on aa1e76d. | The owner's keyring gets a short home in `/tmp`; teardown kills the agent and removes the home. The round trip still really runs. It passes under the long TMPDIR. |
| test_w4_ccfm1, two trend tests | The run crossed midnight UTC. The "today" fixtures (NOW minus 1 h and minus 2 h) fall on yesterday between 00:00 and 02:00. | The fixtures now fall strictly inside today's UTC date. The assertions are unchanged. Proof: `evidence_INTEG3/fakeclock_ccfm1.py`. The old fixture fails at 00:30Z; the new one passes at 23:59:59, 00:00:30 and 01:30Z. |
| (security review of 59675ef, LOW) | — | `migrate.widen` now runs `SET LOCAL lock_timeout = '5s'`. The second LOW, an atomic reserve for Private Laura, belongs to the PRIVLAURA worker and is deferred to the next release. |

FMCLOSE@13aed5e and VISROLE@52b702d merged cleanly. All 33 focused suites passed on the first try: the required set, accounting and money, auth, the visual suites, the board and snapshots, and recovery. Per FMCLOSE, F-575 stays OPEN (its wiring was reverted). PRIVLAURA updates and the VISROLE legibility rework are excluded and go to the next release.

## 8. Freeze 3 (9522fac): 1 of 631 suites failed (8562 tests passing); freeze 4

The failing suite was test_cert_growth_ops, `test_ads_adjust_reads_economics_from_rows_and_escalates_a_winner`, with `KeyError 'attributed_orders'`.

- **Cause.** FMCLOSE (F-570) now marks the Offsite Ads share UNMEASURED while any order has no reading, and the UNMEASURED dict dropped the measured count of attributed orders.
- **Fix.** The UNMEASURED reading keeps `attributed_orders`: the orders the ledger or evidence attributes. Unread orders stay in `attribution.unknown`, and the share is still not computed.
- **Tests now passing:** test_cert_growth_ops, test_w4_fmclose_etsy, test_paid_media_economics, test_v11_ads_readiness and the required set.

## 9. Release candidate a25a3774: verdicts

- **Full suite.** Run 20261013T022833Z-14781 on a25a3774 **passed**: 631 suites, 8563 tests passing, 0 failing, 0 tmp leak. It ran with REQUIRE_CLEAN=1, JOBS=3, the .venv python and the SIG_DFL launcher.
- **Release record.** `deploy_guard record` wrote `release/RELEASE_a25a3774….json` (tree_sha256 6499098f…). It is committed with `release/NOTES_a25a3774.md` as 1b21e81 on `claude/final-candidate-a25a377`.
- **Deploy dry run.** `DRY_RUN=1 sh ops/deploy.sh` returned **ALLOW** on 1b21e81. The built-in rollback rehearsal to 7bbbe72 also returned ALLOW. Nothing was pushed.
- **Rollback rehearsal.** I ran `DRY_RUN=1 sh ops/deploy.sh --rollback-to 7bbbe72… --deployed 1b21e81…`. With the one-word reason "rehearsal" it was REFUSED, because the guard requires a reason of at least 10 characters. With a full reason it returned **ALLOW**: the rollback commit was built and nothing was pushed.
- **Fast-forward.** 7bbbe72 is an ancestor of the candidate.
- **Migration.** The only schema change is widen-only: policy_snapshots.version goes from VARCHAR(40) to VARCHAR(120) on Postgres, under lock_timeout. It is additive and rollback-safe; see NOTES.
- **Excluded from this release:**
  - the PRIVLAURA updates: the laura_private agent, the atomic reserve, and removal of the consent gate;
  - the VISROLE legibility rework;
  - #61's closure (held).
- **Not done:** no deploy. Deploying needs owner approval.
