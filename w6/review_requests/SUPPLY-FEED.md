# SUPPLY-FEED: scan evidence feeds engineering

- **Branch:** `eng/supply-feed`, cut from `claude/w6-release-19h8` (94daf05 = deployed 94daf054).
- **Status:**
  - NOT merged and NOT deployed. Production is unchanged.
  - No production row was read. Railway deploy logs carry no pool or compare rows.
  - No PR was opened. Nothing was pushed to `claude/repository-setup-nc9x6o`.
- **Decision:** D-ENG-SUPPLY-FEED (DECISION_LOG). BUILD_STATE has its entry at the top.
- **New suite:** `brambleloop/tests/test_supply_feed.py` (7 tests).

## The readback (prod 94daf054, 13:50Z)

- **Pool:** 142 total. 32 ready, 95 held, 15 refused, 0 admitted.
- **Engineering:** 1 product in flight, WIP 4, 4 open slots, 0 offers waiting.
- **Certified in 24 h:** 0.

`admit_ready` needs two things for a READY concept:
- (a) an answered research task behind a validated watchlist gap in its pod;
- (b) allowance units.

## The cause: condition (a). A gap the scans corroborate but never link.

Every earlier suite built its research by hand. `test_concepts100._answered_task` writes a
fixture task and a hand-made `CoverageGap`. `test_supply_lane` and the others reuse it. None of
them exercised the real link from the nine-shop scans to research.

The real link is `intel.watchlist.record_comparison`:
- a validated arena becomes a `watchlist` coverage gap;
- the gap's question is opened;
- `watchlist_research.answer` answers it from the recorded comparisons.

The defect is in `compare`. It drops every pod in `_our_pods`, the pods of our existing products
(`_judge_arenas(arenas, ours)`). For those pods:
- there is no gap;
- there is no research question;
- `research_for_pod` returns None forever.

Production has 16 products in those pods. The pool ranks first exactly the READY concepts in
them: cushions (core "pillow" facet, weight 1.5), wall panels, baskets and totes.

Reproduced with the real compare over 4 days of nine-shop scans and products in home_decor,
blankets and bags:
- before: home_decor had 12 READY concepts and `research_for_pod` was None;
- with the fix: it is answered (task, F1/F2/S1/S2, quality 0.65, confidence medium).

There were two smaller stalls on the same path, also fixed:
- **A gap that moves on closes the arena.** `research_for_pod` accepted only `uncovered` and
  `concepting` gaps. Once one concept promoted and the gap moved to `engineering`, the pod's
  other READY concepts were blocked. Now every state but `not_pursuing` counts. That state is a
  recorded decision, and it is still refused (tested).
- **A one-day answer could expire before intake judged it.** A `market_radar` answer lasts 24 h.
  The pool runs every 6 h, and intake runs on its own 6-hourly cadence. Now:
  - an answer expiring within 2 h (`FRESH_MARGIN`) is not handed over;
  - `radar.concept_pool` enqueues `radar.concept_intake` as soon as it admits.

**Allowance (b): not the cause on a clean ledger.** The bounds are 5 per run, the monthly
ceiling and the pool's 10 % share (CA$10 ÷ CA$0.13 ≈ 76 a month). The CA$100 cap is unchanged
and asserted. Production's ledger was not read, so the new readback field reports production's
binding bound.

## The fix

1. **`watchlist.compare`:**
   - `validated_arenas` and `unknown_arenas` are byte-for-byte as before (uncovered pods only).
   - New `demand_arenas` and `demand_unknown_arenas` cover the pods we sell in. They are judged
     by the same `_judge_arenas` rules: fresh reads, ≥ 3 live listings, ≥ 2 shops, and a
     stale/withdrawn majority reads UNKNOWN. Each is marked `covered`.
2. **`record_comparison`:**
   - Each demand arena gets a `watchlist` gap with `covered_by_us`, moved `uncovered → concepting`.
     Laura's summary, `review` and the proposal writer act only on `uncovered` gaps, so a covered
     arena never reads as an open opportunity.
   - The research question is answered by the unchanged `watchlist_research.answer`.
   - Its findings say "an arena we already sell in", never "uncovered".
   - Renewal and withdrawal (`renew_approved_support`, `withdraw_unsupported`) cover these gaps
     unchanged.
3. **`concept_pool.research_status`:** one status per pod, from a fixed vocabulary:
   - `present`: `usable`;
   - `absent`: `no_watchlist_gap`, `gap_not_pursuing` or `no_research_task`;
   - `unanswered`: `task_not_answered`, `evidence_expiring` or `evidence_refused`.

   `research_for_pod` wraps it.
4. **`admit_ready`:** every pass writes a `concept_pool.admit_result` audit row (counts and
   vocabulary only, no slug). Retention class: `latest`.
5. **`factory_visibility.supply`:**
   - `allowance` {units, unit_cad, why}. `why` is the binding bound: `per_run`,
     `monthly_ceiling`, `pool_share`, `unit_cost_unknown` or `ledger_unreadable`.
   - `ready_by_pod` {pod: {ready, research, why}}, plus `ready_by_research`.
   - `last_admit` {ready, admitted, waiting_on_research, capped_by_allowance, at}.
   - Before the first pass, these fields read UNKNOWN (`None`), never 0.

