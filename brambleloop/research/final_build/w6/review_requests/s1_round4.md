# Review request: S1 Product Truth, round 4 (`eng/s1-product-truth-3`)

Base: `origin/claude/w6-INTEG1` at 2676274, with `eng/s1-product-truth-2` (a570aab7 plus c170d99, a REVIEW_REQUEST-only commit) merged in at 813f12b.
This round fixes the independent review of a570aab7 (S1F2-H1, S1F2-M1 and the LOWs) by changing the design to **fail closed**.
It also reconciles A4a's certify-time object-size check with this branch's.

## The design change: fail closed (D-S1-FAIL-CLOSED, DECISION_LOG.md)

Each earlier round found more title phrasings that the parser silently dropped.
`creative/size_truth.claims(category, title, facts)` now tokenises every title in this order:

1. **Garment grades.** "size <grade>" phrases are bound first, to `CIR.grading.size`. This runs before the other parsers, so the "XL" or "2X" in "(size XL)" is never read as a relative word or as a dangling "2 x".
2. **Bound claims.** The parser binds and removes these:
   - named classes that the object's family defines (BLANKET_CLASSES and PILLOW_CLASSES);
   - stated dimensions with a unit: cm, mm, m, in, ft, and **yd/yards** (new);
   - D-S1-UNITLESS-DIMS pairs;
   - relative words, under D-S1-RELATIVE-SIZE. **"medium"** is now a relative word too.
3. **The allow-list.** The `ALLOWED_NON_SIZE` entries are matched next. Each one is cited and has its own test:

   | Entry | Example | Bound to |
   |---|---|---|
   | `n_in_1` | "2 in 1", "2-in-1", "3 in 1", "4 in 1" | Nothing: a versatility idiom, not inches |
   | `count` | "Set of 4", "(6)", "6-piece", "6 pack", "x2", "Set of Six" | The make count of the CIR's single component. A CIR with several components has no piece count, so its count is unbound. |
   | `colours` | "Two-Colour", "3 colour" | The CIR's colour table. It is checked at certification, because the palette is chosen after the plan. |
   | `code` | "C5", "J7", "C2C", "v3" | Nothing: a letter-led name or technique. An x-led token ("x2") is a count instead. |
   | `grade` | "(size 2X)" | `CIR.grading.size` (applied in step 1) |

4. **Everything left is refused** as `unbound size token: <token>`. That covers:
   - a figure: digits, a fraction ("1/2", "½"), a decimal, or a decimal comma ("1,5");
   - a number word ("one" to "ninety", "hundred", "dozen");
   - a word in `SIZE_CLASS_VOCAB` that the family does not define: king, queen, twin, toddler, youth, junior, teen, adult, body, euro, floor, half, quarter, standard, regular, preemie, xs, xxl, xl, "size" and "one size";
   - "full", "double" or "single" on bedding (a blanket or a pillow);
   - a unit with no figure.

   Construction phrases are removed first, so they are not refused: double-sided, double layer, double crochet, half double crochet and half-square triangles.

**Where the rule runs.** It applies at plan and at certification:

- `fallback_constructions.plan` wraps every route that would draft with `size_truth.plan_refusal`.
- The certificate reports `OBJECT_SIZE_UNBOUND` for **every** title, not only flat objects.
- The one carve-out is relative words outside the flat families. A vessel route binds small, medium and large to `products.vessels.BASKET_SIZES`, so those words are not reported there; the vessel routes' own size refusals are unchanged.

**Two decisions deliberately not to allow:**

- **Years ("2026").** A bare four-digit figure can be millimetres, and nothing in the catalogue needs one.
- **Bare "double".** It can mean double-sided or double-layer. "Double bed" and "double size" keep their recorded mapping to the CYC full class.

**Classes refused rather than defined:**

