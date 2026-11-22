# IMAGES-DIALIN: findings, fixes and numbers (branch `eng/images-dialin`, base 5297dbba)

Decision record: `D-ENG-IMAGES-DIALIN` in `brambleloop/DECISION_LOG.md`. Tests: `brambleloop/tests/test_images_dialin.py`.
Nothing is deployed. No threshold, gate or publication rule changed. No paid call was added or made.

## Task A: basket images

### What FLUX was told before this change (product-only and lifestyle frames)

The route is `creative/flux3_generator.py` → `creative/image_stages.py` → `gateway/images.py` → FLUX 3 `/v1/flux-3-image`.

- **References.** The four deterministic pattern references were already sent in `images` (layout, texture, chart, rules). For a basket, though, `layout` was `charts.render_round_fabric`: a flat disc of concentric rounds.
  - That chart draws every round piece as a circle, including the **hexagon** market-basket-small.
  - Nothing showed FLUX the wall from the side, which is the view the gate counts bands on.
- **Prompt.** PRODUCT v3 said "a vessel with a flat 6-sided (hexagon) base" and "cream ground with 2 wine stripes of 2 rounds each (rounds 15-16 and rounds 18-19)".
  - It never said which rounds were base and which were wall. It gave no band order bottom to top, no share of wall height and no base/wall split.
  - The IMAGE-BLOCKED COUNTS section returned "" for vessels.
- **Resolution.** Listing frames already ask for `2048x2048`, which is the **2k** tier (about 2048 px, US$0.10). That meets the 2000 px floor, which `_run` enforces before any call.
  - 16 frames (the per-gallery image cap) at 2k cost US$1.60, under the US$2.50 cap.
  - Only the stage-A identity anchor, an intermediate frame that is not a listing frame, uses 1k.
  - The owner's 896–1024 px frames are 1k dashboard renders. They are not factory output.
  - **No change needed.**

### Fixes on the generation side

1. **`pattern_refs` 3.1.4.** A vessel's `layout` reference, which is `images[0]` in the request, is now two drawings side by side:
   - a **side elevation**: the wall's bands bottom to top at their round shares, with a front face and foreshortened flanks;
   - a **top outline** with the twin's exact side count (a hexagon for market-basket-small, a circle for the key basket).

   `technical_rules["vessel"]` holds the gate's own wall model (`pattern_refs.vessel_spec` ← `visual.vessel.vessel_models`), and the rules sheet lists it.
2. **`flux_prompt` 2.3.0.** For vessels, the COUNTS section states the facts below, all derived from the CIR by the gate's own rule. It goes into every frame built from the certified rules, both anchors and lifestyle.
   - the palette as id → hex;
   - the side count;
   - base rounds, then wall rounds;
   - band order with rounds and share;
   - the number of contrast bands;
   - the plain rim.

   market-basket-small now reads: *"yarn colours exactly and only cream #FAF6EB, wine #6E1F2A …; seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners …; the base is 10 flat rounds in cream …; the wall rises straight from it in exactly 12 rounds; … bands from the base up are, in this order: 4 rounds of cream #FAF6EB (33%); 2 rounds of wine #6E1F2A (17%); 1 round of cream (8%); 2 rounds of wine (17%); 3 rounds of cream (25%); so exactly 2 contrast bands …; the top rim is the plain last round in cream: no braid, roll, border or edging …"*

### Gate checks: verdicts

| check | verdict | numbers |
|---|---|---|
| `basket:palette` | **Wrong measurement, fixed.** It was the only colour check with no illumination correction and no two-colour-mix rule. | Owner hero frame 5fc4ac77 (visibly cream + wine): **47 %** coverage before (FAIL, floor 85 %). After the gate's own bounded gain and mix rule: **94 % (PASS)**. The floor stays 85 % and OFF_PALETTE_DE stays 22. |
| `basket:wall_bands` | **Correct rule, wrong input; fixed by the same change.** | Same frame: before `[off, cream, off, wine, cream, wine, cream, off]`; after `[cream, wine, cream, wine, cream]`, the CIR's order. It still FAILs on share: about three cream rounds between the stripes against the CIR's one, in a 3/4 view. That FAIL is correct. |
| `basket:sides` | **Correct, unchanged.** | The cause was the circular reference image, fixed above. |
| `basket:rim` | Correct, unchanged. | |

