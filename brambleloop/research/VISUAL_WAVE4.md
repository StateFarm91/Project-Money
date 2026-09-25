# Visual wave 4 — the tensile stitch linkage exists now, it works, and it is not the missing mechanism

**Department:** Visual (Lane A). **Date:** 2026-09-25 (UTC). **Mode:** Shadow.
**Spend:** CA$0.00 — no model API calls, no image generation, no rendering, nothing deployed.

Continues `VISUAL_WAVE3.md`, which is not restated, not re-run and not revised. No committed
Visual result is discarded, re-derived or reorganised. **Milestone D remains FAIL.** No lock,
threshold or gate was weakened. Stage 0 stays deferred and **Stage 1 yarn redistribution was
not begun** (owner ruling D7).

Labels follow `YARN_SLIP_RESEARCH.md`: **SOURCED / DERIVED / BOUNDED / MEASURED / UNKNOWN**.

---

## THE RESULT, IN ONE LINE

**No.** Tensile stitch linkage paired with the co-rotational rest state does **not** produce
materially more cloth-like behaviour. The force works exactly as derived — it holds the
certified links shut, 1.75 mm of opening reduced to 0.040 mm — and free-edge stitches still
evert, worse than with co-rotation alone (**+2.418 mm** against **+1.121 mm**, flat −1.540,
committed default −1.599).

And the diagnosis is worth more than the negative. Two measurements, neither of which needed
a new force:

1. **With the rest state carried into the vertex frame, the solve CLIMBS.** The certified 5×5
   gains **1.03e-5 J** of bending energy while gravity releases **1.85e-6 J** — it puts in
   five and a half times what drives it. The implemented bending term is a lumped Laplacian,
   not the gradient of the documented energy (wave 3: cosine 0.911), and with a fixed
   world-space rest state that is survivable because `lap → lap_rest` is still a stable fixed
   point. With a co-rotational rest state the target `R(p)·lap_rest` moves with the
   configuration and the two chase each other.
2. **Switch gravity off and the frame-invariant fabric does the same thing anyway.** At 400
   iterations it moves **0.8140 mm** rms from flat at zero gravity against **0.7443 mm** under
   gravity, and everts to **+1.507 mm** against **+1.517 mm**. The committed solver moves
   **0.0004 mm** at zero gravity. **The motion that raised `within_row_fraction` from 0.008 to
   0.154 is not drape. It is a load-independent instability**, and the conformability metric
   was measuring it.

So the mechanism wave 3 named as missing has been built, is correct, is inert on the committed
model, and does not move Milestone D — because the configuration it was supposed to rescue is
not descending an energy at all.

---

## 1. THE FORCE — what it is, and why this relation and no other

### 1a. The relation is the one the topology module certifies

`crochet_topology.certified_linkage_pairs()` is new, and it is the **single definition** of
which stitch was worked into which. `validate` now iterates it to compute its linking numbers,
so "the pairs the linkage check certifies" and "the pairs the solver pulls on" are the same
list by construction rather than by agreement. [The extraction is behaviour preserving: all 28
adversarial fixtures still REJECT and `test_crochet_topology` still passes, before any force
existed.]

For each certified pair the force acts between exactly two things:

| | what it is | where it comes from |
|---|---|---|
| the passing arc | the stitch's **`pull_through`** span — `insert, through, behind, emerge` | `_hdc_cell` names it as the span that goes through the anchor; `Op.pull_through` has carried it since the construction was written |
| the holding arc(s) | the **anchor's own top-loop legs** — `back_loop` under a back-loop target, `front_loop` under a front-loop target, **both** under `both` | these are precisely the arcs `validate` closes with `linkage.close_arc` into the ring it measures the linking number against |

**Why both legs under `both`, and one under a single loop.** Under both top loops the hook
goes through the opening the V bounds, so the strand passes **between** the legs and leaving
either leg is leaving the loop. Under a single loop the new yarn **encircles that one strand**.
That is the same three-case distinction `validate` makes, for the same geometric reason, and
it is not a setting of one knob. [MEASURED that the fixture exercises both cases: 18 of the
20 pairs on the certified 5×5 are single-loop, 2 are `both`.]

