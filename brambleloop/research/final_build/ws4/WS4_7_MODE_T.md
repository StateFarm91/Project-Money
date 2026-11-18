# WS4-7: Mode T, the policy-issuer service (S3 of Main 6953884261)

Status: **CODE BUILT**. It is not reviewed, integrated, deployed or running. No Railway setting
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

This costs CA$0 and takes about 10 minutes in the Railway Postgres query tab, **after** the
issuer service exists.

```sql
CREATE ROLE bl_issuer LOGIN PASSWORD '<new>';   -- the issuer service's DATABASE_URL
CREATE ROLE bl_worker LOGIN PASSWORD '<new>';   -- the worker service's DATABASE_URL
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bl_issuer, bl_worker;
GRANT INSERT ON standing_grants, standing_grant_slots, audit_log, ops_runtime_samples TO bl_issuer;
GRANT INSERT, UPDATE ON ops_leases TO bl_issuer;        -- the issuer's own lease row
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO bl_issuer;
-- the worker keeps its existing grants, except: no INSERT on the two grant tables,
-- and UPDATE only of the consumed_* columns.
REVOKE INSERT, UPDATE, DELETE ON standing_grants, standing_grant_slots FROM bl_worker;
GRANT UPDATE (consumed_at, consumed_job_id, consumed_stage) ON standing_grants TO bl_worker;
```

**Until the roles exist:**
- Key separation still holds: the worker cannot sign.
- `mode_report` says `db_roles_separated: false`.
- The worker could still write evidence rows the issuer reads. This is design §6 T1, an
  honest limit.

## Not in this increment

- **WS4-8:** the use path. `authority_for_publish.resolve`, consume-at-claim inside the
  draft-intent transaction, and the `before_create` binding. `consume()` exists and is tested,
  but nothing in the publish path calls it yet.
- **The bounded public-activation authority:** a separately reviewable increment, off until
  the owner approves that power. Main S3.
- **Chaining SEG rows into a GrantLedger chain:** the issuer writes an `AuditLog` row per
  grant with its seal. Chaining is WS4-10.
