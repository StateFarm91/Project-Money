# FIX-DEMAND-STALL — review request

- **Branch:** `claude/w6-INTEG8-wip` (Batch 18 = production Batch 17 b098fcce + demand-supply 2a85f4f3 + etsy-publish 04e1200d)
- **Base:** 0b7aeca. **Fix SHA:** `f47a5961`. Merged on top with a fast-forward; no force-push.
- **Status:** not deployed; production unchanged.

## The failing test, and the cause
`test_w5_a7_supply_stall::test_the_production_drafted_set_drafts_what_can_be_drafted_then_names_the_stall`
failed at the later-scan assertions. `cottage-wall-hanging` (wall_decor, flat_panel family, refused as
`construction_unsupported:flat_panel`) is promoted by `radar.score`, offered to `supply`, and then refused at
admission as engine demand. On every later scan `promotion_verdict` still promotes it, so the reading counted it as
`promotable_undrafted: 1, supply_selected: 1, stalled: False` while nothing could draft it. That was a hidden stall.

## The fix (supply code; no test assertion weakened)
- `products/supply.py`: `engine_demand_waiting(db)` returns `{slug: reason}` for every waiting offer whose
  `demand.engine_verdict` is known and not certified. The verdict is re-read live.
- `runtime/pipeline.py` `radar.scan`: a promotable concept in that map is removed from the promotable set and held
  with its `engine_demand:<family>: ...` reason. `_record_supply_stall` takes `engine_demand=` and:
  - counts it as `engine_demand_undrafted`, never as `promotable_undrafted` or `supply_selected`;
  - reports `stalled: True`, with reason `selection_unpromotable`, or the new explicit reason `engine_demand` when
    every undrafted concept left is waiting on an engine. On the production pool other held concepts remain, so the
    test's expected reason stays `selection_unpromotable` and is unchanged;
  - lists the concepts in `engine_demand` on the output and the stored reading.
- `ops/flow_health.concept_supply_stall` carries `engine_demand_undrafted`.
- The concept stays queued in `supply` (never dropped) and drafts automatically once its engine exists.

## Tests added or strengthened
- Later scans also assert `engine_demand_undrafted == len(demanded)`, and that each demanded concept is held with an
  `engine_demand:` reason. `promotable_undrafted == 0` and `undrafted_pool > 0` are kept.
- New `test_an_engine_demand_concept_drafts_once_its_engine_exists`: the concept is engine demand and stalled. An
  engine is registered (an engineered design under its slug, the path `engine_verdict` and `cir.draft` both read).
  The next scan counts it as promotable with `engine_demand_undrafted == 0`, and `radar.score` re-offers it so it is
  admitted and gets its `draft:<slug>` job. The supply queue is then empty.
- Without the pipeline change, the original test fails as described.

## Review b18-a follow-ups
- **B-1, option (b):**
  - `CORE_FAMILIES` and `CORE_BOOST` are now exactly the owner's three: amigurumi 0.30 > baby 0.26 > pillow 0.22.
  - Garments move to `SECONDARY_BOOST = {garment: 0.18}`, which is below every core boost and labelled `core: False`
    everywhere.
  - `BOOSTED_FAMILIES` keeps the strong-category override and the originals catalogue.
  - The reason is recorded as an amendment to D-ENG-DEMAND-SUPPLY.
  - Test: `test_only_the_owners_three_families_are_core_and_garments_are_secondary`.
- **B-2:**
  - `supply.offers` now orders a missing market score as `demand.PRIOR`.
  - Test: `test_a_missing_market_score_orders_as_the_prior_not_zero`.
  - Mutation check: putting back `0.0` makes that test fail, so the test kills the mutant.

## Suites (run on f47a5961, Python 3, locks installed)
| suite | OK | FAIL |
|---|---|---|
| test_w5_a7_supply_stall | 8 | 0 |
| test_eng_demand_supply | 23 | 0 |
| test_eng_supply | 17 | 0 |
| test_research_flow | 22 | 0 |
| test_eng_families | 16 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |
| test_w4_readback_evidence | 23 | 0 |
| **total** | **157** | **0** |

Not run: the rest of the repository's suites.
