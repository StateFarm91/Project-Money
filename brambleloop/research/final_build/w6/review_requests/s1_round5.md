# Review request: S1 Product Truth, round 5 (`eng/s1-product-truth-3`)

Base: 2a858b59, the head the independent review covered. This round fixes that review:

- S1F3-H1;
- S1F3-M1;
- the LOWs;
- the integration finding: the `test_w4_pipe_board` dishcloth and washcloth proposals.

| Commit | What it is |
|---|---|
| 87d2488 | The code changes, plus the two required test-file updates in `test_s1_product_truth_3` (explained below) |
| f2866e9 | The new regression suite, `tests/test_s1_product_truth_4.py` |
| 148533e | Decision log: D-S1-EXACT-ALLOW-LIST and D-S1-PROPOSAL-FIT |
| 6f1db7e | `test_garment_design`: the fixture keys are renamed (explained below) |

Another session pushed two documentation-only commits (12f90e9, c097285) to `s1_round4.md` in between. They touch nothing else.

## What changed

**S1F3-H1: the code allow-list is exact and cited.** The code is in `creative/size_truth.py`.

- `ALLOWED_NON_SIZE["code"]` is no longer the `[a-w][a-z]*\d+` shape. It is an exact list:
  - "C2C";
  - the US crochet hook sizes from the Craft Yarn Council hook chart (craftyarncouncil.com/standards/hooks), letter and number paired exactly: B-1, C-2, D-3, E-4, F-5, G-6, H-8, I-9, J-10, K-10.5 / K-10 1/2, L-11, M-13, N-13, M/N-13, N-15, P-15, N/P-15, with an optional "hook".
- These codes are taken out first (`_protect_codes`), so "L-11" is the 8 mm hook and not a length.
- "C5", "J7", "v3", "L-12", "H-9" and "L11" are no longer codes.
- **Lettered dimensions.** `_bind_lettered` reads L/W/H/D/Dia/Sz followed by a figure:
  - A W together with an L or H is rewritten as the stated pair. "W130cm L170cm" becomes 130 x 170 cm, which the one dimension parser then binds. A unitless pair follows D-S1-UNITLESS-DIMS: "Runner L250 W40" binds as cm and drafts 38.4 x 250.2.
  - A single lettered figure with a unit binds as a length or a width. "L180cm" drafts a scarf 180 cm long.
  - These are refused:
    - a single lettered figure with no unit ("L300", "L230");
    - D/Dia, because the fallback drafts nothing round;
    - Sz;
    - two widths, or two lengths.

**S1F3-M1: size compounds and bed or occasion words.**

- `SIZE_COMPOUNDS` normalises compounds to their CYC class before any size word is read. "Kingsize" and "Queensize" become "king size" and "queen size", and "Calking" becomes "california king".
- "Super King" and "Superking" become "superking", which is refused. It is the UK 6 ft bed, with no CYC class.
- `BEDDING_VOCAB` gained these words, refused on a blanket or a pillow because no cited band exists for them: superking, emperor, bedspread, coverlet, bassinet, moses, cradle, pram, picnic, travel, beach, stadium, camping, grand.
- A bedspread or coverlet is bound when the title names a CYC bed class: "Queen Linen Coverlet" drafts the queen size.
- A title that names only a bedspread or coverlet is a blanket (`object_of`), so certification holds it to the blanket family even without a category.

**LOWs.**

| Was refused | Fix |
|---|---|
| "50 x 60 inches 2 in 1" | `_UNIT`: only a bare "in" refuses a following figure; "inches" never does. |
| "W130cm L170cm" | The lettered-dimension rule above. |
| "60ʺ" | U+02BA, U+02EE, U+02B9 and U+02BC are inch and foot marks (`_QUOTES`). |
| "100% Cotton" | New `percent` entry, 0–100 %: fibre content. |
| "4ply" | New `ply` entry: 2/3/4/5/8/10/12/14 ply, the UK/AU/NZ yarn-weight names in the CYC Standard Yarn Weight System. |
| "No. 5" | New `number` entry: a design number, unless a unit or "x"/"by" follows. Dimensions are read before the allow-list in any case. |
| "3 Colour" was drafted at plan and refused only at certify | At plan the colour count is bound to `fallback_colour_counts()`, the counts the fallback palettes in `runtime.pipeline._PALETTES` have (now {2}). |

**Integration: the dishcloth and washcloth proposals compile inside the band.** The code is in `products/pipeline_board.py`.

