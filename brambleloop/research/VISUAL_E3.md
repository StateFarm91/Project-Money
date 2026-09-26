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

CORRESPONDENCE_PLACEHOLDER

## 6. Presentation-gate distinction, tested (`research/e3/gate_spec.py`, not integrated)

GATE_PLACEHOLDER

## 7. Architecture decision

DECISION_PLACEHOLDER