Nothing else is used. No "neighbouring vertex", no row-above/row-below heuristic, no distance
threshold picking partners. The foundation row has **no** pair, because it was not worked into
anything — and the validator demands no linking number for it either. 20 pairs on the 5×5
(25 stitches), 72 on the 10×8 (80 stitches), which is exactly `stitches_needing_linkage` in
both cases. [MEASURED, pinned by a check.]

### 1b. It is a constraint, not a spring, and that is why it has no free parameter

Yarn is inextensible and this model does not redistribute it — Stage 1 material-coordinate
migration is forbidden and not begun — so **no yarn can flow through the link**. The closest
approach between the two certified arcs therefore cannot *grow* past its value in the
certified rest configuration: the stitch cannot be pulled out. That is a **one-sided distance
constraint** whose only number, the rest separation, is **measured off the certified
geometry** — 2.1783 to 2.4784 mm on the 5×5, mean 2.4346 mm. A spring would have needed a
stiffness, and a stiffness here would have been the invented drape parameter this module is
forbidden. The relaxation factor is `relaxation.apply_contacts`'s own 0.5, shared rather than
re-invented, because it is the same kind of one-sided projection in the same loop.

It is applied **before** contact and **before** the length projection, so inextensibility
remains the constraint that wins: pulling a stitch back into its loop is never allowed to
stretch the yarn to do it.

### 1c. The two properties it was required to have, both measured

Wave 3 specified the mechanism as one that "resists a stitch being pulled out of the loop it
was worked into, **without also resisting that stitch turning**". A constraint on a *distance*
has that property exactly, and it is measured rather than asserted:

| property | measurement |
|---|---|
| blind to rigid motion | rotate the draped fabric 37° about an arbitrary axis and translate it, with the rest state carried along: extension identical to **<1e-9 mm** |
| does not fight a curved surface | wrap the swatch round a **125 mm** cylinder — every stitch moves, the third-loop margin erodes from −1.540 to −1.120 — and the worst certified link opens by **0.0002 mm** |
| tension only | inflate every rest separation by 1 mm so every pair reads closed: the force moves the fabric by **exactly 0.0 mm**. Pushing apart is contact's job and two copies of that floor would be two places for it to drift |

### 1d. It does what it was built to do

MEASURED, 5×5, 400 iterations, everything identical but the force:

| | worst link opening over the run | at the end |
|---|---|---|
| co-rotation alone | **1.1409 mm** | 1.1409 |
| co-rotation + tensile linkage | **0.0400 mm** | 0.0051 |

At 800 iterations, 1.7527 mm against 0.0400 mm — a factor of **44**. The links are held shut.

---

## 2. THE CONTROL — the new force does not move the committed model

Same swatch, same B, same 800 iterations, same everything but the force. [MEASURED.]

| | maxOOP | worst third-loop margin | shaped | gate | within-row relief | worst link opening |
|---|---|---|---|---|---|---|
| **committed default** | 1.5858 mm | **−1.599** | 25/25 | PASS | 0.0083 | 0.1457 mm |
| **default + tensile linkage** | 1.5781 | **−1.599** | 25/25 | PASS | 0.0079 | **0.0079** |

Droop differs by 0.5 %, the margin is identical to three decimals, every lock reads the same.
**On the committed model the links barely open in the first place** (0.146 mm worst), so the
constraint is almost never active. That is the right result for an option that must not move
a committed figure, and it is pinned by a check.

---

## 3. THE EXPERIMENT — every configuration, every lock, two sizes, two cylinders

All runs 800 iterations at the committed `B = 3.0e-8 N m²`, `clamp_fraction = 0.5`,
`benchmarks.cardigan("S")` body, `build → settle → relax(600)`. 5×5 = 474 vertices / 25 hdc;
10×8 = 1494 vertices / 80 hdc. `grad` is §5's gradient form of the bending term.

### 3a. 5×5

