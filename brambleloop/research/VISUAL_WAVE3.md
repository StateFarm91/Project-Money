# Visual wave 3 — the bending energy is not frame invariant, and that is one defect with three faces

**Department:** Visual. **Date:** 2026-09-25 (UTC). **Mode:** Shadow. **Spend:** CA$0.00 — no
model API calls, no image generation, no deployment, nothing published.

Continues `VISUAL_WAVE2.md`, which is not restated, not re-run and not revised. Items 1 and 2
of the queue were completed and committed in wave 2 (`c6316dd`, merged at `03488ae`) and are
**verified as standing, not redone**. This file is items 3, 4 and the honest position on 5.

Labels follow `YARN_SLIP_RESEARCH.md`: **SOURCED / DERIVED / BOUNDED / MEASURED / UNKNOWN**.

Owner ruling D7 observed throughout: **Stage 0 deferred, Stage 1 not begun.** Nothing here
needs either. Everything is measurement on the certified geometry.

---

## 0. The fixture, and one correction to how it was described

`benchmarks.cardigan("S")` body, `build` → `settle` → `relax(600)`, as `test_drape` builds it.
Larger swatches are the same construction at larger `max_rows`/`max_cols`.

| | 5×5 | 7×7 | 10×8 | 12×10 |
|---|---|---|---|---|
| vertices | 474 | 918 | 1494 | 2226 |
| hdc | 25 | 49 | 80 | 120 |
| extent along the wale | 57.549 mm | 78.601 mm | 110.180 mm | 131.234 mm |
| areal mass W | 0.22586 | 0.23810 | 0.24504 | 0.24970 kg m⁻² |

5×5 detail, all MEASURED off the geometry: yarn length 1.1774 m, W g = 2.21492 N m⁻²,
λ = 4.44e-4 kg/m, per-vertex weight λ·l·g = **1.7791e-5 N**, B = 3.0e-8 N m²,
B/l³ = **0.43976 N/m**.

### CORRECTION to the wave 2 record: the solver's length scale is 4.0860 mm, not 3.1427 mm

Wave 2 recorded "median segment length `l` 3.1427 mm — measured" and "bending coefficient
B/l³ = 0.9665 N/m" for this exact fixture. Neither is the quantity `drape()` uses.

```
rest = _segment_lengths(pts);  rest[rest < 1e-9] = 1e-9;  ell = median(rest * 1e-3)
```

is a median over **every** segment of the path, and the path contains 87 artificial hops
between ops (up to 6.73 mm) and 20 sub-micron joins. Measured on the same fixture:

| statistic | value |
|---|---|
| median over the whole path — **what the solver divides by** | **4.0860 mm** |
| median over segments shorter than 5 mm | **3.1427 mm** ← the recorded figure, exactly |
| median over segments that are yarn by both criteria (no hops, no sub-micron joins) | 3.9726 mm |
| B/l³ at the solver's value | **0.43976 N/m** |
| B/l³ at the recorded value | 0.9665 N/m |

Three statistics, one name. The recorded figure is reproducible — it is the median over
segments under 5 mm — but it is not the one `drape()` divides by, and the 20 sub-micron joins
drag it down by a further 21 % below the median over real yarn.

The two differ by 1.30×, so `B/l³` differs by **2.20×**, and every prestress ratio wave 2
derived from the recorded value is out by that factor. The one that can be recomputed exactly:
wave 2's headline for the Kaldor bound, "**2.22× gravity**", is
`(B/l³)·2l·sin(p/2) / (λ l g)` = `0.01·B/l² / (λ l g)`, which at the solver's l is
**1.010× gravity**, not 2.22×. Kaldor's bounded prestress and gravity on a vertex are
**equal to within one per cent** on this fabric, which is a cleaner statement of wave 2's
finding than the one recorded, and it is arrived at by fixing an arithmetic input rather than
by re-running anything. Pinned by a check in `test_drape` so the two medians cannot drift
apart again unnoticed.

Nothing else in wave 2 depends on `l`, and no wave 2 result is withdrawn.

---

