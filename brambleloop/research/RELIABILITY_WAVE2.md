# Reliability and cost governance, wave 2 — 2026-09-25

Scope: the five things the 2026-09-24 audit (`RELIABILITY_AUDIT.md`) could *see* and could not
*stop*, plus the retention policy it named as missing. Production was read over HTTPS, GET
only, at 01:06 UTC on 2026-09-25 (commit `67706c1f356d`). Nothing was deployed, restarted or
reconfigured; every change here needs a deploy that the integrator performs.

The governing input is the owner's ruling of 2026-09-25, which resolves the contradiction the
audit found and could not resolve:

> "Keep the CA$4.00/day market_radar ceiling. Do NOT raise it to fit the existing cadence.
> Adapt/slow/prioritize the gallery cadence so it fits inside the existing authorized budget.
> **Global/monthly spend remains authoritative; per-agent ceilings are permissions, not
> additive budgets.**"

Everything below is built to that model. Twenty-four agents declaring about CA$57 a day
against a CA$100 month is **not** an over-commitment and nothing here treats it as one: the
month is the budget, an agent's day is a permission.

---

## 1. The gallery cadence now fits CA$4.00/day, and the rate is derived from the ceiling

**What was wrong.** `runtime/release.py` held `GALLERY_BATCH = 25` and `runtime/worker.py`
scheduled it two-hourly: three hundred images a day. `finance/spend_policy.ALLOCATION` stated
in its own comment that this costs CA$8.70 a day. `agents/registry.py` gave `market_radar`
CA$4.00 a day. Three numbers in three files, each defensible, and nothing reconciling them —
and nothing enforcing the smallest of them on that path at all.

**What was built.** The batch is no longer a number anywhere. `spend_policy.work_that_fits`
computes it every run from the agent's remaining daily ceiling and the cadence's own period,
read from `worker.cadence_seconds` — the table that schedules it. Change the ceiling in
`agents/registry.py` and the rate follows. Change the period in `worker.CADENCES` and the
per-run batch follows. Neither can drift from the other again because there is only one of
them.

* The per-image figure comes from `vision.per_image_estimate_cad()`, which is the *same*
  padded estimator `check_budget` enforces with — so the batch and the guard cannot be sized on
  different arithmetic. A test pins that they are byte-identical. Deliberately the padded
  estimate (CA$0.062) rather than the measured mean (CA$0.034): a batch sized on the average
  overshoots on the expensive half of it, and this build has been wrong about the image-token
  figure twice, both times optimistically.
* The divisor is runs-**per**-day, not runs-*left*-today. Two reasons, both in the docstring:
  the policy says in as many words that a ceiling is not a target, so an unspent morning must
  not license a burst at 22:00; and a batch is one job holding a five-minute lease, so a run
  that outlives its lease can be reclaimed and re-driven by another worker, which is duplicate
  spend arriving through the recovery path.
* It still adapts downwards, which is the direction that matters. `market_radar` also runs the
  culture sweep, the radar scans and the Etsy probe; when they spend, `remaining` falls and the
  rest of the day's batches get smaller rather than failing.

**The effect, measured against the real registry:** 5 images a run, 12 runs a day — **60 images
a day at about CA$3.74 of padded estimate and about CA$2.04 of measured cost**, inside a
CA$4.00 permission, with room left for the agent's other cadences. It was 300 a day. That is a
five-fold slowdown of the benchmark's visual evidence and it is what the authorised budget
buys; raising it is an owner decision about the ceiling, not a number to edit.

## 2. Per-agent ceilings now bind, before the call, as permissions

**What was wrong.** `Agent.daily_cost_ceiling_cad` was consulted in exactly one place
(`registry.record_cost`, used only by the model gateway) and bypassed by nine real spend paths
that write through `finance/spend_report.record`. `/api/verify` asserted only that a number was
configured. Production, 2026-09-24: `market_radar` averaged CA$3.94 a day against CA$4.00 with
nothing checking it.

