# ENG-CONCEPTS-100 slice 1: review request (concept generation at scale from evidence)

- **Branch.** `eng/concepts-100`, created from `origin/claude/w6-INTEG3` @ `307c7e62`. The final SHA is the commit that adds this file; it is given in the issue #28 comment tagged `[ENG-CONCEPTS-100]`.
- **Not deployed, not merged.** Nothing touches Railway, production, secrets, Etsy writes, spend, `BRAMBLELOOP_PHASE` or `STAGE_A_ENABLED`. Nothing was pushed to `claude/repository-setup-nc9x6o`.
- **Decision.** `D-ENG-CONCEPTS-100` (DECISION_LOG). It follows D-OWNER-CORE-FAMILIES, #88, #108, B-117, D-ENG-FAMILIES-1/2 and D-OWNER-BENCHBUY.

## What was built

1. **Generator:** `src/brambleloop/radar/concept_pool.py`.
   - **Signals.**
     - **Listings.** `observed_listings` reads fresh watchlist `BenchmarkListing` rows from the last 30 days, all nine shops. Each row gives its shop, pod, demand facets, price, favourites, season and last-seen date. Titles are read only to classify demand facets; they are not returned.
     - **Lane signal.** `lane_signal` validates a lane on at least 2 supporting listings. It records the shops, a price band, seasons, facet counts, upcoming events (when the listings are seasonal), review complaint themes (from `BenchmarkObservation`) and up to 8 listing refs sorted by favourites.
   - **Grammar.** `LANES` holds 28 lanes. Each lane has a category, a declared form and construction (closed vocabulary), a pod or facet, the object, how it is built and its own motifs, uses and contexts.
     - **Admitted families:** cushion (panel_pair), storage basket (vessel), tapestry basket (tapestry: the only two charts exist, so a third "geometric diamond" variant is a designed clone), wall panel (flat).
     - **Generic flat forms**, held by #108: throw, baby blanket, runner, placemat, coaster, dishcloth, scarf, pet mat.
     - **Held families:** three amigurumi lanes, animal cushion, cable cushion, baby cardigan, yoke sweater, cardigan, beanie, mosaic, c2c, granny, tote, shawl, stocking, ornament.
   - **Per concept** (`build`):
     - premise and #88 storyboard (object, view, motif, palette);
     - #108 qualifiers from `creative.intake.qualifiers_for`, never typed;
     - an `honesty_reasons` check: premise words may not declare a qualifier the construction does not earn (`qualifier_constructions`);
     - the #108 check `preengineering._silhouette`, exactly as the gate runs it;
     - the family from `construction_families.route`;
     - a size range with its source (CYC blanket classes, `BASKET_SIZES`, pillow forms, the family's own sizes, or UNKNOWN with the reason);
     - its evidence.
   - **Originality** (`originality`):
     - **Copies.** An exact competitor title, or one restating its specific words (Jaccard 0.8 or more), is refused as a copy. So is a twin of an observed listing on everything either side states (`prospecting._matches_a_listing` over `watchlist_comparables`).
     - **POOL titles.** A title restating a POOL title in the same category is refused (intake's own 0.5 rule).
     - **Clones.** A concept below `MIN_NOVELTY` from the briefed catalogue, approved intake rows or anything already kept in the pool is a clone. Higher-priority lanes claim novelty first. A variant tries each context of its lane in turn and keeps the first that is original; with none it is refused.
   - **States.**
     - `READY`: an admitted family and #108 passes.
     - `HELD`: any other reason, recorded.
     - `REFUSED`: clone or copy.
     - `ADMITTED`: attached to intake.
     - `STALE`: no fresh signal; the reason is appended.
     - Rows are never deleted.
   - **Owner weighting.** `priority_of` weights MadelineMaeCo x1.5, the baby, stuffed-animal and pillow facets x1.5, and garment, basket and colourwork x1.25. `health.research_requests` lists arenas that need an answered research task, MadelineMaeCo-backed first.
   - **Admission** (`admit_ready`).
     - A READY concept goes to the answered research task behind a validated watchlist `CoverageGap` in its pod, in state uncovered or concepting, whose refs clear `intake.research_evidence`.
     - The proposal is ours: title, concept, storyboard and qualifiers, the task's fact refs, and a rationale with counts only (no shop names).
     - `radar.intake` approves or refuses it on its own checks.
   - **Spend** (`admission_allowance`). Generation spends CA$0. Admissions are limited by the smallest of three bounds:
     - 5 per run;
     - (CA$100 ceiling - month spend - outstanding reservations) / unit;
     - (10% of the ceiling - this month's admissions x unit) / unit.

     The unit is 2 x `vision.per_image_estimate_cad`, the vision verdict the gate waits for plus one re-judge. An unknown unit or an unreadable ledger admits 0.
   - **Readback.** `health` reports:
     - counts: evidence_backed against the target of 100, ready, admitted, held, refused_clone_or_copy, stale, intake_approved, engineered (`draft:<slug>` jobs), section_33_pool;
     - by_family, by_shop and shops_without_signal;
     - held_reasons and research_requests.

     A pool that was never generated reads UNKNOWN, read-only.
2. **Wiring.**
   - New cadence `radar.concept_pool`: market_radar, 6 hours.
   - Handler in `runtime/intel_ops.py`. Its `work_done` counts new, changed, stale and admitted concepts.
   - Registered in:
     - `FREE_JOB_TYPES`;
     - `UPSTREAM_INPUTS`: `intel.watchlist_scan` and `research.investigate`; `radar.concept_intake` also lists `radar.concept_pool`;
     - the agent allow-list;
     - authority `_R`;
     - department GROW;
     - the band `new_opportunity`;
     - the idle-output key.
   - `autonomy_map.json` was regenerated through `python -m brambleloop.autonomy.map --write`: 146 cadences, 178 handlers.
3. **Registries.**
   - `intel/research_flow.sources()` registers `concept_pool`. It also registers `benchmark_shopping`. On the INTEG3 base, `test_research_flow::test_every_research_cadence_is_in_the_registry...` was already red for `intel.benchmark_shopping`, and that one line turns it green.
   - `scripts/suite_final_segment.txt` lists `tests/test_concepts100.py`, because it reads the clock (F7).
   - The pool readback never creates a table: `test_the_board_section_writes_nothing`.
4. **Mission Control.**
   - P0 board section `concept_pool`, with the JS renderer.
   - `sw.js` bumped to `cc-shell-v37`.
   - Mock data and a `check.mjs` assertion; the board now has thirteen sections.

## Honest status

- The fixture result is not a production measurement. On synthetic scans of three shops (in `tests/test_concepts100.py`):
  - 115 evidence-backed concepts;
  - 19 ready (6 cushions, 5 storage baskets, 2 tapestry baskets, 6 wall panels), every one passing `radar.intake.validate`;
  - 96 held;
  - 7 refused as clones.
- The real pool size, and which shops carry a signal, are UNKNOWN until the cadence runs on production scan data. This checkout has no production database.
- Most of the pool is HELD, and that is the honest outcome. Generic flat forms in plain stripes earn no #108 qualifier, and the families for amigurumi, garments, hats, mosaic, c2c, granny, cable, tote, triangle, stocking and ornament are not certified. Core-family concepts (amigurumi, baby cardigans, animal cushions) are in the pool, HELD with `construction_unsupported:<family>`.
- Admission needs an answered research task behind a validated gap in the concept's pod. Without one, the concept waits as READY and is listed under research requests. The pool does not open research tasks (a slice-2 candidate).
- Pool cushions are `panel_pair`, which is physical-gated: certification withholds them for the class-C sample. Every admitted concept still waits on `image_vision` at the pre-engineering gate (CLOSED), so engineered is 0 until a vision verdict exists.

## Tests

`tests/test_concepts100.py` has 14 tests, all passing:
- 100+ evidence-backed concepts from synthetic scans, each with a premise, storyboard, family and size source, and evidence refs that resolve;
- no fixture competitor word reaches a concept;
- #108 is derived and never constant; generic forms are held;
- an unearned qualifier is refused;
- clones are refused and every kept pair is at or above `MIN_NOVELTY`;
- exact and restated copied titles are refused;
- held families are visible and never dropped (STALE kept);
- idempotent;
- owner weighting;
- spend bounded (ceiling, reservations, unknown cost);
- the pool share caps monthly admissions;
- admitted concepts are approved by intake on its own checks;
- Mission Control counts;
- generation is free.

**Mutants.** 14 of 14 were killed. Each was applied to a copy of `src/` and `tests/`, and `tests/test_concepts100.py` had to fail:

| # | Mutant | Killed by |
|---|---|---|
| M1 | `copy_reasons` returns [] | copied titles |
| M2 | restated-title branch off | copied titles |
| M3 | clone floor off | clones |
| M4 | dedupe ignores pool siblings | clones |
| M5 | honesty check off | unearned qualifier |
| M6 | constant `motif_composition` qualifier | #108 derived; held families |
| M7 | #108 refusal dropped | #108 derived; held families |
| M8 | reservations ignored | spend bounded |
| M9 | pool share ignored | pool share |
| M10 | held recorded as refused | #108; held; 100+ |
| M11 | stale rows deleted | held never dropped |
| M12 | MadelineMaeCo weight off | owner weighting |
| M13 | core facet weight off | owner weighting |
| M14 | per-run cap off | pool share / admission |

**Suites run on this branch.** The results are listed in the #28 comment:
- test_concepts100, test_research_flow, test_w5_concept_intake, test_w5_a4a_research_to_concept, test_prospecting, test_eng_families, test_eng_supply, test_w5_a7_supply_stall, test_watchlist_cadence, test_w4_resume_runner, test_v11_autonomy_timeline, test_vacuity;
- test_s4_p0_board, test_eng_recovery (the static spend-reach proof for `FREE_JOB_TYPES`), test_benchbuy, test_w4_ccux;
- test_v11_pwa_browser (check.mjs: 261 passes, 0 failures, including "all thirteen sections render" and the concept pool check).

## Questions for review

1. Is the 10% pool share and the 2-call unit right for the downstream judging an admission asks for, or should admission read the vision task's own `ALLOCATION` share?
2. Should the pool open research tasks for READY arenas that have none (slice 2), or leave that to the watchlist comparison?