## ITEM 3 — converge the ASTM cantilever inversion, and re-derive B in code

### 3a. It cannot be converged, and the reason is closed form rather than a budget

`cantilever_equilibrium_bound()` computes it without running a solve. Two facts, both from
the code and both confirmed against geometry:

**The implemented bending force is not the gradient of the documented bending energy.** The
module documents `E = (B/2)·Σ|d²p|²/l³`, whose gradient is `-(B/l³)·Dᵀ(lap − lap_rest)` — the
second difference applied **twice**. The loop applies `bend_coeff·(lap − lap_rest)` — the
second difference applied **once**. Settled by finite differences on the real certified
geometry rather than by reading: the analytic `DᵀD` gradient matches central differences of
the energy to a worst relative error of **3e-8** over 18 sampled components, while the
implemented force differs from it by **69 % of the gradient's norm, with a cosine of 0.911**,
and has the **opposite sign** at 3 of those 18 components. [MEASURED,
`tests/test_drape.py`.]

A second difference once is a **string under tension B/l²**, not a beam. Per vertex,
`bend_coeff·lap ≈ (B/l)·u″`; per unit length, `(B/l²)·u″`.

**The specimen cannot hold itself up under that force law.** On the standard cantilever
(`clamp_fraction = 0.3`, i.e. 70 % overhang):

| quantity | value |
|---|---|
| effective tension B/l² | **1.7969e-3 N** |
| weight of the free region | **4.9221e-3 N** |
| weight ÷ tension | **2.74×** |
| free region | 305 of 474 vertices |
| **yarn arc length hanging free** | **0.7329 m** |
| fabric extent that yarn spans | 40.10 mm |

That last pair is the whole thing in two numbers. The bending element is the **yarn path**,
which snakes; the free region of a 58 mm swatch is **733 mm of yarn hanging from an anchor**.
A string clamped at one end with a free end has the natural boundary condition `u′ = 0` there,
which is incompatible with `u″ = w/T` anywhere along it — discretely, the free end of the path
is the one vertex with no bending equation at all. There is **no shallow equilibrium to
converge to**.

**Measured, to 51,200 iterations — 64× the iteration count behind any committed figure, 992 s
on 474 vertices.** 5×5, calibrated B, 70 % overhang:

| iterations | tip drop | max out-of-plane | converged | Δ²z over the free interior, ÷ its own equilibrium |
|---|---|---|---|---|
| 800 | 1.3858 mm | 1.6865 mm | False | 0.031 |
| 3,200 | 4.4911 | 5.2122 | False | 0.158 |
| 12,800 | 8.5986 | 9.8775 | False | 0.303 |
| **51,200** | **12.5742** | **32.4240** | **False** | **0.439** |

The last column is the direct test of the force law on geometry: at equilibrium the solver's
own force law requires the second difference of out-of-plane displacement along the path to be
`λ l g / (B/l³)` = **0.040457 mm** at every free interior vertex. After 51,200 iterations it
has reached 44 % of that, monotonically, still climbing. The fabric has meanwhile displaced
**32.4 mm out of plane on a 57.5 mm swatch**. This is not a drape that has not settled; it is a
**collapse in progress**, and every committed drape figure is an early frame of it.

**ANSWER TO ITEM 3 AS ASKED: the ASTM cantilever inversion cannot be converged in this solver,
and more iterations will not do it.** Not a budget problem. [MEASURED.]

### 3b. So the bending length was re-derived by a different instrument — one with nothing to converge

`flexural_rigidity()`. Bend the certified geometry onto a cylinder (`cylindrical_bend()`,
isometric on the midsurface, exact to 1e-6 on a synthetic strip), evaluate the model's own
bending energy in closed form, and read the areal flexural rigidity off the definition of
bending energy per unit area, `E/A = ½ G κ²`. Bending length follows ASTM's own relation
`G = W g c³`, with W measured off this fabric's yarn length and extent rather than looked up.
One evaluation. No solver, no iteration count, nothing that can be stopped early.

