VERDICT: SHIP 777a66f36e79a8e55716be88ff5db0dd3c54e003

Delta review of origin/eng/families @ 777a66f3 over a24173e3. Base origin/claude/w6-INTEG2 @ cde89a4b. Merged tree built (conflicts only in DECISION_LOG.md and scripts/suite_final_segment.txt; both sides kept).

## Findings

### HIGH / MEDIUM
None.

### LOW
- **L1 test gap, `tests/test_eng_families.py:443,494` vs `creative/construction_families.py:136`.** The bare word "lid" is not pinned. Mutation: change the lid regex to drop `\blids?\b` and the first `\blidded\b` -> the suite stays green (0 failures), and `route(basket, "Basket With Lid")` is then admitted (probe confirmed; "Lidded Basket" is still held). Only "Lidded" is exercised. The code is correct today; a regression of that word would not be caught. Add "Basket With Lid" to the held-title list.
- **L2 deny-list is inherently incomplete.** Names that read as a construction or feature but are not in `NAMED_FEATURES` are admitted as plain baskets: "Braided Basket", "Moss Stitch Basket", "Houndstooth Basket", "Crab Stitch Edge Basket", "Heart/Star Basket", "Spiral Basket", "Chevron Stripe Basket". Everything the review named is held. Not blocking; worth a follow-up to extend the vocabulary (braid, moss/seed/crab stitch, shaped baskets).
- **L3 `creative/construction_families.py:136`** the lid regex repeats `\blidded\b` (harmless duplicate).
- Unrelated change rode along: `gates/policy.py` IP-term matching is now whole-word (fixes "Fernbank" vs 'nba'); covered by new `test_gates` cases, `test_eng_families` and the passing guards. Fine.

## Previous findings: truly fixed? (each mutated)
- H1 named unbuilt construction held, plain basket admitted: FIXED. Probes on the merged tree: "Granny Square", "Cable Stitch", "Bobble", "Lidded", "Basket With Lid", "Bear Ears Amigurumi", "Waffle Stitch", "Pom Pom", "Chunky Handled" baskets are all held; "Saltmarsh Reed", "Plain Striped Storage", "Cotton Rope Basket Bowl", "Ripple Stripe" baskets are admitted. A feature named only in the premise is held too. Mutations: title read removed -> 3 tests fail; premise read removed -> `test_every_named_feature_is_held_for_every_admitted_family` fails.
- M1 pet beds: FIXED by holding. `(vessel, pet)` is in `HELD_CATEGORIES` (reason names TWIN_DIMENSION_IMPLAUSIBLE, 10 cm vs 11.4 cm); a flat pet mat stays admitted through the flat-panel family. Mutation removing the hold -> `test_a_pet_bed_is_held_until_it_certifies` and the pair-proof sweep fail.
- Every admitted (family, category) pair has a certifying proof: CONFIRMED. `PAIR_PROOFS` covers flat-panel x 8 categories, vessel x basket, tapestry x basket, panel-pair x pillow; mutating out `(vessel, basket)` -> `test_every_admitted_family_category_pair_names_an_existing_certifying_proof` fails.
- Batch 12 supply admission (products/supply.py): COMPATIBLE. `supply.family_of` reads the offer's recorded family or the pool seed and never calls the router; `test_eng_supply` passes on the merged tree.

## Suites (merged tree, `PY=venv python`, JOBS=2)
`TOTAL PASSING: 341 ; suites failing: 0` (0 environment failures)
- test_eng_families, test_w5_concept_intake, test_w5_a4a_research_to_concept, test_opus2_draft_constructions, test_s1_product_truth_3, test_prospecting, test_deliverable_qa (plus test_eng_supply), and guards test_vacuity, test_w3_tmp_hygiene, test_w4_resume_runner, test_w4_c12_wiring, test_v11_autonomy_timeline, test_w4_adopt_manual_listing: all pass.
- autonomy_map.json: no regeneration needed.

## sw.js VERSION
Unit does not touch sw.js (stays v33, the base value); no collision.
