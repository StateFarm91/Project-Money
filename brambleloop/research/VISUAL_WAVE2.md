# Visual wave 2 — Kaldor plastic rest state, the recovery experiment corrected, and ASTM convergence

**Department:** Visual. **Date:** 2026-09-25 (UTC). **Mode:** Shadow. **Spend:** CA$0.00 — no model
API calls, no image generation, no deployment.

Three bounded items, all zero-cost, all measurement rather than appearance. Nothing committed was
restarted, redesigned, discarded or weakened. No threshold was lowered. Stage 1 yarn
redistribution / material-coordinate migration was **not** begun, and **Milestone D remains FAIL**.

Labels follow `YARN_SLIP_RESEARCH.md`: **SOURCED / DERIVED / BOUNDED / ESTIMATED / UNKNOWN**.

---

## 0. The fixture, so every number below is comparable

| Quantity | Value | Label |
|---|---|---|
| Fabric | `benchmarks.cardigan("S")` body, `build` → `settle` → `relax(600)`, 5 rows × 5 cols | — |
| Vertices / stitches | 474 / 25 hdc | — |
| Swatch extent along the wale | 57.549 mm | measured |
| Median segment length `l` | 3.1427 mm | measured |
| Yarn length / areal mass | 1.1774 m / 0.2259 kg m⁻² | DERIVED from the geometry |
| Linear density λ | 4.44e-4 kg/m | DERIVED (444 tex is mass per length by definition) |
| Bending rigidity B | 3.0e-8 N m² (`CALIBRATED_BENDING_N_M2`) | BOUNDED, calibrated — unchanged |
| Flat gate | passes; 20/20 linked; 25/25 shaped; worst third-loop margin **−1.540 mm** | measured |

Two force scales, computed once and used throughout, because the whole rest-state argument is
about their ratio:

- gravity on one vertex: `λ·l·g` = **1.3684e-5 N**
- bending coefficient: `B/l³` = **0.9665 N/m**
- the flat fabric's own rest curvature, as a turning angle: **mean 1.394 rad, max 3.142 rad** —
  these are not small angles, which matters for item 1's coordinate mapping.

**Prestress if bending is measured against a STRAIGHT rest state: 285× gravity at the mean
curvature, 753× at the maximum.** That is the previously recorded "200–32,000×" bracket,
re-measured on this fixture with the current calibrated B.

---

## ITEM 1 — Kaldor-2010 bounded plastic rest-state migration

### What was implemented, and where

`visual/drape.py`, as a named, sourced, **off-by-default** option — not a default that silently
changes existing results:

```
DrapeSetup.plastic_rest_migration: bool = False
DrapeSetup.p_plastic_rad:     float = 0.01     # SOURCED, Kaldor et al. 2010
DrapeSetup.p_max_plastic_rad: float = 2.5      # SOURCED, Kaldor et al. 2010
```

Kaldor, James and Marschner (SIGGRAPH 2010, §3.1) — quoted in `YARN_SLIP_RESEARCH.md` §8(e):

> "If the rest state (represented as a 2D point) at a segment/bending element pair lies outside
> the circle of radius p_plastic centered at the current state of that pair, the rest state is
> projected onto the boundary of the circle. Similarly, if the rest state falls outside the circle
> of radius p_max_plastic centered at the origin, it is projected onto the boundary."

Implemented as `_migrate_rest()`: two projections, in that order, applied once per **accepted**
iteration. It is applied after acceptance on purpose — migrating before the clearance test would
let a reverted iteration leave a permanent mark on the rest state, so the fabric would remember a
configuration it was never allowed to occupy.

### Labels on every parameter

