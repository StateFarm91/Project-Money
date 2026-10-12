# Brambleloop always-on cloud hosting plan (v1.1, lane I)

Written 2026-10-06 (UTC). Covers F-880, F-881 (hosting side), F-900, F-923, F-924, directive
§1 (OA-0003 resolved: rented always-on hosting authorised and required), §16 (lights-out
acceptance) and §17 (prepare the hosting path; **no deploy is authorised by this document**).

Status words used below: **OBSERVED** (read from Railway or the repo on 2026-10-06),
**BUILT** (code + tests in branch `claude/v11-I`, not deployed), **PROPOSED** (needs an
integrator wiring change or an owner action), **ASSUMED** (a number not measured from the
owner's bill).

---

## 1. What exists today (OBSERVED)

| Item | State |
|---|---|
| Railway project `brambleloop` | services `Postgres` (5 GB volume), `brambleloop-os`, `Project-Money` |
| `brambleloop-os` | latest deployment SUCCESS 2026-09-25, code `fcb982d`; one container runs uvicorn **plus** embedded worker pool **plus** scheduler thread (`app/runner.py`, started from `app/main.py` startup) |
| `railway.json` | Dockerfile build; `startCommand` uvicorn `--workers 1`; `healthcheckPath /health`, timeout 300 s; `restartPolicyType ON_FAILURE`, `restartPolicyMaxRetries 10` |
| `Project-Money` service | latest deployment FAILED; stale, not part of the runtime |
| External pokes | `/api/verify` every 8 h from a Claude heartbeat routine — the only inbound traffic seen in logs |
| Proof the embedded scheduler does useful work unattended | **NOT PROVEN** by logs. Section 5 gives the read-only query that decides it |
| Declared infra cost | `finance.spend_policy.INFRA_MONTHLY_CAD = 7.0`, basis `declared_not_observed`; ceiling `INFRA_CEILING_CAD = 20.0` |

The production container is already cloud-resident: the PC does not run it. The open question is
whether it *keeps doing work* when nothing pokes it (section 5), and whether anything notices when it
stops (sections 3–4).

## 2. Recommended topology: keep ONE always-on container, add ONE cron watchdog

**Recommendation: do not split web / worker / scheduler now.** Keep `brambleloop-os` as the single
always-on service and add a tiny Railway **cron** service as an outside-in watchdog.

Why this is the simplest durable option:

* Correctness does not depend on the split. The queue is Postgres with leases, fencing and unique
  idempotency keys (`queue/durable.py`); a worker thread in the web process and a worker in its own
  service claim work identically. The scheduler's enqueue is idempotent per cadence window
  (`cadence:<name>:<window>` is a unique key), so even two schedulers cannot double-schedule.
* Splitting triples the always-on Python processes (≈300 MB RSS each) for isolation a zero-revenue
  company does not yet need (`app/runner.py` docstring). Estimated +CA$8–11/month (section 6),
  which would take the declared CA$7 to ~CA$15–18 against the CA$20 ceiling.
* `app/worker_entry.py` and `app/scheduler_entry.py` already exist, so a later split is a config
  change (section 2.3), not a rewrite.

### 2.1 Always-on service `brambleloop-os` (PROPOSED config diff — integrator applies; lane I does not own `railway.json`)

```diff
   "deploy": {
     "startCommand": "uvicorn brambleloop.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1",
     "healthcheckPath": "/health",
     "healthcheckTimeout": 300,
-    "restartPolicyType": "ON_FAILURE",
-    "restartPolicyMaxRetries": 10
+    "restartPolicyType": "ALWAYS",
+    "numReplicas": 1
   }
```

* `ALWAYS`: with `ON_FAILURE` + 10 retries, an eleventh crash in a loop leaves the company down until a
  human redeploys — exactly the dependency on a person v1.1 forbids. `ALWAYS` keeps restarting.
  (`tests/test_cert_claude_independence.py` already accepts `ALWAYS`.)
* `numReplicas: 1`: the embedded scheduler is in this process; one replica is one scheduler. The
  idempotent window keys make a second replica harmless, but there is no reason to pay for it.
* Railway's `healthcheckPath` gates a **deploy** becoming live; it is not a continuous liveness probe
  (verify in Railway docs; treat as ASSUMED). Continuous liveness is the watchdog (2.2) plus the
  in-process self-exit (WIRING REQUEST W-3 in `handoff_I.md`): if the scheduler thread has not ticked
  for 15 minutes the process exits non-zero and Railway's restart policy brings up a fresh container.
* **Restart-loop risk (audit ddf9c6e M-2).** Until r2-AUTO, one cadence whose enqueue raised aborted
  the whole `Scheduler.tick`; the tick never completed, so the self-exit fired ~17 min after every
  boot — a *deterministic* fault, which a restart cannot fix, turned into a crash loop. With the
  current `ON_FAILURE` + `restartPolicyMaxRetries: 10` that loop could exhaust the retries and leave
  the service down (Railway's retry-counter reset semantics are NOT verified; no Railway call was
  made). Mitigated in code, not in `railway.json` (unchanged): `Scheduler.tick` now isolates each
  cadence (failure → deduplicated P2 incident `scheduler.cadence_failed:<name>` + audit row, the other
  cadences still enqueue, the tick completes and heartbeats), and only a tick in which *every*
  attempted cadence failed raises (a genuinely dead scheduler / database). Residual risk: a fault that
  fails every enqueue (e.g. the database unreachable) still self-exits each ~15 min; that is the
  intended behaviour, and the `ALWAYS` proposal above is what keeps it from exhausting retries.
* **App Sleeping / serverless must be OFF** for this service (owner check, section 7 item 3). A
  sleeping service only wakes on inbound HTTP — which here is the 8-hourly Claude `/api/verify` — and
  would exactly reproduce "the factory stops when nobody pokes it".

### 2.2 New cron service `brambleloop-watchdog` (BUILT code, PROPOSED service)

Same repository and Dockerfile, separate Railway service with its own config file
(`brambleloop/railway.watchdog.json`, proposed content):

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "startCommand": "python -m brambleloop.ops.slo watchdog",
    "cronSchedule": "*/5 * * * *",
    "restartPolicyType": "NEVER"
  }
}
```

Variables: `DATABASE_URL` (reference to the Postgres service), `BRAMBLELOOP_PHASE=shadow`,
`BRAMBLELOOP_PUBLIC_HEALTH_URL=https://<brambleloop-os public domain>/health`.

