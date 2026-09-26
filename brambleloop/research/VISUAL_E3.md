# Visual E3 — certified structure in → photoreal presentation out → same product proven?

**Branch** `claude/visual-investigation`, from checkpoint **`4a08871`** (tag `checkpoint-milestone-d-closeout`), integrated checkpoint `fcb982d` untouched. **Date** 2026-09-26 (UTC). **Mode** Shadow. No merge, deploy, publication, production change or calibration claim; `twin.calibrated` stays False.

## 1. Frozen certified inputs

The assessed geometries of Milestone D's close-out, exactly as `milestone_d_<kind>_final.json` records them (draped points saved by the assessment; every consumer refuses them unless the hash matches):

| swatch | geometry sha256 (draped, assessed) | structural reference (judged `presentation2` render) | sha256 |
|---|---|---|---|
| hdc | `3a526ea8f46fca4d46d9035f1fedb06352889ab70bded2b761f4b644e12e8868` | camera | `df76633a0e3f762f94cbfd7b2a1dd6c9c0d8d88492087bb4f969b10f4b693f64` |
| hdc | same | oblique | `688e70b92513bca49032d33dd54cb0164e45823934328673ba5a8ee1923da847` |
| sc | `e0762cc081abbda5b602bab8c4dff097aeacbc7786891c0785108d073860c433` | camera | `acdfc2d869dac12780a8f363e8beff8886866633f120c153c4d97b66a2d348db` |
| sc | same | oblique | `74431f489d31bbb117ae04c0529a055d7ff53d083aa36e2c3108f8f979323c1a` |

