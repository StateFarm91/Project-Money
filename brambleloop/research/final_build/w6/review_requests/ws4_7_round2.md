# Review request: WS4-7 Mode T, round 2 (fixes for the review of 91ee7f50)

> **Round 3 (fixes for the review of `259555fe`)** is at the end of this file. Code SHA
> `dd67d90`; the final SHA is the docs commit that updates this file.

- **Branch:** `eng/ws4-7-mode-t-fix`
- **Reviewed:** `91ee7f50`
- **Code SHA:** `c1743d9` (fixes `99e6d24`, plus one test-only commit). The commit that adds
  this file changes only documentation; the final SHA is that commit.
- **Nothing is live.** No deploy, no Railway change, no secret, no real key, no Etsy call, no
  spend.
  - `deployment_mode()` is still `S` by default.
  - Stage A public activation is still absent.

## Findings: fix and test

Each regression test listed under MEDIUM-1, L3 and L4 was run against the 91ee7f50 sources (a
worktree with the old `src/` and the new tests) and **failed there**; each passes now. The L2
items are tests of checks that already existed, so their evidence is a mutant per check: each
mutant was applied to the current source, and the test named for it failed.

| Finding | Fix | Regression test | On 91ee7f50 / mutant |
|---|---|---|---|
| **MEDIUM-1** `ads_jobs_queued` was hard-coded `PASS 0`. Once ads authority exists, `ads.adjust` queues `ads.campaign` for any eligible product, including standing-lineage products, so the issue-time "ads must be NONE" check could never hold a grant. | `standing_issuer._ads_jobs`: counts PENDING/RUNNING `ads.*` jobs whose `slug` is the requested product or any product in the policy's standing lineage (`standing_stop.lineage`: every grant issued under the policy). The planner `ads.adjust` names no product and spends nothing, so it is not counted. Any other `ads.*` job that names no product **is** counted (fail closed). An unreadable lineage or queue, or content with no `policy_id`, reads **UNKNOWN** (through `_guard`), never `PASS 0`; UNKNOWN holds. | `test_ws4_7_issuer` → `test_ads_jobs_on_the_release_or_its_standing_lineage_hold_the_grant`. Issues a grant for product A (A is now in lineage), queues `ads.campaign` on A, then reads facts for product B: value 1 and `classify` holds with "ads must be NONE". DONE jobs and the planner are not counted; a RUNNING job on the requested product is; a lineage read that raises gives UNKNOWN and holds. | 91ee7f50: `{'state': 'PASS', 'value': 0, 'why': 'no job carries a standing-policy lineage'}`. Mutants killed: hard-coded `PASS 0`; lineage ignored. |
| **L2** The future-dated report check had no independent test. | Test only. | `test_a_report_dated_in_the_future_reads_mode_s`: reports dated 2 min ahead give Mode S, and every reason is "dated after now". At their own time, and within the 30 s skew allowance, they give T. | Mutant `elif at - now > CLOCK_SKEW` → `elif False`: killed (`mode T`). |
| **L2** The boot-key check had no independent test. The subprocess test also sees the key in `/proc/self/environ`. | Test only. | `test_the_issuer_key_seen_at_boot_is_reported_after_the_scrub_in_process`: in process, `mark_job_process()` scrubs the key. `issuer_key_present(<clean mapping>)` is then True from the boot fact alone; the report says `issuer_signing_present: True`; Mode S has exactly one reason. After a reset, the same mapping reads False. | Two mutants killed: the boot fact is not recorded; the boot fact is not read. |
| **L2** The worker-privileges check had no independent test. In every existing case the issuer's reading also fired. | Test only. | `test_a_worker_reporting_grant_store_powers_reads_mode_s_on_its_own`: the worker reports `INSERT standing_grants` and the issuer reads `[]`. Result: Mode S, not separated, and exactly one reason ("the worker's database role 'bl_worker' can write the grant store"). | Mutant `elif wp:` → `elif False:`: killed (`mode T, separated True`). |
| **L3** `consume()` did not re-check the shop binding at use. | `standing_grants.shop_refusal`, called by `consume()` after the policy re-check and before the UPDATE. The shop binding read now must be PASS (a name-verified binding), and its id and name must equal the **signed** `shop` in the grant. Otherwise the grant is void and nothing is consumed. | `test_consume_rechecks_the_shop_binding_at_use` covers four cases: re-bound to another id; unbound; a binding that names another shop; the expected shop name changed after issue. Each is refused with nothing consumed. With the binding restored, the same grant is consumed. Test helpers now bind a shop (`_bind_shop`) in `_effective_db` / PG `_policy`. | 91ee7f50: consumed (`expected a refusal containing 'is void'`). Mutant (call removed): killed. |
| **L4** Worker table ownership. Under the runbook the worker keeps CREATE on `public`, and `worker_entry` ran `db.create_all()`. | `Database.boot_schema(component)`. On PostgreSQL, if the process's role is not the owner of `jobs` (the migration owner), it only checks that every registered table exists. It never creates one. If a table is missing, the worker logs `worker refused to start: … Deploy web (the migration owner) first` and exits **3**. On SQLite, or for the owner's role (Mode S, one role), behaviour is unchanged (`create_all`). `standing_grants.ensure_tables` never creates the grant store in a job or issuer process. `create_all` is split into `register_models()` + create, with the same imports. | **PG16** `test_ws4_7_postgres` → `test_the_worker_role_never_creates_a_table_it_should_not_own`. A release that **adds** the grant store (tables and trigger function dropped by the owner) boots the real `worker_entry.main` as `bl_worker`: rc 3, nothing owned by `bl_worker`, and `ensure_tables` from a job process is refused. Web's `boot_schema` then creates the tables, and the worker starts with rc 0 and still owns nothing. SQLite: `test_a_job_or_issuer_process_never_creates_the_grant_store`. | 91ee7f50: the worker started (`rc 0`) and **created and owned `standing_grants` and `standing_grant_slots`** (checked separately in `pg_tables`). SQLite: a job process created the store. |
| **L4** Runbook: deploy order and ownership. | `WS4_7_MODE_T.md` § "Deploy order and table ownership": web first (wait for `/health` 200), then worker (it refuses until web has migrated, and nothing needs repair), then policy-issuer. Every registered table and the grant store are owned by the migration owner (web's role). The worker may own only handler tables it creates lazily (e.g. `radar_concepts`), and default privileges give web ALL on those. `REVIEW_REQUEST.md` repeats the order. | (doc) | — |
| **L5** The cost card showed a single number, and web without the worker was unmeasured. | `scripts/ws4_7_measure_rss.py` now also runs web as Mode T runs it: `uvicorn … main:app`, `BRAMBLELOOP_EMBEDDED_WORKER=0`, migration owner, `/health` every 30 s. Run 2 (720 s, PG16, runbook roles): **web with the worker removed is 134.1 MiB** (peak = steady), 0.0015 vCPU, 24/24 health checks OK. Issuer 74.8 MiB. Worker steady 291.1 MiB, peak 942.7 MiB, 0.86 vCPU saturated. The card is now a range (below). The `WS4_7_MODE_T.md` cost section and `REVIEW_REQUEST.md` are updated. Data: `research/final_build/ws4/ws4_7_rss_measurement_2026-11-18_round2.json`. | (measurement) | — |
| **L1** Forged web/worker reports could give Mode T. | Accepted while the mode is S, as agreed. `WS4_7_MODE_T.md` now has a **one-time owner catalogue check before Mode T is ever enabled**, CA$0, ~5 min. (1) Confirm the user in each service's `DATABASE_URL` in Railway (`bl_worker` / `bl_issuer`), without pasting it anywhere. (2) Run `pg_stat_activity` grouped by role: exactly web's, `bl_worker` and `bl_issuer`. Check `pg_roles` flags, and four `has_table_privilege` / `has_column_privilege` / `pg_has_role` checks for `bl_worker` on the grant store (all false). List tables owned by `bl_worker`: no grant-store table. (3) Stop the worker; its `bl_worker` connections must disappear. Any difference means Mode T is not enabled. | (doc) | — |

## Cost card (round-2 L5): a range, never one number

Pricing: US$10 per GiB-month of memory, US$20 per vCPU-month.

| Process | Measured | US$/month |
|---|---|---|
| policy-issuer | ~70 MiB (reviewer) to 74.8–75.0 MiB (runs 1–2), 0.0012–0.0016 vCPU | 0.71–0.76 |
| worker, idle | 103.0 MiB (round 3, measured; was 95.8 from a 75 s trial) | 1.01 |
| worker, steady after jobs | ~284 MiB (reviewer) to 291–304 MiB (runs 2, 1); ~300 MiB after jobs (reviewer) | 2.77–2.97 (memory) |
| web, worker removed | **134.1 MiB**, 0.0015 vCPU (run 2) | 1.34 |
| worker, saturated (upper bound) | peak 810–943 MiB, 0.86–0.91 vCPU | 20.1–26.5 |

The new monthly cost has three cases.
- **Low end, ≈ US$1.77** (round 3: 1.01 + 0.76). The worker's job memory moves out of web, so web falls to its measured
  134 MiB floor. The new cost is one more interpreter plus the issuer.
- **High end, ≈ US$4.** Web does not shrink at all. The new cost is the worker's full steady
  footprint (US$2.97) plus the issuer (0.76), plus at most ~US$0.3 of CPU (a daily cycle
  measures ≈ 2.4–2.5 vCPU-min).
- **Upper bound, US$27.** The worker is saturated all month at peak RSS (26.19–26.49) plus the
  issuer.

**Expected: ≈ US$1.77–4/month (≈ CA$2.51–5.70). Upper bound: US$27/month.**

Still not measured, which is why this is a range:
- web *with* the embedded worker under the same load
- cadence CPU at real daily load
- connection-pool growth over days

## Suites

Environment: `/tmp/venv` from `requirements.lock` + `requirements-test.lock`, and PostgreSQL 16
(`/usr/lib/postgresql/16`, apt), using the `_disposable_cluster` pattern.

**Run 1, on `99e6d24` (all code fixes; tree clean at start).** Command:
`JOBS=4 SUITE_REGISTRY=0 SUITES="…31 suites…" PY=/tmp/venv/bin/python bash run_tests.sh`.
Record: `artifacts/suite_runs/20261118T163624Z-3976.json`.
**TOTAL PASSING: 348 ; suites failing: 0** (1609 s).
- The suites are round 1's 29 plus the two other suites that boot `worker_entry`
  (`test_rc1_auth`, `test_cert_claude_independence`).
- The runner warned that HEAD moved to `c1743d9` during the run. That commit is test-only (the
  stronger L4 PG test), so it was re-run cleanly in run 2.

**Run 2, on `c1743d9` (tree clean).** Suites: `test_ws4_7_issuer`, `test_ws4_7_postgres`.
Record: `artifacts/suite_runs/20261118T170323Z-6941.json`.
**TOTAL PASSING: 37 ; suites failing: 0** (33 + 4).

| Suite | OK | FAIL |
|---|---|---|
| `test_acceptance_gates` | 23 | 0 |
| `test_cert_claude_independence` | 4 | 0 |
| `test_codex_v0_postgres` | 1 | 0 |
| `test_compiler` | 9 | 0 |
| `test_continuity` | 15 | 0 |
| `test_continuity_cleanup` | 3 | 0 |
| `test_opus2_owner_queue_races` | 14 | 0 |
| `test_rc1_auth` | 11 | 0 |
| `test_reverse` | 18 | 0 |
| `test_twin` | 8 | 0 |
| `test_v11_wiring` | 14 | 0 |
| `test_w3_priv_continuity` | 3 | 0 |
| `test_w4_agents_secfix` | 13 | 0 |
| `test_w4_auditfix_migrate` | 2 | 0 |
| `test_w4_close5_rows4` | 2 | 0 |
| `test_w4_fm2_log_secret_guard` | 8 | 0 |
| `test_w4_fmbatch2_hq_job_process` | 3 | 0 |
| `test_w4_pl_continuity` | 3 | 0 |
| `test_ws4_0_owner_grant_keys` | 17 | 0 |
| `test_ws4_1_grant_ledger_extra_actions` | 10 | 0 |
| `test_ws4_3_owner_signing_flow` | 11 | 0 |
| `test_ws4_7_issuer` | 33 (was 27; +6 new) | 0 |
| `test_ws4_7_postgres` | 4 (was 3; +1 new) | 0 |
| `test_ws4_boundary` | 16 | 0 |
| `test_ws4_g_shadow` | 18 | 0 |
| `test_ws4_hold_cards` | 8 | 0 |
| `test_ws4_issue_time_readers` | 11 | 0 |
| `test_ws4_issuer_shadow` | 9 | 0 |
| `test_ws4_policy_object` | 25 | 0 |
| `test_ws4_stop` | 20 | 0 |
| `test_ws4_vision_reviewer` | 12 | 0 |

Not run: the other ~884 suites of the full discovery (915 files). The one change with a wide
call path is the `Database.create_all` refactor (same imports, same order, now via
`register_models()`), and every suite above exercises it.

### Test changes that are not new tests (please check none weakens anything)

- `_effective_db` (`test_ws4_7_issuer`) and `_policy` (`test_ws4_7_postgres`) now bind a
  name-verified shop (`_bind_shop`). Without that, L3 correctly voids every grant at use, since
  no shop is bound. No assertion was removed or relaxed.
- No test was skipped, deleted or loosened.

## OWNER ACTION REQUIRED

There is nothing new; the batch in `REVIEW_REQUEST.md` stands, with these changes.
- Its cost is now **≈ US$1.77–4/month expected, US$27/month upper bound**.
- After the services exist and before any policy is activated, the owner runs the one-time
  catalogue check (L1) in `WS4_7_MODE_T.md`: CA$0, ~5 min. Until then, Mode T is not
  enabled.

---

# Round 3: fixes for the review of `259555fe`

- **Branch:** `eng/ws4-7-mode-t-fix`. **Code SHA:** `dd67d90`. The final SHA is the commit
  that adds this section (documentation and one measurement JSON only; `4ccf1fa` plus the commit that records these results).
- **Nothing is live.** No deploy, no Railway change, no secret, no Etsy call, no spend.

| Finding | Fix | Regression test | On 259555fe |
|---|---|---|---|
| **MEDIUM** `_ads_jobs` counted only PENDING and RUNNING. In this queue FAILED means "will retry" (`queue/durable.py` claims PENDING and FAILED; `release_recovery` counts FAILED as live), so a FAILED `ads.campaign` (attempt 1 of 3) on a lineage product read `PASS 0`. | One shared constant, `core.models.LIVE_JOB_STATUSES = (PENDING, RUNNING, FAILED)`. `standing_issuer._ads_jobs` uses it. `release_recovery.certify_in_flight` and `idle_capacity` now use the same constant (same set as before, so no behaviour change there). | `test_ads_jobs_on_the_release_or_its_standing_lineage_hold_the_grant`: a FAILED `ads.campaign` on a lineage product raises the count (2 → 3). DEAD and CANCELLED rows do not raise it. New: `test_the_issuer_and_the_queue_share_one_live_status_set`. | **Failed:** `{'state': 'PASS', 'value': 2, …}` where 3 was expected. The shared-set test also failed. |
| **LOW** The idle-worker figure (95.8 MiB) came from a 75 s trial with no stored artifact. | `scripts/ws4_7_measure_rss.py --idle` enqueues no `plan.cycle`; everything else is unchanged (PG16, runbook roles, grant requests every 30 s, web `/health`). Run for 360 s: the worker's steady RSS (median of the second half) is **103.0 MiB**, peak 103.1, 0.0030 vCPU. The worker ran only its six boot-seeded one-off jobs, all DONE. Issuer 74.7 MiB; web 132.7 MiB; 12/12 health checks OK. Data: `research/final_build/ws4/ws4_7_rss_measurement_2026-11-18_round3_idle.json`, stored next to the round-2 JSON. The card's low end moves from US$1.75 to **US$1.77** (worker idle row: 0.98 → 1.01). `WS4_7_MODE_T.md`, `REVIEW_REQUEST.md` and the cost card above are updated. | (measurement) | — |
| **LOW** The worker's boot check verified tables only. | `Database.boot_schema` on a non-owner role also compares every registered table's columns with the catalogue. When a column is missing it refuses ("N column(s) do not exist yet (…) … Deploy web (the migration owner) first"), exits 3 and reports `missing_columns`. It never ALTERs. Owner and SQLite paths are unchanged. | PG16 `test_the_worker_role_never_creates_a_table_it_should_not_own`, new tail: the owner drops `jobs.last_error`. `boot_schema("worker")` reports `missing_columns == ['jobs.last_error']`, and `worker_entry.main` as `bl_worker` exits rc 3 with the message. Web's `boot_schema` re-adds the column, then the worker starts with rc 0 and owns nothing. | **Failed:** the worker started with **rc 0** against a table missing a column. (With the `missing_columns` key assertion removed, so the old code could be tested at all.) |

## Round 3 suites

**WS4 run, on `dd67d90` (tree clean at start, HEAD unchanged).** Command:
`JOBS=4 SUITE_REGISTRY=0 SUITES="<13 test_ws4_* suites> test_shadow_rehearsal test_w4_listready test_w4_swarmmetrics test_rc1_auth" PY=/tmp/venv/bin/python bash run_tests.sh`.
Record: `artifacts/suite_runs/20261118T190907Z-1352.json`, 630 s.
The run reported **TOTAL PASSING: 264 ; suites failing: 2**. Every WS4 suite passed:

| Suite | OK | FAIL |
|---|---|---|
| `test_ws4_0_owner_grant_keys` | 17 | 0 |
| `test_ws4_1_grant_ledger_extra_actions` | 10 | 0 |
| `test_ws4_3_owner_signing_flow` | 11 | 0 |
| `test_ws4_7_issuer` | 34 (+1 new) | 0 |
| `test_ws4_7_postgres` (disposable PG16 cluster) | 4 | 0 |
| `test_ws4_boundary` | 16 | 0 |
| `test_ws4_g_shadow` | 18 | 0 |
| `test_ws4_hold_cards` | 8 | 0 |
| `test_ws4_issue_time_readers` | 11 | 0 |
| `test_ws4_issuer_shadow` | 9 | 0 |
| `test_ws4_policy_object` | 25 | 0 |
| `test_ws4_stop` | 20 | 0 |
| `test_ws4_vision_reviewer` | 12 | 0 |
| `test_rc1_auth` (boots `worker_entry`) | 11 | 0 |
| `test_w4_swarmmetrics` (`idle_capacity`) | 8 | 0 |
| `test_w4_listready` (`release_recovery`) | 40 | **1** (also fails on 259555fe) |
| `test_shadow_rehearsal` (`release_recovery`) | 10 | **1** (also fails on 259555fe) |

The two failures are in suites I added because `release_recovery` now imports the shared
constant. Neither failure is in a file this round changed:
- `test_w4_listready::test_f8_every_etsy_write_call_site_is_classified…`: "unclassified Etsy
  write call sites: [('app/command_center/approvals.py', '_standing_policy')]". The call site
  comes from earlier WS4 work, and the test **fails identically on `259555fe`** (re-run in a
  clean worktree).
- `test_shadow_rehearsal::test_approval_reaches_the_simulated_publish…`: owner_publication_grant
  is BLOCKED by "an owner grant or rebase is signed only inside the owner's Command Center
  request …". It **fails identically on `259555fe`** (same clean worktree), so it is not caused by this round.
- Both are pre-existing and left as they are; they belong outside WS4-7 round 3.

**`test_cert_claude_independence` alone** (nothing else running): run on `4ccf1fa`, whose code is identical to `dd67d90`. Started 2026-11-18T19:30:40Z and finished 19:46:20Z with rc 0: **4/4 passed in 934 s**.
- `test_the_runtime_import_closure_names_no_claude_session_artefact`: OK
- `test_the_deployed_image_and_start_command_carry_no_session_state`: OK
- `test_production_start_command_runs_kills_and_resumes_without_this_session`: OK
- `test_split_services_do_the_same_work_as_separate_processes`: OK
