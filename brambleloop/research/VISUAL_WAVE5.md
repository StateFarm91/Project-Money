# Visual wave 5 — the fabric is an equilibrium now, and the instability was never in the yarn

**Department:** Visual (Lane B). **Date:** 2026-09-25 (UTC). **Mode:** Shadow.
**Spend:** CA$0.00 — no model API calls, no image-generation API calls, nothing deployed.

Continues `VISUAL_WAVE4.md`, which is not restated, not re-run and not revised except where
this file says so explicitly and shows the measurement. No committed Visual result is
discarded or re-derived. **Milestone D remains FAIL.** No lock, gate or threshold was
weakened. Stage 0 stays deferred and **Stage 1 yarn redistribution was not begun** (owner
ruling D7).

Labels follow `YARN_SLIP_RESEARCH.md`: **SOURCED / DERIVED / BOUNDED / MEASURED / UNKNOWN**.

---

## THE RESULT, IN ONE LINE

**Yes.** The certified relaxed fabric is now an **exact** fixed point of the solver's contact
model — zero gravity, 800 iterations, **1.58e-17 mm rms**, converged at iteration 1 — and with
that seed removed the reconciled co-rotational configuration **descends its own energy under
load for the first time in this programme**, passes every Product Truth lock at both swatch
sizes, and does **nothing at all** with the load switched off.

And the diagnosis is again worth more than the headline. Three measurements, in the order they
had to be made:

1. **Wave 4's attribution was right about the seed and wrong about the mechanism, by a factor
   of about 750.** The contact disequilibrium is real, but as a *displacement* it is worth
   **0.0011 mm rms** over 400 iterations — measured in the null case, bending removed
   entirely, gravity off. It cannot move a fabric 0.814 mm. What it does is **perturb** an
   equilibrium that the co-rotational rest state has made **unstable**, and the instability
   supplies the other 99.9 %.
2. **The certified configuration is the GLOBAL MINIMUM of the energy the solver is
   minimising**, exactly: `lap = lap_rest` and the co-rotational `R = I`, so
   `E = (B/2l³) Σ |lap − R·lap_rest|² = 0` and the energy is a sum of squares. With gravity
   off there is nothing else to minimise. **Every millimetre the frame-invariant solve moves
   at zero load is it climbing out of the global minimum of its own energy**, and that needs
   no interpretation at all.
3. **The climb is not in the yarn. It is in the parts of the stored path that are not yarn.**
   One loaded iteration of `gradient + co-rotation`, from a state made an exact equilibrium of
   contact, injects **9.7564e-06 J** of bending energy — more than the entire gravitational
   budget of the committed 800-iteration solve. Of that, **4.0e-13 J is on the 312 genuine
   yarn vertices and 9.7564e-06 J is on the 162 artificial hops and sub-micron joins.** Not
   90 per cent. **99.99996 per cent.**

The co-rotational frame is fitted to each vertex's two **edge directions**. At a 28-nanometre
join an edge direction is numerically meaningless — a nanometre of motion turns it through two
degrees — so the fitted rotation there is not a continuous function of the configuration, and
it is refitted every iteration. `genuine_yarn_vertices()` has identified exactly those
vertices since wave 3, which recorded that the bending term does not exclude them and
deliberately did not change it. This is the measurement that makes excluding them unavoidable.

---

## 0. The fixtures, unchanged, so every number is comparable with waves 2–4

`benchmarks.cardigan("S")` body, `build → settle → relax(600)`, exactly as `test_drape` builds
it. 5×5 = 474 vertices / 25 hdc; 10×8 = 1494 vertices / 80 hdc. `B = 3.0e-8 N m²`
(`CALIBRATED_BENDING_N_M2`, **unchanged**), `clamp_fraction = 0.5`, `down = −z`,
`ell = 4.0860 mm`, `B/l³ = 0.43976 N/m`. Cylinders are wave 3's isometric wraps, reused
unchanged.

**The control reproduces waves 3 and 4 exactly** before anything new is switched on: 5×5
worst third-loop margin **−1.599**, 10×8 **−1.453**, min gap **1.5000 mm**, and the static
cylinder wraps read **−1.466 / −1.120**, min gap **1.5061 / 1.5239**, intrinsic width
**−0.0000 %**, articulation **0.720° / 2.057°** — every figure in wave 4 §3c, to the digit.

---

## 1. IS THE CERTIFIED FABRIC AN EQUILIBRIUM OF THE CONTACT MODEL?

### 1a. What the disequilibrium actually is — two pairs, and both are the same fold

Wave 4 left this as "1.5000 mm clearance against a 2.0667 mm rest separation, so
`apply_contacts` is pushing from iteration zero". That is true of the minimum. It is not true
of the fabric. [MEASURED on the certified geometry, no solve.]

| | 5×5 | 10×8 |
|---|---|---|
| pairs of yarn segments in contact (`dist < rest_sep = 2.0667 mm`) | **96** | **296** |
| separation: min / p05 / median / max | 1.5000 / 2.0614 / 2.0663 / 2.0667 | 1.5000 / 2.0641 / 2.0662 / 2.0667 |
| pairs below the compressed floor | **0** | **0** |
| pairs with a deficit over 0.0001 mm | 51 | 164 |
| pairs with a deficit over 0.01 mm | **5** | **8** |
| pairs with a deficit over 0.05 mm | **2** | **2** |
| total deficit | 1.242 mm | 1.464 mm, of which **1.133 mm is those two pairs** |

**Two pairs carry 91 per cent of it, and they are the same two on both swatch sizes.** Segments
(463, 465) and (391, 393) on the 5×5; (1483, 1485) and (1357, 1359) on the 10×8. Every one is
the identical local feature: a fold **inside one hdc stitch**, where the yarn doubles back and
segments `i` and `i+2` are bridged by a single **2.1485 mm** inextensible segment. It is
**genuine yarn on both sides** — not one of the path's artificial hops — and it is the pair
`min_segment_separation` has been reporting as the fabric's 1.5000 mm clearance all along.