## Proof (fixture, not a production measurement)

`test_scan_evidence_feeds_engineering_unaided_with_the_halt_open`. The setup:
- the systemic publishing halt is open;
- 16 existing products have their listing work held;
- 3 days of earlier daily comparisons have run;
- only cadence jobs are enqueued (`intel.watchlist_compare`, `radar.concept_pool`,
  `radar.concept_intake`, `mjs.seasonal_sentinel`, `supply.admit`);
- the real worker runs 4 cycles.

Each concept is traced through: scan evidence (`benchmark_listing:` refs) → READY → admitted
onto a `watchlist_gap:` `market_radar` task with fact findings and ≥ 2 corroborating shops →
intake approved → `radar.score` → `supply.offered` → `supply.admitted` → `cir.draft`.

**9 concepts reached `cir.draft` unaided:** 6 cushions (home_decor, an arena we already sell in,
which fed nothing before) and 3 beanies (hats). The suite asserts ≥ 4, a cushion, a clothing lane
and a covered pod. The halt is still open, and nothing was published.

Where the other 11 admitted concepts stopped (all approved by intake):

| Family | Admitted | cir.draft | Stops at |
|---|---|---|---|
| pillows (cushion) | 6 | 6 | none |
| clothing: hats (beanie) | 4 | 3 | 1 refused by the gate (jury, motif grammar): correct |
| clothing: shawl | 4 | 0 | `image_vision`: judge cadence, not a defect (see below) |
| bags (basket, tapestry basket) | 4 | 0 | `image_vision`: judge cadence |
| **amigurumi** | 2 | **0** | `image_vision`: **no toy board exists** (SUPPLY-LANE row 4, still open) |
| **baby** | 0 | **0** | **no READY baby concept**: baby blanket is held by #108 (a rectangle is a shape, not an outline), and baby cardigan by `construction_unsupported:garment_raglan` |

So the goal "including core families (amigurumi, baby, pillows, clothing)" is **met for pillows
and clothing only.** Amigurumi needs a toy renderer for its radar board. Baby needs either an
honest silhouette qualifier on a baby blanket or a certified raglan engine. I did not fake any
of the three.

## Tests (`test_supply_feed.py`, 7/7)

- **The state is production's.** Every research task was opened by the comparison, and none was
  hand-made. Covered gaps are `concepting`, not open opportunities. Yesterday's answer reads
  `unanswered/evidence_expiring`.
- **End to end:** the proof above.
- **Mutation.** `link_demand → []` restores the defect:
  - no covered-pod concept is admitted or drafted;
  - the readback says `absent/no_watchlist_gap`.
- **Honesty.** With stale reads, no arena is corroborated, so no task is answered and nothing is
  admitted.
- **A stopped arena.** A `not_pursuing` gap gives `absent/gap_not_pursuing`.
- **The allowance still bounds admission.** 5 per run; the CA$100 cap is unchanged. An unknown
  unit cost admits 0 (`unit_cost_unknown`).
- **Visibility vocabulary.** Fixed keys and values; no slug, title or competitor word.

## Suite run (this branch)

| Suite | Result |
|---|---|
| `test_supply_feed` (new) | 7/7 |
| `test_supply_lane` | 9/9 (key-set assertion extended for the 4 new fields) |
| `test_concepts100` | 18/18 |
| `test_new_product_flow` | 6/6 |
| `test_eng_supply` | 17/17 |
| `test_research_flow` | 22/22 |
| `test_factory_visibility` | 2/2 |
| `test_vacuity` | 8/8 |
| `test_r5_research_2` | 10/10 |
| `test_r5_research_3` | 7/7 |
| `test_r5_research_4` | 6/6 |
| `test_ws2_research_m2` | 7/7 |
| `test_w4_intelrec_watchlist` | 20/20 |
| `test_ninth_shop` | 6/6 |
| `test_w4_retfix_retention_keys` | 3/3 |
| `test_w4_fmbatch1_retention_guard` | **FAILS identically on base 94daf05** (see below) |

The retention guard fails on base too. `unknown_read_actions()` reports
`unresolved:runtime/release.py::_attempt_gate_refusal` and
`unresolved:runtime/release_recovery.py::_halted_releases`. This branch does not touch those
files.

## Open / not verified

- **UNVERIFIED in production** until deployed. That production's 32 READY concepts sit mostly in
  covered pods is inferred: the ranking puts cushions first, and production has 16 products in
  those pods. Read `factory_visibility.supply.ready_by_pod` after deploy to confirm. It names the
  blocking reason per pod, including whether the allowance binds.
- **If production's scans corroborate nothing,** for example because every shop read is older
  than 48 h, the readback will say `absent/no_watchlist_gap` for every pod. The fix is then the
  scans, not the pool. Nothing here fabricates research.
- **Amigurumi:** a toy board is needed (next engineering item).
- **Baby:** no honest READY concept exists yet (see the table).
- **Judge cadence:** about 20 vision verdicts a day bound research supply.
