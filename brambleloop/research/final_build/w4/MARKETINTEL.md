# W4-MARKETINTEL: market intelligence without the owner collecting it

Date: 2026-10-11 (UTC). Branch `claude/w4-MARKETINTEL`, from `origin/claude/w4-INTEG2` 1982501.

Owner instruction: "I do not want to manually collect Etsy search terms, screenshots or
competitor data. That is what these agents were built to do."

## 1. The exact Etsy limitation (from Etsy's own document)

Etsy's Open API v3 description is
`https://www.etsy.com/openapi/generated/oas/3.0.0.json`. I read it on 2026-10-11: HTTP 200,
911,340 bytes, sha256 `b993d52f46afdf87f7687dc6ff8885f2b012589f9b123e1faf14cc54ee73a9ef`,
76 paths, 105 operations. The facts are vendored in
`evidence_MARKETINTEL/etsy_openapi_facts_2026-10-11.json`.

**What the document does not contain:**
- Occurrences of these strings: `insight` 0, `stats` 0, `statistic` 0, `search volume` 0,
  `traffic` 0, `visit` 0, `impression` 0, `trend` 0.
- Any operation for Marketplace Insights, search-term volume, shop stats, traffic or
  impressions. No operationId matches search/insight/stats/statistic/traffic/visit.

**The only marketplace search:** `findAllListingsActive`, at `GET /v3/application/listings/active`.
- Its parameters are `keywords`, `taxonomy_id`, `sort_on`, `min_price`, `max_price` and so on.
- It returns `{count, results}`: a count of matching *active listings*, not searches.

**Listing counters:**
- `views` exists only on `ShopListingWithAssociations`, described as "tabulated once per day
  and only for active listings".
- `num_favorers` is described as "the number of users who marked this Listing a favorite".

**Conclusion.** No sanctioned API exists for Marketplace Insights, search-term volume or
shop stats. These are visible only on the logged-in Shop Manager page. The repository already
recorded this as `intel.etsy_surfaces` marketplace_insights = UNSUPPORTED (absence probe
`insight` 0). Today's document confirms it.

**Not done, by rule:**
- Shop Manager is not automated.
- etsy.com pages are not scraped.
- No bot protection is passed. etsy.com/legal and search pages answer software with 403
  (DataDome), per decisions B-268 and B-500.

**The "trending crochet patterns" search page.** This is the seed
`etsy.com/search?q=crochet pattern…` in `spec/05_Competitor_and_Market_Seeds.txt`. Its only
approved access path is:
- the `rendered_pages` / browser-worker boundary (B-268, B-500), which is not built because
  it would meet the same 403;
- owner screenshots (`radar.market` uses them).

The sanctioned substitute is the API search index (SERP laboratory). I kept that boundary.

## 2. The compliant alternative, running on the existing scheduler

`intel.serp_capture` runs daily on the existing cadence. It now calls `intel.market_intel.refresh`
after each capture, and also when the capture is blocked. Every figure carries its label,
exact source and timestamp. An absent figure is `None` with a reason, never 0.

| figure | source | label |
|---|---|---|
| competition | findAllListingsActive `count` | PROXY (active listings, not searches) |
| competition_change | the same count, newest vs previous snapshot | PROXY |
| favourite_velocity | median num_favorers gained per day by results present in both snapshots | PROXY demand interest (favourites are neither searches nor sales) |
| recent_entrant_share | share of the top 24 whose `original_creation_timestamp` is under 90 days old (newly captured) | PROXY market entry |
| insights_search_count | owner-recorded Marketplace Insights (InsightsSnapshot) | MEASURED by Etsy, recorded by the owner |
| opportunity | favourite_velocity per 1,000 matching listings | PROXY ratio |

The existing benchmark (MJs) scans, the culture and seasonal feeds, and the SERP laboratory keep
running as before. Once the transactions_r scope and a working credential exist, the existing
`commerce.orders_ingest` and Stats-CSV attribution (`POST /api/attribution/stats`) supply
conversion truth. No proxy is relabelled as search volume.

**Production today.**
- Production's first SERP capture (2026-10-11T14:00Z) received HTTP 403 for every target
  query. The Etsy credential has been refused since 2026-10-07; see B2_GATE2_REPORT F4.
