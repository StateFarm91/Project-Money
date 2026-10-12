# Product-only Visual V1 graduation — blind Brambleloop product (Heirloom Cable Throw)

**Verdict: PRODUCT-ONLY VISUAL V1 = NOT LOCKED.** The blind deterministic chain passed and was
frozen before any spend; sixteen paid draws on the strongest evidenced OpenAI route produced
**no certified image**. The blocker is localised to **image generation (provider capability
at the stitch-structure scale)**, not to Product Truth, the CIR, the reconstruction, the
representation or the validators. Evidence preserved; no threshold moved; no reading retried
to change a verdict; no PASS manufactured.

Branch `claude/visual-investigation`; frozen checkpoint `9cf29f5`; closing commit in git.
Everything measurable is in `research/v1grad/out/` (`v1grad_manifest.json` is the provenance
record). External spend **US$4.86** of the US$5.00 ceiling (generation US$4.37, reads and
judgements US$0.49; OpenAI only). Google intentionally unfunded and not substituted.

## 0. Candidates and provenance

Brambleloop-original designs found in the repository (all committed 2026-09-17/18, before this
benchmark; none derived from Bench1 or Bench2, no purchased pattern):

| candidate | source | why not / why |
|---|---|---|
| **Heirloom Cable Throw** (`heirloom-cable-blanket`) | `products/texture.py::build_cable_throw`, commit 41c9356 | **selected**: class A, one complete component, 18 cable columns crossing every 4th row on back-post ribbing (the most demanding stitch structure the registry can express), 144 x 121, never made, no photograph exists, fourth-ranked portfolio product |
| Bobble Floor Pillow Cover | `products/texture.py` | class B; the back panel and the cover's assembly are not in the CIR (Product Truth incomplete) |
| Market baskets (3 sizes) | `products/vessels.py` | the "trivial basket" case the brief excludes when a stronger product exists |
| Chunky Ribbed Scarf | `products/texture.py` | a plain strip of post-stitch ribbing |
| Mosaic / graphghan / motif catalogue, Nordic Forest throw | `products/builder.py`, `nordic_forest.py` | flat colourwork panels; weaker structural test than cables |
| an original garment | — | none exists: `cir/grading.py` is a primitive; the only cardigans in the repository are the purchased benchmarks |

**Firewall (recorded in `product_truth.json` before construction):** allowed inputs = the
design source, the stitch registry, compiler and twin, the relief rule (visual.fabric,
charts.relief) and code-only generalised capabilities from E1–E5/Bench1/Bench2; forbidden
sources listed and not used; no web search. **Quarantine:** a 6 KB chart image found in the
session scratchpad was moved to `v1grad_quarantine/` unopened; the production artifact store's
93 image blobs were neither opened nor matched to a product. **EXTERNAL FINISHED-PRODUCT VISUAL
REFERENCES USED BY PRODUCT CONSTRUCTION OR GENERATION: NONE.** No independent finished-product
image of this design exists, so there is nothing to reveal after certification.

## 1. Product Truth (`research/v1grad/product_truth.py`, `out/product_truth.json`)

