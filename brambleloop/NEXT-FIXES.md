# NEXT-FIXES — production evidence 15:00Z, release 5297dbba

Branch `eng/next-fixes` (from 5297dbba). Not deployed. No production database was read for
this work: every finding comes from the code and from reproductions on a scratch database.

## 1. Sale admission refuses four products as "product is RETIRED"

Products: cloudline-baby-blanket@1.2.0, winter-village-graphghan@1.3.0,
valentine-heart-garland@1.3.0, spooky-garland@1.3.0.

**Finding: a cached lifecycle (defect).** `sale_admission` reads
`products.lifecycle.derive(...)["stage"]`. `_derive` first checks the company-memory record
`product.lifecycle:<slug>`. If that record's stage is REJECTED, ROLLED_BACK or RETIRED,
`_derive` returns it and never looks at the rows. But `observe()` writes the same record after
every pipeline job, with `observed: True`, and stores whatever stage the rows derived at that
moment. Before 19i14, the rows derived RETIRED for "withdrawn and never on Etsy". So these
products got an observed RETIRED written to memory. After 19i14 fixed the rule, `_derive`
kept replaying the cached value, and the fixed rule never ran for them.

I ruled out the other suspected sources:
- No code calls `lifecycle.transition()`, so there is no deliberate launch or seasonal
  retirement. Nothing else writes `product.lifecycle:` keys.
- `sale_admission` and parked runs re-evaluate admission on every call (`admit_for_sale` →
  `sale_admission` → `derive`). The only per-request memo is `request_memo`, which is
  request-scoped. Nothing parked is cached across calls.

**Fix** (`products/lifecycle.py`): only a deliberate transition (a record without
`observed`) is terminal. An observed record is treated as a cache, and the rows decide. The
next `observe()` overwrites the stale RETIRED with the derived stage. It also logs a
`product.lifecycle_anomaly` (RETIRED → VISUAL is not an allowed move). Nothing consumes that
anomaly, and recording it is the honest outcome.

**Caveat:** if the owner's Etsy exercise really set `etsy_listing_id` on any of these four
listings, they will still derive RETIRED after this fix. That would be a real retirement
(time on Etsy), and the code is right to leave it. Run
`select product_slug, state, etsy_listing_id from listing where product_slug in (...)` on
production to tell which case applies.

**Test:** `tests/test_gallery_start.py::test_an_observed_retirement_the_rows_no_longer_show_is_not_replayed`.
It fails without the fix ("stage RETIRED, basis recorded transition") and passes with it. It
also checks that a deliberate RETIRED still refuses admission.

## 2. The concept gate holds five concepts at `board_missing / prototype_refused`

**Finding: no engine is missing. The board path is the defect.** `radar.intake` admits a
concept only into a family whose engine is verified, or carries a physical gate
(`construction_families.route`). But `creative.intake.file_radar_board` drew the board with
`creative.prototype.author`, which only sizes flat and round forms (`FORM_GEOMETRY`). It
refuses these forms:
- `toy`: ball-body amigurumi bear or bunny, lovey
- `draped_garment`: shawl, wrap
- wearable `fitted_garment`: socks, slippers, baby dress or romper

Those families all have admitted engines. The only one with its own board route was the
stuffed-animal engine (`toy_board`, FLUX). Every other admitted concept in these families got
`prototype_refused`, was never judged, and waited at the gate forever.

Reproduced with the families' own proof proposals on a scratch DB:

| concept (pod) | form | before | after |
|---|---|---|---|
| runner (kitchen_bath), basket, cushion, bowl (home_decor) | flat/round | board | board |
| ball bear, lovey (home_decor) | toy | prototype_refused | board |
| baby dress, socks, slippers (garments) | fitted_garment | prototype_refused | board |
| shawl, wrap (garments) | draped_garment | prototype_refused | board |
| beanie, tote, market bag (garments) | hat / bag | board | board |
| frog (home_decor, animal engine) | toy | toy_board route | toy_board route (unchanged) |

The five production concepts therefore belong to the **garments** pod (wearables and shawls)
and/or toy-form concepts in **home_decor**/baby. Their exact slugs are in production's
`regated.radar_held`, which I did not read from here.

**Is admission filling slots with families that cannot compile?** No. I checked three places:
- `radar.intake.validate` already refuses any family without an admitted engine
  (`construction_unsupported:<family>`).
- `judge_radar_waiting` adds a board-less concept to `held` without counting it against the
  judge-call cap (`asked_n` only counts concepts that have a board).
- `products.supply` only receives offers for concepts that passed the gate.

So bags and home_decor concepts were never queued behind these, and no admission change was
needed. Every gate is unchanged.

**Fix** (`creative/board.py`, `creative/intake.py`): when the prototype refuses,
`file_radar_board` now draws the board from the engine's own draft
(`board.make_engine_board`). It uses the same inputs `radar.score` gives `cir.draft`
(`toy_board.draft_inputs`), the same route (`FC.plan` / `construction_families.route` for
wearables) and the same builder:
- The draft must compile.
- The fabric is rendered from its digital twin. It is disclosed as a deterministic render,
  not a photograph. CA$0, no image provider.
- Wearables render their middle sourced size. The audience check `cir.draft` applies is
  repeated.
- A family whose engine is not admitted gets no board. Stuffed animals keep `toy_board`.

The vision judge, `radar.score` and the full pre-engineering gate still decide the concept.
A new fixed reason code, `engine_draft_refused`, records why the engine draft gave no board
too.

**Tests:** `tests/test_next_fixes_engine_board.py` covers three things:
- bear, shawl and socks get a filed, digest-bound, non-blank engine board;
- the defect reproduced, with the engine board removed;
- no board for an unapproved concept.

The first test fails without the fix (`prototype_refused`).

## Suites run

`SUITE_REGISTRY=0 PY=python3 SUITES="…" JOBS=$(nproc) bash run_tests.sh`. Passing: 21 tests
in 7 suites, 0 failing:
- test_gallery_start
- test_next_fixes_engine_board
- test_concept_board_why
- test_new_product_flow
- test_w4_fmbatch1_lifecycle
- test_w4_fmbatch2_lifecycle_pipeline
- test_vacuity

`PY=python3` was needed because this container has no `.venv`.

`tests/test_amigurumi_judging.py` (the stuffed-animal board route, which now runs after the
engine-board fallback) is very slow here. A direct run timed out at 3300s with 5 of 11 tests
passed and 0 failed:
- crash between request and record is never bought again
- refusal before sending is declined and may be asked again later
- a render that may have been paid for is never bought again
- a toy the animal engine will not draft is never rendered
- an amigurumi concept from scan evidence reaches cir.draft unaided, paid once

The remaining 6 tests were not reached, so they are **unverified**. Run the full suite in CI
or on a larger runner before merging.