- `serp.capture_targets` now stops at the first 401/403 instead of sending every query with a
  refused key.
- Until the owner restores the credential, the market proxies have no new data. Production
  holds 0 SERP snapshots.

## 3. Routing, through existing consumers (proved in a scratch run)

`tests/test_w4_marketintel.py::test_findings_reach_seo_creative_engineering_and_learning`
seeds two snapshots, runs `refresh`, and checks that each existing consumer reads the result:

- **SEO.** Subject `search_language` is read by `listing.seo` through
  `consume.matching('seo_search', …)`. The proxies also enter the SEO keyword-evidence store:
  `seo.evidence._collect_market_intel`, labelled `proxy:demand_interest` and
  `proxy:market_entry`.
- **Creative.** The same lessons reach `bus.brief_lessons`, routed to the product_creativity
  inbox.
- **Crochet Engineer.** The top 3 proxy opportunities are published as subject
  `construction_preference`. The pipeline's radar.score reads them through
  `consume.matching('pattern_engineering', …)`. A concept still passes the tournament, the
  jury and CIR validation.
- **Learning (experiments).** Each opportunity is pre-registered as a growth experiment
  (`market_intel:<query>`), gated on `live_listings`, so the proxy is tested against real
  outcomes.
- **Product Truth.** A new rule, `store_foundation.lint` TRUTH_MARKET_CLAIM, refuses
  "trending", "in demand", "high demand", "viral", "most searched" and similar. The SEO tag
  validator (`seo.truth.check_term`) refuses the same wording, because every demand figure we
  hold is a proxy.

## 4. The one owner step, made small

The phone page is **`/ops/insights`**. It redirects to the Insights section of the existing
owner phone page, `/ops/teardown#insights`, whose script is the only one the page security
policy allows. To record a reading:
1. Paste the operator token.
2. In Shop Manager > Marketing > Marketplace Insights, search a term, copy the view and paste
   it.
3. Tap **Check the parse**, then **Record**.

How the intake behaves:
- `POST /api/insights/paste` requires the operator token. It parses deterministically
  (`market_intel.parse_insights`) and returns every line it did not understand. It records
  nothing until `confirm`.
- On confirm it writes InsightsSnapshot rows through the existing `insights.record`. The
  provenance is `recorded_by` plus the sha256 of the paste. The text itself is not stored.
- Screenshots are not parsed. Reading an image needs `image_vision`, which is unfunded, and
  would not be deterministic.
- The owner card `insights_reading` now points at the page. Its time estimate is now 5 min
  (was 10).

**Which requirements truly need the person:**
- **#1, #37, #236** need Etsy's own search counts. Only Shop Manager shows them. One paste
  opens `insights_access` for all five rows.
- **#237** needs the owner's **Etsy Stats CSV export** (`POST /api/attribution/stats`) and
  orders, not an Insights reading. Opening `insights_access` with a paste would un-park it
  without its real input. **Classification finding for the ledger:** #237's gate should be
  the Stats export plus orders, not `insights_access`.
- **#54**: the company part is proven. Its owner half is the pre-launch traffic baseline,
  which is also a Stats export or an Insights reading.

## Changes

New files:
- `intel/market_intel.py`
- `/api/market-intel`, `/api/insights/paste`, `/ops/insights` (redirect) and the Insights section of `/ops/teardown`, in `app/main.py`

Modified files:
- `intel/serp.py`: creation time; stop on 401/403
- `runtime/release.py`: refresh in `intel.serp_capture`
- `seo/evidence.py`, `seo/truth.py`, `store_foundation/lint.py`
- `ops/owner_queue.py`: insights card

Tests:
- `tests/test_w4_marketintel.py`: 7/7 (new).
- Passed one at a time, each with a private TMPDIR: test_serp, test_insights_intake, test_insights_budget, test_route_auth_default_deny (7/7), test_web_security (11/11), test_r2_product_store_lint, test_v11_store_foundation, test_w3_lint_handmade_aspiration, test_v11_seo_truth (9), test_v11_seo_proposals (8), test_v11_seo_cycle (8), test_w4_mjs_findings, test_w4_owner_actions (6).

No Etsy write, spend or credential change.