It is linearly elastic to **1.0004** over a 4× curvature sweep at the shipped default
κ = 0.25 /m, and the residual is the yarn's own thickness: the wrap is isometric on the
midsurface only, so a strand sitting z above it is strained by z·κ. That residual is
proportional to κ and is reported every time — 1.4e-3 at κ = 0.25, 5.7e-3 at 1.0, 2.3e-2 at
4.0 — which is why the default curvature is a 4-metre radius on a 58 mm swatch.

### 3c. And it immediately found why no bending length from this model was ever a fabric property

**MEASURED. Bending length in mm, same yarn, same B = 3.0e-8, four sizes of the same swatch:**

| rest state | 5×5 (474) | 7×7 (918) | 10×8 (1494) | 12×10 (2226) |
|---|---|---|---|---|
| **world-space (what the solver uses)** | 57.56 | 69.92 | 87.34 | **98.49** |
| world-space, yarn segments only | 41.32 | 51.01 | 64.31 | 72.39 |
| **frame-invariant** | 21.557 | 21.560 | 21.556 | **21.621** |
| frame-invariant, yarn only | 9.911 | 9.797 | 9.770 | 9.713 |

**The committed model's bending length grows by 1.71× when you measure a bigger piece of the
same cloth.** That is not a fabric property, and no calibration against a published fabric
bending length can mean anything while it is true. With the rest state carried into each
vertex's own frame the same measurement is constant to **0.3 % over a 4.7× range of swatch
size**.

---

## THE DEFECT ITSELF — the bending energy is not invariant under rigid rotation

This is the finding the rest of the file hangs on, and it is one line of physics.

The rest curvature is stored as a second difference **in world coordinates**. Rotate a piece
of finished cloth — deform nothing, change nothing about the fabric — and every residual
`lap − lap_rest` changes, because `lap` rotates and `lap_rest` does not. The energy charges
for it.

**MEASURED on the certified 5×5, rotating the entire swatch about its own centre**
(`rigid_motion_response()`). The right-hand column is the height every stitch would have to be
lifted against gravity to cost the same, which is the comparison that decides whether the
defect can compete with the force that drives drape:

| rotation | energy, world-space rest | energy, frame-invariant rest | equivalent lift per stitch |
|---|---|---|---|
| pure translation | **1.5e-33 J** | — | 0 |
| 0.5° | 9.887e-8 J | 2.9e-26 | 0.0117 mm |
| 1° | 3.955e-7 | 3.1e-26 | 0.0469 |
| **5°** | **9.881e-6** | 6.2e-26 | **1.1717 mm** |
| 15° | 8.848e-5 | 5.6e-26 | 10.49 |
| 45° | 7.605e-4 | 3.2e-26 | 90.18 |
| **90°** | **2.597e-3** | 6.2e-26 | **307.90 mm** |

Translation is exactly zero; the energy is translation invariant and rotation is the only thing
wrong. It grows as 1 − cos θ — the 1° figure is 4.0000× the 0.5° figure — so it is a **spring**,
not an offset.

**The scale that makes it matter.** The whole gravitational drive of the standard 800-iteration
cantilever produces **1.586 mm** of droop. Turning one stitch through **5 degrees** costs the
equivalent of **1.172 mm** of lift. Turning it through a right angle costs 308 mm, on a swatch
57.5 mm tall. The spurious rotational stiffness is not a correction to the mechanics of this
model; at stitch scale it **is** the mechanics.

**Why it is this large here specifically, and why crochet is the worst case.** The penalty at
each vertex is `(B/2l³)·|(R−I)·lap_rest|²`, i.e. proportional to how curved the rest state
already is. A crochet loop is nothing but curvature — this swatch's mean turning angle is
1.394 rad — so every stitch carries a large `lap_rest` and therefore a large charge for
turning. A fabric conforms by letting each stitch turn relative to its neighbours. **An energy
that charges each stitch for turning, in proportion to how much of a stitch it is, is an energy
that holds rows rigid.** That is the corrugated-relief symptom, stated as a mechanism.

