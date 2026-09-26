# Visual architecture decision: pattern → structure → photograph, with E1 run

Date: 2026-09-26. Branch `claude/visual-investigation`, from integrated `fcb982d`, which is
untouched. Labels: **MEASURED** (ran it / read the executing line), **OBSERVED** (looked at the
image), **DOCUMENTED** (a lane's write-up), **UNKNOWN**.

---

## 1. Verified architecture map — the actual current data flow

```
CIR ─compile─▶ TwinModel ────────────────────────────────────────┐
  (cir/twin.py: cells, row_widths, width/height, geometry:Revolution, calibrated=False)
        │ (twin, gauge)                    │ (twin, gauge)          │ (cir, geo, twins)
        ▼                                  ▼                        ▼
 visual/yarn.py                   visual/crochet_topology       visual/correspondence
  hand-authored hdc route          Storck hdc cell -- and ANY     Milestone C, garment only,
  NO consumer in src/              stitch becomes hdc (see §2)    hand-typed observations
  (uncommitted script → PNGs)      → relaxation → drape → pbr_scene (Mitsuba)
                                   object: BM.cardigan("S"), ≤10x8 stitches

 ── none of the above reaches a customer image ──

 brief/bible prompt text ──▶ gateway/images.generate ──▶ provider ──▶ listing image
 identity.py HUMAN portrait ─┘ (only reference ever sent)          │
                                                            photoreal.gate, identity.drift_check
                                                            presentation.lock_verdict: NEVER CALLED
```

## 2. Corrections to the first report — three, one of which makes it worse

| Claim in report 1 | Re-check | Correction |
|---|---|---|
| mechanics is "hdc-only" | ran `crochet_topology.build` on the sc basket twin | **It accepted the sc twin and emitted `{'hdc': 24, 'turn': 3}`.** Not a limit: a silent relabel. Any Launch-0 product pushed through mechanics would have been validated as a fabric the pattern does not make. MEASURED |
| `presentation.py` "forbids" the target architecture | grep for callers of `lock_verdict` / `PresentationPlan(` | **No caller anywhere.** The prohibition is declared and never enforced; the conflict is latent. An unenforced lock is itself the docstring-asserts-a-property defect. MEASURED |
| contact search "per iteration" | read `drape.py:1452-1460` | every 12 iterations plus on guard trips. O(n²) conclusion stands; my constant was ~12× overstated. MEASURED |
| BFL provider "8 references" | read `images.py:455-467` | dialect sends `refs[0]` only, as a semantic `image_prompt`. Table says 8; code sends 1. MEASURED |

Everything else re-verified: all four Launch-0 candidates and all six variant builders are `sc`
(MEASURED); drape's object is `BM.cardigan("S")` body (MEASURED, `tests/test_drape.py:38-40`);
`yarn.py` has no consumer (MEASURED, broadened grep); Milestone D is hard-coded prose
(MEASURED); `within_row_fraction` self-describes as necessary-not-sufficient (MEASURED); all
four providers accept references but none is sent a product (MEASURED).

## 3. Root cause — why pattern → truthful photoreal image cannot happen today

Five independent gaps, any one of which alone breaks the chain; all five are present:

1. **No structural product representation is ever built for a Launch-0 product.** The one
   generator that works is bound to the hdc benchmark cardigan and relabels everything else.
2. **Nothing conditions the image model on the product.** The product is prompt text.
3. **Nothing measures the output against the product.** The only gates are realism and human
   identity. Milestone D has no pass condition.
4. **The one rule that speaks to this (`presentation.py`) is unenforced and, if enforced,
   forbids the working path** rather than distinguishing a redesign from a validated
   presentation.
5. **The twin is uncalibrated**, so even a perfect image can only be checked against a
   prediction.

## 4. Architecture decision: **C, with one hybrid clause** — on evidence, not elegance

**C: lightweight deterministic Product Truth geometry conditions AI photography; detailed
mechanics is an independent validator, never the image generator.**

Evidence for C over A and B:

- **E1 (§5) shows a coarse deterministic reference is sufficient** to preserve silhouette,
  proportion, stitch family, colour placement and construction cues through a
  reference-conditioned provider, with no yarn geometry and no mechanics: 4/4 on the working
  provider, under scene, hand and distractor variation. A would spend hours per product
  (§2 scaling) to produce geometry E1 did not need.
- **A cannot represent a Launch-0 product at all today** (§2, relabel). B keeps mechanics in
  the image path and inherits that.
- **Mechanics still has a truth job** (the hybrid clause): the certified stitch *tile* —
  linkage, clearance, gauge envelope — is the ground truth a stitch-family / stitch-scale
  judge is calibrated against, and the calibration path (Stage 0, physical samples) runs
  through the twin, not through pixels. Mechanics validates; it does not draw.

## 5. E1 — design and actual result

**Question.** Can a reference-capable provider turn a deterministic structural reference into
a materially more photoreal presentation while preserving product identity?

**Reference.** `research/e1/structural_reference.py` → `out/basket_large_structural.png` +
`basket_large_structure.json`. Built from the twin alone: the 70-ring `Revolution` profile
(24-round disc base to r=12.73 cm, 46-round straight wall to 23.0 cm) lathed and flat-shaded,
orthographic; colour by round **read from CIR op attributes** (wine at rounds 44–45 and 56–57,
cream elsewhere); one PROCEDURAL tick per stitch at gauge pitch (18 st / 20 rows per 10 cm)
as a density cue, declared as not mechanics-derived. Silhouette ratio 1.107. No Mitsuba, no
drape, no `crochet_topology`. `twin.calibrated` False, so every centimetre is a prediction.

**Arms.** One prompt naming NO stripe count, position, colour band or stitch family, so any
of those in the output came from the reference or from nowhere.
A: reference + prompt, flux-2-pro ×3. B: prompt only, flux-2-pro ×2 (control).
C: reference + prompt, gpt-image-2 ×2. D: gpt-image-2, hands lifting a cloth from it.
E: gpt-image-2, among wooden toys and a plant. **Nine images, US$0.22 at list price**, hard cap
$0.25, manifest in `out/e1_manifest.json`. The providers' own bills are the authority.

**Result — MEASURED (`out/e1_measurements.json`) and OBSERVED.**

| arm | provider / mode | stripes present | stripe heights (frac of visible height) | stitch family | silhouette | verdict |
|---|---|---|---|---|---|---|
| A0–A2 | FLUX, `image_prompt` on generation endpoint | 0/3 (wine px 0.000–0.002) | — | chunky, ≫ gauge | squat bowls | **not preserved**; A1/A2 invented grey and blue/mustard bands |
| B0–B1 | FLUX, no reference | 0/2 | — | chunky | squat | control; indistinguishable from A |
| C0 | GPT Image 2, `/images/edits` | yes (0.0043) | **0.72, 0.41** vs truth 0.70, 0.44 | fine sc | ≈1.1 | preserved |
| C1 | same | yes (0.0088) | **0.71, 0.38** vs 0.70, 0.44 | fine sc | ≈1.1 | preserved; lower stripe 6% low |
| D0 | same, hands + cloth | yes | ≈0.42, 0.70 (OBSERVED) | fine sc | ≈1.1 | preserved under occlusion |
| E0 | same, distractors | yes | ≈0.40, 0.68 (OBSERVED) | fine sc | ≈1.1 | preserved among objects |

Truth: wine at 0.435–0.457 and 0.696–0.717 of height. Stripe *width* (two rounds, ≈4% of
height) is also preserved in all four GPT outputs. Interior stripe visible through the open
top, as in the reference.

**Conclusion.** E1 is **confirmed on GPT Image 2 via the edits endpoint and falsified on
FLUX 2 Pro via `image_prompt`.** The most probable cause of the asymmetry is **conditioning
mode**, not model quality: the OpenAI dialect uploads the reference to an *edit* endpoint
(image-to-image); the BFL dialect passes a semantic image prompt to a *generation* endpoint,
and its outputs match its own no-reference control. Whether BFL exposes an edit mode is
**UNKNOWN** from local evidence (no route list in the cached swagger); it is E2-class work and
not needed for Launch-0.

**What E1 does NOT establish.** Stitch *scale* (stitches per cm) — a photograph cannot give
centimetres without a known object; the dimension-free check is counting stitches on the top
round (144 expected) and no judge did that yet. Nor does E1 establish real dimensions: the
twin is uncalibrated. **None of the nine images is a PASS under the Milestone D definition in
§8**: C1 is FAIL (lower stripe outside the 3% tolerance by a crude pixel measure); C0/D0/E0
are UNKNOWN (calibration). This is stated so that no one reads E1 as "imagery is solved".

## 6. Images produced and what produced each

- `research/e1/out/basket_large_structural.png` — `structural_reference.py`, twin only.
- `out/gen/A0..A2_flux-2-pro.jpg`, `B0..B1_flux-2-pro.jpg` — `run_e1.py`, FLUX 2 Pro.
- `out/gen/C0..C1_gpt-image-2.png` — `run_e1.py`, GPT Image 2 edits, reference attached.
- `out/gen/D0_gpt-image-2.png`, `E0_gpt-image-2.png` — inline probe, same provider/mode.
- `out/e1_contact_sheet.png` — reference | A0 | B0 | C0 | C1, `measure_e1.py`.
All are experiment artefacts, not listing assets; none is approved for anything.

## 7. Minimum `sc` implementation for Launch-0

Three items, in order of necessity, and the first is a *removal*:

1. **Stop the silent relabel** (required, not in my boundary — exact diff for the integrator):
   `crochet_topology.build` must raise on any stitch whose cell it does not model, at the
   point where it emits `Op("hdc", ...)` (`:571`), e.g.
   `if getattr(c, "stitch", "hdc") != "hdc": raise NotImplementedError(f"{c.stitch}: no cell")`.
   Product Truth wins: an unmodelled stitch is refused, not substituted.
2. **For imagery: nothing more.** E1 preserved `sc` from a procedural density cue at gauge
   pitch with the family unnamed in the prompt. A Storck sc cell is *not* on the path to a
   Launch-0 image.
3. **For validation: a Storck sc tile** (the paper covers sc; bounded — one cell builder and
   its linkage assertion on a ≤5×5 swatch) so that the stitch-family / stitch-scale judge has
   a certified tile to be checked against, and so the mechanics validator can run on the
   product's own fabric. This is the hybrid clause of §4, and it is post-E1 work.

## 8. Milestone D, defined — executable in `research/e1/milestone_d_spec.py` (17 checks green)

D claims: *Brambleloop possesses a structurally trustworthy representation adequate for
downstream presentation, and a presentation made from it preserved the product.* Eight
properties, four-valued, never averaged:

| property | evidence | tolerance / rule |
|---|---|---|
| silhouette_proportion | ratio on image vs twin | 2% (B-703, reused) |
| stitch_family | judge vs CIR | exact; hdc-for-sc is FAIL, not a near miss |
| gauge_scale_confidence | counted stitches on a known round vs CIR | 10%; **UNKNOWN whenever `twin.calibrated` is False** |
| topology_construction | cues the CIR makes (base type, wall, seam, opening) | all present |
| shaping_openings | neckline / armholes / handles | NOT_APPLICABLE when the product has none, recorded |
| colour_regions | count and position of every colour boundary | 3% of height each |
| conditioning_reference_complete | does `structure.json` carry every field above | all present |
| final_image_product_truth | conjunction of the image-side properties | UNKNOWN if no image assessed |

Overall: any FAIL → FAIL; else any UNKNOWN → UNKNOWN; else PASS. **While the catalogue is
uncalibrated the best possible verdict is UNKNOWN**, and the spec proves that on E1's own
outputs. `twin.calibrated == False` stays truthful by construction. Not wired into
`milestones.py`; that is an integration change for the integrated branch.

## 9. Presentation gate, refined — executable in `research/e1/presentation_gate_spec.py`

The invariant is kept: a generative operation over the product can invent a product. The
refinement adds the one thing the current rule cannot express — evidence:

- **UNAUTHORISED REDESIGN** — generative over the product with no certified reference
  declared, OR never revalidated, OR revalidation FAILED, OR conditioned on a *different*
  reference than the plan certifies (digest mismatch).
- **AUTHORISED PRESENTATION** — generative over the product, conditioned on the certified
  reference (by digest), and the output's Milestone D assessment PASSED.
- Revalidation UNKNOWN → UNKNOWN: blocks like FAIL, differs only in next action. E1's best
  outputs land here today.
- Structure-preserving operations are unchanged and need neither.

Conditioning is a claim; revalidation is the proof. Fail closed everywhere. This is the
decision the owner has to make explicit; the spec is what it would look like.

## 10. Exact role remaining for mechanics / drape

- **Validator of the stitch tile**: linkage certified, clearance held, equilibrium reached,
  on ≤10×10 swatches of the product's *own* stitch family (after §7.1 and §7.3).
- **Truth source for the stitch-family / stitch-scale judge**: a certified tile render is the
  reference the judge is checked against.
- **Calibration path**: physical samples (Stage 0, deferred by D7) compare against the
  twin/mechanics prediction, never against a generated image.
- **Not**: a producer of full-product geometry; not on the image path; not a Milestone D input
  except through the tile.

## 11. Retain / demote / abandon

**Retain:** CIR → twin; `Revolution`; `correspondence` rubric (extend to vessels: it is the
shape of §8's judge); B-703 ratio lock; `photoreal.gate`; `identity.drift_check`;
`gateway/images` with the edits dialect; `presentation.py`'s classification lists; Storck cells
as the tile source; the 28 adversarial fixtures.
**Demote:** `drape.py` and `relaxation.py` to tile validation; stop re-deriving B; no
cantilever; no full-product drape; Stage 0 stays deferred and off the imagery path.
**Abandon:** `visual/yarn.py` as a generator; Milestone D as prose; the hdc cardigan swatch as
a proxy for anything sold; `image_prompt` as the FLUX conditioning mode for product work.

## 12. UNKNOWNs, kept as such

- Real dimensions of any product (`twin.calibrated` False) — the long pole for a PASS.
- Stitch scale in generated images (needs a stitch-count judge on a known round).
- Whether BFL offers an edit/structural mode reachable from this gateway.
- Whether the E1 result holds for a flat product (blanket, runner: no Revolution profile) and
  for the coaster set (4 pieces — piece count is a new property).
- The benchmark: the purchased cardigan's seller PDF and photographs are **not accessible
  from this environment** (only its numeric encoding and hand-typed observations are). E3 cannot
  run here. Nothing about them was inferred.
- Sample size: n=4 GPT, n=5 FLUX. Enough to decide the architecture; not enough for a rate.

## 13. Estimated work to the first trustworthy full-product AI photograph

| step | size | blocks |
|---|---|---|
| Owner decision: adopt §9's distinction | minutes | everything |
| §7.1 relabel guard | 1 hour + tests | truth |
| Layer 1 for flat products (rectangle + colour map) and coaster set (piece count) | 1 lane | Launch-0 coverage |
| Judges for M1–M6 (pixel measures + vision prompts asked what they see, never whether they agree) | 1 lane | any PASS |
| Wire §8 into `milestones.py`, §9 into `presentation.py`, both into the release chain | 1 lane | gates |
| **One physical sample of one product, measured** (Stage 0 for that product only) | owner action | the first non-UNKNOWN verdict |

Compute: CA$0 for Layer 1; ≈US$0.03–0.10 per candidate image. The first *trustworthy*
photograph — PASS, not UNKNOWN — is gated by the physical sample, not by any software above.

## 14. Shortest credible Launch-0 Visual path, in order

1. Owner adopts §9 (decision, minutes).
2. Integrator applies §7.1 and wires §8/§9 (one lane).
3. Layer 1 for the four Launch-0 products; regenerate on GPT Image edits; judges score;
   every candidate lands at UNKNOWN-or-FAIL (one lane, ≈US$1).
4. Owner makes and measures one basket (the one product with a Revolution profile); the twin
   is calibrated for it; its best candidate is re-assessed → the first PASS or the first
   honest FAIL.
5. FIRST_CUSTOMER_GATE owner review, unchanged.

## 15. Files and commits on this branch; checkpoint status

Branch `claude/visual-investigation` from `fcb982d`. Files: `research/VISUAL_INVESTIGATION.md`
(report 1, with §Corrections appended), this file, `research/e1/structural_reference.py`,
`run_e1.py`, `measure_e1.py`, `milestone_d_spec.py`, `presentation_gate_spec.py`,
`test_specs.py`, and `research/e1/out/` (reference, structure.json, nine generated images,
contact sheet, manifest, measurements). **No file under `src/` or `tests/` changed.**
`fcb982d` is untouched; the integrated branch was never checked out during this work. No
merge, no deploy, no Etsy action, no threshold changed, `twin.calibrated` still False.
