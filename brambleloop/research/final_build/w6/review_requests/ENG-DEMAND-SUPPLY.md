# ENG-DEMAND-SUPPLY: demand-led supply, engine demand, original core-family concepts

Branch `eng/demand-supply`, cut from `claude/w6-INTEG7-wip` @ c6d4400.
- **Status:** NOT merged and NOT deployed. Production is unchanged.
- **Hygiene:** no PR opened. No Railway variables or secrets were read.
- **Measurement:** everything is measured on fixtures. No production reading was taken.

- **Tested SHA:** `0c1305767fa1cec8db99d903daa1a70b636fbe80` (the commit after it touches only this file).
- **Decision:** D-ENG-DEMAND-SUPPLY (DECISION_LOG). BUILD_STATE has its entry at the top.

## What it does
1. **`products/demand.py`: a deterministic demand score from stored evidence only.**
   - **Inputs:**
     - `benchmark_listings`: favourites level; favourites velocity from dated `favorers_history`; per-listing
       `review_count` / `review_history`, `is_bestseller` and `in_baskets`, each counted only where stored;
     - `serp_snapshots`: rank attention, 1/sqrt(rank);
     - the owner's two dated teardown records: numbers and clusters only, never a competitor title.
   - **Clusters:** scored per family/form/subject, backing off to family+form and then to family when there are
     fewer than 3 readings. Recency has a 30-day half-life and a 180-day cut-off.
   - **UNKNOWN is never 0.** A missing signal lowers confidence, and the score shrinks to PRIOR 0.20.
   - **Core-family boost:** amigurumi 0.30 > baby 0.26 > pillow 0.22 > garment 0.18, scaled x(0.5 + 0.5·confidence).
     Flat décor and seasonal get none.
   - **Scanner change:** `intel.observe.scan` now keeps `favorers_history`, bounded at 30 readings and seeded from
     the previous scan's dated count.
2. **Demand-led admission.**
   - `supply.offers` sorts by market demand first, then research flag, then producer score.
   - `radar.intake.run` evaluates in demand order (`order_by_demand`).
   - **Engine gate in `supply.admit`:** an offer with no certified engine is refused as `engine_demand:<family>`.
     It is recorded once as `supply.engine_demand` (retention: lifetime) and stays waiting, so it is admitted on
     the first pass after its engine certifies (tested).
   - **Exempt from the gate:** engineered designs (`pipeline.ENGINEERED`, Launch-0 legacy routes) and offers that
     name no category.
   - WIP refill is unchanged: `after_chain_job` plus the 15-minute `supply.admit`.
3. **`radar/demand_originals.py`: 28 house-original core-family and clothing concepts.**
   - **Mix:** 14 amigurumi, 4 baby, 4 cushions, 6 garments.
   - **When it runs:** at the start of each `radar.concept_intake` pass, only for families a scan has observed,
     and at most 6 per pass.
   - **Evidence:** each family has an evidence task whose confidence follows the demand reading.
   - **Gates:** every intake gate judges each concept. Before attaching, a title that overlaps an observed listing
     is skipped.
   - **Re-proposal:** the trigger carries an engine-table digest, so an engine certification re-proposes on fresh
     evidence.
   - **On fixtures:**
     - **10 approved, buildable today:** ball bear, bunny and teddy; bear and bunny loveys; 2 envelope cushions;
       adult and baby raglan cardigans; kids sweater.
     - **18 refused as `construction_unsupported:*`, which is engine demand:** 11 new animals, lamb and fox
       loveys, 2 face cushions, adult one-piece, vest, drop-shoulder.
4. **Surfaces.**
   - Mission Control Demand view: `GET /api/cc/demand`, `js/views/demand.js`, `sw.js` `cc-shell-v44`.
   - The view shows the ranked "build this engine next" list (supply records + intake holds + POOL), demand by
     family and cluster, and the POOL re-classification.
   - Advisory readback row `engine_demand`: WARN/PASS, never FAIL. Readback items go from 20 to 21.