- **The cause.** `proposal_cir` rounded width and height to whole motifs separately. That drew the 22 x 22 cm proposals at 21.6 x 15.9 cm and 19.2 x 17.0 cm.
- **The fix, `_fit_to_proposal`.** It runs only when the drawn counts miss the proposal's own stated size (`size_truth._met`) or the certificate's size check. It builds the neighbouring whole-motif counts (±2 motifs, ±2 repeats) and measures each on its own twin. The pick must first pass the size check; among those, it has the smallest worst-case log miss of width, height and shape.
- **The band is not loosened.**
- **Results.** The dishcloth is now 21.6 x 23.8 cm (aspect 1.10) and the washcloth 25.6 x 25.7 cm (1.00).
- **The other proposals were checked.** They keep their counts and their CIRs: chevron scarf 19.2 x 154.8; heart runner 32.0 x 119.1; pumpkin runner 32.0 x 116.4; basketweave hand towel 32.0 x 43.1. The fir-and-star runner (28.8 x 112.9) is 3.2 cm under its stated width, so it was searched, and its own counts were already the best.
- **Why it works without A4a.** The trigger is the proposal's stated size, not only the band, so the dishcloths fit whether or not A4a's code is on the tree.

## Two existing test files changed, and why

- **`test_s1_product_truth_3.test_allow_list_letter_led_codes_are_not_figures`.** It asserted that "C5 Linen Throw" and "Linen Throw J7" pass. Under the exact list the review asked for they are refused, so the test now asserts the refusal, which is stricter. Its passing examples are now "H-8 Hook" and "J-10", plus "C2C" as before.
- **`test_s1_product_truth_3.test_every_allow_list_entry_is_tested`.** The entry set gains percent, ply and number. Each has its own test in `test_s1_product_truth_4`.
- **`test_garment_design`.** The fixture concepts were keyed "v1".."v4", and `idea()` uses the key as the title. A product titled "V1" is now an unbound figure, so the keys are renamed to tidepool, forest, deckchair and harbour. The assertions are unchanged.

## Finding → fix → test (`tests/test_s1_product_truth_4.py`, 13 tests)

| Finding | Test |
|---|---|
| S1F3-H1 lettered dimensions | `test_h1_lettered_dimensions_are_bound_or_refused` |
| S1F3-H1 exact, cited code list | `test_h1_code_allow_list_is_exact_and_cited` |
| S1F3-M1 compounds bind to the CYC class | `test_m1_bed_size_compounds_bind_to_their_cyc_class` |
| S1F3-M1 bed and occasion words refused (bed cover with a class binds) | `test_m1_bed_and_occasion_size_words_without_a_cited_band_are_refused` |
| LOW inches then a figure | `test_low_inches_followed_by_a_figure_are_still_inches` |
| LOW W130cm L170cm | `test_low_lettered_dimensions_with_units_bind` |
| LOW 60ʺ | `test_low_modifier_letter_primes_are_inch_and_foot_marks` |
| LOW 100% Cotton / 4ply / No. 5 | `test_low_percent_is_not_a_size`, `test_low_ply_is_not_a_size`, `test_low_number_is_not_a_size` (each with negatives: 150 %, 7 ply, and "No 72 in" read as a dimension) |
| LOW colour count at plan | `test_low_colour_count_is_refused_at_plan_as_at_certify` |
| Integration: proposals | `test_integration_every_proposal_compiles_inside_its_size`, `test_integration_the_dishcloth_band_is_not_loosened` |

**Results on 2a858b59.** I copied the file into a worktree of 2a858b59 and ran it: **12 of the 13 tests fail**.

- **Passes there:** `test_integration_the_dishcloth_band_is_not_loosened`. That is expected: it is a non-regression guard.
- **Fail there on behaviour (10):** the H1, M1 and LOW titles were drafted and certified, or refused, exactly as the review describes.
- **Fail there because the new API is missing:**
  - `test_low_colour_count_is_refused_at_plan_as_at_certify` (`fallback_colour_counts`). On 2a858b59 the plan drafts "3 Colour Linen Throw", and only certify refuses it.
  - `test_integration_every_proposal_compiles_inside_its_size` (`pipeline_board._measured`). On 2a858b59 `certify` refuses both dishcloth proposals with OBJECT_SIZE_OUT_OF_BAND.

## Before / after, measured through the real path

**How this was measured.** Each title went through plan, geometry, builder, compile, twin and certify. "size CERTIFIES" means the certificate has no OBJECT_SIZE_* or LISTING_SIZE_* error.

**S1F3-H1**