| Item | Label | Note |
|---|---|---|
| The two-projection mechanism | **SOURCED** | S2 §3.1, quoted above |
| `p_plastic = 0.01`, `p_max_plastic = 2.5` | **SOURCED** | S2 Table |
| Angular space → this solver's second-difference rest state | **DERIVED** | `angular_radius_to_lap`: for two equal segments of length `l` meeting at turning angle θ, `‖p₋₁ − 2p₀ + p₊₁‖ = 2l·sin(θ/2)` **exactly**. Not a small-angle linearisation — and this swatch's mean turning angle is 1.394 rad, where a linearisation would misplace the radius by a third. Tested to 1e-15 in the suite. |
| The residual in that mapping | **honest approximation** | the second-difference vector also carries a component along the segment direction, which is length variation rather than angle, so our ball is 3-D where Kaldor's is 2-D. The length projection keeps that component small, not zero. |
| Whether `0.01` transfers dimensionally to *our* yarn, `l` and B | **UNKNOWN** | the value is sourced; the dimensionless group it implies for this fabric is not. Swept, below, rather than asserted. |
| The application **rate** | **UNKNOWN** | Kaldor apply the projections once per dynamic time step; this solver's iterations are a quasi-static descent, not physical time. Measured, below, rather than assumed away. |

### What the bound actually does to the mechanics, in one number

At `p_plastic = 0.01 rad`, the steady-state prestress the fabric can carry is `B/l³ · 2l·sin(p/2)`
= **3.0374e-5 N**, i.e. **2.22× gravity** on a vertex.

So the bound converts the rest-state question from a choice between **285–753× gravity**
(straight) and **0×** (frozen at the relaxed shape) into **2.22×** — internal stress and gravity
of the same order, with the stress opposing whichever curvature change last happened rather than
pulling back to one remembered shape. That is the quantified sense in which Kaldor's rest state
"sits between our two brackets", and it is the one genuinely new piece of mechanics here.

### MEASURED — all runs 800 iterations, calibrated B unless stated

`maxOOP` = max displacement along gravity; `within%` = the share of relief variance **not**
explained by a per-row mean (the corrugated-relief metric, new `relief_profile()`); `margin` =
worst third-loop shape margin in mm, negative being correct; flat reference **−1.540**.

| Configuration | B (N m²) | maxOOP mm | meanOOP | edge curl | within% | margin mm | gate | rest migr. rad |
|---|---|---|---|---|---|---|---|---|
| **A** rest = relaxed (committed default) | 2.5e-09 | 14.104 | 3.804 | 10.307 | 0.8 | −1.599 | PASS | 0 |
| | 3.0e-08 | 1.586 | 0.453 | 1.130 | 0.8 | −1.599 | PASS | 0 |
| | 3.6e-07 | 0.138 | 0.044 | 0.092 | 1.1 | −1.534 | PASS | 0 |
| **B** rest = straight (the other bracket) | 2.5e-09 | 4.716 | 1.257 | 3.455 | 0.7 | **+0.297** | **FAIL** | 0 |
| | 3.0e-08 | 2.151 | 0.124 | 2.037 | 40.4 | −0.938 | PASS | 0 |
| | 3.6e-07 | 2.283 | 0.043 | 2.251 | 88.1 | −0.951 | PASS | 0 |
| **C** KALDOR, from the relaxed rest state | 2.5e-09 | 15.265 | 3.650 | 11.621 | 0.1 | **+1.728** | **FAIL** | 1.673 |
| | 3.0e-08 | 4.461 | 0.558 | 3.903 | 0.0 | −1.399 | PASS | 1.141 |
| | 3.6e-07 | 3.318 | 0.292 | 3.021 | 1.3 | −1.405 | PASS | 1.140 |
| **D** KALDOR, from a straight rest state | 2.5e-09 | 15.251 | 3.645 | 11.613 | 0.1 | **+1.710** | **FAIL** | 2.500 |
| | 3.0e-08 | 4.460 | 0.576 | 3.883 | 0.0 | −1.398 | PASS | 2.500 |
| | 3.6e-07 | 3.321 | 0.308 | 3.006 | 1.3 | −1.443 | PASS | 2.500 |

#### Q1 — Does drape respond to stiffness? YES, but weakly, and the default responds far better.

maxOOP across a **144× range of B**:

- **A** (relaxed): 14.104 → 1.586 → 0.138 — monotonic, **102× spread**, close to proportional.
- **B** (straight): 4.716 → 2.151 → **2.283** — **not monotonic**, 2.2× spread. Reproduces the
  recorded stiffness-blindness of the straight-rest bracket on this fixture.
- **C/D** (Kaldor): 15.265 → 4.461 → 3.318 — monotonic, **4.6× spread**.