So the honest form of the finding is: **the certified fabric is an equilibrium of the contact
model everywhere except at two intra-stitch folds, which are jammed against the compressed
floor by the inextensible segment that bridges them.**

### 1b. And as a displacement it is worth a thousandth of a millimetre

The measurement that settles its size is the **null case**: strip the bending term out
entirely (`B = 0`), switch gravity off, and run the solver. Whatever moves is contact and
inextensibility, and nothing else. [MEASURED, 5×5, `clamp_fraction = 0.5`.]

| configuration, gravity OFF | rms from the certified state, by iteration count 1 / 5 / 25 / 100 / 400 |
|---|---|
| **B = 0 — contact and length alone** | 0.000029 / 0.000138 / 0.000539 / 0.001048 / **0.001051 mm** |
| committed default | 0.000029 / 0.000115 / 0.000300 / 0.000408 / **0.000408** |
| the gradient form, world-space rest | 0.000029 / 0.000121 / 0.000371 / 0.000710 / **0.000759** |
| **co-rotation** | 0.000029 / **0.019259** / 0.098611 / 0.326195 / **0.814050** |
| gradient + co-rotation | 0.000029 / 0.009229 / 0.060231 / 0.180288 / **0.244477** |

Three things follow, and the first two are corrections to the record.

1. **Every configuration starts at the same residual** — 0.000029 mm after one iteration,
   identical to six decimal places — because the bending force is **exactly zero** at the
   certified state in all of them. The only thing pushing at iteration 1 is contact.
2. **Contact's own contribution saturates and stops** at 0.0011 mm. The committed model and
   the gradient form saturate with it, at 0.0004 and 0.0008 mm, and **converge** — 56 and 120
   iterations, final step below 1e-5 mm.
3. **The co-rotational configurations take off at iteration 5** and never stop. 0.814 mm at
   400, and at 3200 iterations co-rotation reaches **1.931 mm** — **1,800× the entire
   lifetime contribution of the contact residual** (0.001051 mm) that set it off.

**Wave 4 named the right seed and the wrong mechanism.** The contact residual is not what
moves the fabric; it is what a load-independent instability is amplifying.

### 1c. The increment: a contact rest state measured off the fabric, not chosen

`rest_is_relaxed_shape` already says the yarn is taken as **set** in the shape relaxation left
it in — for bending. Contact does not say it. It aims every pair in every fabric at one
constant, `RESTING_CONTACT = 0.62` of a diameter, which `relaxation.PROVENANCE` has always
labelled **ESTIMATED** ("where two touching strands sit, as a fraction of diameter" — no
source, no measurement).

**Why the handover is not force free, stated as mechanics.** `relax` balances contact against
**its own** bending term, which pulls the yarn towards **straight** (`relaxation.PROVENANCE`:
"unstressed yarn is straight"). Its fixed point is a genuine balance of two forces. `drape`
then replaces that bending term with one whose rest state is the relaxed shape — which is
**zero at the configuration relaxation handed over**. That deletes exactly the force that was
holding contact back, and whatever contact still wants is unopposed. The two solvers do not
disagree about contact; they disagree about which configuration is stress free, and only one
of them was told.

`relaxation.contact_rest_separations()` measures, for every pair of segments already in
contact at the rest configuration, **the separation that pair was relaxed to**, and
`DrapeSetup.contact_rest_is_relaxed_shape` uses it as that pair's soft target. It is:

- **MEASURED, with no new constant.** One number per pair, read off the certified geometry,
  in the same way wave 4's tensile linkage takes its rest separation off the certified
  geometry rather than inventing a stiffness.
- **One-sided.** It can only ever **lower** a target, never raise one, and the correction is
  clipped at zero so a pair sitting further apart than its measured rest is never pulled
  together. Pinned by a check: halve **every** target and the fabric moves **exactly
  0.0 mm**.
- **Blind to the hard floor.** `COMPRESSED_CONTACT = 0.45` is untouched and still enforced at
  full gain. A pair squeezed past the published compression limit is still pushed back, which
  is pinned by a check that squeezes one and measures the correction. **No lock moves.**
- **Inert on the committed model.** 5×5 under gravity, 400 iterations: rms motion
  **0.41231 → 0.41238 mm**, worst margin identical, every lock identical.

**The physical reading, labelled honestly.** Transverse compression of spun yarn at a crossover
is real and is set by the tension that formed the stitch, not by a fraction of a diameter that
is the same for every fabric. That the two jammed folds sit at the floor is what a real
crochet stitch does where the yarn doubles back through itself. **MEASURED** is the separation;
**DERIVED** is the argument that the configuration relaxation produced is the one both terms
should call stress free; **UNKNOWN** remains what the true compressed separation of this yarn
is, and nothing here claims to have measured it — that is Stage 0's question and Stage 0 is
deferred.

### 1d. The answer

| 5×5, **gravity OFF**, 400 iterations | rms from the certified state | iterations | converged |
|---|---|---|---|
| committed default | 0.00041 mm | 56 | True |
| **default + contact rest** | **0.00000 mm** | **1** | **True** |
| gradient + co-rotation | 0.24448 | 400 | False |
| **gradient + co-rotation + contact rest** | **0.00000 mm** | **1** | **True** |

At 800 iterations the reconciled configuration reads **1.58e-17 mm rms** — machine precision
on a 474-vertex fabric. **The certified relaxed fabric is an exact fixed point of the solver's
contact model.** That is the increment, and it is a yes.

**What it does NOT fix, measured immediately and reported here rather than later.** Under
gravity, `gradient + co-rotation + contact rest` still **climbs**: the co-rotational bending
energy goes from −6.6854e-06 J to **+7.4222e-06 J** over 400 iterations. Removing the seed
removes the zero-load drift; under load, gravity is its own perturbation and the instability
returns. Section 3 is why, and it is not the contact model.

---

## 2. THE BENDING FORCE RECONCILED WITH THE DOCUMENTED ENERGY

