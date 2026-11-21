# OWNER-GALLERY — the owner's 7 FLUX 3 basket frames through the listing gates

**Branch:** `eng/owner-gallery` (from `claude/owner-assets-basket` a981e97). Not merged and not deployed. No production row was read or written.
**Run:** 2026-11-21, locally, on a scratch database.
**Input:** `brambleloop/research/owner_assets/flux_basket_2026-11-21/` (7 PNGs).
**Machine output:** `w6/review_requests/OWNER-GALLERY.json`.
**Decisions:** D-OWNER-NO-RENDER-LABELS and D-ENG-OWNER-GALLERY-1.

## Verdict

**None of the 7 frames is certified. No listing set was issued, and nothing was written as a listing asset.**

Three independent deterministic findings each refuse the set on their own:

| # | Finding | Frames | Kind |
|---|---|---|---|
| 1 | **Resolution.** Each frame is 896 to 1024 px on its long side. The listing floor is 2000 px on each side (`candidate_gates.quality`, from Etsy's facts on file). | all 7 | deterministic, real gate |
| 2 | **Stripe placement contradicts the CIR.** The CIR's wall, bottom to top, is cream 4 rounds, wine 2, cream **1**, wine 2, cream 3 (rounds 11 to 22). Every frame shows two wine stripes, as the CIR does, but with a wide cream band between them: **22 to 30 % of the wall** against the CIR's **8 %** (1 of 12 rounds). Each stripe is also thinner than the CIR's 2-round band. | all 7 | deterministic measurement on a judge-pointed strip (stub pointer) |
| 3 | **Scale.** Held by Laura, the basket reads **about 24 to 25 cm** across, against the CIR's 16.0 cm (+50 % and +55 %; the tolerance is ±40 %). | f37f518e, 7b132c05 | deterministic arithmetic on stub boxes |

The other frames could not be measured for scale: they contain no listed anchor object. Measured or not, they read visibly larger than 16 cm against the dresser, the books and the vase. On a scene frame, "unmeasured" blocks certification, as it does for a generated frame.

## Product match

The frames match **`market-basket-small` 1.3.0** ("Crochet Hexagonal Bread Basket"), release `c4aa14a0…`, certified in the scratch chain through the real `gate.certify` and `assets.build`. Its twin gives:
- 16.0 cm across the points;
- 13.9 cm across the flats;
- 8.7 cm tall;
- 60 stitches per round, so 10 per side, with 6 sides;
- cream `#FAF6EB` and wine `#6E1F2A`;
- a plain cream top round, with no edging.

The listing identity is "Hexagonal Bread Basket", kitchen and home, **not merchandised to children** (D-W4-OWNER-BASKET-IDENTITY).

## Per-file verdicts

Statuses below are from `owner_frames.ingest` on the real chain:
- `RealJudges` are the production judges. Vision is unfunded locally, so their vision readings are UNKNOWN, as production's are today.
- The `stub_pointer` supplies the scale and wall-strip boxes. It is a builder's reading of each frame, labelled as one; code does the measuring.

"UNM" means UNMEASURED, which never counts as PASS.

| File | sha256 (16) | Slot | Quality | Stripes (cream gap, CIR 8 %) | Scale | Fidelity / motif / realism | Laura gates | Verdict |
|---|---|---|---|---|---|---|---|---|
| 5fc4ac77 | b2c968bbb599af3b | hero (plain) | **FAIL** 1024×1024 | **FAIL** 26 % | N/A (plain, no props) | UNM | n/a | **REFUSED** |
| 2fb50fed | 5fec052b5bbf36ec | colour_context | **FAIL** 912×1152 | **FAIL** 26 % | UNM (no listed anchor) | UNM | n/a | **REFUSED** |
| 0394c9ef | 7fba90cd1f968a8a | lifestyle | **FAIL** 896×1132 | **FAIL** 30 % | UNM (required here) | UNM | n/a | **REFUSED** |
| 7fe9128f | d167c384b4c5784a | angle | **FAIL** 912×1152 | **FAIL** 24 % | UNM | UNM | n/a | **REFUSED** |
| 6c6539b4 | 30778caedade04d0 | detail | **FAIL** 912×1152 | **FAIL** 27 % | UNM | UNM | n/a | **REFUSED** |
| f37f518e | 881c178d66486e2b | size (Laura) | **FAIL** 912×1152 | **FAIL** 23 % | **FAIL** ≈25 cm, +55 % | UNM | identity, body, outfit, publication: UNM | **REFUSED** |
| 7b132c05 | 7da9b35423fcf795 | size, alternate (Laura) | **FAIL** 912×1152 | **FAIL** 22 % | **FAIL** ≈24 cm, +50 % | UNM | identity, body, outfit, publication: UNM | **REFUSED** |

Gates every frame passed:
- `role`: each slot's job admits the medium.
- `provenance`: provider and model recorded; never a photograph.
- `alt_text`: no label, no render wording, no made-sample claim.

Gates every frame failed or could not pass:
- `exception_route` FAILs, because structural fidelity and motif fidelity are UNKNOWN.
- `cir_references` is UNM. No generated-gallery run has prepared the release's CIR reference renders, and the owner did not condition on them.
- The set check `campaign_consistency` is UNM: 15 frame pairs were not judged against each other.

The 54 blockers are listed by file, gate and reason in `OWNER-GALLERY.json`.

### Stripe measurements

Each value is the share of the wall, bottom to top, measured by `owner_frames.bands_in_column`. Every frame has 2 stripes, as the CIR does. The middle cream band is the failure.

| File | Measured | CIR |
|---|---|---|
| 5fc4ac77 | cream 23 % · wine 12 % · **cream 26 %** · wine 13 % · cream 26 % | 33 · 17 · **8** · 17 · 25 |
| 2fb50fed | middle cream **26 %** | 8 % |
| 0394c9ef | middle cream **30 %** | 8 % |
| 7fe9128f | middle cream **24 %** | 8 % |
| 6c6539b4 | middle cream **27 %** | 8 % |
| f37f518e | middle cream **23 %** | 8 % |
| 7b132c05 | middle cream **22 %** | 8 % |

The method is the same on every frame:
1. The judge points at a narrow strip on the face toward the camera, from the base to the top of the rim.
2. Code white-balances the strip to its brightest rows.
3. Code labels each row by its nearest CIR colour in CIELAB.
4. Code compares the band sequence and shares with `vessel.vessel_models(cir)`, within `vessel.SHARE_REL_MAX` (35 %).

Perspective scales one face's bands alike, so the ratio holds in three-quarter views. The tolerance is far from deciding these frames: the worst band is off by 165 to 264 %.

### Scale measurements (the two Laura frames)

Anchor: `"adult head, chin to crown"`, 22 cm. This anchor was added in this change and is a stated anthropometric assumption, not a measurement of the model.

| File | Head (chin to crown) | Basket long side | Implied size | CIR | Result |
|---|---|---|---|---|---|
| f37f518e | 211 px | 238 px | 24.8 cm | 16.0 cm | **+55 %, FAIL** |
| 7b132c05 | 211 px | 231 px | 24.1 cm | 16.0 cm | **+50 %, FAIL** |

To fit the CIR, the basket would need to be about 0.73 head-heights across. It is about 1.1.

### What a stub stood in for, and what a paid judge would read

- **Stub pointer.** Builder-read boxes (frame grids in the session scratchpad) for:
  - the scale anchor and product, on the two Laura frames;
  - the wall strip, on all 7.

  The first pass of wall strips ran onto the wood below the base on three frames, or caught the inner wall above the rim on two. Those were corrected by reading each strip's row profile. The corrected strips agree across all 7 frames.
- **UNKNOWN for lack of a funded vision judge or the qualified identity method:**
  - product fidelity against the CIR anchor (no release anchor exists for this basket, so it is UNKNOWN even with vision);
  - motif fidelity;
  - realism and anatomy;
  - Laura identity and body proportions (the ENG-VIS-IDENTITY method is not qualified for production);
  - Laura's per-image publication approval;
  - the pairwise item consistency.

  Funding the judges would not rescue the set: findings 1 and 2 are pixel facts.
- **Builder's visual reading, not a gate result** (the deterministic rim check needs a level side view, which none of the frames is):
  - The rim is a braided, rope-like edging. The CIR works a plain final round of single crochet, so this is likely `INVENTED_EDGING`.
  - About 13 stitch columns per flat on the hero (measured stitch period 34 px). The CIR has 10.
  - All frames show a six-sided vessel and the CIR's two colours.

### Merchandising (not a gate here; for the owner)

Every scene frame is a **nursery**: a nursing chair, a wooden toy train and children's books. 0394c9ef is filled with **baby booties, nappies and a teething ring**. The owner's 2026-10-27 decision (D-W4-OWNER-BASKET-IDENTITY) positions this basket as kitchen and home, removes nursery and baby-product claims, and says it is "not merchandised to a child". Main or the owner should decide whether frames that sell it as nursery storage are admissible. No code gate reads scene content for audience today.

## Owner order: what was done

"NO FLUX PHOTOS WILL SAY RENDERING. Everything is supposed to look real. Do not add labels."
- **No label or watermark.** The owner's bytes are stored and judged unchanged. test_3 checks the stored sha256.
- **Alt text describes the scene**, built from the CIR. Example: "Hexagonal crochet basket in cream with two wine stripes, on a wooden dresser, seen from above to show the inside."
  - It never says render or rendering, never calls the image a photograph, and never claims a made sample (`owner_frames.buyer_text_problems`).
  - It is checked at intake, and again in `release_gates.generated_listing_set` before any certificate is issued.
- **Internal provenance is still recorded**, and no buyer surface reads it:
  - the `images.owner_frame_received` audit: sha256, generator `FLUX 3 (BFL dashboard, owner-reported)`, model, Laura `laura-r2-a42aeac7`, actor;
  - the candidate row: `ai_generated_owner_submitted`, `_route.supplied_by: owner`;
  - the asset claims: `is_photograph: False`, `supplied_by: owner`;
  - the `visual_truth` lineage.
- **Unchanged, flagged for main:**
  - The listing-description AI disclosure in copy. It is not a photo label and the order did not name it.
  - The factory-generated route's alt text, which opens with `CONCEPT_LABEL` ("Illustrative concept image, AI-assisted; …"). It contains no "rendering", but it is a label. Applying the order to factory FLUX frames as well is main's call.
  - `SAMPLE_PHOTO_REQUIRED` (D-OWNER-NO-SAMPLE) still blocks publication. These frames cannot satisfy it and are never presented as a sample photo.

## How to get a certifiable owner set

These are the gates the frames must pass, not a lowering of them:
1. Export at **2048 px or larger** on each side.
2. Draw the **CIR's wall**: wine rounds 15 and 16, cream round 17, wine rounds 18 and 19. That gives two 2-round wine bands separated by a single cream round, in the upper half of the wall, with 3 cream rounds above.
3. Give a **plain top round**, not a braided edge.
4. Show it at **16 cm across the points**: a little over half a 27 cm dinner plate, or about three quarters of a head-height across when held.
5. Condition on the release's **CIR reference renders**. The factory's generated-gallery route prepares them (`creative.pattern_refs`).
6. Fund the vision judge, so fidelity, motif and realism can be read.
7. Use the qualified Laura identity method, so the identity gates can be read.
8. Use a kitchen or home scene.

## Code

- **`brambleloop/src/brambleloop/visual/owner_frames.py`** (new). Contents:
  - `ingest(db, slug, version, files, actor="owner")`;
  - `buyer_text_problems` and `check_listing_copy`;
  - `alt_text` and `product_phrase`, which take their words from the CIR;
  - `stripe_layout` and `bands_in_column`;
  - `product_scale`.
- `visual/scale.py`: the head anchor, and `setting` in the prompt and the result.
- `visual/gallery_persist.write_frames`: `extra_claims` (`supplied_by` only).
- `visual/image_production.record_candidate`: `_route.supplied_by`.
- `publish/release_gates.generated_listing_set`: re-checks an owner selection's alt text and certifies with it.
- `brambleloop/scripts/owner_gallery_review.py`: the local run that produced this report.
- `brambleloop/tests/test_owner_gallery.py` (new), on the ENG-VIS-GALLERY world. It proves:
  1. a scale contradiction is refused and nothing is written;
  2. an owner set certifies exactly like a generated set (same jobs, kinds and order);
  3. no buyer alt text or label says rendering, the bytes are unchanged, and a tampered selection is refused by the listing set;
  4. provenance is recorded: candidate row, asset claims, receipt audit and `visual_truth` lineage;
  5. made-sample copy is refused, and honest negations pass;
  6. the stripe layout is measured against the CIR.

Test results are in BUILD_STATE (2026-11-21 OWNER-GALLERY entry).
