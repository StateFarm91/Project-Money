# Rule #1 output audit — what the autonomous departments actually produced (W4-AUTO)

As of 2026-10-07 (UTC). Basis: **measured**. Read-only GETs of production
(`/api/status`, `/api/jobs?limit=20000`, `/api/queue/cadences`, `/api/catalogue`, `/api/audit`)
and bounded local shadow proofs (`python -m brambleloop.autonomy.proof`, temp SQLite, network
closed, no credentials). Machine-readable twin: `RULE1_OUTPUT_AUDIT.json`. Judge:
`runtime.pipeline.did_no_work`; "business output" additionally excludes heartbeats, probes,
infrastructure, flags and repeats. Nothing here was enqueued, published, sent or spent.

## 1. Production (what really exists)

Production runs **fcb982d** (built 2026-09-25, 678 commits behind this branch), phase SHADOW.

| Measure | Value |
|---|---|
| Jobs recorded | 9,882 (56 job types) |
| Excluded as heartbeat / health / probe / infra | 5,254 (53%) — ops.heartbeat 1,866, ops.health 1,600, ops.queue_check 467, build.tick 428, ops.sentinel 401, … |
| Refused by design (shadow) | store.publish 165 dead letters — the guard working, not output |
| Remaining company-work jobs | 4,463 |
| Certified pattern versions (deterministic CIR → compile → certify) | **15** |
| Draft listings | 16 rows, **15 distinct** (`nordic-forest-bundle` duplicated) |
| Published listings / customers / orders / revenue | **0 / 0 / 0 / CA$0.00** |
| Agent opex to date | CA$76.40 (LLM) |
| Owner actions open | 9 |

**Durable company output (lifetime):** 15 certified patterns with PDFs (assets.build), 15 draft
listings with SEO/pricing/launch plans, a market-radar pool of 34 scored opportunities (11
selected), MJs benchmark observation of 441 listings and 100 reviews read, daily culture-demand
readings (10/day, Wikimedia), seasonal milestone assessments (56 on track / 4 at risk / 30
missed), monthly P&L reconciliation, 3 verified database archives, an image-model benchmark
decision (nano-banana-2) from earlier spend.

**Repetition, not output:** chain.rebuild 474, creative.image_benchmark 422,
creative.model_reference_pack 396, creative.model_tournament 377, radar.score 319,
assets.owned_photography 227, intel.gallery_analysis 213, improve.role_work 144 — each
re-runs on an hourly/daily cadence and, in the latest cycle, reports nothing new or refuses.

### Latest cycle of every production cadence (46)

* Judged useful by the current judge: **15/46 (33%)**.
* Business output after excluding infra, flags and repeats: **8/46 (17%)** — radar.scan,
  portfolio.review, improve.nightly (incomplete), seasonal.sentinel, mjs.scan (131 new
  listings seen), mjs.reviews, seasonal.remerchandising (45 ready moves), culture.sweep.
* No-ops and why (external, not discovery): **Anthropic credit balance exhausted** →
  model.probe, seasonal.cycle_proof, creative.tournament/expedition and all vision work
  (intel.gallery_analysis) refuse; **image generation not demonstrated** →
  assets.owned/model_photography; no `BRAMBLELOOP_ARCHIVE_URL` / browser URL; owner rejected
  model-tournament finalists (waits for owner); creative.blinded below its 12-pair floor;
  improve.role_work ×8 read 0 rows (nothing routed to learn from); Learn produced nothing.

## 2. Why the owner dashboard shows QUEUE PENDING 0 / RUNNING 0

**Both, for different reasons — and the dominant one is a deploy gap, not shadow mode.**

1. **Work-discovery defect in the deployed build.** fcb982d predates the autonomy orchestrator
   (`autonomy.orchestrate`, every 15 min, generators per department). It has 46 fixed
   cadences and nothing that discovers work between ticks, so the queue drains in seconds
   after each tick and sits at 0/0. This branch has 112 cadences plus the orchestrator; a
   fresh 10-minute shadow run ends with ~68 jobs still pending (see §3). Closing it is a
   deploy (integrator) — not a capability graduation.
2. **External blockers make most cadence runs no-ops** (credits, image generation, archive /
   browser configuration) — OWNER ACTION #19/#20 already open (add Anthropic credit; the
   CA$100/month ceiling is enforced in code).
3. **Shadow by design (legitimate idle):** store.publish refusals, Support (no customers),
   Finance revenue lines (no orders), ads (no authority). These are not defects and were not
   "fixed" by flipping shadow → live or by busywork.

## 3. Local shadow proofs, before → after (this branch)

Bounded 10-minute runs of the real embedded runner (worker + scheduler), shadow, no network.

