# WS2 — Research / competitor-scan audit (READ-ONLY)

- Checkout audited: `/home/user/bl-runs/wt-cert9`, commit `5f4a175e` (branch `claude/w6-INTEG1`).
- Code root: `brambleloop/src/brambleloop` (paths below are relative to it unless stated).
- Method: reading code and `git show` only. No tests or jobs were run, and no file in the worktree was changed.
- **How this relates to production.** `brambleloop/release/DEPLOYED_HISTORY.json` (in the main checkout, commit `85cbe680`) records `88d1ce5e` as deployed at 2026-11-12T02:18Z.
  - Every file this audit relies on is byte-identical between `88d1ce5e` and `5f4a175e`: intel/{scan_evidence, watchlist, benchmarks, observe, panel_discovery, second_market, research_fetch, mission_runtime}.py, radar/intake.py, runtime/{intel_ops, evidence_ops, release, pipeline}.py, creative/intake.py, laura/executive/loop.py, app/{main, security}.py and ops/production_evidence.py. `runtime/worker.py` differs, but only outside the CADENCES tuples.
  - The SHA production actually runs is **UNKNOWN** from code; `/health build.commit` would confirm it.
  - Note that `brambleloop/BUILD_STATE.md` on this branch still names `0967c3ee` as production. That commit has **no** seed shops, no `scan_evidence.py` and no `radar/intake.py`.
- Nothing below has been read from a production database. Every production value is **UNKNOWN** unless marked otherwise.

---

## 1. The eight shops

**Where the shops are defined:**
- Registry: `intel/benchmarks.py:146` `REGISTRY = (MJS, MADELINE, ZKB, EASY) + SEED_SHOPS`. All eight are `mandatory=True`.
- Watchlist: `intel/watchlist.py:107-122` `WATCHLIST`.
- Owner-ordered evidence list: `intel/scan_evidence.py:50-59` `OWNER_SHOPS`.

**Decision IDs:**
- **W4-INTELREC** (owner directive 2026-10-26): Madeline, ZKB, Easy. See `benchmarks.py:116-132`.
- **D-W4-OWNER-SEEDSHOPS** (owner decision 2026-10-27; `DECISION_LOG.md:2660`): the four seed shops. See `benchmarks.py:134-152` and `watchlist.py:89-93, 116-122, 314-329`.
- **#301**: the anchor. See `benchmarks.py:34-46`.

Aliases are `runtime/intel_ops.py:33` `benchmark_alias`, i.e. `bm-` + sha256(key)[:10].

| # | Benchmark key (alias) | Code shop name | Role (`watchlist.Member.role`) | Collection method | Credential | Cadence (worker.py CADENCES) |
|---|---|---|---|---|---|---|
| 1 | `mjs_off_the_hook_designs` (bm-c4c0ef76f3) | MJsOffTheHookDesigns | `anchor`, special=True | Etsy Open API v3, public read (`findShops` → catalogue → listing images) via `intel.observe.scan` (`observe.py:122`), with a deep audit of at most 25+40 listings per scan. Reviews: `mjs.reviews` → `observe.scan_reviews` (`observe.py:772`). URL health: `intel.benchmark_health` → `benchmarks.api_resolve` (findShops). Gallery vision: `intel.gallery_analysis` (paid, anchor only). | ETSY_API_KEY + ETSY_SHARED_SECRET (`launch/access.py:228-233`); the gate opens on a successful `etsy.probe`, not on the variables being present. | `mjs_scan` every 2 h (`worker.py:801`), gated by the adaptive interval (`observe.py:569-585`): 6 h fixed while history is thin, 2–24 h once adaptive (`observe.py:467-483`). `mjs_reviews` weekly (`:826`), `mjs_benchmark_health` daily (`:807`), `gallery_analysis` every 2 h (`:928`). |
| 2 | `madeline_mae_co` (bm-fe8c952f65) | MadelineMaeCo | `special`, special=True | The same `observe.scan`, plus `findShops` shop counters (`watchlist.py:147-148, 233-234`) and weekly `scan_reviews` (`watchlist.py:241-248`), run through `intel.watchlist_scan` → `watchlist.scan_all` (`watchlist.py:332`). Mission paid steps are withheld (`watchlist.py:276-290`). | Same Etsy read key | `watchlist_scan` every 6 h (`worker.py:975`), then a per-shop adaptive due check (`watchlist.py:217-220`) and exponential backoff from 6 h up to 7 d (`watchlist.py:78-86, 221-230`). `watchlist_compare` daily (`:976`). `mjs_benchmark_health` daily resolves it too (`mission_runtime.py:1396`). |
| 3 | `zkbdesigner` (bm-b412aca9ee) | ZKBDESIGNER | `permanent` | as #2 | as #2 | as #2 |
| 4 | `the_easy_design` (bm-95ea4c898c) | TheEasyDesign | `permanent` | as #2 | as #2 | as #2 |
| 5 | `hanjan_crochet` (bm-a798c93351) | HanJanCrochet | `seed` | as #2. The alternative evidence is the seed observation in `radar.market.COMPETITORS` (`watchlist.py:302-311`). | as #2 | as #2 |
| 6 | `ivyloop` (bm-8042e052c4) | IvyLoop | `seed` | as #5 | as #2 | as #2 |
| 7 | `loveandstitch_designs` (bm-257d48a710) | LoveandStitchDesigns | `seed` | as #5 | as #2 | as #2 |
| 8 | `firefly_crochets` (bm-c217e10a8e) | FireflyCrochets | `seed` | as #5 | as #2 | as #2 |

