# Owner report: competitive intelligence and autonomous learning, reconciled

- **Date:** 2026-10-26 (UTC). Prepared on branch `claude/w4-INTELREC`.
- **Branches and builds:**
  - INTELREC is cut from `claude/w4-INTEG7` at 67920948, the combined candidate.
  - Production runs **b2e49455**, which is 051dbee2 plus SECPATCH.
  - The FMBATCH1 and AGENTS work is in the combined candidate only.
  - INTELREC batch 4a (876b4fee) and batch 4b (dd04c40f) are **unreviewed and not deployed**.
- **Companion files** (all in `research/final_build/w4/intel/`): `TRACEABILITY.md`/`.json`, `FOUR_SHOP_COMPARISON.md`, `REMEDIATION_LEDGER.md`, `ACCEPTANCE_PLAN.md`, `evidence/`, and `intel_reconciliation.py`, the generator.

**How production evidence was gathered.** No token was used. The sources are:

- the anonymous production captures taken earlier today, before SECPATCH closed the routes (`evidence/`):
  - `/api/jobs` at 17:24Z (33,776 jobs, ids and status only);
  - `/api/benchmark-selection` at 13:56Z;
  - `/api/etsy` on 2026-10-19;
- `MJS_FINDINGS.md`, read from production's public endpoints on 2026-10-07;
- Railway deploy logs, read-only. They contain container start and stop lines and HTTP lines only; **no job execution is logged there**, so they add no evidence.

Everything else is marked **needs operator readback**. `ACCEPTANCE_PLAN.md` lists those reads.

---

## 0. Answers first

