# Reliability and cost-governance audit — 2026-09-24

Scope: the observability path (`/health`, `/api/status`, `/api/verify`, `ops/health.py`),
the cost ledger and the spend guards, the durable queue and lease locks, and the things that
work today and stop working in a month.

Production was read over HTTPS, GET only, between 19:40 and 20:10 UTC on 2026-09-24
(commits `fce7d8cd` and `8a831d8e`). Nothing was deployed, restarted or reconfigured.

Every finding below carries the reading it was found from. Where a check and the system
disagreed, the section says which one I judged wrong and why.

---

## The shape of what was found

All nine findings are one defect family, which is the family this build keeps naming:

* a verdict computed from the absence of evidence — §1, §2
* one value living in two places — §3, §8
* a check that cannot see what it exists to measure — §4, §5
* a proof measured on a sample that cannot contain the broken case — §6
* a guard that destroys its own evidence — §7

---

## 1. `spend_limits_not_breached` and the `spend` health signal are green because there are no ceilings — HIGH

**Reading.** `/api/health-signals`, 2026-09-24 19:50 UTC:

```
spend healthy {"limits": 0, "paused": []}
```

`/api/verify` at the same time: `spend_limits_not_breached: true, {"paused_scopes": []}`.

**What the code does.** Both compute `all(not limit.paused for limit in limits)` over
`SpendLimit`. Nothing in `src/` ever calls `SpendGuard.set_limit` — the only callers are in
`tests/`. So the table is empty, `all([])` is `True`, and the signal whose description was
*"the ceilings are on and unbreached"* was green precisely because no ceiling existed. The
more scopes anybody forgets to configure, the greener it gets.

**Not a bug on its own.** The empty table is also how advertising is kept off:
`build2/executor.py::_ads_authorised` requires a `SpendLimit` row with scope `ads` and a
positive cap. The gate is correctly closed. The defect is that a *closed gate* and a
*healthy ceiling* are being reported by the same sentence.

**What breaks and when.** Nothing yet — there is no scoped spend. It breaks the first time
someone configures a scope, spends against it and reads a green light that was green before
the scope existed.

**Fixed.** `ops/health.py::_spend` now reads the ceilings that exist *and* bind: the scoped
limits with their count, the monthly model ceiling with what it is actually at, and each
agent's daily ceiling against what that agent actually spent today. `DEGRADED` means a
ceiling was crossed, not approached — approaching at four-fifths is
`spend_policy.escalation`'s job, and a signal that goes yellow on a normal working day is a
signal people turn off. `/api/verify`'s check keeps its verdict (an unconfigured scope is
not a breach) and its evidence now names `scopes_configured` and what it cannot see.

---

## 2. The per-agent daily ceiling is consulted by one writer and bypassed by all the others — HIGH

**Reading.** `/api/spend-report`, month to date: `creative_director` CA$41.54,
`market_radar` CA$23.67, `quality_director` CA$7.80. Declared daily ceilings, from
`agents/registry.py`: CA$28.00, CA$4.00, CA$1.00. `/api/governor` reports five days of
history plus today, so `market_radar` averaged about CA$3.94 a day against a CA$4.00
ceiling, and `spend_policy.ALLOCATION` states in its own comment that the raised gallery
cadence is **CA$8.70 a day** — twice that agent's ceiling — while the backlog drains.

**What the code does.** `Agent.daily_cost_ceiling_cad` is checked in exactly one place:
`registry.record_cost`, used only by `gateway/model_gateway.py`. Every other real spend path
— `intel/vision.py`, `gateway/images.py`, `gateway/image_bench.py`, `visual/inspect.py`,
`visual/tournament.py`, `visual/model_registry.py`, `visual/photoreal.py`,
`creative/reference.py`, `culture/classify.py`, and the probes — writes through
`finance/spend_report.record`, which never looks at an agent's ceiling. That is the single
writer the owner's spend-accounting instruction created, so the ceiling is bypassed by
design rather than by accident.

