# Build 2 ledger (W4-B2)

Generated 2026-10-10T03:26:33+00:00 by `research/final_build/w4/build2_ledger.py` from `build2.closure.ledger` (evidence-computed; registry status is the claim under test).
Gate readings: production GET /api/build (read-only), deployed commit fcb982d, read 2026-10-10.

## Reconciliation of the owner dashboard figure

The dashboard's `Build 2: 227/320 complete (70.9%), executable remaining 45, owner-gated 28, data-gated 20` is `build2.requirements.coverage()` served by production `/api/build2` at deployed commit fcb982d (read-only GET 2026-10-07: `evidence_B2/prod_build2_coverage_fcb982d.json`). That registry dates from 2026-09-22 (af3a12f/53227fa). It is stale -- the 2026-09-27/28 certification reopened and re-parked rows, giving covered 218 / partial 85 / owner 9 / data 8 on the integrated branch -- and miscounted in meaning: `executable_remaining` = partial + missing, so partial rows parked on owner/data/external gates read as executable work, and `complete` is the registry's claim, not proof. The figures below are `closure.dashboard()` / `closure.ledger()`: evidence-computed, gated rows by the kind of their gate, OPEN the only executable remainder.

| state | rows |
|---|---|
| PROVEN | 215 |
| OWNER-GATED | 54 |
| DATA-GATED | 41 |
| EXTERNAL-GATED | 7 |
| NOT-APPLICABLE | 3 |
| OPEN-DEFECT | 0 |

## Gated rows by exact gate

| gate | kind | state | rows |
|---|---|---|---|
| acceptance_ruling | OWNER-GATED | unchecked | #189 #221 #222 #320 |
| ad_authority | OWNER-GATED | closed | #294 #295 |
| benchmark_purchases | OWNER-GATED | closed | #163 #165 #168 #315 #317 |
| customers | DATA-GATED | closed | #8 #18 #19 #20 #21 #25 #28 #31 #33 #41 #45 #48 #120 #147 #169 #226 #229 #235 #242 #243 #244 #245 #252 #253 #256 #257 #258 #260 #265 #270 #272 #280 #292 |
| image_vision | OWNER-GATED | closed | #15 #44 #61 #67 #86 #88 #116 #126 #218 #277 #281 #304 #308 #309 |
| insights_access | OWNER-GATED | unchecked | #1 #37 #54 #236 #237 |
| live_listings | OWNER-GATED | closed | #14 #16 #46 #238 #239 #241 #254 #263 #266 |
| model_bearing_render | EXTERNAL-BLOCKED | unchecked | #72 #130 #202 #203 #300 |
| offsite_storage | OWNER-GATED | closed | #51 |
| owned_surfaces | OWNER-GATED | closed | #4 #10 #246 #247 #248 #251 #255 |
| physical_proof | OWNER-GATED | closed | #64 |
| production_window | OWNER-GATED | unchecked | #195 |
| rendered_pages | EXTERNAL-BLOCKED | closed | #35 #39 |
| tester_roster | OWNER-GATED | closed | #9 #43 #250 |
| transactions_r | OWNER-GATED | unchecked | #11 #12 |

NOT-APPLICABLE (process directives to the auditor, followed): #32, #56, #197

OPEN-DEFECT: 0