Each run (`ops.slo.watchdog`, ~seconds, then exits):
1. GETs the public `/health` **from outside the web container** and writes an
   `ops_runtime_samples` probe row — the only evidence the F-923 availability SLO accepts.
2. Writes its own heartbeat row.
3. Runs `ops.slo.check`: stale scheduler (P1 `slo.scheduler_stale`), stalled queue
   (P1 `slo.worker_stalled`), every SLO breach (`slo.breach:<key>`), and closes those that recovered
   with the reading that closed them (`ops.incident_lifecycle`).
4. Prunes samples older than 35 days.

Because it runs in a different container, it detects the one failure the main container cannot report
about itself: the main container being dead or hung. It writes incidents to Postgres — the stored
notification system the Command Center reads. **Limitation, stated:** if the web container is down the
owner cannot *see* those incidents until it is back; the out-of-band signal in that case is Railway's
own crash/deploy-failure e-mail to the account owner. No new outbound notification channel is added
(brief: stored notification system only).

Five-minute cadence is deliberate: the availability SLO buckets into 5-minute intervals and grades
anything under 50 % coverage as UNKNOWN, so a 15-minute probe could never produce a reading.

### 2.3 Later split (documented, not recommended now)

| Service | Start command | Replicas | Notes |
|---|---|---|---|
| web | uvicorn … (as today) with `BRAMBLELOOP_EMBEDDED_WORKER=0` | 1+ | serves owner UI/API only |
| worker | `python -m brambleloop.app.worker_entry` | 1..n | leases + fencing already make n safe |
| scheduler | `python -m brambleloop.app.scheduler_entry` with `BRAMBLELOOP_SCHEDULER_ONCE=0` | **1** | must hold `ops_leases['scheduler']` (`ops.slo.acquire_lease`, renewed each tick, TTL 180 s) — WIRING REQUEST W-1 |