So the plastic rest state fixes the straight bracket's stiffness-blindness, and is **much less
stiffness-sensitive than the committed default**. That is expected rather than surprising: the
bound caps the restoring stress at 2.22× gravity, so above that stiffness the fabric's shape is
set by the cap and not by B.

#### Q2 — Do the edge stitches survive? AT THE CALIBRATED B, YES. ACROSS THE BRACKET, NO.

At B = 3.0e-8 the worst third-loop margin is **−1.399 mm** (flat: −1.540). All 25 stitches keep
their shape, 20/20 stay linked, the gate passes, total yarn length changes by 1e-5 % and no strand
ever reached another. So the Kaldor option does **not** reproduce the straight-rest eversion at the
calibrated stiffness — but it **erodes the margin by 0.14 mm**, where the default erodes it by
none, and at the soft end of the bracket (B = 2.5e-9) it **everts stitches and fails the gate**
(+1.728 mm), which the default does not (−1.599 mm).

Diagnosis, before changing anything: the geometry is wrong there, not the instrument. The margin is
+1.7 mm past the threshold, not grazing it, and the same instrument reads −1.599 on the default run
at the same B and the same iteration count. This is the documented eversion failure mode returning
at low stiffness once the restoring stress is capped.

**Consequence: this option must not become the default, and must not be used at the soft end of the
bending bracket.** It is recorded as an option with a stated safe range, not as an improvement.

#### Q3 — Does conformability improve against the corrugated-relief symptom? NO. IT GETS WORSE.

This is the headline negative result, and it is the opposite of what the option was worth trying
for.

`within_row_fraction` — the share of relief variance that a per-row mean does **not** explain — at
the calibrated B:

- **A** default: **0.8 %**
- **C/D** Kaldor: **0.0 %** (within-row RMS 0.0117 mm against a total RMS of ~1 mm)

The rows became **more** rigid, not less. The fabric droops 2.8× further (4.461 mm vs 1.586 mm) but
does so as an even purer function of position along the cantilever. Mechanically that follows: the
plastic rest state erases exactly the local, stitch-scale restoring stress whose variation between
neighbours is the only thing that could make one stitch move differently from the one beside it.

The metric is a **necessary and not sufficient** condition and the table shows why: configuration B
at high stiffness scores 40–88 % within-row variation, which is prestress-driven buckling of a
plate, not cloth. A high score means the rows are not rigid; it does not mean the fabric looks like
crochet.

#### Q4 — p_plastic sweep: the option is SATURATED, and the published value is not special here

At the calibrated B, 800 iterations:

| p_plastic (rad) | 0.0005 | 0.002 | **0.01 (SOURCED)** | 0.05 | 0.25 |
|---|---|---|---|---|---|
| maxOOP mm | 4.461 | 4.488 | **4.461** | 4.867 | 2.925 |
| worst margin mm | −0.639 | −0.768 | **−1.399** | −1.372 | −0.419 |

Droop varies by **1.66× over a 500× range of `p_plastic`**. The projection runs every iteration and
the per-iteration curvature change is far smaller than any of these radii, so the rest state simply
tracks the current curvature with a lag equal to the radius, and the radius barely reaches the
shape. **The stitch margin, however, is worst at the smallest radius** (−0.639 mm at 0.0005, versus
−1.540 flat): the tighter the ball, the less restoring stress is left to hold a stitch's shape. So
`p_plastic` is not a drape dial here; it is a stitch-integrity dial.

#### Q5 — The starting rest state is FORGOTTEN, which is the most consequential finding

Configurations C and D differ **only** in whether the rest state started at the relaxed shape or at
straight — the single decision the entire previous increment turned on. Their results are
indistinguishable: 4.461 vs 4.460 mm maxOOP, −1.399 vs −1.398 mm margin, 0.0 vs 0.0 % within-row.

D's rest migration reads exactly **2.5000 rad** — pinned at `p_max_plastic`, the absolute bound —
confirming the straight rest state is dragged to the cap and then to the current curvature. **With
plasticity on, `rest_is_relaxed_shape` stops meaning anything.** Anyone enabling this option should
know that it silently retires the choice documented as "the whole increment in one decision".

