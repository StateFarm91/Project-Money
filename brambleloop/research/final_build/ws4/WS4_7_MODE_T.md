# WS4-7: Mode T, the policy-issuer service (S3 of Main 6953884261)

Status: **CODE BUILT; review of fa3a09e9 and the round-2 review of 91ee7f50 fixed on
`eng/ws4-7-mode-t-fix`** (see `REVIEW_REQUEST.md` and
`research/final_build/w6/review_requests/ws4_7_round2.md`). It is not integrated, deployed or running. No Railway setting
was changed. No standing policy is active, and none can be activated until the owner approves
this service's spend and activates a policy after a MET G-SHADOW reading.

## What it is

- **`app/issuer_entry.py`**: its own Railway service. It has no HTTP listener and no inbound
  port. Under the `policy_issuer` lease it writes a signed heartbeat about every 60 s and
  answers `policy.grant_requested` rows. A second replica idles. It refuses to start if job
  handlers are embedded, or if it holds Etsy credentials.
- **`ops/standing_grants.py`**: the grant store and its rules.
  - It holds the `standing_grants` and `standing_grant_slots` tables.
  - Only the issuer process signs (Ed25519 under `BRAMBLELOOP_GRANT_ISSUER_KEY`).
  - A grant is single use, bound to one job, expires after 15 min, and only 2 can be
    outstanding.
  - The database itself refuses a 4th slot of a day, and a second open grant for a release.
- **`standing_policy.deployment_mode(db)`**: reads Mode T only when three latest reports agree:
  the issuer's signed heartbeat, the worker's boot report and the web startup report.
  - Fingerprints only; no key leaves a process.
  - The worker must hold the issuer verify key, never the signing key.
  - Web must not embed the worker.
  - The roles must differ once the runbook below is applied.
  - A stale (>5 min), forged or disagreeing report reads Mode S.

## Cost: a range, from measurements only (round-2 L5)

Railway bills used resources per minute: **US$10 per GiB-month of memory and US$20 per
vCPU-month** (docs.railway.com pricing, read 2026-11-17). Two runs of
`scripts/ws4_7_measure_rss.py` (720 s each, PG16, runbook roles; VmRSS of each process tree
every 5 s) plus the reviewer's own measurement of 91ee7f50:

- Run 1 (`ws4_7_rss_measurement_2026-11-18.json`): issuer and worker.
- Run 2 (`ws4_7_rss_measurement_2026-11-18_round2.json`): issuer, worker **and web with the
  worker removed** (`uvicorn brambleloop.app.main:app`, `BRAMBLELOOP_EMBEDDED_WORKER=0`, as
  the migration owner, `/health` read every 30 s: 24/24 OK).
- Load: a `plan.cycle` every 3 min (4 cycles, ~200 jobs through the offline pipeline,
  `store.publish` refused in SHADOW) and a grant request every 30 s (24 answered, HELD).

| Process | Measured RSS | Avg vCPU | US$/month |
|---|---|---|---|
| policy-issuer | **~70 MiB** (reviewer) to 74.8–75.0 MiB (runs 1–2) | 0.0012–0.0016 | 0.71–0.76 |
| worker, idle (empty queue) | 95.8 MiB (75 s trial) | 0.0022 | 0.98 |
| worker, steady after jobs (median, 2nd half) | **~284 MiB** (reviewer) to 291.1–304.0 MiB (runs 2, 1); **~300 MiB** after jobs (reviewer) | — | 2.77–2.97 (memory) |
| worker, saturated (cycle every 3 min) | steady 291–304, peak 809.8–942.7 MiB | 0.86–0.91 | 20.1–26.5 (upper bound) |
| **web, worker removed** (run 2) | **134.1 MiB** (peak = steady) | 0.0015 | 1.34 |

**The new monthly cost, as a range (never one number):**

| Case | What it assumes | US$/month |
|---|---|---|
| **Expected, low** | Splitting the worker out *moves* its job memory out of web: web falls to its measured 134 MiB floor, and the only new memory is one more interpreter (the idle worker, 95.8 MiB) plus the issuer. 0.76 + 0.98 | **≈ 1.75** |
| **Expected, high** | Web does not shrink at all: the worker's whole steady footprint (284–304 MiB) is new, plus the issuer, plus a daily cycle's CPU (measured ≈ 2.4–2.5 vCPU-min per cycle ≈ US$0.04/month) and the cadences (not measured; allowed up to ~US$0.25). 0.76 + 2.97 + ≤ 0.3 | **≈ 4** |
| **Upper bound** | The worker saturated all month with its peak RSS held throughout, plus the issuer. 26.19–26.49 (runs 1–2) + 0.76 | **≈ 27** |

