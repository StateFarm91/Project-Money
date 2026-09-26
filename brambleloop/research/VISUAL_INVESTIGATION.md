# Visual chain investigation: pattern → structure → photograph, traced rather than assumed

Date: 2026-09-25. Branch `claude/visual-investigation`, from integrated `fcb982d` (4,181
passing, 0 failing — preserved, untouched). Read-only investigation; no source changed.

Every claim below is labelled **MEASURED** (I ran it or read the code/line), **OBSERVED**
(I looked at the image), **DOCUMENTED** (a lane's write-up, not re-run by me), or **UNKNOWN**.

---

## 0. The finding that reframes everything

**Every Launch-0 product is single crochet. The entire mechanics chain models only half
double.** — MEASURED

```
basket_large / basket_medium / basket_small   ['sc']
cloudline_blanket / harvest_runner            ['sc']
hexagon_coasters                              ['sc']
```
(all six `launch0.BUILDERS`, ops enumerated), against `crochet_topology.Op.kind` which is
`"hdc" | "chain" | "turn"` (`crochet_topology.py:232`) and a single cell builder
`_hdc_cell` (`:270`).

The drape tests build their fabric from `BM.cardigan("S")`, component `"body"`
(`tests/test_drape.py:38-40`) — the **benchmark cardigan**, an encoding of a real purchased
garment pattern, worked in hdc. So five waves of Visual mechanics, the equilibrium result,
the conformability metric, 144 drape tests and 28 adversarial fixtures are all measured on
**a stitch family and a product that Brambleloop does not sell.** Not one Launch-0 product
can be pushed through `crochet_topology.build` today; it would produce hdc cells for an sc
pattern, which is a different fabric.

This is not a criticism of the mechanics work — it was correctly aimed at Milestone C, the
benchmark cardigan. It is a statement about where the chain currently ends: nowhere a
customer image comes from.

---

## 1. Architecture map — what actually flows where

```
pattern (purchased / original)
   │  cir/benchmarks.py:cardigan()  or  products/*.py builders
   ▼
CIR ──compile──▶ CompileResult ──build_twin──▶ TwinModel          (cir/twin.py)
                                                 ├ cells, row_widths, width/height
                                                 ├ geometry: Revolution (rings) — round pieces only
                                                 └ calibrated: False  (catalogue-wide)
        ┌──────────────────────────────────┬────────────────────────────────┐
        │ (twin, gauge)                    │ (twin, gauge)                  │ (cir, geo, twins)
        ▼                                  ▼                                ▼
 visual/yarn.py                   visual/crochet_topology.py        visual/correspondence.py
  yarn_path → relax               build (Storck 2022 hdc cells)       predict → compare
  → write_curve_file              → settle → relaxation.relax         (Milestone C, garment:
  hand-authored _hdc_stitch       → drape.drape (1,861 lines)          neckband, pockets,
  NO CONSUMER IN src/ (MEASURED)  → pbr_scene.render (Mitsuba)         silhouette)
        │                                  │                          vs BENCHMARK_OBSERVATIONS
        ▼                                  ▼                          (hand-typed text, :203)
 yarn_layer1..5_*.png              wave5_*.png, pbr_*.png,
 yarn_drape_*.png                  topology_*.png
 (uncommitted script,
  VISUAL_WAVE5.md:590)

 ── nothing above reaches the customer image ──

 visual/brief.py + bible.py ──prompt text──▶ gateway/images.py ──▶ provider
 visual/identity.py (HUMAN model) ──reference_image (base64)──▶ provider   (model_registry:148,526)
                                                                   │
                                                                   ▼
                                                  generated listing image
                                                                   │
        ┌──────────────────────────────────────────────────────────┤
        ▼                          ▼                               ▼
 presentation.py lock_verdict    photoreal.judge/gate          identity.drift_check
 (PROVENANCE: no generative      (realism, LLM-vision)         (human face/morphology)
  op may touch product)
```

**The product's structure reaches the image model as prompt text only.** — MEASURED. The
only `reference_image` anywhere in the generation path is the canonical human model's
portrait (`model_registry.py:148`, `:526`). `image_bench.py:300` rules out providers that
cannot hold a *human identity*; nothing rules on holding a *product*.

**All four remaining providers accept reference images** — MEASURED (`gateway/images.py:
95-122`): flux-2-pro 8, gpt-image-2 16, nano-banana-2 5, seedream-v5-lite 4. Conditioning
is available and unused for the product. None is a ControlNet-style structured-map model;
they take *images* as references. Whether a structural render, given as a reference,
constrains structure is exactly the untested question.

---

## 2. Exact breakpoints

| # | Where | What breaks | Label |
|---|---|---|---|
| B1 | `crochet_topology.py:232,270` vs Launch-0 builders | Only hdc is modelled; every sellable product is sc | MEASURED |
| B2 | `tests/test_drape.py:38-40` | Mechanics object is the benchmark cardigan body, not a product | MEASURED |
| B3 | `visual/yarn.py` | Second generator; zero consumers in `src/`; produced the best-looking images via a script never committed | MEASURED |
| B4 | `yarn_layer5_*.png` vs `wave5_reconciled_camera.png` | Material realism lives on the structurally-rejected generator; structural correctness lives on a bare smooth tube | OBSERVED |
| B5 | `milestones.py:79-98` | Milestone D is a hard-coded `FAIL` with frozen prose; it reads no measurement | MEASURED |
| B6 | `drape.py:1703-1742` | The "conformability metric" is `within_row_fraction`, self-described as *necessary, not sufficient*, and not wired to D | MEASURED |
| B7 | `presentation.py:57-61, lock_verdict` | `image_to_image`, `inpaint`, `generate`, `refine` are GENERATIVE; any touching the product FAILs Product Truth | MEASURED |
| B8 | `model_registry.py:148,526` | No product reference image; structure is prompt text | MEASURED |
| B9 | `correspondence.py:90-245, :203` | Milestone C predicts garment characteristics (neckband, pockets, silhouette); no vessel/disc branch; observations are hand-typed strings, not measured from photographs | MEASURED |
| B10 | `crochet_topology.py:1193-1203`, `drape.py:1455,1535` | Contact search is all-pairs O(n²), called per iteration by the clearance guard; 10×8 (80 st) takes 13 s solve + 39 s topology per 800 iterations (VISUAL_WAVE5.md:418) | MEASURED / DOCUMENTED |
| B11 | Whole tree | No full-product 3D geometry exists at stitch level; largest object ever solved is 10×8 stitches. `TwinModel.geometry: Revolution` gives a per-round profile (radius, axial) for vessels — a coarse whole-product shape — but nothing consumes it for imagery | MEASURED |

**B7 deserves its own sentence.** The owner's stated target architecture — deterministic
geometry establishes identity, a reference-conditioned image model supplies photoreal yarn,
lighting and drape — is, by `presentation.py`'s own definition, a generative operation
whose output region is the product. The lock exists precisely to refuse that. This is not a
bug in either; it is a decision the owner has not yet made explicitly, and until it is made,
a perfect result from the target architecture fails Product Truth by construction.

---

## 3. Root-cause hypotheses, ranked by evidence

**H1 — The programme has been optimising the wrong object.** Mechanics were built for
Milestone C on the hdc benchmark cardigan. Launch-0 is sc vessels and flats. The chain
cannot represent a product it sells. *Evidence: B1, B2 (MEASURED).* Strongest; explains why
no amount of mechanical progress moved a customer image.

**H2 — Material and structure were developed on different generators and never
unified.** yarn.py got fibre, ply, fuzz (Layers 1-5); crochet_topology got linkage, contact,
equilibrium. Neither has the other's property. *Evidence: B3, B4 (MEASURED/OBSERVED).*

**H3 — Milestone D has no pass condition.** It is a declaration (B5). The one measurement
near it (B6) measures rigid-row bowing, a mechanics property, and says itself it cannot
establish "looks like crochet". So D is unpassable by any render, and its FAIL carries no
information about photographic drift. *Evidence: B5, B6 (MEASURED).*

**H4 — The intended architecture is forbidden by an existing gate.** B7. Until the owner
re-scopes the provenance lock (from "no generative pixels over the product" to "measured
structural fidelity of the generated product"), the pipeline cannot be built inside the
gates. *Evidence: B7 (MEASURED).*

**H5 — Product drift is uncontrolled because nothing conditions on the product.** B8.
Providers can take references; the only reference is a person. *Evidence: B8, provider
table (MEASURED).*

**H6 (weaker) — Scaling the current solver to a whole product is not viable as designed.**
O(n²) contact per iteration (B10). A large basket is ~70 rounds; even at ~50 sc per round
that is ~3,500 stitches ≈ 44× the 10×8, and the per-iteration search grows ~1,900×. Hours
per solve at best. *Evidence: B10 (MEASURED complexity, DOCUMENTED timing).*

---

## 4. The ten questions, answered

1. **What feeds mechanics?** `crochet_topology.Fabric` built from `(twin, gauge)` of
   `BM.cardigan("S")`, hdc only, ≤10×8 stitches. MEASURED.
2. **What feeds the best renderer?** `yarn.py.yarn_path` from the same `(twin, gauge)`,
   through an uncommitted script into Mitsuba. MEASURED. "Best" is best in *material*
   only; its structure is the netting B-705/B-707 rejected. OBSERVED.
3. **Where do they diverge?** At the stitch cell: `yarn._hdc_stitch` (hand-authored) vs
   `crochet_topology._hdc_cell` (Storck proportions). Same twin in; different yarn route out.
4. **Which derives from the CIR?** Both. Neither is the problem. The problem is that both
   model hdc and Launch-0 is sc (B1).
5. **Must the solver generate final render geometry?** No, and the evidence says it should
   not. B-704 already concluded "the deterministic layer cannot BE the photograph, it must be
   the authority constraining one." The solver's genuine outputs are *constraints*: linkage
   certified, clearance held, equilibrium reached — properties of a stitch tile, not of a
   whole product image. Producing full-product yarn geometry from it is H6.
6. **Minimum 3D fidelity before AI preserves identity?** UNKNOWN, and it is the first thing
   to measure. Hypothesis, stated so it can be falsified: silhouette + stated dimensions +
   colour placement per row/round + a correctly-scaled stitch-family texture tile are
   sufficient for reference conditioning; yarn-level mechanics are not required. Experiment
   E1 below decides it.
7. **Conditioning signals worth testing?** Given the providers take reference *images*
   (not control maps): (a) a structural RGB render of the coarse product with the sc tile
   applied; (b) the same plus a macro tile of the stitch at true scale; (c) multi-view of
   (a). Depth/normal/edge maps are worth testing only if a provider dialect accepts them —
   UNKNOWN for these four; none of their entries claims it.
8. **The purchased benchmark?** Its seller photographs are ground truth for the REAL
   object's characteristics — that is what Milestone C already uses them for. They must not
   be conditioning inputs (copyright; and it would test whether we can copy a photo, not
   whether we can render a pattern). Use them to (i) validate `predict()` against a real
   made object and (ii) grade the AI image with the same four-valued rubric. Overfitting is
   avoided by scoring at characteristic level, never pixel level, and by running the same
   rubric on at least one Launch-0 vessel once a physical sample exists.
9. **Is Milestone D measuring the right property?** No — and this is proven rather than
   argued: D is prose (B5). The metric beside it measures rigid-row bowing and disclaims
   sufficiency in its own docstring (B6). Neither measures "photographic presentation without
   structural drift". The correct measurements are §7 M1-M7: structural fidelity of the
   *generated image* against the twin's prediction. D should not be weakened; it should be
   given a definition for the first time.
10. **Dead-end complexity** — §6 "abandon / demote".

---

## 5. Recommended target architecture

Three layers, each with a named output and a named check. Nothing "beautiful" passes
without the middle layer's numbers.

**Layer 1 — Deterministic structure (CA$0, no Mitsuba, no drape).**
From the twin: for a vessel, lathe `TwinModel.geometry.rings` (radius, axial per round)
into a surface; for a flat piece, a rectangle of `width_cm × height_cm`; for a garment,
the panel outlines the CIR already carries. Paint it with (a) colour by row/round from the
CIR's colour changes and (b) a stitch-family texture tile at the gauge's true scale — sc
for Launch-0, from a *small* Storck sc cell (a bounded extension of `crochet_topology`,
not a full solve). Output: `structural_render.png` + `structure.json` (dimensions,
ratios, colour map, stitch family, construction cues such as joined-round seam).

**Layer 2 — Generative presentation, conditioned.** Provider call with reference images:
the structural render, the stitch macro tile, and (when a model is in frame) the human
identity pack. Scene, light, pose, environment are free; the product is not.

**Layer 3 — Product Truth on the OUTPUT image**, measured against `structure.json`:
M1-M7 below, four-valued, fail-closed on unmeasured. The B-703 ratio lock (2%) is the
spine; Milestone C's `correspondence` framework is the shape.

**The decision this needs from the owner:** re-scope `presentation.py`'s provenance lock.
Today it guarantees "no generative pixels over the product". The target architecture can
only guarantee "generated product measured within tolerance of the certified structure".
That is a weaker provenance guarantee and a stronger fidelity guarantee. It should be a
recorded decision, not a quiet edit; I have not made it.

---

## 6. Retain / simplify / abandon

**Retain (load-bearing):** CIR → twin; `Revolution` geometry; `correspondence` four-valued
rubric; B-703 ratio lock; `photoreal` gate; `identity` drift check; provider gateway with
reference conditioning; `presentation` lock *as a mechanism* (re-scoped); Storck cells as
the source of a truthful stitch tile; the 28 adversarial topology fixtures.

**Demote (keep, stop treating as the path to imagery):** `drape.py` — a validator of stitch
tile mechanics, not a producer of product geometry. Stop re-deriving `CALIBRATED_BENDING`,
stop the cantilever/ASTM inversion, do not attempt full-product drape (H6). Stage 0 stays
deferred; it is calibration, not imagery.

**Abandon:** `visual/yarn.py` as a generator (dead in `src/`, wrong topology by the
repository's own finding; keep only what the Layer 1-5 material work learned, as Mitsuba
material settings, if the macro tile is ever rendered physically); Milestone D as prose;
the hdc swatch as a proxy for any Launch-0 product; continuous topology validation and the
`_encirclement` false-negative fix as prerequisites for imagery.

---

## 7. Acceptance metrics for pattern → 3D → photograph → Product Truth

All computed on the *generated image* against `structure.json`; each is PASS / FAIL /
NOT_OBSERVABLE / INDETERMINATE; any FAIL fails; any unmeasured required metric fails.

| | Metric | Source of truth | Tolerance |
|---|---|---|---|
| M1 | Silhouette & aspect ratios (overall; per component; vessel diameter:height) | twin / Revolution; B-703 | 2% (existing) |
| M2 | Stitch family (sc/hdc/dc) and stitch scale at stated size | CIR gauge | family exact; scale ±10% |
| M3 | Colour placement by row/round | CIR colour changes | ±1 row/round |
| M4 | Construction cues present where the CIR makes them (joined-round seam, BLO ridge, turning-chain edge) and absent where it does not | CIR ops | presence |
| M5 | No invented feature (pocket, button, edging, motif the CIR does not make) | `correspondence` CONTRADICTS | zero |
| M6 | Photographic realism gate | `photoreal.gate` (existing) | existing |
| M7 | Human identity drift (when modelled) | `identity.drift_check` (existing) | existing |

M1-M5 are the definition Milestone D never had. M2-M5 need one new judge each; the
judge is asked what it sees, never whether it agrees (the repository's own rule).

---

## 8. Minimum experiments to falsify or confirm

**E1 — Does reference conditioning preserve structure at all?** (decides everything)
Build the coarse Layer-1 render for `basket_large` (lathe of `Revolution.rings`, sc tile
at gauge scale, single colour) — CA$0. Submit as a reference to flux-2-pro and gpt-image-2
with a plain product-photo brief, 10 samples each (~US$0.50). Score M1, M2, M3 on every
sample. *Falsified if* median M1 drift > 2% or M2 family flips. *Confirmed if* ≥8/10 pass
M1-M3. This single result tells us whether Layer 1 fidelity can be coarse.

**E2 — Does yarn-level structure in the reference help?** Same as E1 with the reference
replaced by `wave5_reconciled_camera.png`-class detail (needs the sc cell first). Run only
if E1 fails; it costs a bounded topology extension.

**E3 — Benchmark end to end.** Cardigan: `correspondence.predict` → Layer 1-2 image →
grade with the same rubric the seller photographs were graded with. Reports drift per
characteristic. ~US$1.

**E4 — Milestone D redefinition proof (CA$0).** Run M1-M5 on `wave5_reconciled_camera.png`
and `yarn_layer5_*.png`. Both should FAIL on measurable grounds (no stated size; hdc not
sc; no colour map) — showing the new definition rejects today's best images for reasons
that can be stated, which the current D cannot do.

Everything here is isolated to this branch and reads production nothing.

---

## 9. Shortest credible path to Launch-0-quality imagery

1. **Owner decision:** re-scope the provenance lock (§5). Minutes. Everything waits on it.
2. **Layer 1 for three product shapes** (vessel lathe, flat rectangle, sc tile): one lane,
   CA$0, no Mitsuba.
3. **E1.** ~US$1. If it passes, the architecture is confirmed and the mechanics programme
   is decoupled from imagery. If it fails, E2 tells us how much structure the reference
   needs.
4. **Wire M1-M7** as the gate on generated images; make Milestone D read them.
5. **Generate Launch-0 candidates**; owner review remains required for the first listings
   (FIRST_CUSTOMER_GATE rule unchanged).

What this path does *not* do: calibrate the twin (still False, still the largest unmeasured
risk — image dimensions are predictions from gauge), prove sc mechanics, or close
`_encirclement`. Those are real and are not on the path to a truthful listing image.

---

## 10. UNKNOWN, kept as UNKNOWN

- Whether any of the four providers preserves stitch family from a reference image. (E1.)
- Whether a provider dialect accepts depth/normal/edge control maps. Not claimed by any entry.
- Whether a Storck sc cell reproduces sc fabric faithfully; the paper covers sc, the tree
  does not yet.
- Where the B-703 ratio lock is implemented; `presentation.py` carries provenance, the
  ratio code was not located in this pass.
- The true finished dimensions of any product (`twin.calibrated` False). Every centimetre
  in every image is a gauge prediction.

---

## Corrections after adversarial re-check (2026-09-26)

Three claims above were wrong or overstated; the full table is in
`VISUAL_ARCHITECTURE_DECISION.md` §2. In brief: (1) mechanics is not "hdc-only" — `build()`
**accepts an sc twin and silently emits hdc cells**, which is worse; (2) `presentation.py`'s
lock is **never called**, so the conflict I described as forbidding the target architecture
is latent, not active; (3) the contact search runs every 12 iterations, not every iteration —
the O(n²) conclusion stands, the constant was overstated. E1 was run: see the decision
document for design, result (confirmed on GPT Image via the edits endpoint, falsified on FLUX
via `image_prompt`), cost (US$0.22 list) and what it does not establish.
