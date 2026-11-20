# Visual E5 — structure-locked photorealisation: provider / model / mode benchmark

**Branch** `claude/visual-investigation`, from checkpoint **`a447c2f`** (E4 close); `4a08871`, `1229442`, `fcb982d` untouched. **Date** 2026-09-26. **Verdict: no repeatable route found.** Realism is now near-universal (18 of 21 draws pass all seven judge items); structural certification is not, on any provider or mode reachable from here. Best modes: **gpt-image-1.5 with `input_fidelity=high`, 2 certified of 4**, and **gemini-3-pro-image, 2 of 8**, against E4's gpt-image-2 at 1 of 4 on the same view. No mode produced two consecutive certified draws. External spend **US$2.80** of the US$3.00 ceiling (generation US$2.58, judge US$0.22). `twin.calibrated` False. No threshold changed.

Every number below is read from `research/e5/out/` (manifest with request and output digests, per-image validation, judge records with response ids) and reproducible offline from those files; `research/e5/test_e5.py` (19 checks) asserts the bookkeeping.

## 1. Frozen benchmark

The E4 SC camera package, byte for byte, re-hashed before every mode (`research/e5/frozen.py`):

| input | sha256 |
|---|---|
| certified geometry (draped points) | `e0762cc081abbda5b602bab8c4dff097aeacbc7786891c0785108d073860c433` |
| `sc_draped.npz` | `3eaae06df07b2a84…` |
| assessment record | `4aaca8f9ab5ceb41…` |
| RGB reference (presentation3, continuous yarn) | `acdfc2d869dac12780a8f363e8beff8886866633f120c153c4d97b66a2d348db` |
| silhouette mask | `c0980cec58e3e8b9…` |
| normals | `8d3b03ecaab2e416…` |
| depth | `1c191852de387958…` (visibility only; not sent) |
| projected-stitch manifest | `c9b35caf4201b770…` |
| E4 baseline image | `46eebcecd2c19e12…` |

Two edit masks were derived from the frozen silhouette (dilated 3 px, 193,607 editable px): OpenAI alpha convention `a92d73a87120be11…`, BFL white convention `a0ad01b9a069d3ce…`. Nothing in the crochet reference was changed for any provider.

## 2. Capabilities, verified on the wire before spending

Credentials present for three accounts (OpenAI, Black Forest Labs, Google); none for anything else. Read-only probes: model listings, BFL's OpenAPI document and credit balance, and parameter probes with a deliberately unreadable image so that nothing rendered or billed.

| provider | verified | not available |
|---|---|---|
| OpenAI `images/edits` | `gpt-image-1` and `gpt-image-1.5` accept `input_fidelity=high`, `quality`, and a `mask`. `gpt-image-2`, `gpt-image-2.5-flare`, `gpt-image-2.5-sunburst` **refuse `input_fidelity`** (`invalid_input_fidelity_model`). Up to 16 reference images. | any depth / normal / structure conditioning |
| Black Forest Labs | `/v1/flux-2-pro`, `/v1/flux-2-max` (multi-image edit, `disable_pup`), `/v1/flux-2-flex` (edit with `guidance`, `steps`, "preserving small details"), `/v1/flux-kontext-pro|max` (edit), `/v1/flux-pro-1.0-fill` (mask inpainting, `guidance`, `steps`), `/v1/flux-pro-1.0-expand`, tools (erase, deblur, outpaint, VTO). Balance 1,397 credits. | **`flux-pro-1.0-depth` and `-canny` answer 404**: the ControlNet-style structural conditioning this benchmark was hoping for no longer exists on this API |
| Google Generative Language | `gemini-2.5-flash-image`, `gemini-3.1-flash-image(-preview, -lite)`, `gemini-3-pro-image(-preview)`: multi-image edit, `imageSize`; the key is on a billed project (probes answered 400 on the bad image, not 429 free-tier). | no fidelity, strength, mask or structure parameter of any kind |

Ranking for *this* control problem, before any draw: (1) explicit fidelity control (gpt-image-1 / 1.5 `input_fidelity=high`); (2) construction-locked silhouette via mask inpainting (OpenAI mask, FLUX Fill); (3) FLUX.2 flex with guidance; (4) FLUX.2 max / Kontext max (documented consistency, no knob); (5) Gemini 3 Pro / 3.1 Flash image (strong editors, no knob). Seedream is unreachable (Volcano Engine account), as `gateway.images.ACCOUNTS` already records.