| # | Question | Verdict | Evidence |
|---|---|---|---|
| 1 | Mrs J monitoring fully built | **PARTIAL** | Built and running: the catalogue scan, change detection, the mission, reviews, the seasonal sentinel, pod learning, URL health. Not done: #304 visual study is parked on browser_vision; #320 end-to-end acceptance is OWNER-GATED (`acceptance_ruling`); #318 dashboard; F-224 open. |
| 2 | MadelineMaeCo fully built | **PARTIAL (new today)** | Absent from every spec, registry, DECISION_LOG entry, code path and branch before INTELREC. It is now registered with the special role and the same scan and mission as Mrs J (876b4fee), but unreviewed and undeployed. |
| 3 | Both monitored in production today | **Mrs J YES; MadelineMaeCo NO** | `mjs.scan` executed 266 times, the last at job 33702 (near head 33776, 17:24Z). The 13:56Z reading shows 442 listings observed through the official API. MadelineMaeCo is not in production. |
| 4 | ZKBDESIGNER and TheEasyDesign fully integrated | **PARTIAL** | Registered, scanned, compared and routed to decisions on INTELREC, with offline tests only. Not deployed and not reviewed, so they have no production observation. |
| 5 | Trend radar works | **PARTIAL** | The culture radar (`culture.sweep`, 37 runs), radar scan and score (211 and 544), seasonal engine and harvest (16 each) and SERP capture (16) all execute. The trend-provenance discount is live (#38 PROVEN). The "trending crochet patterns" search page itself is reachable only through the browser boundary, and Etsy refuses that with 403. Whether these runs produced useful signals needs readback. |
| 6 | Product Family Engine works | **NO in production; PARTIAL in code** | `creative.family_engine` exists in the combined candidate only, with 0 production runs. It reads families, bundle readiness and recolour duplicates. INTELREC 4b makes it delegate follow-ons. Amplification stays UNMEASURED below 5 orders, and production has no orders. |
| 7 | Winner Amplification works | **NO in production; PARTIAL in code** | There are no orders, so no winner can be detected. INTELREC 4b wires this, offline-tested only: winner → original follow-on (radar.score → pre-engineering gate → cir.draft, or a divergent tournament) → measured follow-on orders → hold after two empty attempts. Investigation of why the best seller sells now calls `commerce.replication.study` (bounded study and ranked testable causes; below its 30-order, 4-week floor it records the module's own refusal). The follow-on brief carries the causes to hold. **Still missing:** price and merchandising tests (owner-gated #295 / live listings). See §3. |
| 8 | Laura uses the intelligence | **NO in production; built on INTELREC** | Production Laura (`laura.executive_tick`, 4,352 deterministic runs) has seven providers, none of them intelligence. INTELREC adds the `intelligence` provider and the delegated `intel.opportunity_review`. Laura's model-backed CEO paths are OFF (`BRAMBLELOOP_LAURA_CEO_MODEL`, default OFF). The deterministic tick does not need the model. |
| 9 | Agents create original products from it | **PARTIAL, stalled** | Competitor evidence drives original divergent tournaments (`creative.tournament`, 191 runs, last 33597). No tournament has reached engineering since `cir.draft` job 24731, and 0 `cir.draft` have run since. The reason sits in `creative.winner_intake` audit rows (needs readback). |
| 10 | The company learns and improves | **PARTIAL** | Lessons are published, and `radar.score` acts on them (544 runs). Also running: `improve.mine` 117, `improve.measure` 32, `creative.outcome_learning` 16, `learn.scan` 364. No production record yet shows a lesson changing a product outcome: there is no measured outcome, because there are no live listings and no orders. `improve.weekly` dead-lettered once; the PRODFIX2 fix is pending deploy. |
| 11 | Engineering-complete % | **71.3%** | 72 of 101 traced requirements are implemented, tested and integrated (TRACEABILITY). |
| 12 | Production-verified % | **15.8% by record; 0% by acceptance readback** | 16 of 101 have a production execution record, a valid output reading and a PROVEN ledger row. All 16 are Mrs J catalogue rows. None has been verified end to end against its acceptance text by an operator readback in this reconciliation. |
| 13 | Exact remaining work | See §7 | Also `REMEDIATION_LEDGER.md`. |

---

## 1. Per shop

The permitted competitor figures are in `FOUR_SHOP_COMPARISON.md`.

### 1.1 Mrs J (MJsOffTheHookDesigns): the anchor

**Registration and agent.**

- Permanent target: yes. `intel/benchmarks.MJS` with `mandatory=True`. The owner-supplied URL is kept verbatim, per #301.
- Agent: `market_radar`, in the Intelligence charter.

**Fields collected.**

| Data | Source / job | Grade |
|---|---|---|
| title, price, `is_sale`, tags, materials, state, last-modified, favourites, taxonomy, options and variations, deliverable facts, size range | `intel/observe.py`, fingerprint over the commercial fields | MEASURED (official API) |
| gallery image URLs and count | listing images | MEASURED (official API) |
| pod and category | our routing | DERIVED |
| review complaint themes, counted | `mjs.reviews` | DERIVED |
| image judgements | `intel.gallery_analysis` | vision, inside the ceiling |

**Frequency.**

| Job | Cadence |
|---|---|
| `mjs.scan` | 2-hourly floor, with the adaptive interval (#213/#313) |
| `mjs.reviews` | weekly |
| gallery analysis | 2-hourly |
| benchmark health, pod learning, seasonal sentinel, SERP capture | daily |

**Last successful collection.**

- `mjs.scan` job 33702 completed. That is near head 33776 at 17:24Z [`evidence/prod_job_counts…`].
- The reading at 13:56Z: 442 listings observed [`evidence/prod_benchmark_selection…`].
- Reviews: `mjs.reviews` job 27005, 7 runs in total.

**Access and history.**

- Access is the official Etsy Open API v3 only. The credential was demonstrated on 2026-10-19.
- History retained: `BenchmarkListing` (first and last seen, per-row detail), `BenchmarkObservation` (dated), `MjsMissionEvent`, and the daily `mjs.findings` readings.

**What is tracked.**

- New and removed listings: detected by fingerprint diff (`new listing`, `materially changed`, `no longer listed`).
- Price and promotions: tracked. 0 of 441 were on sale on 2026-10-07.
- Catalogue and families: tracked by pods and options.
- Reviews and sentiment: themes counted weekly.
- Seasonal trends: `mjs.seasonal_sentinel` (#311) and the seasonal benchmark matrix.

**Outage, freshness and uncertainty.**

- An unconfigured credential gives `ran: false` plus the requirements left unmet (#224).
- A refused credential waits for `etsy.probe` and does not retry into a dead letter.
- Rate limits and server faults are left to the job's retries.
- Scan health is recorded per benchmark.

**Do findings become opportunities?** Yes, through two paths:

- the mission's coverage gaps and divergent tournaments;
- `mjs.findings` lessons, which `radar.score` consumes.

They have not become engineered products since job 24731 (§2).

**What is observable, inferred or unavailable.**

- Observable: catalogue, price, sale flag, tags, favourites, gallery counts, review themes.
- Inferred: categories, seasonality, positioning.
- Unavailable: revenue, conversion, rendered search position, off-Etsy channels.

### 1.2 MadelineMaeCo: special monitoring

**Registration and agent.**

- Before INTELREC, MadelineMaeCo was named nowhere: not in any spec, the registry, DECISION_LOG, code or any branch. I searched every ref.
- So no "original special monitoring" ever existed to keep. It is restored from today's directive: `intel/watchlist.WATCHLIST` (role `special`) and `benchmarks.MADELINE` (`mandatory=True`).
- Agent: `market_radar`. Job: `intel.watchlist_scan`, 6-hourly with an adaptive per-shop interval.

**Fields collected.** The same as Mrs J, plus the `findShops` public counters: `transaction_sold_count`, `review_count`, `review_average`, `num_favorers` and `listing_active_count`. The full map is in `intel/watchlist.SCOPE`.

**Last collection:** none. It is not deployed.

**Outage handling.**

- A failed read is recorded per shop as `source_outage` or `credential_refused`, with a consecutive-failure count. Other shops continue.
- Laura sees an outage after 2 failures, and stale data after 48 h.

**Do findings become opportunities?** Yes. Arenas corroborated by two or more watchlist shops enter the coverage-gap queue, and Laura delegates a decision on each. This is offline-tested only.

**Vision.** Image-level judgement is not run for this shop. It stays anchor-only, inside `market_radar`'s ceiling. Widening it is an owner spend decision.

### 1.3 ZKBDESIGNER and 1.4 TheEasyDesign: permanent benchmarks

- They have the same mechanism as MadelineMaeCo, with role `permanent`. The owner's `/ca/shop/` URLs are kept verbatim.
- Last collection: none (not deployed).
- AI-operation is never assumed. The comparison carries an `ai_use` slot with assessment UNKNOWN and hypothesis-only. No evidence collector exists for it, and none is claimed.

### 1.5 The original seed shops (spec/05)

**What the spec required of all of them.** `spec/05_Competitor_and_Market_Seeds.txt` says, verbatim:

> "Use these as initial research targets, not designs to copy."

It then lists HanJanCrochet, IvyLoop, MJsOffTheHookDesigns, LoveandStitchDesigns and FireflyCrochets, with example listings, plus the crochet-pattern search seed. The ten research objectives are:

- category mix and whitespace;
- release cadence and seasonality;
- product ladders and bundles;
- regular vs promotional pricing observations;
- first-image/thumbnail patterns;
- use of recurring human models;
- PDF + video positioning;
- reviews: delight, confusion, missing features;
- external traffic/content ecosystems;
- bestseller/trending signals where publicly visible.

The spec adds: "do NOT copy protected designs, charts, text or photography".

**No ledger row** carries the seed list (TRACEABILITY `SEEDS-05`, plus one row per shop). The spec calls them *initial* research targets, not permanent monitoring targets. Only Mrs J was later made permanent, by #301.

| Seed | Registered today? | Monitored today? | Evidence | Restoration proposal (owner decision; no code added) |
|---|---|---|---|---|
| **HanJanCrochet** | Not in the code registry. A **second-market candidate** (`intel/second_market.CANDIDATES`, decision D-W4-GATESB-1, UK market), which `intel.panel_discovery` joins once `getShop` verifies its stated location. | **Possibly, weekly.** `intel.panel_discovery` ran 3 times in production (last job 27000) and scans every joined panel member. The `second_market_benchmark` gate reads **open** at 17:24Z (`evidence/prod_gates_…`). That means observed listings exist for two or more stated markets, so some non-US shop is observed. **Whether that is HanJanCrochet, or LakesideLoops (the Canadian candidate), needs readback** of the `Benchmark` rows or the `intel.panel_discovery` audit. | Also a dated static profile in `radar/market.COMPETITORS`, observed 2026-09-17: overlay-mosaic blankets, a pattern-plus-video format, a 50% display discount with a timer, "Bestseller… 200+ bought in the last week", 8.4k reviews on the hero listing. It is read by `commerce.pricing_intel` and by `seo.truth`'s competitor-name refusal. | Option A: add it to the permanent watchlist (role `seed`; one `Member` line plus one registry spec, the same mechanism as ZKBDESIGNER). Option B: keep it as a panel or second-market member, observed weekly as now. |
| **IvyLoop** | No | **No** | `radar/market.COMPETITORS` says "Seeded by owner; profile to be filled on first live scan" and "Not yet observed". | Option A: add it to the watchlist. Option B: leave it to panel discovery, which joins category leaders from the API search index. Option C: close the seed with a recorded owner decision. |
| **LoveandStitchDesigns** | No | **No** | A dated static profile only, observed 2026-09-17: everyday garments, a recurring human model, a 55% display discount from about CA$22. It is read by pricing intel and the SEO name refusal. | As IvyLoop. |
| **FireflyCrochets** | No | **No** | A dated static profile only, observed 2026-09-17: character amigurumi at CA$2.75–8.78, frequent deep discounts. | As IvyLoop. |
| **MJsOffTheHookDesigns** | Yes. It became the #301 anchor. | Yes (§1.1) | `mjs.scan`: 266 runs | — |
| **Search seed** (crochet pattern, star seller) | n/a | **Partly.** The rendered page answers software with 403 (B-268, B-500). The sanctioned substitute, the API search index, runs as `intel.serp_capture` (16 production runs, PROXY-labelled). | `intel/serp.py`, `MARKETINTEL.md` | Keep as it is. The rendered page stays a browser-boundary item. |

**Proposal for the owner.**

- Decide per shop whether HanJanCrochet, IvyLoop, LoveandStitchDesigns and FireflyCrochets rejoin the permanent watchlist.
- If yes, the change is one `Member` and one `BenchmarkSpec` each, plus a test. They then get the same scan, comparison and Laura chain as the new watchlist shops.
- Nothing has been added to monitoring code. This is the owner's call.

**A correction to an earlier statement.** The code-declared registry at production b2e49455 is Mrs J only. But the elite panel in production is **not** necessarily one seller: panel discovery joins members from evidence, and the second-market gate is open. "Three of the four watchlist shops are unobserved" stands. "The panel has one member" does not.

---

## 2. Chain trace

The production evidence is the 17:24Z job capture. "Offline" marks something exercised only by tests.

| # | Transition | Agent / service | Trigger | Input → output | Record | Permission | Code | Tests | Production evidence | Failure handling |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Observation | market_radar: `mjs.scan` (Mrs J); `intel.watchlist_scan` (others, INTELREC) | cadence | API listings → `BenchmarkListing` and observations | `benchmark_listings`, `benchmark_observations`, audit `mjs.scanned` | registry `market_radar`; authority GREEN | `intel/observe.py`, `intel/watchlist.py` | `test_cert_mjs`, `test_w4_intelrec_watchlist` (offline) | Mrs J: 266 runs, last 33702. Others: none. | credential refusal waits for the probe; per-shop outage recorded |
| 2 | Market Intelligence | market_radar: mission pipeline, director and pods | inside the scan | new or changed listing → mission event, decomposition, panel gate, coverage gap, tournament | `mjs_mission_events`, `coverage_gaps` | same | `intel/mission_runtime.py` | `test_cert_mjs` | scans run; event counts need readback | duplicate-suppressed by event fingerprint |
| 3 | Research Agent | research_agent: `research.sweep` / `research.investigate` | unknowns and due tasks; INTELREC 4b: every validated watchlist arena | unknown → research task → internal evidence; the arena question is cited on the opportunity decision | `research_tasks` | combined candidate | `intel/research_agent.py`, `intel/watchlist._research_question` | `test_w4_research_agent`; offline test | **0 runs (not deployed)** | deduped on the trigger; research never blocks the comparison |
| 4 | Opportunity validation | mission `arena_demand` / panel `may_enter`; INTELREC cross-shop corroboration | scan; `intel.watchlist_compare` daily | stored rows → proven arena or validated gap | `coverage_gaps.evidence` | GREEN | `intel/panel.py`, `intel/watchlist.compare` | `test_cert_mjs`; offline test | MJs arenas: needs readback. Watchlist: none. | an unknown is not zero |
| 5 | Laura | `laura.executive_tick` (deterministic) | 5-minute cadence | providers → priorities → delegation | `laura.memory`, timeline, missions | constitution | `laura/executive/loop.py` | `test_w3_laura_core_executive`; offline test | 4,352 runs, **but no intelligence provider in production**. **This is where the chain breaks today.** | one provider failing never stops her |
| 6 | Delegation | COO mission → `intel.opportunity_review` (INTELREC) | Laura priority (provider DEGRADED) | gap → decision record + job | `intel:opportunity:<gap>` memory | charter generatable and SAFE_GENERATED | `intel/watchlist.review` | offline test | none | idempotent per attempt; ≤3 per run |
| 7 | Product development | creative_director: `creative.tournament` → intake → crochet_engineer `cir.draft` | mission, concepting, or review | brief → candidates → pre-engineering gate → CIR | `creative.winner_intake` audit, `jobs` | ceilings (paid) | `creative/intake.py`, `runtime/release.py` | `test_cert_mjs`, intake suites | tournaments: 191, last 33597. **`cir.draft` last 24731**, 0 since. **Second break.** | WAITING or REFUSED with reasons (needs readback) |
| 8 | Certification | quality_director `gate.certify` | after `cir.draft` | CIR → certificate | `pattern_versions` | deterministic gate | `gates/*` | release suites | 102 runs, last 24735 | rebuild deadlock fixed in PRODFIX (pending deploy) |
| 9 | Visual production | publishing `assets.*` | release chain | release → frames/photography | `listing_assets` | ceilings | `runtime/release.py` | visual suites | owned 313 (last 33592), model 78 (last 33593), build 201 (last 13530) | paid-call guard |
| 10 | Marketing and growth | `marketing.schedule`, `growth.steer` | release chain | content drafts | `content_pieces` | SHADOW: drafts only | `growth/*` | growth suites | schedule 171 (last 23462), steer 46 (last 33450) | halted by stale artefacts (PRODFIX) |
| 11 | Etsy ops | `store.publish` | release chain | listing → Etsy | — | **SHADOW refuses**; owner grants | `runtime/etsy_ops.py` | publish suites | 186 refusals (dead, by design) | **activation gate: phase plus owner grant** |
| 12 | Measurement | `listing.outcomes`, `commerce.orders_ingest` | daily | orders and traffic → readings | `orders`, readings | GREEN | `commerce/*` | outcome suites | 16 and 62 runs; **0 orders** | UNMEASURED, never 0 |
| 13 | Learning | `creative.outcome_learning`, `improve.mine` / `measure` / `weekly`, the lesson bus | daily / weekly | outcomes → lessons | `lessons` | Product Truth floors are not tunable | `improve/*` | improve suites | 16, 117, 32, and `improve.weekly` 6 (1 dead) | `improve.weekly` fix in PRODFIX2 |
| 14 | Next opportunity | `radar.score` lesson nudge; INTELREC lesson deferral | per score or review | lesson → score or decision change | `bus.acted_on` | bounded nudge | `improve/consume.py` | `test_w4_mjs_findings`; offline test | 544 `radar.score` runs; acted-on counts need readback | — |

**Where the chain stops.**

1. **Today in production, at step 5.** Laura never observes competitor intelligence.
2. **At step 7.** No tournament has reached engineering since job 24731.
3. **At step 11.** SHADOW plus owner grants, by design.
4. **At step 12.** No orders.

The deterministic Laura tick runs. Her model paths are OFF. INTELREC adds the step-5 link, and it **activates only when INTELREC is reviewed and deployed**. That is the activation gate.

---

## 3. Quality and commercial intelligence

| Can the system distinguish… | Mechanism | Status |
|---|---|---|
| genuine demand vs passing trends | culture `score.py` (saturation and timing, #145), `demand.py` lead-lag (#140), trend provenance discount (#38), seasonal breakout mining (#128) | code deployed, jobs run. Lead-lag at one shop is honest about being one shop; it gets a real cross-shop answer only once the watchlist is scanned |
| originals vs recolours | `creative/preengineering.py` novelty floor ("near-clone or recolour" refused); `creative/family.py` (a family whose members differ only by palette is refused) | deployed, deterministic |
| strong vs weak families | `creative/family_engine.py` | combined candidate only, and UNMEASURED below 5 orders: **cannot yet** |
| profitable opportunities vs costly experiments | `commerce/attribution.py` (contribution, not revenue, #45); spend ceilings | contribution needs orders: **cannot yet in production** |
| successes vs too little traffic | `creative/outcome_learning.py` `MIN_VISITS = 200` (below it, UNMEASURED) | deployed; no traffic yet |
| verified vs unmeasured feedback | review themes counted (never quoted); support cases; UNMEASURED labels throughout | deployed |

**Winner Amplification, step by step.** It does not operate end to end.

1. **Detect a winner.** `commerce/attribution` and `family_engine` (combined only) need orders, and there are 0. **Missing: a production order source.**
2. **Investigate why.** `commerce/replication.py` (#22) is deployed and PROVEN, but has never been triggered, for lack of a winner. **Built on INTELREC (offline-tested):** `family_engine.investigate` builds the SKU catalogue from certified rows, orders and the pool's declared traits, then calls `replication.study` for the family's best seller. A credible winner gets a bounded study with ranked, testable explanations, which the follow-on brief carries as `amplify_holds`. Below the winner floor, the refusal is recorded in the module's own words and no cause is guessed.
3. **Delegate original related designs.** **Built on INTELREC 4b (dd04c40f, offline-tested).** `family_engine.amplify` sends the next declared member through `radar.score` and the pre-engineering gate, whose novelty floor refuses a recolour. With no declared member, it briefs an original divergent tournament. One attempt is open per family, and the family is held after two empty attempts.
4. **Test pricing and merchandising.** Price experiments wait on live listings. Paid scaling (#295) is OWNER-GATED (`ad_authority`).
5. **Measure the follow-ons.** **Built on INTELREC 4b.** Follow-on orders are counted only for members certified after the decision. Production has nothing to measure yet.

---

## 4. Learning: the 10 steps

| Step | Where | Production record | Strongest offline proof |
|---|---|---|---|
| 1 detects | `mjs.scan` change detection; watchlist scan | MJs runs | `test_w4_intelrec_watchlist` |
| 2 prioritises | Laura priorities; pod priority; coverage-gap score | Laura runs, but not on intelligence | offline test (provider → priority) |
| 3 delegates | COO missions; `intel.opportunity_review` | missions run; review not deployed | offline test (Laura tick → review job) |
| 4 delivers | tournaments → intake → `cir.draft` | 191 tournaments; **0 drafts since 24731** | intake suites |
| 5 evaluates | Laura REVIEW (`did_no_work`); judges | runs | `test_w3_laura_core_executive` |
| 6 detects failure | Laura CHALLENGE/rework; INTELREC settled-attempt failure | runs (needs readback) | offline test (two settled attempts) |
| 7 requests correction | Laura rework (bounded `MAX_CORRECTIONS`) | needs readback | laura suites |
| 8 measures outcomes | `listing.outcomes`, orders | **no outcomes (0 orders)** | outcome suites |
| 9 records lessons | lesson bus, `improve.mine`, the INTELREC stop lesson | lessons exist (needs readback) | offline test (lesson recorded) |
| 10 changes later decisions | `radar.score` nudge; INTELREC lesson deferral | 544 scores; acted-on needs readback | offline test (a later gap deferred by the lesson) |

**Full example.** No production example exists that spans all ten steps, because step 8 has no outcome yet. The strongest offline example is `tests/test_w4_intelrec_watchlist.py::test_offline_observation_to_lesson_through_the_real_job_system`. **It is OFFLINE and not production evidence.** It goes:

1. seeded official-API observations of three shops;
2. scan, then comparison (an arena two shops share becomes a validated gap);
3. Laura observes the provider (DEGRADED), prioritises it and delegates the review;
4. the review routes a departmental job;
5. two attempts settle with no engineered product;
6. the arena is stopped and a lesson recorded;
7. a new gap in the same arena is deferred by that lesson.

**Production steps still missing:** step 4 (engineering since 24731), step 8 (outcomes) and step 10's outcome-driven form.

---

## 5. Reliability

**Schedules active.** The cadences run (job counts above).

- `improve.weekly` dead-lettered once (job 26949, unhashable dict). Fixed in PRODFIX2 67920948; pending deploy.
- The certification and publication deadlock is fixed in PRODFIX 86fe2b50, with the policy-review door. Pending deploy.

**Recovery and persistence.**

- Jobs are durable with leases (`queue/durable.py`).
- Watchlist state is in company memory and survives restart (offline-tested).

**Duplicate suppression.**

- Fingerprints on listings and on mission events.
- Idempotency keys on every enqueue.
- The review is keyed per attempt (offline-tested).

**Provider outages.**

- Etsy refusals are reported, not retried into dead letters.
- Model outages park model jobs (F-098).
- A watchlist outage is isolated per shop and visible to Laura.

**Spend limits.**

- Every paid call goes through `check_budget` with agent and monthly ceilings. Month spend is CA$81.35 of CA$100 (`/api/verify`, 17:24Z).
- The watchlist jobs spend CA$0 (offline-tested: no cost rows).
- Tournaments the review starts pass the creative ceilings, at most 3 per run.

**Research retention.** Covered by the retention guard (FMBATCH1). Observations keep their dates.

**Real department jobs.** Yes: tournaments, scoring and the photography jobs run.

**Laura review and reject.** REVIEW and CHALLENGE run in production. Their effect on intelligence work is not visible yet, because there is no provider.

**Owner gates.** Publication, activation, ads, benchmark purchases and the acceptance ruling stay owner-gated. Learning cannot open them.

**Learning cannot bypass Product Truth or security.**

- Lesson nudges are bounded (`consume.score_adjustment` caps them).
- Hard floors are not tunable (`improve/invariants.py`).
- The pre-engineering gate and certification are deterministic.

**Scheduled reports rather than working business processes.** These produce readings and nothing acts on them yet:

- `radar.competitor_snapshot` (combined only);
- `intel.children_portfolio` (combined only);
- `creative.family_engine` (recommends, writes nothing);
- `intel.benchmark_refresh` (recommends purchases; owner-gated);
- `seasonal.cycle_proof`;
- the Mrs J dashboard (#318).

`intel.watchlist_compare` would be one too, without `intel.opportunity_review`. INTELREC pairs them.

---

## 6. Reconciliation summary

From TRACEABILITY: 101 requirements, and the counts reconcile to the rows. The six spec/05 seed rows were added in this revision.

| stage | Y | N | ? |
|---|---|---|---|
| specified | 101 | 0 | 0 |
| implemented | 96 | 5 | 0 |
| tested | 75 | 26 | 0 |
| integrated | 83 | 18 | 0 |
| reviewed (per row) | 0 | 0 | 101 |
| deployed | 93 | 3 | 5 |
| scheduled and executing | 65 | 6 | 30 |
| valid evidence | 17 | 0 | 84 |
| feeds decisions | 0 | 27 | 74 |
| verified (ledger) | 65 | 36 | 0 |

**Omissions** (no ledger row):

- MP1.2 §4: multi-shop competitor digital twins;
- MP1.2 §5: Winner Amplification as a named row;
- MP1.2 §9: competitor price and promotion scanner;
- spec/05: the seed list and its ten research objectives, plus four seed shops with no ledger row: HanJanCrochet, IvyLoop, LoveandStitchDesigns and FireflyCrochets (§1.5);
- the 2026-10-26 watchlist directive.

The restorations are in `TRACEABILITY.md` and `REMEDIATION_LEDGER.md`.

**Names with no spec source:** "Etsy Trending Crochet Radar", "Plush Culture Radar" and "Product Family Engine". They are mapped to existing rows: #1/#38/#128/#277, #133–#147, and MP §5/#22/#111/#295/F-351. Nothing was invented.

---

## 7. Exact remaining work

The full list is in `REMEDIATION_LEDGER.md`.

1. **Review and deploy INTELREC 876b4fee** (activation). Then the operator reads in `ACCEPTANCE_PLAN.md` §1–§3.
2. **Find out why tournaments stopped reaching engineering** after `cir.draft` 24731 (external evidence, then code). Start with the `creative.winner_intake` readback.
3. **Deploy PRODFIX and PRODFIX2** (activation). These clear the stale-artefact halt, the paid repeats and the `improve.weekly` dead letter. Then the owner records the `listing_image_rules` policy review.
4. **Review and deploy INTELREC 4b and 4c**: Winner Amplification delegation with the `commerce.replication.study` investigation, and the Research Agent questions. No code item remains on this list. Everything here becomes useful only once orders exist.
5. **Deploy the combined candidate** (activation) so the Research Agent and the Family Engine run at all.
6. **Owner decisions:**
   - the acceptance ruling (#320);
   - vision for the non-anchor shops (spend);
   - the benchmark purchases (#148/#317, spend);
   - publication and activation grants (go-live).
7. **Production evidence** that only time and customers produce: orders, outcomes, and lessons changing outcomes.