| Run | Commit | Done | Useful | Useful rate | Distinct-useful rate |
|---|---|---|---|---|---|
| before (16 min, pre-merge) | fee1cfe | 220 | 99 | 45.0% | n/a |
| before2 (10 min, post-INTEG) | fc7ed8e | 175 | 95 | 54.3% | 53.7% |
| after (10 min) | ea368fd | 258 | 136 | 52.7% | 49.2% |

Per department (before2 → after useful rate): executive 31.2% → 63.6%; finance 25.0% → 16.7%; growth 66.7% → 45.5%; intelligence 54.2% → 48.3%; learn UNKNOWN → 33.3%; platform 25.0% → 36.0%; product_design 0.0% → 40.6%; product_truth 61.1% → 61.7%; store_commerce 88.9% → 78.6%; support 0.0% → 0.0%; visual 76.9% → 61.1%. Departments idle with eligible untaken work at end (rule1_defect): none. Final queue: 261 done, 49 pending, 1 running, 2 dead (was 175 / 68 / 1 / 2). Throughput +47% (258 vs 175 judged done in the same 10 min); the overall useful rate is flat (54.3% → 52.7%) because the extra throughput is new departments' first runs (learn now works inside the window: UNKNOWN → 33.3%) and judged honest no-ops, not busywork. Product & Design 0% → 40.6% is the cir.draft judge fix. The per-department drops (growth, visual, store) are fewer *repeats* of the same plans inside the window, not lost output.

Dead letters in the after run: 1 shadow refusal (store.publish, by design) and 2 **defects found by this proof** — `creative.candidates_file` and `swarm.allocate` were dead-lettered by the provenance backstop for market-basket-small's listing copy, which a concurrent `listing.seo` (52 s, another runner lane) was writing in the same window. Fixed (cause #7).

### Causes found and fixed

| # | Cause | Kind | Fix |
|---|---|---|---|
| 1 | `cir.draft` declared work key `drafted`, but its engineered and fallback success paths never set it → **Product & Design judged 0% useful** although it drafted every CIR | judge/handler defect | success paths return `drafted: True` |
| 2 | `gate.certify` counted only `granted`; deterministic refusals (UNCALIBRATED_PRIMITIVE, GAUGE_OUTSIDE_DECLARED_YARN_BAND) were judged no-ops | judge defect | WORK_KEYS += `reasons` (refusal = QA output; repeats dedupe) |
| 3 | `launch.plan` undeclared → dated launch plan + publish/marketing hand-off invisible | judge defect | WORK_KEYS `launch_on`, `held`, `withheld` |
| 4 | mjs.scan findings synthesis (W4-MJS) not counted | wiring | WORK_KEYS += `findings.changed` (unchanged digests / errors do not count) |
| 5 | `store.live_drift` (W4-STORE) had no cadence → never ran by itself | discovery | daily orchestrator cadence after `etsy_shop_snapshot`, registry + WORK_KEYS |
| 6 | visual.rnd.cycle launch-imagery refresh (W4-VISUAL) not counted | wiring | `imagery_refreshed` in work_done |
| 7 | Provenance backstop is time-windowed (C-52) but workers run concurrently (runner lanes): slug-less jobs were dead-lettered for another product job's artefacts | attribution defect | `runtime.worker.concurrent_attribution`: an artefact is set aside only when another job for the same product overlapped the window (its own backstop checks it); all else still enforced. tests/test_w4_auto_provenance_concurrency.py |
| 8 | `ops.maturity_disagreements` (~80 s read-only) claimed ahead of release-chain work at boot (W4-CHAIN residual) | scheduling | housekeeping band + first run deferred 10 min after process start (`BOOT_DEFERRED_SECONDS`); 240 s stall detector unchanged |

### Not defects (left alone, with reasons)

* **Learn 0 done in 10 min:** boot burst — every cadence enqueues at boot and the product
  pipeline (higher band) holds the single worker; bounded aging (C-15, 600 s/step) lets learn
  work through. Starvation is bounded, not a discovery failure.
* **No department ended idle with eligible untaken work** (`rule1_defect` false for all 11);
  Support ended idle with no eligible work — shadow-by-design (no customers).
* `gate.lanes`, `collection.assemble` refusals, `creative.blind_review` (all `unknown`),
  `ops.sentinel` with 0 checked — honest no-ops, judged as such.

## 4. Per-agent visibility (lane CC)

`brambleloop.autonomy.status.agents(db)` returns, per agent: state
(active/sleeping/blocked/unhealthy), doing-now, started_at, current job and why, last useful
result with produced/rejected keys, last run, blockers (department block, owner gate, dead
letters), next work, next wake and trigger, completed/useful/no-op/dead counts and rates
(UNKNOWN when nothing completed, never 0), cost, as_of. WIRING REQUEST to lane CC: register it
as provider `"agents"` in `app/command_center/providers.py`.