**The fix is DERIVED and standard, and is what the source already does.** Kaldor, James and
Marschner hold the rest state as a 2D point in the segment pair's **own** frame — which is also
why their plasticity radii are 2D where wave 2's mapping had to be 3D, a residual wave 2
labelled honestly as an approximation without identifying what it cost. `corotational_rotations()`
computes, per vertex, the least-squares rotation carrying the rest edge pair onto the current
one (Kabsch, on the two unit edge vectors). It recovers a known rigid rotation to **8.7e-11** at
every interior vertex, is orthogonal with determinant +1, and makes the energy invariant under
any rigid motion **to machine precision** (≤6.2e-26 J against 2.6e-3 J).

---

## 3d. B RE-DERIVED IN CODE, with the conditions it holds under

`derive_bending_rigidity()`. The energy is linear in B, so G is linear in B and `c` goes as
`B^(1/3)`; one evaluation at a reference B inverts exactly,
`B_target = B_ref · (c_target / c_ref)³`. Closed form. The suite checks the derivation by
re-running the instrument at the derived B and requiring it to land on the target, which it
does to **1e-6 relative**.

**Target: 34.6 mm, the geometric midpoint of the 15–80 mm band. BOUNDED, argued, unchanged.**

| bend direction | non-yarn hops counted? | c at the committed B | **derived B** | ×committed |
|---|---|---|---|---|
| wale | yes (whole path) | 21.552 mm | **1.2413e-7 N m²** | 4.14× |
| wale | no (yarn only) | 9.927 mm | **1.2701e-6** | 42.3× |
| course | yes | 13.475 mm | 5.0784e-7 | 16.9× |
| course | no | 13.310 mm | 5.2701e-7 | 17.6× |

**The honest answer is a bracket, not a number: B is between 1.24e-7 and 1.27e-6 N m², i.e.
4× to 42× the committed 3.0e-8.** Both ends sit inside the published bracket the module already
carries (free fibres 2.062e-8, solid rod 1.515e-2). This is deliberately **not** offered as the
kind of cross-check that was withdrawn on 2026-09-25 — that bracket spans 735,000×, so landing
inside it excludes almost nothing, and the withdrawn claim is not restored here or anywhere.

**Three conditions, all reported in the result and none of them optional:**

1. **Frame invariance must be on.** With it off the quantity is not a material property and
   `derivable` returns False. Pinned by a check.
2. **Bend direction.** The fabric is anisotropic: wale 21.55 mm against course 13.48 mm, a
   1.60× ratio. ASTM D1388 is run on strips cut both ways for exactly this reason. Reported,
   not averaged.
3. **Whether the artificial hops count.** They are 87 of 473 segments and they are not yarn,
   and they carry 60 % of the world-space energy. Including or excluding them is worth
   **10.2× in the derived B**. The solver's bending term currently includes them. That is
   recorded, not silently changed.

**`CALIBRATED_BENDING_N_M2` has NOT been changed.** Moving it moves every committed Visual
result, the answer is a 10× bracket rather than a value, and the bracket's width is set by a
property of the solver's own force term rather than by the fabric. The module docstring, the
constant's comment and `PROVENANCE["bending_calibration"]` now say all of this, and the
withdrawn "1.45× the free-fibre floor" cross-check has been **removed from the three places it
was still asserted in code** — it was withdrawn in the record on 2026-09-25 but `drape.py` was
still making the claim.

**Direction check against wave 2.** Wave 2 inferred from the unconverged cantilever trend that
"a convergent calibration would demand a LARGER B — by roughly (34.6/c)³, which the data do not
yet pin down", and labelled it INFERRED and not acted on. That inference is **confirmed and
now quantified: 4× to 42×.**

### One cross-check this makes possible, reported because it fails

From the frame-invariant G (wale, whole path), beam theory predicts cantilever tip drops of
1.118 / 8.590 / 32.93 mm at the 17.3 / 28.8 / 40.3 mm overhangs wave 2 swept. Wave 2 measured
1.779 / 4.182 / 6.635 mm at 6,400 iterations — **1.6× too much at the short overhang and 5×
too little at the long one**, in opposite directions. A beam's deflection goes as s⁴ and a
string's as s²; the measured ordering is what a string gives, which is the same conclusion
3a reaches from the code and the same one the 51,200-iteration run reaches from the geometry.
Three independent routes, one answer. [MEASURED.]

