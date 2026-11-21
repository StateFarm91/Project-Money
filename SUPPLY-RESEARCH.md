# ENG-SUPPLY-RESEARCH: READY concepts were blocked by research that could not arrive

## Symptom (production 5188badb, 15:51Z)

`factory_visibility.supply.last_admit` read {ready 32, admitted 0, waiting_on_research 32}, and the allowance was 5 units. Every pod's research was `absent`:

- amigurumi, bags and home_decor: `no_watchlist_gap`;
- garments and hats: `gap_not_pursuing`.

## Root cause

1. **No deploy pass for the comparison.** ENG-SUPPLY-FEED (`watchlist.link_demand`, deployed in 19h10) opens a watchlist gap and a research question for the arenas we already sell in. It does this only inside `intel.watchlist_compare`. That job ran daily and last ran at 00:39Z, before 19h10, and the next run was 00:38Z tomorrow. So no gap existed for covered pods.
2. **Durability could not be met for days.** `watchlist_research.answer` needs DURABLE_DAYS (3) distinct observation dates per shop, for at least 2 shops. It read those dates only from the daily comparison readings. The readings written before ENG-SUPPLY-FEED have no `demand_arenas`, so covered pods had no recorded observation dates, even though the successful scans that observed them are recorded. Even after a compare, the answer would have waited about 3 more days.

## Fix

The research requirement is unchanged and no gate is weakened. Nothing new is paid.

- **`watchlist_research.scan_history`** reads the same observations from their primary records. For each shop, it collects the dates of a *successful* read (`intel.watchlist_scan` audit with shop ran=True, or `mjs.scanned` for the anchor) on which the stored catalogue held ≥ MIN_LISTINGS_FOR_ARENA live listings in the pod (first_seen ≤ day ≤ last_seen). Withdrawn rows and failed reads never count.
- **`durability_with_history`** unions those dates with the readings and applies the same rule: 3 days, ≥ 2 shops. History fills **only** days whose reading predates ENG-SUPPLY-FEED (no `demand_arenas` key). A day with a current reading is decided by that reading alone. When the history contributes, the durability fact cites a recorded `benchmark_listings+scan_audit` source.
- **Boot step:** `intel.watchlist_compare` is queued once per deploy, before the pool and intake passes.
- **Cadence:** left at 24 h, which the r5 research suites pin. A daily answer can read `evidence_expiring` for about the last 2 hours before the next compare. That is a known residual, not fixed here.

## Not changed (recorded decisions)

The hats and garments gaps are `not_pursuing`, which `review` decided after MAX_FAILED_ATTEMPTS measured attempts. They are left as decided and are not overridden here. Their READY concepts stay waiting, and the readback says why.

## Tests

`tests/test_supply_research.py` is new. It:

- reproduces production (pre-feed readings, scans recorded, 0 admitted, research absent);
- runs the deploy pass, after which the research is answered from recorded scans and covered pods are admitted, with the halt still open;
- includes a mutation (no scan history), under which covered pods are not admitted;
- checks honesty: failed reads, withdrawn rows and single-day scans corroborate nothing;
- checks the boot order, and checks that a current reading is never overridden by history.

Suites run with a private TMPDIR, all passing: test_supply_research, test_supply_feed, test_watchlist_cadence, test_ws2_research_m2, test_r5_research_2, test_r5_research_3, test_r5_research_4 (52 tests, after the final change). Earlier run on this branch, also passing: test_w4_intelrec_watchlist, test_concepts100, test_supply_lane, test_new_product_flow, test_factory_visibility, test_vacuity, test_w4_readback_evidence, test_w4_integ3_boot_tables, test_w4_fm2_lock_boot_guard, test_compiler.