| Title | Category | Before (2a858b59) | After |
|---|---|---|---|
| Linen Scarf L300 | scarf | 19.2 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: l300 (a lettered length with no unit: a single figure's unit cannot be determined; D-S1-FA… |
| Linen Scarf L230 | scarf | 19.2 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: l230 (a lettered length with no unit: a single figure's unit cannot be determined; D-S1-FA… |
| Runner L250 W40 | runner | 32.0 x 120.7 cm; size CERTIFIES | 38.4 x 250.2 cm; size CERTIFIES |
| Pillow Cover W60 H60 | pillow | 41.6 x 41.7 cm; size CERTIFIES | 59.8 x 60.8 cm; size CERTIFIES |
| Throw H150 W200 | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: the title states '200 x 150' with no unit, and the unit cannot be determined: neither cm nor in fits the blank… |
| Linen Blanket W50 L60 | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: the title states '50 x 60' with no unit, and the unit cannot be determined: both cm and in fit the blanket ban… |
| Linen Throw d50 | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: d50 (a diameter; the fallback drafts no round piece, so it cannot be bound; D-S1-FAIL-CLOSED) |
| Linen Throw sz60 | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: sz60 (a size code with no unit and no size class it binds to; D-S1-FAIL-CLOSED) |
| C5 Linen Throw | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: c5 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) |
| Linen Throw L-11 | blanket | REFUSED at plan: unbound size token: 11 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) | 128.0 x 152.2 cm; size CERTIFIES |
| Linen Throw H-8 Hook | blanket | REFUSED at plan: unbound size token: 8 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) | 128.0 x 152.2 cm; size CERTIFIES |

**S1F3-M1**