The lease is a database row with a conditional UPDATE/INSERT (works on SQLite and Postgres, tested in
`test_v11_reliability_slo.py`). `ops/lock.py` is a file lock for development sessions and is **not**
usable across containers. A Postgres advisory lock (`pg_try_advisory_lock`) would also work but is
session-scoped, so a pooled connection could silently drop it; the row lease is explicit and visible
to the Command Center (`lease_state`) and recoverable (`ops.recovery.release_stale_lease`).

## 3. What must happen to stop depending on the owner PC / Claude heartbeat (F-881)

| # | Change | Owner of change | State |
|---|---|---|---|
| 1 | Prove the embedded scheduler runs unattended: run the section 5 query on production | integrator (read-only) | PROPOSED |
| 2 | App Sleeping OFF on `brambleloop-os` | owner | PROPOSED (section 7) |
| 3 | Scheduler self-heartbeat row every tick (`ops.slo.record_heartbeat(db, "scheduler", …)`) | lane A (W-1) | BUILT here, wiring pending |
| 4 | Worker heartbeat row (throttled, once a minute) | lane A (W-2) | BUILT here, wiring pending |
| 5 | In-process self-exit when the scheduler thread is stale > 15 min → platform restart | lane A (W-3) | PROPOSED |
| 6 | `ops.slo` in-process cadence every 15 min (`check(db)`) — alerting while the container lives | lane A (W-4) | BUILT here, wiring pending |
| 7 | Watchdog cron service (2.2) — alerting when the container does not | owner approval + integrator | BUILT code, PROPOSED service |
| 8 | Restart policy `ALWAYS` (2.1) | integrator via deploy | PROPOSED |
| 9 | Disable the Claude 8-hourly `/api/verify` routine for the soak; afterwards keep it only as an optional external check, never a dependency | owner | PROPOSED |
| 10 | Command Center Operations page renders `ops.slo.summary(db)` and exposes `ops.recovery` actions behind owner auth | lane C (W-5) | PROPOSED |

## 4. Database backup and restore

