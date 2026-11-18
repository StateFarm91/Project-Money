# WS4-7: Mode T, the policy-issuer service (S3 of Main 6953884261)

Status: **CODE BUILT; review of fa3a09e9 fixed on `eng/ws4-7-mode-t-fix`** (see
`REVIEW_REQUEST.md`). It is not integrated, deployed or running. No Railway setting
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

## Cost (memory-priced, measured)

Railway bills used resources per minute: **US$10 per GB-month of memory and US$20 per
vCPU-month** (docs.railway.com, pricing comparison page, read 2026-11-17).

| Measured on this build (CPython, SQLite) | Figure |
|---|---|
| Peak RSS: idle pass, or a refusal before evaluation | 66.6 MiB |
| Peak RSS upper bound: an in-policy evaluation that loads the CIR compiler and twin, measured with every model imported | 155 MiB |
| CPU per idle pass | 1.9 ms per 60 s ≈ 0.00003 vCPU |

| Monthly | US$ | CA$ (at the assumed 1.4154, core/fx) |
|---|---|---|
| Memory, idle, 66.6 MiB ≈ 0.070 GB | 0.70 | 0.99 |
| Memory, upper bound, 155 MiB ≈ 0.163 GB | 1.63 | 2.30 |
| CPU | < 0.01 | < 0.01 |
| **Total** | **0.70 – 1.63** | **≈ 0.99 – 2.30** |

**What the estimate covers:**
- It adds no resident memory to the existing services. Web and worker each write one report
  row at boot, and nothing stays resident.
- Postgres is the existing database: one more small connection, and two small tables.

**Caveats:**
- The figures are measured on SQLite in this container. Production uses psycopg2 on
  Postgres, which adds a few MiB.
- The owner approves the spend before any service exists. This is the Mode T owner action of
  design §8.

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
  what it creates; it cannot alter, drop or add a trigger to the grant store.

**Mode T reads privileges, not names (M-3).** Each process reports its role's write powers
over the grant store from PostgreSQL's catalogue (superuser, owner membership, table
privileges, UPDATE on any signed column), and the issuer's signed heartbeat also reads the role
the worker names. Mode T needs the worker to have none and the issuer only its two INSERTs; a
worker on the web/superuser role reads Mode S whatever it is called. On PostgreSQL, Mode T is
therefore not reachable until this runbook is applied.

**Honest limits that remain:**
- The worker and web reports are unsigned rows: a compromised worker can write a false web
  report. Mode T is a check against misconfiguration; the boundary is the key and the database
  privileges.
- The issuer reads the role the worker *names*; a compromised worker could name another role.
  The worker's actual connection is bound by `bl_worker`'s privileges whatever it reports.
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