| lock | control | + linkage | linkage + co-rotation | grad + co-rotation | **grad + co-rotation + linkage** |
|---|---|---|---|---|---|
| topology gate | PASS | PASS | **FAIL** | PASS | **PASS** |
| linkage | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| stitch morphology | 25/25 | 25/25 | **22/25** | 25/25 | **25/25** |
| unmeasurable / unframeable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| identity, row, position | held | held | held | held | held |
| loop targets | held | held | held | held | held |
| min gap | 1.5000 mm | 1.5000 | 1.5000 | 1.5000 | 1.5000 |
| pull-through impossible | True | True | True | True | True |
| **yarn length change** | **+1.4e-5 %** | **+1.4e-5 %** | **+2.5e-5 %** | **−3e-7 %** | **+4e-6 %** |
| max measurable strain | 0.000005 | 0.000005 | 0.000021 | 0.000007 | 0.000014 |
| join within a row | 0.003→0.003 | 0.003→0.003 | 0.003→0.003 | 0.003→0.003 | 0.003→0.003 |
| join at a turn | 5.998→5.998 | 5.998→5.998 | 5.998→5.998 | 5.998→5.998 | 5.998→5.998 |
| intrinsic width | −0.044 % | −0.045 % | +0.225 % | −0.103 % | −0.116 % |
| intrinsic height | +0.136 % | +0.147 % | +0.665 % | +0.021 % | +0.013 % |
| **worst third-loop margin** | **−1.599** | **−1.599** | **+2.418** | **−0.402** | **−0.414** |
| maxOOP | 1.5858 | 1.5781 | 3.4258 | 1.2546 | 1.1934 |
| within-row relief | 0.0083 | 0.0079 | 0.3334 | 0.1002 | 0.0471 |
| local articulation | 3.388° | 3.271° | 9.117° | 1.779° | 1.619° |
| worst link opening over the run | 0.1457 | 0.0079 | 0.0400 | 0.4368 | 0.0141 |

### 3b. 10×8

| lock | control | + linkage | linkage + co-rotation | grad + co-rotation | **grad + co-rotation + linkage** |
|---|---|---|---|---|---|
| topology gate | PASS | PASS | **FAIL** | PASS | **PASS** |
| linkage | 72/72 | 72/72 | 72/72 | 72/72 | 72/72 |
| stitch morphology | 80/80 | 80/80 | **74/80** | 80/80 | **80/80** |
| unmeasurable / unframeable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| min gap | 1.5000 mm | 1.5000 | 1.5000 | 1.5000 | 1.5000 |
| yarn length change | +1.9e-5 % | +2.0e-5 % | −1e-6 % | −2.3e-5 % | +1.6e-5 % |
| max measurable strain | 0.000020 | 0.000019 | 0.000115 | 0.000079 | 0.000090 |
| intrinsic width | −0.037 % | −0.037 % | +0.041 % | −0.039 % | −0.041 % |
| intrinsic height | +0.034 % | +0.033 % | +0.332 % | +0.019 % | +0.016 % |
| **worst third-loop margin** | **−1.453** | **−1.495** | **+1.871** | **−0.444** | **−0.446** |
| maxOOP | 1.6894 | 1.6843 | 3.4532 | 1.2406 | 1.2265 |
| within-row relief | 0.0031 | 0.0026 | 0.1341 | 0.0769 | 0.0681 |
| local articulation | 2.062° | 1.926° | 3.213° | 1.572° | 1.567° |
| worst link opening over the run | 0.2166 | 0.0095 | 0.0068 | 0.5279 | 0.0043 |

**The larger swatch behaves like the small one on every lock and every configuration**, which
is the first time that has been checked for these options. Eversion is worse on the 10×8 in
count (6 stitches against 3) and milder in margin (+1.871 against +2.418).

### 3c. The curved configurations — wave 3's cylinders, reused unchanged

Static isometric wraps of the certified geometry, so the numbers are directly comparable with
wave 3's table. The new column is the certified linkage.

| lock | 5×5 R=500 mm (κ=2) | 5×5 R=125 mm (κ=8) | 10×8 R=500 mm | 10×8 R=125 mm |
|---|---|---|---|---|
| topology gate | PASS | PASS | PASS | PASS |
| linkage | 20/20 | 20/20 | 72/72 | 72/72 |
| stitch morphology | 25/25 | 25/25 | 80/80 | 80/80 |
| unmeasurable / unframeable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| min gap | 1.5061 mm | 1.5239 | 1.5061 | 1.5239 |
| yarn length change | +0.000 % | +0.000 % | +0.000 % | +0.000 % |
| intrinsic width | −0.0000 % | −0.0000 % | −0.0000 % | −0.0000 % |
| intrinsic height | +0.092 % | +0.289 % | +0.092 % | +0.288 % |
| worst third-loop margin | −1.466 | −1.120 | −1.466 | −1.120 |
| within-row relief | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| local articulation | 0.720° | 2.057° | 0.526° | 1.329° |
| **worst certified link opening** | **0.0003 mm** | **0.0002 mm** | **0.0003 mm** | **0.0002 mm** |