---

## ITEM 4 — every Product Truth lock, re-run on real geometry

Re-run on the certified 5×5 **and on a 10×8 (1494 vertices, 110.2 mm along the wale — the
larger swatch wave 2 queued)**, in four configurations each, including two the validators had
never been shown: a fabric wrapped round a cylinder, which is curved everywhere and planar
nowhere.

| lock | 5×5 default | 10×8 default | cylinder κ=2 (R 500 mm) | cylinder κ=8 (R 125 mm) | 5×5 frame-invariant, 400 it |
|---|---|---|---|---|---|
| topology gate | PASS | PASS | PASS | PASS | **FAIL** |
| linkage preserved | 20/20 | 72/72 | 20/20 | 20/20 | 20/20 |
| stitch morphology | 25/25 | 80/80 | 25/25 | 25/25 | **21/25** |
| unmeasurable / unframeable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| stitch identity, row, position | held | held | held | held | held |
| loop targets | held | held | held | held | held |
| no interpenetration (min gap) | 1.5000 mm | 1.5000 | 1.5061 | 1.5239 | 1.5000 |
| no pull-through (crossing impossible) | True | True | n/a | n/a | True |
| yarn length change | +1.4e-5 % | +1.9e-5 % | +0.076 % | +0.305 % | +1.4e-5 % |
| max measurable strain | 0.00000 | 0.00002 | 0.01141 | 0.04561 | 0.00002 |
| join within a row | 0.003→0.003 mm | 0.003→0.003 | 0.003→0.003 | 0.003→0.003 | 0.003→0.003 |
| join at a turn | 5.998→5.998 | 5.998→5.998 | 5.998→5.972 | 5.998→5.894 | 5.998→5.998 |
| intrinsic width | −0.044 % | −0.037 % | **−0.0000 %** | **−0.0000 %** | +0.137 % |
| intrinsic height | +0.136 % | +0.034 % | +0.092 % | +0.289 % | +0.646 % |
| worst third-loop margin (flat −1.540) | −1.599 | −1.453 | −1.466 | −1.120 | **+1.121** |
| relief, within-row share | 0.0083 | 0.0031 | 0.0000 | 0.0000 | 0.1544 |

**Findings.**

1. **No validator was passing because the fabric was planar.** Wrapped round a 125 mm
   cylinder — curved everywhere, every stitch moved, the third-loop margin eroded from −1.540
   to −1.120 mm — all 25 stitches stay linked and shaped, nothing becomes unframeable, and the
   gate passes. The morphology and linkage checks were made frame-invariant in an earlier
   increment and this is the first test that actually demanded it.
2. **The intrinsic/projected separation holds exactly under a pure bend.** Wrapping changes
   intrinsic width by **−0.0000 %** on both swatches while moving every stitch, which is
   what that separation exists to do. Intrinsic height rises 0.09–0.29 % because the wrap
   strains the yarn's own thickness, which is the residual the instrument reports.
3. **The larger swatch behaves like the small one on every lock**, which is the first time
   that has been checked. Its relief within-row share is 0.0031 against the 5×5's 0.0083 —
   **a bigger piece of this cloth is more rigid, not less**, consistent with the rotational
   stiffness being the dominant term.
4. **The frame-invariant option fails Product Truth partway through its descent, and that is
   a finding about the locks and not only about the option.** See below.

### The lock finding that matters most: a solve can pass through a broken product and come back

MEASURED, 5×5, frame-invariant rest, by iteration count:

| iterations | max OOP | worst third-loop margin | shaped | gate | within-row relief |
|---|---|---|---|---|---|
| 100 | 1.884 mm | −0.417 | 25/25 | PASS | 0.1411 |
| 200 | 2.753 | **+0.574** | **21/25** | **FAIL** | 0.1453 |
| 400 | 3.312 | **+1.517** | **21/25** | **FAIL** | 0.1453 |
| 800 | 2.355 | **+1.121** | **21/25** | **FAIL** | 0.1544 |
| **1600** | 3.768 | **−0.426** | **25/25** | **PASS** | 0.1023 |
| **3200** | 16.544 | **+3.547** | **20/25** | **FAIL** | 0.1291 |
| **6400** | 20.633 | **+8.864** | **17/25** | **FAIL** | 0.1289 |