Nothing structural was altered: stitch identity, topology, linkage, morphology, colour, macro structure and the certified deformation are those of the close-out records. (A defect in `research/d/present.py` was found on the way: it hashed each render before Mitsuba's asynchronous write had finished, so the `image_sha256` fields in `*_draped_presentation*.json` up to `4a08871` are of partial files; the judge records hashed the finished files and are authoritative, and the table above uses the finished files. Fixed for future renders.)

## 2. Conditioning package

Derived from the same frozen geometry under the same camera (`research/e3/assets.py`, Mitsuba AOV pass, pinhole): the fabric's own **silhouette mask**, **depth** (mm) and **shading normals**, per view. The package actually supplied to the generator was the **minimum that answers the experiment: the RGB structural render alone** — the same single-reference route E1 showed to preserve structure. Mask, depth and normals were used for *validation*, not conditioning. Mask pixels: hdc camera 383,551, oblique 309,956; sc camera 184,524, oblique 143,986.

## 3. Generation

Provider **`gpt-image-2` through the `images/edits` endpoint** via the repository's own `gateway.images.generate` (reference inline, 1024×1024), one image per view, four in all. Prompt (names no stitch family, count, construction or fold):

> Product photograph for a handmade craft marketplace listing of the crocheted swatch shown in the reference image, resting exactly as it does there on the same pale ball on the same surface. Keep the piece exactly as shown: the same outline, the same proportions, the same stitches in the same places, the same colour. Photograph it as a real object made of real yarn: natural fibre texture with a little fuzz, soft window daylight from one side, a plain neutral tabletop, an ordinary camera. No text, nothing else in frame.

| swatch | view | geometry | reference | output sha256 | time | list price |
|---|---|---|---|---|---|---|
| hdc | camera | `3a526ea8f46fca4d…` | `df76633a0e3f762f…` | `21cf49e0cd615b6c…` | 17.7 s | US$0.03 |
| hdc | oblique | `3a526ea8f46fca4d…` | `688e70b92513bca4…` | `82edf2284862d14f…` | 15.7 s | US$0.03 |
| sc | camera | `e0762cc081abbda5…` | `acdfc2d869dac127…` | `af2f7b5b4c75ecc0…` | 13.6 s | US$0.03 |
| sc | oblique | `e0762cc081abbda5…` | `74431f489d31bbb1…` | `6076995d5a48f47a…` | 15.0 s | US$0.03 |

**Actual external image-generation spend: US$0.12 list** (ceiling US$1.00; the provider's bill is the authority). Outputs: `research/e3/out/gen/<kind>_<view>_0.png`.

## 4. Photographic realism — the unchanged independent D judge (`d_judge`, gpt-5-2025-08-07)

- **hdc**: fabric_folds_naturally: FAIL | lighting_is_realistic: PASS | shadows_are_coherent: PASS | has_ordinary_photographic_imperfection: FAIL | melted_yarn: FAIL | synthetic_stitch_texture: FAIL | catalogue_perfect_sterility: FAIL
- `hdc_camera_0.png` — `chatcmpl-ESDyKRFI39KSGqldgdQWfmtB0UeKJ`, US$0.0159: “Yarn surface looks plasticky with uniform ribbing; stitch rows and bead-like nubs repeat with uncanny regularity.”
- `hdc_oblique_0.png` — `chatcmpl-ESDygabV4aYv8P682xA8Nj3bKbYg4`, US$0.0127: “The yarn appears plasticky with uniform ribbing and identical bead-like ends, and the whole scene is impeccably clean like a studio render.”
- **sc**: fabric_folds_naturally: PASS | lighting_is_realistic: PASS | shadows_are_coherent: PASS | has_ordinary_photographic_imperfection: PASS | melted_yarn: PASS | synthetic_stitch_texture: PASS | catalogue_perfect_sterility: FAIL
- `sc_camera_0.png` — `chatcmpl-ESDyuombLCUiD1SUNjdE9eXkSYTDY`, US$0.0086: “(no note)”
- `sc_oblique_0.png` — `chatcmpl-ESDz543KdqPSJphunDsSxKNm662uK`, US$0.0139: “Very clean studio setup with a prop sphere and smooth background makes it feel like a styled product shot.”

Judge cost US$0.0512. Records `research/e3/out/judge_<kind>_generated.json`.

Against the close-out (`4a08871`, deterministic presentation2 renders: both swatches FAIL on folds, imperfection, melted yarn, synthetic texture, sterility; lighting and shadows PASS):

| item | hdc deterministic | hdc generated | sc deterministic | sc generated |
|---|---|---|---|---|
| fabric_folds_naturally | FAIL | FAIL | FAIL | PASS |
| has_ordinary_photographic_imperfection | FAIL | FAIL | FAIL | PASS |
| melted_yarn | FAIL | FAIL | FAIL | PASS |
| synthetic_stitch_texture | FAIL | FAIL | FAIL | PASS |
| catalogue_perfect_sterility | FAIL | FAIL | FAIL | FAIL |
| lighting_is_realistic | PASS | PASS | PASS | PASS |
| shadows_are_coherent | PASS | PASS | PASS | PASS |

## 5. Structural correspondence (`research/e3/correspond.py`)

Method. Numeric properties are measured against the silhouette mask derived from the frozen geometry under the same camera; because the edits endpoint re-frames (the piece sits at 0.84–1.21× and up to 134 px away), the generated silhouette is **aligned to the reference by centroid and area** — scale free, shape not, the presentation gate's own rule — and both the raw and aligned figures are recorded. Structure placement is the normalised correlation of blurred gradient magnitude inside the reference silhouette (where rows and posts sit). Counted properties are read blind by the independent model (`gpt-5-2025-08-07`) from the reference render AND the photograph with one neutral questionnaire; such a property passes only when the reader sees the certified truth on the reference (the instrument can see it) and the photograph reads the same. Bars: IoU ≥ 0.80, aspect drift ≤ 10 %, NCC ≥ 0.30, hue spread ≤ 12° — each CHOSEN and stated with its reason in `e3_correspondence.json`. Reader spend US$0.133 (round 1) + US$0.041 (package arm).

**Round 1 — conditioned on the RGB structural render alone (four images)**

| property | hdc camera | hdc oblique | sc camera | sc oblique |
|---|---|---|---|---|
| silhouette | **PASS** IoU 0.82 (raw 0.66) | **PASS** IoU 0.84 (raw 0.59) | **PASS** IoU 0.88 (raw 0.62) | **PASS** IoU 0.90 (raw 0.76) |
| major_proportions | **FAIL** aspect 1.29→1.00 (+23%) | **PASS** aspect 1.45→1.42 (+2%) | **PASS** aspect 1.00→1.10 (+9%) | **PASS** aspect 1.25→1.30 (+4%) |
| structure_placement | **FAIL** NCC 0.15 (raw -0.03) | **FAIL** NCC 0.24 (raw -0.01) | **FAIL** NCC 0.08 (raw 0.02) | **PASS** NCC 0.57 (raw 0.11) |
| colour_regions | **PASS** hue spread 7.7°, colours read 1 | **PASS** hue spread 6.0°, colours read 1 | **PASS** hue spread 6.4°, colours read 1 | **PASS** hue spread 3.1°, colours read 1 |
| rows | **UNKNOWN** truth 5, ref read 6, gen read 5 | **PASS** truth 5, ref read 5, gen read 5 | **UNKNOWN** truth 5, ref read 3, gen read 4 | **UNKNOWN** truth 5, ref read 4, gen read 4 |
| stitches_per_row | **UNKNOWN** truth 5, ref read 6, gen read None | **FAIL** truth 5, ref read 5, gen read 4 | **UNKNOWN** truth 5, ref read None, gen read 5 | **UNKNOWN** truth 5, ref read None, gen read 5 |
| stitch_family | **PASS** truth tall, ref read tall, gen read tall | **PASS** truth tall, ref read tall, gen read tall | **UNKNOWN** truth short, ref read tall, gen read tall | **UNKNOWN** truth short, ref read tall, gen read tall |
| construction_cues_loose_ends | **FAIL** ref “sides”, gen “none” | **FAIL** ref “top and sides”, gen “sides” | **FAIL** ref “sides”, gen “bottom” | **PASS** ref “none”, gen “none” |
| openings | **PASS** n/a | **PASS** n/a | **PASS** n/a | **PASS** n/a |
| deformation_fold_placement | **FAIL** IoU 0.82, NCC 0.15 | **FAIL** IoU 0.84, NCC 0.24 | **FAIL** IoU 0.88, NCC 0.08 | **PASS** IoU 0.90, NCC 0.57 |
| **overall** | **FAIL** | **FAIL** | **FAIL** | **UNKNOWN** |

- hdc camera — reference read: “Tall open stitches alternate with flatter horizontal bands, giving a lacy ladder-like look with small bobbly clusters visible along both side edges.”; photograph read: “Open lattice with elongated loops, and the fabric appears to form a tube rather than a flat swatch.”
- hdc oblique — reference read: “Open, airy pattern with tall posts and wide gaps; edges are uneven and the bottom curls.”; photograph read: “Open, lacy structure with large elongated loops and several small knotted tassels at the edges.”
- sc camera — reference read: “Open, airy stitches with pronounced vertical posts and slight curling at the edges.”; photograph read: “Open, lacy fabric made of crossed elongated stitches creating a zigzag mesh.”
- sc oblique — reference read: “Open, loosely worked tall loops with large gaps; the swatch is curved and the edges curl.”; photograph read: “Open tall-loop structure with pronounced ridges makes the small swatch appear ruffled and corrugated.”

**Package arm — RGB + silhouette mask + normals (two oblique views)**

| property | hdc oblique | sc oblique |
|---|---|---|
| silhouette | **PASS** IoU 0.93 (raw 0.77) | **PASS** IoU 0.84 (raw 0.89) |
| major_proportions | **PASS** aspect 1.45→1.47 (+1%) | **FAIL** aspect 1.25→0.80 (+36%) |
| structure_placement | **PASS** NCC 0.59 (raw 0.08) | **PASS** NCC 0.40 (raw 0.65) |
| colour_regions | **PASS** hue spread 3.2°, colours read 1 | **PASS** hue spread 9.6°, colours read 1 |
| rows | **PASS** truth 5, ref read 5, gen read 5 | **UNKNOWN** truth 5, ref read 4, gen read 4 |
| stitches_per_row | **FAIL** truth 5, ref read 5, gen read 6 | **UNKNOWN** truth 5, ref read None, gen read None |
| stitch_family | **PASS** truth tall, ref read tall, gen read tall | **UNKNOWN** truth short, ref read tall, gen read tall |
| construction_cues_loose_ends | **FAIL** ref “top and sides”, gen “sides” | **PASS** ref “none”, gen “none” |
| openings | **PASS** n/a | **PASS** n/a |
| deformation_fold_placement | **PASS** IoU 0.93, NCC 0.59 | **PASS** IoU 0.84, NCC 0.40 |
| **overall** | **FAIL** | **FAIL** |

- hdc oblique — photograph read: “Open, lacy mesh with very tall twisted posts and large gaps between rows.”
- sc oblique — photograph read: “Deep wavy ridges form a highly textured, ruffled surface with open gaps between rows.”

**What the correspondence says.** The photographs keep the *outline* of the certified object (aligned IoU 0.82–0.93 on all six) and, where the package arm was used, where its rows and posts sit (NCC 0.40–0.60). They do **not** reliably keep the *stitch-level* structure: where the independent reader can count the truth on the reference at all (hdc oblique only), the photograph shows 4 or 6 stitches per row for 5, and the reference's cut strand ends become "knotted tassels"; the hdc camera photograph reads as "a tube rather than a flat swatch" (aspect −23 %). On three of four views the reader cannot see the certified counts **on the deterministic reference itself** (6×6, 3 rows, "tall" for single crochet), so those properties are UNKNOWN for the photograph too — an instrument limit of the 5×5 swatch at this yarn scale, not evidence either way. No image reaches "same product proven": overall FAIL ×3 / UNKNOWN ×1 (round 1), FAIL ×2 (package).


## 6. Presentation-gate distinction, tested (`research/e3/gate_spec.py`, not integrated)

`gate_spec.classify` — a generative operation that touched the product is a **certified presentation transformation** only when it declares the frozen geometry *and* reference digests it was conditioned on, its revalidation was made against those same digests, and every structural property PASSED; a FAIL anywhere is unauthorised redesign; an UNKNOWN with no FAIL blocks as UNKNOWN. `test_e3.py`, 10/10: against E3's actual evidence every round-1 image classifies as

- hdc camera (RGB): **UNAUTHORISED_REDESIGN**
- hdc oblique (RGB): **UNAUTHORISED_REDESIGN**
- sc camera (RGB): **UNAUTHORISED_REDESIGN**
- sc oblique (RGB): **UNKNOWN**

and the boundaries hold — no declared reference is redesign however good the picture, a non-frozen reference is redesign, never revalidated is redesign ("conditioning is a claim, revalidation the proof"), revalidation against a different digest is redesign, one UNKNOWN never certifies. **The distinction works experimentally and fails closed; nothing in it was satisfied by this experiment's outputs, which is the correct reading of them.** Proposed treatment (not integrated): `presentation.PresentationPlan` gains `conditioned_on` (geometry + reference digests) per generative operation and a `correspondence` result; `refuse_if_the_product_is_redesigned` raises unless the plan classifies as certified; the existing `ProductRedesigned` path is unchanged for every unconditioned or unrevalidated operation. The current production gate is not changed.


## 7. Architecture decision

### 7a. Did generative presentation repair the five D photographic failures?

| item | deterministic (4a08871) | sc, RGB arm | sc, package arm | hdc, RGB arm | hdc, package arm |
|---|---|---|---|---|---|
| fabric_folds_naturally | FAIL | PASS | UNKNOWN | FAIL | FAIL |
| has_ordinary_photographic_imperfection | FAIL | PASS | PASS | FAIL | FAIL |
| melted_yarn | FAIL | PASS | PASS | FAIL | FAIL |
| synthetic_stitch_texture | FAIL | PASS | PASS | FAIL | FAIL |
| catalogue_perfect_sterility | FAIL | FAIL | FAIL | FAIL | FAIL |
| lighting / shadows | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |

Package-arm judge notes — hdc: “Yarn has a uniform ribbed surface with no fibers and identically repeated stitch shapes with bead-like nubs; the scene is extremely clean and sterile, reading as CG.”; sc: “Very smooth, seamless backdrop and a perfectly matte white sphere create a stylized, almost CG display. The ruffled pattern is highly uniform.”.

Read together with §4: on the **sc** swatch one reference-conditioned generation repaired **four of the five** (folds, imperfection, melted yarn, synthetic texture); the fifth, sterility, is the *scene we asked for* (a prop sphere on a seamless surface, chosen so correspondence could be measured) and the judge says exactly that. On the **hdc** swatch the generator repaired nothing — and the reason is the other half of the finding: it **faithfully carried the reference's own artefacts** (the 68 cut strand ends of the yarn-path model became "bead-like nubs" and "knotted tassels"; the uniform ribbing stayed uniform). A generator that preserves the reference this literally is evidence for conditioning fidelity, and it means a deterministic reference with artefacts produces a photograph with artefacts.

### 7b. Did any Product Truth property drift?

Yes, at the stitch level, and it was caught: stitches per row read 4 (RGB arm) and 6 (package arm) against a certified 5 on the one view where the instrument can count the reference (hdc oblique); cut ends became tassels — a feature the product does not have; the hdc camera photograph reads as a tube (aspect −23 %). Preserved: outline (aligned IoU 0.82–0.93 on all six), rows (5 where readable), stitch family at the reader's level, single colour, and — with the mask + normals package — where the rows and posts sit (NCC 0.40–0.60). The gate classifies every output as redesign or UNKNOWN, which is right.

### 7c. The decision — OPTION 3, hybrid, with the split drawn by this evidence

**Option 1 is refuted for the photographic properties.** Three deterministic rounds failed all five in three independent readings; one conditioned generation repaired four of them on the sc swatch at US$0.03. The deterministic renderer does not need to become a camera.

**Option 2 is refuted for stitch-level Product Truth.** Counts drifted (5 → 4, 5 → 6), artefacts became features, one silhouette re-shaped. A generative layer cannot be trusted with the stitches, and no validation this experiment could run establishes the same product at that level.

**Option 3, with this division:**

| stays deterministic (certified, measured) | may be generated (presentation authority) | must be revalidated, and today cannot be |
|---|---|---|
| CIR → stitch identity, topology, linkage, morphology, colour placement; the certified deformation on the form; the structural reference and its digests | fibre and fuzz, yarn surface and material response, lighting, shadows, camera response, background and surface | stitch count and organisation, and any construction cue at stitch scale: the independent reader could not count the truth on three of four *deterministic reference renders* (6×6, 3 rows, "tall" for single crochet), so the photograph cannot be measured against it there |

The conditioning package matters: RGB + silhouette mask + normals raised structure placement from 0.24 to 0.60 (hdc oblique) and silhouette from 0.84 to 0.93. The minimum package that answers the next experiment is therefore the three-image one, not the RGB render alone.

### 7d. What the hybrid needs before it can certify anything (the next phase's work, not started)

1. **A stitch-level correspondence instrument that does not read pixels blind.** The geometry is ours: project every certified stitch centre into the reference camera and test the photograph *at those locations* (local structure present, row/column adjacency preserved) rather than asking a model to count. Counting was UNKNOWN on three of four references; a projected-stitch test has no such limit.
2. **A reference without artefacts of the model.** The 68 cut ends are the yarn-path model's hops between operations; a continuous path removes the "tassels" at the source. This is a Visual/topology increment, not a rendering one.
3. **A scene that is a real place.** Sterility is the one item the sc swatch failed, and the scene was chosen for measurability. The next phase's benchmark scene (a listing photograph's) answers it directly.
4. **The gate treatment in §6**, integrated only once 1–2 make a certified transformation reachable.

### 7e. Spend and boundaries

External spend for E3: **image generation US$0.18** (six gpt-image-2 edits at list; ceiling US$1.00), independent judge US$0.0773, structural reader US$0.1738 — **US$0.43 in all**. Session total across D close-out and E3: US$0.57 list, plus the earlier E1/E2 US$0.46.

Not done, per the brief: no purchased-pattern work, no lifestyle or model photography, no provider tournament, no gate change in production, no merge, no deploy, no Etsy change, no calibration claim; `twin.calibrated` False. Checkpoints `4a08871` (tag `checkpoint-milestone-d-closeout`) and `fcb982d` untouched.