Task as set: establish what adopting `energy_gradient_bending` **costs** and what it **fixes**,
against the committed control under identical conditions. It is not a calibration exercise;
the force is either the gradient of the documented energy or it is not, and wave 3 measured
that it is not — 69 % of the gradient's norm away, cosine 0.911, opposite sign at 3 of 18
sampled components, against an analytic gradient that matches central differences to 3e-8.

### 2a. What it costs: the fabric stops being a string and becomes a beam, and droops 3.4× less

5×5, 800 iterations, identical in everything but the force law. [MEASURED.]

| | control | **+ gradient** |
|---|---|---|
| maxOOP | 1.5858 mm | **0.4682 mm** |
| rms from flat | 0.7363 | 0.2227 |
| worst third-loop margin | −1.599 | −1.523 |
| within-row relief | 0.0083 | 0.0019 |
| local articulation | 3.388° | 1.707° |
| bending energy at the end | — | descends, −6.69e-06 → −7.74e-06 J |
| every other lock | — | identical |

**The cost is 3.4× less droop at the same B**, and it is arithmetic rather than a surprise. The
lumped Laplacian is a **string under tension B/l²**; `DᵀD` is a **beam**. Wave 3 established
both independently (§3a, and the beam-theory cross-check that failed in exactly this pattern),
and wave 3's derived-B bracket — 4× to 42× the committed value — is the *same* statement seen
from the calibration side. **`CALIBRATED_BENDING_N_M2` has NOT been changed**, for the reason
wave 3 gave: the honest answer is a 10× bracket rather than a value, and moving it moves every
committed Visual result. Adopting the gradient form therefore **makes the existing B visibly
too soft** rather than fixing it, and that is the cost, stated plainly.

### 2b. What it fixes, and what it does not

**It fixes:** the force becomes a descent direction for the energy the module documents. On
the committed world-space rest state both forms descend, so this is not visible there; it
becomes decisive the moment the rest state moves with the configuration.

**It does not fix the co-rotational climb under load.** This is the correction to the
expectation wave 4 set, and the two columns have to be read separately because the
perturbation is different in each. 400 iterations, 5×5. [MEASURED.]

| configuration | rms at **zero load** | energy under load, start → end |
|---|---|---|
| co-rotation, lumped Laplacian | 0.814 mm | **climbs** |
| co-rotation, **gradient** | 0.244 mm | −6.69e-06 → **+2.22e-06** climbs |
| co-rotation, gradient, **+ contact rest** | **0.000 mm** | −6.69e-06 → **+7.42e-06** climbs |
| co-rotation, gradient, **+ contact rest + yarn only** | **0.000 mm** | −6.69e-06 → **−7.34e-06** ✓ descends |
| co-rotation, gradient, **+ yarn only**, no contact rest | 0.0014 mm | — |
| co-rotation, **lumped Laplacian**, + contact rest + yarn only | **0.000 mm** | −6.69e-06 → **−8.97e-06** ✓ descends |

**At zero load the contact residual is the only perturbation, so removing it removes the drift
whatever the force law** — that is row 3, and it is the equilibrium result of §1. **Under load
gravity is its own perturbation, and only the yarn mask makes the scheme descend.** The
gradient form reduces the zero-load drift by 3.3× and does not stop the loaded climb; the mask
does, and the last row settles the attribution — the **un**-reconciled Laplacian force with the
artefact vertices excluded also descends. So the gradient reconciliation is **correct and worth
adopting on its own terms** — it is the gradient of the documented energy and the committed
force is not — but **it is not what was making the co-rotational scheme climb.**

### 2c. On the cylinders

Static wraps first, which are force-law independent and are re-run only to confirm nothing
moved: **every lock identical to wave 3 and wave 4**, both sizes, both curvatures (table in
§5).

The force-law test on curved geometry is a **release**: the certified flat fabric is the global
minimum of the bending energy, so a fabric wrapped on a cylinder and released with gravity off
must lower the energy. 5×5, 400 iterations, `clamp_fraction = 0`, rest state the flat certified
curvature. [MEASURED.]

| configuration | κ = 2 (R 500 mm) E start → end | κ = 8 (R 125 mm) E start → end | gate |
|---|---|---|---|
| control | 1.9913e-06 → 2.9845e-07 J | 3.3644e-05 → 1.9439e-06 J | PASS |
| + gradient | 1.9913e-06 → 4.3034e-07 | 3.3644e-05 → 2.9040e-06 | PASS |
| + yarn only | **7.3593e-07** → 2.4142e-07 | **1.2371e-05** → 7.0830e-07 | PASS |
| + gradient + yarn | 7.3593e-07 → 2.6621e-07 | 1.2371e-05 → 8.8906e-07 | PASS |
| **reconciled co-rotational** | **1.0090e-08** → 5.0235e-09 | **1.6420e-07** → 8.7574e-08 | PASS |

Every force law descends on curved geometry and every one keeps the product valid. Two things
are worth reading off it. **The path's artefacts carry 63–73 % of the world-space energy of a
pure bend** (1.99e-06 → 7.36e-07 J at κ = 2), consistent with wave 3's independent finding that
they carry 60 % and are worth 10.2× in the derived B. And **the co-rotational energy of a wrap
is 197× smaller than the world-space energy** at κ = 2, which is frame invariance demonstrated
on real curved cloth rather than on a rigid rotation: most of what a wrap does to a stitch is
turn it.

---

## 3. WHERE THE INSTABILITY ACTUALLY LIVES

### 3a. The theorem, which needs no experiment

At the certified configuration with `rest_is_relaxed_shape`, `lap = lap_rest`; and the
co-rotational rotation of a configuration onto itself is the identity. So

```
E_bend(certified) = (B / 2l³) · Σ |lap − R·lap_rest|²  =  0
```

exactly — **measured as exactly 0.0 J in the world-space form and 4.18e-34 J in the
co-rotational form**, which is the floating-point zero of a sum over 474 squared residuals.
The energy is a sum of squares, so **zero is its global minimum**. With gravity off there is
nothing else in the objective. **Any motion at zero load is the solve climbing out of the
global minimum of its own energy**, and that statement does not depend on any threshold,
instrument or interpretation.

