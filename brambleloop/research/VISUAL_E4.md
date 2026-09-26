# Visual E4 — stitch-addressable correspondence, a continuous reference, and the yield of the photographic layer

**Branch** `claude/visual-investigation`, from checkpoint **`1229442`** (tag `checkpoint-e3`); `4a08871` (Milestone D close-out) and the integrated checkpoint `fcb982d` untouched. **Date** 2026-09-26. **Verdict: E4 FAIL as a pipeline; one image proves the two properties can coexist.** External spend **US$0.60** of the US$1.00 ceiling (images US$0.42 list, judge US$0.18), stopped with the evidence complete. Nothing structural was changed, no threshold was weakened, `twin.calibrated` is False.

Everything below is measured from files in `research/e4/out/` (manifests, per-stitch results, judge records with response ids and cost) and from `research/d/out/` (the frozen geometry and its digests). Where a number is a chosen bar it says CHOSEN; where a claim could not be tested it says UNKNOWN.

## 1. Frozen inputs

The assessed geometries of Milestone D's close-out, unchanged, hash-checked by every consumer:

| swatch | geometry sha256 (draped, assessed) |
|---|---|
| sc | `e0762cc081abbda5b602bab8c4dff097aeacbc7786891c0785108d073860c433` |
| hdc | `3a526ea8f46fca4d46d9035f1fedb06352889ab70bded2b761f4b644e12e8868` |

`research/e4/project.py` refuses a geometry whose digest differs from `milestone_d_<kind>_final.json`; the generation manifest records the digest per run; `research/e4/test_e4.py` checks that every manifest, every reference and every generation carry the same digests.

## 2. The reference had artificial features; they were traced and removed without moving a control point

E3 found that cut yarn ends became "tassels" and "bead-like nubs" in the photographs. The cause was in the yarn-path model, not the geometry: the certified 5×5 swatch's path contains 87 segments longer than `JUMP_SEGMENT_MM`, which the renderer believed were "artificial hops between ops" and cut, drawing two capped strand ends at every one -- 68 ends on hdc for a fabric that has two.