From the CIR, the registry, the compiler and the twin only, every fact cited to its source:
throw blanket, one flat rectangle, bottom-up turned rows, no shaping/seams/openings/edging/
closures; gauge 16 sts x 18 rows per 10 cm (stated in sc), 5 mm hook; worsted acrylic, one
colour (cream #FAF6EB); stitch family post-stitch ribbing + 2x2 cable crossings on a sc
foundation row, all both-loop; pattern `bpdc 2, fpdc 4, bpdc 2` x 18, crossing row `bpdc 2,
cable2x2, bpdc 2` x 18, 3 plain rows then 1 crossing row, 30 blocks; 144 sts x 121 rows, 30
crossing rows at 5, 9, …, 121; 17,424 cells. Derived: 90.0 x 128.9 cm (aspect 1.432), column
pitch 5.0 cm, cable and channel 2.5 cm each, crossing period 4.22 cm, 1,716.6 m of yarn.
**Ten deterministic cross-checks pass.** Uncertainties declared: the gauge is stated in sc while
the fabric is post dc (height from the registry's row-height ratio, uncalibrated); cable
fabric draws in (the design's own note); crossing direction unspecified by the design (the
reference declares the left pair in front); no edging specified (none drawn).

**Company defect found and fixed generally (D-V1-3):** `visual.fabric.texture_signature` read
this fabric as flat because it measured unworked loops only. It now measures relief stitches
(post, bobble, crossing, star): textured, columns vs checkered, along-row period. Regression
test `tests/test_fabric_relief.py` (8 checks) covers the throw, the pillow, the scarf, a plain
panel and back-loop ribbing.

## 2. Deterministic representation (`research/v1grad/reference.py`)

The whole throw laid flat, straight on, at counts x gauge (1024 x 1536 frame, 10.24 px/cm):
every one of the 17,424 cells drawn from the twin, rows horizontal, fpdc ribs raised, bpdc
channels recessed, each 2x2 crossing drawn as two strand pairs swapping over their row,
relief height field → normal map, mask, region map (cable columns / channels / foundation
row). Validation: every cell, row and crossing drawn; extent 90.0 x 128.9 cm; every region
present. Later versions re-state the same frozen Product Truth (D-V1-4): **ref2** stronger
column/channel contrast and relief gain; **ref3** the throw folded in half across its length
with the upper half tucked underneath (rows 1–61 visible, fold at the top), landscape 1536 x
1024 at 14.24 px/cm (column pitch 71 px, crossing 60 px). Each version passes its own gate.

## 3. Cable identity + gauge instrument and the freeze (`research/v1grad/gate.py`)

Measures, on the aligned candidate: the fundamental period of the along-row profile of |gx|
(column pitch); the period of the along-column profile of diagonal gradient energy inside the
cable strips (crossing period); column dominance (gx²/gy²); pitch ratio. A priori bars:
lattice peak ≥ 0.10, column dominance ≥ 1.20, pitch/crossing ratio 0.83–1.65 (derived 1.18
± 30 %), gauge ± 35 %. Self-test (`out/cable_identity_selftest.json`): reference PASS/PASS
(51 vs 51.2 px, 44 vs 43.2 px); rotated quarter turn FAIL (dominance 0.13); plain rows FAIL;
Bench2 star truth FAIL; Bench1 waffle FAIL; 2x scale identity PASS, gauge FAIL.

**BLIND DETERMINISTIC CHAIN: PASS** (`out/v1grad_manifest.json`): Product Truth compiles and
cross-checks; CIR validates; reference draws every cell/row/crossing at Product Truth's
dimensions from the frozen digest; instrument passes the reference and rejects the controls;
reference passes its own gate; firewall statement true. Digests of every input, output and
code file and the exact generation package recorded; frozen at commit `9cf29f5` before the
first paid call.

## 4. Generation (gpt-image-1.5, `input_fidelity=high`, quality medium, rgb + mask + normal)

Prompt v1 = Bench1's certified round-2 presentation wording (dark cloth, worsted yarn,
"stitch texture exactly as drawn"); prompt v2 adds a fidelity sentence naming the drawn
columns and edges (D-B2-4 rule, no counts or stitches named).

| draw | ref / prompt | IoU | aspect drift | gauge ratio col / cross | cable identity / gauge | reader texture / edging / type | judge fail | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | ref / v1 | 0.942 | 0.058 | 1.33 / 1.36 | PASS / FAIL | ribbed / none / – | folds | FAIL |
| 2 | ref / v1 | 0.816 | 0.187 | 1.78 / 0.39 | FAIL / FAIL | ribbed / none / other | folds | FAIL |
| 3 | ref / v1 | 0.935 | 0.077 | 1.56 / 1.25 | PASS / FAIL | cabled / other / throw | none | FAIL |
| 4 | ref / v1 | 0.944 | 0.051 | 1.43 / 1.27 | PASS / FAIL | cabled / none / throw | folds | FAIL |
| 5 | ref2 / v1 | 0.906 | 0.090 | 1.74 / 1.53 | PASS / FAIL | cabled / other / other | none | FAIL |
| 6 | ref2 / v1 | 0.893 | 0.006 | 1.64 / 0.65 | FAIL / FAIL | cabled / other / – | folds | FAIL |
| 7 | ref2 / v1 | 0.933 | 0.093 | 1.31 / 0.46 | FAIL / FAIL | ribbed / other / other | folds | FAIL |
| 8 | ref / v2 | 0.940 | 0.056 | 1.23 / 0.42 | FAIL / FAIL | ribbed / none / throw | none | FAIL |
| 9 | ref / v2 | 0.963 | 0.020 | 1.37 / 0.56 | FAIL / FAIL | ribbed / none / throw | folds | FAIL |
| 10 | ref / v2 | 0.929 | 0.079 | 1.56 / 0.79 | FAIL / FAIL | ribbed / none / other | folds | FAIL |
| 11 | ref3 / v1 | 0.962 | 0.052 | 1.22 / 1.45 | PASS / FAIL | cabled / other / – | none | FAIL |
| 12 | ref3 / v1 | 0.942 | 0.044 | 1.28 / 0.67 | FAIL / PASS | cabled / none / – | folds | FAIL |
| 13 | ref3 / v1 | 0.941 | 0.061 | 1.21 / 1.02 | FAIL / PASS | cabled / none / other | none | FAIL |
| 14 | ref3 / v1 | 0.977 | 0.029 | 1.24 / 0.42 | FAIL / FAIL | waffle / other / – | none | FAIL |
| 15 | ref3 / v1 | 0.938 | 0.059 | 1.35 / 1.23 | PASS / PASS | (reader answered nothing) | folds UNKNOWN | UNKNOWN |
| 16 | ref3 / v1 | 0.942 | 0.049 | 1.19 / 0.95 | PASS / PASS | waffle / other / throw | none | FAIL |

Yield **0 / 16**; cost per certified image undefined. Judge (pinned gpt-5 D judge) passed
realism on 8 of 16 and failed "folds naturally" on 7 (ruler-straight, square edges reading as
computer-generated); the reader (pinned gpt-5) returned an empty answer on draw 15 (recorded
as UNKNOWN, not retried).

## 5. What the evidence says (OBSERVE → HYPOTHESIS → EXPERIMENT → MEASURE)

- **Observed:** at the whole-throw scale (51 px column pitch) every draw places the columns
  1.3–1.8x too far apart (12–14 columns for the 18 designed) and most rewrite the 2x2
  crossings as rib, ladder, moss or waffle textures; several add an edge border the design
  does not have. Silhouette and proportions are kept (IoU 0.89–0.98 on 15 of 16).
- **H1 (package contrast):** stronger column/channel contrast would hold the columns. **Refuted**
  (ref2: 1.3–1.7x, more borders).
- **H2 (fidelity prompt):** naming the drawn columns and edges would hold them. **Refuted**
  (prompt v2: columns 1.2–1.6x, crossings lost on all three).
- **H3 (pixel scale):** the generator keeps stitch structure only when the drawn repeat is near
  its own preferred scale (~70–95 px here). **Partly supported:** at the 71 px folded pitch the
  gauge came within band on 4 of 6 and both identity and gauge passed on 2 of 6, versus 0 of
  10 at 51 px. But the folded view lost product identity for the reader (product type
  unreadable or "other" on 4 of 6, borders on 3 of 6) and the judge read the flat squared
  edges as generated.
- **Root cause:** gpt-image-1.5 with high input fidelity preserves outline and coarse layout and
  re-synthesises the surface at its own stitch prior; the deterministic package cannot force
  18 columns into 1024 px. Same finding as Bench1 (stitch scale 1.6–3.6x) and Bench2 (texture
  rewritten), now measured on a Brambleloop-original product with no photograph in the loop.

## 6. Gate corrections made during the run (recorded, no verdict manufactured)

- D-V1-5: the reader answers cable direction relative to the piece's longer side as shown; for
  the folded view the expectation was corrected to "across_the_width" and all sixteen
  candidates re-evaluated offline from their stored readings (`run.py regate`). It certified
  nothing.
- The reader's empty answer on draw 15 and the judge's UNKNOWN were left as they are.

## 7. Reusable improvements recorded

1. `visual.fabric.texture_signature` sees relief stitches (module fix + regression test).
2. A blind-benchmark firewall record (allowed inputs with digests, forbidden-not-used list,
   quarantine, statement) as a Product Truth field, and a freeze command that refuses
   generation until every deterministic check is PASS.
3. The cable identity + gauge instrument (fundamental-period rule with harmonic rejection,
   strip-restricted crossing period, column dominance) with self-test controls.
4. Reference versioning that re-states the same frozen Product Truth (digest-checked before
   use) for presentation experiments (contrast, folded view).
5. Reader expectations that follow the presentation geometry; offline re-evaluation that
   never touches a reading.
6. Cost/yield: US$0.27 per 1024x1536 gpt-image-1.5 draw, US$0.03 per read+judge; 0/16.

## 8. Localised blocker and the shortest credible next experiment

**Blocker: image generation / provider capability.** The generator will not reproduce 18
cable columns with 2x2 crossings across a 1024-px-wide throw from a structural package; at a
scale it can hold (≥ ~70 px per repeat) the whole product no longer fits the frame, and a
folded partial view loses the product's identity for the reader.

**Shortest credible next experiment (≈ US$1.50, no new research wave):** two-stage
presentation on the same frozen chain — generate the folded view (ref3, where structure held
on 2 of 6) with a presentation sentence that keeps the throw recognisably a throw (a fold
visible, edges as fabric edges, no border), 4 draws; gate unchanged. If the reader then reads
"throw" and the judge passes folds, the route certifies without touching Product Truth. If
not, the provider is the ceiling for this product at listing resolution, and the honest
production path is a photograph of a physical sample (the company's Class-A-to-sample step),
not more generation.

## 9. Tests, branch, checkpoint

`research/v1grad/test_v1grad.py` 40 checks passing; `tests/test_fabric_relief.py` 8/8;
`tests/test_texture.py`, `tests/test_visual.py`, `tests/test_deliverable_qa.py` green. Full
suite result in BUILD_STATE. Isolated branch `claude/visual-investigation`; integrated branch
untouched at `fcb982d`; checkpoints `ad81e30`, `9cf29f5` and earlier preserved.

## 10. Confidence statement

High confidence that the recorded chain is blind (no finished-product image at any stage),
deterministic and reproducible, that the instrument recognises the designed structure and
rejects the controls, and that every rejection is for its stated measured reason. No
confidence claim about a hero: none exists. Product-only Visual V1 is not ready to lock, and
the reason is the provider's stitch-structure fidelity at listing resolution.