#### Q6 — Iteration dependence: REAL, and it is the same defect item 3 diagnoses

Plastic, calibrated B, p = 0.01 — maxOOP by iteration count: **200 → 2.591; 400 → 3.605;
800 → 4.461; 1600 → 6.004 mm**, still climbing, `converged=False` throughout. The default does the
same thing. So every number in this section is a **transient at a fixed iteration count, not an
equilibrium**, and comparisons between configurations at equal iteration count compare rates of
approach, not shapes. That is stated here rather than discovered later.

### ITEM 1 VERDICT

**Implemented, sourced, measured, and NOT adopted as a default.** It does what the research said it
would — it removes the 285–753× prestress without freezing the rest state, and it restores
monotonic stiffness response to the straight bracket. It does **not** improve conformability: it
makes the corrugated-relief symptom measurably worse, it erodes the stitch-shape margin, and at the
soft end of the bending bracket it everts stitches and fails the gate. The research ranked it
fourth and called it an interim fix for the rest-state bracket rather than a mechanism; that
ranking is confirmed by measurement. **Milestone D does not move.**

---

## ITEM 2 — The recovery experiment, corrected

### Why the first one was invalid, now pinned by a test

`rest_is_relaxed_shape` captures rest curvature at the **start** of the call. Releasing gravity on
an already-draped fabric therefore left the draped shape as its own rest state: bending force zero
by construction, no restoring force, and no possible detection of recovery whichever answer was
true.

Fixed by making the rest state an explicit, passable quantity: `rest_curvature_of(fab)` and
`drape(..., rest_curvature=...)`. Two suite checks now pin the trap itself, so the experiment cannot
be run that way again.

Measured contrast at 400 iterations, from the same loaded state, gravity off:

| Release method | Motion from the loaded state |
|---|---|
| Against the **original flat** rest curvature (correct) | **0.5115 mm** |
| Rest captured at the start of the release call (the invalid version) | **0.0461 mm** |

The invalid version moves 11× less and its residual droop is 0.4432 mm against the loaded 0.4531 —
**2 % apparent "recovery"**. It would have reported the extension as permanent, and that reading
would have been an artefact of the experiment.

### A confound ruled out before anything was concluded

The first corrected run showed intrinsic height *rising* on unload, which raised the possibility
that `apply_contacts` inflates the fabric regardless of load. **Control: the same solve, same rest
curvature, same iteration count, from the flat fabric with gravity already zero.** Result: droop
mean **0.0001 mm**, intrinsic height **−0.000 %**. The solver has no intrinsic drift, so the
inflation hypothesis is wrong and the measured motion is real.

### MEASURED — 5×5, load then release, same rest curvature throughout

| Load / release iterations | droop mean, loaded | droop mean, released | droop recovered | intrinsic h, loaded | intrinsic h, released |
|---|---|---|---|---|---|
| 800 / 800 | 0.4531 mm | 0.3078 mm | **32.1 %** | +0.136 % | +0.334 % |
| 3200 / 3200 | 1.0025 mm | 0.3273 mm | **67.4 %** | +2.042 % | +2.181 % |

Release from the **same** 800-iteration loaded state, for progressively longer (item 2c):

| Release iterations | droop mean | droop max | RMS distance to flat | intrinsic h vs flat |
|---|---|---|---|---|
| 0 (loaded) | 0.4531 | 1.5858 | 0.7363 mm | +0.1355 % |
| 400 | 0.3636 | 1.3611 | 0.6120 mm | +0.2477 % |
| 1600 | 0.2322 | 0.9846 | 0.4060 mm | +0.4233 % |
| 6400 | 0.1022 | 0.5833 | 0.1975 mm | +0.3689 % |
| **25600** | **0.0743** | **0.4751** | **0.1324 mm** | **+0.1017 %** | ← **`converged = True`**, final step 1.00e-05 mm |

The 7×7 swatch behaves the same way: load 800 / release 3200 gives +0.062 % loaded and
+0.229 % released, droop 1.686 mm, 42/42 stitches linked, gate passes, yarn length +1.1e-5 %.

### ITEM 2 VERDICT — ELASTIC, and the experiment had to be run 32x longer to say so

