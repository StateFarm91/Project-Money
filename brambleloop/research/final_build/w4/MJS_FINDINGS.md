# MJs / competitor intelligence findings (lane W4-MJS)

As of 2026-10-07T00:04Z. Machine-readable version: `MJS_FINDINGS.json`. Regenerate with
`PYTHONPATH=src python research/final_build/w4/mjs/snapshot_findings.py` (add `--offline` to
re-run from `mjs/raw_snapshot.json` without network).

## Where the evidence comes from

- **Source.** The production service's public read-only JSON endpoints, called with HTTP GET only: `/api/teardown` (mjs_market_map), `/api/arbitrage/departments`, `/api/arbitrage?pod=*`, `/api/gallery-intelligence`, `/api/mjs` and `/api/audit`. These endpoints serve the data that production's own `mjs.scan` and `mjs.reviews` cadences collected through the sanctioned Etsy Open API v3, which is read-only.
- **What this lane did not do.** It made no Etsy call of its own, scraped nothing and wrote nothing to production.
- **Deployed build.** Production runs `fcb982d`, which is 666 commits behind `claude/visual-investigation`.
- **Competitor content.** No competitor titles, descriptions, tags, review text, images, charts or instructions are stored here. The findings are counts, medians and shares only.

## What actually ran in production (audit evidence, 2026-09-19 → 2026-10-07)

| Cadence | Production state |
|---|---|
| `mjs.scan` (6-hourly on the deployed build) | **Running.** At least 72 `mjs.scanned` rows. The latest scan saw 441 listings, inspected 65 and skipped 310 unchanged. It was blocked from 2026-09-19T06:00 to 18:00 because `ETSY_API_KEY` was unset, then started working. |
| `learning.ingested` | **Running.** 18 rows across four learning domains. |
| `mjs.reviews` (weekly) | **Running.** 3 rows. 100 reviews read, recorded as theme counts only. |
| `intel.gallery_analysis` | **Stalled since 2026-09-24.** 175 or more `intel.gallery_analysis_blocked` rows say "no vision probe has succeeded". 34 of 154 audited listings have a judged image. |
| `intel.serp_capture`, `intel.panel_discovery`, `intel.benchmark_refresh`, mission pipeline (`mjs.mission_events`), `mjs.pod_capability`, `mjs.seasonal_sentinel` | **Never ran in production.** None of these exist on the deployed `fcb982d`. They are wired on this branch only and need a deploy. |
| Market map | **Two defects, fixed here.** `has_video` reported False for all 440 listings, while the per-pod audits recorded video on 116 of 142. Seasonal positioning read "none stated" for all 440. |

## Findings

**Confidence grades.** `observed` means the finding was read directly from the evidence. `proxy` means a stand-in was used, such as favourites in place of sales, or shelf allocation in place of demand.