| Layer | What it is | State |
|---|---|---|
| Railway Postgres volume | 5 GB volume on the Postgres service | OBSERVED |
| Railway volume backups | Platform snapshots of the Postgres volume (availability depends on the owner's Railway plan) | UNVERIFIED — owner checks Postgres service → Backups; enable daily + weekly if offered at CA$0 |
| `ops.continuity` (daily) | export → restore into scratch DB → digest compare; retained in-database | BUILT + running in production (BUILD_STATE: 4,304 rows / 25 tables proven on live Postgres) — **does not survive loss of the database itself** |
| `core/offsite.py` + `ops.offsite_archive` (daily) | AES-256 sealed export to any S3-compatible bucket, read back, restore-proved, pruned after a good write | BUILT, **unconfigured** (`/api/offsite` → `configured: false`) |

Restore procedure (owner-free once configured): `core.continuity.restore(export, target_db)` from the
latest offsite object (`core.offsite.get` + `unseal`), into a fresh Railway Postgres, then repoint
`DATABASE_URL`. The repoint is a Railway variable change — an owner/integrator action under the
rollback runbook (`ops/ROLLBACK_RUNBOOK.md`).

Recommendation: configure the offsite archive on **Backblaze B2** (existing BUILD_STATE recommendation;
first 10 GB stored free, so ≈ CA$0 at current size — ASSUMED from B2's published free tier).

## 5. Read-only proof that the embedded scheduler works without pokes

Run against production Postgres (read-only) — the integrator can do it through the existing read
endpoints or a read-only SQL session; it changes nothing:

```sql
-- Cadence jobs the scheduler created, per UTC hour, last 72 h. An always-on scheduler shows
-- every hour populated (infra_heartbeat alone opens a window every 15 min). A sleeping service
-- shows bursts only in the hours following the 8-hourly /api/verify pokes.
SELECT date_trunc('hour', created_at) AS hour, count(*) AS cadence_jobs,
       count(*) FILTER (WHERE status = 'done') AS done
FROM jobs
WHERE idempotency_key LIKE 'cadence:%' AND created_at >= now() - interval '72 hours'
GROUP BY 1 ORDER BY 1;
```

After deploy, `ops.slo.summary(db)` answers the same question continuously (`scheduler_freshness`
SLI and the `scheduler_liveness` item).

## 6. Cost (CAD per month, incremental)

Basis: Railway usage list prices **ASSUMED** (vCPU ≈ US$20/vCPU-month, RAM ≈ US$10/GB-month,
volume ≈ US$0.15/GB-month, egress ≈ US$0.05/GB), converted at the repo's assumed 1.37 CAD/USD
(`gateway.anthropic.USD_TO_CAD`). None of these is read from the owner's invoice; the current
CA$7.00 is itself declared, not observed.

| Change | Estimate | Basis |
|---|---|---|
| Watchdog cron, every 5 min | **+CA$0.50–1.00** | 8,640 runs/month × 15–30 s = 36–72 h runtime; × 0.25 vCPU = 9–18 vCPU-h (US$0.25–0.49) + × 0.25 GB = 9–18 GB-h (US$0.12–0.25) = US$0.37–0.74 |
| Restart policy `ALWAYS`, `numReplicas 1` | CA$0 | config only |
| App Sleeping OFF | CA$0 if already off; if it is on, always-on compute for one container ≈ CA$4–8 more than a sleeping one — and it is required (F-880) | |
| Offsite archive on B2 | ≈ CA$0 (under 10 GB free) | B2 free tier, ASSUMED |
| Split into 3 services (not recommended) | +CA$8–11 | 2 extra ~300 MB always-on processes + idle CPU |
| New SLO tables | negligible (KB/day; pruned at 35 days) | |

**Recommended path total: declared CA$7.00 + ≈ CA$0.50–1.00 ≈ CA$7.50–8.00/month, under the
CA$20.00 infra ceiling.** No new recurring cost is incurred until the owner approves item 2 in
section 7. `spend_policy.INFRA_MONTHLY_CAD` stays declared until the owner records the actual bill.

## 7. OWNER ACTION REQUIRED (batched)

1. **Approve the v1.1 deploy** (gates everything below that needs new code live, including the soak).
   Why: no production deploy is authorised by the v1.1 directive (§17, §20). Cost: CA$0.
   Minutes: 5 to review the integrator's release record. Waiting: SLOs/watchdog/recovery stay
   un-deployed; the lights-out soak cannot start.
2. **Approve the watchdog cron service** (section 2.2). Why: the only component that can notice the
   main container dying (F-900/F-924). Max cost: CA$1.50/month (estimate CA$0.50–1.00). Minutes: 10
   (create service from the same repo, set config path and 3 variables) — or approve and let the
   integrator do it. Waiting: a dead or hung container is noticed only by the next human visit.
3. **Check App Sleeping / serverless is OFF on `brambleloop-os`** (Railway → service → Settings).
   Why: a sleeping service runs only when poked, which makes the company depend on the Claude
   heartbeat. Max cost: CA$0–8/month (only if it is currently on). Minutes: 2. Waiting: F-880/F-881
   may be violated right now; section 5 query will show it.
4. **Configure offsite backups** (B2 bucket + application key → set `BRAMBLELOOP_ARCHIVE_URL`,
   `BRAMBLELOOP_ARCHIVE_BUCKET`, `BRAMBLELOOP_ARCHIVE_REGION`, `BRAMBLELOOP_ARCHIVE_KEY_ID`,
   `BRAMBLELOOP_ARCHIVE_SECRET`, `BRAMBLELOOP_ARCHIVE_ENCRYPTION_KEY` on `brambleloop-os`), and enable
   Railway volume backups if the plan offers them. Why: the only restore copy today lives inside the
   database it would restore. Max cost: ≈CA$0 (free tier); B2 may require a card on file. Minutes: 15.
   Waiting: loss of the Postgres volume loses the company's memory.
5. **For the soak window only: disable the Claude 8-hourly heartbeat routine and do not prompt any
   development session or the operator API for 24 h; leave the PC off.** Why: §16 requires a genuine
   lights-out run. Cost: CA$0. Minutes: 2 + 24 h of not touching it. Waiting: no lights-out evidence.
6. **Decommission the failed `Project-Money` Railway service** (Railway → service → Settings → Delete
   service; first confirm it holds no volume/variables still needed — it has no successful deployment).
   Why: a stale failed service confuses status and may carry a volume/variable cost. Cost: CA$0
   (saves any residual). Minutes: 3. Waiting: clutter; possibly a small residual charge.
   *Lane I did not and will not touch it.*
7. **Record the actual Railway bill** (Railway → Usage) so `INFRA_MONTHLY_CAD` can stop being
   "declared". Cost: CA$0. Minutes: 3. Waiting: infra spend stays an unmeasured declaration.
8. *(Not recommended now)* a project-scoped Railway API token for automatic redeploy by the watchdog.
   A credential that can mutate hosting is a consequential capability; the self-exit + restart policy
   covers the same failure without one.

## 8. Lights-out soak protocol (§16, §95 bullet 1) — GATED on deploy approval (item 1)

**The soak has not started and cannot start until the v1.1 build is deployed.** Nothing in this
branch fakes a soak; `ops.slo.soak_report` refuses a window that ends in the future and grades any
window under 24 h as INCOMPLETE.

Preconditions (all verified, not assumed):
1. v1.1 deployed with a release record; boot guard reports proven build; phase **shadow**.
2. W-1..W-4 wired (scheduler/worker heartbeats, self-exit, `ops.slo` cadence); watchdog cron running
   and its first probe row present.
3. Section 5 query shows cadence jobs in every hour of the preceding 24 h.
4. App Sleeping confirmed off.

Procedure:
1. T0 (UTC) recorded by the integrator in BUILD_STATE. Owner: PC off, all development chats closed,
   Claude heartbeat routine disabled, no operator API calls.
2. Nothing is touched for ≥ 24 h. (Optional, only with separate approval: one deliberate container
   restart via Railway at T0+12 h to prove durable restart state — a Railway mutation, so not part of
   the default protocol.)
3. At T0+24 h or later, the integrator runs read-only `ops.slo.soak_report(db, start=T0, end=T1)` and
   commits its JSON under `evidence/I_soak_<T0>.json`.

Evidence and pass criteria (each computed from durable rows, each names its source):

| Criterion | Source | Pass |
|---|---|---|
| Window ≥ 24 h | clock | ≥ 24.0 h |
| Scheduler kept scheduling | `jobs.idempotency_key LIKE 'cadence:%'` | cadence job in every hour |
| Scheduler freshness SLO | heartbeats / cadence jobs | MET or AT_RISK (≥ 99 %) |
| Durable cadences executed | `jobs` done in window | > 0, and `cadence_freshness` reported |
| Independent departments did useful work | `jobs.outputs` via `did_no_work` | ≥ 3 departments with useful hours |
| Follow-on work generated by the company | non-cadence jobs created | > 0 (lane A mission/handoff tables replace this proxy when they land) |
| No interactive / development actor | `audit_log.actor` | zero rows from owner/operator/claude/codex/fable/chatgpt |
| Owner surface stayed readable | watchdog probes | availability MET/AT_RISK with ≥ 50 % coverage |
| No duplicated external effect | `audit_log` fenced-write refusals; unique idempotency keys | zero |
| No P0/P1 incident opened | `incidents` | none |
| Budgets respected | `cost_entries`, `spend.refused` | reported; any ceiling breach is a FAIL by the existing guards |

Verdict: PASS only if every criterion is PASS; any UNKNOWN → INCOMPLETE; any FAIL → FAIL. Tested in
`tests/test_v11_reliability_slo.py` (short window → INCOMPLETE; no probe → INCOMPLETE; interactive
actor → FAIL; complete evidence → PASS).

## 9. Degraded mode (F-923)

| Condition | What the owner sees | What keeps running |
|---|---|---|
| Postgres unreachable | `/health` 503 `{"db":"unreachable"}`; Command Center cannot read state and must say so (lane C), never show zeros | nothing durable; restart policy retries; watchdog cannot write either — Railway e-mail is the signal |
| Web up, scheduler thread dead | P1 `slo.scheduler_stale` (watchdog + in-process check); self-exit restarts the container (W-3) | worker drains existing queue |
| Queue not draining | P1 `slo.worker_stalled`; `ops.recovery.restart_stuck_job` from the phone | scheduler keeps enqueuing (idempotent) |
| Model provider down | `model_failover` item DEGRADED; jobs PARK (retry with backoff) or use an approved *stronger* fallback within the ceiling | all non-model work |
| Container dead | availability probes fail → SLO breach incident on recovery; Railway crash e-mail | nothing until restart (`ALWAYS`) |

## 10. Secrets / variables checklist (names only — no values in the repo)

`brambleloop-os`: `DATABASE_URL` (Railway reference), `BRAMBLELOOP_OPS_TOKEN`,
`BRAMBLELOOP_SECRET_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (only if the image provider needs it),
`BRAMBLELOOP_IMAGE_KEY`, `BRAMBLELOOP_MODEL_KEY`, `ETSY_KEYSTRING` / `ETSY_API_KEY`,
`ETSY_SHARED_SECRET`, `ETSY_SHOP_ID`, `ETSY_SHOP_NAME`, `ETSY_REDIRECT_URI`, `ETSY_SCOPES`
(tokens `ETSY_ACCESS_TOKEN`/`ETSY_REFRESH_TOKEN` only if not DB-held), `BRAMBLELOOP_BROWSER_URL`,
`BRAMBLELOOP_BROWSER_TOKEN`, `BRAMBLELOOP_LEARN_REVIEW_TOKEN`, `BRAMBLELOOP_ARCHIVE_URL`,
`BRAMBLELOOP_ARCHIVE_BUCKET`, `BRAMBLELOOP_ARCHIVE_REGION`, `BRAMBLELOOP_ARCHIVE_KEY_ID`,
`BRAMBLELOOP_ARCHIVE_SECRET`, `BRAMBLELOOP_ARCHIVE_ENCRYPTION_KEY`.
Non-secret config: `BRAMBLELOOP_PHASE=shadow`, `BRAMBLELOOP_EMBEDDED_WORKER=1`,
`BRAMBLELOOP_WORKER_THREADS`, `BRAMBLELOOP_BOOT_GUARD`, `BRAMBLELOOP_REQUIRE_POSTGRES`,
`BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD` (may only lower the policy ceiling).

`brambleloop-watchdog` (new): `DATABASE_URL` (reference), `BRAMBLELOOP_PHASE=shadow`,
`BRAMBLELOOP_PUBLIC_HEALTH_URL`. It needs **no** API keys and no operator token.

## 11. Rollback

Unchanged: `ops/ROLLBACK_RUNBOOK.md` and `ops/deploy.sh --rollback-to`. The watchdog service can be
deleted independently with no effect on the company (it only reads, probes and writes incident/sample
rows). The two new tables are additive; rolling back the code leaves them unused.
