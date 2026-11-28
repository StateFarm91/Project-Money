# MANUAL-METHOD-COMPARISON: the owner's October 28 FLUX 3 hand method vs the factory

Branch `eng/manual-method`, from `46908fe66` (19i31, production). Date 2026-11-28 (UTC).
Not deployed. No paid call was made: every request below was built by the factory's real code
with the stub renderer, and each FLUX 3 body was produced by the real
`gateway.images._request_for` and passed `flux_contract.validate_request`.

**Sources.** The owner's handoff (README plus ten images: PDF page screenshots 32841, 32843,
32845 and 32847; product master 32861, 1536x1536; lifestyle 32865, 1216x1536; styled nursery
32867, 1216x1536; Laura canonicals 31584, 31585 and 31586). The handoff calls itself a
reconstruction. The prompts are reconstructed rather than recovered, and the seed, the
settings and the intermediate frames are unknown. Its prompts are treated below as the
specification of the method, not as historical transcripts. The release is **Crochet
Hexagonal Storage Basket v1.2.0** = CIR `market-basket-medium@1.2.0` (`launch0.cir_for(
"basket_medium", "1.2.0")`, release `1c9b59d4ca1a3d86...`). Its round-by-round facts match
the handoff exactly: cream R14-21, wine R22-23, cream R24-27, wine R28-29, cream R30-35;
base R1-13 to 78 sts; 20.8 cm across the points, 15.9 cm tall.

**What I saw in the owner's images.** 32861 is a good commercial master. It has a hexagonal
basket, two level wine bands with a dominant cream ground, matte cotton single-crochet texture,
light oak, an ivory wall and a three-quarter elevated camera. It is **not** a stitch-perfect
match: its rim is a braided, rope-like rolled edge, which the pattern (a plain final sc round)
and the handoff's own prompt ("no ... rolled rim") both forbid. 32865 and 32867 inherit that
rim. 32865 has the exact outfit and the canonical identity. 32867 has scaled nursery props, the
same room and the same basket. None of the three images proves fidelity. They show *commercial
attractiveness with near-correct product*, which is what the factory lacks.

## 1. The factory's request construction, stage by stage (production 46908fe66)

Line numbers are for `origin/claude/repository-setup-nc9x6o` at 46908fe66.

### 1a. product_generation (the anchor / product frame)

- The orchestrator, `visual/image_production.py:1822-1870`, calls `_generate` with
  `role=product_anchor`. For a vessel it first makes a second paid render,
  `product_anchor_side` (`:1840-1862`). The briefs are hard-coded (`:1852`, `:1864`) and are
  ignored by the generator for these roles.
- The generator is `creative/flux3_generator.py:429-432`, which calls
  `image_stages.product_only(rel, view=...)`.
- References come from `creative/image_stages.py:330-402`, `campaign_references(...,
  features_laura=False)`. Positions 1-4 are the four **CIR diagram renders** in the order
  layout, texture, chart (detail), rules (`:342`). The certified-PDF pages then fill the free
  slots, here 6 of them (`:351-360`), chosen by `pdf_page_refs.select`.