**A pure bend of the cloth opens no link.** That is the constraint's most important negative
property measured on real curved geometry rather than on a rotation: it does not resist the
fabric conforming.

---

## 4. EVERSION — measured, and diagnosed as geometry rather than instrument

The specific failure that made co-rotation unadoptable. **It does not disappear.**

| configuration | worst third-loop margin | stitches shaped |
|---|---|---|
| flat baseline | **−1.540** | 25/25 |
| committed default | **−1.599** | 25/25 |
| default + tensile linkage | −1.599 | 25/25 |
| co-rotation alone | +1.121 | 21/25 |
| **co-rotation + tensile linkage** | **+2.418** | 22/25 |
| grad + co-rotation | −0.402 | 25/25 |
| **grad + co-rotation + tensile linkage** | **−0.414** | 25/25 |

Adding the linkage to co-rotation under the committed force law **recovers one stitch's shape
(21→22) and makes the worst margin 1.30 mm worse.** The fabric droops further (3.43 mm against
2.36 mm) and the extra load reaches the free tip.

### Is it a deformed stitch or a rotated measuring frame?

Diagnosed before anything was changed, by Kabsch-fitting each draped stitch onto its own flat
points and re-reading the margin in the **co-rotated** frame — the flat frame carried by the
stitch's own rigid rotation — as well as in the neighbour-derived frame the validator uses.
A stitch that merely rotated fits rigidly and reads correct in its own frame. [MEASURED, 5×5,
800 iterations.]

| stitch | flat | neighbour frame | co-rotated frame | residual from a rigid fit |
|---|---|---|---|---|
| **co-rotation + linkage**, r1p2 | −1.654 | **+2.418** | **+1.409** | **1.679 mm** |
| r1p1 | −1.654 | +2.047 | +1.169 | 1.475 |
| r1p3 | −1.646 | +1.536 | +0.875 | 1.521 |
| r2p2 | −1.640 | −0.523 | −1.675 | 0.631 |
| **committed default**, worst stitch | −1.599 | −1.599 | −1.599 | 0.000 |

**It is the geometry.** The three failing stitches are 1.5–1.7 mm away from any rigid motion
of themselves on a 6.90 mm stitch pitch, and they read everted **in their own co-rotated
frame** as well as in the validator's. The frame contributes — r2p2 reads −0.523 in the
neighbour frame and −1.675 co-rotated, so part of what the validator sees there is the frame
turning — but that stitch passes anyway. The ones that fail are deformed.

**Every failing stitch is in the foundation row**, which is the free tip of the cantilever and
the one row with **no certified linkage at all**: it was not worked into anything, so there is
nothing for a tensile link to hold it by. That is not a gap in the force; it is what crochet
is. The foundation row's *top* loops are held — they are the holding arcs of the row above —
and it is the body of the stitch below them that turns inside out.

---

## 5. WHY THE EXPERIMENT COULD NOT BE DECIDED IN THIS SOLVER AS IT STOOD

### 5a. The co-rotational energy is correct. Verified, not assumed.

Before blaming it, it was tested on constructed geometry with nothing else present: a
three-vertex chain, equal segments, rest turning angle t₀, current angle t₀+δ, opened
symmetrically so there is no net rotation to remove. [MEASURED.]

| t₀ | δ | world-space energy | co-rotational energy | ratio |
|---|---|---|---|---|
| 30° | 1° / 5° / 20° | 7.90e-11 / 2.24e-9 / 5.33e-8 J | identical | **1.00000** |
| 80° | 1° / 5° / 20° | 4.77e-10 / 1.24e-8 / 2.28e-7 | identical | **1.00000** |
| 140° | 1° / 5° / 20° | 1.01e-9 / 2.56e-8 / 4.25e-7 | identical | **1.00000** |
| a pure 25° rotation | — | 1.65e-6 J | **5.7e-37 J** | — |

**The co-rotational form charges for a genuine bend exactly, and for a rotation not at all.**
It does not absorb deformation. Wave 3's 109× compliance figure is the removal of a spurious
term, not a softening of real bending. Nothing here is wrong with the energy.