Measured, gravity off, co-rotational energy by iteration count: **5.81e-06 J at 100, 8.15e-06
at 400, 1.17e-05 at 1600, 4.92e-06 at 3200** — while the displacement keeps growing, 0.33 →
0.81 → 0.97 → 1.93 mm. **Non-monotone energy with monotonically growing displacement** is an
oscillation, and it is the same oscillation whose surface appearance wave 3 recorded as
non-monotone validity (PASS at 100, FAIL 200–800, PASS at 1600, FAIL at 3200).

### 3b. The location: 99.99996 % of it is on path that is not yarn

One loaded iteration of `gradient + co-rotation + contact rest`, from the exact equilibrium,
5×5. [MEASURED.]

| | value |
|---|---|
| genuine yarn vertices (`genuine_yarn_vertices`) | **312** of 474 |
| excluded: artificial hops ≥ 5 mm | 87 segments, up to 6.73 mm |
| excluded: sub-micron joins ≤ 0.01 mm | 20 segments, the shortest **28 nanometres** |
| rms motion after one iteration | 0.00032 mm |
| co-rotational bending energy injected | **9.7564e-06 J** |
| — of which on the 312 genuine yarn vertices | **3.9942e-13 J** |
| — of which on the 162 artefact vertices | **9.7564e-06 J** |

For scale: the committed 800-iteration solve lowers its total energy by **2.92e-06 J** over
its whole run (−6.685e-06 → −9.603e-06 J). **One iteration of the co-rotational scheme puts in
three and a third times that**, and essentially all of it is charged for bends in geometry
that is not yarn. Through the whole loaded run the share
never falls below **96.5 %**.

**Why it is the co-rotational frame specifically.** `corotational_rotations` fits each vertex's
rotation by Kabsch on its two **unit edge vectors**. A 28-nanometre segment's direction is
determined by a difference of two nearly identical positions: a nanometre of motion turns it
through about two degrees, and the solver's own step moves vertices by microns. The fitted
rotation at such a vertex is therefore **not a continuous function of the configuration**, and
it is refitted every iteration against a `lap_rest` that is *larger* there than on real yarn
(mean 4.907e-03 against 3.582e-03 m — a second difference taken across a 6.73 mm hop is not a
small number). With a **fixed** world-space rest state none of this matters, because
`lap → lap_rest` is still a stable fixed point whatever the vertex is; with a rest state
carried into that frame it is the dominant term.

### 3c. Bending only where there is yarn

`DrapeSetup.bend_on_yarn_only` zeroes the bending residual at any vertex either of whose
segments is not yarn, so neither force law charges for a bend that is not in the fabric and no
co-rotational frame is ever fitted to a direction that does not exist. The classification is
**the one wave 3 already built and pinned**; there is no new constant, and the mask is computed
once from the rest configuration because no vertex is ever added, removed or reconnected and
segment lengths are held.

5×5, 400 iterations, `B = 3.0e-8`, everything else identical. [MEASURED.]

| configuration | rms, g = 9.81 | **rms, g = 0** | E start → E final, g = 9.81 |
|---|---|---|---|
| committed default | 0.4123 mm | 0.0004 mm | −6.6854e-06 → −8.4771e-06 ✓ descends |
| gradient + co-rotation | 0.2757 | 0.2445 | −6.6854e-06 → **+2.2249e-06** ✗ climbs |
| gradient + co-rotation + contact rest | 0.2651 | **0.0000** | −6.6854e-06 → **+7.4222e-06** ✗ climbs |
| **+ yarn only** (the reconciled configuration) | **0.1250** | **0.0000** | −6.6854e-06 → **−7.3400e-06** ✓ **descends** |
| co-rotation + contact rest + yarn only (Laplacian force) | 0.5001 | 0.0000 | −6.6854e-06 → −8.9668e-06 ✓ descends |

**The reconciled co-rotational configuration is the first in this programme that descends its
own energy under load and does nothing at all without it.** 100 % of its motion is load
response, against 109 % load-independent for co-rotation alone in wave 4.