- No shop is collected by rendered-page reading or by hand.
  - A rendered page is used only for URL health, and only if a browser capability is proven (`benchmarks.py:384-403`). Otherwise the official API is used.
  - The only "manual" evidence is the owner-seeded profile observation, used as alternative evidence.
- `intel.scan_evidence` runs daily (`worker.py:994`) and **joins** these sources. It does not collect anything itself.

### The states each shop can be in

**Watchlist shops (#2–#8).** The state lives in company memory `intel:watchlist:<key>`:
- `ok` (`watchlist.py:267`)
- `source_outage` (`:252-264`, `:366-372`)
- `credential_refused` (`:252`, `:348-359`)
- `not_accessible`: HTTP 404/410, or "was not found exactly" (`:93-94, 295-329`)
- `not_configured`: no key (`:340-347`)
- deferred, which is returned but never saved (`:220`, `:227-230`)

**The anchor (#1)** has no state machine of its own. Its state is inferred from:
- `mjs.scan` job outputs and the audits `mjs.scanned` / `mjs.scan_blocked` (`release.py:4464-4515`);
- `Benchmark.scan_health`, which is `unverified|healthy|moved|unreachable|wrong_shop` (`benchmarks.py:202-206`).

**Derived states in scan evidence** (`scan_evidence.py:40-44, 156-236`): `scanned`, `attempted_not_scanned`, `not_accessible`, `never_attempted`, `not_registered`. The last one is now unreachable for all eight shops, because the seed shops joined `WATCHLIST`; the docstring at `:26-28` is stale.

### Defects found in the per-shop record (verified from code)

- **D1 — anchor deferrals are reported as failures.**
  - `mjs.scan` fires every 2 h, but the interval is at least 6 h until history adapts, so most runs are deferrals.
  - A deferral returns `{"ran": False, "reason": "adaptive interval (#313): not due ..."}` (`observe.py:621-626` → `release.py:4479-4486`). The `deferred` flag is not carried into the job output.
  - `scan_evidence._anchor` treats any `outputs.ran is False` as a failure (`scan_evidence.py:171-183`). So whenever the newest `mjs.scan` job was a deferral, the anchor reads `attempted_not_scanned`, with the deferral text as its `failure_reason`. Its `last_attempted` is also the deferral's time (`:192-193`).
- **D2 — every watchlist observation is recorded at grade `supporting`, never `mandated`.**
  - `watchlist.scan_member` calls `observe.scan(..., env={})` (`watchlist.py:235-236`).
  - `observe.scan` passes `env={}` to `mission.record` (`observe.py:343-347`), which grades through `access.available("benchmark_observation", {})`. With `env={}` the key variables are always absent (`launch/access.py:211-213, 311-322, 330-335`).
  - The result: every watchlist `official_api_read` observation is stored `grade=supporting, satisfies_mandate=False` (`launch/access.py:122-125`), even when the credential works.
- **D3 — HanJanCrochet can be registered twice.**
  - It is a seed shop (`hanjan_crochet`) and also a second-market candidate (`second_market.py:40-49`).
  - `ensure_selected` de-duplicates on the key `panel_hanjancrochet` only, not on the shop name (`second_market.py:71-75`).
  - If HanJanCrochet is verified as `other`, a second `Benchmark` row appears, with its own listings, scanned weekly by panel_discovery and six-hourly as a seed. `scan_evidence` only reports the seed key.
- **D4 — `listings_observed` overcounts the live catalogue.** `scan_evidence._observed` counts every `benchmark_listings` row, including `audit_state='withdrawn'` rows (`scan_evidence.py:99-111`; withdrawn rows are kept at `observe.py:314-325`). It is not a measure of current coverage.
- **D5 — dead constant.** `watchlist.SCAN_READING = "intel.watchlist_shop"` (`watchlist.py:43`) is never written. No per-shop reading row exists besides memory.
- **D6 — stale docstrings.** The watchlist docstring says "Four shops" (`watchlist.py:3`), and the compare docstring says "four-shop comparison" (`intel_ops.py:308`). The code covers eight. This is cosmetic.

---

## 2. Where each per-shop fact is stored

| Fact | Anchor (#1) | Watchlist shops (#2–#8) | Recorded? |
|---|---|---|---|
| Collection method | `scan_evidence.METHOD` constant (`scan_evidence.py:46-47`); not stored per shop | Same constant; `_save_state` sources=`["etsy_open_api_v3"]` (`watchlist.py:178-180`) | Constant only. Not stored per run. |
| Scheduling | `scan_evidence._cadence("mjs.scan")` (`:77-83`) | `_cadence("intel.watchlist_scan")` | The cadence is recorded. **NOT recorded**: the per-shop adaptive interval, the next-due time and the backoff-until time. They are computed (`observe.adaptive_interval`, `watchlist.backoff_for`) but never stored or projected; the backoff-until appears only in a transient return value (`watchlist.py:227-230`). |
| Last attempted scan | `jobs` rows of type `mjs.scan` (created_at/finished_at), via `scan_evidence._jobs` (`:86-96`). Includes deferrals (D1). | Memory `intel:watchlist:<key>`.body.`last_attempt_at` (`watchlist.py:253, 267, 322, 344, 353, 368`) | Yes. The anchor value is wrong (D1). |
| Last successful scan | `benchmarks.last_scan_at` (`observe.py:332`); `benchmark_observations` kind `official_api_read` `at`; audit `mjs.scanned` | Memory body `last_ok_at` (`watchlist.py:267`); `benchmarks.last_scan_at`; `benchmark_observations.at` | Yes |
| Source timestamp | `scan_evidence` sets `source_timestamp = last_successful` (`:194`), which is **our** clock | Same (`:228`) | **NOT recorded as a source-side time.** Etsy's own `last_modified_timestamp` is used in the fingerprint (`observe.py:37-38`) but not stored (`observe.py:189-206` keeps only tags, materials, num_favorers, who_made, when_made). No response `Date` or shop `update_date` is kept. |
| Listing coverage | `benchmark_listings` count, first_seen and last_seen (D4). Per-scan `catalogue_coverage` sits in the `benchmark_observations.detail` and `mjs.scanned` audit detail (`observe.py:62-75`). | Memory `listings_seen` (`watchlist.py:269`); `shop.listing_active_count` (`:147-148, 268`); `benchmark_listings` | Partial. Coverage against Etsy's active count is computable for #2–#8 from memory, but `scan_evidence` does not project `listing_active_count`. For the anchor, the shop's active count is **NOT recorded**. |
| Recorded errors | `jobs.last_error`; `mjs.scan_blocked` audit detail (`release.py:4479`); `incidents` signature `benchmark.url_health:<key>` (`mission_runtime.py:1401-1417`) | Memory `last_error` (latest only, 300 chars), `consecutive_failures`, `limitation`/`limitation_on`/`alternative_evidence` (`watchlist.py:253-264, 321-324`); `intel.watchlist_scan` audit (state per alias, no error text: `intel_ops.py:294-300`) | Latest error only. **NOT recorded**: the per-shop error history and the error class. |
| Downstream research results | `mjs_mission_events` (benchmark_key); `coverage_gaps` (benchmark_key); `mjs.findings` reading; lessons | `mjs_mission_events` (benchmark_key, capped at 5 per run, paid steps withheld); `coverage_gaps` under `benchmark_key='watchlist'`, which is cross-shop and not per shop (`watchlist.py:42, 491`); `research_tasks` trigger `watchlist_gap:<id>` (`:503-524`); memory `intel:opportunity:<gap>` (`:648-659`); `operating_readings` kind `intel.watchlist_compare` (`:488`) | **NOT recorded per shop.** `scan_evidence.downstream` is only `_observed()` listing counts (`scan_evidence.py:266`). None of the downstream rows are joined to the shop. |
| Joined per-shop table | `operating_readings` kind `intel.scan_evidence`, one row per UTC day (`scan_evidence.py:307-323`); audit `intel.scan_evidence` (`evidence_ops.py:21-27`) | Same | Yes, with the D1 and D4 defects and the gaps above. |

---

## 3. What production exposes

**The anonymous public projections** are allow-listed in `app/security.py:240-251`:
- `/api/verify` shows the name and ok of each check, and of `evidence_checks`.
- `/api/verify/smoke` shows `verdict` and `as_of` only.
- No per-shop fact is reachable without a token.

**`/api/verify` with the operator token** (`app/main.py:5416`) carries no intel-specific check. The only related evidence is `no_unexpected_dead_letters_in_24h`, which counts dead letters by job type, so it would show an `mjs.scan` dead letter. It also carries `production_evidence.checks()`, whose four checks contain nothing about competitors (`ops/production_evidence.py:643-687`).

**`/api/verify/smoke`** (`ops/smoke.py`), full body to the operator only:
- `probe_recency` includes `etsy.probe` (`smoke.py:33-34, 75-110`), so whether the credential works is visible as the probe audit's age.
- `search_intelligence_captured` (`intel.serp_capture`, `:206-230`).
- `cadence_coverage` (ops.slo freshness over all cadences, `:162-179`).
- Nothing per shop.

**`/api/readback/evidence`**, the only route the read-only `BRAMBLELOOP_READBACK_TOKEN` can reach (`security.py:321`, `main.py:5689-5703`):
- `autonomy_loop.stages[market_observation]` counts useful, no-op, dead and open jobs of `mjs.scan`, `mjs.reviews`, `radar.scan`, `radar.competitor_snapshot`, `intel.serp_capture`, `intel.watchlist_scan`, `intel.gallery_analysis`, `etsy.listing_census` and `culture.sweep` (`production_evidence.py:55-58, 430-507`).
- `opportunity_validation` counts `radar.score`, `intel.opportunity_review`, `intel.watchlist_compare`, `portfolio.review` and `research.investigate`. `original_product` counts `cir.draft`, `cir.compile` and `gate.certify`.
- Plus `concept_supply_stall` and `dead_letters_24h` by job type with error class.
- **Not exposed:** `intel.scan_evidence`, `intel.panel_discovery` and `radar.concept_intake`, which are in no stage. Nothing is per shop: no state, timestamps, errors or coverage.

**Operator token only** (default-deny, `security.py:114-131, 283-285`):
- `/api/mjs` gives the anchor mission report only (`main.py:1363`; `mission_report` defaults to MJS).
- `/api/mjs/findings` and `/api/mjs/coverage`.
- `/api/culture` (`main.py:1988`), `/api/market-intel` and `/api/etsy`.
- `/api/audit?action=intel.scan_evidence` or `action=intel.watchlist_scan` (`main.py:5353`), and `/api/jobs` (`:5226`).
- No endpoint serves the `intel.scan_evidence` reading or the `intel:watchlist:*` memory. A grep of `app/` finds no reference to `scan_evidence` or `watchlist`.

**Command center** (`app/command_center/providers.py:22-52`) has no intel, watchlist or scan-evidence provider. Related surfaces:
- `company.py:736-760` shows the latest `mjs.findings` reading.
- `causal.py:48` labels `mjs.scan`.
- `brief.py:34` reads `mjs.findings`, `mjs.mission_events` and `intel.gallery_analysis`.

**Laura's intelligence provider**:
- It is `intel.watchlist.summary` (`laura/executive/loop.py:66-67`; `watchlist.py:549-599`).
- It covers the seven non-anchor shops, by alias, giving status OK/DEGRADED/UNKNOWN with lists of outages, stale, unobserved and not_accessible shops.
- It is persisted only as a status word in memory `laura:last_tick`.body.observed.providers (`loop.py:757-761, 852-857`).
- It has no HTTP route of its own (UNKNOWN whether any CC tab renders `laura:last_tick`), and the anchor is excluded.

**Summary of token reach:**
- Readback token: aggregate job counts per stage, plus dead letters. No per-shop facts.
- Operator token: the anchor's report, audit and job rows (from which the per-shop facts could be reconstructed by hand), and the scan_evidence audit detail (counts, scanned, not_scanned with reasons).
- Not reachable on any route: the full per-shop scan-state table.

---

## 4. From observation to product

### Path A — anchor only (scheduled end to end, paid, behind gates)

1. `mjs_scan` cadence (`worker.py:801`) → `handle_mjs_scan` (`release.py:4464`) → `observe.scan_or_explain` (`observe.py:588`) → `observe.scan` (`:122`) writes `benchmark_listings` and `benchmark_observations` (`:343-347`).
2. `_run_mjs_mission` (`release.py:4523`) → `mission_runtime.process` (`mission_runtime.py:1333`) → `process_listing` (`:766`). Step 8 enqueues `creative.tournament` when `will_tournament` (`:937, 1007`) via `_enqueue_breakthrough` (`:721-748`). The same-arena path is `consume_concepting` (`:1303`).
3. `creative.tournament` (`release.py:5952`) is model-paid, inside the `creative_director` ceiling of CA$28/day (`agents/registry.py:174`). It needs a working model (`model.probe`, `worker.py:745`).
4. → `_winner_intake` (`release.py:6221`) → `creative/intake.py` pre-engineering gate. The concept stays `WAITING` without a vision judgement (`creative/intake.py:768, 877-882`); `regate_held` re-presents it (`:1050-1121`).
5. → `cir.draft` (`creative/intake.py:806`) → `handle_cir_draft` (`pipeline.py:717`) → `cir.compile` (`pipeline.py:990/1067`) → `gate.certify` (`pipeline.py:1093`).

Whether this path is wired: **yes, in the scheduler, with no owner trigger.** It depends on four things, each UNKNOWN in production: a working Etsy read credential (BUILD_STATE recorded HTTP 403 from 2026-10-07; current state UNKNOWN), a model probe that succeeds, `image_vision` being open, and creative ceiling headroom.

### Path B — the seven non-anchor shops (scheduled up to a dead end)

1. `watchlist_scan` (`worker.py:975`) → `scan_all` (`watchlist.py:332`) → `observe.scan` + `mission_runtime.process`, with paid steps withheld (`watchlist.py:276-290`; `mission_runtime.py:711-718, 734-736`). **No tournament is ever started from a non-anchor observation.**
2. `watchlist_compare` (`worker.py:976`) → `record_comparison` (`watchlist.py:480`): a pod that two or more watchlist shops occupy and we do not → a `coverage_gaps` row (`:491`) plus a research question (`:496, 503-524`).
3. The Laura tick (`worker.py:1024`, every 5 min) → provider DEGRADED (`watchlist.py:577-595`) → priority `provider:intelligence` (`loop.py:295-305`) → `intel.opportunity_review` (`intel_ops.py:321`). This is bounded by `MAX_DELEGATIONS_PER_TICK=4` and a one-per-day window, so whether it is selected in a given tick is UNKNOWN.
4. `watchlist.review` (`watchlist.py:748`):
   - If a concept in POOL or the intake pool matches the pod: `radar.score` (`:726-745, 853`) → pre-engineering gate → `cir.draft` (`pipeline.py:497-560`).
   - Otherwise it records `needs_original_design` (`:843-850`) and **stops**. No original concept is created; the decision is parked for 7 days (`:628-645`) and re-recorded.
   - So non-anchor evidence can only route **pre-existing** concepts. It never produces an original one.

### Path C — concept intake (scheduled, with no automatic input)

- `concept_intake` (`worker.py:982`) → `radar.intake.run` (`radar/intake.py:1098`). Its sources are:
  1. `research_candidates`: research tasks that carry `detail.concept_proposals` (`intake.py:750-765`).
  2. `family_candidates`: these need at least `AMPLIFY_MIN_ORDERS = 5` orders (`creative/family_engine.py:27`), and in shadow there are none.
- **Gap:** `attach_proposal` (`intake.py:378`) is the only writer of `concept_proposals`, and **no production code calls it.** A grep outside `tests/` finds only its definition. `research.investigate`/`research_agent` never writes one.
- So the chain "observation → research task → concept proposal" needs a manual call (a Python shell or a test). There is no endpoint for it.
- Downstream it is wired: an approval → `radar.score` → `cir.draft` (`intel_ops.py:335-357`; `pipeline.py:559`).

### Path D — weekly creative cadences that read observed listings (scheduled, paid)

- `arena_expedition` (`worker.py:859`), `product_tournament` (`:867`) and `white_space_discovery` (`:661`) read `prospecting.arenas` → `seasonal.benchmark_matrix` (`creative/prospecting.py:213-251`).
- The expedition and tournament then go through `_winner_intake` → `cir.draft`, under the same gates as Path A.

### Culture and research

- `culture.sweep` (`worker.py:908`; `release.py:8035`) reads Wikimedia pageviews and routes findings into `learning.record` lessons (`culture/radar.py:487-527`). There are no `enqueue` calls in `culture/`, so culture influences scores and briefs but **creates no concept**.
- `research.sweep` (`worker.py:979`; `intel_ops.py:231-259`) investigates from internal evidence, at CA$0 with no network (agent ceiling CA$0, `registry.py:994-999`).
- The research fetch runs under `learn.scan` (hourly, `worker.py:614`; `learn/runtime.py:55`), only when `BRAMBLELOOP_RESEARCH_FETCH=1` (`research_fetch.py:299-315`). Production's value for that variable is UNKNOWN. Hosts are allow-listed and free (`:42-49`).

### The gaps, by name

- **G1:** Non-anchor shops never produce an original concept (`watchlist.py:843-850`; tournament withheld per INTELREC M-3). Changing this is an owner spend decision.
- **G2:** Research → concept proposal has no automated writer (`radar/intake.py:378`).
- **G3:** Original concepts wait on `image_vision` at the pre-engineering gate. Production state UNKNOWN.
- **G4:** Every path needs a working Etsy read key. The current probe result is UNKNOWN; it was 403 as of 2026-10-11 in BUILD_STATE.
- **G5:** There is no production-readable proof joining one observation id to a `cir.draft`. The lineage exists in rows (`mjs_mission_events.observation_id` → tournament job → `cir.draft` inputs), but no projection exposes it.

---

## 5. Category-leader discovery and second-market research

### `intel.panel_discovery` (`intel/panel_discovery.py:124-210`; handler `release.py:4640`)

- **Built:** yes.
- **Scheduled:** weekly (`worker.py:811`).
- **Flag or gate:** none in code. It runs only if `ReadCredential.from_env(...).complete` (`panel_discovery.py:111-121, 135-138`); otherwise the reason is audited as `intel.panel_discovery_blocked`.
- **Not owner-gated** (authority `_R`, `authority/classes.py:92`).
- **Caveats:**
  - It does not check `auth_refused(last_probe)`, so with a refused key it still attempts reads (errors are recorded per member).
  - It has no due or backoff logic.
  - Members are not in `scan_evidence`.
- **Input dependency:** `serp_snapshots` from `intel.serp_capture` (daily, `worker.py:804`). BUILD_STATE line 177 recorded "Production has 0 SERP snapshots" while the key was refused. Current state UNKNOWN.
- **Paid calls:** none in discovery (Etsy API, CA$0). `serp_capture` may make paid vision thumbnail calls under the `market_radar` ceiling of **CA$4.00/day** (`registry.py:90-112`; `release.py:4809-4816`).

### Second market (`intel/second_market.py`, decision **D-W4-GATESB-1**, `DECISION_LOG.md:1719`)

- **Built:** yes.
- **Scheduled:** runs inside each `panel_discovery` run (`panel_discovery.py:142-144`).
- **Owner gating:** company-selected, not owner-gated (`build2/gate_clearance.py:483-484` `COMPANY_SELECTED`). `ops/owner_queue.py:91-92` still labels the gate `physical`, which is inconsistent.
- **What it joins:** LakesideLoops (CA) and HanJanCrochet (other), only after `findShops` plus `getShop` verify the name and stated location (`second_market.py:59-108`).
- **Gate:** `second_market_benchmark` opens when listings have been observed from more than one distinct stated market (`build2/executor.py:459-485`). Whether it is open in production is UNKNOWN.
- **Paid calls:** none (CA$0). D3 applies (a possible HanJanCrochet double row).

**"Activated where authorized"** holds in code. Both run automatically once the Etsy read key works. Whether they ran in production is UNKNOWN; `intel.panel_discovered` / `intel.panel_discovery_blocked` audits (operator `/api/audit`) would show it.

---

## 6. Producing the per-shop table from production

**What exists today:**
- `intel.scan_evidence` writes the joined table daily to `operating_readings` (kind `intel.scan_evidence`), plus an audit.
- No route serves the reading. The closest is operator `/api/audit?action=intel.scan_evidence`, which carries only `counts`, `scanned`, `not_scanned` (with reasons), `credential` and `references_observed`, not the timestamps (`evidence_ops.py:21-27`).
- `brambleloop/scripts/p0_acceptance.py:263` cites `GET /api/audit?action=intel.watchlist_scan` as the production read, which is operator-only.
- **No script or endpoint produces the full per-shop scan-state table from production with the readback token.**

**Smallest read-only addition.** Add one section to `ops/production_evidence.py` `SECTIONS` (`:582-591`), so it ships through the existing `/api/readback/evidence` and the readback token, with no new route and no security-list change:

```python
def competitor_scans(db, *, now):
    from ..intel import scan_evidence as SE, watchlist
    from ..runtime.intel_ops import benchmark_alias
    rep = SE.report(db, now=now)           # read-only, no network (scan_evidence.py:239)
    stored = SE.latest(db) or {}
    rows = []
    for i, r in enumerate(rep["shops"], 1):
        st = watchlist._state(db, r["key"]) if r.get("key") in watchlist.BY_KEY else {}
        rows.append({
            "owner_order": i, "alias": benchmark_alias(r.get("key") or r["shop"]),
            "role": r["owner_role"], "state": r["state"],
            "cadence": (r.get("schedule") or {}).get("cadence"),
            "every_hours": (r.get("schedule") or {}).get("every_hours"),
            "last_attempted": _iso(r.get("last_attempted")),
            "last_successful": _iso(r.get("last_successful")),
            "age_h": _age_h(r.get("last_successful"), now),
            "consecutive_failures": _int(r.get("consecutive_failures")),
            "failure_class": _fixed_vocab(st.get("state")) or error_class(r.get("failure_reason")),
            "listings_observed": _int(r["downstream"]["listings_observed"]),
            "listings_seen_last_scan": _int(r.get("listings_seen_last_scan")),
            "listing_active_count": _int((st.get("shop") or {}).get("listing_active_count")),
            # downstream, per key: COUNT(mjs_mission_events), COUNT(coverage_gaps), etc.
        })
    return {"readable": True, "credential": rep["credential"].split(":")[0],
            "reading_period": (stored.get("as_of") or "")[:10] or None,
            "shops": rows, "counts": rep["counts"]}
```

- The section emits only aliases, enums, counts and UTC timestamps, never shop names or error text, so it stays inside the module's contract (`production_evidence.py:26-30`). The alias→shop mapping can be derived offline from the code (table in §1).
- Add `intel.scan_evidence`, `intel.panel_discovery` and `radar.concept_intake` to `LOOP_STAGES` (`:55-62`).
- **Fix D1 first** (carry `deferred` into the `mjs.scan` output and skip deferrals in `_anchor`), or the anchor row will often read `attempted_not_scanned`. Also add a per-shop next-due field (`observe.scan_due` + `watchlist.backoff_for`), and count only non-withdrawn listings (D4).
- A judged `/api/verify` check is not needed. If one is added, mark it advisory (`main.py:5430-5436`) so a seed shop that is `not_accessible` does not flip the verdict.

---

## Facts NOT recorded anywhere (consolidated)

1. A source-side (Etsy) timestamp for each scan or listing. `source_timestamp` is our own observation time.
2. Per-shop next-due, adaptive-interval and backoff-until times.
3. Per-shop error history and error class. Only the latest `last_error` is kept.
4. The anchor's Etsy active-listing count, so anchor coverage against the shop's own catalogue cannot be computed.
5. Downstream research results per shop. Watchlist gaps are keyed `watchlist` (cross-shop); research tasks, decisions and lessons are not joined to a shop.
6. An observation→concept→`cir.draft` lineage projection.

## UNKNOWN (needs production data)

- The SHA production actually runs.
- The current `etsy.probe` result.
- Whether any `intel:watchlist:*` memory or `intel.scan_evidence` reading exists, and its contents.
- Whether panel or second-market shops joined.
- Whether `image_vision` is open.
- `BRAMBLELOOP_RESEARCH_FETCH`.
- Whether `mjs.scan` produced a `cir.draft` in production.
- Which cadences are suspended or blocked at runtime (`worker.py:1335-1355`).