### 5b. The FORCE is not a descent direction for it

Bending energy and gravitational potential along the run, 5×5, committed B, energies measured
in the form each configuration is supposed to be minimising. [MEASURED.]

| iterations | committed default: bend / potential / total | co-rotation: bend / potential / total |
|---|---|---|
| 0 | 0 / 0 / **0** | 4.2e-34 / 0 / **4.2e-34** |
| 50 | 1.82e-8 / −3.08e-7 / **−2.90e-7** | 8.17e-6 / −2.89e-8 / **+8.15e-6** |
| 100 | 3.35e-8 / −5.84e-7 / **−5.50e-7** | 8.70e-6 / −3.53e-8 / **+8.66e-6** |
| 200 | 6.87e-8 / −1.10e-6 / **−1.03e-6** | 8.33e-6 / −5.84e-8 / **+8.27e-6** |
| 400 | 2.35e-7 / −2.03e-6 / **−1.79e-6** | 5.72e-6 / −3.01e-7 / **+5.42e-6** |
| 800 | 5.98e-7 / −3.52e-6 / **−2.92e-6** | 1.03e-5 / −1.85e-6 / **+8.44e-6** |

**The committed solve descends monotonically. The co-rotational solve climbs, within fifty
iterations, and then oscillates** — 8.15, 8.66, 8.27, 5.42, 8.44 e-6 J. It puts in **5.6×**
the energy gravity releases.

The mechanism is the one wave 3 already named, in a place it had not been looked for. The
implemented bending term is `bend_coeff·(lap − lap_rest)`, a lumped Laplacian, not the
gradient `−bend_coeff·Dᵀ(lap − lap_rest)` of the documented energy. With `lap_rest` FIXED,
`lap → lap_rest` is still a stable fixed point of that update, so the run descends despite the
mismatch. With the rest state carried into the vertex frame the target is `R(p)·lap_rest`,
which **moves with the configuration**: the fit re-orients to whatever deformation just
happened, the residual is taken against the new orientation, and the two chase each other.

### 5c. So the gradient was implemented, and the experiment re-run

`DrapeSetup.energy_gradient_bending`, OFF by default, replaces the term with
`−B/l³·Dᵀ(lap − oriented)`, which is the gradient — the suite already verifies that expression
against central differences of the energy on the certified geometry to a worst relative error
of 3e-8, and that check was not touched. There is **no new constant** in it; the step's
reference force scale is multiplied by 4 because Dᵀ has an absolute row sum of 4, which is
arithmetic.

With it, at 400 iterations, `grad + co-rotation + linkage`: **25/25 shaped, gate PASS, worst
margin −0.692**, and at 800, **−0.414**. **Eversion disappears.** Every lock in §3a and §3b
passes. That is the first configuration in this work in which the spurious rotational
stiffness is gone and Product Truth survives.

It still does not make Milestone D pass, and §6 is why.

---

## 6. IS IT ARTICULATION, OR MORE DISPLACEMENT? — NEITHER. IT IS NOT A LOAD RESPONSE AT ALL.

This is the measurement that decides the increment, and it is one line of method: **run the
identical solve with gravity switched off.** Whatever still happens is not drape.

MEASURED, 5×5, 400 iterations, `gravity=0.0` against `gravity=9.80665`, everything else
identical. The step size is unchanged between the two because the bending term dominates the
step's reference force (1.797e-3 N against 1.78e-5 N of weight), so this is a clean pair.

| configuration | rms motion from flat, g = 9.81 | rms motion, **g = 0** | margin, g = 9.81 | margin, **g = 0** |
|---|---|---|---|---|
| **committed default** | 0.4123 mm | **0.0004 mm** | −1.561 | −1.539 |
| co-rotation | 0.7443 | **0.8140** | +1.517 | **+1.507** |
| grad + co-rotation + linkage | 0.2546 | **0.2495** | −0.692 | **−0.699** |

**The committed solver has no drift — 0.0004 mm at zero gravity, which is wave 2's control
reproduced. Every frame-invariant configuration does essentially all of its motion with the
load removed.** 109 % of it for co-rotation alone, 98 % for the gradient form with linkage.