**What the mask costs, stated rather than skipped.** Excluding a vertex removes its bending
term, so the path has **no bending resistance across a hop or a join**. For the 87 hops that
is right by construction — there is no yarn there. For the 20 joins the yarn IS continuous,
and what is lost is the bending coupling between the last point of one stitch and the first
point of the next; the justification is not that the coupling does not exist but that a second
difference across **28 nanometres** cannot measure it. The consequence is measurable and is in
the tables: with the world-space rest state, the mask alone makes the fabric **1.47× floppier**
(maxOOP 2.332 mm against the control's 1.586 mm on the 5×5) and erodes the worst third-loop
margin from −1.599 to −1.343. **Every lock still passes at both sizes**, min gap is unchanged
at 1.5000 mm and `crossing_impossible` is True — but it is a real softening and it is a second
reason, alongside wave 3's 10.2×, that `CALIBRATED_BENDING_N_M2` is now visibly too small for
the force law. **The right repair is a re-derived B, not a narrower mask.**

---

## 4. INTERMEDIATE VALIDITY — the decision, and why it is this one

Task as set: a solve must not pass through a broken product and be certified because its final
frame happens to pass; `watch_linkage` is monotone and cheap; decide what a guard does when it
fires, and say why.

### 4a. `watch_linkage` stays ON and stays MEASUREMENT ONLY. It does not abort.

The reason is that there is **no non-invented threshold on a link opening**. The committed
default — a valid product by every lock — opens its worst certified link by **0.1457 mm** over
a run. Any hard limit would either reject that product or be a number chosen so that it does
not, and a number chosen to avoid failing the thing you already believe is exactly the move
this codebase keeps catching. It stays as wave 4 built it: 0.081 ms an iteration, a maximum
over the whole run rather than a value at its end, and monotone where the gate is not.

### 4b. A guard that DOES fire, whose criterion is a lock rather than a number

`DrapeSetup.guard_morphology`. Its criterion is the **committed morphology lock itself**: a
stitch is broken when its third loop is no longer below its V, `margin ≥ 0` — the same line
`stitch_shape` draws and `crochet_topology.validate` counts. **The guard evaluates the lock
more often. It does not move it.** Nothing is invented, because nothing new is decided.

**What it does when it fires:** reverts the iteration and retries at half the force step — the
machinery the clearance guarantee already runs — and if no step keeps the product valid, the
solve **stalls and says so** (`DrapeReport.stalled`). It does not raise, because a transient is
not a reason to throw a run away; it does not carry on and report at the end, because that is
the behaviour being fixed.

**And it stands aside on an already-broken input.** If the fabric handed in is invalid, every
step would be rejected and the stall would be a property of the input rather than of the solve.
The guard records `morphology_guard_stood_aside` instead of deadlocking.

**Measured, 5×5, 400 iterations.** [MEASURED.]

| | unguarded | **guarded** |
|---|---|---|
| committed default: worst margin at the end | −1.561 | −1.561, **0 rejections**, identical to the last bit |
| committed default: cost | 8.6 s | 10.0 s (**+16 %**) |
| co-rotation alone (the known eversion): margin at the end | **+1.5169** (3 stitches everted) | **−0.0001**, 21 rejections, stalled |
| co-rotation alone: maxOOP | 3.3116 mm | 2.2730 mm |

**The everting run now stops at the last valid configuration instead of finishing broken.**

**Cost, and why it is affordable where continuous topology is not.** Wave 4 measured a full
topology pass at 97.673 ms an iteration — 39 s on top of a 13 s solve, 4× the solve — and would
in any case be guarding with `_encirclement`, which wave 4 showed **false-negatives on exactly
the strongly deformed geometry it would be watching**. The morphology margin is **2.168 ms**,
45× cheaper, and it is the instrument that actually catches what fails in these runs. That
finding is unchanged, the direction set was not touched, and no lock was made stricter.

### 4c. The residual, stated rather than implied

A monotone descent removes the *oscillation* that produced wave 3's PASS → FAIL → PASS. It does
not forbid a descent path that passes through a broken product on its way to a lower-energy
valid one; the morphology guard is what covers that, and it covers the morphology lock and not
the topology lock. **Continuous linking-number validation remains unbought and unbuilt**, for
wave 4's reasons, and `_encirclement`'s false negative on strongly deformed cloth remains
**recorded and unfixed** — it is an owner-visible change to a committed instrument that all 28
adversarial fixtures are calibrated against, and this increment did not touch it.

### 4d. Monotone descent, which is a check and not a crutch

`DrapeSetup.monotone_descent` rejects any iteration whose **finished** configuration — after
the linkage, after contact, after the length projection — raises the total energy, and retries
at half the force step. It has **no constant in it**: the comparison bound is
`64 · eps · max(|E|)`, a floating-point rounding bound for a sum over ~2,000 squared residuals,
and an iteration in which the **hard contact floor** had to be enforced is exempt, because
un-squeezing yarn past the published compression limit is not optional and is not a descent
step.

It is reported here because of what it measures rather than what it fixes:

| configuration, 400 iterations | rejections | iterations accepted | result |
|---|---|---|---|
| committed default, g = 9.81 | **0** | 400 | identical to the control, bit for bit |
| **reconciled co-rotational**, g = 9.81 | **0** | 400 | identical to the same run without it |
| gradient + co-rotation, artefacts still in, g = 9.81 | **20** | **0** | **deadlock** |
| co-rotation + contact rest, artefacts still in, g = 9.81 | 18 | 19 | deadlock |

**The deadlock is the proof.** After twenty halvings — a force step 1e-6 of its original size —
the un-reconciled co-rotational scheme still cannot find a step that lowers its own energy.
That is what "not a descent direction" means when it is measured instead of argued, and it is
an independent confirmation of §3b: a step-independent energy injection can only come from
something that is not proportional to the step, which is the rotation refit at a vertex where
the edge direction is noise.

On the reconciled configuration it never fires. **It verifies a descent rather than
manufacturing one.**

---

## 5. EVERY PRODUCT TRUTH LOCK, RE-RUN

All runs 800 iterations, `B = 3.0e-8 N m²`, `clamp_fraction = 0.5`, identical in everything
but the force law. `co-rot full` = gradient + co-rotation + measured contact rest + bending on
yarn only. `M` = monotone descent.

### 5a. 5×5 (474 vertices, 25 hdc), under gravity

| lock | control | +grad | +yarn | +grad+yarn | **co-rot full** | +link | +link+M |
|---|---|---|---|---|---|---|---|
| **topology gate** | PASS | PASS | PASS | PASS | **PASS** | PASS | PASS |
| linkage | 20/20 | 20/20 | 20/20 | 20/20 | **20/20** | 20/20 | 20/20 |
| stitch morphology | 25/25 | 25/25 | 25/25 | 25/25 | **25/25** | 25/25 | 25/25 |
| unmeasurable / unframeable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| identity, row, position, loop targets | held | held | held | held | held | held | held |
| **min gap** | 1.5000 | 1.5000 | 1.5000 | 1.5000 | **1.5000** | 1.5000 | 1.5000 |
| pull-through impossible | True | True | True | True | True | True | True |
| join within a row | 0.003 | 0.003 | 0.003 | 0.003 | 0.003 | 0.003 | 0.003 |
| join at a turn | 5.998 | 5.998 | 5.998 | 5.998 | 5.998 | 5.998 | 5.998 |
| yarn length change | +1.4e-5 % | +1.3e-6 % | +1.4e-5 % | +1.2e-6 % | **+1.2e-6 %** | +1.1e-6 % | +1.1e-6 % |
| max measurable strain | 4.6e-6 | 2.0e-6 | 1.0e-5 | 1.5e-6 | 5.9e-7 | 5.9e-7 | 5.9e-7 |
| intrinsic width | −0.044 % | −0.017 % | −0.160 % | −0.025 % | **−0.019 %** | −0.018 % | −0.018 % |
| intrinsic height | +0.136 % | −0.007 % | +0.026 % | −0.033 % | **−0.019 %** | −0.021 % | −0.021 % |
| **worst third-loop margin** (flat −1.540) | **−1.599** | −1.523 | −1.343 | −1.486 | **−1.457** | −1.473 | −1.473 |
| maxOOP | 1.586 mm | 0.468 | 2.332 | 0.548 | 0.566 | 0.566 | 0.566 |
| within-row relief | 0.0083 | 0.0019 | 0.0069 | 0.0007 | 0.0006 | 0.0007 | 0.0007 |
| local articulation | 3.388° | 1.707° | 5.117° | 1.513° | 1.412° | 1.289° | 1.289° |
| worst link opening over the run | 0.146 | 0.150 | 0.479 | 0.177 | 0.230 | **0.0009** | 0.0009 |
| **energy, start → end** | −6.69→−9.60e-6 | −6.69→−7.74 | −6.69→−10.74 | −6.69→−7.88 | **−6.69→−7.98** | −6.69→−7.97 | −6.69→−7.97 |
| monotone rejections | — | — | — | — | — | — | **0** |

### 5b. 10×8 (1494 vertices, 80 hdc), under gravity

| lock | control | +grad | +yarn | +grad+yarn | **co-rot full** | +link | +link+M |
|---|---|---|---|---|---|---|---|
| **topology gate** | PASS | PASS | PASS | PASS | **PASS** | PASS | PASS |
| linkage | 72/72 | 72/72 | 72/72 | 72/72 | **72/72** | 72/72 | 72/72 |
| stitch morphology | 80/80 | 80/80 | 80/80 | 80/80 | **80/80** | 80/80 | 80/80 |
| unmeasurable / unframeable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| min gap | 1.5000 | 1.5000 | 1.5000 | 1.5000 | 1.5000 | 1.5000 | 1.5000 |
| yarn length change | +1.9e-5 % | +9.5e-7 % | +9.1e-5 % | +5.3e-6 % | +4.5e-6 % | +4.2e-6 % | +4.2e-6 % |
| intrinsic width | −0.037 % | −0.013 % | −0.094 % | −0.012 % | **−0.010 %** | −0.009 % | −0.009 % |
| intrinsic height | +0.034 % | −0.007 % | −0.052 % | −0.021 % | **−0.016 %** | −0.015 % | −0.015 % |
| **worst third-loop margin** | **−1.453** | −1.518 | −1.368 | −1.479 | **−1.492** | −1.503 | −1.503 |
| maxOOP | 1.689 mm | 0.475 | 2.326 | 0.548 | 0.566 | 0.568 | 0.568 |
| within-row relief | 0.0031 | 0.0019 | 0.0032 | 0.0017 | 0.0009 | 0.0010 | 0.0010 |
| local articulation | 2.062° | 0.922° | 2.387° | 0.797° | 0.637° | 0.655° | 0.655° |
| worst link opening | 0.217 | 0.150 | 0.569 | 0.189 | 0.246 | **0.021** | 0.021 |
| energy, start → end (×1e-5 J) | −2.20→−3.40 | −2.20→−2.55 | −2.20→−3.26 | −2.20→−2.59 | **−2.20→−2.64** | −2.20→−2.63 | −2.20→−2.63 |

**Every lock passes in every configuration at both sizes.** The larger swatch behaves like the
small one throughout. `crossing_impossible` is True and `cap_exceeded` is 0 everywhere, so the
continuous non-crossing guarantee held in all 28 solves.

### 5c. THE ZERO-GRAVITY CONTROL, which is the column that decides the increment

800 iterations, everything identical, gravity switched off.

| | 5×5 rms from the certified state | 10×8 | gate | worst margin |
|---|---|---|---|---|
| control | 0.0004 mm | 0.0005 mm | PASS | −1.539 |
| +grad | 0.0008 | 0.0009 | PASS | −1.538 |
| +yarn | 0.0005 | 0.0006 | PASS | −1.539 |
| +grad+yarn | 0.0007 | 0.0012 | PASS | −1.538 |
| **co-rot full** | **1.58e-17 mm** | **2.43e-17 mm** | **PASS** | **−1.540** (the flat baseline, exactly) |
| **co-rot full + linkage** | **1.58e-17** | **2.43e-17** | PASS | −1.540 |

For comparison, wave 4's zero-gravity readings for the same family were **0.8140 mm** (109 % of
its loaded motion) and **0.2495 mm** (98 %). This is now **zero to machine precision, and
100 % of the loaded motion is load response.**