**Validity is not monotone in the iteration count.** Valid at 100, broken at 200–800, valid
again at 1600, then broken and getting worse — 20/25 at 3200 and 17/25 at 6400, with the swatch
20.6 mm out of plane. The 1600-iteration reading is a sample of an oscillation, not a recovery,
and the run is going the same way the default solve goes (§3a). At the derived stiffness
B = 1.3e-6 the same pattern appears at the same iteration counts (−0.531 at 100, then +0.436 /
+1.512 / +1.779 at 200 / 400 / 800), so **it is not a stiffness problem**. And it is geometry
rather than the instrument: the same instrument reads −1.561 on the default solve at 400
iterations.

**Every Product Truth lock in this repository is evaluated at the END of a solve.** A
1600-iteration run of this configuration ends valid having passed through 1,400 iterations in
which four of twenty-five stitches were everted, and no gate can see that it happened. Stopping
the same solve at 400 or at 3200 catches it; stopping at 100 or 1600 does not. Recorded as a
real gap, not patched: continuous validation costs a topology pass per iteration, which is the
dominant cost of the solve, and choosing how to pay for it is a design decision rather than a
fix to slip in at the end of an increment. It applies to the committed default too — nothing
establishes that the default's descent is monotone in validity, only that its endpoints tested
so far are valid.

---

## What the frame-invariant option is, and why it is OFF

`DrapeSetup.frame_invariant_rest: bool = False`. Not adopted. What it does, measured:

- **Removes the spurious rotational stiffness exactly** (energy invariant to 6e-26 J).
- **Makes the model's flexural rigidity a material property**: size-independent to 0.3 %.
- **Makes the fabric 109× more compliant at the same B**: at B = 1.3e-6 and 800 iterations the
  default gives 0.038 mm of droop and the frame-invariant option gives 4.158 mm. That single
  ratio is the size of what the spurious term was carrying.
- **Moves the standing conformability symptom in the right direction for the first time.** The
  within-row share of relief variance — the share a per-row mean cannot explain, the corrugated
  relief measure wave 2 built — goes from **0.0083 to 0.1544 on the 5×5** and **0.0031 to
  0.0624 on the 10×8** at 800 iterations, and from 0.0156 to 0.1023 at 1600. Factors of 18.6,
  20.1 and 6.6. For comparison, wave 2's Kaldor option moved the same metric from 0.0083 to
  **0.0000**, i.e. made it worse. This is the first option tried that improves it at all.
- **And it everts stitches partway down**, as above.

**It is not adoptable, and Milestone D does not move.** But the failure says something precise
about what is missing, which is the point of running it.

---

## MILESTONE D — still FAIL, and the missing mechanism is now named

**FAIL. Unchanged, not weakened, no threshold lowered.**

What this increment adds is that the standing symptom now has a mechanism with a number on it,
and removing that mechanism exposes the next one.

**The spurious rotational stiffness is a cause of the corrugated relief.** Quantified: turning
one stitch 5° costs 1.17 mm of lift per stitch against a whole-solve droop of 1.59 mm. Removing
it raises within-row relief 10–20× and makes the fabric 109× more compliant. [MEASURED.]

**It is not the only cause, and removing it exposes the next one: there is no tensile linkage
between stitches in this model at all.** Three things hold this fabric together:

1. bending along the **single yarn path** — but along the path, a stitch in row 2 is a
   neighbour of the stitches beside it in row 2, and of row 1 only at the turn;
2. **inextensibility** of that same path;
3. **contact**, which is **purely repulsive** — `_segment_contacts` returns only pairs closer
   than `rest_sep`, so `apply_contacts` can only ever push apart. [MEASURED, from the code and
   its call site.]

