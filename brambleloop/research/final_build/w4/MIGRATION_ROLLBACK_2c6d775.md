# Production upgrade fcb982d → 2c6d775: migration, backup and rollback proof + morning runbook

Lane W4-MIGRATE. Date 2026-10-11 (UTC). Everything below ran **offline** on a throwaway local
PostgreSQL 16.13 cluster (127.0.0.1:55433, trust auth, since removed). No Railway write, no
deploy, no accept-deploy, no spend, nothing pushed to `claude/repository-setup-nc9x6o` or the
candidate branch. Code under test: detached worktrees at **fcb982d** (production) and
**2c6d775** (release candidate, `claude/final-candidate-2c6d775`), each started with its own
`uvicorn brambleloop.app.main:app --workers 1` (the Railway start command), so schema creation
went through each version's real startup (`Database.create_all()` = `Base.metadata.create_all`
+ `core/migrate.apply`, then agent/benchmark seeding and boot enqueues).

Boot environment (production-like, no secrets): `DATABASE_URL=postgresql://…/prod_sim`,
`BRAMBLELOOP_REQUIRE_POSTGRES=1`, `BRAMBLELOOP_PHASE=shadow`, `BRAMBLELOOP_COMMIT=<sha>`,
`BRAMBLELOOP_EMBEDDED_WORKER=0` (no job execution locally: CPU budget and no credentials),
no `RAILWAY_*` markers except in the one hosted-guard boot (§3.4), no owner-auth variables.

