# Independent construction review: `market-basket-small@1.2.0` (Hexagonal Bread Basket)

- **Date:** 2026-10-31 (UTC)
- **Reviewer:** independent construction review (W4-CONSTRUCTREVIEW). No source code was changed.
- **Subject:** release hash `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991`.
  Recomputed by `probe_basket_small.py` through `launch0.cir_for("basket_small")`, `write_pattern(..., "US")` and `gates.certificate._release_hash`. **It matches.**
- **Sources read:**
  - `products/vessels.py` (`build_basket`, `_disc_rounds`). The builder is in `products/`, not `cir/`.
  - `creative/prototype.gauge_for` and `publish/substitution.WEIGHT_BY_KEY`.
  - `cir/twin.py`, `cir/geometry.py` and the compiler.
  - The customer PDF `market-basket-small-1.2.0.pdf` (13 pp.) from `origin/claude/w4-PDF1`.
  - The record sheet, test PDF, `quality/tester_kit.py` and `quality/physical.py` from `origin/claude/w4-INTEG8-trial-adopt`.
- **Probes:** in `construction_review_probes/`. Both are read-only.
  - `probe_basket_small.py` gives the counts, twin, rings, independent recomputation, hash, reverse and text.
  - `probe_fix_blo.py` is the in-memory what-if for the recommended fix.

## Verdict (N4, the Rnd 10→11 transition)

**COSMETIC (minor).** The pattern works as a basket. When it is worked as written:
- the base is a flat hexagon;
- the wall stands, because a 60-stitch tube on a 60-stitch base has nowhere to go but up;
- the base corners are preserved.

N4 is real in one respect. Without a loop or turning cue, the fold from base to wall is a **rounded curve spread over about Rnds 11–13**, not a crease. The likely consequences:
- the standing height comes out roughly **0.3–0.8 cm under the twin's 8.7 cm**;
- the wall corners soften towards the rim.

That is inside the project's own size tolerance (`physical.SIZE_DISAGREEMENT` = 12 %, which allows 7.66–9.74 cm), so it is **not a DEFECT**.

The real fault is in the copy and the visuals, not the arithmetic:
- p2/p3 say "rise straight up";
- the p5 checkpoint says Rnd 11 is "1 cm tall";
- the cover render and side schematic draw a crisp prism.

All three promise the sharp fold that the twin models and the instructions do not produce. The p9 tip is the one passage that is accurate.

A design change is **not required** to sell 1.2.0 honestly. If the owner wants a crisp edge, the minimal fix is a 1.3.0 change (§4).

## 1. Rounds 10→11, the base-to-wall transition

### 1.1 What the certified pattern says (compiled US text, identical to PDF p7)

```
Join each round with a sl st to the first stitch, then ch 1 to begin the next round.
Rnd 1 (cream): 6 sc in magic ring. (6 sts)
Rnd 2 (cream): [inc in next st] x 6. (12 sts)
Rnd 3 (cream): [sc in next st, inc in next st] x 6. (18 sts)
Rnd 4..10: [sc in next k-2 sts, inc in next st] x 6   -> 24, 30, 36, 42, 48, 54, 60 sts
Rnd 11 (cream): sc in next 60 sts. (60 sts)
Rnd 12-14 (cream), 15-16 (wine), 17 (cream), 18-19 (wine), 20-22 (cream): sc in next 60 sts. (60 sts)
Component note: "Work each increase into the second stitch of the previous round's
increase, so the increases stack into six corners and the base is a hexagon."
```

Every wall round is plain sc through both loops (twin `loop` = `both` for all 1,050 cells). The transition has:
- no back loop or front loop;
- no surface slip-stitch round;
- no turn;
- no post stitch.

It also has no corner stitch in the wall. At the transition the pattern simply stops increasing.

### 1.2 Base