**1. Whether the extension is elastic is not an empirical question for this model — it is a
theorem, and the answer is "elastic".** With plasticity off the model contains **no dissipative
term at all**. Its energy is `(B/2)·Σ‖lap − lap₀‖²/l³` subject to fixed segment lengths, which is
zero at the flat configuration; and for a polyline, fixed segment lengths together with fixed
second-difference **vectors** determine the shape up to translation, which the clamp removes. So
the flat shape is the unique minimiser. **A drape/unload cycle in this solver can only ever report
full recovery given convergence.** Any residual is a convergence artefact, and the invalid
experiment's 2 % was measuring its own construction.

**2. The measurements are consistent with that and confirm it directionally.** The global distance
back to flat falls monotonically with release iterations (0.736 → 0.612 → 0.406 mm) and droop
recovery rises with the budget spent (32 % at 800, 67 % at 3200). Nothing plateaus.

**3. The intrinsic HEIGHT recovers too, but roughly an order of magnitude more slowly, and it
goes the WRONG WAY first.** Released from the same loaded state, intrinsic height reads +0.1355 %
loaded → +0.2477 % (400) → +0.4233 % (1600) → **+0.3689 % (6400)**. It rises for the first few
thousand iterations and only then turns back. Anyone who stopped at 1600 — as the 800- and
3200-iteration paired runs above did — would have measured the extension as *growing* under
unload and concluded it was permanent, or worse, that unloading stretches the fabric.

Diagnosis, and it is a property of the solver rather than of crochet: stitch-to-stitch wale
spacing is a **soft** mode. It changes loop shape at constant yarn length — measured yarn per
stitch changed by **+0.0000 % (max +0.0001 %)**, so nothing stretched, the loops merely reshaped —
and in a gradient descent the relaxation rate of a mode is proportional to its stiffness, so the
softest mode is the slowest to come back. The droop, which is the stiff mode, is 77 % recovered at
6400 release iterations while the height is barely turning around.

**4. At 25600 release iterations the solve CONVERGES, and the answer is ELASTIC.** Its final step
is 1.00e-05 mm, the first converged solve anywhere in this work. Against the loaded state:

- droop mean 0.4531 → **0.0743 mm: 83.6 % recovered**
- RMS distance to flat 0.7363 → **0.1324 mm: 82.0 % recovered**
- intrinsic height +0.1355 % → **+0.1017 %: 75.0 % of the extension recovered**

**So the +2.81 %-family intrinsic-height load extension is ELASTIC, not permanent.** The product's
intrinsic dimensions do come back when the load is removed.

**The residual ~20 % is not dissipation, and saying so requires care.** The model has no
dissipative term, so a residual at convergence must come from somewhere else. The convergence
criterion — largest finished move below 1e-5 mm — bounds the residual bending force at about
2e-7 N, which means curvature has returned to within 2e-4 mm of its rest value while positions
remain 0.1324 mm RMS away from flat. A restoring force has therefore not "run out"; there is
nothing left pulling. **[INFERRED, leading explanation, not established]** the curvature-matching
energy does not rigidly determine the shape of *this* path: it contains 20 degenerate sub-micron
segments and the artificial jumps between ops, at which the second difference does not pin
orientation, so the energy has a small null space and the fabric can sit 0.13 mm from flat at zero
cost. That is a candidate, it is cheap to test, and it is not claimed as a result.

**The methodological point is the one to carry forward: the answer inverts depending on when you
stop.** A release stopped at 1600 iterations reports the extension *growing* (+0.42 %) and would be
written up as permanent. It takes **25600 iterations — 475 s on a 474-vertex swatch** — to reach a
converged answer. And **the recorded "+2.81 % intrinsic-height load extension" is not an equilibrium
property of the product**: it is a transient that grows with the iteration count. On this fixture
the same figure reads +0.136 % at 800 iterations and +2.042 % at 3200, then falls back to +0.102 %
at convergence.

**4. A live risk this exposes in an existing check, reported rather than changed.** `test_drape`
holds intrinsic height to `< 4 %`. That tolerance is now known to bound an unconverged transient
that grows with the iteration count: 0.136 % → 2.042 % for a 4× iteration increase on this
fixture, and 2.81 % on the 7×7 solve. The check will fail on nothing more than running the solver
longer. **I have not touched the threshold** — raising it would hide the growth and lowering it
would fail a correct result. The right fix is to make the quantity converge, which is item 3's
finding, or to measure it at a stated iteration count. Recorded for the next increment.