### 5d. The cylinders, static, re-run unchanged

| lock | 5×5 R=500 (κ=2) | 5×5 R=125 (κ=8) | 10×8 R=500 | 10×8 R=125 |
|---|---|---|---|---|
| topology gate | PASS | PASS | PASS | PASS |
| linkage | 20/20 | 20/20 | 72/72 | 72/72 |
| stitch morphology | 25/25 | 25/25 | 80/80 | 80/80 |
| unmeasurable / unframeable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| min gap | 1.5061 | 1.5239 | 1.5061 | 1.5239 |
| intrinsic width | −0.0000 % | −0.0000 % | −0.0000 % | −0.0000 % |
| intrinsic height | +0.092 % | +0.289 % | +0.092 % | +0.288 % |
| worst third-loop margin | −1.466 | −1.120 | −1.466 | −1.120 |
| local articulation | 0.720° | 2.057° | 0.526° | 1.329° |
| worst certified link opening | 0.0003 mm | 0.0002 mm | 0.0003 mm | 0.0002 mm |

**Identical to wave 3 §ITEM 4 and wave 4 §3c, figure for figure.** Nothing in this increment
moved a committed number.

### 5e. Suites

| suite | result |
|---|---|
| `test_drape` | **124 → 144, 0 failing** (20 checks added) |
| `test_render` | 11 passing, 0 failing (5 added for the committed scene) |
| `test_topology_adversarial` | **28 / 28 adversarial fixtures still REJECT** |
| `test_crochet_topology` | 43, 0 failing |
| `test_linkage` | 18, 0 failing |
| `test_hand_tension` | 24, 0 failing |
| `test_compiler` / `test_reverse` / `test_twin` | 9 / 12 / 6, 0 failing |
| `test_visual` | 0 failing |