So: **≈ US$1.75–4/month expected (≈ CA$2.50–5.70 at 1.4154), US$27/month upper bound.**

What is still **not** measured (so it is a range, not a point): web's RSS *with* the embedded
worker under the same load (which would say exactly how much moves); the cadence jobs' CPU at a
real daily load; psycopg2 connection-pool growth over days.

## Deploy order and table ownership (round-2 L4)

**Every table belongs to the migration owner, the role web uses.** Web creates every registered
table, the grant store and its write-once trigger on boot (`Database.create_all`). Neither the
worker nor the issuer ever creates a registered table:

- **Worker boot** (`Database.boot_schema("worker")`): on PostgreSQL, if the worker's role is
  not the owner of `jobs` (the migration owner), it only checks that every registered table
  exists. If one is missing it logs `worker refused to start: … Deploy web (the migration
  owner) first` and exits with code 3, having created nothing. Railway restarts it; it starts
  once web has migrated. On a single-role (Mode S) deployment the worker is the owner and
  boots exactly as before.
- **The grant store** (`standing_grants.ensure_tables`): a job or issuer process never creates
  it, whatever its role may do. It refuses instead ("never creates it … Deploy web first").
- **Handler tables** created lazily by a job on first use (e.g. `radar_concepts`) are the only
  tables the worker may own; the default privileges below give web ALL on them. The worker
  owns nothing that bounds it.

**On every release, deploy in this order:**
1. **web** first. Wait until it is healthy (`/health` 200): its boot has created the new
   tables and the trigger, as the owner.
2. **worker** next. If it was deployed first, it refuses to start (exit 3) until step 1 is
   done; nothing needs repair.
3. **policy-issuer** last. It only checks the grant store and refuses while it is missing.

The first time only: run the runbook below after step 1, before steps 2 and 3.

## Owner runbook: database roles (§2.3). Not executed by code.

Revised after review of fa3a09e9 (M-3, M-5, LOW runbook gaps). The statements are generated
by `standing_grants.runbook_sql(owner, issuer_password, worker_password)`, the same text the
PostgreSQL suite (`tests/test_ws4_7_postgres.py`) applies and tests. CA$0, about 10 minutes in
the Railway Postgres query tab, run as the role **web** uses (the migration owner, which
creates every table), **after** web has started once on this release (so the grant store and
its write-once trigger exist).

```sql
CREATE ROLE bl_issuer LOGIN PASSWORD '<new>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE bl_worker LOGIN PASSWORD '<new>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO bl_issuer, bl_worker;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bl_issuer;
GRANT INSERT ON standing_grants, standing_grant_slots, audit_log, ops_runtime_samples, incidents, owner_actions TO bl_issuer;
GRANT UPDATE ON ops_leases, incidents, owner_actions TO bl_issuer;
GRANT INSERT ON ops_leases TO bl_issuer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bl_issuer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bl_worker;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO bl_worker;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES ON standing_grants, standing_grant_slots FROM bl_worker;
GRANT UPDATE (consumed_at, consumed_job_id, consumed_stage) ON standing_grants TO bl_worker;
GRANT CREATE ON SCHEMA public TO bl_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE bl_worker IN SCHEMA public GRANT ALL ON TABLES TO "<web role>";
ALTER DEFAULT PRIVILEGES FOR ROLE bl_worker IN SCHEMA public GRANT SELECT ON TABLES TO bl_issuer;
ALTER DEFAULT PRIVILEGES FOR ROLE bl_worker IN SCHEMA public GRANT ALL ON SEQUENCES TO "<web role>";
ALTER DEFAULT PRIVILEGES FOR ROLE "<web role>" IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bl_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE "<web role>" IN SCHEMA public GRANT SELECT ON TABLES TO bl_issuer;
ALTER DEFAULT PRIVILEGES FOR ROLE "<web role>" IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO bl_issuer, bl_worker;
```