| Check | Finding |
|---|---|
| Increase rate | 6 per round on Rnds 2–10. Each round adds exactly 6 (6→12→…→60). **Yes.** |
| Hexagon | The increases stack, and `geometry.corners()` = **6**. The base is a hexagon, not a circle. **Yes.** |
| Flat | Per-wedge check at the stated gauge: at round k a wedge is k × 0.80 cm wide and k × 0.725 cm tall. That gives an apex angle of 57.8° against the 60° a flat hexagon needs (346.9° of 360°). The circle-model growth ratio is 1.05 against tolerance. This is the conventional "6 sc per round" flat disc. It lies flat, or very slightly domed, in practice. **Yes.** |
| Increases stop | After **Rnd 10** (60 sts). Rnds 11–22 are 12 rounds worked even. |

### 1.3 What working even in sc does, by geometry and in practice

A round with the same count as the one below cannot lie flat. Lying flat would need about 6 more stitches, so the new round must rise.

- **Inextensible-surface model.** The rise is immediate and 90°. This is exactly what the twin computes. At Rnd 11, `radius_delta` = 0 and `rise` = the full 0.725 cm row height. It then adds 0.725 cm a round, giving 12 × 0.725 = **8.70 cm**.
- **Real sc fabric.** Real fabric has bending stiffness. The outer base rounds and the first wall rounds share the turn, so the fold forms as a curve over about 2–3 rounds. This is the familiar soft-bottomed basket. Crisp folds come from a loop or surface technique, which this pattern does not use.
  - Take a quarter-round of fabric arc L ≈ 1.5–2.2 cm (2–3 rounds). Its radius is r = 2L/π ≈ 1.0–1.4 cm.
  - The height lost against a sharp fold is L − r = 0.57 r ≈ **0.5–0.8 cm**.
  - The table-to-rim height also gains about half the fabric thickness of the base. Net, expect **about 8.0–8.5 cm** against the stated 8.7 cm.

| Question | Outcome as written |
|---|---|
| Six-sided basket, corners kept? | **Base: yes.** The 6 stacked-increase columns are explicit. **Wall: partly.** No round above Rnd 10 has anything at the corner columns. The wall's lower edge follows the hexagon, and the rim relaxes towards a rounded hexagon. Rim across-points tends from 16.0 cm towards the 15.3 cm circle figure (48 cm / π); across-flats stays about 13.9 cm. |
| Defined base edge? | **No, a soft one.** The edge is a rounded fold over about Rnds 11–13, not a crease. |
| Wall that stands? | **Yes.** The wall count equals the base count, so the wall is a prism or tube. It cannot flare or cup inward from stitch count. How firmly it stands depends on tension; see §3. |
| Stated dimensions | Base points and flats: met; they are set by the Rnd 10 count. Height: likely 0.3–0.8 cm short. That is within the project's ±12 % (7.66–9.74 cm) and within "about 9 cm". |

**Classification: COSMETIC (soft edge, still meets the stated dimensions).**

### 1.4 The claims, word for word

| Where | Text | Accurate? |
|---|---|---|
| p2 Overview | "Rounds 1 to 10 grow a flat base, and rounds 11 to 22 **rise straight up** from it to make the wall." | **Overstated.** Rnds 11–13 curve; the wall is straight above that. |
| p3 How it is made | "rounds 11 to 22 keep that count and **rise straight up** to make the wall." | **Overstated**, as above. |
| p3 base schematic | "The wall (Rnds 11 to 22) rises from its edge." | Acceptable. |
| p5 Checking your progress | "ROUND 11 OF 22 … about 16 cm across the points and **1 cm tall**". The page header adds: "If it does not, the difference is gauge". | **Misleading.** After Rnd 11 the piece is mostly still turning, about 0.2–0.4 cm high. The page then tells a correctly working maker that their gauge is wrong. Rnd 16 "4 cm" also reads high, at about 3.4–3.9 cm. |
| p9 tip | "Rnd 11 is the first round with no increases, so the edge of the base starts to turn upward there. Let it turn rather than pulling it flat; by Rnd 14 the wall will be clearly rising from the base." | **Accurate.** It describes the real gradual turn, and it contradicts the "straight up" wording above. |
| Finishing | "damp-finish it standing up … **stuffed lightly with a towel if it needs help standing**" | Honest. It concedes that the wall may need help. |

