# Review request: WS4-7 Mode T, fixes for the review of fa3a09e9

- **Branch:** `eng/ws4-7-mode-t-fix`, from `fa3a09e9` (`opus2/ws4-7-mode-t`)
- **Final SHA:** see the last commit on the branch (the commit that adds this file)
- **Nothing is live.** No deploy, no Railway change, no secret, no Etsy call, no spend.
  - `deployment_mode()` with no database is still `S`.
  - With a database it is `T` only on agreeing, fresh reports. On PostgreSQL it now also needs
    the runbook's real privilege separation, so it cannot read `T` before the owner applies
    the runbook.
  - Activation still needs the owner. Stage A public activation is untouched.

## Findings: fix and test

Each regression test was run against the fa3a09e9 sources (a worktree with the old `src/`
and the new tests) and **failed there**. Each one passes now.

| Finding | Fix | Regression test (file → test) | On fa3a09e9 |
|---|---|---|---|
| **HIGH-1** Owner pace limits ignored. `read_facts` reported 0/0/0 as a fact, and `issue()` enforced only 3/day and 2 outstanding. | `standing_grants.pace` / `pace_facts` read today, 7 days, outstanding and minutes-since-last from the grant store (every policy; an expired unused grant still used its slot). `issue()` enforces **min(signed policy, code ceiling)** on all four. The pace is re-read in the **same transaction** as the slot insert, under one store-wide lock (`pg_advisory_xact_lock` on PostgreSQL, `BEGIN IMMEDIATE` on SQLite), and the grant is signed inside that transaction. `read_facts` reads the store. | `test_ws4_7_issuer` → `test_the_owner_pace_limits_are_enforced_not_only_the_code_ceilings` (the reviewer's probe: 2/day, 1 outstanding, 180 min); `test_the_seven_day_limit_counts_every_grant_in_the_window`; `test_read_facts_reports_the_grant_store_not_zero`; `test_concurrent_issuers_cannot_both_take_the_last_grant` | 2nd grant issued 1 min later; 7-day not enforced; `read_facts` had no store |
| **HIGH-2** The worker's key report always said "no key", because the scrub ran before the report. | `mark_job_process` records presence **before** the scrub. `process_report` reads the recorded fact, the live environment and `/proc/self/environ`. A non-issuer process that held the key → Mode S + **P1** `standing_grant_issuer_key_exposed:<component>`. | `test_ws4_7_issuer` → `test_a_worker_booted_with_the_issuer_key_reports_it_and_opens_a_p1` (boots the real `worker_entry.main` in a subprocess with the key set); `test_a_clean_worker_boot_reports_no_key_and_no_incident` | report `issuer_signing_present: False` |
| **M-3a** `consume()` trusted the unsigned `expires_at` column. | `consume()` checks the **signed** `expires_at` and `not_before` (30 s skew tolerance on `not_before` only). | `test_consume_trusts_the_signed_expiry_not_the_column` (column pushed +3 days, consumed 2 days late) | accepted |
| **M-3b** Policy state was not re-checked at use. | `consume()` re-reads `SP.effective`. A grant is void unless the policy is EFFECTIVE with the same approval row and seal; a suspended, revoked or replaced policy, or Mode S, voids it. | `test_a_suspended_or_revoked_policy_voids_its_outstanding_grants` | consumed |
| **M-3c** With the runbook's column grant, the worker could reset `consumed_at` and consume again. | `standing_grants_write_once` trigger (plpgsql on PostgreSQL, a `RAISE(ABORT)` trigger on SQLite). It refuses any UPDATE of a consumed grant, and any UPDATE that leaves a grant unconsumed. It is created with the table (`after_create`); `install_guards` (from `Database.create_all`, run by the migration owner) adds it to an older table. `consume()` turns a database refusal into a `GrantRefused`. | `test_ws4_7_issuer` → `test_consumption_is_write_once_in_the_database`; **PG16** `test_ws4_7_postgres` → `test_the_worker_role_cannot_reset_a_consumed_grant_or_mint_one` (as `bl_worker`) | the reset succeeded |
| **M-3d** Role separation compared names only. | Each process reports its role's **real write powers** from the catalogue: `rolsuper`, membership of the tables' owner, INSERT/DELETE/TRUNCATE/TRIGGER, and UPDATE on any signed column. The issuer's **signed** heartbeat also reads the role the worker names. On PostgreSQL, Mode T needs the worker to have none of these powers and the issuer only its two INSERTs. | `test_role_separation_is_judged_by_privileges_not_names` (6 cases, catalogue stubbed); **PG16** `test_role_separation_is_read_from_the_catalogue` (worker on `postgres` superuser) | `{'mode': 'T', 'db_roles_separated': True}` |
| **M-4** The stop-watch lineage was a stub that returned empty. | `standing_stop.lineage` reads every grant issued under any approval of the policy, used or not. A grant whose approval row cannot be read also counts (fail closed). It also returns those releases' Etsy listing ids. Wiring lineage would have made `_spend` (UNKNOWN for any non-empty lineage) suspend the policy on the first grant. So `_spend` is now a real join: listing fees on a lineage listing or product in 30 days over min(policy cap, code ceiling), or any ads cost, fails. | `test_ws4_stop` → `test_the_lineage_is_read_from_the_grant_store` (a defect on a granted product now stops the policy with no lineage passed in); `test_spend_under_a_non_empty_lineage_is_read_from_the_cost_rows` | lineage empty; spend UNKNOWN |
| **M-5** Issuer wedge: a permission error on `owner_actions` aborted the pass, and the issuer could not create its tables. | `answer()` turns **any** failure into a recorded HELD answer, and logs if even that write fails, so the pass continues. The runbook grants the issuer INSERT/UPDATE on `owner_actions` and `incidents`. `ensure_tables` only **checks** from a non-owner role and refuses instead of creating; the migration owner creates the tables in `Database.create_all`. | `test_an_unexpected_error_on_one_request_is_a_recorded_refusal_and_the_pass_goes_on`; **PG16** `test_the_issuer_role_answers_an_out_of_policy_request_and_the_next` (HOLD card written by `bl_issuer`, next request answered) | `ProgrammingError` escaped `tick`; PG: `permission denied for table owner_actions` |
| **LOW** Heartbeat freshness came from the unsigned row time. | Freshness is the issuer's **signed** `at`, so a replayed old heartbeat is stale. A report dated after now is refused. | `test_issuer_freshness_is_its_signed_time_and_clock_skew_is_refused` | replay read Mode T |
| **LOW** No ±30 s clock-skew refusal. | The issuer heartbeat signs `clock_skew_s` (process clock minus database clock). Mode S if the skew is over 30 s, and `issue()` refuses on its own reading. | same test (skew 45 s) | Mode T |
| **LOW** Request job id was not validated. | `job_refusal`: the job must exist, be `store.publish`, be PENDING or RUNNING, and be for that exact slug@version. | `test_the_request_job_must_be_a_live_publish_job_for_that_release` | "no job 10" was issued |
| **LOW** Runbook privilege gaps. | `standing_grants.runbook_sql()` is the single source, applied by the PG suite. The worker keeps DML everywhere except the grant store, and keeps CREATE in `public`: the cost run found `radar.scan` dying on `radar_concepts` without it. Default privileges cover later tables. Doc: `brambleloop/research/final_build/ws4/WS4_7_MODE_T.md`. | the PG16 suite applies it; the cost run's worker ran 16 job types as `bl_worker` with 0 permission errors | — |
| **LOW** The worker can forge web reports. | **Not fixed; documented as an honest limit.** Web/worker reports are unsigned rows. Mode T is a check against misconfiguration. The boundary is the key plus the database privileges, which bound the worker whatever it reports. | — | — |

### Test changes that are not new tests (please check none weakens anything)

- **Code-ceiling tests now use a policy at the ceilings** (`AT_CEILINGS`: 3/day, 10/7d, 0 min, 2 outstanding). `test_outstanding_and_daily_limits…` and `test_an_expired_or_tampered…` previously passed only because the policy's own 1-outstanding / 180-min limits were ignored (HIGH-1). The 4th-grant refusal now reads `grants_today: 3 issued`; the database's slot-4 refusal is still asserted separately.
- **The tamper test** now first asserts that the write-once trigger refuses the edit. It then drops the trigger (an owner-level attacker) and still asserts that the signature check refuses.
- **The expiry assertion** now matches `"expired"`; the message is `… expired at … (signed)`.
- **The name-only separation test** now needs privilege readings for `T`. Names alone are the bug.
- **`test_spend_under_a_non_empty_lineage_is_unknown_and_stops` was replaced** by the two-sided reader test above. A reader failure is still UNKNOWN and still stops; that is asserted.
- **Helpers:** `all_pass(..., **_kw)` in `test_ws4_issuer_shadow` / `test_ws4_hold_cards` (`read_facts` takes `now`). `_job()` creates the `store.publish` job a grant binds to.

## Suites

Command: `JOBS=4 SUITE_REGISTRY=0 SUITES="…" PY=/tmp/venv/bin/python bash run_tests.sh`, run on
the final code. venv from `requirements.txt` + `requirements-test.lock`. The test lock is
needed for the starlette TestClient: without it, `test_w4_agents_secfix`,
`test_ws4_3_owner_signing_flow` and `test_w4_close5_rows4` fail on a missing `httpx2`, an
environment problem only.

Run on code SHA `d0725222` (clean tree), record `artifacts/suite_runs/20261118T144204Z-8693.json`: **TOTAL PASSING: 326 ; suites failing: 0** (29 suites, 1745 s). Per suite (each suite's own `OK` lines; they sum to 326):

| Suite | OK | FAIL |
|---|---|---|
| `test_acceptance_gates` | 23 | 0 |
| `test_codex_v0_postgres` | 1 | 0 |
| `test_compiler` | 9 | 0 |
| `test_continuity` | 15 | 0 |
| `test_continuity_cleanup` | 3 | 0 |
| `test_opus2_owner_queue_races` | 14 | 0 |
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
| `test_ws4_7_issuer` | 27 | 0 |
| `test_ws4_7_postgres` | 3 | 0 |
| `test_ws4_boundary` | 16 | 0 |
| `test_ws4_g_shadow` | 18 | 0 |
| `test_ws4_hold_cards` | 8 | 0 |
| `test_ws4_issue_time_readers` | 11 | 0 |
| `test_ws4_issuer_shadow` | 9 | 0 |
| `test_ws4_policy_object` | 25 | 0 |
| `test_ws4_stop` | 20 | 0 |
| `test_ws4_vision_reviewer` | 12 | 0 |

**PostgreSQL:** real PG16 (`/usr/lib/postgresql/16`), with a throwaway loopback cluster per
run. `test_ws4_7_postgres` 3/3 and `test_codex_v0_postgres` pass. On fa3a09e9, all 3 new PG
tests fail as the reviewer described.

## Cost: owner approval needed before any Railway change

Measured by `brambleloop/scripts/ws4_7_measure_rss.py` (re-runnable), over 720 s on PG16 under
the runbook roles:
- **Issuer:** runs as `bl_issuer` with a 10 s pass and a grant request every 30 s (24 answered).
- **Worker:** runs as `bl_worker` and gets a `plan.cycle` every 3 min. That is 203 jobs across
  16 types through the whole offline pipeline: radar, CIR, certify, listing, SEO, pricing,
  image production, assets, launch plan, then `store.publish`, which was refused in SHADOW.

No provider, network or spend was involved. The figures are VmRSS of the process tree, sampled
every 5 s. The summary is in `brambleloop/research/final_build/ws4/ws4_7_rss_measurement_2026-11-18.json`.
Pricing: Railway memory ~US$10/GB-month, vCPU ~US$20/vCPU-month.

| Process | Peak RSS | Steady RSS | Avg vCPU | US$/month | CA$/month (1.4154) |
|---|---|---|---|---|---|
| policy-issuer | 75.0 MiB | 74.9 MiB | 0.0016 | **0.76** | 1.08 |
| worker, idle (no `plan.cycle`, 360 s, round 3; `brambleloop/research/final_build/ws4/ws4_7_rss_measurement_2026-11-18_round3_idle.json`) | 103.1 MiB | 103.0 MiB | 0.0030 | **1.01** | 1.42 |
| worker, saturated: steady RSS | 809.8 MiB | 304.0 MiB | 0.914 | **21.25** | 30.08 |
| worker, saturated: peak RSS all month | 809.8 MiB | — | 0.914 | **26.19** | 37.07 |

(The reviewer measured the issuer at 80.7 MiB; this run measured 75.0 MiB peak.)

**How to read the worker rows:**
- The worker's jobs run inside web today, as the embedded worker, so splitting them out
  **moves** most of that memory and CPU rather than adding it.
- The new cost is a **range, ≈ US$1.77–4/month expected, US$27 upper bound** (round 2 measured
  web with the worker removed at 134.1 MiB; derivation in `WS4_7_MODE_T.md` "Cost" and
  `brambleloop/research/final_build/w6/review_requests/ws4_7_round2.md`).
- The saturated rows are an upper bound. A cycle every 3 minutes keeps the worker busy all the
  time; production runs one daily cycle plus the cadences.
- Web's RSS with the worker removed: measured in round 2 (134.1 MiB). Web *with* the embedded
  worker under the same load is still not measured, hence the range.

### The Railway setup the owner would create (names only, no values)

**1. `policy-issuer` (new service; same repo and Dockerfile)**
- Start command: `python -m brambleloop.app.issuer_entry`
- 1 replica. No public domain, no healthcheck path: it has no HTTP listener.
- Variables:
  - `DATABASE_URL` (the `bl_issuer` connection)
  - `BRAMBLELOOP_GRANT_ISSUER_KEY`
  - `BRAMBLELOOP_GRANT_ISSUER_VERIFY_KEY`
  - `BRAMBLELOOP_POLICY_VERIFY_KEY`
  - `BRAMBLELOOP_EMBEDDED_WORKER=0`
  - optional: `BRAMBLELOOP_ISSUER_INTERVAL`, `BRAMBLELOOP_LOG_LEVEL`
- **Must not have:** any `ETSY_*`, `BRAMBLELOOP_POLICY_SIGNING_KEY`, or `BRAMBLELOOP_OWNER_GRANT_SIGNING_KEY`.

**2. `worker` (new service; same repo and Dockerfile)**
- Start command: `python -m brambleloop.app.worker_entry`
- No public domain.
- Variables:
  - `DATABASE_URL` (the `bl_worker` connection)
  - `BRAMBLELOOP_GRANT_ISSUER_VERIFY_KEY`
  - `BRAMBLELOOP_POLICY_VERIFY_KEY`
  - `BRAMBLELOOP_EMBEDDED_WORKER=0`
  - the variables web's embedded worker uses today (provider and Etsy settings)
- **Must not have:** `BRAMBLELOOP_GRANT_ISSUER_KEY`, or any signing key. If the issuer key is
  set, the worker now reports it, raises a P1 and holds Mode S.

**3. `web` (existing service)**
- Set `BRAMBLELOOP_EMBEDDED_WORKER=0`.
- Add `BRAMBLELOOP_GRANT_ISSUER_VERIFY_KEY`.
- Keep the owner `DATABASE_URL`: web is the migration owner.

**Then** run `runbook_sql` in the Postgres query tab, as web's role, after web has started on
this release. It is printed in `WS4_7_MODE_T.md`. **Deploy order on every release: web, then
worker, then policy-issuer** (round 2: a worker on `bl_worker` refuses to start while a table
is missing, and never creates one). Before Mode T is ever enabled, the owner runs the one-time
catalogue check of the worker's real role in `WS4_7_MODE_T.md`.

## OWNER ACTION REQUIRED (batched; nothing is blocked on it today)

| Action | Why | Max cost | Minutes | If it waits |
|---|---|---|---|---|
| Approve the Mode T spend: the `policy-issuer` service, and splitting `worker` out of web | Mode T is the only path to standing issuance. | ≈ US$1.77–4/month expected; US$27/month upper bound (worker saturated all month) | 0 to approve | No standing policy can be activated. Per-product approval continues as today. |
| After approval and integration: create the services, set the variables and run the runbook | The database privileges are what bound the worker. | CA$0 beyond the above | ~30 | Same as above. |