## 3. Prompts and modes

Presentation-only prompts, no stitch family, count, construction, fold or answer (`test_e5.py` checks the words). `PROMPT_EDIT_3REF` is E4 round 2 verbatim (RGB + mask + normals); `PROMPT_EDIT_1REF` the same without the sentence about images that are not sent (BFL edit modes take the RGB only); `PROMPT_INPAINT` for the two mask modes, describing only the material inside the editable region. Modes, with every parameter, are in `run_e5.MODES` and copied into the manifest.

## 4. Instrument

The unchanged E4 instrument (`research/e4/project.py`, `validate_e4.py`): per-stitch presence against the projected manifest (bar 0.60), then silhouette (≥ 0.80), proportions (aspect drift ≤ 0.10), colour (hue spread ≤ 12°), row placement (≥ 0.72), structure placement (NCC ≥ 0.30), construction cues, macro deformation, handedness (certified ≥ 2× mirrored); then the unchanged independent D judge (`gpt-5-2025-08-07`, seven items). **Certified = structural PASS and all seven judge items PASS.** UNKNOWN never certifies.

**One instrument change, measured before it was made, and reported both ways.** The E4 aligner takes scale from the area ratio and shift from the centroids of a hue segmentation. On real photographs the segmentation catches warm scene pixels (the wooden ball, linen), which mis-scales and mis-centres the alignment: a bounded search found the structure NCC under-read by up to 0.44 (gpt-image-1.5 draw 1: 0.131 by the E4 aligner, 0.572 at scale 1.007 / 16 px away) while the E4 baseline moved only 0.47 → 0.51. E5 therefore adds `refine=True` to `aligned_masks`: from the E4 estimate, climb scale and shift to the maximum **silhouette** overlap (never the structure or per-stitch quantities it then feeds). E4's default is unchanged and its records are untouched; `research/e4/test_e4.py` now runs every adversarial case under both aligners (66 checks: erasure caught, re-framing tolerated, blank refused, mirror fails handedness, under both). Every E5 verdict below is given under the E5 aligner with the E4 aligner's verdict beside it, and the E4 baseline was re-measured under both (`e4_baseline_under_e5_instrument.json`): its four sc camera draws stay 2/4 structural, 1/4 certified either way.

## 5. Every draw