### 1.5 Twin, render and schematic

- **The twin does not model the base edge.**
  - It treats the fold as an instantaneous 90° turn (ring 11: `radius_delta` 0.000, `rise` 0.725).
  - Its rings are circles with radius = circumference/2π. Points and flats come afterwards from `polygon_spans_cm`.
  - It keeps loop placement per cell, but this pattern has only `both`, so there is nothing to model.
  - **The 8.7 cm height is therefore an upper bound**, not a central estimate.
- **The render promises more than the instructions make.** The cover (p1) draws a hexagonal prism with sharp vertical corner edges and a sharp 90° base edge. The side schematic (p3) draws a rectangle with square bottom corners. The instructions make neither the wall corner edges nor the crisp fold. Both images are labelled "digital rendering … not a photograph", which discloses the method but not this gap. Finding F3.

## 2. Internal consistency

Each value was recomputed independently from `gauge_for("worsted")`: 12.5 sts and 13.8 rows per 10 cm, hook 5.0 mm. The stitch width is 0.80 cm and the row height 0.725 cm.

| Quantity | Independent recomputation | Twin / CIR | Customer PDF | Kit | Agrees? |
|---|---|---|---|---|---|
| Base count | 6 × 10 = 60 | Rnd 10 = 60 | 60 | n/a | ✅ |
| Total stitches | 330 base + 12 × 60 = 1,050 | 1,050 cells | n/a | n/a | ✅ |
| Perimeter | 60 × 0.80 = 48.0 cm | circumference 48.0 | n/a | n/a | ✅ |
| Across points | side 8.0 × 2 = **16.0** | 16.0 | 16.0 (p1, p2, p3, p5) | 16.0 | ✅ |
| Across flats | 8.0 × √3 = **13.86** | 13.9 | 13.9 | 13.9 | ✅ |
| Height | 12 × 0.725 = **8.70** | 8.7 | 8.7; "about 9 cm" in note and p5 | 8.7 | ✅ arithmetic; ⚠ upper bound (§1.3) |
| Rnd 1 / Rnd 5 points | 6 st → 1.6 cm (~2); 30 st → 8.0 | n/a | ~2 cm, ~8 cm | n/a | ✅ |
| Rnd 11 / 16 / 22 height | 0.72 / 4.35 / 8.70 | axial 0.72 / 4.35 / 8.70 | 1 / 4 / 9 cm | n/a | ✅ to the twin; ⚠ Rnd 11 not physical (F2) |
| Cream yarn | (222 sc × 6.2 + 54 inc × 12.4 + 480 sc × 6.2) × 0.8 cm = **40.2 m** | 40.2 | 32–48 m (±20 %) | 40.2 | ✅ |
| Wine yarn | 240 × 6.2 × 0.8 = **11.9 m** | 11.9 | 10–14 m | 11.9 | ✅ |
| Total yarn | **52.1 m** | 52.1 | 42–63 m | 52.1; 63 m in cost basis | ✅ |
| Kit cost ceiling | 2.15 h × 1.3 × CA$20 + 62.5 m × CA$0.06 = **CA$59.65** | n/a | n/a | 59.65 | ✅ |
| Colour rounds | `int(12 × .45)` = 5, 6 → Rnds 15–16; `int(12 × .7)` = 8, 9 → Rnds 18–19 | same | 15–16, 18–19; 4 changes | n/a | ✅ |
| Rows gauge | 12.5 × `SC_ROW_RATIO` 1.1 = 13.75 → 13.8 | 13.8 | 13.8 | 13.8 | ✅ traced |
| DK substitution "about 60 m" | 52.1 × 1.15 = 59.9 | n/a | 60 m, "(1-1 x 100g balls)" | n/a | ✅ number; "1-1" is awkward copy |