- The prompt comes from `creative/flux_prompt.py:392-529` (builder 2.4.0) and has nine pinned
  sections: REFERENCES, PRODUCT v3 ("shown exactly as in image 1 (complete product ...)", where
  image 1 is the **layout diagram**), COUNTS (`vessel_counts`, `:305-345`, ending "show the
  wall exactly as in the side elevation on the left of the layout reference"), NEGATIVES,
  SCENE, REALISM and STATUS (the disclosure text is sent to the image model).
- The scene is `image_stages.py:617-672`, `product_scene`. The ground is a **mid-tone taupe**
  (#7A746C), and the prompt says "no white, cream or pale background" (`flat_lay_environment`,
  `:609-614`). A flat product is a diagnostic flat lay. A vessel gets a straight-down top view
  and an eye-level side view (`VESSEL_TOP_SCENE`, `VESSEL_SIDE_SCENE`).
- Size: `PRODUCT_SIZE` "2048x2048" (`:72`). `gateway/images.py:656-668` sends
  `aspect_ratio` "1:1" and `resolution` "2k" (`bfl3_aspect` `:524`, `bfl3_tier` `:510`),
  with `grounding` false and the 10 references in `images`. **Seed**: FLUX 3 Image has no seed
  field (`gateway/flux_contract.py`, `ABSENT_FIELDS`). The receipt records the provider's seed
  when the provider reports one, and None otherwise.
- Reference sizes for the basket: layout 1800x900, texture 1008x408, chart 1384x1768, rules
  1500x1600, and each PDF page 1187x1536 (`pdf_page_refs.LONG_SIDE_PX`).

### 1b. Correction ("repair") of the product frame

- After a fidelity FAIL, `fidelity_gate` sends the run back to `product_generation`
  (`image_production.py:1899`). `_repair_for` (`:4386`) turns the failure codes into
  `repair_routes` directives (`:1837`).
- The generator, `flux3_generator.py:421-425` and `:618-624`, **appends the directives'
  negatives to the rules and regenerates from scratch** through the same `product_only`
  call. The failed candidate is never sent. Nothing is edited.

### 1c. Lifestyle and Laura frames

- The orchestrator, `image_production.py:2040-2072`, takes the owner-method branch
  (ENG-IMAGES-LAURA): `refs = _refs_with_bytes() + lr + [pf]` (`:2070`), where `pf` is
  `_accepted_product_frame` (`:4091`), the ACCEPTED anchor's bytes re-read and re-hashed.
- The generator, `flux3_generator.py:447-449` and `_owner_method` `:522-546`, re-checks the
  frame against the anchor lookup's PASS. The stage is `image_stages.owner_method_lifestyle`
  (`:819-847`). The references are **exactly** canonical face, torso and body, then the
  accepted product frame (`owner_method_references`, `:797-816`). No room, no campaign and no
  outfit image are sent.
- The prompt is the same nine-section builder, with every product role aliased to image 4
  (`_OWNER_METHOD_ALIAS`). The text therefore reads "the fabric looks exactly like image 4 ...
  Stitch placement is charted in image 4; the technical rules are in image 4". The scene is
  `laura_home.scene_for(slug)` (the basket category maps to **the kitchen**), and the framing
  is the default "the whole product in frame". The output is square 2048 at 2k.
- **For a vessel, the "accepted product frame" is the straight-down top view on taupe.** That
  is the gate's diagnostic view. It shows the rim polygon and the inside, and not the wall
  bands. This is the only product image the lifestyle request receives.

### 1d. Styled product-only frames and the remaining roles

- Every non-Laura role of the seven-frame FLUX campaign goes through
  `image_production.py:2075`: hero (DESIRE), colour_context, angle, detail and size
  (`visual/shot_plans.py` `FLUX_BRIEFS[small_goods]`, `:319-362`; `flux_campaign_for`
  `:379-411`).
- The generator, `flux3_generator.py:490-509`, calls `S.variant(rel, anchor, "styled_scene",
  edit)` for **every** product-only role, whatever its job. The edit is
  `"<room cue>. <brief>"`.
- References come from `image_stages.variant` (`:935-976`) through `campaign_references(...,
  leading=[("base", anchor)])`: the four CIR diagrams first, the anchor as **image 5**, then
  the PDF pages. `room_references.scene_supplement` returns nothing, because
  `visual/room_refs/MANIFEST.json` has no approved room, so no room or campaign image is ever
  sent.
- The prompt is "Edit image 5: move the scene to a different, natural setting suited to the
  product: in the kitchen ... hero: the finished piece in use, styled table or shelf. Keep
  everything else in image 5 unchanged". In practice it asks FLUX to keep a straight-down taupe
  diagnostic frame unchanged while moving it into a kitchen. The prompt also carries the full
  diagram-led PRODUCT, COUNTS and NEGATIVES sections. Environment and pose fall back to "a
  calm, natural setting" and "the product at rest".
- `visual/prompt_assembly.py` is **not on this request path**. It is used by
  `gallery_planner` (the wardrobe scenes), not by `image_production` or the FLUX generator.

## 2. Side by side, per stage

| | Manual (Oct 28) | Factory (46908fe66) |
|---|---|---|
| **Product: references, order** | PDF pages 1, 2, 4 as screenshots (plus the dashboard basket draft). No diagram. | CIR layout, texture, chart and rules diagrams at 1-4, then 6 PDF pages at 5-10. |
| **Product: prompt spec** | Prose: hexagonal, 20.8 / 18 / 15.9 cm, worsted cotton, 5 mm, sc; "8 cream rounds, 2 wine rounds, 4 cream, 2 wine, 6 cream"; "plain final cream round". | Spec-sheet sections: "shown exactly as in image 1 (layout)", percentages of wall height, change rounds, "these are checked", STATUS/disclosure text. Facts correct; the authority is the diagram. |
| **Product: negatives** | Short and concrete: no stripe, braid, rolled rim, handles, lining, fringe, label, person, props, text, second basket. | Long and legalistic (knitting, ribbing, edging, colour-change rounds), plus "anatomically correct hands" in a product-only frame. |
| **Product: composition and camera** | Light natural oak, warm ivory wall, diffused window light, three-quarter slightly elevated, centred, editorial. | Mid-tone taupe, "no white, cream or pale background", straight down (top) or eye-level edge-on (side): a measurement photo. |
| **Product: aspect** | Square (1536 upload). | Square 2048 / 2k. |
| **Correction** | "Edit the first image only to fix X": the candidate, then the PDF pages. | Full regeneration with extra negatives; the failed candidate is never sent. |
| **Lifestyle: references** | Face, torso, body, accepted master (+ room scene for continuity). | Face, torso, body, accepted anchor = **top-down taupe diagnostic** for a vessel. No room. |
| **Lifestyle: prompt** | Positional map ("Reference 4 is the exact finished basket"); explicit outfit; nursery scene; action ("places a folded muslin into the basket"); size (~21 cm, not a hamper); two wine bands, no handles; no infant. | Nine sections; "charted in image 4; the technical rules are in image 4" (aliases); kitchen; brief as pose; "the whole product in frame". |
| **Lifestyle: aspect** | Portrait 1216x1536. | Square 2048. |
| **Styled product-only** | Master + accepted room scene; nursery props scaled to 21 cm; three-quarter; no person or child. | Edit of the diagnostic anchor at image 5, behind 4 diagrams; room cue only; generic "styled table or shelf"; no props. |
| **Master reuse** | One accepted master conditions every derivative. | Yes for Laura frames (the same bytes); styled frames edit it; for a vessel the master is the wrong view. |
| **Room / campaign continuity** | The accepted scene is carried into the next image. | None: no approved room exists, and no accepted frame is ever reused as a campaign reference. |
| **Receipt** | No record. | Ordered input hashes, prompt *ref* and text sha256, size, seed (if reported), cost and output sha. Not the prompt text, aspect or tier. |

## 3. Answers

**(a) Diagram-like product frames: yes.** The product stage sends four rendered CIR diagrams at
positions 1-4, and the prompt makes image 1 (the layout diagram) the authority: "shown exactly
as in image 1", "show the wall exactly as in the side elevation on the left of the layout
reference". The PDF pages fill only the slots left over. The scene then asks for a
mid-grey measurement ground and an orthographic camera. Everything in the request points at a
technical drawing. The owner sent the PDF page screenshots and a rich prose spec.

**(b) Accepted master bytes in lifestyle: yes, the exact bytes** (`_accepted_product_frame`,
re-hashed, and the generator re-checks the PASS). Two weaknesses remain. For a vessel those
bytes are the top-down diagnostic view on taupe, which never shows the wall bands. The
lifestyle frame was meant to carry the bands, so for the basket the factory's "master" is the
least useful product image it owns. The prompt also tells FLUX the stitch chart and the
technical rules are "in image 4".

**(c) Styled non-Laura route: it receives the master, but as an edit base in position 5,
behind the four diagrams, and with no room or campaign reference.** No room image is approved
(the manifest is empty). No accepted frame (lifestyle or styled) is ever handed on as a
continuity reference. Every product-only role (hero, angle, detail, size, colour_context) is
the same "move the scene" edit of the diagnostic frame.

**(d) Repair: full regeneration, not an edit.** `flux3_generator._repair_negatives` adds
negatives and `product_only` renders again from the same references. The failed candidate,
which may be 90% right, is discarded. The hand method kept everything that was right and
named the defect.

**(e) Prompt specificity and art direction: specific, but not art-directed.** The factory
states more facts than the owner did (exact hexes, percentages, change rounds). It never says
*what picture to make*. There is no surface the buyer would want, no light, no camera that
sells, no props and no action, and its "do not" list is as long as its "do". The section that
reaches FLUX also includes publication-policy text ("STATUS: ... candidate only ... not
published until ... owner approves"), which the image model cannot use. The owner's prompts
are shorter, ordered as *what it is, how it is coloured, what it must not have, how it is
photographed*, and every sentence describes the picture.

### Top reasons the factory underperformed

1. **The diagrams lead.** Four CIR renders at positions 1-4, named "the authority", push
   toward drawing-like, flat, orthographic output. The PDF pages, the owner's actual
   method, were an afterthought in leftover slots.
2. **The product frame is a measurement photo, not a master.** The taupe ground and
   straight-down or edge-on cameras serve the gate and produce a frame nobody would put in a
   gallery. That same frame is then the "master" every derivative is conditioned on.
3. **No correction loop.** A near-miss is thrown away and re-rolled from scratch, three
   attempts deep, with longer negative lists each time. Under the per-gallery money cap this is
   what exhausted the basket runs (`product_generation:budget:exhausted`, BUILD_STATE
   VERIFY-REFS).
4. **No continuity.** No room or campaign image is ever sent, so every frame invents its own
   room. Styled frames "edit" a diagnostic frame into a scene instead of photographing the
   master in a scene.
5. **Prompts are compliance documents.** The prompts contain correct facts and no art
   direction, and they include disclosure and publication text that the image model cannot
   act on.

## 4. What changed (manual_method/1, Phase 2)

The changes are in the existing factory only. No parallel system was added.

- **`creative/manual_method.py` (new).** It builds the prompt from the release's own
  `pattern_refs.technical_rules` and nothing else. Four new pinned prompt sections are added:
  `image.flux3.manual.{product,correction,lifestyle,styled}@1`.
  - The prose spec covers the shape (polygon, vessel, flat), the size note, the fibre, hook,
    stitches and gauge, and the final round.
  - The **colour sequence is written out in working order**:
    - basket: "Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream
      rounds, 2 wine rounds, 6 cream rounds";
    - coaster: "from the centre outward: 5 cream rounds, 1 wine round, 1 cream round";
    - blanket: mixed stitch heights, so the surface is said to follow the chart, and the
      worked order "6 cream rows, then (2 ink rows, 2 cream rows) repeated 21 times ..." is
      stated without claiming plain stripes.
  - The negatives are the release's own.
  - The editorial composition chooses a light surface and backdrop at least 25 CIE delta E
    from every yarn colour. For cream and wine that is light natural oak against a warm greige
    wall. The contrast reason the gate had for taupe is kept.
  - Every prompt has a positional map ("Image 1 is ...").
- **`creative/image_stages.py`.**
  - `manual_product`: certified PDF pages **only** (the CIR renders still bind the release in
    `_bind`, are still recorded on the candidate for the CIR-reference gate, and are not
    transmitted). Square 2k, no person, no room.
  - With `correction_base`, `manual_product` makes a **targeted edit**: image 1 is the failed
    candidate, the PDF pages follow, and the defect is named from the gate's codes
    (`manual_method.defects_for`).
  - `manual_lifestyle`: canonical three, then the accepted master, then a vessel's accepted
    side view, then the approved room or campaign reference. The outfit comes from the
    reservation and is preserved across the listing.
  - `manual_styled`: the master first, the side view, then the room or campaign reference.
    Each job gets its own shot (hero, colour_context, angle, detail, size). Props suit the
    category and room (nursery storage gets nappies and muslins; a coaster gets a mug), are
    scaled to the certified size, and never include a crocheted or knitted item (the house
    rule).
- **`creative/flux3_generator.py` `_manual`.**
  - Routes the anchor, side, Laura lifestyle and product-only roles to those stages. The
    stage-A identity anchor, the stage-D lifestyle edits and a release with **no certified
    PDF** keep the earlier route, which is recorded.
  - A correction with no nameable defect is a fresh master, never a blind edit.
  - For the manual method the candidate records the exact prompt text.
- **`visual/image_production.py`.**
  - `_correction_refs` hands the failed anchor, and the side view judged with it, as
    `correction_base` when a repair is routed.
  - `_accepted_product_side` gives every derivative the accepted pair's side view.
  - `manual_extras` gives every frame after the lifestyle frame the accepted lifestyle frame
    as `campaign_reference`, for room and campaign continuity. It is keyed into the owner-method
    replay digest.
  - **The generation-method version gains `image_method: manual_method/1`**, so every run
    FAILed under the earlier method is method-redrive eligible once, under the existing caps
    (D-RESTART-PER-METHOD).
- **Receipt.** On every stage, `_run` now also records `prompt_text`, `aspect_ratio`,
  `resolution` and `provider_attempt`. It already recorded the model, the ordered input hashes,
  the size, the seed (if reported), the cost and the output sha256. The manual stages add
  `method`, `view`, `correction_of` and `correction_codes`. The orchestrator's candidate row
  keeps the plan attempt.
- **Unchanged.**
  - Every gate, including fidelity, the vessel top/side views (the gate's cameras are kept;
    only the art direction changed), the CIR-reference count, identity, outfit and lifestyle
    evidence.
  - Every cap: MAX_SPEND_CAD_PER_GALLERY 2.00, 12 calls, 3 attempts per role, the paid-provider
    gate, the 2k per-call reservation and the daily ceilings.
  - The listing floor of 2000 px.
  - Laura's canonical files and laura-r2-a42aeac7.

### Not done, and why

- **Portrait lifestyle (manual 1216x1536).** I did not ship this, and it needs an owner
  decision. The listing floor (`candidate_gates.quality`) requires 2000 px on **each** side.
  FLUX 3 documents a 4 MP output bound when references are sent (`flux_contract`
  `EXACT_MAX_PIXELS_WITH_REFERENCES`), so a 4:5 frame with references tops out at about
  1832x2290, which is below the floor. Meeting both requires either a 4k-tier portrait with
  references (undocumented, US$0.607 per image) or a floor of 2000 on the long side only. I
  did not weaken the gate. Lifestyle stays square 2k.
- **A three-quarter editorial product master.** The hand master is three-quarter elevated.
  The vessel gate reads a straight-down top view and an eye-level side view, and the 19i32
  lane is calibrating those gates against the owner's images. Until a three-quarter view is a
  gate-readable anchor, the master keeps the gate's cameras with the hand method's references,
  spec, surface and light. The commercial three-quarter hero is the styled `hero` role, which
  now photographs the master (and side view) in the campaign room.
- **Live proof.** These results come from stub-provider traces only. After a deploy, the
  candidate viewer (eng/candidate-viewer, another lane) is how the real frames get inspected.
  The method redrive fires once per FAILed run, under the existing caps.

---

# Appendix A. Factory requests before this change (hexagon basket v1.2.0), verbatim

## A. market-basket-medium@1.2.0, production method

`market-basket-medium@1.2.0` (Crochet Hexagonal Storage Basket), release `1c9b59d4ca1a3d865129e310c58f67726efdd44386162e5fcdfa75d9ca43597e`, PDF sha256 `d6eaa32617e11f3f...` (the US edition rendered locally by `publish.pdf.build_pattern_pdf`). Production code at 46908fe66 with the stub renderer. In production the `base` / product-frame image is the 2048x2048 accepted anchor; the stub writes a 128x128 placeholder, which is why it shows 128x128 here. No approved room image exists (`visual/room_refs/MANIFEST.json` is empty), so no room reference appears. The `product_anchor` row after `product_anchor_side` is the factory's repair (a regeneration with added negatives for WRONG_COLOUR_LAYOUT); its reference list is identical to the first attempt.


### product_anchor (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_layout | 1800x900 | `ce64760e61c31780` |
| 2 | product_texture | 1008x408 | `8439874a9b66cc09` |
| 3 | product_detail | 1384x1768 | `bc6a0de709fd3f86` |
| 4 | product_rules | 1500x1600 | `b703661f5d3c0bc5` |
| 5 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 6 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 7 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 8 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 9 | pdf_finished | 1187x1536 | `ecc6779f78467429` |
| 10 | pdf_instructions | 1187x1536 | `b6888ec8866de621` |

Prompt, verbatim:

```text
REFERENCE IMAGES, in order of authority: image 1 = certified product layout; image 2 = certified crochet stitch texture close-up; image 3 = certified stitch chart; image 4 = certified technical rules; image 5 = page of the certified pattern PDF: the cover, with the finished product; image 6 = page of the certified pattern PDF: the materials and colour key (the exact yarn colours); image 7 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 8 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 9 = page of the certified pattern PDF: the finished design; image 10 = page of the certified pattern PDF: the written rounds, each round's colour named. The canonical Laura images decide who she is; the certified product images decide what the product is; any supplementary image adds context only and never overrides either.
PRODUCT: Crochet Hexagonal Storage Basket, Brambleloop market-basket-medium version 1.2.0 (release 1c9b59d4ca1a3d86), shown exactly as in image 1 (complete product: shape, colour placement, proportions and pieces). The fabric looks exactly like image 2: real crochet, its stitch posts, top loops and crossings at true scale. Stitch placement is charted in image 3; the technical rules are in image 4. Construction: joined_rounds, gauge 12.5 sts x 13.8 rows per 10 cm in sc. Pieces: 1 in total: basket x1 (in rounds, 20.8 x 15.9 cm). Size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall, at the stated gauge. Computed, not yet measured on a worked sample. Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the increases stack, and walls rising from it. Colours, exact and only these: cream #FAF6EB, wine #6E1F2A. Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each (rounds 22-23 and rounds 28-29); 2 stripes in total, no others. Edge: the top rim is the plain final round (round 35) of sc in cream #FAF6EB, with no edging. Stitches: inc, sc. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.
COUNT AND PROPORTION (these are checked): yarn colours exactly and only cream #FAF6EB, wine #6E1F2A (no other colour, tint or shade of yarn); seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners, no more and no fewer; the base is 13 flat rounds in cream, underneath; the wall rises straight from it in exactly 22 rounds; the wall's horizontal colour bands from the base up are, in this order: 8 rounds of cream #FAF6EB (36% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 4 rounds of cream #FAF6EB (18% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 6 rounds of cream #FAF6EB (27% of the wall height); so exactly 2 contrast bands on the wall, each running all the way round, level and unbroken; the top rim is the plain last round in cream: no braid, roll, border or edging; show the wall exactly as in the side elevation on the left of the layout reference.
THIS FABRIC MUST NOT SHOW: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30; a missing, moved, merged or recoloured contrast band: wine #6E1F2A rounds 22-23; wine #6E1F2A rounds 28-29 -- each is worked into the fabric as charted and is part of the design, never an edging, border or trim, and must be shown.
SCENE (product-only top view, standing): The product alone; no person.  Environment: a plain, matte, mid-tone taupe surface (#7A746C), at least 25 colour-distance units (CIE delta E) from every yarn colour so every edge and band of the piece separates from it; soft, even daylight; no white, cream or pale background. Pose and action: the product standing upright on its base, empty, seen from directly above: the camera points straight down at 90 degrees over the centre of the opening, so the outline of the image is the top rim and every corner of it is visible; you see the rim, the inside of the walls and the base, and none of the outside of the wall; nothing inside it. As in the base-from-above drawing on the right of the layout reference. The certified PDF's cover and gallery pictures show this basket from above at an angle, with the inside visible: use them for its colours, stripes and shape only, never for the camera angle of this image.. Framing: the whole object in frame with a margin on every side, the camera square above its centre, so every side of the outline can be counted.
REALISM: a natural, believable photograph, not an illustration or a render. Real handmade crochet with visible yarn texture and true stitch scale; natural light; anatomically correct hands with five fingers; no over-staged composition. The product is in focus and fully legible for its role. No text, logos, watermarks or borders in the image.
STATUS: This is an AI-generated image of a certified Brambleloop product and will be disclosed as AI-generated wherever it is shown. It is a candidate only: it is not published until identity, bust and body proportion, outfit, Product Truth, anatomy, realism and disclosure checks pass and the owner approves.
```

### product_anchor_side (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_layout | 1800x900 | `ce64760e61c31780` |
| 2 | product_texture | 1008x408 | `8439874a9b66cc09` |
| 3 | product_detail | 1384x1768 | `bc6a0de709fd3f86` |
| 4 | product_rules | 1500x1600 | `b703661f5d3c0bc5` |
| 5 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 6 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 7 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 8 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 9 | pdf_finished | 1187x1536 | `ecc6779f78467429` |
| 10 | pdf_instructions | 1187x1536 | `b6888ec8866de621` |

Prompt, verbatim:

```text
REFERENCE IMAGES, in order of authority: image 1 = certified product layout; image 2 = certified crochet stitch texture close-up; image 3 = certified stitch chart; image 4 = certified technical rules; image 5 = page of the certified pattern PDF: the cover, with the finished product; image 6 = page of the certified pattern PDF: the materials and colour key (the exact yarn colours); image 7 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 8 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 9 = page of the certified pattern PDF: the finished design; image 10 = page of the certified pattern PDF: the written rounds, each round's colour named. The canonical Laura images decide who she is; the certified product images decide what the product is; any supplementary image adds context only and never overrides either.
PRODUCT: Crochet Hexagonal Storage Basket, Brambleloop market-basket-medium version 1.2.0 (release 1c9b59d4ca1a3d86), shown exactly as in image 1 (complete product: shape, colour placement, proportions and pieces). The fabric looks exactly like image 2: real crochet, its stitch posts, top loops and crossings at true scale. Stitch placement is charted in image 3; the technical rules are in image 4. Construction: joined_rounds, gauge 12.5 sts x 13.8 rows per 10 cm in sc. Pieces: 1 in total: basket x1 (in rounds, 20.8 x 15.9 cm). Size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall, at the stated gauge. Computed, not yet measured on a worked sample. Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the increases stack, and walls rising from it. Colours, exact and only these: cream #FAF6EB, wine #6E1F2A. Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each (rounds 22-23 and rounds 28-29); 2 stripes in total, no others. Edge: the top rim is the plain final round (round 35) of sc in cream #FAF6EB, with no edging. Stitches: inc, sc. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.
COUNT AND PROPORTION (these are checked): yarn colours exactly and only cream #FAF6EB, wine #6E1F2A (no other colour, tint or shade of yarn); seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners, no more and no fewer; the base is 13 flat rounds in cream, underneath; the wall rises straight from it in exactly 22 rounds; the wall's horizontal colour bands from the base up are, in this order: 8 rounds of cream #FAF6EB (36% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 4 rounds of cream #FAF6EB (18% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 6 rounds of cream #FAF6EB (27% of the wall height); so exactly 2 contrast bands on the wall, each running all the way round, level and unbroken; the top rim is the plain last round in cream: no braid, roll, border or edging; show the wall exactly as in the side elevation on the left of the layout reference.
THIS FABRIC MUST NOT SHOW: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30; a missing, moved, merged or recoloured contrast band: wine #6E1F2A rounds 22-23; wine #6E1F2A rounds 28-29 -- each is worked into the fabric as charted and is part of the design, never an edging, border or trim, and must be shown.
SCENE (product-only side view, standing): The product alone; no person.  Environment: a plain, matte, mid-tone taupe surface (#7A746C), at least 25 colour-distance units (CIE delta E) from every yarn colour so every edge and band of the piece separates from it; soft, even daylight; no white, cream or pale background. Pose and action: the product standing upright on its base, empty, seen from the side with the camera level with the middle of the wall and looking horizontally; one flat side facing the camera. The opening and the inside are NOT visible: the top rim is seen edge-on as a straight line, exactly as in the side elevation on the left of the layout reference and in the PDF's schematic drawing. The certified PDF's cover and gallery pictures show this basket from above at an angle, with the inside visible: use them for its colours, stripes and shape only, never for the camera angle of this image.. Framing: the whole object in frame with a margin on every side, from the base to the top of the rim, so every colour band up the wall and the rim can be counted.
REALISM: a natural, believable photograph, not an illustration or a render. Real handmade crochet with visible yarn texture and true stitch scale; natural light; anatomically correct hands with five fingers; no over-staged composition. The product is in focus and fully legible for its role. No text, logos, watermarks or borders in the image.
STATUS: This is an AI-generated image of a certified Brambleloop product and will be disclosed as AI-generated wherever it is shown. It is a candidate only: it is not published until identity, bust and body proportion, outfit, Product Truth, anatomy, realism and disclosure checks pass and the owner approves.
```

### product_anchor (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_layout | 1800x900 | `ce64760e61c31780` |
| 2 | product_texture | 1008x408 | `8439874a9b66cc09` |
| 3 | product_detail | 1384x1768 | `bc6a0de709fd3f86` |
| 4 | product_rules | 1500x1600 | `b703661f5d3c0bc5` |
| 5 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 6 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 7 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 8 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 9 | pdf_finished | 1187x1536 | `ecc6779f78467429` |
| 10 | pdf_instructions | 1187x1536 | `b6888ec8866de621` |

Prompt, verbatim:

```text
REFERENCE IMAGES, in order of authority: image 1 = certified product layout; image 2 = certified crochet stitch texture close-up; image 3 = certified stitch chart; image 4 = certified technical rules; image 5 = page of the certified pattern PDF: the cover, with the finished product; image 6 = page of the certified pattern PDF: the materials and colour key (the exact yarn colours); image 7 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 8 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 9 = page of the certified pattern PDF: the finished design; image 10 = page of the certified pattern PDF: the written rounds, each round's colour named. The canonical Laura images decide who she is; the certified product images decide what the product is; any supplementary image adds context only and never overrides either.
PRODUCT: Crochet Hexagonal Storage Basket, Brambleloop market-basket-medium version 1.2.0 (release 1c9b59d4ca1a3d86), shown exactly as in image 1 (complete product: shape, colour placement, proportions and pieces). The fabric looks exactly like image 2: real crochet, its stitch posts, top loops and crossings at true scale. Stitch placement is charted in image 3; the technical rules are in image 4. Construction: joined_rounds, gauge 12.5 sts x 13.8 rows per 10 cm in sc. Pieces: 1 in total: basket x1 (in rounds, 20.8 x 15.9 cm). Size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall, at the stated gauge. Computed, not yet measured on a worked sample. Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the increases stack, and walls rising from it. Colours, exact and only these: cream #FAF6EB, wine #6E1F2A. Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each (rounds 22-23 and rounds 28-29); 2 stripes in total, no others. Edge: the top rim is the plain final round (round 35) of sc in cream #FAF6EB, with no edging. Stitches: inc, sc. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.
COUNT AND PROPORTION (these are checked): yarn colours exactly and only cream #FAF6EB, wine #6E1F2A (no other colour, tint or shade of yarn); seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners, no more and no fewer; the base is 13 flat rounds in cream, underneath; the wall rises straight from it in exactly 22 rounds; the wall's horizontal colour bands from the base up are, in this order: 8 rounds of cream #FAF6EB (36% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 4 rounds of cream #FAF6EB (18% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 6 rounds of cream #FAF6EB (27% of the wall height); so exactly 2 contrast bands on the wall, each running all the way round, level and unbroken; the top rim is the plain last round in cream: no braid, roll, border or edging; show the wall exactly as in the side elevation on the left of the layout reference.
THIS FABRIC MUST NOT SHOW: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30; wall bands in the wrong order or count; a missing, moved, merged or recoloured contrast band: wine #6E1F2A rounds 22-23; wine #6E1F2A rounds 28-29 -- each is worked into the fabric as charted and is part of the design, never an edging, border or trim, and must be shown.
SCENE (product-only top view, standing): The product alone; no person.  Environment: a plain, matte, mid-tone taupe surface (#7A746C), at least 25 colour-distance units (CIE delta E) from every yarn colour so every edge and band of the piece separates from it; soft, even daylight; no white, cream or pale background. Pose and action: the product standing upright on its base, empty, seen from directly above: the camera points straight down at 90 degrees over the centre of the opening, so the outline of the image is the top rim and every corner of it is visible; you see the rim, the inside of the walls and the base, and none of the outside of the wall; nothing inside it. As in the base-from-above drawing on the right of the layout reference. The certified PDF's cover and gallery pictures show this basket from above at an angle, with the inside visible: use them for its colours, stripes and shape only, never for the camera angle of this image.. Framing: the whole object in frame with a margin on every side, the camera square above its centre, so every side of the outline can be counted.
REALISM: a natural, believable photograph, not an illustration or a render. Real handmade crochet with visible yarn texture and true stitch scale; natural light; anatomically correct hands with five fingers; no over-staged composition. The product is in focus and fully legible for its role. No text, logos, watermarks or borders in the image.
STATUS: This is an AI-generated image of a certified Brambleloop product and will be disclosed as AI-generated wherever it is shown. It is a candidate only: it is not published until identity, bust and body proportion, outfit, Product Truth, anatomy, realism and disclosure checks pass and the owner approves.
```

### hero (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_layout | 1800x900 | `ce64760e61c31780` |
| 2 | product_texture | 1008x408 | `8439874a9b66cc09` |
| 3 | product_detail | 1384x1768 | `bc6a0de709fd3f86` |
| 4 | product_rules | 1500x1600 | `b703661f5d3c0bc5` |
| 5 | base | 128x128 | `2e34865716f9b543` |
| 6 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 7 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 8 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 9 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 10 | pdf_finished | 1187x1536 | `ecc6779f78467429` |

Prompt, verbatim:

```text
REFERENCE IMAGES, in order of authority: image 1 = certified product layout; image 2 = certified crochet stitch texture close-up; image 3 = certified stitch chart; image 4 = certified technical rules; image 5 = the image to edit; image 6 = page of the certified pattern PDF: the cover, with the finished product; image 7 = page of the certified pattern PDF: the materials and colour key (the exact yarn colours); image 8 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 9 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 10 = page of the certified pattern PDF: the finished design. The canonical Laura images decide who she is; the certified product images decide what the product is; any supplementary image adds context only and never overrides either.
PRODUCT: Crochet Hexagonal Storage Basket, Brambleloop market-basket-medium version 1.2.0 (release 1c9b59d4ca1a3d86), shown exactly as in image 1 (complete product: shape, colour placement, proportions and pieces). The fabric looks exactly like image 2: real crochet, its stitch posts, top loops and crossings at true scale. Stitch placement is charted in image 3; the technical rules are in image 4. Construction: joined_rounds, gauge 12.5 sts x 13.8 rows per 10 cm in sc. Pieces: 1 in total: basket x1 (in rounds, 20.8 x 15.9 cm). Size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall, at the stated gauge. Computed, not yet measured on a worked sample. Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the increases stack, and walls rising from it. Colours, exact and only these: cream #FAF6EB, wine #6E1F2A. Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each (rounds 22-23 and rounds 28-29); 2 stripes in total, no others. Edge: the top rim is the plain final round (round 35) of sc in cream #FAF6EB, with no edging. Stitches: inc, sc. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.
COUNT AND PROPORTION (these are checked): yarn colours exactly and only cream #FAF6EB, wine #6E1F2A (no other colour, tint or shade of yarn); seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners, no more and no fewer; the base is 13 flat rounds in cream, underneath; the wall rises straight from it in exactly 22 rounds; the wall's horizontal colour bands from the base up are, in this order: 8 rounds of cream #FAF6EB (36% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 4 rounds of cream #FAF6EB (18% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 6 rounds of cream #FAF6EB (27% of the wall height); so exactly 2 contrast bands on the wall, each running all the way round, level and unbroken; the top rim is the plain last round in cream: no braid, roll, border or edging; show the wall exactly as in the side elevation on the left of the layout reference.
THIS FABRIC MUST NOT SHOW: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30; a missing, moved, merged or recoloured contrast band: wine #6E1F2A rounds 22-23; wine #6E1F2A rounds 28-29 -- each is worked into the fabric as charted and is part of the design, never an edging, border or trim, and must be shown.
SCENE (styled_scene): Edit image 5: move the scene to a different, natural setting suited to the product: in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash. hero: the finished piece in use, styled table or shelf. Keep everything else in image 5 unchanged. The product alone; no person.  Environment: a calm, natural setting suited to the product. Pose and action: the product at rest, whole piece visible. Framing: the whole product in frame.
REALISM: a natural, believable photograph, not an illustration or a render. Real handmade crochet with visible yarn texture and true stitch scale; natural light; anatomically correct hands with five fingers; no over-staged composition. The product is in focus and fully legible for its role. No text, logos, watermarks or borders in the image.
STATUS: This is an AI-generated image of a certified Brambleloop product and will be disclosed as AI-generated wherever it is shown. It is a candidate only: it is not published until identity, bust and body proportion, outfit, Product Truth, anatomy, realism and disclosure checks pass and the owner approves.
```

### colour_context (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_layout | 1800x900 | `ce64760e61c31780` |
| 2 | product_texture | 1008x408 | `8439874a9b66cc09` |
| 3 | product_detail | 1384x1768 | `bc6a0de709fd3f86` |
| 4 | product_rules | 1500x1600 | `b703661f5d3c0bc5` |
| 5 | base | 128x128 | `2e34865716f9b543` |
| 6 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 7 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 8 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 9 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 10 | pdf_finished | 1187x1536 | `ecc6779f78467429` |

Prompt, verbatim:

```text
REFERENCE IMAGES, in order of authority: image 1 = certified product layout; image 2 = certified crochet stitch texture close-up; image 3 = certified stitch chart; image 4 = certified technical rules; image 5 = the image to edit; image 6 = page of the certified pattern PDF: the cover, with the finished product; image 7 = page of the certified pattern PDF: the materials and colour key (the exact yarn colours); image 8 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 9 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 10 = page of the certified pattern PDF: the finished design. The canonical Laura images decide who she is; the certified product images decide what the product is; any supplementary image adds context only and never overrides either.
PRODUCT: Crochet Hexagonal Storage Basket, Brambleloop market-basket-medium version 1.2.0 (release 1c9b59d4ca1a3d86), shown exactly as in image 1 (complete product: shape, colour placement, proportions and pieces). The fabric looks exactly like image 2: real crochet, its stitch posts, top loops and crossings at true scale. Stitch placement is charted in image 3; the technical rules are in image 4. Construction: joined_rounds, gauge 12.5 sts x 13.8 rows per 10 cm in sc. Pieces: 1 in total: basket x1 (in rounds, 20.8 x 15.9 cm). Size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall, at the stated gauge. Computed, not yet measured on a worked sample. Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the increases stack, and walls rising from it. Colours, exact and only these: cream #FAF6EB, wine #6E1F2A. Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each (rounds 22-23 and rounds 28-29); 2 stripes in total, no others. Edge: the top rim is the plain final round (round 35) of sc in cream #FAF6EB, with no edging. Stitches: inc, sc. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.
COUNT AND PROPORTION (these are checked): yarn colours exactly and only cream #FAF6EB, wine #6E1F2A (no other colour, tint or shade of yarn); seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners, no more and no fewer; the base is 13 flat rounds in cream, underneath; the wall rises straight from it in exactly 22 rounds; the wall's horizontal colour bands from the base up are, in this order: 8 rounds of cream #FAF6EB (36% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 4 rounds of cream #FAF6EB (18% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 6 rounds of cream #FAF6EB (27% of the wall height); so exactly 2 contrast bands on the wall, each running all the way round, level and unbroken; the top rim is the plain last round in cream: no braid, roll, border or edging; show the wall exactly as in the side elevation on the left of the layout reference.
THIS FABRIC MUST NOT SHOW: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30; a missing, moved, merged or recoloured contrast band: wine #6E1F2A rounds 22-23; wine #6E1F2A rounds 28-29 -- each is worked into the fabric as charted and is part of the design, never an edging, border or trim, and must be shown.
SCENE (styled_scene): Edit image 5: move the scene to a different, natural setting suited to the product: in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash. the finished piece(s) flat-lay, every piece visible, plain surface. Keep everything else in image 5 unchanged. The product alone; no person.  Environment: a calm, natural setting suited to the product. Pose and action: the product at rest, whole piece visible. Framing: the whole product in frame.
REALISM: a natural, believable photograph, not an illustration or a render. Real handmade crochet with visible yarn texture and true stitch scale; natural light; anatomically correct hands with five fingers; no over-staged composition. The product is in focus and fully legible for its role. No text, logos, watermarks or borders in the image.
STATUS: This is an AI-generated image of a certified Brambleloop product and will be disclosed as AI-generated wherever it is shown. It is a candidate only: it is not published until identity, bust and body proportion, outfit, Product Truth, anatomy, realism and disclosure checks pass and the owner approves.
```

### lifestyle (stage `lifestyle_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | laura_face | 1024x1024 | `a42aeac72ba5733e` |
| 2 | laura_torso | 1024x1024 | `afe6191fb4c68d0a` |
| 3 | laura_body | 1024x1024 | `f32bac686cba46c7` |
| 4 | product_candidate | 128x128 | `2e34865716f9b543` |

Prompt, verbatim:

```text
REFERENCE IMAGES, in order of authority: image 1 = canonical Laura face (neutral portrait); image 2 = canonical Laura torso and bust; image 3 = canonical Laura full body; image 4 = AI-generated product-only flat lay of this exact product (verified against the pattern). The canonical Laura images decide who she is; the certified product images decide what the product is; any supplementary image adds context only and never overrides either.
IDENTITY: the woman is Laura, exactly the person in image 1, image 2 and image 3. These three references fix her identity and anatomy ONLY, never her clothing. Preserve her face from image 1: eyes, eyebrows, nose, lips, cheekbones, jawline, freckles, apparent age, hairline and her highlighted wavy hair. Preserve face, bust fullness and projection, shoulders, waist, hips, legs and silhouette exactly as in image 2 and image 3; never flatten, reduce, exaggerate or redesign the bust; clothing fits and drapes over these approved proportions. Keep her full-body silhouette from image 3: waist-to-hip and legs. REPLACE ALL clothing from the reference images with the selected outfit: top/dress: soft sage-green blouse; bottoms: cream tailored trousers; do not reuse the reference beige trousers, ivory/cream tops or tan sandals. Do not change her identity, body shape or proportions.
LAURA MUST NOT WEAR: the beige trousers from the reference images; the ivory or cream top from the reference images; the tan sandals from the reference images; any garment copied from the canonical reference images.
PRODUCT: Crochet Hexagonal Storage Basket, Brambleloop market-basket-medium version 1.2.0 (release 1c9b59d4ca1a3d86), shown exactly as in image 4 (complete product: shape, colour placement, proportions and pieces). The fabric looks exactly like image 4: real crochet, its stitch posts, top loops and crossings at true scale. Stitch placement is charted in image 4; the technical rules are in image 4. Construction: joined_rounds, gauge 12.5 sts x 13.8 rows per 10 cm in sc. Pieces: 1 in total: basket x1 (in rounds, 20.8 x 15.9 cm). Size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall, at the stated gauge. Computed, not yet measured on a worked sample. Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the increases stack, and walls rising from it. Colours, exact and only these: cream #FAF6EB, wine #6E1F2A. Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each (rounds 22-23 and rounds 28-29); 2 stripes in total, no others. Edge: the top rim is the plain final round (round 35) of sc in cream #FAF6EB, with no edging. Stitches: inc, sc. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.
COUNT AND PROPORTION (these are checked): yarn colours exactly and only cream #FAF6EB, wine #6E1F2A (no other colour, tint or shade of yarn); seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners, no more and no fewer; the base is 13 flat rounds in cream, underneath; the wall rises straight from it in exactly 22 rounds; the wall's horizontal colour bands from the base up are, in this order: 8 rounds of cream #FAF6EB (36% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 4 rounds of cream #FAF6EB (18% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 6 rounds of cream #FAF6EB (27% of the wall height); so exactly 2 contrast bands on the wall, each running all the way round, level and unbroken; the top rim is the plain last round in cream: no braid, roll, border or edging; show the wall exactly as in the side elevation on the left of the layout reference.
THIS FABRIC MUST NOT SHOW: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30; a missing, moved, merged or recoloured contrast band: wine #6E1F2A rounds 22-23; wine #6E1F2A rounds 28-29 -- each is worked into the fabric as charted and is part of the design, never an edging, border or trim, and must be shown.
SCENE (lifestyle): Laura with the product. She wears top/dress: soft sage-green blouse; bottoms: cream tailored trousers; the outfit is the same in every image of this listing. Environment: Laura's own home (laura-home-v1), the kitchen: a modest two-storey 1990s family house in a Canadian suburb: white-oak-look laminate floors, warm off-white walls, white painted trim, standard double-hung windows with plain linen curtains. shaker cabinets painted soft sage, a butcher-block counter, a white subway tile backsplash, the window over the sink looking onto a back yard. a round pine table with four mismatched chairs by the window. Lived in: a kettle and two mugs by the sink; a fruit bowl with a few apples. In the frame: a mug of tea set down beside the product mid-morning. Light: soft morning daylight from the window over the sink, no flash. Camera: a standing three-quarter view. A believable, modest family home with ordinary belongings, natural photographic composition. No other crocheted or knitted item is in the scene besides the product.. Pose and action: Laura using the finished piece in everyday life at home. Framing: the whole product in frame.
REALISM: a natural, believable photograph, not an illustration or a render. Real handmade crochet with visible yarn texture and true stitch scale; natural light; anatomically correct hands with five fingers; no over-staged composition. The product is in focus and fully legible for its role. No text, logos, watermarks or borders in the image.
STATUS: This is an AI-generated image of a certified Brambleloop product and will be disclosed as AI-generated wherever it is shown. It is a candidate only: it is not published until identity, bust and body proportion, outfit, Product Truth, anatomy, realism and disclosure checks pass and the owner approves.
```

### angle (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_layout | 1800x900 | `ce64760e61c31780` |
| 2 | product_texture | 1008x408 | `8439874a9b66cc09` |
| 3 | product_detail | 1384x1768 | `bc6a0de709fd3f86` |
| 4 | product_rules | 1500x1600 | `b703661f5d3c0bc5` |
| 5 | base | 128x128 | `2e34865716f9b543` |
| 6 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 7 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 8 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 9 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 10 | pdf_finished | 1187x1536 | `ecc6779f78467429` |

Prompt, verbatim:

```text
REFERENCE IMAGES, in order of authority: image 1 = certified product layout; image 2 = certified crochet stitch texture close-up; image 3 = certified stitch chart; image 4 = certified technical rules; image 5 = the image to edit; image 6 = page of the certified pattern PDF: the cover, with the finished product; image 7 = page of the certified pattern PDF: the materials and colour key (the exact yarn colours); image 8 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 9 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 10 = page of the certified pattern PDF: the finished design. The canonical Laura images decide who she is; the certified product images decide what the product is; any supplementary image adds context only and never overrides either.
PRODUCT: Crochet Hexagonal Storage Basket, Brambleloop market-basket-medium version 1.2.0 (release 1c9b59d4ca1a3d86), shown exactly as in image 1 (complete product: shape, colour placement, proportions and pieces). The fabric looks exactly like image 2: real crochet, its stitch posts, top loops and crossings at true scale. Stitch placement is charted in image 3; the technical rules are in image 4. Construction: joined_rounds, gauge 12.5 sts x 13.8 rows per 10 cm in sc. Pieces: 1 in total: basket x1 (in rounds, 20.8 x 15.9 cm). Size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall, at the stated gauge. Computed, not yet measured on a worked sample. Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the increases stack, and walls rising from it. Colours, exact and only these: cream #FAF6EB, wine #6E1F2A. Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each (rounds 22-23 and rounds 28-29); 2 stripes in total, no others. Edge: the top rim is the plain final round (round 35) of sc in cream #FAF6EB, with no edging. Stitches: inc, sc. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.
COUNT AND PROPORTION (these are checked): yarn colours exactly and only cream #FAF6EB, wine #6E1F2A (no other colour, tint or shade of yarn); seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners, no more and no fewer; the base is 13 flat rounds in cream, underneath; the wall rises straight from it in exactly 22 rounds; the wall's horizontal colour bands from the base up are, in this order: 8 rounds of cream #FAF6EB (36% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 4 rounds of cream #FAF6EB (18% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 6 rounds of cream #FAF6EB (27% of the wall height); so exactly 2 contrast bands on the wall, each running all the way round, level and unbroken; the top rim is the plain last round in cream: no braid, roll, border or edging; show the wall exactly as in the side elevation on the left of the layout reference.
THIS FABRIC MUST NOT SHOW: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30; a missing, moved, merged or recoloured contrast band: wine #6E1F2A rounds 22-23; wine #6E1F2A rounds 28-29 -- each is worked into the fabric as charted and is part of the design, never an edging, border or trim, and must be shown.
SCENE (styled_scene): Edit image 5: move the scene to a different, natural setting suited to the product: in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash. the finished piece from another angle showing its construction: base, joins or back. Keep everything else in image 5 unchanged. The product alone; no person.  Environment: a calm, natural setting suited to the product. Pose and action: the product at rest, whole piece visible. Framing: the whole product in frame.
REALISM: a natural, believable photograph, not an illustration or a render. Real handmade crochet with visible yarn texture and true stitch scale; natural light; anatomically correct hands with five fingers; no over-staged composition. The product is in focus and fully legible for its role. No text, logos, watermarks or borders in the image.
STATUS: This is an AI-generated image of a certified Brambleloop product and will be disclosed as AI-generated wherever it is shown. It is a candidate only: it is not published until identity, bust and body proportion, outfit, Product Truth, anatomy, realism and disclosure checks pass and the owner approves.
```

### detail (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_layout | 1800x900 | `ce64760e61c31780` |
| 2 | product_texture | 1008x408 | `8439874a9b66cc09` |
| 3 | product_detail | 1384x1768 | `bc6a0de709fd3f86` |
| 4 | product_rules | 1500x1600 | `b703661f5d3c0bc5` |
| 5 | base | 128x128 | `2e34865716f9b543` |
| 6 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 7 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 8 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 9 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 10 | pdf_finished | 1187x1536 | `ecc6779f78467429` |

Prompt, verbatim:

```text
REFERENCE IMAGES, in order of authority: image 1 = certified product layout; image 2 = certified crochet stitch texture close-up; image 3 = certified stitch chart; image 4 = certified technical rules; image 5 = the image to edit; image 6 = page of the certified pattern PDF: the cover, with the finished product; image 7 = page of the certified pattern PDF: the materials and colour key (the exact yarn colours); image 8 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 9 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 10 = page of the certified pattern PDF: the finished design. The canonical Laura images decide who she is; the certified product images decide what the product is; any supplementary image adds context only and never overrides either.
PRODUCT: Crochet Hexagonal Storage Basket, Brambleloop market-basket-medium version 1.2.0 (release 1c9b59d4ca1a3d86), shown exactly as in image 1 (complete product: shape, colour placement, proportions and pieces). The fabric looks exactly like image 2: real crochet, its stitch posts, top loops and crossings at true scale. Stitch placement is charted in image 3; the technical rules are in image 4. Construction: joined_rounds, gauge 12.5 sts x 13.8 rows per 10 cm in sc. Pieces: 1 in total: basket x1 (in rounds, 20.8 x 15.9 cm). Size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall, at the stated gauge. Computed, not yet measured on a worked sample. Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the increases stack, and walls rising from it. Colours, exact and only these: cream #FAF6EB, wine #6E1F2A. Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each (rounds 22-23 and rounds 28-29); 2 stripes in total, no others. Edge: the top rim is the plain final round (round 35) of sc in cream #FAF6EB, with no edging. Stitches: inc, sc. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.
COUNT AND PROPORTION (these are checked): yarn colours exactly and only cream #FAF6EB, wine #6E1F2A (no other colour, tint or shade of yarn); seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners, no more and no fewer; the base is 13 flat rounds in cream, underneath; the wall rises straight from it in exactly 22 rounds; the wall's horizontal colour bands from the base up are, in this order: 8 rounds of cream #FAF6EB (36% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 4 rounds of cream #FAF6EB (18% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 6 rounds of cream #FAF6EB (27% of the wall height); so exactly 2 contrast bands on the wall, each running all the way round, level and unbroken; the top rim is the plain last round in cream: no braid, roll, border or edging; show the wall exactly as in the side elevation on the left of the layout reference.
THIS FABRIC MUST NOT SHOW: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30; a missing, moved, merged or recoloured contrast band: wine #6E1F2A rounds 22-23; wine #6E1F2A rounds 28-29 -- each is worked into the fabric as charted and is part of the design, never an edging, border or trim, and must be shown.
SCENE (styled_scene): Edit image 5: move the scene to a different, natural setting suited to the product: in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash. close-up of the stitch texture of the finished piece. Keep everything else in image 5 unchanged. The product alone; no person.  Environment: a calm, natural setting suited to the product. Pose and action: the product at rest, whole piece visible. Framing: the whole product in frame.
REALISM: a natural, believable photograph, not an illustration or a render. Real handmade crochet with visible yarn texture and true stitch scale; natural light; anatomically correct hands with five fingers; no over-staged composition. The product is in focus and fully legible for its role. No text, logos, watermarks or borders in the image.
STATUS: This is an AI-generated image of a certified Brambleloop product and will be disclosed as AI-generated wherever it is shown. It is a candidate only: it is not published until identity, bust and body proportion, outfit, Product Truth, anatomy, realism and disclosure checks pass and the owner approves.
```

### size (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_layout | 1800x900 | `ce64760e61c31780` |
| 2 | product_texture | 1008x408 | `8439874a9b66cc09` |
| 3 | product_detail | 1384x1768 | `bc6a0de709fd3f86` |
| 4 | product_rules | 1500x1600 | `b703661f5d3c0bc5` |
| 5 | base | 128x128 | `2e34865716f9b543` |
| 6 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 7 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 8 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 9 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 10 | pdf_finished | 1187x1536 | `ecc6779f78467429` |

Prompt, verbatim:

```text
REFERENCE IMAGES, in order of authority: image 1 = certified product layout; image 2 = certified crochet stitch texture close-up; image 3 = certified stitch chart; image 4 = certified technical rules; image 5 = the image to edit; image 6 = page of the certified pattern PDF: the cover, with the finished product; image 7 = page of the certified pattern PDF: the materials and colour key (the exact yarn colours); image 8 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 9 = page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts); image 10 = page of the certified pattern PDF: the finished design. The canonical Laura images decide who she is; the certified product images decide what the product is; any supplementary image adds context only and never overrides either.
PRODUCT: Crochet Hexagonal Storage Basket, Brambleloop market-basket-medium version 1.2.0 (release 1c9b59d4ca1a3d86), shown exactly as in image 1 (complete product: shape, colour placement, proportions and pieces). The fabric looks exactly like image 2: real crochet, its stitch posts, top loops and crossings at true scale. Stitch placement is charted in image 3; the technical rules are in image 4. Construction: joined_rounds, gauge 12.5 sts x 13.8 rows per 10 cm in sc. Pieces: 1 in total: basket x1 (in rounds, 20.8 x 15.9 cm). Size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall, at the stated gauge. Computed, not yet measured on a worked sample. Shape: a vessel with a flat 6-sided (hexagon) base: exactly 6 corners where the increases stack, and walls rising from it. Colours, exact and only these: cream #FAF6EB, wine #6E1F2A. Colour layout: cream #FAF6EB ground with 2 wine stripes of 2 rounds each (rounds 22-23 and rounds 28-29); 2 stripes in total, no others. Edge: the top rim is the plain final round (round 35) of sc in cream #FAF6EB, with no edging. Stitches: inc, sc. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.
COUNT AND PROPORTION (these are checked): yarn colours exactly and only cream #FAF6EB, wine #6E1F2A (no other colour, tint or shade of yarn); seen from above the rim is a hexagon: exactly 6 flat sides and 6 corners, no more and no fewer; the base is 13 flat rounds in cream, underneath; the wall rises straight from it in exactly 22 rounds; the wall's horizontal colour bands from the base up are, in this order: 8 rounds of cream #FAF6EB (36% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 4 rounds of cream #FAF6EB (18% of the wall height); 2 rounds of wine #6E1F2A (9% of the wall height); 6 rounds of cream #FAF6EB (27% of the wall height); so exactly 2 contrast bands on the wall, each running all the way round, level and unbroken; the top rim is the plain last round in cream: no braid, roll, border or edging; show the wall exactly as in the side elevation on the left of the layout reference.
THIS FABRIC MUST NOT SHOW: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30; a missing, moved, merged or recoloured contrast band: wine #6E1F2A rounds 22-23; wine #6E1F2A rounds 28-29 -- each is worked into the fabric as charted and is part of the design, never an edging, border or trim, and must be shown.
SCENE (styled_scene): Edit image 5: move the scene to a different, natural setting suited to the product: in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash. the finished piece beside everyday objects of known size. Keep everything else in image 5 unchanged. The product alone; no person.  Environment: a calm, natural setting suited to the product. Pose and action: the product at rest, whole piece visible. Framing: the whole product in frame.
REALISM: a natural, believable photograph, not an illustration or a render. Real handmade crochet with visible yarn texture and true stitch scale; natural light; anatomically correct hands with five fingers; no over-staged composition. The product is in focus and fully legible for its role. No text, logos, watermarks or borders in the image.
STATUS: This is an AI-generated image of a certified Brambleloop product and will be disclosed as AI-generated wherever it is shown. It is a candidate only: it is not published until identity, bust and body proportion, outfit, Product Truth, anatomy, realism and disclosure checks pass and the owner approves.
```

---

# Appendix B. Requests under manual_method/1, verbatim

## B1. Hexagon basket v1.2.0

`market-basket-medium@1.2.0` (Crochet Hexagonal Storage Basket), release `1c9b59d4ca1a3d865129e310c58f67726efdd44386162e5fcdfa75d9ca43597e`, PDF sha256 `d6eaa32617e11f3f...` (the US edition rendered locally by `publish.pdf.build_pattern_pdf`). This branch (manual_method/1), same stub. The second `product_anchor` call is the correction: a targeted edit of the failed candidate for codes WRONG_COLOUR_LAYOUT and WRONG_REPEAT_COUNT. The trace generates roles in shot-plan order, so `hero` and `colour_context` run before the lifestyle frame. In production `remaining_roles` runs after `lifestyle_generation`, so every product-only role carries the campaign reference.


### product_anchor (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 2 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 3 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 4 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 5 | pdf_finished | 1187x1536 | `ecc6779f78467429` |
| 6 | pdf_instructions | 1187x1536 | `b6888ec8866de621` |

Prompt, verbatim:

```text
Create one photorealistic product visualization for Brambleloop Studio's crochet pattern listing. Image 1 is a page of the certified pattern PDF: the cover, with the finished product. Image 2 is a page of the certified pattern PDF: the materials and colour key (the exact yarn colours). Image 3 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 4 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 5 is a page of the certified pattern PDF: the finished design. Image 6 is a page of the certified pattern PDF: the written rounds, each round's colour named. Use the attached pattern pages as the authoritative instructions for the finished item; never reproduce their page layout, text, charts or drawings in the image.

The finished item is one basket: Crochet Hexagonal Storage Basket, version 1.2.0. Its flat base and its rim have 6 sides and 6 corners (hexagon); the wall is straight and upright and the top is open. Retain a visibly hexagonal silhouette. Approximate finished size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall (computed at the stated gauge, not measured on a sample). It is made from worsted cotton with a 5 mm hook in single crochet with increases, at 12.5 stitches and 13.8 rows per 10 cm. Show compact, recognisable crochet stitches and believable matte yarn fibres, not knitting, rope, plastic or woven wicker. The top ends in the pattern's ordinary cream final round: no added rim, braid, roll, border or trim.

The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant.

It must not show: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.

Photograph-style composition: the item alone on a light natural oak surface (#C9A97E) against a seamless warm greige wall (#B5ADA2), softly diffused window light, clean natural styling, centred, the entire item in frame with a margin on every side. Camera: straight down at 90 degrees over the centre of the opening of the empty item standing on its base, so the rim's whole outline and every corner are visible; nothing inside it. Sharp fabric detail, realistic texture and depth, natural shadows. No person, hands, props, text, logo, watermark, collage or second basket. Output one square image. The product must faithfully represent the pattern rather than an embellished alternative.
```

### product_anchor_side (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 2 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 3 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 4 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 5 | pdf_finished | 1187x1536 | `ecc6779f78467429` |
| 6 | pdf_instructions | 1187x1536 | `b6888ec8866de621` |

Prompt, verbatim:

```text
Create one photorealistic product visualization for Brambleloop Studio's crochet pattern listing. Image 1 is a page of the certified pattern PDF: the cover, with the finished product. Image 2 is a page of the certified pattern PDF: the materials and colour key (the exact yarn colours). Image 3 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 4 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 5 is a page of the certified pattern PDF: the finished design. Image 6 is a page of the certified pattern PDF: the written rounds, each round's colour named. Use the attached pattern pages as the authoritative instructions for the finished item; never reproduce their page layout, text, charts or drawings in the image.

The finished item is one basket: Crochet Hexagonal Storage Basket, version 1.2.0. Its flat base and its rim have 6 sides and 6 corners (hexagon); the wall is straight and upright and the top is open. Retain a visibly hexagonal silhouette. Approximate finished size: A hexagonal basket: the increases stack at six corners, so the base is a hexagon about 20.8 cm across the points and 18.0 cm across the flats, and the walls stand about 16 cm tall (computed at the stated gauge, not measured on a sample). It is made from worsted cotton with a 5 mm hook in single crochet with increases, at 12.5 stitches and 13.8 rows per 10 cm. Show compact, recognisable crochet stitches and believable matte yarn fibres, not knitting, rope, plastic or woven wicker. The top ends in the pattern's ordinary cream final round: no added rim, braid, roll, border or trim.

The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant.

It must not show: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 22, 24, 28, 30. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.

Photograph-style composition: the item alone on a light natural oak surface (#C9A97E) against a seamless warm greige wall (#B5ADA2), softly diffused window light, clean natural styling, centred, the entire item in frame with a margin on every side. Camera: level with the middle of the wall, looking horizontally at one flat side of the empty item standing on its base; the top rim is seen edge-on as a straight line and the inside is not visible, so every colour band up the wall can be read. Sharp fabric detail, realistic texture and depth, natural shadows. No person, hands, props, text, logo, watermark, collage or second basket. Output one square image. The product must faithfully represent the pattern rather than an embellished alternative.
```

### product_anchor (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | correction_base | 128x128 | `e56b6e34fca8a94d` |
| 2 | pdf_cover | 1187x1536 | `173c3fda576e4987` |
| 3 | pdf_colour_key | 1187x1536 | `2d29c457995a052b` |
| 4 | pdf_chart | 1187x1536 | `713976d4781dd0b6` |
| 5 | pdf_chart | 1187x1536 | `e02e01730686c684` |
| 6 | pdf_finished | 1187x1536 | `ecc6779f78467429` |
| 7 | pdf_instructions | 1187x1536 | `b6888ec8866de621` |

Prompt, verbatim:

```text
Edit image 1 only, to fix: the colour layout; it must read exactly: The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant; the outline; it has exactly 6 sides and 6 corners. Image 1 is the image to edit. Image 2 is a page of the certified pattern PDF: the cover, with the finished product. Image 3 is a page of the certified pattern PDF: the materials and colour key (the exact yarn colours). Image 4 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 5 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 6 is a page of the certified pattern PDF: the finished design. Image 7 is a page of the certified pattern PDF: the written rounds, each round's colour named. The remaining attachments are the original pattern instructions and the authoritative product reference. Keep the camera, lighting, background, material, silhouette and all correct details of image 1 unchanged. Preserve: Its flat base and its rim have 6 sides and 6 corners (hexagon); the wall is straight and upright and the top is open. Retain a visibly hexagonal silhouette. The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant. The top ends in the pattern's ordinary cream final round: no added rim, braid, roll, border or trim. Do not add anything or redesign the item. Return one corrected product image, square.
```

### hero (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_master | 128x128 | `e56b6e34fca8a94d` |
| 2 | product_master_side | 128x128 | `5a308291961a6247` |

Prompt, verbatim:

```text
Create a photorealistic product photograph-style image of the exact crochet basket in the product master. Image 1 is the accepted product master: the exact finished item to depict. Image 2 is the same accepted item from the side, standing. The setting: in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash. Keep the basket itself identical to the product master: Its flat base and its rim have 6 sides and 6 corners (hexagon); the wall is straight and upright and the top is open. Retain a visibly hexagonal silhouette. The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant. The top ends in the pattern's ordinary cream final round: no added rim, braid, roll, border or trim. It is a small item approximately 20.8 cm wide and 15.9 cm tall; props and furniture are scaled to it.

A three-quarter editorial composition, the item the clear subject in sharp focus and set where it lives. Brief: hero: the finished piece in use, styled table or shelf.

Style it realistically with a restrained arrangement of everyday things that fit inside it without stretching or enlarging it: a few rolled linen tea towels, a small wooden spoon and a folded cotton napkin. Keep the front and its colour layout unobstructed. No person, no hands, no child. Camera: a slightly elevated three-quarter view. Soft natural daylight, gentle background depth of field, a calm natural-home look. No text, watermark or logo. Output one square image.
```

### colour_context (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_master | 128x128 | `e56b6e34fca8a94d` |
| 2 | product_master_side | 128x128 | `5a308291961a6247` |

Prompt, verbatim:

```text
Create a photorealistic product photograph-style image of the exact crochet basket in the product master. Image 1 is the accepted product master: the exact finished item to depict. Image 2 is the same accepted item from the side, standing. The setting: in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash. Keep the basket itself identical to the product master: Its flat base and its rim have 6 sides and 6 corners (hexagon); the wall is straight and upright and the top is open. Retain a visibly hexagonal silhouette. The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant. The top ends in the pattern's ordinary cream final round: no added rim, braid, roll, border or trim. It is a small item approximately 20.8 cm wide and 15.9 cm tall; props and furniture are scaled to it.

Show the same item directly overhead on a plain natural surface, every piece visible, no props or perspective distortion. Brief: the finished piece(s) flat-lay, every piece visible, plain surface.

No props. Keep the front and its colour layout unobstructed. No person, no hands, no child. Camera: directly overhead. Soft natural daylight, gentle background depth of field, a calm natural-home look. No text, watermark or logo. Output one square image.
```

### lifestyle (stage `lifestyle_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | laura_face | 1024x1024 | `a42aeac72ba5733e` |
| 2 | laura_torso | 1024x1024 | `afe6191fb4c68d0a` |
| 3 | laura_body | 1024x1024 | `f32bac686cba46c7` |
| 4 | product_master | 128x128 | `e56b6e34fca8a94d` |
| 5 | product_master_side | 128x128 | `5a308291961a6247` |

Prompt, verbatim:

```text
Create a photorealistic lifestyle photograph-style image for Brambleloop Studio.

Image 1 is the canonical model face. Image 2 is the canonical model's natural upper-body proportions. Image 3 is the canonical model's complete body proportions and silhouette. Image 4 is the accepted product master: the exact finished item to depict. Image 5 is the same accepted item from the side, standing. Preserve the appearance established by the three model references; do not redesign the model or copy the reference outfit. The product master controls the product's shape, size, colours, colour layout and crochet texture. 

IDENTITY: the woman is Laura, exactly the person in image 1, image 2 and image 3. These three references fix her identity and anatomy ONLY, never her clothing. Preserve her face from image 1: eyes, eyebrows, nose, lips, cheekbones, jawline, freckles, apparent age, hairline and her highlighted wavy hair. Preserve face, bust fullness and projection, shoulders, waist, hips, legs and silhouette exactly as in image 2 and image 3; never flatten, reduce, exaggerate or redesign the bust; clothing fits and drapes over these approved proportions. Keep her full-body silhouette from image 3: waist-to-hip and legs. REPLACE ALL clothing from the reference images with the selected outfit: soft sage-green blouse, cream tailored trousers; do not reuse the reference beige trousers, ivory/cream tops or tan sandals. Do not change her identity, body shape or proportions.

Dress the model in soft sage-green blouse, cream tailored trousers. Natural makeup and a relaxed expression. The outfit looks like everyday home styling. Preserve this outfit in every image of this listing.

Scene: Laura's own home (laura-home-v1), the kitchen: a modest two-storey 1990s family house in a Canadian suburb: white-oak-look laminate floors, warm off-white walls, white painted trim, standard double-hung windows with plain linen curtains. shaker cabinets painted soft sage, a butcher-block counter, a white subway tile backsplash, the window over the sink looking onto a back yard. a round pine table with four mismatched chairs by the window. Lived in: a kettle and two mugs by the sink; a fruit bowl with a few apples. In the frame: a mug of tea set down beside the product mid-morning. Light: soft morning daylight from the window over the sink, no flash. Camera: a standing three-quarter view. A believable, modest family home with ordinary belongings, natural photographic composition. No other crocheted or knitted item is in the scene besides the product.

Action: Laura using the finished piece in everyday life at home. The basket remains clearly visible and in sharp focus; no fingers hide its colour layout. It is a small item approximately 20.8 cm wide and 15.9 cm tall: keep it at that real size against her hands and the furniture. Match the accepted product master; do not invent a different basket. Its flat base and its rim have 6 sides and 6 corners (hexagon); the wall is straight and upright and the top is open. Retain a visibly hexagonal silhouette. The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant. The top ends in the pattern's ordinary cream final round: no added rim, braid, roll, border or trim.

Natural hand anatomy, realistic perspective and scale. Commercial home-and-lifestyle editorial photography, softly lit. No infant, no text, no logos, no watermark. One image.
```

### angle (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_master | 128x128 | `e56b6e34fca8a94d` |
| 2 | product_master_side | 128x128 | `5a308291961a6247` |
| 3 | campaign_reference | 128x128 | `05d42f2675bcb1a4` |

Prompt, verbatim:

```text
Create a photorealistic product photograph-style image of the exact crochet basket in the product master. Image 1 is the accepted product master: the exact finished item to depict. Image 2 is the same accepted item from the side, standing. Image 3 is the approved campaign image of this listing: use it only for the location, light and styling, never for the product or the person. Use the approved room or campaign image for the same setting (in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash); it never changes the product. Keep the basket itself identical to the product master: Its flat base and its rim have 6 sides and 6 corners (hexagon); the wall is straight and upright and the top is open. Retain a visibly hexagonal silhouette. The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant. The top ends in the pattern's ordinary cream final round: no added rim, braid, roll, border or trim. It is a small item approximately 20.8 cm wide and 15.9 cm tall; props and furniture are scaled to it.

Show the exact same item from a different three-quarter angle with consistent materials, shape and colour layout. Do not redesign it. Brief: the finished piece from another angle showing its construction: base, joins or back.

No props. Keep the front and its colour layout unobstructed. No person, no hands, no child. Camera: a slightly elevated three-quarter view. Soft natural daylight, gentle background depth of field, a calm natural-home look. No text, watermark or logo. Output one square image.
```

### detail (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_master | 128x128 | `e56b6e34fca8a94d` |
| 2 | product_master_side | 128x128 | `5a308291961a6247` |
| 3 | campaign_reference | 128x128 | `05d42f2675bcb1a4` |

Prompt, verbatim:

```text
Create a photorealistic product photograph-style image of the exact crochet basket in the product master. Image 1 is the accepted product master: the exact finished item to depict. Image 2 is the same accepted item from the side, standing. Image 3 is the approved campaign image of this listing: use it only for the location, light and styling, never for the product or the person. Use the approved room or campaign image for the same setting (in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash); it never changes the product. Keep the basket itself identical to the product master: Its flat base and its rim have 6 sides and 6 corners (hexagon); the wall is straight and upright and the top is open. Retain a visibly hexagonal silhouette. The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant. The top ends in the pattern's ordinary cream final round: no added rim, braid, roll, border or trim. It is a small item approximately 20.8 cm wide and 15.9 cm tall; props and furniture are scaled to it.

A macro close-up of the same stitches: preserve the colour transitions and the final round, realistic yarn fibres, no knitted or rope texture. Brief: close-up of the stitch texture of the finished piece.

No props. Keep the front and its colour layout unobstructed. No person, no hands, no child. Camera: a slightly elevated three-quarter view. Soft natural daylight, gentle background depth of field, a calm natural-home look. No text, watermark or logo. Output one square image.
```

### size (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_master | 128x128 | `e56b6e34fca8a94d` |
| 2 | product_master_side | 128x128 | `5a308291961a6247` |
| 3 | campaign_reference | 128x128 | `05d42f2675bcb1a4` |

Prompt, verbatim:

```text
Create a photorealistic product photograph-style image of the exact crochet basket in the product master. Image 1 is the accepted product master: the exact finished item to depict. Image 2 is the same accepted item from the side, standing. Image 3 is the approved campaign image of this listing: use it only for the location, light and styling, never for the product or the person. Use the approved room or campaign image for the same setting (in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash); it never changes the product. Keep the basket itself identical to the product master: Its flat base and its rim have 6 sides and 6 corners (hexagon); the wall is straight and upright and the top is open. Retain a visibly hexagonal silhouette. The base is cream. Reading the wall from bottom to top: 8 cream rounds, 2 wine rounds, 4 cream rounds, 2 wine rounds, 6 cream rounds. Colours cream #FAF6EB, wine #6E1F2A, and no others. Exactly 2 continuous wine bands running level all the way round; the cream is dominant. The top ends in the pattern's ordinary cream final round: no added rim, braid, roll, border or trim. It is a small item approximately 20.8 cm wide and 15.9 cm tall; props and furniture are scaled to it.

Show the same item beside everyday objects of known size so its real size is clear. No unsupported size label. Brief: the finished piece beside everyday objects of known size.

Style it realistically with a restrained arrangement of everyday things that fit inside it without stretching or enlarging it: a few rolled linen tea towels, a small wooden spoon and a folded cotton napkin. Keep the front and its colour layout unobstructed. No person, no hands, no child. Camera: a slightly elevated three-quarter view. Soft natural daylight, gentle background depth of field, a calm natural-home look. No text, watermark or logo. Output one square image.
```

## B2. Hexagon coaster set (product master and correction)

`hexagon-coaster-set@1.2.1` (Hexagon Coaster Set), release `83b5db1f2cb4e9d2ce6a8011ed43278d048e4d9b60aaccc7086f0853e599534e`, PDF sha256 `ec86049c6da2d7ff...` (the US edition rendered locally by `publish.pdf.build_pattern_pdf`). Generated from the coaster's own CIR; nothing of the basket appears.


### product_anchor (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | pdf_cover | 1187x1536 | `dfd5a1b4ad14e2b8` |
| 2 | pdf_colour_key | 1187x1536 | `adc92b8a9da9cb50` |
| 3 | pdf_chart | 1187x1536 | `4a6a8358affbd3c2` |
| 4 | pdf_chart | 1187x1536 | `517d9e85811d7e82` |
| 5 | pdf_finished | 1187x1536 | `e2eac6d6c854b4dd` |
| 6 | pdf_chart_key | 1187x1536 | `5681ebd8bf69b67c` |

Prompt, verbatim:

```text
Create one photorealistic product visualization for Brambleloop Studio's crochet pattern listing. Image 1 is a page of the certified pattern PDF: the cover, with the finished product. Image 2 is a page of the certified pattern PDF: the materials and colour key (the exact yarn colours). Image 3 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 4 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 5 is a page of the certified pattern PDF: the finished design. Image 6 is a page of the certified pattern PDF: the chart key. Use the attached pattern pages as the authoritative instructions for the finished item; never reproduce their page layout, text, charts or drawings in the image.

The finished item is 4 pieces: Hexagon Coaster Set, version 1.2.1. Each piece is a flat hexagon with exactly 6 corners. Approximate finished size: A hexagon about 9.7 cm across the points and 8.4 cm across the flats (computed at the stated gauge, not measured on a sample). It is made from dk cotton with a 5 mm hook in single crochet with increases, at 14.5 stitches and 16.0 rows per 10 cm. Show compact, recognisable crochet stitches and believable matte yarn fibres, not knitting, rope, plastic or woven wicker. The outer edge is the final round in cream, exactly as charted; nothing is worked beyond it.

Reading the rounds from the centre outward: 5 cream rounds, 1 wine round, 1 cream round. That is 1 contrast band in total on a cream ground. Colours cream #FAF6EB, wine #6E1F2A, and no others.

It must not show: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the outer edge is the last round exactly as charted, and a vessel's top rim is that plain final round: no braided, rolled, twisted, scalloped, picot or crab-stitch (reverse single crochet) rim; colour changes anywhere except rounds 6, 7. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.

Photograph-style composition: the item alone on a light natural oak surface (#C9A97E) against a seamless warm greige wall (#B5ADA2), softly diffused window light, clean natural styling, centred, the entire item in frame with a margin on every side. Camera: directly overhead, square to the item, every piece laid completely flat and unfolded with no folds, drape or tucked edges, so every edge and band is visible. Sharp fabric detail, realistic texture and depth, natural shadows. No person, hands, props, text, logo, watermark, collage or extra piece. Output one square image. The product must faithfully represent the pattern rather than an embellished alternative.
```

### product_anchor (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | correction_base | 128x128 | `dd7e250562aac00f` |
| 2 | pdf_cover | 1187x1536 | `dfd5a1b4ad14e2b8` |
| 3 | pdf_colour_key | 1187x1536 | `adc92b8a9da9cb50` |
| 4 | pdf_chart | 1187x1536 | `4a6a8358affbd3c2` |
| 5 | pdf_chart | 1187x1536 | `517d9e85811d7e82` |
| 6 | pdf_finished | 1187x1536 | `e2eac6d6c854b4dd` |
| 7 | pdf_chart_key | 1187x1536 | `5681ebd8bf69b67c` |

Prompt, verbatim:

```text
Edit image 1 only, to fix: the colour layout; it must read exactly: Reading the rounds from the centre outward: 5 cream rounds, 1 wine round, 1 cream round. That is 1 contrast band in total on a cream ground. Colours cream #FAF6EB, wine #6E1F2A, and no others; the outline; it has exactly 6 sides and 6 corners. Image 1 is the image to edit. Image 2 is a page of the certified pattern PDF: the cover, with the finished product. Image 3 is a page of the certified pattern PDF: the materials and colour key (the exact yarn colours). Image 4 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 5 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 6 is a page of the certified pattern PDF: the finished design. Image 7 is a page of the certified pattern PDF: the chart key. The remaining attachments are the original pattern instructions and the authoritative product reference. Keep the camera, lighting, background, material, silhouette and all correct details of image 1 unchanged. Preserve: Each piece is a flat hexagon with exactly 6 corners. Reading the rounds from the centre outward: 5 cream rounds, 1 wine round, 1 cream round. That is 1 contrast band in total on a cream ground. Colours cream #FAF6EB, wine #6E1F2A, and no others. The outer edge is the final round in cream, exactly as charted; nothing is worked beyond it. Do not add anything or redesign the item. Return one corrected product image, square.
```

### lifestyle (stage `lifestyle_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | laura_face | 1024x1024 | `a42aeac72ba5733e` |
| 2 | laura_torso | 1024x1024 | `afe6191fb4c68d0a` |
| 3 | laura_body | 1024x1024 | `f32bac686cba46c7` |
| 4 | product_master | 128x128 | `dd7e250562aac00f` |

Prompt, verbatim:

```text
Create a photorealistic lifestyle photograph-style image for Brambleloop Studio.

Image 1 is the canonical model face. Image 2 is the canonical model's natural upper-body proportions. Image 3 is the canonical model's complete body proportions and silhouette. Image 4 is the accepted product master: the exact finished item to depict. Preserve the appearance established by the three model references; do not redesign the model or copy the reference outfit. The product master controls the product's shape, size, colours, colour layout and crochet texture. 

IDENTITY: the woman is Laura, exactly the person in image 1, image 2 and image 3. These three references fix her identity and anatomy ONLY, never her clothing. Preserve her face from image 1: eyes, eyebrows, nose, lips, cheekbones, jawline, freckles, apparent age, hairline and her highlighted wavy hair. Preserve face, bust fullness and projection, shoulders, waist, hips, legs and silhouette exactly as in image 2 and image 3; never flatten, reduce, exaggerate or redesign the bust; clothing fits and drapes over these approved proportions. Keep her full-body silhouette from image 3: waist-to-hip and legs. REPLACE ALL clothing from the reference images with the selected outfit: soft sage-green blouse, cream tailored trousers; do not reuse the reference beige trousers, ivory/cream tops or tan sandals. Do not change her identity, body shape or proportions.

Dress the model in soft sage-green blouse, cream tailored trousers. Natural makeup and a relaxed expression. The outfit looks like everyday home styling. Preserve this outfit in every image of this listing.

Scene: Laura's own home (laura-home-v1), the kitchen: a modest two-storey 1990s family house in a Canadian suburb: white-oak-look laminate floors, warm off-white walls, white painted trim, standard double-hung windows with plain linen curtains. shaker cabinets painted soft sage, a butcher-block counter, a white subway tile backsplash, the window over the sink looking onto a back yard. a round pine table with four mismatched chairs by the window. Lived in: a child's drawing held on the fridge with a magnet; a folded tea towel over the oven handle. In the frame: a mug of tea set down beside the product mid-morning. Light: overcast midday light from the back window, even and soft. Camera: a standing three-quarter view. A believable, modest family home with ordinary belongings, natural photographic composition. No other crocheted or knitted item is in the scene besides the product.

Action: Laura using the finished piece in everyday life at home. The coasters remains clearly visible and in sharp focus; no fingers hide its colour layout. It is approximately 9.7 x 8.4 cm: keep it at that real size against her hands and the furniture. Match the accepted product master; do not invent a different coasters. Each piece is a flat hexagon with exactly 6 corners. Reading the rounds from the centre outward: 5 cream rounds, 1 wine round, 1 cream round. That is 1 contrast band in total on a cream ground. Colours cream #FAF6EB, wine #6E1F2A, and no others. The outer edge is the final round in cream, exactly as charted; nothing is worked beyond it.

Natural hand anatomy, realistic perspective and scale. Commercial home-and-lifestyle editorial photography, softly lit. No infant, no text, no logos, no watermark. One image.
```

### size (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_master | 128x128 | `dd7e250562aac00f` |
| 2 | campaign_reference | 128x128 | `f54a85a12e93e210` |

Prompt, verbatim:

```text
Create a photorealistic product photograph-style image of the exact crochet coasters in the product master. Image 1 is the accepted product master: the exact finished item to depict. Image 2 is the approved campaign image of this listing: use it only for the location, light and styling, never for the product or the person. Use the approved room or campaign image for the same setting (in the kitchen of a modest family home, soft morning daylight from the window over the sink, no flash); it never changes the product. Keep the coasters itself identical to the product master: Each piece is a flat hexagon with exactly 6 corners. Reading the rounds from the centre outward: 5 cream rounds, 1 wine round, 1 cream round. That is 1 contrast band in total on a cream ground. Colours cream #FAF6EB, wine #6E1F2A, and no others. The outer edge is the final round in cream, exactly as charted; nothing is worked beyond it. It is approximately 9.7 x 8.4 cm; props and furniture are scaled to it.

Show the same item beside everyday objects of known size so its real size is clear. No unsupported size label. Brief: the finished piece beside everyday objects of known size.

One coaster under a ceramic mug of tea, the others stacked neatly beside it, with a small plate and a teaspoon. Keep the front and its colour layout unobstructed. No person, no hands, no child. Camera: a slightly elevated three-quarter view. Soft natural daylight, gentle background depth of field, a calm natural-home look. No text, watermark or logo. Output one square image.
```

## B3. Cloudline baby blanket (product master and correction)

`cloudline-baby-blanket@1.2.0` (Cloudline Textured Baby Blanket), release `7c63dbdd501fa6b1ec89a12b29ad50ad26f52091884b5d60893fafa4a27d9684`, PDF sha256 `5c584474bdb98394...` (the US edition rendered locally by `publish.pdf.build_pattern_pdf`). Flat rows with mixed stitch heights: the surface follows the chart; the worked colour order is stated.


### product_anchor (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | pdf_cover | 1187x1536 | `9df4a1c2a58420a8` |
| 2 | pdf_colour_key | 1187x1536 | `b54dfb1d17052f50` |
| 3 | pdf_chart | 1187x1536 | `77b8000e23fbaf82` |
| 4 | pdf_chart | 1187x1536 | `8a096538ef84228c` |
| 5 | pdf_chart | 1187x1536 | `5c0377298b4efdee` |
| 6 | pdf_finished | 1187x1536 | `82f39f187ebd7465` |

Prompt, verbatim:

```text
Create one photorealistic product visualization for Brambleloop Studio's crochet pattern listing. Image 1 is a page of the certified pattern PDF: the cover, with the finished product. Image 2 is a page of the certified pattern PDF: the materials and colour key (the exact yarn colours). Image 3 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 4 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 5 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 6 is a page of the certified pattern PDF: the finished design. Use the attached pattern pages as the authoritative instructions for the finished item; never reproduce their page layout, text, charts or drawings in the image.

The finished item is one blanket: Cloudline Textured Baby Blanket, version 1.2.0. Its shape is a flat rectangle, as the pattern pages draw it. Approximate finished size: about 79.2 x 96.4 cm at the stated gauge. It is made from worsted acrylic with a 5 mm hook in double crochet, single crochet, at 12.5 stitches and 13.8 rows per 10 cm. Show compact, recognisable crochet stitches and believable matte yarn fibres, not knitting, rope, plastic or woven wicker. The piece ends in the pattern's ordinary cream final row: no added rim, braid, roll, border or trim.

The colourwork is exactly as charted on the pattern pages, in cream #FAF6EB, ink #1A2B3C and no other colour. The rows are worked in this colour order, from the first: 6 cream rows, then (2 ink rows, 2 cream rows) repeated 21 times, 2 ink rows, 8 cream rows; the textured stitches carry colour over earlier rows, so the surface follows the chart rather than plain stripes.

It must not show: knitting of any kind: this is crochet (no knit V-columns, no stockinette, no purl ridges, no knitted rope cables); ribbing anywhere (the pattern has none); an edging, border, rib, fringe or trim along any edge; the edges are the plain ends of the rows; any end-band treatment other than exactly rows 1-6: plain cream #FAF6EB sc, solid, no stripe, no ribbing, no contrast row; any end-band treatment other than exactly rows 95-100: plain cream #FAF6EB sc, solid, no stripe, no ribbing, no contrast row; colour changes anywhere except every 2 rows from row 7 to 93. Never add: colours not in the certified palette; motifs, appliques or embroidery not in the certified pattern; borders, edgings, fringe, tassels or pom-poms not in the pattern; extra or missing pieces; a different stitch, texture or construction; knit, woven or printed fabric; text, logos, labels or watermarks.

Photograph-style composition: the item alone on a light natural oak surface (#C9A97E) against a seamless warm greige wall (#B5ADA2), softly diffused window light, clean natural styling, centred, the entire item in frame with a margin on every side. Camera: directly overhead, square to the item, every piece laid completely flat and unfolded with no folds, drape or tucked edges, so every edge and band is visible. Sharp fabric detail, realistic texture and depth, natural shadows. No person, hands, props, text, logo, watermark, collage or second blanket. Output one square image. The product must faithfully represent the pattern rather than an embellished alternative.
```

### product_anchor (stage `product_generation`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | correction_base | 128x128 | `46a6a6e32f09d1b9` |
| 2 | pdf_cover | 1187x1536 | `9df4a1c2a58420a8` |
| 3 | pdf_colour_key | 1187x1536 | `b54dfb1d17052f50` |
| 4 | pdf_chart | 1187x1536 | `77b8000e23fbaf82` |
| 5 | pdf_chart | 1187x1536 | `8a096538ef84228c` |
| 6 | pdf_chart | 1187x1536 | `5c0377298b4efdee` |
| 7 | pdf_finished | 1187x1536 | `82f39f187ebd7465` |

Prompt, verbatim:

```text
Edit image 1 only, to fix: the colour layout; it must read exactly: The colourwork is exactly as charted on the pattern pages, in cream #FAF6EB, ink #1A2B3C and no other colour. The rows are worked in this colour order, from the first: 6 cream rows, then (2 ink rows, 2 cream rows) repeated 21 times, 2 ink rows, 8 cream rows; the textured stitches carry colour over earlier rows, so the surface follows the chart rather than plain stripes; the repeat count; it must match the pattern pages exactly. Image 1 is the image to edit. Image 2 is a page of the certified pattern PDF: the cover, with the finished product. Image 3 is a page of the certified pattern PDF: the materials and colour key (the exact yarn colours). Image 4 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 5 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 6 is a page of the certified pattern PDF: the chart / schematic (colour bands, round and repeat counts). Image 7 is a page of the certified pattern PDF: the finished design. The remaining attachments are the original pattern instructions and the authoritative product reference. Keep the camera, lighting, background, material, silhouette and all correct details of image 1 unchanged. Preserve: Its shape is a flat rectangle, as the pattern pages draw it. The colourwork is exactly as charted on the pattern pages, in cream #FAF6EB, ink #1A2B3C and no other colour. The rows are worked in this colour order, from the first: 6 cream rows, then (2 ink rows, 2 cream rows) repeated 21 times, 2 ink rows, 8 cream rows; the textured stitches carry colour over earlier rows, so the surface follows the chart rather than plain stripes. The piece ends in the pattern's ordinary cream final row: no added rim, braid, roll, border or trim. Do not add anything or redesign the item. Return one corrected product image, square.
```

### hero (stage `remaining_roles`)

- size `2048x2048` -> FLUX 3 `aspect_ratio` `1:1`, `resolution` `2k`; seed: not sent (FLUX 3 has no seed field)
- `images`, in order:

| # | role | px | sha256 (16) |
|---|---|---|---|
| 1 | product_master | 128x128 | `46a6a6e32f09d1b9` |

Prompt, verbatim:

```text
Create a photorealistic product photograph-style image of the exact crochet blanket in the product master. Image 1 is the accepted product master: the exact finished item to depict. The setting: in the nursery of a modest family home, soft late-morning daylight through half-open curtains. Keep the blanket itself identical to the product master: Its shape is a flat rectangle, as the pattern pages draw it. The colourwork is exactly as charted on the pattern pages, in cream #FAF6EB, ink #1A2B3C and no other colour. The rows are worked in this colour order, from the first: 6 cream rows, then (2 ink rows, 2 cream rows) repeated 21 times, 2 ink rows, 8 cream rows; the textured stitches carry colour over earlier rows, so the surface follows the chart rather than plain stripes. The piece ends in the pattern's ordinary cream final row: no added rim, braid, roll, border or trim. It is approximately 79.2 x 96.4 cm; props and furniture are scaled to it.

A three-quarter editorial composition, the item the clear subject in sharp focus and set where it lives. Brief: hero: the finished piece in use, styled table or shelf.

Style it realistically as small nursery storage with rolled white cloth nappies, folded cream or sage muslin cloths and one small wooden rattle; the contents fit within it without stretching or enlarging it. Keep the front and its colour layout unobstructed. No person, no hands, no child. Camera: a slightly elevated three-quarter view. Soft natural daylight, gentle background depth of field, a calm natural-home look. No text, watermark or logo. Output one square image.
```