Evidence files: `research/final_build/w4/evidence_MIGRATE/` (scripts + outputs; `$SCRATCH`
stands for the lane's scratch directory).

## Verdict

| Question | Answer | Evidence |
|---|---|---|
| Backup procedure (the staged `db-backup` job's exact commands) produces a restorable dump | **YES** — `BK RESULT OK`, 51/51 tables, 3,516/3,516 rows, per-table content md5 identical, sequences identical | §2 |
| 2c6d775 migrates the fcb982d schema additively | **YES** — 0 dropped/renamed/retyped columns, 0 NOT NULL tightened, 0 constraints added to existing tables; +75 tables, +38 nullable columns, +3 non-unique indexes on `ledger` | §3.1 |
| No data loss | **YES** — 3,516/3,516 pre-existing rows present by primary key; only change to existing rows is the designed, audited `agents.allowed_job_types` reconcile (9 rows) | §3.2 |
| Idempotent on second boot | **YES** — second boot: no `schema.migrated`, no `agents.reconciled`, schema diff 0, `migrate.plan` = `[]` | §3.3 |
| `/health` 200 after migration | **YES** (every boot) | §3 |
| CC login closed without hash | **YES** — `POST /api/cc/auth/login` → 503 `LOGIN_NOT_CONFIGURED`; `/api/cc/auth/status` `login_configured:false` | §3.5 |
| fcb982d runs on the migrated schema (rollback = redeploy code only) | **YES** — boots, `/health` 200, its 138 parameterless GET routes return the **identical** status codes as on the pre-migration DB; writes through its ORM succeed | §4 |
| 2c6d775 deploys today via `ops/deploy.sh` | **NO, not yet** — guard REFUSES: no tracked release record for its tree digest. Needs the release-record commit on top (step C1). If pushed without it, the boot guard forces SHADOW and opens a **P1 that halts publication** | §3.4, §5(c) |
| Rollback via `ops/deploy.sh --rollback-to fcb982d` | **ALLOW** in dry run | §5(e) |

## 1. fcb982d schema + realistic data

1. `fcb982d` booted on an empty DB `prod_sim`: `/health` 200, **51 tables**, 557 columns, 225
   indexes, 66 constraints, 49 sequences; boot enqueued its real boot jobs and seeded 24 agents
   and 8 benchmarks/loops through `Registry.seed_defaults` and `growth.loops.seed`.
2. Seeder `scripts/seed_old.py` (run on fcb982d's code): 2,500 `Registry.audit` rows (unicode
   and JSON details), 400 `JobQueue.enqueue` jobs of which 250 claimed and completed/failed
   through `claim/complete/fail` (25 DEAD), 300 `gateway.routing.record` cost entries (cached and
   uncached), then fcb982d's own ORM metadata filled every remaining table to ≥ 6 rows with
   **every** column populated (type-driven values, FKs to real rows). Result
   (`seed_report.json`): **51/51 tables non-empty, 3,516 rows** (audit_log 2,503, jobs 406,
   cost_entries 300, agents 24, every other table 6–7), 0 insert errors.

Limit (honest): volumes are synthetic and small; production's real row counts and value edge
cases are not reproduced. The real-data rehearsal is the morning `db-backup` run (§5a).

## 2. Backup and restore (validates the staged `db-backup` job)

The staged job's script (`$SCRATCH/bk/backup_script_readable.sh`, identical to `backup.sh`) was
run with only paths changed (`scripts/backup_local.sh`; restore target = a database on the same
local cluster instead of a second `initdb` on :5499). Same commands: `pg_dump --format=custom
--compress=6 --no-owner --no-privileges`, `pg_restore --no-owner --exit-on-error`, per-table
`count(*)` restored vs source. Output (`backup_run.log`):

```
BK server_version 16.13 …            BK pg_dump_version pg_dump (PostgreSQL) 16.13 …
BK file …/brambleloop_prod_20261011T074055Z.dump bytes 255004 sha256 0b903f30…382fe1
BK toc_entries 527
BK restore_ok
BK tables 51 restored_rows 3516 tables_changed_since_snapshot 0
BK RESULT OK …/brambleloop_prod_20261011T074055Z.dump
```

Beyond the job's own counts: a schema + content snapshot (`scripts/snap.py`: every column's
type/nullability/default, every index and constraint, and an md5 over every row of every table)
of source vs restored differs in **nothing** (0 of 12 difference classes), and sequence
positions are identical (`audit_log_id_seq=2503`, `jobs_id_seq=406`, `cost_entries_id_seq=300`,
`ledger_id_seq=6`), so a restored database continues ids without collision.

## 3. Upgrade: 2c6d775 boots on the fcb982d database

### 3.1 Schema change (`cmp_s0_s1.json`)
First 2c6d775 boot: `/health` 200 after ~5 s, `schema.migrated` audit row with 41 changes
(38 `ADD COLUMN` + 3 `CREATE INDEX`); `create_all` and the lane modules created 75 new tables
(e.g. `cc_*`, `learn_*`, `acct_*`, `draft_creation_intents`, `orders`, `customers`,
`paid_call_records`, `ops_leases`).

| Class | Count |
|---|---|
| dropped tables / columns | **0 / 0** |
| retyped columns / NOT NULL tightened | **0 / 0** |
| dropped indexes / constraints | **0 / 0** |
| constraints added to a pre-existing table | **0** |
| added columns on pre-existing tables | 38, **all nullable** (artefact_provenance 12, ledger 8, owner_actions 6, cost_entries 4, model_identities 2, teardown_findings 2, benchmarks, config_versions, growth_loops, jobs.lease_token 1 each) |
| indexes added on pre-existing tables | 3, non-unique (`ix_ledger_external_id`, `ix_ledger_reconciliation_state`, `ix_ledger_source`) |
| new tables | 75 (126 total) |

Literal model defaults are backfilled on existing rows (e.g. legacy `ledger` rows →
`basis='unknown'`, `fees_basis='unknown'`, `reconciliation_state='unreconciled'`,
`currency='CAD'`; `owner_actions.state='open'`, `max_cost_basis='stated'`): legacy money is
marked unmeasured, never promoted to measured. `audit_log` (the largest production table) gains
no column, so no large-table rewrite.

### 3.2 Data preservation (`rowdiff_pre_vs_migrated.json`)
Row-by-row against the restored pre-migration copy, by primary key, over every original column:
**3,516 rows compared, 0 missing, 9 changed — all `agents.allowed_job_types`**, which is
`Registry.seed_defaults` widening the 9 existing agents' permissions for 2c6d775's job types
(designed behaviour, written to `audit_log` as `agents.reconciled`). Row-count changes are
inserts only: agents +5 (new agents, e.g. `learn`), audit_log +4, jobs +5 (boot jobs),
owner_actions +1 (Laura voice-selection seed).

### 3.3 Idempotency (`cmp_boot1_boot2.json`)
Second 2c6d775 boot: `/health` 200; audit rows written = `release.boot_verdict` +
`runtime.started` only (no `schema.migrated`, no `agents.reconciled`); schema snapshot diff vs
after-boot-1 = 0 in every class; boot jobs reported `duplicate`; `core.migrate.plan(engine)` = `[]`.

### 3.4 Boot guard on the hosting platform (finding — affects the runbook)
Boot 3 with `RAILWAY_ENVIRONMENT=production` and `RAILWAY_GIT_COMMIT_SHA=2c6d775…`:
`/api/status.boot_guard = {enforced: true, ok: false, action: "forced_shadow", reasons: ["no
committed release record names this build's tree digest"], tree_sha256: 30a4dc93…cea}` and an
`incidents` row `P1 release.unproven_build`, **`halts_publication = true`**. `/health` stays 200.
`DRY_RUN=1 ops/deploy.sh --deployed fcb982d…` on 2c6d775 → **REFUSE** for the same reason
(`brambleloop/release/` holds only `RELEASE_3967f40….json`). So the release-record commit
(§5c step C1) is required before promotion; the expected deployable tree digest of 2c6d775 is
**`30a4dc9314ceaf6c9ed6c841e098355e208c6a8cdd99eee5278dd547541c8cea`** (`src/**` without
bytecode + `requirements.lock`; a release-record commit on top does not change it).

### 3.5 Command Center auth closed by default
With no owner-auth variables: `GET /cc/` 200 (static shell), `GET /api/cc/auth/status` 200
`{"authenticated":false,"login_configured":false,"totp_required":false,…}`, `POST
/api/cc/auth/login` → **503 `LOGIN_NOT_CONFIGURED`**, `GET /api/cc/company` and `/api/cc/money`
→ **503 `OPS_UNCONFIGURED`** ("BRAMBLELOOP_OPS_TOKEN is not configured, so the command center is
closed"). So the CC needs `BRAMBLELOOP_OPS_TOKEN` present as well as the passphrase hash.

## 4. Rollback: fcb982d on the migrated database

1. fcb982d booted on the migrated `prod_sim` (126 tables): `/health` 200 in ~3 s, startup clean.
2. Every parameterless GET route of fcb982d (138) swept: **132×200, 3×500, 3×503 — identical,
   route for route, to fcb982d on the pre-migration copy** (`old_pre_sweep.txt` vs
   `old_rollback_sweep.txt`). The three 500s (`/api/console`, `/api/culture`, `/api/learning`)
   are synthetic seed values (`KeyError: 'seed-learning_observations-domain-0'`, `Invalid
   isoformat string`), present before migration too; the 503s are unconfigured credentials.
3. Writes through fcb982d during the rollback window (`scripts/rollback_window.py`): audit row,
   enqueue/claim/complete a job, a cost entry, a `ledger` row, an `owner_actions` row, a
   `listings` row, and full ORM reads of every pre-existing table that gained columns — all
   succeeded (`rollback_window_out.json`).

Consequences to know (all observed):
- Rows fcb982d writes leave the new columns **NULL** (no server defaults): e.g. ledger id 7
  `basis/fees_basis/reconciliation_state/currency/source` all NULL; owner_actions id 8 `state`
  NULL. After roll-forward, 2c6d775 reads them without error (all 126 mapped classes load,
  3,862 rows, 0 errors; revenue reading `UNMEASURED`), and a 194-path GET sweep is identical with
  and without these rows (`new_mc_sweep.txt` = `new_rf_sweep.txt`). The migration does **not**
  re-backfill them (it only backfills when it adds a column), so treat window rows as
  unknown provenance.
- fcb982d's boot reconciles `agents.allowed_job_types` **back** (narrows; `agents.reconciled`
  audit row); 2c6d775's next boot widens them again. Agents added by 2c6d775 (e.g. `learn`) stay.
- **Pending jobs of 2c6d775-only job types are dead-lettered by fcb982d's worker** (no retry):
  job 413 `ops.slo` → `DEAD`, `permission denied: agent 'orchestrator' may not run 'ops.slo'`.
  The same applies, as `no handler registered`, during the Railway rolling overlap. After
  roll-forward, re-queue them (`JobQueue.requeue_dead(job_types=[…])`) or let cadences re-enqueue.
- New tables (e.g. `draft_creation_intents`, `cc_*`) are untouched by fcb982d.

### 4.1 Restore-from-backup (only if a code-only rollback is not enough)
Tested on a copy of the migrated DB:
- **Do not** `pg_restore --clean` into the migrated database. It fails (`cannot drop constraint
  support_cases_pkey … orders_support_case_id_fkey depends on it` — a 2c6d775 table references a
  fcb982d table) and, without `--single-transaction`, leaves the database **half-stripped**
  (174 indexes and 15 constraints dropped before the error). With `--single-transaction` the
  failure is atomic (0 changes) but still does not restore.
- **Works:** empty the schema, then restore in one transaction:
  `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` then
  `pg_restore --no-owner --exit-on-error --single-transaction -d <db> <dump>` → schema and every
  row identical to the pre-migration state (0 differences; 3,516/3,516 rows by PK), and fcb982d
  boots on it with `/health` 200. Safer still on Railway: restore into a **new** Postgres service
  and repoint `DATABASE_URL`, keeping the migrated database intact for forensics.
- A restore loses every write made after the dump. It is never needed for a plain code rollback.

### 4.2 Environment note
At 07:46:31Z the local cluster PANICked (`could not open … pg_control: Permission denied`)
because the sandbox reset `/tmp/claude-0` to mode 700; it was moved to `/var/tmp`, recovered
cleanly (redo done), all data intact (verified), and the one sweep that overlapped was re-run.
Not an application finding.

## 5. Morning runbook (owner + integrator), in order

Times UTC. Production URL `https://brambleloop-os-production.up.railway.app` (`$PROD`).

### (a) Database backup — owner clicks Deploy on `db-backup`
1. Railway → project → service **db-backup** → review the staged change → **Deploy**.
   (Owner action; no cost beyond a few minutes of compute and the volume already staged.)
2. Railway → db-backup → **Deployments** → latest → **View logs**. Expect, in order:
   - `BK server_version <N>` and `BK pg_dump_version pg_dump (PostgreSQL) <M>` with **M ≥ N's
     major** (an older pg_dump aborts on server-version mismatch → `BK RESULT FAIL pg_dump`).
   - `BK file /backup/brambleloop_prod_<TS>.dump bytes <n> sha256 <h>` — n > 0; note `<h>`.
   - `BK toc_entries <k>` — locally 527 for the 51-table fcb982d schema; production should be of
     the same order (≈ 500+).
   - `BK restore_ok`.
   - `BK tables 51 restored_rows <R> tables_changed_since_snapshot <D>` — **tables must be 51**
     (fcb982d schema; a different number means production is not the schema we tested). `BK
     drift <table> restored=<a> source_now=<b>` lines are **expected** for live-written tables
     (`audit_log`, `jobs`, `cost_entries`, …) with `b ≥ a`; a drift with `b < a`, or on a table
     nothing writes, is not normal — stop and investigate.
   - Final line **`BK RESULT OK /backup/brambleloop_prod_<TS>.dump`**. Any `BK RESULT FAIL …`
     → do not deploy; the reason follows on the same line.
3. Record `<TS>`, bytes, sha256, R and D in `BUILD_STATE.md` before continuing.

### (b) Set the auth variables (owner, before the deploy so it is one rebuild)
Railway → service **brambleloop-os** → **Variables** (see `w4/OWNER_DEPLOY_CHECKLIST.md`):
1. `BRAMBLELOOP_OWNER_PASSPHRASE_HASH` — on the owner's computer in a checkout:
   `cd brambleloop && PYTHONPATH=src python3 -m brambleloop.app.command_center.auth hash`,
   paste only the value after `=`. Never paste the passphrase.
2. `BRAMBLELOOP_OWNER_TOTP_SECRET` — base32 secret also enrolled in the authenticator app.
3. `BRAMBLELOOP_TRUSTED_PROXY_HOPS=1`, `BRAMBLELOOP_PUBLIC_ORIGIN=$PROD`.
4. **Confirm `BRAMBLELOOP_OPS_TOKEN` exists** (name only). Without it every `/api/cc/*` owner
   route answers 503 `OPS_UNCONFIGURED` (§3.5).
5. Confirm `BRAMBLELOOP_PHASE` is unset or `shadow`, and `DATABASE_URL` is bound on web,
   worker and scheduler services.
Do not apply/deploy the variable change separately if the code deploy follows within minutes.

### (c) Promote 2c6d775 via `ops/deploy.sh` (integrator, with the owner's go-ahead)
C1. Release record (prerequisite, currently missing). On a clean checkout of
    `claude/final-candidate-2c6d775` at 2c6d775: a full, clean-tree, zero-failing run of
    `brambleloop/run_tests.sh` (writes `brambleloop/artifacts/suite_runs/<run>.json`, release
    eligible), then
    `python3 ops/deploy_guard.py record --sha 2c6d775e2f897f60b48341bc81962e9e4714ec71`,
    and commit the new `brambleloop/release/RELEASE_2c6d775….json` + `release/suite_runs/…`
    on top (commit **R**). Check: the record's `source_tree_sha256` is `30a4dc93…cea`.
C2. Read production's commit: `python3 ops/deployed_sha.py` → must print `fcb982d57e29…`
    (`<deployed>`). If not, stop: production is not what this proof tested.
C3. Rehearse with R checked out (HEAD = R):
    `DRY_RUN=1 ops/deploy.sh --deployed fcb982d57e291c88d9f78eaa091e90904b6c2cc9`
    → expect `deploy.sh: ALLOW <R> (dry run; nothing pushed)`, exit 0. (Today, at 2c6d775
    itself, it prints REFUSE — §3.4.)
C4. Only after (a) is `BK RESULT OK` and (b) is set:
    `ops/deploy.sh --deployed fcb982d57e291c88d9f78eaa091e90904b6c2cc9`
    — pushes R to `claude/repository-setup-nc9x6o`; Railway builds it (approve the deployment in
    Railway if it is held for approval). Startup migrates in seconds (§3: 41 column/index
    changes + 75 tables); the old container keeps serving on the migrated schema during the
    overlap (§4 proves that is compatible).
C5. After verification (d), append R to `brambleloop/release/DEPLOYED_HISTORY.json` with the
    observed date and evidence, commit, so the next rollback can target it.

### (d) Post-deploy verification checklist
1. **SHA served:** `curl -s $PROD/api/status` → `build.commit` = R (full sha), `build.known:
   true`; `python3 ops/deployed_sha.py` prints R.
2. **Boot guard:** same response `boot_guard.ok: true`, `action: "none"`, `tree_sha256 =
   30a4dc93…cea`. If `forced_shadow` → a P1 `release.unproven_build` incident is open and
   publication is halted: roll back or fix the record.
3. **/health:** `curl -s -o /dev/null -w '%{http_code}' $PROD/health` = 200; body `db: "ok"`,
   `runner.worker_alive: true`, no `boot_enqueues` entry with outcome `error`.
4. **Migration happened once:** audit trail shows one `schema.migrated` (≈41 changes) and one
   `agents.reconciled` at the deploy time; a later restart shows neither.
5. **CC closed then open:** `GET $PROD/api/cc/auth/status` → `login_configured: true`,
   `totp_required: true`; `GET $PROD/api/cc/company` without a session → 401.
6. **Login with TOTP** on the phone at `$PROD/cc/` (passphrase + current 6-digit code) → signed
   in; a wrong code → refused (each refusal is a `cc_security_events` row). Not exercised
   offline: `__Host-` cookies need HTTPS.
7. **Each CC page renders with live data:** Laura, Home, Approvals, Money, Store, Company,
   Completion effort, Operations, Autonomy & Learn, Insights, Notifications, Timeline, Ask
   Company, Account. Check against production facts: Store shows the real listings; Money's
   revenue is `UNMEASURED` (not CA$0) while the order source is gated and spend matches the
   cost ledger; Operations' queue figures agree with `/api/status.queue`; Approvals agrees
   with `/api/status.owner_actions_open`; nothing shows placeholder or seed text. (Page
   rendering itself was not exercised offline: these routes need an owner session.)
8. **Phase shadow:** `GET $PROD/api/owner/phase` with `Authorization: Bearer
   $BRAMBLELOOP_OPS_TOKEN` → effective phase `shadow`; `GET $PROD/api/verify` → shadow check ok.
9. **Queue health 15 min later:** `/api/status.dead_letters` not growing; any DEAD jobs created
   during the rollout overlap with `no handler registered` (old container claiming new job
   types) can be re-queued by job type.

### (e) Rollback command
Code-only rollback (the schema stays; proven in §4):
```sh
python3 ops/deployed_sha.py                 # → <deployed> (R)
DRY_RUN=1 ops/deploy.sh --rollback-to fcb982d --reason "<owner's reason, ≥10 chars>" --deployed <deployed>
ops/deploy.sh --rollback-to fcb982d --reason "<owner's reason, ≥10 chars>" --deployed <deployed>
```
Rehearsed here with `--deployed 2c6d775…`: **ALLOW**, `mode: rollback`, candidate =
a commit on top of the deployed one carrying exactly fcb982d's tree (its sha differs per run).
Then run (d) items 1 and 3 for fcb982d (no boot guard, no CC in fcb982d), record the incident
and reason in `BUILD_STATE.md`, and do not add the rollback commit to `DEPLOYED_HISTORY.json`.
Expect after rollback: agents' permissions narrowed back (audited); jobs of 2c6d775-only types
dead-lettered; rows written in the window carry NULL in the added columns.

Database restore only if data, not code, is the problem: §4.1 (new Postgres service, or
`DROP SCHEMA public CASCADE; CREATE SCHEMA public;` + `pg_restore --no-owner --exit-on-error
--single-transaction`) — never `pg_restore --clean` over the migrated database. Owner decision;
loses writes after the dump.

## 6. What this does not prove
- Real production volumes, values and timings (synthetic 3.5k rows; backfill `UPDATE`s on
  `cost_entries`/`ledger`/`owner_actions`/`artefact_provenance` will take longer on real data
  but touch only those tables, not `audit_log`).
- The Railway Postgres server version, the db-backup image's pg_dump version, and Railway's
  rolling-deploy overlap length (the job prints the first two).
- Job execution (embedded worker off locally), a real TOTP login over HTTPS (`__Host-` cookies
  need TLS), and a run with production's credentials.