**Numbers that do not fully trace to the source:**
- **Hook 5.0 mm.** `gauge_for` hard-codes `hook_mm=5.0` for **every** yarn weight; the DK coaster gets 5.0 mm too. It is a constant, not derived from the yarn or the gauge. See F6.
- **Make hours 2.15.** This is a static constant in `tester_kit.KIT`. I did not trace its derivation. It feeds the CA$59.65 ceiling.
- **Yardage omits the 22 joining sl st + ch 1** (about 22 × (2.6 + 2.2) × 0.8 cm ≈ 0.85 m), plus about 4 woven-in tails. This is about 2–3 %, inside ±20 %, and the error runs low. See F5.
- **Height 8.7** traces exactly to the twin, but the twin assumes a sharp fold (F4).

The twin, CIR, compiled text, PDF and kit are otherwise **mutually consistent**. Reverse re-derivation of the compiled text returns no findings, and the compiler returns no findings.

## 3. Gauge plausibility and wall stability

- **12.5 sc / 10 cm** is the midpoint of the repository's medium/worsted sc band (11–14, `substitution.WEIGHT_BY_KEY`). It is a plausible gauge for worsted cotton. However, it is a mid-density, garment-style fabric, not a structural one. Baskets are more usually worked tighter than the band midpoint (or with doubled yarn) so the walls are stiff.
- **Hook 5 mm with worsted cotton is reasonable.** Many makers will work *tighter* than 12.5 sts at 5 mm in cotton, which helps stiffness. The risk is the instruction "5 mm, or whatever hook gets you the gauge": a tight maker sizes **up** (5.5–6 mm) to reach 12.5 sts, which gives a looser, floppier wall.
- **DK substitution** is offered on p4. At 12.5 sts, DK is at the loosest end of its band (12–17). The result is an open fabric, and the wall is markedly less able to stand. The PDF says only "lighter and more open".
- **Wall stability.** This is a short wall (9 cm), with a 48 cm perimeter, in dense-ish cotton sc, so it should stand empty. It may lean or slump at the rim under a load of bread, especially in a loose gauge. The pattern already concedes this ("stuffed lightly with a towel if it needs help standing"; designer note "nothing is claimed about that until a physical sample says so"). It is acceptable for Class B with a physical gate, and it is exactly what the make must measure.

## 4. Recommendation

1.2.0 needs **no design change**. The outcome is COSMETIC and meets the stated dimensions within tolerance. Recommended actions:

1. **Copy, highest value.**
   - Replace "rise straight up" (p2, p3) with wording consistent with the p9 tip. For example: "turn upward over the first few rounds and then rise straight".
   - Fix the p5 "Round 11 … 1 cm tall" checkpoint so it does not blame gauge for the fold. For example, drop the height at Rnd 11, or say "the edge is beginning to turn up".
   - Whether this changes the release hash depends on whether this text is in the hashed pattern text. "Rise straight up" and the checkpoint come from the PDF composer, not `write_pattern`. Check before deciding the version.
2. **Visuals.** The cover render and side schematic should not draw crisp vertical corner edges or a square base edge that the instructions do not make. Alternatively, wait for the physical sample photo to replace them.
3. **If the owner wants a crisp, defined base edge (design change → `1.3.0`):** Rnd 11 → `Row(index=11, ops=[Op("sc", 60, loop="back")], declared_count=60, color="cream")`. That is, "sc in back loop of next 60 sts". It is the minimal one-round, one-modifier change.
   - Prototyped in memory (`probe_fix_blo.py`):
     - it compiles clean, with no findings;
     - reverse is clean;
     - counts are unchanged (60 each round, 1,050 total);
     - twin points, flats and height are unchanged (16.0 / 13.9 / 8.7);
     - yarn is unchanged (40.2 / 11.9 m; the yardage model ignores the loop);
     - the twin's only change is `loop` = `back` on Rnd 11.
   - The change makes the real fabric match what the twin already assumes: a sharp fold.
   - The release hash changes, so the PDF, tester kit and listing must be regenerated, and the version is **1.3.0**.
   - It does **not** add wall corners. Keeping corners up the wall would be a larger design change, and I do not recommend it for a bread basket.
   - **Not applied.**