| Title | Category | Before (2a858b59) | After |
|---|---|---|---|
| Kingsize Linen Blanket | blanket | 128.0 x 152.2 cm; size CERTIFIES | 252.8 x 273.6 cm; size CERTIFIES |
| Queensize Linen Blanket | blanket | 128.0 x 152.2 cm; size CERTIFIES | 230.4 x 253.6 cm; size CERTIFIES |
| Superking Linen Blanket | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: superking (a size-class word the blanket family does not define from a cited standard; D-S… |
| Linen Bedspread | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: bedspread (a size-class word the blanket family does not define from a cited standard; D-S… |
| Linen Coverlet | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: coverlet (a size-class word the blanket family does not define from a cited standard; D-S1… |
| Queen Linen Coverlet | blanket | REFUSED at plan: unbound size token: queen (a size-class word the object family does not define from a cited standard; D-S1-FAI… | 230.4 x 253.6 cm; size CERTIFIES |
| Bassinet Blanket | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: bassinet (a size-class word the blanket family does not define from a cited standard; D-S1… |
| Picnic Blanket | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: picnic (a size-class word the blanket family does not define from a cited standard; D-S1-F… |
| Travel Blanket | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: travel (a size-class word the blanket family does not define from a cited standard; D-S1-F… |
| Grand Throw | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: grand (a size-class word the blanket family does not define from a cited standard; D-S1-FA… |

**LOWs**

| Title | Category | Before (2a858b59) | After |
|---|---|---|---|
| Linen Blanket 50 x 60 inches 2 in 1 | blanket | REFUSED at plan: the title states '50 x 60' with no unit, and the unit cannot be determined: both cm and in fit the blanket ban… | 128.0 x 152.2 cm; size CERTIFIES |
| Linen Blanket W130cm L170cm | blanket | REFUSED at plan: the title states 2 different sizes (130, 170 cm); one pattern makes one size | 131.2 x 170.3 cm; size CERTIFIES |
| Linen Table Runner 60ʺ | runner | REFUSED at plan: unbound size token: 60 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) | 35.2 x 152.4 cm; size CERTIFIES |
| 100% Cotton Linen Throw | blanket | REFUSED at plan: unbound size token: 100 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) | 128.0 x 152.2 cm; size CERTIFIES |
| 4ply Linen Throw | blanket | REFUSED at plan: unbound size token: 4ply (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) | 128.0 x 152.2 cm; size CERTIFIES |
| Linen Throw No. 5 | blanket | REFUSED at plan: unbound size token: 5 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) | 128.0 x 152.2 cm; size CERTIFIES |
| 3 Colour Linen Throw | blanket | 128.0 x 152.2 cm; certify REFUSES OBJECT_SIZE_UNBOUND | REFUSED at plan: unbound size token: 3 colour (a colour count the fallback does not draft: its palettes have 2 colours; a colou… |
| Two-Colour Linen Throw | blanket | 128.0 x 152.2 cm; size CERTIFIES | 128.0 x 152.2 cm; size CERTIFIES |

**Plain titles (unchanged)**

| Title | Category | Before (2a858b59) | After |
|---|---|---|---|
| Linen Throw | blanket | 128.0 x 152.2 cm; size CERTIFIES | 128.0 x 152.2 cm; size CERTIFIES |
| Linen Scarf | scarf | 19.2 x 152.2 cm; size CERTIFIES | 19.2 x 152.2 cm; size CERTIFIES |
| Linen Pillow Cover | pillow | 41.6 x 41.7 cm; size CERTIFIES | 41.6 x 41.7 cm; size CERTIFIES |
| Linen Dishcloth | dishcloth | 21.9 x 22.4 cm; size CERTIFIES | 21.9 x 22.4 cm; size CERTIFIES |

## Catalogue and Launch-0

- **All 41 catalogue CIRs are byte-identical between 2a858b59 and this branch**: SHA-256 of `dataclasses.asdict(cir)`, using `test_s1_product_truth_2._catalogue()`. They also have identical certification outcomes.
- Every one certifies except the three recorded refusals, each by exactly its recorded codes:
  - `heart-row-ring-pillow`: OBJECT_SIZE_OUT_OF_BAND and PHYSICAL_TEST_REQUIRED;
  - `reading-nook-cable-wrap`: UNCALIBRATED_PRIMITIVE;
  - `spring-garden-kneeler`: PHYSICAL_TEST_REQUIRED.
- **All 11 Launch-0 products (`launch0.BUILDERS`) certify:** basket_large, basket_medium, basket_small, cloudline_blanket, harvest_runner, hexagon_coasters, key_basket, nordic_forest_baby, placemat_pair, snowfall_throw, snowflake_ornaments.
- The only CIRs that changed are the two pipeline proposals, `diamond-lattice-dishcloth` and `basketweave-textured-washcloth`. They are 0.1.0 pre-release proposals, not catalogue releases.

## Integration check (scratch merges, not pushed)

1. **This branch at f2866e9 merged with `origin/claude/w6-INTEG1` (e4c442c).** The merge was clean.
   - `test_w4_pipe_board` passes with **0 failures**.
   - `test_s1_product_truth_4` and `test_s1_product_truth_3` pass.
2. **INTEG1 with A4a reverted, then this branch merged.**
   - **How it was built.** I ran `git revert -m 1 d51adb3` on INTEG1. The revert's conflicts in `suite_final_segment.txt` and `autonomy_map.json` were resolved to INTEG1's side. The merge's conflicts in `certificate.py` and `pipeline.py` were resolved to S1's side. `test_a4a_fix_object_size.py` stays deleted.
   - **Passes:** `test_w4_pipe_board` (0 failures), `test_s1_product_truth_4`, `test_s1_product_truth_2` and `test_s1_fix_size_families`.
   - **Fails:** one assertion in `test_s1_product_truth_3.test_one_object_size_check_after_the_integ1_rebase`. It checks that A4A-1 refuses a 38.4 x 11.4 "Linen Ridge Dishcloth". Without A4a's `first_customer` family words, "dishcloth" is not a product-type family, so that gate is absent. This is a round-4 test of A4a's own integration, and it is expected to fail while A4a is reverted.
   - The scratch branches were deleted locally and never pushed.

## Suites

All runs used `JOBS=… SUITE_REGISTRY=0 PY=/tmp/venv/bin/python bash run_tests.sh`.

**1. The 113 suites that call `certify(`, `size_truth`, `pipeline_board` or `fallback_constructions`, plus every s1, a4a, opus2, radar, pods, listing and size suite** (everything except `test_product_run`).

- **Run:** `artifacts/suite_runs/20261118T161538Z-2321`, at GIT SHA f2866e9 with a clean tree. HEAD moved to 148533e during the run, a decision-log-only commit.
- **TOTAL PASSING: 1704; suites failing: 2.**
  - `test_garment_design`: the "V1" fixture titles. Fixed in 6f1db7e; it now passes with 25 passing and 0 failing.
  - `test_w4_listready` `test_f8_…`: "unclassified Etsy write call sites: approvals.py `_standing_policy`". This also fails at the base (WS4 standing-policy merge on INTEG1; recorded in round 4). It is not from this branch.
- These suites ran and passed here: `test_cert_growth_ops` (13 OK), `test_cert_growth_seasonal` (24 OK), `test_fb4_launch` (9 OK), `test_fb4_lc` (16 OK) and `test_w4_adopt_manual_listing` (19 OK). In round 4 they could not start because `httpx2` was missing. In this venv `httpx2` only causes a StarletteDeprecationWarning.

**2. `test_garment_design` and `test_w4_listready` re-run at 6f1db7e:** TOTAL PASSING 65, 1 suite failing (run record `artifacts/suite_runs/20261118T164935Z-9774.json`). `test_garment_design` passes. The one failure is `test_w4_listready` f8 (`unclassified Etsy write call sites: [('app/command_center/approvals.py', '_standing_policy')]`). That failure is pre-existing on the base 2a858b59 and lies outside S1's scope.

**3. `test_product_run`, run alone at 4ab9559:** TOTAL PASSING 36, 0 suites failing (run record `artifacts/suite_runs/20261118T165218Z-10183.json`, tree clean at start). 4ab9559 changes only this document on top of 6f1db7e, so the code under test is the same as at 6f1db7e.