The reference these checks compare against is correct: `vessel_models(cir)` from the certified CIR and twin, with palette `cir.colors`.

Raw, uncorrected palette coverage on all 7 owner frames, measured on a centre box of the basket wall: 16–63 %. After the gate's correction and mix rule: 86–97 %. Six of the seven have busy backgrounds, so the vessel mask reads them UNKNOWN anyway ("background is not one plain surface"). That is expected: the vessel anchor check is for plain product-only views.

**Not loosened.** A substituted colourway still FAILs: yellow/navy reads 0 % coverage, and wine swapped for green FAILs (tests). I considered adding a cluster-centre FAIL and rejected it. On textured photos the dark colour's cluster collects the stitch shadows: the owner's "wine" centre measured #5F3F3A. So that test would measure stitch gaps, not yarn colour. The centre distances are now recorded as evidence, unjudged.

### Pinned by tests

- The request (product-only, top and side) carries the layout reference byte-for-byte as `images[0]`, with resolution `2k` and aspect `1:1`.
- The expected output is ≥ 2000 px, and 16 × US$0.10 ≤ US$2.50.
- The prompt states the exact palette, bands, sides and wall rounds, equal to `vessel_models`. The round key basket is told "circle" and "4 contrast bands".
- The layout's side elevation reads the CIR's band order, and its top outline counts 6 corners with the gate's own `corner_count`.
- A shaded, correctly coloured wall passes palette and bands, and its raw reading is under the floor. Wrong colourways fail.

### Not done / unknown

- **No live FLUX call.** No paid call was authorised for this branch. Whether the new references and prompt lift the pass rate is UNKNOWN until the next production run.
- **Existing runs.** In-flight vessel runs hold references built at pattern-refs 3.1.3. The generator re-renders references and refuses a mismatch, so an exhausted run needs a restart (new references) to benefit. The run cap and budget are unchanged.

## Task B: Images page showed nothing

**Root cause.** `api.get()` resolves `{data, stale, fetchedAt}`, while POST resolves the body. `views/images.js` read `board.products` off the envelope, which is undefined, so it rendered `[]`: an empty "Visual evidence for" dropdown and an empty "Gallery production" list. The same bug hit `imagesCard`, `experimentCard`, `wardrobe` and `experiments`. `_visual_studio.js` read `.canonical` and the evidence off the envelope too.

**Fix.**
- Both views unwrap every GET.
- `image_production.status_board` lists every Launch-0 listing and every listing with runs or candidates. Before, only the 8 LAUNCH0_SLUGS were listed, so market-basket-small runs were invisible.
- Each product has:
  - `runs`: every run, with its state, blocked reason, spend and update time;
  - for each run, every candidate frame: thumbnail via the existing `/api/cc/images/candidates/{id}/image`, `technical_status`, `outcome`, codes, failed checks and size.
  - Owner `#owner` candidate sets appear as their own run.
- The page renders each run as a collapsible block with a thumbnail grid.
- The service-worker shell version moves `cc-shell-v47` → `v48`, so browsers fetch the fixed JS.

## Files

- `brambleloop/src/brambleloop/visual/vessel.py`
- `brambleloop/src/brambleloop/creative/pattern_refs.py`
- `brambleloop/src/brambleloop/creative/flux_prompt.py`
- `brambleloop/src/brambleloop/visual/image_production.py`
- `brambleloop/src/brambleloop/app/command_center/static/js/views/images.js`
- `brambleloop/src/brambleloop/app/command_center/static/js/views/_visual_studio.js`
- `brambleloop/src/brambleloop/app/command_center/static/sw.js`
- `brambleloop/tests/test_images_dialin.py`
- `brambleloop/DECISION_LOG.md`
- `brambleloop/src/brambleloop/core/decision_index.json`
