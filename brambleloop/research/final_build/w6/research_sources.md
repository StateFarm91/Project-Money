# Research source registry (ENG-RESEARCH, W6)

Audited 2026-11-19 on `eng/research-flow` (base `claude/w6-INTEG2` @ a35ad302). This is the
prose form of the code registry `brambleloop.intel.research_flow.sources()`.
`test_research_flow.test_every_research_cadence_is_in_the_registry_and_every_mandatory_shop_too`
keeps the two in step. It also fails if a research cadence or a mandatory shop is missing.

The cadence for each source is read from `runtime.worker.CADENCES`, never copied. Its status is
derived by `research_flow.status_of`: **scheduled**, **disabled** (a deployment flag),
**blocked** (credential, owner readings, vision) or **missing** (no collector). A source is
never silently dropped. Source ids are the code's own keys. Readings and the Mission Control
section show watchlist shops by **alias** only (`bm-…`, watchlist L-3).

**What "scheduled" means.** No env flag disables any cadence in this table. The scheduler skips
a cadence only in two cases:
- The thrash breaker has suspended its job type (the ENG watchlist-cadence fix lifts a
  suspension when its gate changes).
- Its department is blocked.

Any Etsy-reading job also no-ops with `credential_refused` until `etsy.probe` succeeds. That
is the shared gate `etsy_credential` below. Production's state is visible at
`/api/cc/p0-board` (`credential`). This audit cannot read it.

## 1. Owner watchlist: the eight mandatory shops

All eight are collected through the official Etsy Open API v3, using
`intel.etsy_public.PublicReader` and the `ETSY_API_KEY` + `ETSY_SHARED_SECRET` pair. Agent:
`market_radar`. All eight are **scheduled**, gated on `etsy_credential`.

| id | owner role | job | cadence | method |
|---|---|---|---|---|
| `mjs_off_the_hook_designs` | anchor | `mjs.scan` (+ `mjs.reviews`, 7 d) | 2 h, adaptive | findShops, shop listings, images |
| `madeline_mae_co` | special | `intel.watchlist_scan` | 6 h | findShops, shop listings, getReviewsByShop (weekly inside the scan) |
| `zkbdesigner` | permanent | `intel.watchlist_scan` | 6 h | same |
| `the_easy_design` | permanent | `intel.watchlist_scan` | 6 h | same |
| `hanjan_crochet` | seed (D-W4-OWNER-SEEDSHOPS) | `intel.watchlist_scan` | 6 h | same |
| `ivyloop` | seed | `intel.watchlist_scan` | 6 h | same |
| `loveandstitch_designs` | seed | `intel.watchlist_scan` | 6 h | same |
| `firefly_crochets` | seed | `intel.watchlist_scan` | 6 h | same |

**When a shop cannot be read:**
- A shop the API cannot find (404/410, or no exact match) is recorded as `not_accessible`. The
  record carries the reason, the date, `monitoring: kept` and the dated spec/05 public-profile
  evidence. The shop is never recorded as "scanned".
- Any other failure is recorded as a `source_outage`, with backoff of 6 h × 2ⁿ, capped at 7 d.
- Neither case stops the other shops. `test_research_flow` checks this.

`radar.market.COMPETITORS` is a static, dated profile (2026-09-17), not a collector. The
comparison reads it.

## 2. Analysis over the observed rows (no network, CA$0)

| id | agent / job | cadence | status | role in the loop |
|---|---|---|---|---|
| `watchlist_compare` | market_radar / `intel.watchlist_compare` | 24 h | scheduled | Fresh, live listings in a pod that ≥2 watchlist shops occupy and we do not → a validated arena → a `watchlist` coverage gap and its research question |
| `concept_intake` | market_radar / `radar.concept_intake` | 6 h | scheduled | Proposal writer → intake → `radar.score`, then records the cycle's conclusion (new) |
| `market_radar` | market_radar / `radar.scan` | 6 h | scheduled | Scores the POOL and intake concepts. Gives coverage handoffs to ideation |
| `research_sweep` | research_agent / `research.sweep` | 24 h | scheduled | Queues `research.investigate` |
| `competitor_snapshot` | market_radar / `radar.competitor_snapshot` | 24 h | scheduled | Aggregate snapshot, aliases only |
| `scan_evidence` | market_radar / `intel.scan_evidence` | 24 h | scheduled | Daily per-shop scan evidence |
| `benchmark_refresh` | market_radar / `intel.benchmark_refresh` | 7 d | scheduled | Raises owner purchase asks only |
| `gallery_analysis` | market_radar / `intel.gallery_analysis` | 2 h | **blocked** until a vision model is usable (`image_vision`) | Judges stored gallery URLs within market_radar's ceiling |

## 3. Second market and category leaders

| id | agent / job | cadence | method | status |
|---|---|---|---|---|
| `second_market` | market_radar / `intel.panel_discovery` | 7 d | Candidates `LakesideLoops` (CA) and `HanJanCrochet` (UK) were picked from dated search-index snippets (2026-10-07). A candidate joins only after the API resolves the exact shop and `getShop` states the market (D-W4-GATESB-1). HanJan dedupes onto its seed key | scheduled, `etsy_credential` |
| `category_leaders` | market_radar / `intel.panel_discovery` | 7 d | Top of the API search index for ≥2 queries, at most 2 per run, then the anchor's scan | scheduled, `etsy_credential` |
| alternates `PippaPatternsCrochet`, `NikByDesign`, `CrochetPatternHouse` | — | — | on record only | **not collected, by decision** (never registered) |
| `benchmark_health` | market_radar / `intel.benchmark_health` | 24 h | Rendered page when `BRAMBLELOOP_BROWSER_URL` is set, otherwise API findShops | scheduled. Rendered evidence reads `unverified` without the browser worker |