So the honest answer to "does the fabric gain local articulation, or merely more
displacement?" is **neither**. It gains a **load-independent instability**. The
`within_row_fraction` reading that looked like the first movement in the right direction —
0.0083 → 0.1544 in wave 3, → 0.3334 here — is measuring that instability: at zero gravity the
same configurations read 0.1104 and 0.2662 on the same metric.

**What drives it.** The certified relaxed fabric is not an equilibrium of `drape`'s own contact
model: its minimum segment separation is 1.5000 mm — the compressed-contact floor — while
`material.rest_separation_mm` is 2.0667 mm, so `apply_contacts` is pushing from iteration
zero. In the committed model the world-frame bending term resists that rearrangement, which is
the same stiffness wave 3 identified as spurious. Remove it and contact rearranges the fabric
freely, with no load applied. [MEASURED; the min gap stays pinned at 1.5000 mm in every run,
so it is rearrangement rather than inflation.]

### The supplementary measure, offered with its floor and not used to claim anything

`relief_profile`'s `within_row_fraction` stays the primary metric, as instructed. Wave 3's
warning about it is confirmed rather than worked around, and the zero-gravity control is what
confirms it: a high score means the rows are not rigid, and says nothing about what made them
move.

A second measure was derived because the first cannot distinguish a wavelength:
`articulation_profile` takes the **second difference of the surface normal across the stitch
grid**, which is exactly zero for a rigid panel (all normals equal) and exactly zero for a
uniform cylinder (the normal turns by the same angle every step). A plate buckles smoothly
over many stitches and scores low; cloth articulating at the stitch scores high.

**Its floor on real geometry is reported because it is not zero**: the certified flat 5×5
reads **0.519°**, the 500 mm cylinder **0.720°**, the 125 mm cylinder **2.057°**. The stitch
centres a frame is built from are not a smooth sample of any surface. So it is a comparative
measure with a stated floor, it is reported alongside the committed metric and never instead
of it, and **it does not rescue the result**: `grad + co-rotation + linkage` reads **1.619°**
against the committed default's **3.388°** — lower, not higher. It is pinned in the suite as
invariant under a rigid rotation of the fabric.

---

## 7. THE NON-MONOTONE VALIDITY FINDING — diagnosed

Wave 3 found the product's validity is not monotone in the iteration count with frame
invariance on, and asked whether an intermediate topology failure is **actual strand passage**
or an **instrument / sampling issue**. Re-measured, and extended to the new configurations and
to 3200 iterations. [MEASURED, 5×5, committed B.]

| config | 100 | 200 | 400 | 800 | 1600 | 3200 |
|---|---|---|---|---|---|---|
| **co-rotation** — gate | PASS | FAIL | FAIL | FAIL | **PASS** | FAIL |
| linked | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | **17/20** |
| shaped | 25/25 | 21/25 | 21/25 | 21/25 | 25/25 | 20/25 |
| margin | −0.417 | +0.574 | +1.517 | +1.121 | −0.426 | +3.547 |
| **worst link opening so far** | **0.3083** | **0.6465** | **1.1409** | **1.7527** | **1.7527** | **1.7527** |
| **co-rotation + linkage** — gate | PASS | FAIL | FAIL | FAIL | FAIL | FAIL |
| linked | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 19/20 |
| shaped | 25/25 | 22/25 | 22/25 | 22/25 | 24/25 | 18/25 |
| margin | −0.402 | +0.500 | +1.466 | +2.418 | +0.062 | +3.189 |
| worst link opening so far | 0.0330 | 0.0400 | 0.0400 | 0.0400 | 0.0400 | 0.0697 |
| **grad + co-rotation + linkage** — gate | PASS | PASS | PASS | **PASS** | FAIL | FAIL |
| shaped | 25/25 | 25/25 | 25/25 | 25/25 | 24/25 | 23/25 |
| margin | −0.962 | −0.722 | −0.692 | −0.414 | +0.030 | +1.107 |

Wave 3's sequence is reproduced exactly (valid at 100, broken 200–800, valid at 1600, broken
at 3200). **The gradient form is monotone out to 800 and then fails too**, consistent with §6:
nothing has stopped the load-independent drift, only slowed it.

### The diagnosis asked for: instrument, and the evidence is three-fold

