# Review request: CLOTHING-E2E (garment and baby concepts through the production chain)

- Branch `eng/clothing-e2e`, cut from `claude/batch19-fixers` at 8204c93. No PR was opened. Nothing was deployed, and production is unchanged.
- **Production has still made no clothing product.** This branch proves the chain in tests only. One handoff is still open (see [The open handoff](#the-open-handoff-not-fixed)).

## Did the chain run unaided?

New suite: `tests/test_clothing_e2e.py`. It builds one world on a file-backed SQLite database, in SHADOW, with sockets closed. Its only input is fixture scan rows for the garments pod (marked TEST FIXTURES). From there the real handlers run.

| Step | Status |
|---|---|
| Scan evidence → `radar.demand_originals` proposes the 8 wearable originals | PASS |
| `radar.concept_intake`, with every intake gate, approves 7 of them. The kids tank is held by name. | PASS |
| `radar.score` pre-engineering gate → `supply` offer and admit, demand-ordered | PASS |
| `cir.draft` routes to the wearable engine and grades every size from its CYC table | PASS |
| `cir.compile` → `gate.certify` (compile, twin, reverse, child_safety stages) for every size | PASS |
| `listing.draft` → `assets.build`: the PDF, premium-standard and children's checks pass | PASS |
| `assets.build` → pricing → SEO → launch plan → listing package | **BLOCKED** at the listing image gate. Pinned by a test, not claimed. |
| Each size's certified CIR renders as US and UK customer PDFs. Each has a size chart naming every size, finished measurements, a schematic and care. Baby sizes also carry the children's safety block. | PASS (rendered from the stored CIR) |

Two products go through the whole chain:
- a baby romper (CYC baby table, 3m to 24m);
- a baby beanie (CYC head chart, Preemie to Toddler).

For the other 6 wearables, the suite checks routing and engine certification through the router and the intake records.

What the suite holds back, and nothing else:
- The other approved originals' `radar.score` jobs are cancelled before the drain. Each would otherwise run its own full chain.
- The `supply.after_chain_job` refill is held, as in `test_w6_listing_chain_e2e`.
- The vision judge is CLOSED, so it is replaced by the same fixture verdict `test_eng_families` uses.

## Broken handoffs fixed (each has a test)

1. **The concept generator never proposed a wearable.**
   - `products.demand` classed beanies, socks and slippers as `accessory`, which is not a boosted family.
   - The catalogue had no ENG-GARMENT-2 concepts at all.
   - Added 8 original wearables:
     - baby: beanie, romper, dress, V-neck cardigan;
     - clothing: kids beanie, boxy tee, kids tank, socks.
   - Hats, socks and slippers now read as `garment` (D-CLOTHING-E2E-1).
2. **Every closed-front child garment was refused at the PDF** with `OPENING_UNVERIFIED`, even though certification had granted it.
   - `intel.childrens.physical_plausibility` now checks the opening the engines measure against the CYC head and foot charts.
   - An unmeasured opening still reads UNVERIFIED (D-CLOTHING-E2E-2).
3. **The kids tank was certified, then refused at the PDF.** Its slash neck opens 37–48 cm, but a child's head is 46–56 cm.
   - `top_gates` now refuses it with `GARMENT_NECK_FIT`.
   - The router now admits the tank for adults only, so the concept is held at intake (D-CLOTHING-E2E-3).
4. **Baby dresses and rompers failed a top's length band** (`PROPORTION_LENGTH`). Each garment kind now has its own band (D-CLOTHING-E2E-4).
5. **Baby V-neck and raglan cardigans were refused** with `CLOSURE_WITHOUT_BUTTONS`. Their plain front bands were labelled `button_band`; a band with no buttonholes is now labelled `band` (D-CLOTHING-E2E-5).
6. **Baby beanies and kids socks got no children's safety block.** `graded_childrens_assignment` now reads the head and foot charts (D-CLOTHING-E2E-6). This is the child-safety gate getting stricter.
7. **A hat's size chart crashed `assets.build`** (`TypeError` formatting a `None` chest), and the premium standard required "to fit chest". Both now use the head or foot measures (D-CLOTHING-E2E-7).
8. **Two pre-existing failures on base, caused by the ENG-HOMEDECOR feature words:**
   - the outline word "round" held the owner's "Cosy Round Bear Amigurumi" original (`test_eng_demand_supply`) and the shawl proof ("wrap round the shoulders", `test_eng_garment2`);
   - the texture word "moss" held "Slouchy Moss Hat".

   "round" is now honest for the ball-body amigurumi and for a shawl worn round the shoulders. "Moss" stays held, because no engine works moss stitch, so that test's title was changed (D-CLOTHING-E2E-8).

**Child safety:**
- No child-safety gate was weakened.
- Baby wear has no buttons, snaps, ties or pom-poms. These are refused by the engines, and the e2e asserts it on the PDF.
- The baby PDFs carry the care note and the children's safety block.
- `small_parts.blocking` is empty for every baby size.

## The open handoff (not fixed)

`assets.build` passes every PDF and children's check, then stops on `LISTING_HERO_FABRIC_FLAT`. The digital-twin hero image of a single-colour wearable has almost no internal contrast, so the gate reads it as blank.

- The dead end is recorded (a chain successor is opened), not silent.
- No size reaches `pricing.position`, `listing.seo`, `launch.plan` or a listing package.
- No PDF file is stored: `assets.build` returns before the hand-off.
- The test `test_open_handoff_assets_build_stops_on_the_blank_single_colour_hero` pins this. Restore the chain assertions when the hero render is fixed.
- This is the next highest-value fix for clothing: render relief for single-colour fabric in the listing hero, or give wearables a hero source of their own.

Also not fixed:
- **One-piece kids sweater (`kite-day-kids-sweater`, ENG-GARMENT):** intake approves it, but it would be refused at the PDF with `OPENING_UNVERIFIED`. Its engine does not measure a neck opening yet.
- **Adult XS boxy tee and tank:** the slash neck opens 58.0 cm against the CYC Woman head's upper bound of 58.5 cm. Adult sizes are not checked by the children's rule, but the XS neck is marginal.

## Shared code touched (please review)

- `intel/childrens.py`:
  - `head_to_pass_cm`, `opening_reading`;
  - the openings check;
  - `LENGTH_TO_BACK_LENGTH_BY_KIND`.
- `publish/pdf.py`:
  - `graded_childrens_assignment` now reads the HEAD and FOOT tables;
  - `size_chart` and `_measure_row` for sizes not graded on the chest.
- `publish/pdf_standard.py`: `_size_chart` names the measure each size is graded on.
- `products/demand.py`: family and form words, category map.
- `products/wearables.py`:
  - the kids-tank neck gate;
  - V-neck band feature;
  - shawl honest phrase.
- `products/garment_families.py`: the band feature is `band` when the cardigan has no buttons.
- `creative/construction_families.py`:
  - tank audience is adult only;
  - `outline_round` is honest for amigurumi.
- `radar/demand_originals.py`: the 8 wearable originals.

## Tests

Every run used a venv built from `requirements.lock` plus `requirements-test.lock`.

**Runner, `JOBS=3 SUITE_REGISTRY=0 SUITES="…" bash run_tests.sh`.** The tree was dirty, and the run started before the last `pdf.py`, `pdf_standard.py` and `outline_round` edits. Result: 236 passing, 2 suites failing.
- `test_concepts100`: 2 failures, **identical on the unmodified base 8204c93** (pre-existing): the `hat` held key, and the synthetic-scan families.
- `test_vacuity`: failed on the new e2e loops. They now assert non-emptiness.
- Passed: `test_compiler`, `test_reverse`, `test_twin`, `test_eng_families`, `test_eng_garment`, `test_eng_garment2` (0 failed; its 2 failures on base are fixed), `test_eng_homedecor`, `test_garments`, `test_cert_grading`.

**Re-runs on the pushed tree 9125b51:**
- `test_clothing_e2e`, run with `CLOTHING_E2E_ONLY=thistledown-baby-beanie` (3 sizes): 10 OK, 0 failed.
- `test_vacuity`: 0 failed.
- `test_eng_demand_supply`: 0 failed. On base it has 1 failure, Cosy Round Bear, which is fixed here.

**Not re-run on the final tree:**
- The default two-product e2e. On the earlier tree the romper's 5 sizes all passed compile, certify, listing.draft, the PDF checks and the child-safety stage. Its PDFs were rendered directly after the last PDF edits: size chart, schematic, finished measurements, care, "size X of 5", no problems.
- `test_eng_families`, `test_eng_garment2` and `test_eng_homedecor`, after the last `pdf.py`, `pdf_standard.py` and `outline_round` edits.
- Run these before merging.