## POOL re-classification (fixtures; production's live "18 held" was not measured)
20 of 34 POOL concepts have no certified engine. Each one is named on the Demand view with the engine it needs:

| Engine needed | Concepts |
|---|---|
| amigurumi shapes | woodland-fox, no-sew-reindeer, pocket-penguin-trio |
| garment routing | boxy-summer-tee, cropped-cardigan |
| seasonal_decor | spooky-garland, valentine-heart-garland, pumpkin-cluster-set, nordic-forest-bundle |
| flat_panel shapes | cloudline-baby-hat, cottage-wall-hanging |
| nursery | nursery-cloud-mobile |
| hat | alpine-slouch-beanie |
| ornament | nordic-star-ornaments |
| flower | pressed-flower-motifs |
| triangle | lattice-triangle-shawl, mothers-day-shawlette |
| tote | everyday-market-tote |
| cosy | easter-egg-cosies |
| stocking | nordic-forest-stocking |

## Tests
New suite `tests/test_eng_demand_supply.py`: **22 tests, 0 failed.** It covers:
- **The score:** deterministic and pinned arithmetic; velocity; recency.
- **Ordering:** boost order; flat décor ranks only on evidence.
- **UNKNOWN handling:** UNKNOWN never 0 and never high; None vs measured 0.
- **Engines:** engine verdicts; engine-demand ranking.
- **POOL and admission:** POOL re-classification; admission order + engine-demand record + panel/readback;
  re-admission after certification; intake demand order.
- **Originals:** the catalogue (≥20, core, pairwise novelty ≥ 0.45, competitor-overlap skip); the scan-evidence
  guard; originals end to end through the real intake.
- **Three killed mutants:** UNKNOWN→0, flattened boost, engine gate removed.

The required and touched suites, run on this tree and on the base worktree (c6d4400):

| suite | this branch | base c6d4400 |
|---|---|---|
| test_eng_demand_supply | 0 failed | n/a |
| test_eng_supply | 0 failed (17) | — |
| test_w5_concept_intake | 0 failed | 0 failed |
| test_w5_a4a_research_to_concept | 0 failed | 0 failed |
| test_eng_families | 0 failed | 0 failed |
| test_eng_garment | 0 failed | 0 failed |
| test_eng_plush | 3 failed | **3 failed (pre-existing)** |
| test_research_flow | 0 failed (22) after the fix below | 0 failed |
| test_w4_research | 10 passed | — |
| test_w4_fmbatch1_research | 13 passed | — |
| test_w4_research_to_product_stall | 0 failed | — |
| test_r5_research_2 / _3 / _4 | 3 / 4 / 3 failed | **3 / 4 / 3 failed (pre-existing)** |
| test_ws2_research_m2 | 1 failed | **1 failed (pre-existing: coaster held by flat_panel)** |
| test_vacuity | pass | — |
| test_w4_resume_runner | 0 failed (40 OK) | 0 failed |
| test_v11_pwa_static | 87 passed | — |
| test_w4_readback_evidence | 23/23 | — |
| test_eng_daily | 0 failed | — |
| test_etsy_readback_observe | 37 passed | — |
| test_compiler / test_reverse / test_twin | pass | — |

**Test edits outside the new suite:**
- `test_w4_readback_evidence`: the advisory row is added; count 20 → 21.
- `test_research_flow`: two lines now select the watchlist task by trigger. Originals legitimately attach their
  own evidence task when the simulator's listings carry favourites.
- `scripts/suite_final_segment.txt`: declares the new date-sensitive suite.

**Autonomy map:** regenerated. Only the timestamp changed, because no new job type was added: originals run inside
`radar.concept_intake`.

## Honest gaps
- Per-listing review counts, bestseller and "in baskets" are UNKNOWN until a scan stores them. The public API
  scan does not read them today, so those signals lower confidence instead.
- SERP entries carry pod but no title, so SERP attention is attributed at the family level unless the query names
  the same family.
- Amigurumi titles the engine builds today are limited to its closed vocabulary ("Cosy Round Bear Amigurumi").
  The new animals wait on the plush engine extension.