- Toddler, body, euro and floor are refused because I hold no cited standard for them here. I tried to fetch the CYC blanket table to cite a toddler size; the site returned a landing page, so I did not add one from memory.
- A pet blanket ("XL Dog Blanket") gets no human size family: the CYC classes are human sizes. Its class and relative words are therefore unbound.

## Plan and certify read one check

- `gates.certificate.size_findings_for(title, w, h, facts)` is the single size function:
  - the family bands (`OBJECT_SIZE_BANDS`, including A4a's dishcloth band unchanged);
  - then `size_truth.coded_findings`.
- `object_size_findings(cir, twin)` calls it with `facts_of(cir)`.
- `size_truth.drafted_refusal` measures the size the plan would draft (`runtime.pipeline.drafted_size`: the `concept_geometry` numbers, measured by their own compiled twin). It runs the same `size_findings_for` with category None, as certification does.
- So "Linen Throw 1.5 m", 'Throw Blanket 60"' and "Large Baby Blanket" are now refused at plan. Previously they were drafted and then refused at certify.
- Curly quotes and primes (“ ” ″ ′ ’) are normalised to the inch and foot marks they stand for.

## Rebase onto w6-INTEG1: one size gate

Merge 813f12b had conflicts in `gates/certificate.py`, `runtime/pipeline.py` and `tests/test_a4a_fix_object_size.py`. They were resolved hunk by hunk.

- **certificate.py.** This branch already carried a port of A4A-1 (5f22fe3), so its `OBJECT_SIZE_BANDS` is a superset of A4a's: the `dishcloth` entry is identical. `certify` calls `object_size_findings(cir, twin)` exactly once (asserted in `test_one_object_size_check_after_the_integ1_rebase`). There is no second, contradictory gate.
- **pipeline.py.** The template sizes come from S1. INTEG1's dishcloth template, coverage handoff and ideation briefs, consume-based concept text and `_reaches_network` are all kept.
- **test_a4a_fix_object_size.py.** Kept from INTEG1:
  - the ideation import;
  - `test_ideation_drafts_a_dishcloth_on_its_own_template_and_offers_no_hot_pad`.

  Taken from S1: the unbanded-title example is an ornament, because a placemat is banded since the flat-rows fix.
- Every A4a suite passes: `test_a4a_fix_object_size`, `test_a4a_low_fixes`, `test_a4a_fix_floor_and_reopen` and `test_w5_a4a_research_to_concept`. The research dishcloth certifies, `granted=True`.

## A catalogue change this rule forced: `bobble-floor-pillow` 1.4.0 → 1.5.0

`products.texture.build_bobble_pillow` was titled "Bobble Floor Pillow Cover", but it is a 44.0 x 45.4 cm cushion. Floor pillows are made for 56–91 cm pads.

- Under D-S1-FAIL-CLOSED, "floor" is unbound. That made `test_texture.test_all_three_certify` fail, because it lets through only the product-truth gates.
- I did not add the code to the fixture's allow-set: that would weaken the test.
- Instead the product is retitled "**Bobble Pillow Cover**", as with the W4-PRODREADY title corrections:
  - version bumped to 1.5.0;
  - fingerprint row updated (content fingerprint changed, claims fingerprint unchanged);
  - version pins updated in `test_release_versions` and `test_w4_pipe_board`;
  - the radar seed title changed to match.
- The slug stays `bobble-floor-pillow` (release identity).
- The product was already refused by `UNCALIBRATED_PRIMITIVE`, and it is not one of the 41 catalogue CIRs below.

## Finding → fix → test (`tests/test_s1_product_truth_3.py`, 16 tests)

| Finding | Fix | Test |
|---|---|---|
| S1F2-H1 unrecognised figures dropped ("108", "72", "20", "forty by fifty inches"; also ½, 1/2, 2026, 1,5) | Fail-closed residual: `unbound size token: <tok>` at plan and certify | `test_h1_every_unbound_figure_is_refused_at_plan_and_at_certify` |
| S1F2-H1 no yard unit ("3 yards", "2 yards", "60 yd") | `yd/yds/yard/yards` = 91.44 cm | `test_h1_yards_are_a_unit` |
| S1F2-M1 body / euro / floor / king pillow, double / toddler / half size / size S / size L | `SIZE_CLASS_VOCAB` and `BEDDING_VOCAB`, refused unless the family defines the class | `test_m1_size_class_words_without_a_cited_family_are_refused` |
| S1F2-M1 Medium passed while Small / Petite were refused | "medium" is in RELATIVE_SIZE | `test_m1_medium_follows_the_relative_size_rule_like_small_and_petite` |
| (guard) construction phrases are not sizes | NON_SIZE_PHRASES: double-sided / layer / thick / knit…, half-square… | `test_m1_construction_phrases_with_bed_words_are_not_sizes` |
| LOW plan and certify disagree | `drafted_refusal`: measure the drafted size, run the certificate's `size_findings_for` | `test_low_plan_refuses_exactly_what_certify_refuses` (the three titles, plus the property over 18 titles: whatever the plan drafts has no size error at certify) |
| LOW curly quotes refused | `_QUOTES` normalisation before NFKC | `test_low_curly_quotes_are_inch_marks` |
| LOW "XL Dog Blanket" drafted 153.6 x 202.9 | Pet blanket: no human size family; size words unbound | `test_low_a_pet_blanket_has_no_human_size_family` |
| Allow-list entries | One test each, plus a guard that the entry set equals the tested set | `test_allow_list_*` (5), `test_every_allow_list_entry_is_tested` |
| Rebase: one gate | `size_findings_for` shared; `object_size_findings` called once in `certify` | `test_one_object_size_check_after_the_integ1_rebase` |
| Prior fixed cases | — | `test_prior_fixed_cases_hold` |

**Results on a570aab7.** I copied the file into a worktree of a570aab7 and ran it: **15 of the 16 tests fail**.

- **Passes there:** `test_prior_fixed_cases_hold`. That is expected: it is a non-regression guard.
- **Fail there only because the new API is missing** (`AttributeError` on `plan_refusal`, `ALLOWED_NON_SIZE` or `drafted_refusal`):
  - `test_m1_construction_phrases_with_bed_words_are_not_sizes`, a guard;
  - `test_allow_list_n_in_1_is_not_a_size`, a guard;
  - `test_every_allow_list_entry_is_tested`;
  - `test_one_object_size_check_after_the_integ1_rebase`.
- **The other 11 fail on behaviour:** the old code drafted or certified the title.

## Before / after, measured through the real path (plan → geometry → builder → compile → twin → certify)

**How this was measured.** Each title went through `FC.plan`, `pipeline.concept_geometry`, `concept_to_cir`, `panel_pair` (for pillows), `compile_cir`, `build_twin` and `C.certify`.

- **"Before"** is the a570aab7 parser, measured at merge 813f12b. `size_truth.py` there is byte-identical to a570aab7.
- **"After"** is this branch's head.
- **"size CERTIFIES"** means the certificate has no `OBJECT_SIZE_*` or `LISTING_SIZE_*` error. The fixture's bare drafted CIRs also carry PROVENANCE_MISSING, and pillows carry PHYSICAL_TEST_REQUIRED. Those are not size findings.

**S1F2-H1**

| Title | Category | Before (a570aab7 parser) | After |
|---|---|---|---|
| Linen Scarf 3 yards | scarf | 19.2 x 152.2 cm; size CERTIFIES | REFUSED at plan: the title states one dimension (274.3 cm), which is neither the width (12-35 cm) nor the length (110-230 cm) o… |
| Linen Table Runner 2 yards | runner | 32.0 x 120.7 cm; size CERTIFIES | 35.2 x 182.6 cm; size CERTIFIES |
| Linen Table Runner 108 | runner | 32.0 x 120.7 cm; size CERTIFIES | REFUSED at plan: unbound size token: 108 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) |
| Linen Scarf 72 | scarf | 19.2 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: 72 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) |
| Linen Pillow Cover 20 | pillow | 41.6 x 41.7 cm; size CERTIFIES | REFUSED at plan: unbound size token: 20 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) |
| Linen Throw 60 yd | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: the title asks for a blanket 5486.4 cm a side; the blanket band is 42-290 cm (a blanket is from about 46 x 61 … |
| Linen Throw forty by fifty inches | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: forty (a number word; D-S1-FAIL-CLOSED) |

**S1F2-M1**

| Title | Category | Before (a570aab7 parser) | After |
|---|---|---|---|
| Body Pillow Cover | pillow | 41.6 x 41.7 cm; size CERTIFIES | REFUSED at plan: unbound size token: body (a size-class word the pillow family does not define from a cited standard; D-S1-FAIL… |
| Euro Pillow Sham | pillow | 41.6 x 41.7 cm; size CERTIFIES | REFUSED at plan: unbound size token: euro (a size-class word the pillow family does not define from a cited standard; D-S1-FAIL… |
| Floor Pillow Cover | pillow | 41.6 x 41.7 cm; size CERTIFIES | REFUSED at plan: unbound size token: floor (a size-class word the pillow family does not define from a cited standard; D-S1-FAI… |
| Double Linen Blanket | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: double (a size-class word the blanket family does not define from a cited standard; D-S1-F… |
| Toddler Linen Blanket | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: toddler (a size-class word the blanket family does not define from a cited standard; D-S1-… |
| Medium Linen Throw | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: the title names a relative size ('medium') with no dimensions, and a blanket has no defined size family for it… |
| Half Size Linen Blanket | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: half (a size-class word the blanket family does not define from a cited standard; D-S1-FAI… |
| Linen Throw Size S | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: size s (a graded size the pattern does not make: the fallback drafts no graded size; a gar… |
| Linen Throw Size L | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: size l (a graded size the pattern does not make: the fallback drafts no graded size; a gar… |
| Small Linen Throw | blanket | REFUSED at plan: the title names a relative size ('small') with no dimensions, and a blanket has no defined size family for it … | REFUSED at plan: the title names a relative size ('small') with no dimensions, and a blanket has no defined size family for it … |
| Petite Linen Throw | blanket | REFUSED at plan: the title names a relative size ('petite') with no dimensions, and a blanket has no defined size family for it… | REFUSED at plan: the title names a relative size ('petite') with no dimensions, and a blanket has no defined size family for it… |
| King Pillow Cover | pillow | 41.6 x 41.7 cm; size CERTIFIES | REFUSED at plan: unbound size token: king (a size-class word the pillow family does not define from a cited standard; D-S1-FAIL… |

**LOWs**

| Title | Category | Before (a570aab7 parser) | After |
|---|---|---|---|
| Linen Throw 1.5 m | blanket | 150.4 x 150.4 cm; certify REFUSES OBJECT_SIZE_NOT_AS_TITLED | REFUSED at plan: the title names a throw blanket, and the pattern's finished size 150.4 x 150.4 cm is outside that size class (… |
| Linen Blanket 150cm square | blanket | 150.4 x 150.4 cm; size CERTIFIES | 150.4 x 150.4 cm; size CERTIFIES |
| Linen Throw Blanket 60" | blanket | 153.6 x 152.2 cm; certify REFUSES OBJECT_SIZE_NOT_AS_TITLED | REFUSED at plan: the title names a throw blanket, and the pattern's finished size 152.2 x 153.6 cm is outside that size class (… |
| Linen Blanket 2 metres | blanket | 198.4 x 200.0 cm; size CERTIFIES | 198.4 x 200.0 cm; size CERTIFIES |
| Large Baby Blanket | blanket | 115.2 x 160.1 cm; certify REFUSES OBJECT_SIZE_NOT_AS_TITLED | REFUSED at plan: the title names a baby blanket, and the pattern's finished size 115.2 x 160.1 cm is outside that size class (b… |
| Linen Throw 50”x60” | blanket | REFUSED at plan: the title has a figure the size parser cannot read ('x6') | 128.0 x 152.2 cm; size CERTIFIES |
| XL Dog Blanket | blanket | 153.6 x 202.9 cm; size CERTIFIES | REFUSED at plan: the title names a relative size ('xl') with no dimensions, and a pet blanket has no cited size band (the CYC c… |

**Prior fixed cases**

| Title | Category | Before (a570aab7 parser) | After |
|---|---|---|---|
| King Size Ridge Throw | blanket | REFUSED at plan: the title names throw and king, and no size is all of them (throw: 75-145 x 90-170 cm; king: 240-280 x 260-290… | REFUSED at plan: the title names throw and king, and no size is all of them (throw: 75-145 x 90-170 cm; king: 240-280 x 260-290… |
| Linen Lumbar Pillow 12 x 24 | pillow | 32.0 x 60.5 cm; size CERTIFIES | 32.0 x 60.5 cm; size CERTIFIES |
| Linen Blanket 200 x 220 | blanket | 198.4 x 219.9 cm; size CERTIFIES | 198.4 x 219.9 cm; size CERTIFIES |
| Linen Pillow Cover 26x26 | pillow | 67.2 x 65.9 cm; size CERTIFIES | 67.2 x 65.9 cm; size CERTIFIES |
| Queen Linen Blanket | blanket | 230.4 x 253.6 cm; size CERTIFIES | 230.4 x 253.6 cm; size CERTIFIES |
| Queen Size Linen Blanket | blanket | 230.4 x 253.6 cm; size CERTIFIES | 230.4 x 253.6 cm; size CERTIFIES |
| Linen Blanket 200 x 220 cm | blanket | 198.4 x 219.9 cm; size CERTIFIES | 198.4 x 219.9 cm; size CERTIFIES |
| Pillow Cover 26 x 26 inch | pillow | 67.2 x 65.9 cm; size CERTIFIES | 67.2 x 65.9 cm; size CERTIFIES |
| Large Tapestry 100 x 150 cm | wall_decor | 99.2 x 150.4 cm; size CERTIFIES | 99.2 x 150.4 cm; size CERTIFIES |
| Baby Burp Cloth | baby | 51.2 x 25.4 cm; size CERTIFIES | 51.2 x 25.4 cm; size CERTIFIES |
| Linen Lumbar Pillow | pillow | 28.8 x 49.6 cm; size CERTIFIES | 28.8 x 49.6 cm; size CERTIFIES |
| Large Linen Throw | blanket | 128.0 x 164.9 cm; size CERTIFIES | 128.0 x 164.9 cm; size CERTIFIES |
| Linen Throw 2 in 1 | blanket | 128.0 x 152.2 cm; size CERTIFIES | 128.0 x 152.2 cm; size CERTIFIES |
| Skinny Scarf 10 cm | scarf | REFUSED at plan: the title asks for a scarf 10 cm wide; the scarf band is 12-35 cm wide (a scarf is about 15-30 cm wide and 120… | REFUSED at plan: the title asks for a scarf 10 cm wide; the scarf band is 12-35 cm wide (a scarf is about 15-30 cm wide and 120… |
| Short Runner 40 cm | runner | REFUSED at plan: the title asks for a runner 40 cm long; the runner band is 90-275 cm long (a table runner is about 30-45 cm wi… | REFUSED at plan: the title asks for a runner 40 cm long; the runner band is 90-275 cm long (a table runner is about 30-45 cm wi… |
| Linen Blanket 50 x 60 | blanket | REFUSED at plan: the title states '50 x 60' with no unit, and the unit cannot be determined: both cm and in fit the blanket ban… | REFUSED at plan: the title states '50 x 60' with no unit, and the unit cannot be determined: both cm and in fit the blanket ban… |

**Extra fail-closed probes and plain titles**

| Title | Category | Before (a570aab7 parser) | After |
|---|---|---|---|
| Linen Throw 2026 | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: 2026 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) |
| Linen Coaster Set of 4 | coaster | REFUSED at plan: category 'coaster' needs a disc worked in joined rounds (products.vessels.build_hexagon_coaster); the fallback… | REFUSED at plan: category 'coaster' needs a disc worked in joined rounds (products.vessels.build_hexagon_coaster); the fallback… |
| Linen Throw ½ | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: 1⁄2 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) |
| Linen Throw 1/2 | blanket | 128.0 x 152.2 cm; size CERTIFIES | REFUSED at plan: unbound size token: 1/2 (a figure with no unit and no claim it binds to; D-S1-FAIL-CLOSED) |
| Linen Table Runner 72 in | runner | 35.2 x 182.6 cm; size CERTIFIES | 35.2 x 182.6 cm; size CERTIFIES |
| Linen Placemat | placemat | 44.8 x 30.1 cm; size CERTIFIES | 44.8 x 30.1 cm; size CERTIFIES |
| Linen Throw | blanket | 128.0 x 152.2 cm; size CERTIFIES | 128.0 x 152.2 cm; size CERTIFIES |
| Linen Scarf | scarf | 19.2 x 152.2 cm; size CERTIFIES | 19.2 x 152.2 cm; size CERTIFIES |
| Linen Pillow Cover | pillow | 41.6 x 41.7 cm; size CERTIFIES | 41.6 x 41.7 cm; size CERTIFIES |

Notes on the "after" sizes:

- 'Linen Throw 50”x60”' drafts at 128.0 x 152.2 cm. That is 50 x 60 in (127 x 152.4) within tolerance, and it certifies. It was refused before because of the curly quotes.
- "Linen Table Runner 2 yards" drafts at 182.6 cm long, which is 2 yd (182.9).
- "Linen Blanket 2 metres" and "150cm square" draft at 198.4 x 200.0 and 150.4 x 150.4, and certify.
- "Linen Scarf 3 yards" (274 cm) and "Linen Throw 60 yd" are refused by size, because no scarf or throw is that long.

## Catalogue and Launch-0

- **All 41 catalogue CIRs are byte-identical before and after**: SHA-256 of `dataclasses.asdict(cir)`, compared slug by slug. They also have the same certification outcome. The set is `_catalogue()` in `test_s1_product_truth_2`: Launch-0 and proposed builders, `builder.CATALOGUE`, every Nordic Forest size, 6 moment candidates, the vessel and 17 graded garments. It contains the review's 29.
- Every one certifies except the three recorded refusals, each by exactly its recorded codes:
  - `heart-row-ring-pillow`: OBJECT_SIZE_OUT_OF_BAND and PHYSICAL_TEST_REQUIRED;
  - `reading-nook-cable-wrap`: UNCALIBRATED_PRIMITIVE;
  - `spring-garden-kneeler`: PHYSICAL_TEST_REQUIRED.
- The garment titles "(size 2X)" … "(size 16)" bind to `CIR.grading.size`. "Textured Stripe Ornament Set (6)" binds to make 6.
- **All 11 Launch-0 products (`launch0.BUILDERS`) certify:** basket_large, basket_medium, basket_small, cloudline_blanket, harvest_runner, hexagon_coasters, key_basket, nordic_forest_baby, placemat_pair, snowfall_throw, snowflake_ornaments.

## Suites

All runs used `JOBS=… SUITE_REGISTRY=0 PY=/tmp/venv/bin/python bash run_tests.sh`.

**1. The 38 size, fallback, OPUS2 and A4a suites** (the a4a, s1, opus2, fallback, size-truth, texture, release-versions, w5 intake and research suites), before the retitle. The run record says GIT SHA 813f12b with a dirty tree: the uncommitted fail-closed change, committed unchanged as 72404da.

- **TOTAL PASSING: 440; suites failing: 1.**
- The one failure was `test_texture.test_all_three_certify`: "floor" became unbound. It is fixed by the retitle above.
- `test_texture` and `test_release_versions` were then re-run after the retitle and pass.

**2. All 73 suites that call `certify(`, plus the radar, pods and listing suites and every S1 suite** (everything except `test_product_run`). The run record says GIT SHA da7ea00 with a dirty tree: the retitle, committed as ae44cc8.

- **TOTAL PASSING: 1296; suites failing: 8.** One of those failures was mine: the bobble pillow version pin in `test_w4_pipe_board` (`pillow_release_is_name_true`). It was updated with the bump in cdbe5d5.
- The other 7 also fail at the w6-INTEG1 base. I re-ran `test_w4_pipe_board`, `test_w4_listready` and `test_cert_growth_ops` in a worktree of 2676274 with the same failures:
  - `test_cert_growth_ops`, `test_cert_growth_seasonal`, `test_fb4_launch`, `test_fb4_lc`, `test_w4_adopt_manual_listing`, `test_w4_shopsync`: `starlette.testclient requires the httpx2 package`. This is an environment gap. My attempt to install `httpx2` into the venv was not permitted, so **these 5 suites were not exercised here**, and neither were the HTTP-client tests in `test_cert_growth_ops`.
  - `test_w4_listready` `test_f8_…`: "unclassified Etsy write call sites: approvals.py `_standing_policy`". This comes from the WS4 standing-policy merge on INTEG1, not from this branch.
  - `test_w4_pipe_board` `proposal_certifies:diamond-lattice-dishcloth` and `basketweave-textured-washcloth`, and `proposals_reach_visual`. A4a's dishcloth band refuses two proposal CIRs (21.6 x 15.9 and 19.2 x 17.0 cm). These are the same failures on the base, unchanged by this branch.

**3. After the retitle:** `test_w4_pipe_board test_texture test_release_versions test_geometry test_s1_product_truth_3` → **TOTAL PASSING: 156; suites failing: 1** (`test_w4_pipe_board`, with only the base failures above).

**4. `SUITES="test_product_run"`, run alone:** **TOTAL PASSING: 36; suites failing: 0** (3644 s).

- Run record `artifacts/suite_runs/20261118T153536Z-8896.json`: GIT SHA cdbe5d5, tree clean at start.
- During the run, HEAD moved to 2a858b5. That commit adds only this file and deletes the root REVIEW_REQUEST.md, so the runner marks the run not release-eligible. The code under test is the code at the final SHA.

## Files

- `brambleloop/src/brambleloop/creative/size_truth.py`: fail-closed tokenizer, `ALLOWED_NON_SIZE`, `SIZE_CLASS_VOCAB`, yards, quote normalisation, pet blankets, `facts_of`, `plan_refusal`, `drafted_refusal`.
- `brambleloop/src/brambleloop/gates/certificate.py`: `size_findings_for`, the one size check; the listing title is checked with the CIR's facts.
- `brambleloop/src/brambleloop/creative/fallback_constructions.py`: `plan` wraps `_plan` with `plan_refusal`; `_size_refusal` adds `drafted_refusal`.
- `brambleloop/src/brambleloop/runtime/pipeline.py`: `drafted_size`; merge resolution.
- `brambleloop/src/brambleloop/products/texture.py`, `radar/opportunity.py`, `tests/data/release_fingerprints.tsv`, `tests/test_release_versions.py`, `tests/test_w4_pipe_board.py`: the bobble pillow retitle to 1.5.0.
- `brambleloop/tests/test_s1_product_truth_3.py`: new, 16 tests.
- `brambleloop/tests/test_a4a_fix_object_size.py`: merge resolution.
- `brambleloop/DECISION_LOG.md`: D-S1-FAIL-CLOSED.
- Root `REVIEW_REQUEST.md`: deleted. This file replaces it.

**Final SHA:** the head of `eng/s1-product-truth-3`, which is the commit that adds this section. Code is unchanged since cdbe5d5.
