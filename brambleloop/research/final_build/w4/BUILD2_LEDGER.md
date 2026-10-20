# Build 2 ledger (W4-B2)

Generated 2026-10-20T12:20:09+00:00 by `research/final_build/w4/build2_ledger.py` from `build2.closure.ledger` (evidence-computed; registry status is the claim under test).
Gate readings: production GET /api/build (read-only), deployed commit fcb982d, read 2026-10-07.

## Reconciliation of the owner dashboard figure

The dashboard's `Build 2: 227/320 complete (70.9%), executable remaining 45, owner-gated 28, data-gated 20` is `build2.requirements.coverage()` served by production `/api/build2` at deployed commit fcb982d (read-only GET 2026-10-07: `evidence_B2/prod_build2_coverage_fcb982d.json`). That registry dates from 2026-09-22 (af3a12f/53227fa). It is stale -- the 2026-09-27/28 certification reopened and re-parked rows, giving covered 218 / partial 85 / owner 9 / data 8 on the integrated branch -- and miscounted in meaning: `executable_remaining` = partial + missing, so partial rows parked on owner/data/external gates read as executable work, and `complete` is the registry's claim, not proof. The figures below are `closure.dashboard()` / `closure.ledger()`: evidence-computed, gated rows by the kind of their gate, OPEN the only executable remainder.

| state | rows |
|---|---|
| PROVEN | 229 |
| OWNER-GATED | 39 |
| DATA-GATED | 41 |
| EXTERNAL-GATED | 6 |
| NOT-APPLICABLE | 3 |
| OPEN-DEFECT | 2 |

## Gated rows by exact gate

| gate | kind | state | rows |
|---|---|---|---|
| acceptance_ruling | OWNER-GATED | closed | #189 #221 #222 #320 |
| ad_authority | OWNER-GATED | closed | #294 #295 |
| benchmark_purchases | OWNER-GATED | closed | #163 #165 #168 #315 #317 |
| concept_outcomes | DATA-GATED | closed | #89 |
| customers | DATA-GATED | closed | #8 #18 #19 #20 #21 #25 #28 #31 #33 #41 #45 #48 #120 #147 #169 #226 #229 #235 #242 #243 #244 #245 #252 #253 #256 #257 #258 #260 #265 #270 #272 #280 #292 |
| insights_access | OWNER-GATED | closed | #1 #37 #54 #236 #237 |
| lead_lag_series | DATA-GATED | closed | #140 |
| learning_sources | DATA-GATED | closed | #98 |
| listing_traffic | DATA-GATED | closed | #23 |
| live_listings | OWNER-GATED | closed | #14 #16 #46 #238 #239 #241 #254 #263 #266 |
| market_outcomes | DATA-GATED | closed | #94 |
| model_bearing_render | EXTERNAL-BLOCKED | closed | #72 #130 #202 #203 #300 #308 |
| owned_surfaces | OWNER-GATED | closed | #4 #10 #246 #247 #248 #251 #255 |
| physical_proof | OWNER-GATED | closed | #64 |
| production_window | OWNER-GATED | closed | #195 |
| rendered_pages | OWNER-GATED | closed | #35 #39 |
| season_harvest | DATA-GATED | closed | #298 |
| seasonal_orders | DATA-GATED | closed | #296 |
| style_outcomes | DATA-GATED | closed | #82 |
| tester_roster | OWNER-GATED | closed | #9 #43 #250 |

NOT-APPLICABLE (process directives to the auditor, followed): #32, #56, #197

OPEN-DEFECT: 2 -- #11 gate transactions_r has opened; the remaining work is no longer parked, #12 gate transactions_r has opened; the remaining work is no longer parked
