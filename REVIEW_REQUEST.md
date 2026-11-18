# REVIEW_REQUEST: eng/s1-product-truth-2 (based on e490fc6f, opus2/s1-product-truth-fix)

Product Truth: a product's title, its size claims and its compiled digital twin must agree, or the product is refused.
This branch fixes the independent review of e490fc6f (S1F-H1, S1F-M1 and the LOW findings).

## The rule now enforced

`creative/size_truth.claims(category, title)` finds every size-bearing token in a title: class words, relative size words, and stated dimensions.
It either binds each token to what the twin must be, or records why it cannot ("unbound").
Three places read the same function:

- **intake**: `radar.intake.validate` calls `request` and refuses.
- **draft**: `fallback_constructions.plan` and `concept_geometry` call `request`. A bound size is drafted; an unbound one is refused.
- **certify**: `gates.certificate.object_size_findings` and the listing title call `coded_findings`. They report:
  - `OBJECT_SIZE_UNBOUND` for any token that cannot be bound.
  - `OBJECT_SIZE_NOT_AS_TITLED` when the twin misses a bound claim.
  - `OBJECT_SIZE_OUT_OF_BAND` for the title-only bands.

A token the parser cannot bind is never passed.

## Finding → fix → test (`tests/test_s1_product_truth_2.py`, 11 tests)

| Finding | Fix | Test |
|---|---|---|
| H1 (2) two class words: the draft used the first class in the table, and the check passed if any class fitted | All named classes must hold the twin (`coded_findings`: `missed` = every class the twin is outside). The draft target lies inside the intersection of the class bands; an empty intersection is refused, naming both classes ("King Size Ridge Throw"). | `test_h1_two_class_words_are_both_bound_or_refused` |
| H1 (3) bare queen/king/twin/full not recognised | Bare words added to the classes. `NON_SIZE_PHRASES` removes single/double crochet, Queen Anne's, possessives (King's Cross), full moon/bloom/of/colour, twin peaks/set, long stitch and short rows first. | `test_h1_bare_bed_size_words_are_size_classes` |
| H1 (1) unitless sizes not parsed | Recorded rule **D-S1-UNITLESS-DIMS** (DECISION_LOG): read the size as cm and as inches, and bind it only when exactly one reading lies in the cited object band and every named class. Both or neither → refused. | `test_h1_unitless_dimensions_are_read_by_the_recorded_rule_or_refused` |
| H1 "anything the parser cannot bind → REFUSE" | Two different sizes, three dimensions or a dangling figure → refused at draft and `OBJECT_SIZE_UNBOUND` at certify. The same size in two units counts as one size. | `test_h1_a_size_the_parser_cannot_bind_is_refused`, `test_h1_the_listing_title_is_bound_the_same_way` |
| M1 inconsistent relative words | **D-S1-RELATIVE-SIZE**: a relative word is bound by stated dimensions or by a defined family, otherwise refused. The only family is the large blanket (HOUSE FAMILY between the CYC throw and twin, drafted at 60 x 80 in); it keeps `nordic-forest-mosaic-throw-large` (120 x 171) certifying. All other cases (extra long/long/skinny/petite scarf, large dog mat, mini placemat, large pillow) are refused at draft and are `OBJECT_SIZE_UNBOUND` at certify. | `test_m1_relative_size_words_follow_one_rule` |
| LOW catalogue test certified only the 11 Launch-0 products | The test certifies every catalogue CIR I could enumerate. That is **41**: Launch-0 + proposed builders, `builder.CATALOGUE`, every Nordic Forest size, 6 moment candidates, vessels, and 17 graded garments. Three are refused for recorded non-size reasons and must be refused by exactly those codes: ring pillow (D-S1-SIZE-FAMILIES), cable wrap (UNCALIBRATED_PRIMITIVE), kneeler (PHYSICAL_TEST_REQUIRED). I could not reproduce the review's count of 29; this set contains it. This test passes on the old code too, because it guards against regressions and is not a reproduction of the defect. | `test_low_every_catalogue_cir_certifies` |
| LOW pet-mat, burp-cloth and tapestry bands never fire at certify | `object_of` reads pet/dog/cat… mat and "tapestry" (not "tapestry crochet") from the title. Bands that no product-type family word reaches are checked in `coded_findings`. | `test_low_pet_mat_burp_cloth_and_tapestry_bands_fire_at_certification` |
| LOW "Linen Throw 2 in 1" refused as a 5.1 cm request | "in" is a unit only when no figure follows it. | `test_low_two_in_one_is_not_a_size` |
| LOW "Skinny Scarf 10 cm" refused with the wrong reason | A single figure binds to the side a length word or width word names; otherwise to the one side whose band holds it; otherwise refused. Now refused as "10 cm wide". "Short Runner 40 cm" is still refused as "40 cm long". | `test_low_skinny_scarf_10_cm_is_refused_as_a_width` |
| Must keep | Queen Size 230x254, 200x220 cm, 26x26 inch, 100x150 cm tapestry, burp cloth, lumbar, and all refusals | `test_kept_cases_stay_fixed` + `test_s1_fix_size_families` (unchanged, 14/14) |