**What was built.** `check_budget` takes `agent=` and checks it. Three things, in the order the
owner's ruling puts them in:

1. The **authorised monthly ceiling** — the budget. Counts the billed month, this caller's own
   unbilled spend, and every other caller's live reservation.
2. The **agent's daily ceiling** — a permission. Raises `AgentCeilingExceeded`, a *subclass* of
   `BudgetExceeded` so every one of the existing handlers still refuses, and so the two can be
   told apart where the difference matters.
3. Nothing else. A purpose's monthly share stays `spend_policy.may_spend`'s job, asked once per
   batch by the handler, because it is a stop rather than a rate and folding it in would
   re-decide it.

The refusal names the ceiling, says it is a permission and not the budget, states how much
month is left, says the work resumes at the next UTC day, and says what to do (lower the work,
or have the owner raise the agent's ceiling) — and never mentions a cheaper model.

Call sites now passing their agent: `intel/vision.py` (market_radar), `culture/classify.py`
(market_radar), `creative/reference.py` (creative_director), `gateway/image_bench.py::_judge`
(creative_director), and both probes in `gateway/anthropic.py` (gateway).

A spender with no `Agent` row gets **no invented ceiling**. Production attributes spend to
`gateway`, `publishing` and `intel`, none of which is a registered agent; enforcing a number
nobody authorised would be worse than the gap, and `spend_report.per_agent_today` already
reports them under `spenders_with_no_agent_row`.

## 3. A durable aggregate spend reservation

**What was wrong** (the audit's §5, left open as the only remaining unbounded overshoot): the
ceiling is read from `cost_entries`, a cost row is written *after* the provider answers, and
nothing was written down in between. Two processes reading CA$99 of a CA$100 month both find
room and both spend. Overshoot bounded only by (concurrent callers × largest estimate), and
`image_bench` can estimate double figures in one call. Several departments now run against one
database at once.

**What was built.** A `spend_reservations` table and `finance/reservations.py`.

* `check_budget` counts live reservations **from other holders** against the month, then writes
  its own reservation *before* returning, and returns its id. `release_reservation` gives it
  back with what the call actually cost.
* A caller does not reserve against itself: a batching loop already carries its own in-flight
  spend through `uncommitted_cad`, and counting both would refuse work the ceiling has room
  for.
* **Expiry is the whole safety argument.** A reservation carries the caller's bound on how long
  its call can take (300s default, above the 60s gateway timeout and the 120s image poll), and
  one past that bound counts for nothing. Railway replaces this container several times an
  hour, so a holder dying between claiming and spending is the normal case, not the unlucky
  one. The failure mode is a bounded over-reservation, never a permanent phantom charge.
* An expired-unreleased reservation is still **reported** — it is the evidence that a call site
  does not release what it takes. `reservations.sweep` marks it abandoned with the reason
  rather than tidying it away, and the `spend` health signal carries
  `reservations_expired_unreleased_cad`.
* Rows survive release, because a reservation beside the bill it became is the reconciliation
  the owner's spend-accounting instruction asked for and never had. Retention prunes them after
  48 hours.

## 4. Temporary-file lifecycle: all ten call sites

The call that left 29 GB and 37,284 directories in the suite's `/tmp` on 2026-09-20 was in ten
production handlers on cadences that repeat forever. Only frequent container replacement was
saving us. `core/workspace.work_dir` is the one pattern: it yields a supplied directory
untouched, and otherwise a `TemporaryDirectory` removed on the way out **including when the
body raises**, which is the path that leaked worst.

| site | how |
|---|---|
| `runtime/release.py` ops.continuity | block spans the retain, which reads the export file |
| `runtime/release.py` ops.offsite_archive | block is the archive call; the rest reads the database |
| `runtime/release.py` creative.model_tournament | block spans the whole run; the package is built from the renders |
| `runtime/release.py` assets.owned_photography | block is `make`, which stores what it keeps before returning |
| `runtime/release.py` creative.model_reference_pack | block is `build`, same reason |
| `publish/motif_fidelity.py::check` | owns its chart; deterministic from the CIR, so redrawn for nothing |
| `publish/motif_fidelity.py::chart_image` | **cannot** own it — the path is handed to `generate`. Writes into the caller's directory or returns "" |
| `core/offsite.py::archive` | block spans export, upload, read-back and restore proof |
| `gateway/images.py::generate` | **cannot** own it — the returned path must outlive the call. Now **refuses** without one |
| `app/main.py` /api/continuity/export | **cannot** own it — FileResponse streams after the handler returns. Cleans up in a `BackgroundTask` |

Three of the ten could not simply become a `with`, and saying why is the point: a directory
this function deletes on the way out is a path the caller cannot use. Where the bytes outlive
the call, the lifetime moved to whoever consumes them, and `images.generate` now refuses rather
than inventing a directory nobody owns. That refusal found the two callers production's
`generated-` directories actually came from — `images.reference_probe` (four times a day
through `ops.capability_probes`) and `image_bench.run` (thirty renders a candidate), both of
which now own their directory.

**The trap this nearly walked into.** Because `chart_image` can no longer invent a directory, a
caller with no `work_dir` would have received an empty chart path and gone on rendering: the
picture made, the record written, the fabric judged against nothing. A silent downgrade is worse
than the leak it replaced. So `publish/model_photography.sequence`, `.make` and
`publish/owned_photography.make` now create the directory themselves when nobody gives them one
— which is also correct on its own terms, since the sequence and the frame are what consume the
chart. A test pins that both modules do this, and that `chart_image("")` returns "" rather than
inventing anywhere to write.

`health.TEMP_PREFIXES` gained six prefixes that were already in production and uncounted, and a
test reads every `prefix="..."` out of `src/` and fails on one the disk signal has not heard
of. The signal, its threshold and its refusal to delete anything are all unchanged; its
docstring now says the count has changed meaning — it was an accumulation and is now a census
of work in flight plus whatever a dead process was holding.

## 5. Retention

**The horizon was the easy half.** The hard half is that several checks are *lifetime*
aggregates over `audit_log`, and a lifetime count over a pruned table is a different claim from
the one it says it is making. `ops/retention.py` is three rules, not one horizon:

1. **Protected actions are never deleted at any age**, each with the reader that makes it
   evidence. `store.published` and `store.publish_refused` (`/api/verify` counts both over all
   time; the second is what stops `nothing_published` passing by absence), `continuity.verified`
   (`scale.confidence`), `image.benchmark` and `image.reference_probe`
   (`image_bench.spent_to_date` **sums every row ever written** to enforce the owner's
   cumulative CA$50 — pruning these would rebuild the exact defect that cumulative rule was
   written to close), `model.frozen` and `design.provenance` (permanent provenance).
2. **The two most recent rows of every action survive**, protected or not, so none of the two
   dozen "latest row of this action" readers can be made to answer "never happened" by
   retention.
3. **Everything else goes after 90 days.**

`KNOWN_READ_ACTIONS` records every action the codebase reads by name and how it is read, and
`unknown_read_actions()` scans `src/` for action literals. `retention.apply` **refuses to run
at all** when it finds one it has no decision about, and a test fails on the same condition.
That is the check that matters in a year: the danger is not this policy, it is the next
lifetime aggregate somebody writes over a table that is now pruned.

Jobs: 45 days, which is arithmetic rather than taste — the scheduler's idempotency key is
`cadence:<name>:<now // period>`, the longest cadence period is `strategy_review` at 30 days,
and deleting the job that holds a key whose window is still open lets a spending cadence run
twice in one window. A test computes the longest period from `worker.CADENCES` and refuses a
horizon that does not clear it. A job is also kept if anything points at it
(`audit_log.job_id`, `cost_entries.job_id`, `spend_reservations.job_id` are real foreign keys),
if it is one of the three newest of its type (`build2.maturity`'s `jobs_seen` must not narrow),
or if deleting it would take the completed-job count below 1,000 — `scale.confidence` gates on
100 over all time, and retention must not be able to make a true claim false.

Dead letters: 90 days, **deliberate refusals only**, classified by the shared
`queue.durable.deliberate_refusal`. A defect is never pruned at any age. All 149 dead letters in
production are refusals working correctly.

`cost_entries` and the ledger are never touched: every ceiling in the company is computed from
those rows, and a retention policy that pruned the money would be a retention policy that
lowered a ceiling. That is asserted by a test.

`purge_dead` gained the same reference guard. It was called from nowhere, so this never bit; it
has a caller now, and a dead letter with a cost row against it is one foreign key away from an
integrity error.

Wired as `ops.retention`, daily, under `orchestrator` (permission added to `DEFAULT_AGENTS` in
the same commit — a cadence scheduled against an agent with no permission for it dead-letters
every time it fires, which is how the operational heartbeat dead-lettered every fifteen minutes
from the first boot). A refusal is recorded and returned rather than raised: "somebody added a
reader" is not a queue failure and should not become an incident with the wrong name on it.

---

## What this now refuses that it did not before

Each of these stops work that currently runs. That is intended.

1. **Gallery analysis judges 5 images a run instead of 25**, and judges none at all once
   `market_radar` has spent its day. Both are reported with the binding ceiling named
   (`agent_daily_ceiling` / `monthly_model_ceiling`) and with the backlog explicitly unchanged.
2. **Any call whose agent is over its daily ceiling is refused before the call**, through
   `AgentCeilingExceeded`, on six paths that previously had no per-agent check at all. On
   2026-09-24's figures `market_radar` at CA$3.94/day was within CA$0.06 of this — expect it to
   fire.
3. **A call is refused when other callers' live reservations plus the billed month would cross
   the ceiling.** Previously both callers were authorised and both spent.
4. **`images.generate` refuses a render with no `work_dir`.** No production caller is left that
   does this, but a future one gets an error instead of a slow disk failure.
5. **`retention.apply` refuses to delete anything** when the code reads an audit action the
   policy has no decision about.
6. `image_bench.run` no longer renders into a directory nobody owns; the directory is removed
   when the judging finishes.

## What needs a deploy (the integrator performs it, not me)

1. **Schema.** One new table, `spend_reservations`. `Database.create_all` creates it and
   `core/migrate.py` is additive, so no manual migration — but the first boot after deploy is
   where it appears, and until then `check_budget` would raise on a missing table. Deploy is
   the only step.
2. **Expected visible changes after deploy.**
   `/api/status`: gallery analysis runs report `batch_units` (about 5) and `binding_ceiling`.
   `/api/health-signals`: the `spend` signal gains `reserved_but_not_yet_billed_cad`,
   `reservations_live` and `reservations_expired_unreleased_cad`.
   A new daily `ops.retention` job and an `ops.retention` audit row. **Its first run will delete
   a large number of audit rows at once** — about 4,700 a day accumulated since the audit log
   began, minus everything protected. It is bounded and it is one transaction; if it times out,
   the second run takes the rest.
3. **Watch `reservations_expired_unreleased_cad` for the first day.** Anything but zero is a
   call site that takes a reservation and does not release it. The one I know of is
   `visual/inspect.py` (below); anything else is a bug in what I wrote.
4. **Owner-visible consequence, no decision required.** The benchmark's visual evidence now
   completes about five times more slowly. That is what CA$4.00/day buys and the owner has
   already ruled on it. If the evidence is wanted sooner the lever is the ceiling in
   `agents/registry.py`, and the cadence will follow it without another code change.

## Left for the departments that own the files

* **`visual/inspect.py:246`** — two things, both one line, owned by Visual:
  pass `agent="quality_director", purpose="asset_inspection"` so the daily ceiling binds
  (`asset_inspection` is CA$8.84 this month across 504 calls), and release the reservation
  `check_budget` now returns (`gw.release_reservation(db, ...["reservation_id"], actual_cad=...)`)
  so it is not held for its full TTL. Without the release the mechanism still works — the
  reservation expires — but it holds budget nobody is spending for up to five minutes.
* **`visual/model_registry.py`, `visual/photoreal.py`, `visual/tournament.py`,
  `visual/bible.py`** — these write through `spend_report.record` and do not call
  `check_budget` at all, so they are not ceiling-checked before the call by anything. Same
  shape as the audit's §2, in files I must not touch this session.
* **`runtime/release.py`** — I hold six edits in this file (four temp-directory conversions, the
  image-benchmark call, the gallery handler, the new retention handler). Deliverable QA II may
  also be in it. I did not collide with anything while working, but this is the merge to review
  first.

## One thing I changed that was not asked for, and why

`registry.spend_today` took no timestamp: it read the wall clock. That was harmless while it was
only called after the fact, and it stopped being harmless the moment it became half of a pre-call
guard — `check_budget` takes a `now` and would have computed the month from the caller's instant
and the agent's day from the host's clock. Two clocks, one question, agreeing only while the
frozen date happens to be today. It takes `now` now, defaulting to `utcnow()`, and a test asks it
about a day that is deliberately neither today nor the day of the rows.

## Tests

`brambleloop/tests/test_cost_governance_wave2.py` — 39 tests, all passing. Every one names the
production reading or the owner ruling it comes from.

Suites re-run green (targeted, not the full suite — `run_tests.sh` is the 1,133-second suite
and deploys are serialised this session). Chosen by grepping `tests/` for every consumer of
what this branch touches (`check_budget`, `record_cost`, `spend_today`, `purge_dead`,
`images.generate`, `image_bench.run`, `chart_image`, `health.*`, `/api/status`, `/api/verify`,
`spend_policy.*`) plus the gates, chaos and deploy suites that exercise them end to end:

```
test_cost_governance_wave2 39   test_image_bench 59        test_model_photography 44
test_engine 41                  test_intel 38              test_spend_governance 35
test_health 34                  test_executor 34           test_deploy 32
test_gateway 30                 test_owned_photography 30  test_chaos 25
test_spend_policy 24            test_acceptance_gates 23   test_platform 22
test_reliability 17             test_governor 16           test_finance 16
test_defects 16                 test_clusters 15           test_continuity 15
test_seasonal_cycle 15          test_offsite 14            test_model_provider 12
test_motif_fidelity 11          test_visual 10             test_persistence 10
test_swarm 6
```

Twenty-eight suites, 0 failing. Two pre-existing checks moved, and in both cases the *check* was
pinning the wrong property while the change was right:

* `test_motif_fidelity.py::test_the_comparison_is_against_the_chart_rather_than_a_sentence`
  asserted the chart file existed *after* `check` returned. Its stated property — that the judge
  compared against a chart rather than a sentence — is true or false at the moment the judge is
  handed it, and the old position additionally pinned that the chart outlives the comparison,
  which is the leak. The assertion moved inside the judger, where it is the stronger test: it
  proves the judge got a file rather than a path. Every other assertion is verbatim, and a new
  one pins `chart_retained: False`.
* `test_model_photography.py::test_every_frame_in_the_sequence_sees_the_chart` failed because
  `sequence` was being called without a `work_dir` and had been relying on `mkdtemp`. The fix
  was in the code, not the check: `sequence` now owns a directory. The test is unchanged.

Three checks in `tests/test_image_bench.py` were re-run rather than changed for the same reason:
the first version of the `image_bench` change made `run` refuse without a caller-supplied
directory, those three failed, and **the design was wrong rather than the checks** — the renders
are consumed inside `run`, so the lifetime belongs there. `run` now owns the directory and all
three pass untouched.

No threshold was lowered and no existing check was removed.