**Nothing weakened, no threshold moved, no existing check deleted or relaxed.** One of my own
new checks failed first time and the instrument was right again: I asserted the artefact share
of the injected energy as `yarn < 1e-9 × total` when the measured ratio is 4.09e-8. The
threshold was invented; the measurement was correct. Replaced with the statement the data
actually support — the artefacts carry more than 99.99 % — which is a claim rather than a
guess.

---

## 6. MILESTONE D

**FAIL. Unchanged, not weakened, no threshold lowered, no lock relaxed.**

### 6a. The renders, and the honest problem with the comparison that was asked for

The comparison specified — against the existing Layer 5 / drape attribution set under
**identical camera, lighting, material and staging** — **cannot be made**, and the reason is a
reproducibility hole rather than a result:

- **Mitsuba is not a dependency of this repository.** `requirements.txt` excludes it on
  purpose ("~200MB and is only needed to run the feasibility spike by hand, never by the
  deployed service"). It was installed locally for this increment, at CA$0, and **was not
  added to `requirements.txt`.**
- **The scene that produced the existing set was never committed.** `yarn_drape_control.png`,
  `yarn_drape_draped.png`, `yarn_drape_oblique.png` and the Layer 1–5 ladder were rendered by
  hand; the commit that added them asserts they are "identical in yarn, material, fibre
  layers, lighting, camera and contact staging", and **that claim is not checkable from
  anything in the tree.** It is the same defect wave 2 found in `CALIBRATED_BENDING_N_M2`: a
  result whose procedure cannot be re-run.
- **And the existing set is not of this geometry.** It is rendered from `visual/yarn.py`'s
  `yarn_path` and its own `relax` — a **second, separate geometry generator** with its own
  stitch construction (`_hdc_stitch`, `YARN_FILL`, `POST_DEPTH`) and its own out-of-plane
  relaxation. `drape` acts on `crochet_topology.Fabric`, built by `_hdc_cell` from the Storck
  proportions. So a like-for-like comparison would need the two pipelines bridged first, which
  is real work and is not a rendering setting. **This is the concrete blocker, and it is worth
  more than the render was:** the mechanics increments of waves 2–5 have all been measured on
  a geometry that the repository's best pictures are not of.

So rather than approximate someone else's staging from a picture — which would produce a
comparison that looks like one and is not — the staging is now **committed as data**
(`visual/pbr_scene.py`, `STAGING`), the fabric-to-strand conversion is committed with it, and
the comparison made is the one this increment can actually support: **control against the
reconciled configuration, framed by the same reference fabric, under one scene, differing only
in the force law.** `wave5_flat_*.png`, `wave5_control_*.png`, `wave5_reconciled_*.png`,
straight-on and oblique.

**What the scene deliberately does not have**, said in data rather than in a comment
(`STAGING["not_reproduced"]`): fibre halo, ply wobble, surface fuzz, hand tension drift, and
the Layer 1–5 material stack. It is a **geometry comparison instrument**, and it renders at a
standard far below the committed yarn ladder. A picture from it is not evidence about
appearance and is not offered as any.

One substantive decision is in it: **the artificial hops are not drawn.** The stored path
contains 87 segments that are not yarn, and drawing them would put strands in the picture that
are not in the fabric. The path is cut at them, which is also what Mitsuba's linear-curve
format wants. 54 strands, 1,710 vertices on the certified 5×5.

**And one defect caught by committing it.** The first staging put a 55 mm fill sphere 63 mm
from the oblique camera and filled a third of that frame with the lamp — in one picture of a
comparison and not the other. The fill is now an environment emitter with no geometry, the key
is a single sphere, and **the scene refuses to render if the key is in front of the camera**
rather than leaving it to be noticed. That is the kind of thing an uncommitted scene hides.

`scene_dict()` is the **only** description of the scene; `render` builds from it and
substitutes three symbolic transforms. A second description inside the renderer would be two
places for a material or a light to drift apart, which is how a comparison stops being one.

### 6b. Did D move? No.

**What the pictures show, before the numbers.** Between `wave5_control_*` and
`wave5_reconciled_*`, framed by the same fabric under the same scene, the only visible
difference is at the **free bottom row**: the control's posts swing further out of plane and
less evenly, the reconciled fabric's hang shorter and more uniformly. That is the 1.586 mm
against 0.566 mm of maxOOP, and it is a **stiffer beam**, not cloth. **Every row still reads
as a rigid bar bowing as a unit** — the corrugated-relief character the standard was failed on
is unchanged, in both configurations, in both views. Against the committed Layer 5 set these
are a far cruder picture in every respect that is about yarn rather than geometry, which is
what §6a says they are for.

**It did not, and nothing here was expected to move it.** The standing symptom is that the
fabric reads as a corrugated relief rather than cloth, and on the committed conformability
metric the reconciled configuration reads **0.0006** against the control's **0.0083** — it is
**lower**, not higher. Local articulation reads **1.41°** against **3.39°**, also lower, and
both are near the certified flat fabric's own floor of 0.519°.

That is not a regression being buried; it is the predictable consequence of two of the three
corrections. The gradient form turns a string into a beam and the fabric droops 3.4× less at
the same B, and the yarn mask removes a spurious stiffness that was also a spurious source of
stitch-to-stitch variation. **Wave 3's 18–20× rise in `within_row_fraction` is now known to
have been the instability** — wave 4's gravity-off control established that, and this wave
established what the instability was. Removing it removes the reading with it.

**What has changed is that the question can now be asked.** Every previous frame-invariant
experiment measured a fabric settling out of a state it was never in equilibrium in, or
climbing out of the global minimum of its own energy. Neither is true any more: the certified
fabric is an exact fixed point, the solve descends, the zero-load control is zero to machine
precision, and every lock passes at both sizes. **An experiment run on this configuration
measures the mechanics and not the solver.** That is the increment, and it is not Milestone D.

### 6c. The next mechanism, specific and falsifiable

Three things are now measurable that were not, and none of them needs Stage 0 or Stage 1.

1. **B is too small for the force law now that it is a beam.** Wave 3 derived a bracket of
   4×–42× the committed value, and the yarn mask decides which end: the solver now excludes
   the hops, which is wave 3's "yarn only" column, which derives **1.27e-6 N m²** — 42× the
   committed constant. At the committed B the reconciled fabric droops 0.566 mm where the
   control droops 1.586 mm. **`CALIBRATED_BENDING_N_M2` was not changed**, because moving it
   moves every committed Visual result and is owner visible; but the configuration that makes
   the derivation valid now exists, and re-deriving it is a bounded, self-contained increment.
2. **The cantilever can be attempted again.** Wave 3 proved the ASTM inversion cannot converge
   *because* the implemented force is a string whose free region outweighs its tension by
   2.74×. With `energy_gradient_bending` the force is a beam, so that closed-form obstruction
   no longer applies and `cantilever_equilibrium_bound` should be re-derived against it.
3. **Conformability can be tested against a load that is not gravity.** With the equilibrium
   exact and the solve monotone, a prescribed displacement — a fabric pulled over a form —
   measures how the cloth articulates without a load-independent term in the answer. That is
   what the drape attribution set is actually for.

And one that is not a mechanism at all and is probably worth more than any of them:
**bridge the two geometry generators, or retire one.** `visual/yarn.py` builds the pictures
and `visual/crochet_topology.py` builds the product; three waves of mechanics have now been
measured on a fabric that the repository's best renders are not of, and nothing will close
Milestone D while the thing being improved and the thing being looked at are different
objects.

---

## 6d. What was NOT done, and why

- **`CALIBRATED_BENDING_N_M2` was not changed**, although two independent findings now say it
  is too small for the reconciled force law (wave 3's 4×–42× bracket, and the 1.47× softening
  the yarn mask adds). Moving it moves every committed Visual result and is owner visible.
- **None of the four new options is on by default.** Every committed Visual figure was
  produced without them, and a check pins that the committed default does not move by a
  nanometre.
- **`_encirclement`'s false negative on strongly deformed cloth is still unfixed**, exactly as
  wave 4 left it. Widening the closure set changes a committed instrument that all 28
  adversarial fixtures are calibrated against. The direction set was not touched.
- **Continuous topology validation was not bought.** 97.673 ms an iteration, 4× the solve, and
  it would guard with the instrument above. The morphology guard is the affordable half and it
  is what actually fails in these runs.
- **The existing Layer 5 / drape attribution set was not reproduced.** The scene was never
  committed, so identical staging is not reconstructible; §6a.
- **Stage 1 yarn redistribution was not begun and Stage 0 stays deferred** (owner ruling D7).
  Nothing here needs either: every statement is about what the model contains.
- **`requirements.txt` was not changed.** Mitsuba was installed locally to render, at CA$0,
  and is deliberately still not a dependency.

---

## 7. What changed in the tree

`visual/relaxation.py` — **additive; the default contact behaviour is unchanged**:

- `contact_rest_separations()` — the per-pair separation relaxation left each contacting pair
  at, measured off a configuration.
- `apply_contacts(..., pair_rest=None, stats=None)` — the optional per-pair soft target, which
  can only lower a target and never raise one; the hard floor is untouched. The growth factor
  is now clipped at **zero** as well as at `_MAX_CONTACT_GAIN`, which is a no-op for the
  existing single-target path (`want > n` always held there) and is what makes the new path
  one-sided. `stats` reports how many pairs the hard floor was enforced on.

`visual/drape.py` — **additive; no existing default altered and no committed figure moved**:

- `DrapeSetup.contact_rest_is_relaxed_shape` (default **False**) — the contact rest state.
- `DrapeSetup.bend_on_yarn_only` (default **False**) — the bending residual is zero where the
  path is not yarn, using wave 3's `genuine_yarn_vertices` classification.
- `DrapeSetup.monotone_descent` (default **False**) — reverts and halves any iteration that
  raises the total energy; no new constant, floating-point noise bound only, hard-floor
  iterations exempt.
- `DrapeSetup.guard_morphology` (default **False**) — the committed morphology lock, evaluated
  every iteration; reverts and halves, stalls if no valid step exists, stands aside on an
  already-broken input.
- `worst_third_loop_margin()` — the third-loop margin instrument, moved here from the suite so
  there is one definition; the suite now imports it and a check pins that it reproduces the
  figures it has asserted since the first out-of-plane run.
- `DrapeReport.energy_start_J`, `energy_final_J`, `energy_max_J`, `energy_rise_J`,
  `energy_rejections`, `floor_enforced_iterations`, `margin_start_mm`, `margin_max_mm`,
  `margin_worst_iteration`, `morphology_rejections`, `morphology_guard_stood_aside`,
  `stalled`, `contact_pair_rest_used`, `bending_vertices` — the instruments. The energy is
  evaluated once at each end of a run by default, so the control pays nothing for it.

`visual/pbr_scene.py` — **new**. The Mitsuba scene as committed data, the certified fabric to
strands (cutting at the path's artefacts), the curve writer, and a lazy `render` that says
plainly that Mitsuba is not a dependency. Nothing above `render` needs Mitsuba and everything
above it is tested without it.

`tests/test_drape.py` — **20 checks added, 124 → 144, 0 failing**, including **four recorded
negatives**: the contact residual is non-zero without the measured rest state; the
co-rotational energy injected in one loaded iteration is 99.99996 % on path that is not yarn;
the monotone criterion **deadlocks** the un-reconciled co-rotational scheme; and the morphology
guard stops a run that would otherwise finish with three stitches everted.

`tests/test_render.py` — **5 checks added**, all of the committed scene and none of them a
claim about appearance.

CA$0.00. No model calls, no image-generation API calls, nothing published, nothing deployed.
Mitsuba was installed locally and **deliberately not added to `requirements.txt`**. Committed
on the worktree branch, **not pushed**.