**1. No strand ever passed another, and that is a continuous guarantee rather than an
end-of-solve reading.** `min_gap_seen_mm` is 1.5000 mm in **every** run in this file,
`cap_exceeded` is 0 and `crossing_impossible` is True, including the 3200-iteration run that
reports 17 of 20 linked. The solver measures the clearance and spends it down, reverting and
retrying any iteration whose finished move exceeds it, so between one look at the geometry and
the next no strand can reach another. **A linking number between two real closed curves cannot
change without a crossing.** So the change is in the instrument's fictitious part.

**2. The certified linkage barely opened.** At 3200 iterations the `co-rotation + linkage` run
reports 19 of 20 linked while its worst certified link has opened by **0.0697 mm** against
rest separations of 2.18–2.48 mm. A stitch that has genuinely been drawn out of its loop is
not 0.07 mm from where it was worked.

**3. The direct test.** The three "unlinked" stitches at 3200 iterations are all single-loop
targets, measured by `_encirclement`, which closes a single top loop through a **fictitious**
point and tries ten structured directions, taking one clear detection as proof. Re-measured
against 400 directions drawn at random on the sphere, with the same clearance test:

| stitch | the instrument's ten directions | 400 directions |
|---|---|---|
| r2p4 | 8 had room, **0 found the crossing** | 365 had room, **52 found it** |
| r2p2 | 10 had room, **0 found it** | 373 had room, **57 found it** |
| r2p1 | 10 had room, **0 found it** | 371 had room, **50 found it** |
| r2p3 — reported LINKED | 10 had room, **1 found it** | 363 had room, 60 found it |

**The stitches are linked. The instrument ran out of triangles.** And the margin is
measurable on correct geometry too: on the certified flat 5×5 and on both cylinders, **40 %**
of closure directions detect the crossing (min 0.397, mean 0.402–0.414 over the 18 single-loop
stitches). On the strongly deformed 3200-iteration geometry that falls to **14 %**, and the
ten structured directions — which are built from the local frame, and the local frame is what
the deformation has turned — find none.

**Written down before changing anything, and nothing changed.** `_encirclement` produces a
FALSE NEGATIVE on strongly deformed cloth. Fixing it means enlarging the closure set, which
makes the linkage lock *stricter about nothing* but changes a committed instrument that all 28
adversarial fixtures are calibrated against — so it is an owner-visible change to a lock, not
a patch to slip into an increment whose result is a negative. **The direction set was not
touched, no threshold was moved, and the defect is pinned by a check on the cheap
configurations so the margin cannot thin further unnoticed.** Recorded as the next increment's
work, with the measurement that justifies it.

### How to guard it, and what the guard costs

Wave 3 declined continuous per-iteration validation because it costs a topology pass per
iteration. Measured, 5×5, 474 vertices: [MEASURED.]

| per-iteration cost | |
|---|---|
| one full topology pass (`validate`) | **97.673 ms** |
| one third-loop morphology margin pass | 2.168 ms |
| one `articulation_profile` pass | 1.384 ms |
| **one certified-linkage closest-approach pass** | **0.081 ms** |
| the whole 400-iteration solve, watch off / on | 12.99 s / **11.23 s** (within noise) |

Continuous topology validation would cost **39 s on top of a 13 s solve — 4× the solve**.
Wave 3 was right to decline it, and it would in any case be guarding with the instrument §7
just showed produces false negatives on exactly the geometry it would be watching.

**The cheaper sufficient invariant exists and is now checked every iteration.**
`DrapeSetup.watch_linkage` (default **True**) records the worst opening of any certified link
over the **whole run**, at 0.081 ms per iteration — **1,200× cheaper than a topology pass**,
and free against the solve. It is sufficient for the question an end-of-solve gate cannot
answer, and the reason it is sufficient is §7's first two points: the solver already
guarantees continuously that no strand passed another, so the only way a stitch can leave its
loop is by the link OPENING, and that is what this measures.

**And it is monotone where the gate is not.** For co-rotation alone the worst opening reads
0.3083 → 0.6465 → 1.1409 → 1.7527 mm and then never falls, across exactly the iteration counts
where the gate goes PASS → FAIL → FAIL → FAIL → **PASS** → FAIL. **A run that ends at 1600
iterations reports a clean gate and a worst opening of 1.7527 mm — the guard sees what the gate
cannot**, which is precisely the gap wave 3 recorded. `DrapeReport.linkage_max_extension_mm`
and `linkage_worst_iteration` carry it, and a check pins that the maximum is over the run
rather than the value at the end.