What each part is for:
- **Issuer:** reads everything; writes only grants, slots, its audit rows, its heartbeat, its
  lease, and the HOLD owner card + incident an out-of-policy request becomes (M-5: without
  `owner_actions`, the first out-of-policy request raised a permission error mid-pass).
- **Worker:** keeps the DML it has today on every table except the grant store, where it may
  only mark a grant consumed. The write-once trigger (installed by `Database.create_all`, as
  the migration owner) refuses any UPDATE of a consumed grant or one that leaves it unconsumed,
  so the column grant cannot be used to reset `consumed_at` and consume twice (M-3).
- **Worker CREATE:** several handlers create their own tables on first use (the cost
  measurement found `radar.scan` dying on `radar_concepts` without it). The worker owns only
  what it creates. It never creates a registered table or the grant store (see "Deploy order
  and table ownership"), so it cannot alter, drop or add a trigger to the grant store.

**Mode T reads privileges, not names (M-3).** Each process reports its role's write powers
over the grant store from PostgreSQL's catalogue (superuser, owner membership, table
privileges, UPDATE on any signed column), and the issuer's signed heartbeat also reads the role
the worker names. Mode T needs the worker to have none and the issuer only its two INSERTs; a
worker on the web/superuser role reads Mode S whatever it is called. On PostgreSQL, Mode T is
therefore not reachable until this runbook is applied.

**Honest limits that remain:**
- The worker and web reports are unsigned rows: a compromised worker can write a false web
  report. Mode T is a check against misconfiguration; the boundary is the key and the database
  privileges. (Review L1: accepted while the mode is S.)
- The issuer reads the role the worker *names*; a compromised or misconfigured worker could
  name another role. The worker's actual connection is bound by `bl_worker`'s privileges
  whatever it reports, so the owner checks the real role once (below).

**One-time owner check before Mode T is ever enabled (review L1).** CA$0, about 5 minutes. The
reports are not evidence of which role the worker *really* connects as; the owner checks it
from PostgreSQL's own catalogue, once, after the services exist and before activating any
policy:
1. In Railway, open the **worker** service's variables and confirm the user in its
   `DATABASE_URL` is `bl_worker` (and the issuer's is `bl_issuer`). Do not paste the URL anywhere.
2. In the Postgres query tab (as web's role), with web, worker and issuer running:
   ```sql
   SELECT usename, application_name, client_addr, count(*)
     FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1, 2, 3 ORDER BY 1;
   SELECT rolname, rolsuper, rolcreaterole, rolbypassrls FROM pg_roles
    WHERE rolname IN ('bl_worker', 'bl_issuer');
   SELECT has_table_privilege('bl_worker', 'standing_grants', 'INSERT')  AS w_insert,
          has_table_privilege('bl_worker', 'standing_grants', 'DELETE')  AS w_delete,
          has_column_privilege('bl_worker', 'standing_grants', 'expires_at', 'UPDATE') AS w_exp,
          pg_has_role('bl_worker', (SELECT tableowner FROM pg_tables
                                    WHERE tablename = 'standing_grants'), 'MEMBER') AS w_owner;
   SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tableowner = 'bl_worker';
   ```
   Expected: connections from exactly three roles (web's, which includes this query tab,
   `bl_worker` and `bl_issuer`) and no other; both roles `rolsuper = false`, `rolcreaterole = false`, `rolbypassrls = false`; all
   four privilege columns `false`; the last query lists no grant-store table (only handler
   tables such as `radar_concepts`, or nothing).
3. Stop the worker service for a minute and re-run the first query: the `bl_worker`
   connections disappear. That ties the role to the worker service, not to another process.

If any answer differs, Mode T is not enabled; the report rows alone never suffice.
- If web is not a superuser, `ALTER DEFAULT PRIVILEGES FOR ROLE bl_worker` must be run by a
  member of `bl_worker` (on Railway's default `postgres` superuser this needs nothing more).

## Not in this increment

- **WS4-8:** the use path. `authority_for_publish.resolve`, consume-at-claim inside the
  draft-intent transaction, and the `before_create` binding. `consume()` exists and is tested,
  but nothing in the publish path calls it yet.
- **The bounded public-activation authority:** a separately reviewable increment, off until
  the owner approves that power. Main S3.
- **Chaining SEG rows into a GrantLedger chain:** the issuer writes an `AuditLog` row per
  grant with its seal. Chaining is WS4-10.