---

## ITEM 3 — ASTM convergence

### The symptom, reproduced on this fixture

Simulated cantilever tip angle falling as overhang grows is physically backwards. Reproduced (5×5,
calibrated B, `clamp_fraction = 1 − overhang fraction`, the same `drop`/`angle` definitions
`cantilever_test` uses):

| iterations | l = 17.3 | 23.0 | 28.8 | 34.5 | 40.3 mm |
|---|---|---|---|---|---|
| 400 — tip drop mm | 0.680 | 0.708 | 0.730 | 0.730 | 0.730 |
| 400 — tip angle ° | 2.256 | 1.762 | 1.453 | 1.211 | 1.038 |

**At 400 iterations the tip drop is essentially CONSTANT across a 2.3× range of overhang** (0.680
→ 0.730 mm, and identical to four decimals for the three longest). The angle is
`atan(drop / reach)`, so with `drop` fixed and `reach` growing the angle must fall as `1/reach`.
**The falling angle is arithmetic, not stiffness.**

### The cause, established rather than assumed

1. **Every run is unconverged, and the report now says so.** `converged=False` for all 25 runs;
   the final step per iteration is 6e-4 to 2e-3 mm and never reaches the 1e-5 mm convergence test.
   (`DrapeReport.final_step_mm` and `converged` are new; `largest_step_mm` is a maximum over the
   run and cannot distinguish a finished solve from one that ran out of iterations still moving.)
2. **Per-iteration progress is overhang-independent by construction.** The step is
   `0.05·l / max(B/l³·l, |f_grav|max)`, in which nothing depends on the clamp. Gravity therefore
   moves a free vertex ~7.1e-4 mm per iteration whatever the overhang, so at a fixed iteration
   count the tip drop is dominated by near-uniform descent — which is overhang-independent —
   rather than by the integral of curvature along the arm, which is what grows with length.
3. **The clearance cap is NOT the limit.** The measured per-iteration cap is 0.101 mm
   (`0.15 × 0.45 × min gap 1.5 mm`) and the largest step actually taken is 3.1e-3 mm, 33× below
   it. Zero retries, `cap_exceeded = 0`. So the topology guarantee is not what is throttling this,
   and loosening it would not help.
4. **Drop grows with the iteration budget and the ordering repairs itself as it does.** Tip drop
   in mm, five overhangs by five iteration counts, calibrated B:

| iterations | l = 17.3 | 23.0 | 28.8 | 34.5 | 40.3 mm | drop monotonic in overhang? |
|---|---|---|---|---|---|---|
| 400 | 0.680 | 0.708 | 0.730 | 0.730 | 0.730 | **no** |
| 800 | 1.024 | 1.136 | 1.371 | 1.386 | 1.386 | **no** |
| **1600** | 1.281 | 1.500 | 2.302 | 2.550 | 2.657 | **YES** |
| 3200 | 1.490 | 1.768 | 3.263 | 4.046 | 4.491 | YES |
| 6400 | 1.779 | 2.054 | 4.182 | 5.450 | 6.635 | YES |

   Growth per doubling of the iteration count, longest overhang: 1.90, 1.92, 1.69, 1.48 — still
   well above 1.0, so **not one of the 25 runs converged**, and the longer the overhang the further
   from convergence it is, exactly as predicted.

### THE ANSWER TO THE QUESTION AS ASKED

**Tip DROP becomes monotonic in overhang at 1600 iterations** and stays monotonic at 3200 and
6400. The originally reported backwards ordering was measured below that threshold, and it is an
under-convergence artefact. **Established, not assumed.**

**Tip ANGLE becomes monotonic at 6400 iterations for every overhang that spans more than one
row** — 5.10 < 8.27 < 8.97 < 9.35 degrees. It is not monotonic at 3200 (6.68 falls to 6.36 at the
longest overhang).