`/api/verify`'s `every_agent_has_a_cost_ceiling` reports `{"agents": 24,
"without_ceiling": []}`. It measures that a number is configured. It does not, and could
not, measure that the number binds.

**Two authorities disagree about the same money.** The registry says `market_radar` may
spend CA$4.00 a day. `spend_policy` says the gallery cadence costs CA$8.70 a day and
allocates it 40% of a CA$100 month. Both are owner-derived. I have **not** raised the
ceiling to make anything pass — that is the weakening this audit exists to refuse. The
contradiction is an owner/integrator decision and is listed in §10.

**Fixed (visibility, not enforcement).** `finance/spend_report.per_agent_today` reports each
agent's spend today beside its ceiling, names those over it, and separately names spenders
with no agent row at all (who have no ceiling of any kind). It is wired into
`/api/verify`'s evidence and into the `spend` health signal, which goes `DEGRADED` on a real
overrun.

**Not fixed.** Enforcement. Making it bind means checking the agent's ceiling *before* the
call, in `gateway/anthropic.check_budget`, and that changes what the running system refuses
— it would halt the gallery cadence at CA$4.00/day today. That is a behaviour change for the
integrator and owner, not a reporting fix. §10.

---

## 3. Three of the governor's five dimensions were read from a field nothing writes — HIGH

**Reading.** Same rows, same minute, 2026-09-24:

| endpoint | department attribution |
|---|---|
| `/api/spend-report` | creative CA$39.80, intel CA$23.65, quality CA$7.80 |
| `/api/governor` | `unattributed_cad: 75.93`, `unattributed_share: 1.0`, `rows: []` |

Same for `product`. Both read `cost_entries`.

**What the code does.** `finance/spend_report.record` writes the `department` and
`product_slug` **columns**. `finance/governor.spend_by` read `entry.detail[dimension]` — the
JSON blob those dimensions lived in *before* the columns were added, and which the single
writer no longer touches. So the governor found nothing and filed the entire bill under
`unattributed`.

**Why nothing caught it.** The module's headline invariant is *"attribution sums to the bill
or it is refused"*. It does sum: a dimension that reads nothing puts 100% of the bill in the
`unattributed` bucket, where it reconciles perfectly. A total that adds up is not a dimension
that works. This is the reconciliation check passing by absence of evidence, in the module
whose docstring warns that a table which does not add up "is worse than none, because it is
acted on" — a table reading `unattributed: 100%` is acted on the same way.

**Fixed.** `COLUMN_FOR` maps each dimension to the column that holds it, with the `detail`
key kept as a fallback so rows written before the columns existed still attribute. Every
dimension now reports `read_from`, so "100% unattributed" can be told apart from "this is
being read out of the wrong place".

`experiment` has no column and no writer anywhere in the repository. It now reports
`has_writer: false` with the reason, rather than reading as call sites that forgot — those
are different faults fixed in different places.

---

## 4. The monthly ceiling could not see a batch's own spend — HIGH

**What the code does.** `gateway/anthropic.check_budget` reads the month from cost rows and
refuses before the call. The callers that spend the most do not write a row per call:

* `intel/vision.py::analyse` calls `check_budget` **inside a loop** over a page of gallery
  images and calls `_bill` **once, after the loop**.
* `visual/inspect.py` makes two vision calls and writes one row after both.

So every call after the first in those loops was checked against the month as it stood
*before the loop began*. A guard whose entire purpose is to refuse before the call was, in
practice, refusing only the first call of each batch.

**Reading.** `/api/spend-report`: `gallery_observation` is CA$23.65 across **33 ledger
rows** carrying 4,175,276 input tokens — about 126,000 input tokens per row, which at the
measured 6,000 tokens an image is roughly **21 vision calls behind one row**. Twenty of
those twenty-one were authorised against a stale total.

**What it costs.** Up to one run's full cost of overshoot per run — about CA$0.72 at
observed rates, and up to CA$8.70 on a full backlog day. It only bites at the ceiling, which
is where the month currently is: CA$76.01 of CA$100 on 2026-09-24, projected CA$95.62.

**Fixed.** `check_budget` takes `uncommitted_cad` — money the caller has spent and not yet
billed — and `intel/vision.py` passes `max(spent, reserved)`, the pessimistic of its two
running totals. A caller that bills every call passes nothing and is unaffected. The
refusal message now names the billed and unbilled halves separately.

`visual/inspect.py` has the identical defect and is **not** fixed here: `visual/**` is owned
by another department this session. The change is one line — pass
`uncommitted_cad=max(billed["actual"], billed["reserved"])` to the `check_budget` call at
`visual/inspect.py:238`. §10.

---

## 5. The cross-process half of the same race is real and is not fixable from here — HIGH, open

`check_budget` reads the total, returns, the call runs for seconds, and only then is a row
written. Two agents in two processes both read CA$99, both find room, both spend. There is
no reservation anywhere: `visual/inspect.py` names a local variable `reserved`, and
`spend_report`'s docstring says "the reservation and the bill are kept side by side", but
nothing is ever written down before a call. `estimated_cad` is recorded *after* the fact,
beside the bill it is compared against.

So the overshoot is bounded by (number of concurrent callers) x (largest single estimate),
and `image_bench` can estimate double figures in one call. Nothing caps it.

The same lost-update shape was in `SpendGuard.authorize_spend`: `SELECT` then `UPDATE` with
no lock, so two concurrent authorisations both read the same `spent_today_cad` and the
second wrote over the first. **Fixed** — the read now takes `FOR UPDATE` on Postgres (a
no-op on SQLite, which serialises writers anyway).

**Not fixed.** The model ceiling's cross-process race needs a durable reservation: a row
written before the call and released after it, with expiry so a dead process does not hold
budget forever. That is a schema change and a deploy. §10.

---

## 6. `worker_restarts` cannot count a restart — MEDIUM

**Reading.** `worker_started_at` moved three times inside forty-seven minutes —
`19:16:04`, `19:44:25`, `20:03:00` — while `/api/verify` reported `restarts: 0` throughout.

Those three were deploys (`commit_short` moved `fce7d8cd` → `8a831d8e`), which is exactly
the point: **nothing in the system could have told them apart from a container dying and
being replaced every twenty minutes**, and the second is the case a restart count is for.
`runner.STATE.worker_restarts` counts the worker thread's own restart loop inside one
process and resets to zero with that process — it is a measurement whose sample cannot
contain the event it is named after.

**Fixed.** `_startup` writes one `runtime.started` audit row per boot carrying the commit.
`ops/health.container_starts` reads those rows and separates a start on a commit already
seen in the window (a restart) from a start on a new commit (a deploy).
`/api/verify`'s `worker_is_alive` evidence now carries
`container_starts_24h` beside the renamed `restarts_in_this_process`. Verdict unchanged.

One row a boot, against 4,700 audit rows a day. It takes a deploy to start collecting.

---

## 7. The daily ceiling deleted the evidence that it had been crossed — MEDIUM

`registry.record_cost` checked the ceiling first and wrote the cost row second, so the one
call that crossed the ceiling wrote **no row at all**. It is called *after* the provider has
answered — the money has already left — and
`gateway/anthropic.spent_this_month_cad` sums exactly these rows to enforce the monthly
ceiling. So a daily-ceiling breach quietly lowered the number the monthly ceiling is checked
against. A guard that erases its own evidence weakens the guard above it.

**Fixed.** The row is written, then the refusal raises. The refusal is unchanged: the caller
still raises `BudgetExceeded`, the worker still dead-letters the job with `retry=False`, and
nothing new is permitted.

`tests/test_platform.py::test_agent_daily_cost_ceiling_is_enforced` asserted
`# refused spend is not recorded`. **I judged the check wrong, not the system.** There is no
spend to refuse by the time `record_cost` runs; the assertion pinned the wrong property. The
refusal assertions are kept verbatim and only the ledger-completeness line changed, with the
reasoning in the test.

Also fixed in the same file: `spend_today` and the `SpendLimit` day-roll used
`date.today()` — the *host's* local day — to sum rows stamped with `utcnow`. On any host not
set to UTC the ceiling resets at an hour that depends on a container setting nobody records.
Both are UTC now, matching the repository convention.

---

## 8. One dead letter, three classifications, two production endpoints disagreeing — MEDIUM

**Reading**, 2026-09-24, same rows, same minute:

* `/api/status`: `dead_letter_defects: 1`
* `/api/verify`: `historical_total: 0`, `expected_stand_asides: 1`

The row is `creative.model_reference_pack` standing aside for the build that can run it — a
refusal working correctly. Three rules answered the question:

| rule | where | used by |
|---|---|---|
| `deliberate_refusal()` | `queue/durable.py` | `/api/verify` |
| `JobQueue.REFUSAL_MARKERS` | `queue/durable.py` | `requeue_dead`, `health.remediation` |
| `job_type != "store.publish"` | `app/main.py` | `/api/status`, `/api/queue/requeue` |

`durable.py`'s own comment says this value is *"defined once because it is asked in two
places, and a value that lives in two places disagrees with itself"*. It was answered three
ways, and two of this company's own status endpoints disagreed about whether anything was
wrong.

**Fixed, carefully.** The two rules answer *different questions* and must not be merged:

* *Is this a defect somebody has to explain?* → `deliberate_refusal`. `/api/status` and
  `health.remediation` now use it. A stand-aside is not a defect.
* *May this be re-driven?* → `REFUSAL_MARKERS`. A stand-aside **is** re-drivable (the right
  build should take it) while a publication refusal is not. That rule is unchanged.

After deploy, `/api/status` will report `dead_letter_defects: 0` and agree with
`/api/verify`. `/api/status` also stopped calling `dead_letters()` three times per request.

---

## 9. Sustainability: what works now and fails later — MEDIUM to LOW

**Observed growth rates, 2026-09-24:**

| store | size | rate | source |
|---|---|---|---|
| `audit_log` | 9,622 rows | +66 in 20 min → ~4,700/day | `/api/verify` |
| `jobs` (done) | 4,148 | 226 in 6h → ~900/day | `/api/status` |
| dead letters | 149 | +21/day | `/api/queue/dead` |
| `cost_entries` | 1,147 this month | — | `/api/spend-report` |

Nothing prunes any of them. `purge_dead` exists and is called from nowhere in `src/`. At
these rates the audit log passes 1.7M rows in a year, on a database that is the whole
CA$20/month infrastructure ceiling's main cost driver.

**Fixed — `/api/status` was getting slower with every job ever run.** `JobQueue.counts()`
built each count by loading every matching row into Python objects: six full scans of
`jobs`, six times the table materialised, on the endpoint the console polls. `/api/status`
measured **0.80s** against `/health`'s 0.23s. It is now one grouped `COUNT`. A test asserts
the call issues exactly one `SELECT` and that it is a count.

**Fixed — nobody could see the disk.** The health sweep had eleven signals and none of them
was storage. There is now a `disk` signal: free space where the container writes, and a count
of the temporary directories this system's own handlers left behind. It reads the facts the
*running container* reports (via `runner.STATE`), for the same reason the worker heartbeat
does — a sweep that measures whichever machine answered the request is a check that cannot
see the thing it exists to measure. Absent reads `unknown`, never `healthy`.

The threshold is **absolute free space, not a share**, and that is a correction I made after
writing the share version: ten percent of a 270 GB volume is 27 GB, which is no risk to a
workload whose largest write is a few-megabyte render, while ten percent of a small container
volume is. A share answers "how full is this disk" when the question is "is there room for
the next write".

**Open — the leak itself.** Production job handlers call `tempfile.mkdtemp`, which never
cleans up, in the continuity, offsite, tournament, owned-asset, reference-pack,
image-generation and motif-chart paths (`runtime/release.py` ×5, `gateway/images.py:682`,
`publish/motif_fidelity.py` ×2, `core/offsite.py:364`, `app/main.py:816`). These run on
cadences forever and several write rendered images. This is the same call that left 29 GB
and 37,284 directories in the test suite's `/tmp` on 2026-09-20 — the fix there was
containment in `run_tests.sh`; production has no equivalent. What saves it today is that
Railway replaces the container often (three times in the hour I watched). The signal makes
the accumulation visible; the durable fix is `TemporaryDirectory` at each call site, and the
`release.py` handlers already use it in four other places, so the pattern is established. Not
done here: four of the leaking files are in `runtime/` and `publish/`, which I did not want
to touch while other departments are mid-flight, and the count-first approach means the next
session can see whether it is actually accumulating. §10.

**Deliberately not done.** The health sweep does not delete temp directories. One may belong
to a job that is still writing into it.

---

## 10. Lease locks and lost work

**`queue/durable.py::claim` could only recover an orphan while the queue was idle — HIGH,
fixed.** `_reclaim_expired` ran *only* when the pending query came back empty. So a job whose
worker died holding the lease was recoverable exactly while there was nothing else to do, and
never under a backlog — which is when a worker is most likely to be killed and the only time
losing work costs anything. Nothing reports a job stuck in `RUNNING`, so it is not a delay
anybody would notice; it is work that quietly stops existing.

The reclaim now runs first. That is also the right order on its own terms: a reclaimable job
was enqueued before everything pending and has already waited a whole lease. It cannot spin —
`claim` increments `attempts`, so a job that keeps dying dead-letters like any other, and a
test pins that.

**Two workers could reclaim the same orphan — fixed.** `_reclaim_expired` had no lock while
the pending claim had `SKIP LOCKED`. Two workers reclaiming together would both set the row
`RUNNING` and both run it — the double execution `idempotency_key` exists to prevent,
arriving through the recovery path instead of the enqueue path. It now takes the same lock.

**`ops/lock.py` was not a lock — HIGH, fixed.** Several departments run in parallel against
it. `acquire` read the file and then wrote it: two sessions that both find no lease both
write one, the second overwrites the first, and both believe they hold it. The take is now a
single `O_CREAT|O_EXCL` create, and a stale takeover is a write-then-`os.replace`.

**A live session could have its lease stolen — fixed.** `STALE_HOURS` measured time since the
lease was *acquired*, so any session running longer than three hours was declared dead while
it ran. The lease now carries a heartbeat, `refresh` moves it, and staleness is measured from
it — so a long session keeps its lease by saying it is alive and a dead one still loses it
after three hours. A malformed lease reads as infinitely old instead of raising, so an
unparseable lock file cannot wedge every session after it.

**Retries terminate.** `fail()` dead-letters at `max_attempts`, backoff is capped at one hour
and jittered; the permission, capability and budget paths pass `retry=False`. No unbounded
retry found. The deploy-triggered re-drive is the right trigger and is not a timer.

**Queue depth is visible.** `/api/status` reports it, `queue_age` degrades past an hour, and
`/api/queue/dead` groups the graveyard. This was the one part of the failure path already in
good shape.

---

## What needs the integrator or the owner

Nothing here has been deployed. Everything below needs someone with the deploy.

1. **Deploy this branch.** The whole audit is reporting fixes plus one queue-ordering change.
   Expected visible changes after deploy: `/api/status` reports `dead_letter_defects: 0`
   (agreeing with `/api/verify`), `/api/verify` gains evidence fields, `/api/health-signals`
   gains a `disk` signal, and `/api/status` gets faster.

2. **The `spend` signal may go `DEGRADED` on the first full gallery-analysis day**, because
   `market_radar`'s CA$4.00/day ceiling is below the CA$8.70/day the spend policy itself
   budgets for that cadence. If it does, that is a true reading, not a false alarm. Do not
   raise the ceiling to silence it — see 3.

3. **OWNER DECISION: two authorities disagree about `market_radar`'s daily budget.**
   `agents/registry.py` says CA$4.00/day. `finance/spend_policy.ALLOCATION` says gallery
   observation may take 40% of a CA$100 month and states the cadence costs CA$8.70/day.
   Either the registry ceiling rises to match the allocation, or the cadence slows to fit the
   ceiling. Cost of deciding: zero. Cost of not deciding: the ceiling stays unenforced, which
   is the state it has been in.

4. **Enforcement of per-agent ceilings before the call.** The measurement now exists
   (`spend_report.per_agent_today`). Making it refuse means adding the agent to
   `gateway/anthropic.check_budget` and passing it at its six call sites. It will stop work
   that currently runs. Decide 3 first.

5. **A durable spend reservation** for the cross-process race (§5). Schema change: a
   reservations table with an expiry, written before the call and released after. This is the
   only remaining unbounded overshoot in the model ceiling.

6. **`visual/inspect.py:238`** — same in-batch ceiling hole as §4, one line, owned by Visual:
   pass `uncommitted_cad=max(billed["actual"], billed["reserved"])`.

7. **`tempfile.mkdtemp` → `TemporaryDirectory`** in the ten production call sites listed in
   §9, owned by whoever holds `runtime/` and `publish/`.

8. **Retention.** Nothing prunes the audit log, the job table or the dead-letter queue.
   4,700 audit rows a day is 1.7M in a year on the database that dominates the CA$20/month
   infrastructure ceiling. `purge_dead` exists and needs a caller with a policy behind it.

---

## What I checked and found sound

* `no_revenue_claimed`, `nothing_published`, `publication_was_actually_attempted_and_refused`
  — all read rows, and the third is the one that stops the second passing by absence. Good
  shape, and the model for the fixes above.
* `state_is_in_a_durable_database` reads the dialect and the row counts, and
  `core/db.resolve_url` refuses to start on ephemeral SQLite. Correct.
* `worker_is_alive`'s startup grace is bounded by the runner's own knobs and expires. It
  narrows a window without softening the check.
* `no_unexpected_dead_letters_in_24h` is recent-not-historical with the history kept in the
  evidence, and the naive/aware normalisation is right.
* `evidence_freshness` — jobs completing is not evidence being produced. This is the best
  check in the codebase and nothing here touches it.
* `no_paid_advertising` reads `CostEntry.kind == "ads"` and nothing writes that kind — so it
  is technically a check passing by absence. It is backed by a real closed gate
  (`_ads_authorised` requires a `SpendLimit` row that does not exist) and there is no ad
  integration to spend through, so I left it alone and note it here rather than in the
  findings.

---

## Tests

`brambleloop/tests/test_spend_governance.py` — 35 tests, all passing. Every one is against a
defect that was live on 2026-09-24, and each quotes the production reading it was found from,
so a future session can tell a regression from a disagreement about what the check should
mean.

Suites re-run green after these changes (targeted, not the full suite — deploys are
serialised this session):

```
test_spend_governance 35   test_health 34        test_governor 16   test_platform 22
test_gateway 30            test_engine 41        test_persistence 10  test_finance 16
test_spend_policy 24       test_reliability 17   test_intel 38      test_executor 34
test_clusters 15           test_defects 16       test_model_provider 12
test_provider_trial 22     test_swarm 6          test_twin 6        test_listing_parity_gate 6
test_acceptance_gates 23   test_deploy 32        test_chaos 25
```

Twenty-three suites, 0 failing. `run_tests.sh` itself was not run: it is the full 1,133-second
suite and deploys are serialised to the integrator this session, so the suites above were
chosen by grepping `tests/` for every consumer of the functions this branch touches
(`counts`, `claim`, `record_cost`, `spend_by`, `check_budget`, `health.*`, `/api/status`,
`/api/verify`, dead-letter classification) plus the acceptance gates, chaos and deploy suites
that exercise them end to end.

One pre-existing test was changed: `test_platform.py::test_agent_daily_cost_ceiling_is_enforced`
(§7). The refusal it gates is unchanged; only the assertion about whether the breaching spend
appears in the ledger moved, and the reasoning is in the test.

No threshold was lowered and no existing check was removed.