## 4. Search (SERP) and trend sources

| id | agent / job | cadence | method | status |
|---|---|---|---|---|
| `serp_capture` | market_radar / `intel.serp_capture` | 24 h | API `findAllListingsActive` sort_on=score. Queries "crochet <keyword> pattern" per pod (≤2) plus one per seasonal event | scheduled, `etsy_credential`. Thumbnail judging needs `image_vision` |
| `culture_sweep` | market_radar / `culture.sweep` | 24 h | Wikimedia REST pageviews: 12 standing topics (`BRAMBLELOOP_CULTURE_TOPICS` overrides), top-article discovery, 10 colour signals, the children's monthly series; plus derived Etsy first-seen demand | scheduled (keyless). P1-CULTURE-SWEEP-TIMEOUT is still open in BUILD_STATE |
| `external_trends` (Google Trends, Pinterest Trends, social, Etsy trend reports) | — | — | none | **missing**: no official API is wired, and none will be scraped. Requested only generically (spec/05 "external traffic/content ecosystems"; master v1.1 "external research"; B2#38 "Etsy trend reports"). Kept visible as a limitation |
| spec/05 search seed URL (`is_star_seller=true`) and example listing ids | — | — | — | **missing as a source id**. SERP derives its own queries and has no star-seller filter. The example listings are not monitored individually; their shops are |

## 4a. Off-Etsy competitor channels (Master Plan MP1.2-s4) — UNAVAILABLE

MP1.2-s4 asks for competitors' websites, YouTube and Pinterest. `FOUR_SHOP_COMPARISON.md`
(w4/intel) records all three as UNAVAILABLE: no compliant collector exists. Each is a
registry row with `kind="offsite"`, status **missing**, and its reason, so it stays visible as
a limitation (the board's `limitations` list) and is never scraped.

| id | agent / job | cadence | method | status |
|---|---|---|---|---|
| `competitor_websites` | market_radar / — | — | none | **missing (UNAVAILABLE)**: no allow-listed, terms-compliant fetch exists for a competitor's site; `research_fetch` covers gov, Wikipedia and Etsy help only |
| `youtube` | market_radar / — | — | none | **missing (UNAVAILABLE)**: needs a YouTube Data API key (owner action) and a collector |
| `pinterest` | market_radar / — | — | none | **missing (UNAVAILABLE)**: needs Pinterest API app approval and owner OAuth; never scraped |

## 5. Reference and owner-supplied

| id | agent / job | status |
|---|---|---|
| `research_fetch` (allow-listed HTTPS: laws-lois.justice.gc.ca, canada.ca, cpsc.gov, en.wikipedia.org, help.etsy.com) | learn / `learn.scan`, 1 h | **disabled** unless the deployment sets `BRAMBLELOOP_RESEARCH_FETCH=1`. Off is reported, never silent. Turning it on is a deployment change (Railway), which belongs to Main, not this branch |
| `marketplace_insights` (Etsy Shop Manager) | owner, `POST /api/insights/snapshot` | **blocked by design**. Etsy exposes no API, so the owner records the readings (gate `insights_access`) |

## 6. The loop: where it stopped and what was wired

Traced on the real handlers, using `tests/_watchlist_sim.py` and the production cadences:

```
intel.watchlist_scan ─► intel.watchlist_compare ─► coverage gap + research task (answered)
  ─► proposal_writer (ORIGINAL proposal) ─► radar.concept_intake (approve)
  ─► radar.score ─► pre-engineering gate ─► cir.draft (crochet_engineer)
```

**Stop 1, fixed.** Every watchlist proposal reached `radar.score` and was **refused** by the
gate, deterministically:
- #88: no thumbnail storyboard.
- #108: the "coaster" outline carried no qualifier.

The refusal was recorded as `returned_to_ideation`, but nothing consumes that for intake
concepts. So no watchlist opportunity could ever reach engineering. The writer now adds the
gate's own brief (`proposal_writer.brief_for`), in our house vocabulary.

**Stop 2, fixed.**
- The anti-clone check (#87 novelty, and intake's anti-copy) compared a concept only with the
  anchor's listings.
- A concept that other watchlist shops inspired was therefore never checked against those
  shops, and waited on `benchmark_observation` forever when the anchor had nothing in the pod.
- Both checks now use `prospecting.watchlist_comparables`, which covers all eight shops. More
  cards can only add twins to refuse.

**Stop 3, legitimate.**
- The gate's #83/#88 checks are vision judgements. Without a recorded vision verdict the
  concept **waits** (unmeasured is never passing).
- `radar.intake.rescore_judged` re-scores it automatically once a verdict exists.
- No path yet asks the paid vision judge about a radar-intake concept that has no board. That
  belongs to the creative director's budget and `image_vision`, which is closed in SHADOW. It
  is not bypassed here.

**Conclusion, new.** `radar.concept_intake` now ends every cycle with
`research_flow.conclude`. It stores one dated reading, `intel.research_conclusion`, with one of
two outcomes:
- `opportunities`: each qualifying opportunity, the stage it reached and what holds it.
- `no_qualifying_opportunity`: the evidence behind it (shops compared and fresh, validated and
  UNKNOWN arenas with their reasons, the writer's skip reasons, intake counts).

The reading uses aliases and our own words only, and `_assert_no_content` refuses a shop name
or key.