The one point that stays out of order at every iteration count is the **shortest** overhang, and
that is a third cause rather than a failure of the first two: at `frac = 0.3` the clamp frees
**one row of stitches plus its turning chain** (measured: free rows `[1]`, 112 of 474 vertices,
16.06 mm of actual extent). A one-row specimen is not a beam, so beam quantities are not defined
for it and its tip drop is local stitch sag rather than bending along an arm. **A five-row swatch
cannot form a short cantilever.** That is a limit of the specimen, not of the solver.

So all three causes are instrumental and none is the fabric:

| Cause | Evidence | Fixable by |
|---|---|---|
| Under-convergence (dominant) | drop constant across overhang at 400 it; monotonic from 1600; growth per doubling still 1.5–1.9 at 6400; `converged=False` in all 25 | iterations, or a better solver |
| Nominal ≠ measured overhang | free extent 16.06 vs nominal 17.27 mm; fractions 0.4 and 0.5 free the same two rows | now reported per step (`free_extent_mm`) |
| The shortest overhang is one row deep | free rows `[1]`, 112/474 vertices | a larger swatch |

### What this does to the calibration — the part that matters commercially

ASTM D1388's 41.5° criterion is unreachable at this swatch size, so every bending length quoted
from this solver comes from the small-deflection inversion `c = (l⁴ / 8δ)^(1/3)`. If `δ` at a fixed
iteration count is overhang-independent, then `c` inverted from it scales as `l^(4/3)` — it is a
property of the run, not of the fabric.

**Bending length in mm, inverted from every run. The calibration target was 34.6 mm.**

| iterations | l = 17.3 | 23.0 | 28.8 | 34.5 | 40.3 mm | spread |
|---|---|---|---|---|---|---|
| 400 | 25.37 | 36.73 | 48.97 | 62.44 | 76.69 | **3.02×** |
| 800 | 22.14 | 31.38 | 39.68 | 50.43 | 61.93 | 2.80× |
| 1600 | 20.54 | 28.60 | 33.39 | 41.15 | 49.85 | 2.43× |
| 3200 | 19.53 | 27.08 | 29.72 | 35.28 | 41.85 | 2.14× |
| 6400 | 18.41 | 25.76 | 27.36 | 31.95 | 36.75 | **2.00×** |

Three things follow, and they are the answer to how much of the calibration is trustworthy.

**1. The inverted bending length is not yet a property of the fabric.** At one fixed B it spans
**2.00× across overhang** at the best-converged tier and **3.02×** at the tier the original figures
came from. The same overhang gives **76.69 mm at 400 iterations and 36.75 mm at 6400 — a 2.09×
range for one unchanged fabric.** A quantity that moves by 2× with the iteration count is not a
measurement of the cloth.

**2. The calibration is therefore conditioned on an overhang and an iteration count that the
record does not state.** 34.6 mm is producible from this table at four different overhangs
depending on which iteration count is used — l = 23.0 at 400 iterations, l = 28.8 at 1600,
l = 34.5 at 3200, l = 40.3 at 6400 all land within ~6 % of it. So `CALIBRATED_BENDING_N_M2` was
determined as much by the run configuration as by the target.

**3. Every column is still FALLING at 6400 iterations** (longest overhang: 76.69 → 61.93 → 49.85 →
41.85 → 36.75, ratios 0.81, 0.80, 0.84, 0.88). The converged bending length is therefore **below**
every figure the calibration was set against, which means a calibration redone at convergence would
demand a **larger** B than 3.0e-8 — by roughly `(34.6 / c_converged)³`, which the data do not yet
pin down. **[INFERRED from the trend; not a result, and deliberately not acted on.]**

**I have not changed `CALIBRATED_BENDING_N_M2`.** Changing a physical constant on an extrapolation
would be exactly the kind of move this codebase keeps catching. The honest status of every bending
length quoted so far is: **conditioned on an unconverged solve, and biased high by a factor the
data show is at least 1.2× and may be larger.**

### One further finding, incidental but worth recording

**The calibration procedure is not reproducible from anything in the repository.** `grep` finds no
code and no test that computes a bending length: the procedure exists as prose in `drape.py`'s
docstring and the result exists as the literal `CALIBRATED_BENDING_N_M2 = 3.0e-8`. That is a
derived physical constant whose derivation cannot be re-run, which is the same defect family as a
stale copy of a calibrated number — it cannot be checked, and it cannot be updated when the
solver's convergence behaviour changes. I have **not** changed the constant. Recorded as work for
the next increment: a test that re-derives it and states the overhang and iteration count it is
conditioned on.