## 5. Tester kit adequacy

The kit is `origin/claude/w4-INTEG8-trial-adopt`: the record sheet, test PDF and `tester_kit.RECORD_FIELDS`.

| Field / step | Detects N4? |
|---|---|
| `holds_shape` yes/no (step 6: "walls upright, no collapse, lean or flare") | Detects collapse, lean or flare, the gross failure. **Not** a soft base edge or loss of wall corners. A soft-edged basket will honestly be marked "yes". |
| `lies_flat` ("base sits flat, no rocking") | Detects a domed or rocking base. Not the edge. |
| `width_cm` (points), `flats_cm` | Measured at the base, so they will match the twin. They do not see rim rounding or a soft edge. |
| `height_cm` "wall height (cm)" | **Undefined method**: inside or outside, table to rim, or base fold to rim. A rounded fold makes these differ by about 0.5–1 cm, so the one number most affected by N4 is ambiguous. Even a 0.8 cm shortfall passes the 12 % size check. |
| Photos (2) top-down and (3) side at table level | Would *show* the base-edge profile and the corner retention, but only qualitatively. No field asks the tester to judge them. |
| `problems` (round numbers) | Catches it only if the tester volunteers it. The p5 checkpoint may cause a false "my gauge was off" note at Rnd 11. |

**Missing fields** (add to `RECORD_FIELDS` and the sheet; this is a kit change, not a pattern change):
1. `wall_height_method`: fix the method in the protocol as "outside, flat table to top of rim, at the middle of a flat side". Optionally add `inside_depth_cm`.
2. `base_edge`: "crisp fold / rounded curve". If rounded, add `wall_vertical_from_rnd`, the round at which the wall is upright.
3. `corners_at_rim` yes/no, plus `rim_across_points_cm`. This measures whether the hexagon survives to the top.
4. `rnd11_height_cm`: optional in-progress reading. It tests the p5 checkpoint directly.

With these fields the single physical make answers N4 conclusively, and calibrates the twin's sharp-fold height.

## Findings

| ID | Severity | Finding |
|---|---|---|
| F1 | **Cosmetic (minor)** | The Rnd 10→11 transition, as written, makes a rounded base edge over about Rnds 11–13. The basket is still six-sided at the base, the wall stands, and the size is within tolerance; the expected height is about 8.0–8.5 cm against 8.7 cm. **N4 is confirmed as cosmetic, not a defect.** |
| F2 | **Minor (copy)** | p2/p3 "rise straight up" overstates, and p9 contradicts it (accurately). The p5 "Round 11 … 1 cm tall … the difference is gauge" can send a correctly working maker to change hooks. |
| F3 | **Minor (visual promise)** | The cover render and side schematic show a crisp prism (sharp vertical corner edges and a square base edge) that the instructions do not produce. |
| F4 | **Info (model)** | The twin models the fold as an instantaneous 90° turn and does not model the base-edge radius, so 8.7 cm is an upper bound. Loop placement is carried per cell (all `both` here). |
| F5 | **Minor (yardage)** | Joining sl st + ch 1 (about 0.85 m) and tails are not counted. This is inside ±20 % and the error runs low. |
| F6 | **Minor (traceability / stability)** | `hook_mm=5.0` is a constant for all weights, not derived. 12.5 sts is a mid-band, not a structural, density. "Whatever hook gets you gauge" and the DK substitution can both produce a soft wall. |
| F7 | **Moderate (test coverage)** | The tester kit cannot record N4 in structured form: wall height is undefined, and there is no base-edge or rim-corner field. Add the four fields in §5 before the make. |