| mode | draw | sha256 | structural (E5 aligner) | E4 aligner | silhouette | drift | NCC | handedness | min stitch IoU | judge | certified |
|---|---|---|---|---|---|---|---|---|---|---|---|
| oa1_hifi | 1 | `b3b0a7c30d08` | FAIL | FAIL | 0.802 | 0.004 | 0.141 | FAIL | 0.70 | 7/7 | no |
| oa15_hifi | 1 | `89e77df92876` | PASS | FAIL | 0.849 | 0.095 | 0.592 | PASS | 0.65 | 7/7 | **yes** |
| oa1_hifi_mask | 1 | `f4fb2dadffbb` | FAIL | FAIL | 0.333 | 0.012 | 0.065 | UNKNOWN | 0.32 | 2/7 | no |
| bfl_fill | 1 | `361184f82113` | FAIL | FAIL | 0.010 | 0.003 | 0.094 | UNKNOWN | 0.00 | 0/7 | no |
| bfl_flex | 1 | `e5788e0df2c0` | FAIL | FAIL | 0.784 | 0.141 | 0.398 | PASS | 0.76 | 7/7 | no |
| bfl_2max | 1 | `2b8e0091ba03` | FAIL | FAIL | 0.837 | 0.198 | 0.252 | PASS | 0.69 | 7/7 | no |
| bfl_kmax | 1 | `cf51b533106f` | FAIL | FAIL | 0.850 | 0.077 | 0.110 | FAIL | 0.83 | 7/7 | no |
| g3pro | 1 | `2dad12dbf61e` | PASS | FAIL | 0.847 | 0.073 | 0.432 | PASS | 0.68 | 7/7 | **yes** |
| g31flash | 1 | `98fd291ac30d` | FAIL | FAIL | 0.874 | 0.451 | 0.377 | FAIL | 0.79 | 7/7 | no |
| g3pro | 2 | `1d072bba5f43` | FAIL | FAIL | 0.780 | 0.017 | 0.499 | PASS | 0.66 | 7/7 | no |
| g3pro | 3 | `854c7fb1e4e1` | FAIL | FAIL | 0.822 | 0.222 | 0.455 | PASS | 0.62 | 7/7 | no |
| g3pro | 4 | `b55cc910a302` | PASS | PASS | 0.874 | 0.002 | 0.468 | PASS | 0.73 | 7/7 | **yes** |
| bfl_flex | 2 | `81999b4ee4ba` | PASS | PASS | 0.840 | 0.009 | 0.376 | PASS | 0.81 | 6/7 | no |
| bfl_flex | 3 | `e8095ff2f8c6` | FAIL | FAIL | 0.813 | 0.256 | 0.174 | PASS | 0.70 | 5/7 | no |
| g3pro | 5 | `1e84841f6d12` | FAIL | FAIL | 0.777 | 0.000 | 0.411 | FAIL | 0.63 | 7/7 | no |
| g3pro | 6 | `6f41a4aed782` | FAIL | FAIL | 0.840 | 0.343 | 0.494 | PASS | 0.74 | 7/7 | no |
| g3pro | 7 | `c2907c015aaf` | FAIL | FAIL | 0.569 | 0.277 | 0.284 | PASS | 0.47 | 7/7 | no |
| g3pro | 8 | `e64a56195f98` | FAIL | FAIL | 0.577 | 0.329 | 0.389 | PASS | 0.50 | 7/7 | no |
| oa15_hifi | 2 | `94788347aa6e` | FAIL | FAIL | 0.877 | 0.127 | 0.533 | PASS | 0.73 | 7/7 | no |
| oa15_hifi | 3 | `a43dff4e48d6` | FAIL | FAIL | 0.824 | 0.180 | 0.477 | PASS | 0.66 | 7/7 | no |
| oa15_hifi | 4 | `5fbb3207dd9d` | PASS | PASS | 0.938 | 0.004 | 0.355 | PASS | 0.85 | 7/7 | **yes** |

Full digests, per-stitch tables, judge response ids and notes: `e5_validation.json`, `judge_<mode>_<draw>.json`.

## 6. Yield and cost

Judge cost is US$0.0107 per draw (US$0.224 over 21). Generation cost per draw is measured where the provider reports it (OpenAI usage tokens at the gpt-image-1 list rates: 13,062 image-input tokens per three-reference call, 1,056–1,414 output; BFL credit balance, which updates lazily, reconciled 1,397 → 1,364 → 1,354) and list price for Google.

| mode | provider / model | draws | structural PASS (E4 aligner) | judge 7/7 | **certified** (E4 aligner) | US$ generation / draw | US$ / certified (incl. judge) | mean s |
|---|---|---|---|---|---|---|---|---|
| oa15_hifi | OpenAI gpt-image-1.5, `input_fidelity=high`, quality medium, RGB+mask+normals | 4 | 2 (1) | 4 | **2 (1)** | 0.187 | 0.40 | 21.0 |
| g3pro | Google gemini-3-pro-image, 1K, RGB+mask+normals | 8 | 2 (1) | 8 | **2 (1)** | 0.134 | 0.58 | 16.8 |
| bfl_flex | BFL flux-2-flex, guidance 5, 50 steps, RGB | 3 | 1 (1) | 1 | 0 | 0.067 | — | 15.7 |
| oa1_hifi | OpenAI gpt-image-1, `input_fidelity=high` | 1 | 0 | 1 | 0 | 0.174 | — | 17.2 |
| bfl_2max | BFL flux-2-max, no prompt upsampling | 1 | 0 | 1 | 0 | 0.10 | — | 27.4 |
| bfl_kmax | BFL flux-kontext-max | 1 | 0 | 1 | 0 | 0.08 | — | 18.6 |
| g31flash | Google gemini-3.1-flash-image, 1K | 1 | 0 | 1 | 0 | 0.067 | — | 8.4 |
| oa1_hifi_mask | OpenAI gpt-image-1, mask = yarn region | 1 | 0 | 0 | 0 | 0.086 | — | 18.0 |
| bfl_fill | BFL flux-pro-1.0-fill, mask = yarn region | 1 | 0 | 0 | 0 | 0.05 | — | 20.8 |
| **E4 baseline** | OpenAI gpt-image-2 edits, no fidelity control (same view, re-measured) | 4 | 2 (2) | 1 | **1 (1)** | 0.03 | 0.16 | ~15 |