---

## What changed in the tree

`visual/drape.py` (Visual-owned) — additive only, no existing default altered:

- `DrapeSetup.plastic_rest_migration` / `p_plastic_rad` / `p_max_plastic_rad` — Kaldor 2010, off
  by default.
- `_migrate_rest()`, `angular_radius_to_lap()` — the sourced mechanism and the derived coordinate
  mapping.
- `rest_curvature_of()` and `drape(rest_curvature=...)` — the rest state as an explicit quantity
  that survives across two calls, without which item 2 cannot be run.
- `relief_profile()` — the corrugated-relief symptom made measurable.
- `DrapeReport.final_step_mm`, `converged`, `rest_migration_max_rad`, `rest_migration_mean_rad` —
  instruments. `converged` is what turned item 3 from a suspicion into a measurement.
- `_laplacian()` — the curvature definition was written out twice in this file; now once.
- `PROVENANCE["plastic_rest_migration"]` — SOURCED mechanism, SOURCED values, DERIVED mapping,
  UNKNOWN rate, stated in that form.
- `cantilever_test()` now reports `free_extent_mm`, `free_vertices`,
  `angle_on_measured_overhang_deg`, `converged`, `final_step_mm` and `iterations` **alongside** the
  existing `overhang_mm` / `tip_angle_deg` pair, which are unchanged — so no committed figure
  moves and the nominal and measured overhangs can be compared. Its docstring now states the two
  things the instrument cannot do, with the measurements behind each.

`tests/test_drape.py` — **23 checks added, 32 -> 55**, nothing weakened, no threshold moved.
Five Visual suites: **34 + 28 + 18 + 24 + 55 = 159 checks, 0 failing** (baseline this
morning: 136). All 28 adversarial fixtures still REJECT broken fabric.

**One of my own new checks failed and the instrument was right.** I asserted
`within_row_fraction > 0.3` on a synthetic fixture whose arithmetic gives exactly 0.235006. The
threshold was invented, the metric was correct. Fixed by replacing the guess with the two fixtures
whose answer the construction pins to a single exact value: displacement that depends only on the
row scores **0**, displacement that varies only across the row scores **1**. A guessed threshold in
an instrument test is how an instrument gets "corrected" to match a wrong expectation.

---

## Milestone D

**FAIL. Unchanged, and not weakened.** None of these three items is a conformability mechanism.
Item 1 measured the best available interim rest state and found it makes the dominant realism
symptom worse. Items 2 and 3 found that a substantial part of what has been measured about this
fabric — load extension, tip angle, bending length — is conditioned on an iteration count rather
than being an equilibrium property, and quantified by how much: the bending length moves 2.09x for
one unchanged fabric across the iteration range, and the load extension inverts sign if you stop
too early. **That makes the calibration less certain than it was before this increment, not more**,
which is a real result and the correct thing to report rather than bury.

### What the next Visual increment should be, on this evidence

Not a new mechanism. Three things this work showed are wrong with the instruments, none of which
needs the Stage 0 measurement and none of which is Stage 1:

1. **Make the cantilever inversion converge, then re-derive `CALIBRATED_BENDING_N_M2` in code with
   a test**, stating the overhang and iteration count it is conditioned on. Today it is a literal
   whose derivation cannot be re-run, and the sweep shows the converged answer differs from the one
   it was set against.
2. **A larger swatch for cantilever work.** Five rows cannot form a short cantilever; the shortest
   overhang frees one row.
3. **Either make the solver converge in a practical budget or state a converged iteration count per
   quantity.** The release solve needed 25600 iterations and 475 s on 474 vertices; nothing under
   gravity converged at 6400. Every drape figure in the record predates that knowledge.

**Stage 1 yarn redistribution / material-coordinate migration was not begun**, per the owner's
ruling that it must not start on the knit analogy alone. The Stage 0 physical measurement remains
the blocking dependency and remains an OWNER ACTION item unchanged by this work.