Before the fix, 9 of the 11 new tests fail on e490fc6f. The two that pass there are the catalogue and kept-cases guards, which are non-regression tests.
Mutation check: 15 mutants of `size_truth.py`, all killed by this file. They covered the bare queen and king words, the class intersection, any-class versus all-class matching, the unitless rule, the "2 in 1" lookahead, the relative rule, width words, title-only bands, non-size phrases, unbound-at-certify, several sizes, three dimensions, a dangling figure, and the large family.

## Before / after, measured through the real path (plan → geometry → builder → compile → twin → certify)

"size CERTIFIES" means the certificate has no size finding. PROVENANCE_MISSING and PHYSICAL_TEST_REQUIRED come from the fixture's bare drafted CIR and are not size findings.

| Title | Category | Before (e490fc6f) | After |
|---|---|---|---|
| King Size Ridge Throw | blanket | 128.0 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) | REFUSED at draft (the title names throw and king, and no size is all of them (throw: 75-145 x 90-170 cm; kin) |
| Linen Lumbar Pillow 12 x 24 | pillow | 28.8 x 49.6; size CERTIFIES (other: PHYSICAL_TEST_REQUIRED,PROVENANCE_MISSING) | 32.0 x 60.5; size CERTIFIES (other: PHYSICAL_TEST_REQUIRED,PROVENANCE_MISSING) |
| Linen Blanket 200 x 220 | blanket | 128.0 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) | 198.4 x 219.9; size CERTIFIES (other: PROVENANCE_MISSING) |
| Linen Pillow Cover 26x26 | pillow | 41.6 x 41.7; size CERTIFIES (other: PHYSICAL_TEST_REQUIRED,PROVENANCE_MISSING) | 67.2 x 65.9; size CERTIFIES (other: PHYSICAL_TEST_REQUIRED,PROVENANCE_MISSING) |
| Queen Linen Blanket | blanket | 128.0 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) | 230.4 x 253.6; size CERTIFIES (other: PROVENANCE_MISSING) |
| Linen Blanket 50 x 60 | blanket | 128.0 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) | REFUSED at draft (the title states '50 x 60' with no unit, and the unit cannot be determined: both cm and in) |
| Linen Pillow 12 x 24 in and 18 x 18 in | pillow | 32.0 x 60.5; size CERTIFIES (other: PHYSICAL_TEST_REQUIRED,PROVENANCE_MISSING) | REFUSED at draft (the title states 2 different sizes (30.5 x 61, 45.7 x 45.7 cm); one pattern makes one size) |
| Large Linen Throw | blanket | 128.0 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) | 128.0 x 164.9; size CERTIFIES (other: PROVENANCE_MISSING) |
| Oversized Chunky Throw | blanket | 128.0 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) | 128.0 x 164.9; size CERTIFIES (other: PROVENANCE_MISSING) |
| Extra Long Linen Scarf | scarf | 19.2 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) | REFUSED at draft (the title names a relative size ('extra long') with no dimensions, and a scarf has no defi) |
| Long Linen Scarf | scarf | 19.2 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) | REFUSED at draft (the title names a relative size ('long') with no dimensions, and a scarf has no defined si) |
| Skinny Linen Scarf | scarf | 19.2 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) | REFUSED at draft (the title names a relative size ('skinny') with no dimensions, and a scarf has no defined ) |
| Large Dog Mat | pet | REFUSED at draft (the title names a size ('large') with no dimensions; the template makes one size and canno) | REFUSED at draft (the title names a relative size ('large') with no dimensions, and a pet mat has no defined) |
| Mini Placemat | placemat | REFUSED at draft (the title names a size ('mini') with no dimensions; the template makes one size and cannot) | REFUSED at draft (the title names a relative size ('mini') with no dimensions, and a placemat has no defined) |
| Linen Throw 2 in 1 | blanket | REFUSED at draft (the title asks for 5.1 x 5.1 cm and names throw, whose band does not hold it) | 128.0 x 152.2; size CERTIFIES (other: PROVENANCE_MISSING) |
| Skinny Scarf 10 cm | scarf | REFUSED at draft (the title asks for a scarf 10 cm long; the scarf band is 110-230 cm long (a scarf is about) | REFUSED at draft (the title asks for a scarf 10 cm wide; the scarf band is 12-35 cm wide (a scarf is about 1) |
| Queen Size Linen Blanket | blanket | 230.4 x 253.6; size CERTIFIES (other: PROVENANCE_MISSING) | 230.4 x 253.6; size CERTIFIES (other: PROVENANCE_MISSING) |
| Linen Blanket 200 x 220 cm | blanket | 198.4 x 219.9; size CERTIFIES (other: PROVENANCE_MISSING) | 198.4 x 219.9; size CERTIFIES (other: PROVENANCE_MISSING) |
| Pillow Cover 26 x 26 inch | pillow | 67.2 x 65.9; size CERTIFIES (other: PHYSICAL_TEST_REQUIRED,PROVENANCE_MISSING) | 67.2 x 65.9; size CERTIFIES (other: PHYSICAL_TEST_REQUIRED,PROVENANCE_MISSING) |
| Large Tapestry 100 x 150 cm | wall_decor | 99.2 x 150.4; size CERTIFIES (other: PROVENANCE_MISSING) | 99.2 x 150.4; size CERTIFIES (other: PROVENANCE_MISSING) |
| Short Runner 40 cm | runner | REFUSED at draft (the title asks for a runner 40 cm long; the runner band is 90-275 cm long (a table runner ) | REFUSED at draft (the title asks for a runner 40 cm long; the runner band is 90-275 cm long (a table runner ) |
| Baby Lovey | baby | REFUSED at draft (a lovey is a small security blanket with a stuffed head or toy joined to it; the fallback ) | REFUSED at draft (a lovey is a small security blanket with a stuffed head or toy joined to it; the fallback ) |
| Baby Bib | baby | REFUSED at draft (a bib needs a shaped neck opening and a tie or fastening; a flat rectangle is not a bib: t) | REFUSED at draft (a bib needs a shaped neck opening and a tie or fastening; a flat rectangle is not a bib: t) |
| Baby Burp Cloth | baby | 51.2 x 25.4; size CERTIFIES (other: PROVENANCE_MISSING) | 51.2 x 25.4; size CERTIFIES (other: PROVENANCE_MISSING) |
| Linen Lumbar Pillow | pillow | 28.8 x 49.6; size CERTIFIES (other: PHYSICAL_TEST_REQUIRED,PROVENANCE_MISSING) | 28.8 x 49.6; size CERTIFIES (other: PHYSICAL_TEST_REQUIRED,PROVENANCE_MISSING) |
| Linen Rug | runner | REFUSED at draft (a rug needs its own size band, a firm fabric and a non-slip backing: there is no size band) | REFUSED at draft (a rug needs its own size band, a firm fabric and a non-slip backing: there is no size band) |
| Linen Bath Mat | placemat | REFUSED at draft (a bath mat needs its own size band and a dense, absorbent fabric: there is no size band an) | REFUSED at draft (a bath mat needs its own size band and a dense, absorbent fabric: there is no size band an) |
| Linen Tablecloth | runner | REFUSED at draft (a tablecloth is sized to a table; there is no band or template for it: there is no size ba) | REFUSED at draft (a tablecloth is sized to a table; there is no band or template for it: there is no size ba) |
| Linen Hot Pad | placemat | REFUSED at draft (a hot pad needs a double-thickness heat-safe fabric and its own band: there is no size ban) | REFUSED at draft (a hot pad needs a double-thickness heat-safe fabric and its own band: there is no size ban) |
| Lace Doily | placemat | REFUSED at draft (a doily is a lace motif worked in the round, not a flat panel: there is no size band and n) | REFUSED at draft (a doily is a lace motif worked in the round, not a flat panel: there is no size band and n) |
| Linen Pouf | pillow | REFUSED at draft (a pouf is a stuffed three-dimensional form: there is no size band and no correct template ) | REFUSED at draft (a pouf is a stuffed three-dimensional form: there is no size band and no correct template ) |

Notes: "Large Linen Throw" and "Oversized Chunky Throw" now draft at 128 x 164.9 cm. That is inside both the throw class (≤145 x ≤170) and the large family (≥110 x ≥160), the only size both names allow. All 11 Launch-0 products certify, `nordic-forest-mosaic-throw-baby` is 57.6 x 67.8 cm and certifies, and radar pool geometry is unchanged (`test_the_radar_pool_drafts_exactly_what_it_drafted_before`).

## Suites

- `JOBS=4 SUITE_REGISTRY=0 SUITES="test_a4a_fix_object_size test_blanket_size_truth test_colourwork_template_size_truth test_fallback_draft_provenance test_flat_rows_size_truth test_opus2_draft_constructions test_opus2_drawstring_pouch test_opus2_knowledge_gaps test_opus2_pet_bed test_opus2_stocking test_opus2_tapestry_basket test_s1_fix_size_families test_s1_product_truth test_s1_product_truth_2 test_w4_pipe2_candidates test_w5_concept_intake"` → **TOTAL PASSING: 226; suites failing: 0**
- `SUITES="test_w5_a7_supply_stall"` → **6 passing, 0 failing**
- `SUITES="test_product_run"`, run alone → PRODUCT_RUN_RESULT

## Files

- `brambleloop/src/brambleloop/creative/size_truth.py`: `claims`, `coded_findings`, the unit/token parser, bed words, the large family, and the title-only objects
- `brambleloop/src/brambleloop/gates/certificate.py`: uses `coded_findings` for the CIR title and the listing title
- `brambleloop/tests/test_s1_product_truth_2.py`: new
- `brambleloop/DECISION_LOG.md`: D-S1-UNITLESS-DIMS and D-S1-RELATIVE-SIZE

Final SHA: FINAL_SHA