## 7. What the evidence says

- **Realism is solved by the presentation-only prompt, on every capable model.** 18 of 21 draws pass all seven judge items, including the two no deterministic render ever passed. The only judge failures are the two mask modes and two FLUX.2 flex draws (window-and-room scene "CG vibe").
- **Structure is not locked by any available control.** The failure is the same on every provider: the generator re-poses or re-frames the object. Aspect drift exceeds the 10 % bar on 11 of 19 non-mask draws (0.13–0.45), and when it does not, silhouette or structure placement usually does. When a draw keeps the pose (drift ≤ 0.10 and silhouette ≥ 0.80), it almost always certifies: 5 of 6 such draws did (oa15 #1, #4; g3pro #1, #4; the exception oa1_hifi #1, whose fibre synthesis erased the stitch structure at NCC 0.14).
- **`input_fidelity=high` helps but does not lock.** gpt-image-1.5 held proportions within 0.4–9.5 % on 2 of 4 and drifted 13–18 % on the other 2; its structure correlation is the highest of any mode (0.36–0.59) and its certified draw #4 is the best-scoring image of E4 and E5 together (silhouette 0.938, drift 0.004, 22 of 22 testable stitches with worst IoU 0.85). gpt-image-1 with the same setting re-synthesised the fibre so heavily that the stitch pattern was lost.
- **Mask inpainting is the wrong tool for this transformation.** Making the yarn region editable removes the very pixels that carry the structure: both mask modes produced a shapeless fuzzy mass (silhouette 0.33 and 0.01), and FLUX Fill painted the phrase "editable region" from the prompt as text. Masking only preserves what is outside the mask, which is not where the product truth is.
- **No provider here offers structure conditioning.** BFL's depth and canny endpoints are gone (404); OpenAI and Google expose nothing that takes a depth map, normal map or edge map as a constraint. Sending the mask and normals as extra reference images is a suggestion the models may ignore, and the drift numbers say they often do.
- **Yield versus E4.** Under the same instrument on the same view, E4's gpt-image-2 certified 1 of 4; gpt-image-1.5 high-fidelity certified 2 of 4 and gemini-3-pro-image 2 of 8. At these sample sizes that is not a demonstrated improvement, and neither produced consecutive successes (oa15: draws 1 and 4; g3pro: 1 and 4). The brief's bar for a repeatable route is not met.

## 8. Remaining failure mode, stated precisely

Pose/framing drift of the whole object under an edit that is asked to change only the material. It is provider-independent, appears on 50–75 % of draws on the best modes, and is not controllable through any parameter these three APIs expose. When it does not occur, the certified structure survives the material change: the gate can then certify the image with the existing instrument. A production route from here is therefore a **gated rejection-sampling loop** (draw, validate, keep only certified) with an expected cost of about US$0.40–0.60 per certified SC image on the two best modes, and no guarantee of termination on a given draw budget; that is a cost model, not a structure lock, and it is reported as such rather than called a winner.

## 9. Winning configuration

None meets the success criterion. The two best configurations are preserved exactly (provider, model, endpoint, parameters, package digests, prompt, output digests, judge ids) in `research/e5/out/e5_manifest.json` and `run_e5.MODES` (`oa15_hifi`, `g3pro`), and the route (frozen package → mode → automatic structural + judge validation → certified/not) is runnable from `research/e5/` with the same three credentials. Nothing was integrated into production, per the brief.

## 10. Changes in the repository

- `research/e5/`: `frozen.py` (digests, `verify()`), `run_e5.py` (modes, clients, manifest, ceiling), `validate_e5.py` (both aligners, judge cache, yields), `test_e5.py` (19), `out/` (21 images, manifest, validation, 21 judge records, edit masks, E4 baseline re-measurement).
- `research/e4/validate_e4.py`: `aligned_masks(..., refine=False)` — E4 behaviour unchanged by default; the silhouette-refined option documented above. `research/e4/test_e4.py`: adversarial block runs under both aligners (66).
- `research/VISUAL_E4.md`: erratum on the sc draw split (4 camera / 6 oblique); no result changed.
- No change to `src/`, the gate, the drape solver, thresholds or `cir/`.