Nothing represents the fact that a crochet stitch is **pulled through** the loop below it, which
is a link that carries tension. In the committed model the missing cohesion was being supplied,
accidentally, by the spurious world-frame rotational stiffness — which is exactly why removing
that stiffness lets free-edge stitches evert. **The mechanism Milestone D is still missing is an
inter-stitch linkage force that resists a stitch being pulled out of the loop it was worked
into, without also resisting that stitch turning.** The linkage is already identified and
validated geometrically by `crochet_topology.validate` (20 of 25 stitches "needing linkage" on
the 5×5); it exists as a **check** and not as a **force**.

That is a specific, falsifiable next mechanism. It does **not** require Stage 0 — it is a
statement about what the model contains, not about what crochet does under load — and it is
**not Stage 1** yarn redistribution. Stage 1 remains forbidden and not begun.

---

## ITEM 5 — the per-stitch colour primitive: NOT STARTED, and why

`cir.model.Row` carries a single `color` field, so no CIR can express a colour change within a
row. `publish.motif_fidelity.rows_working_more_than_one_colour` and the float-claim branch of
`gates.asset_truth` both have a branch no CIR can currently reach, and both are tested against
hand-made twins so they will not silently pass when it lands.

**Not started.** Items 3 and 4 took the increment, and this one changes the CIR contract — the
dataclass, the compiler's count arithmetic, the writer, the independent reverse compiler (which
shares no parsing code by decision B-005 and therefore needs its own colour grammar), the twin,
the chart renderer and eleven existing CIRs. Beginning it with the budget left would have
produced a half-changed contract, which is worse than an unchanged one. It is unblocked,
correctly scoped to Visual, and it is the right next increment for this department if the
mechanism work is not taken up.

---

## What changed in the tree

`visual/drape.py` — **additive; no existing default altered and no committed figure moved**:

- `genuine_yarn_vertices()`, `JUMP_SEGMENT_MM`, `DEGENERATE_SEGMENT_MM` — what in the path is
  not yarn, named once.
- `corotational_rotations()` — the DERIVED, exactly equivariant per-vertex rotation (Kabsch).
- `bending_energy_J()` — the documented energy, evaluable on any configuration, either way.
- `rigid_motion_response()` — the defect, measured.
- `cylindrical_bend()`, `flexural_rigidity()` — the imposed-curvature instrument.
- `derive_bending_rigidity()` — B in closed form, with its conditions and a `derivable` flag.
- `cantilever_equilibrium_bound()` — why the cantilever has no shallow equilibrium, without
  running one.
- `DrapeSetup.frame_invariant_rest` (default **False**) and `drape(rest_points=...)`.
- Refuses `frame_invariant_rest` together with `plastic_rest_migration`: the composition is
  UNKNOWN rather than merely untested, so it raises instead of producing a number.
- `TARGET_BENDING_LENGTH_MM = 34.6`, which was previously prose only.
- The withdrawn "1.45× the free-fibre floor" cross-check **removed** from the module docstring,
  the constant's comment and `PROVENANCE`; replaced with what is now known about the procedure
  that set B.

`tests/test_drape.py` — **47 checks added, 55 → 102, 0 failing.** Nothing weakened, no threshold moved, no
existing check deleted or relaxed. Two of the new checks are **recorded negatives**: the
frame-invariant option everts stitches partway through its descent, and the solver's length
scale is not the yarn's. Both fail loudly if they stop being true.

**Suites re-run, all green:** `test_drape` **102/102**, `test_hand_tension` 24/24,
`test_topology_adversarial` **28/28 adversarial fixtures still REJECT**,
`test_crochet_topology` 34/34, `test_linkage` 18/18, `test_visual` 0 failing,
`test_render` 0 failing, `test_fabric` 0 failing, `test_dimensions` 0 failing,
`test_compiler` 0 failing, `test_reverse` 0 failing, `test_twin` 0 failing.
`run_tests.sh` deliberately not run — the integrator runs it.

CA$0.00. No model calls. No image generation. Nothing published, nothing deployed. Branch
committed, not pushed. No committed Visual result discarded, re-derived from scratch or
reorganised.