Tracing every one of the 87 (`tests/test_render.py::test_the_yarn_is_one_strand_with_exactly_two_ends_where_the_yarn_starts_and_stops`): 83 lie inside an hdc cell between named key points of the stitch (through→behind 6.41 mm, behind→emerge 5.52 mm, emerge→rise 5.80 mm -- the yarn's own travel around the post), 4 are in turning chains; sc has none. All of them are yarn. `pbr_scene.fabric_strands(continuous=True)` (now the default) drops only the duplicate point at each join and lets the strand run on; the cut mode is kept and tested for what it is. Control points are untouched: the strand is built from the certified points, nothing is inserted or moved, and `validate()` on the geometry is unchanged. Result: **one strand, two ends** on both swatches.

The clean references (`presentation3`, same camera and staging as the judged `presentation2`, 256 spp, 232–615 s each) and their digests:

| swatch | view | reference sha256 |
|---|---|---|
| sc | camera | `acdfc2d869dac12780a8f363e8beff8886866633f120c153c4d97b66a2d348db` |
| sc | oblique | `74431f489d31bbb117ae04c0529a055d7ff53d083aa36e2c3108f8f979323c1a` |
| hdc | camera | `93c9fd25af752562646b04464553c6a0b83eacf65bf5fdc59ffd4d54c1b7617a` |
| hdc | oblique | `986dbe48c2b94e8535e32a823c15a1ef46912f18af61256aca86027221dc020b` |

## 3. The projected-stitch correspondence instrument (`research/e4/project.py`)

We own the geometry, the stitch identities and the exact camera, so no stitch is counted blind. Every certified stitch is projected through the presentation camera (analytic pinhole verified against Mitsuba's own render to 0.5 px) into the reference image. The manifest per stitch: `id`, `family`, `row`, `position`, `points_px`, `depth_mm`, `centroid_px`, `bbox_px`, `orientation_up_px`, `colour_region`, `visible_points`/`visible_fraction` (depth-tested against the yarn's own depth map and the sphere), `testable`, and `neighbours` (anchor below, row ahead and behind, with projected offsets). Criteria are named in the manifest with reasons: visible_fraction ≥ 0.5 to be testable (CHOSEN), self-validation IoU ≥ 0.70 (CHOSEN), stitch-present IoU ≥ 0.60 (CHOSEN, below the self-validation bar by the margin E3 measured between an RGB render and its own outline), projected points in silhouette ≥ 0.98 (DERIVED).

**Self-validation on the deterministic reference, before any photograph was judged:**

| view | stitches | testable | projected points in silhouette | worst per-stitch reference IoU |
|---|---|---|---|---|
| sc camera | 25 | 22 | 1.000 | 0.902 |
| sc oblique | 25 | 8 | 1.000 | 0.928 |
| hdc camera | 25 | 23 | 1.000 | 0.928 |
| hdc oblique | 25 | 8 | 1.000 | 0.970 |

The instrument reads its own reference on every view. The oblique views expose only 8 of 25 stitches to the camera; the other 17 are reported UNKNOWN there, never PASS.

**Adversarial tests (`research/e4/test_e4.py`, 56 checks, offline):** the reference read as a photograph passes every testable stitch; erasing one stitch from it is caught and named, failures confined to overlapping regions, the rest still pass; the reference re-framed (scaled 0.8, shifted) still passes (scale free, shape not); a blank frame fails and no longer asks the aligner for a 1.3 TiB zoom; **a mirror image of the near-symmetric swatch passes the presence test** -- a real limit, recorded as a test -- so handedness is a separate global property: the certified orientation's structure map must correlate with the photograph at least twice as well as the mirrored one (CHOSEN; the references themselves read 4.2–9.5×; the mirrored reference FAILS it, the reference PASSES it).

## 4. Conditioning package and generation

From the same frozen geometry under the same camera (`research/e4/assets.py`, Mitsuba AOV pass): the clean RGB reference, the silhouette **mask**, the **normal** map, and depth (`.npz`, used for visibility, not sent). Package digests per run are in `e4_manifest.json`; the package is byte-identical across every round.

Provider `gpt-image-2`, `images/edits`, through the repository's `gateway.images.generate` (an optional `extra_fields` pass-through was added for round 3 and nothing else changed). The prompts name presentation only -- no stitch family, count, construction or fold:

- **Round 1** (`e4`): "…Keep the piece exactly as shown… natural fibre texture with a little fuzz, soft window daylight… plain linen tablecloth…"
- **Round 2** (`e4r2`): the same, but calling the first image "a computer rendering" and asking for "real spun wool yarn: a matte surface with a fine fibre halo, a slightly uneven twist, no plastic sheen, no stripes, no beads or knobs anywhere along the strands". This is the localised fix for round 1's realism failures, which the judge attributed to the copied rendered material.
- **Round 3** (`e4r3`): round-2 prompt plus the endpoint's `input_fidelity=high`, the localised fix for round 2's structural drift. **Refused by the provider before any spend**: `The model 'gpt-image-2' does not support the 'input_fidelity' parameter` on all four requests.
- **Yield round** (`e4y`): the round-2 prompt unchanged, four more sc oblique draws and two more sc camera draws, to measure per-attempt yield rather than tune further.

## 5. Results, image by image

Structural = every testable stitch present (local) AND silhouette, proportions, colour, row placement, structure placement, construction cues, macro deformation, handedness (global). Judge = the unchanged independent D judge (`gpt-5-2025-08-07`, seven items, PASS only when every item is sound). Bars: silhouette IoU ≥ 0.80, aspect drift ≤ 0.10, structure NCC ≥ 0.30, hue spread ≤ 12°, row IoU ≥ 0.72, stitch IoU ≥ 0.60, handedness ≥ 2×.

| round | image | local (tested, min IoU) | aspect drift | silhouette IoU | structure NCC | handedness | structural | judge |
|---|---|---|---|---|---|---|---|---|
| 1 | **sc camera** | PASS (22, 0.81) | 0.042 | 0.890 | 0.471 | 0.47/0.06 | **PASS** | **7/7 PASS** |
| 1 | sc oblique | PASS (8, 0.71) | 0.076 | 0.841 | 0.341 | 0.34/0.21 FAIL | FAIL | 4/7 (plasticky, striped, rigid) |
| 1 | hdc camera | PASS (23, 0.75) | 0.091 | 0.840 | **0.191** | 0.19/0.03 | FAIL | 4/7 (bead-like clumps) |
| 1 | hdc oblique | PASS (8, 0.80) | **0.105** | 0.850 | 0.443 | 0.44/0.10 | FAIL | 5/7 |
| 2 | sc camera | PASS (22, 0.82) | 0.086 | 0.911 | 0.437 | 0.44/0.09 | **PASS** | 4/7 (plastic, repeats) |
| 2 | sc oblique | PASS (8, 0.82) | **0.239** | 0.885 | 0.470 | 0.47/0.11 | FAIL | **7/7** |
| 2 | hdc camera | PASS (23, 0.78) | 0.040 | 0.827 | **0.207** | 0.21/0.03 | FAIL | **7/7** |
| 2 | hdc oblique | PASS (8, 0.86) | **0.176** | 0.893 | 0.407 | 0.41/0.18 | FAIL | **7/7** |
| y | sc oblique #1 | PASS (8) | **0.366** | 0.848 | **0.039** | UNKNOWN | FAIL | **7/7** |
| y | sc oblique #2 | PASS (8) | **0.254** | 0.888 | 0.371 | PASS | FAIL | 4/7 |
| y | sc oblique #3 | PASS (8) | **0.216** | **0.800** | **0.260** | PASS | FAIL | **7/7** |
| y | sc oblique #4 | PASS (8) | **0.474** | 0.851 | **0.126** | PASS | FAIL | 5/7 |
| y | sc camera #1 | PASS (22) | **0.166** | 0.916 | 0.452 | PASS | FAIL | 6/7 |
| y | sc camera #2 | PASS (22) | **0.173** | 0.880 | 0.564 | PASS | FAIL | 4/7 |

Per-stitch detail for every image is in `<tag>_validation.json` (`local.per_stitch`, id → status, IoU, reference IoU, row, position, family). Judge records: `judge_<kind>_<view>_<tag>.json` (response id, tokens, cost, raw JSON, notes).

**The one image that satisfies both:** `research/e4/out/gen/sc_camera_e4.png`, sha256 `46eebcecd2c19e123c358f7da9f7c76e8c48035f65e22c972fb73db43d0eaf40`, generated from geometry `e0762cc0…` and reference `acdfc2d8…`; 22 of 25 stitches testable at this camera and all 22 present (mean IoU 0.899, worst 0.808 at r1p3); silhouette 0.890, proportions +4.2 %, structure 0.471 (mirror 0.056), one hue; judge `chatcmpl-ESEfOjAjMBHtIeVV7dTCKbtFp1cPj`, all seven items true, no note. The three untestable stitches (r3p1, r4p4, r5p4) are UNKNOWN, not PASS.

## 6. Yield, and where the failure lives

*Erratum 2026-09-26 (E5): this table originally split the sc draws as 6 camera / 5 oblique; the correct split is 4 camera (r1, r2, y1, y2) / 6 oblique (r1, r2, y1–y4). The per-image table above and every record were already correct; only the two row labels changed.*

Over 14 images with the same geometry and package:

| | structural PASS | judge 7/7 | both |
|---|---|---|---|
| sc camera (4 draws) | 2 | 1 | **1** |
| sc oblique (6 draws) | 0 | 3 | 0 |
| hdc camera (2) | 0 | 1 | 0 |
| hdc oblique (2) | 0 | 1 | 0 |

Localisation, by the brief's five candidates:

- **Instrument:** validated on all four references; adversarial cases caught; the aligner is scale-and-shift only. Not the failure. One limit found and closed (handedness).
- **Reference:** one continuous strand with two ends; the "bead" and "tassel" features of E3 are gone from the reference and from the round-2 photographs. Not the failure.
- **Package:** byte-identical across rounds; the same package produced a full pass and full failures. Not the failure.
- **Judge:** its verdicts follow the material the generator drew (round 1: copied rendered yarn → FAIL; round 2: re-synthesised wool → PASS on three views). Consistent. Not the failure.
- **Generator: this is where it fails, and the mechanism is measured.** On `gpt-image-2` edits the two things we need are coupled. Told to keep the piece exactly, it keeps the rendered material too (round 1: proportions held within 4–11 %, realism failed 3 of 4). Told the material is a rendering to replace, it re-shoots the object (round 2 and yield: real wool on 5 of 10, but the aspect ratio moves 17–47 % on 8 of 10 draws, and structure NCC collapses on the worst). The endpoint's control for exactly this, `input_fidelity`, is refused for this model. The per-attempt structural yield with the presentation-only prompt is 2/14 overall and 0/7 on the oblique view, where only 8 stitches face the camera and the generator has the most freedom to re-pose.

This is the blocker, proven within scope: with this provider and endpoint, the presentation authority cannot be exercised without the generator also exercising structural authority, and there is no parameter that separates them. The remaining US$0.40 (about 13 draws) could not change that reading at 0/7 on the oblique view, so spending stopped.

## 7. The D criteria in the neutral scene

The scene was changed as the brief allows -- a plain wooden ball on a linen tablecloth in window light, no lifestyle content -- and on the images the generator re-synthesised, the judge passes all seven items including the two that no deterministic render ever passed (melted yarn, synthetic stitch texture) and the sterility item the prop sphere failed in E3. That is an answer about the presentation layer only. Milestone D itself is unchanged: FAIL, with the same physical blocker recorded in `research/VISUAL_MILESTONE_D.md` §11, because a judged PASS on a generated image is not evidence about the deterministic drape.

## 8. Success criteria A–G, honestly

| | criterion | sc | hdc |
|---|---|---|---|
| A | reference valid (continuous yarn, digests) | PASS | PASS |
| B | instrument self-validates | PASS | PASS |
| C | structure preserved in the photograph | **1 image of 11**; pipeline FAIL | FAIL (NCC 0.19–0.21 camera; drift 0.11–0.18 oblique) |
| D | no hop/end becomes a feature | PASS (round 2 and yield: none named by the judge) | PASS on round 2 |
| E | D judge criteria pass | 1 image of 11 with C; 4 of 11 alone | 2 of 4 alone, 0 with C |
| F | no threshold weakened | PASS (one property added, none moved) | PASS |
| G | `twin.calibrated` truthful | False | False |

**E4: FAIL.** The claim "photoreal AND proven the same certified crochet structure" is true of exactly one image and of no view-pair, and the pipeline's yield is too low to call it a pipeline. It is not UNKNOWN: every property was measured.

## 9. What E4 changed in the repository

- `pbr_scene.fabric_strands(continuous=True)` default; `write_curve_file`/`write_plied_curve_file` take `continuous`; three continuity tests in `tests/test_render.py`.
- `research/e4/`: `assets.py` (package), `project.py` (instrument), `run_e4.py` (rounds), `validate_e4.py` (local → global → judge, judge cache keyed by image digest, handedness), `test_e4.py` (56 checks).
- `gateway.images.generate(..., extra_fields=None)`: verbatim pass-through on the OpenAI edits path, default none.
- No change to the production gate, the drape solver, the assessment, the thresholds, or anything under `cir/`.

## 10. Comparison: before, E3, E4

| | deterministic renders (D close-out) | E3 (cut-end reference, E3 correspondence) | E4 (continuous reference, per-stitch instrument) |
|---|---|---|---|
| judge, best view | 2/7 | 4/5 repaired on sc, hdc none | 7/7 on sc camera, sc oblique, hdc camera, hdc oblique (separate draws) |
| structure, best view | n/a (the reference) | FAIL ×5, UNKNOWN ×1; counts drifted 5→4, 5→6 | every testable stitch present in 14/14; global PASS on 2/14 |
| both at once | never | never | once |
| artefacts from the reference | 68 cut ends → tassels, beads | same | none |

## 11. Recommendation, not a decision

The deterministic side is finished for this purpose: certified geometry, clean reference, a stitch-addressable instrument that validates itself and catches erasure, mirroring and re-framing. The generative side needs a generator that accepts a structure lock (a fidelity or ControlNet-style conditioning input, or an inpainting mode that repaints material inside the mask only) so that presentation authority can be exercised alone. That is a provider question, to be answered by the existing image-provider benchmark on this exact package, not by more draws here. Until then, the gate distinction of E3 §6 stands and every E4 output but one classifies as redesign.