| Key | Grade | n | Finding | Opportunity | Consumer (bus subject → cells) |
|---|---|---|---|---|---|
| assortment | proxy | 441 | The benchmark's catalogue is garments 32%, hats 20%, blankets 19% and collections 7% | — | Stored reading only; seasonal benchmark matrix |
| demand_by_pod | proxy | 437 | Median favourites per listing: garments 1701, stockings 1472, blankets 1400, amigurumi 1111, bags 920. Stockings get above-median favourites from a below-median number of listings | Original stocking concepts: demand per listing is high and the benchmark's range is thin | `radar.arbitrage.score_observed` (demand) |
| pricing | observed | 437 | Pattern prices are tightly clustered: the median is CA$18 in most pods, CA$22 for garments and CA$19 for stockings, with near-zero IQR. 0 of 441 listings were on sale. Brambleloop's radar concept pool is priced 39–69% below these medians | Test launch prices inside the observed band. Radar scoring still uses the pool prices, although release pricing already anchors on the observed median | `pricing_response` → pricing, portfolio, finance |
| bundle_premium | observed | 437 | Collections sell at a median of CA$60.5, against CA$18 for single patterns (3.36×, n=29) | Plan every launch family with a priced bundle | `pricing_response` → pricing, portfolio, finance |
| presentation | observed | 441 | The median gallery has 10 images: 342 listings have 10 or more and 58 have fewer than 5. 116 of 142 audited galleries include a video. The most common judged shots are flat_lay, in_use and hero_styled | Ten images plus a technique video is table stakes. The benchmark's thin galleries are the opening | `thumbnail` → creative_assets, seo_search, product_creativity |
| palette | observed | 143 | 87 of 143 hero palettes are low-saturation neutrals (saturation below 15) | Test saturated colourways against neutral ones in briefs | `palette` → product_creativity, creative_assets |
| seasonality | proxy | 441 | The Christmas window (2026-12-25) is open. The benchmark has 10 stocking and 13 ornament listings. Positioning by title is unmeasured from public endpoints | Prioritise Christmas stocking and ornament quick makes now | `seasonal_timing` → market_radar, growth, portfolio, product_creativity |
| customer_pain | observed | 100 | 5 of 100 reviews are rated 3 or lower. The recurring theme is "instructions unclear" (3 reviews) | Sell instruction clarity as a feature: stitch counts, photo steps, stated US terms | `instruction_clarity` → pattern_engineering, quality, customer_experience |
| deliverable_gaps | observed | 439 | 154 of 439 descriptions are unclear. They are silent on delivery (438), page extent (432), hook (218), finished size (196) and terms (79) | Add a complete "what you get" block to every listing | `delivery_experience` → customer_experience, creative_assets, quality |
| coverage_gaps | observed | 7 | 7 proven arenas have no Brambleloop answer: hats/wearables, amigurumi, garments, collections, Christmas stockings, kitchen/bath and education | Use the top gap-queue arenas as the next original-concept briefs | `intel.mission_runtime.consume_concepting` |

**Unmeasured findings**
- **seasonal_positioning:** the public endpoints carry no titles. The in-database cadence path measures it.
- **search_index:** `intel.serp_capture` has never run in production.

**Blocked sources**
- **Image judgements:** the vision probe is failing.
- **Rendered etsy.com search and shop pages:** these return HTTP 403 and were not scraped.
- **Marketplace Insights:** there is no API for it.
- **Competitor sales and revenue:** the API does not expose them, so favourites are used as a labelled proxy.

## How the findings flow downstream (runtime)

1. The `mjs_scan` cadence runs `mjs.scan`, which calls `_run_mjs_mission` and then `intel.findings.refresh` (`runtime/release.py`).
2. Each day's findings are stored as an `OperatingReading(kind="mjs.findings", period_key=<date>)`, with an audit row of `mjs.findings`.
3. Actionable findings are published with `improve.bus.publish(origin_cell="learn")`.
   - Each lesson is idempotent on `mjs_finding:<key>:<digest>`.
   - When a finding's numbers change, its new lesson supersedes the previous one, so an inbox never holds two versions of the same fact.
4. Findings reach these readers:
   - `radar.score` reads them through `improve.consume.matching("market_radar")` and nudges the concept score within its bound, recording `bus.acted_on`.
   - `creative.ideation.lessons` reads them through `bus.brief_lessons`, so they feed every tournament and expedition brief.
   - The SEO, support and pricing inboxes also receive them.

`tests/test_w4_mjs_findings.py` proves this path at runtime:
- The Scheduler tick leads the Worker to run `mjs.scan`, which stores the reading and publishes the lessons.
- `radar.score` for `nordic-forest-stocking` acts on the seasonal lesson, with `lesson_adjustment > 0` and `acted_on` set to market_radar.
- The creative brief draws on every product_creativity-routed finding.
- A second window with the same evidence publishes nothing new.
- A changed catalogue the next day produces a new pricing finding, supersedes the old lesson and stores a second day's reading, all without any prompt.