**What it does not cover, stated rather than implied.** It sees a link opening. It does not
see a stitch's *shape* failing with its link intact, which is what the third-loop margin
catches and what actually fails in these runs. A continuous morphology guard would cost 2.168
ms per iteration — 7 % of a 400-iteration solve, affordable — and is the obvious companion. It
is **not** wired in here, because a guard that would have fired on every frame-invariant run
in this file needs a decided policy for what it does when it fires, and the configuration it
would be guarding is not adoptable anyway.

---

## 8. MILESTONE D

**FAIL. Unchanged, not weakened, no threshold lowered, no lock relaxed.**

What this increment establishes, with the evidence rather than the hope:

- **The tensile stitch linkage that wave 3 named as the missing mechanism now exists**, is
  derived from the relation the topology module certifies, has no free parameter, holds the
  certified links shut by a factor of 44, does not resist rotation or a bend of the cloth, and
  is inert on the committed model. It is a correct piece of mechanics.
- **It is not what was missing.** Free-edge eversion is unchanged by it, because the row that
  everts is the foundation row, which has no linkage by construction.
- **The pairing it was to be evaluated with cannot be evaluated in this solver as it stood**,
  because the implemented bending force is not a descent direction for the co-rotational
  energy. Correcting the force law to the actual gradient removes the eversion and passes every
  lock — and the zero-gravity control shows what remains is **not drape**.
- **The standing conformability symptom has not moved.** The only configuration that improves
  `within_row_fraction` does essentially all of its motion with the load switched off.

**The next mechanism is now specific and falsifiable, and it is not a new force.** The
certified relaxed fabric is not an equilibrium of `drape`'s own contact model — 1.5000 mm of
clearance against a 2.0667 mm rest separation — so every drape run begins by rearranging the
fabric under contact, and the committed model's only defence against that is the spurious
rotational stiffness. **Until the flat fabric is an equilibrium of the solver it is dropped
into, no experiment that removes that stiffness can be read**, because the first thing it
measures is the fabric settling out of a state it was never in equilibrium in. That is a
statement about the model, it needs no Stage 0 measurement, and it is not Stage 1.

---

## What changed in the tree

`visual/crochet_topology.py` — **additive and behaviour preserving**, verified against all 28
adversarial fixtures before any force existed:

- `LinkagePair`, `certified_linkage_pairs()` — the stitch-to-stitch linkage as spans of the
  yarn path, in ONE place. `validate` now iterates it, so the relation the validator certifies
  and the relation the solver acts on cannot drift into two ideas of what crochet is.
- `stitch_frames()` — the fabric's own local frame at every stitch, extracted from inside
  `validate` unchanged, so anything outside the module uses the same frame the locks do.

`visual/drape.py` — **additive; no existing default altered and no committed figure moved**:

- `linkage_holds()`, `linkage_rest_separations()`, `apply_stitch_linkage()`,
  `linkage_extension()`, `LINKAGE_GAIN` — the tensile linkage, its measured rest state, and
  the instrument that reads it on any configuration.
- `DrapeSetup.stitch_linkage` (default **False**), `watch_linkage` (default **True**).
- `DrapeSetup.energy_gradient_bending` (default **False**) — the bending term as the gradient
  of the documented energy.
- `DrapeReport.linkage_pairs`, `linkage_holds`, `linkage_max_extension_mm`,
  `linkage_final_extension_mm`, `linkage_worst_iteration` — the continuous guard's readings,
  maxima over the run rather than end-of-solve values.
- `articulation_profile()` — the supplementary conformability measure, with its measured floor
  in its docstring.

`tests/test_crochet_topology.py` — **9 checks added, 34 → 43, 0 failing.**
`tests/test_drape.py` — checks added for every new behaviour, including **four recorded
negatives**: the linkage does not stop eversion; the co-rotational run climbs; the
frame-invariant fabric moves the same distance with gravity off; and the single-loop linkage
instrument's closure margin. Nothing weakened, no threshold moved, no existing check deleted
or relaxed.

CA$0.00. No model calls. No image generation. Nothing published, nothing deployed. Committed
on the worktree branch, **not pushed** — the integrator merges.
