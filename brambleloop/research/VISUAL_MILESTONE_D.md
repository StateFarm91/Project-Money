# Visual wave 6 — Milestone D measured on the certified geometry

**Department:** Visual, isolated branch `claude/visual-investigation`. **Date:** 2026-09-26 (UTC).
**Mode:** Shadow. **Spend this wave:** CA$0.00 — no model calls, no image-provider calls,
nothing deployed, nothing published. (Session total, frozen by the owner: US$0.46 list, E1/E2.)
**Integrated checkpoint `fcb982d`: untouched.**

Continues `VISUAL_WAVE5.md`. Labels: **SOURCED / DERIVED / BOUNDED / MEASURED / UNKNOWN**.

---

## THE RESULT, IN ONE LINE

**Milestone D is PARTIAL, measured — not FAIL and not PASS.** Every item of the claim that can
be measured without a judge now passes on the certified hdc and sc swatches: identity, the flat
locks, the fixed point, energy descent, contact with a form, **no structural drift through a
real drape** (every stitch linked, shaped as ordered, above the compression floor), double
curvature, and a render derived from that exact configuration with plies and fibres. The items
that are a judgement about a photograph — folds natural, lighting, shadows, imperfection, and
the three rejects — are **UNKNOWN**, because no judge ran and an UNKNOWN never counts toward a
PASS. Hand-tension irregularity is UNKNOWN because it was not applied to the assessed build
(it builds and certifies: measured, below).

---

## 1. The failure inherited, reproduced

Wave 5 §6b: *"every row still reads as a rigid bar bowing as a unit"* — the reconciled
configuration moved 0.566 mm maxOOP at 800 iterations, conformability `within_row_fraction`
0.0006, and D stayed a hard-coded FAIL in `visual/milestones.py`. Reproduced on the same
fixture: 0.5661 mm at 800 iterations, 0.0007 within-row.

## 2. Defects found, with root causes

**D1 — The reported motion was free drift, not drape (MEASURED).** The force step is scaled
so the *largest* force — yarn bending, 200–30,000× gravity — moves a vertex 0.05 of a
segment. Gravity therefore moves a vertex ~0.7 µm per iteration. maxOOP: **0.566 mm at 800,
1.130 at 1600, 4.44 at 6400** — linear in the iteration count. A fabric drifting uniformly
under a force proportional to mass moves every row as a unit *by construction*. The rigid-bar
symptom was the signature of a solve that had not started to drape.

**D2 — The frictionless force law takes stitches apart once the drape proceeds (MEASURED).**
Plain descent, committed defaults + reconciled configuration, **25,600 iterations**: 17.3 mm
drape, **14 of 25** third loops above the V. With momentum, with the morphology guard, after an
800-iteration settle-back: same. At the derived bending rigidity (1.27e-6 N m², 42×): 3 of 25
at 1600, **16 of 25** at 6400. The sc swatch loses **13 of 20 linkages** (netting) at 4 mm. A
loop fabric whose strands slide freely over each other reorganises under a load a thousand
times smaller than what holds a real stitch — the model had no yarn-on-yarn friction.

**D3 — The morphology check's frame measured the neighbours, not the stitch (MEASURED).**
With every stitch held rigid to 0.1 mm through a 26 mm drape, four intact stitches (third loop
−1.55 to −1.62 mm below the V in their own frame, exactly as certified) read **+0.19 to
+0.56 mm** in the neighbour frame, whose UP sat 17–19.5° off the stitch's own. Synthetic
fold of intact rows: neighbour frame clears 25° and reports five false eversions from 35°.

**D4 — A projection that ends on the length constraint leaves the pinned pair under the
floor (MEASURED).** The certified hdc pins one pair at exactly 1.5000 mm; every drape returned
it at 1.5 − 5e-5 … 1.5 − 2e-13 mm and `validate` refused it, correctly by its rule. The floor
pass converges from below and never crosses.

**D5 — A frictionless sphere gives the fabric no equilibrium (MEASURED).** rms motion still
growing 6.5 % per 640 iterations at 6,400, the fabric sliding off the form. Three friction
models were tried and measured on a 200 mm "table" tilted 15°, sliding read between 300 and
600 iterations (1.15 mm with no friction): pinning vertices found *inside* the form — 0.60 mm
(a resting vertex sits *on* the surface, so it was free every other iteration); pinning
vertices within one force step of the surface — 0.60 mm; the same with memory (a touched
vertex stays anchored until lifted two force steps off) — 0.60 mm, with the anchored vertices
drifting **0.0** while the fabric crept past them, because a yarn that flows freely inside
its stitches flows around any pin. With the friction lock inside the stitch as well:
**−0.001 mm**. Friction against the form and friction within the stitch are one physical
fact and only work together.

**D6 — The stitch identity relabel** (sc built as hdc): fixed and pinned in the previous commit
`deface1`; a `validate` key named `stitches_shaped_like_hdc` counted sc stitches as "like hdc"
and is renamed `stitches_shaped_as_ordered`.

## 3. What was implemented (all OFF by default; every committed Visual result untouched)

| where | what | label |
|---|---|---|
| `drape.DrapeSetup.momentum` | FIRE (Bitzek et al. 2006): per-vertex velocity, zeroed where force opposes it | SOURCED, rate only |
| `drape.DrapeSetup.step_multiplier` | ≤ 8×, inside the four-point stencil's stability margin (step·λmax = 0.2 → 1.6 < 2) | DERIVED, rate only |
| `drape.DrapeSetup.support_sphere` | a rigid form the cloth may not enter, radial push-out, every correction counted | the experiment wave 5 §6c asked for |
| `drape.DrapeSetup.support_friction` | static-friction limit against the support: a vertex within one force step of the surface is anchored where it touched, is a fixed point for the length projection, and stays anchored until lifted two force steps off; `stuck_vertices` / `stuck_drift_mm` on the report | BOUNDED |
| `drape.DrapeSetup.rigid_stitches` | per-operation shape matching (Müller et al. 2005) as the infinite-friction limit inside a stitch; `shape_residual_max_mm` reports the stress the lock bore | BOUNDED, argued: 3e-4 N gravity per stitch vs µ 0.2–0.3 × residual loop tension |
| `drape.DrapeSetup.polish_passes` | alternating contact/length passes after the last iteration, ending on the floor, iterated until no pair is under it; residual strain reported; guard-aware | DERIVED |
| `DrapeReport.trace` | (iteration, rms motion, step) every 50 iterations, so "still moving" is visible | — |
| `crochet_topology.validate(reference=)` / `stitch_frames(reference=)` / `stitch_shape.carried_frame` | on a deformed fabric, each stitch's certified frame carried by its own rigid motion; the frame used is named in the result | — |
| `crochet_topology.FLOOR_TOLERANCE_MM = 1e-9` | the floor compared to a nanometre; the floor itself unchanged | numerical |
| `pbr_scene.write_plied_curve_file` / `render(plied_tex=)` / `STAGING_PLIED` | **the bridge**: the certified fabric's own strands → `yarn_construction.ply_geometry` + `surface_fibres` → the committed scene. One geometry for mechanics and picture. `STAGING_PLIED` differs from `STAGING` only in what it admits it does not reproduce | — |
| `visual/milestone_d.py` | the executable assessment (§4) | — |
| `visual/milestones.py` | D is **UNMEASURED** unless measured on the call or a result is passed in; never a stored claim | — |
| `visual/sc_swatch.py` | the sc fixture, in the package | — |

**Bending rigidity.** The D solve uses `derive_bending_rigidity` on the fabric being solved
(hdc wale **1.27e-6 N m²**, 42.3× the committed constant, curvature-independent to 1.0025;
course 5.27e-7; sc wale 1.11e-7). The committed `CALIBRATED_BENDING_N_M2` is documented in
`drape` as unconverged and **was not changed**; the value used is on every result.

## 4. The assessment (`milestone_d.assess`) — what each item measures

| item | measurement | bar | label |
|---|---|---|---|
| stitch_identity | every built op's kind == the CIR cell's stitch; unmodelled kinds refused by name | exact | — |
| certified_flat | `validate` on the relaxed flat | the lock, unchanged | — |
| bending_rigidity_provenance | derived on this fabric; spread over 0.5–2× curvature | < 1.01 | DERIVED |
| equilibrium_fixed_point | gravity off, every option on, 200 iterations | rms < 1e-9 mm (wave 5: 1.6e-17) | — |
| energy_descends | total energy, loaded | final < start | — |
| stationary | rms motion, last tenth of the solve | change < 2 % of the whole motion | CHOSEN, reported with the trace |
| contacts_the_form | closest vertex to the keep-out; corrections counted | ≤ 0.05 mm (under half the smallest cap) | DERIVED |
| no_structural_drift | `validate(draped, reference=flat)`; same count, kinds, loop targets | the lock, unchanged; frame named; **morphology is held by the friction lock and the result says so** | — |
| double_curvature | contact patch on the form: a rigid row tangent to a sphere touches at one point, so rigid rows meet it along one column | ≥ 2 columns in one row AND ≥ 2 rows in one column; articulation up | DERIVED from geometry |
| hand_irregularity | `realised_variation` if a HandTension was applied | ≥ 3.4 % (craft threshold, `hand_tension.PROVENANCE`) | SOURCED |
| render_consumes_validated_geometry | sha256 of the draped points before/after writing; every ply vertex within 1.05 yarn radii of its own strand | exact | — |
| images_rendered | flat and draped, camera and oblique, `STAGING_PLIED`, framed by the same reference | drawn or UNKNOWN | — |
| fabric_folds_naturally, lighting_is_realistic, shadows_are_coherent, has_ordinary_photographic_imperfection, melted_yarn, synthetic_stitch_texture, catalogue_perfect_sterility | — | **UNKNOWN**: a judgement; paid judges frozen by the owner | — |

Rule on the result: *PASS only when every item passes; an UNKNOWN never counts toward a PASS;
a FAIL anywhere is FAIL.*

## 5. Measured evidence

Final evidence: `milestone_d.assess`, 6,400 iterations, the friction model of commit `4c739b1`, renders included. JSON beside the images in `research/d/out/`.

### hdc 5x5 — PARTIAL (B = 1.27e-06 N m², 6400 iterations, 264.5 s)

| item | status | measured |
|---|---|---|
| stitch_identity | PASS | kinds built ['hdc'], mismatches [] |
| certified_flat | PASS | linked 20, shaped 25/25, closest 1.5 mm |
| bending_rigidity_provenance | PASS | used 1.27e-06; derived (wale) 1.27e-06 = 42.3x committed; curvature-independent to 1.0025 |
| equilibrium_fixed_point | PASS | rms 5.67e-15 mm |
| energy_descends | PASS | -6.685e-06 → -4.580e-05 J; rejections 0; stalled False |
| stationary | UNKNOWN | rms motion 6.69 mm; last-tenth change 0.023; final step 1.81e-03 mm; trace (it: mm) … 5650: 6.48, 5850: 6.54, 6050: 6.59, 6250: 6.65 |
| contacts_the_form | PASS | closest 0.0000 mm to the keep-out; 36937 corrections; form R = 18.1 mm |
| no_structural_drift | PASS | linked 20/20, shaped 25/25, closest 1.5 mm (floor 1.5), max strain 8.85e-04, linkage opened 1.918 mm, maxOOP 19.27 mm, lock residual 0.062 mm, frame: certified stitch frame carried by each stitch's own rigid motion |
| double_curvature | PASS | contact patch 10 stitches, 4 columns in one row, 4 rows in one column; within-row fraction 0.0145 vs wrap target 0.0268 (rigid rows: 0); articulation 0.52° → 10.67° |
| hand_irregularity | UNKNOWN | — |
| render_consumes_validated_geometry | PASS | sha256 c39c8b669ed1…, unchanged True; worst ply offset 0.976 mm of yarn radius 1.667; 54 strands, 216 plies |
| images_rendered | PASS | flat_camera: 216 plies, 3456 fibres; flat_oblique: 216 plies, 3456 fibres; draped_camera: 216 plies, 3456 fibres; draped_oblique: 216 plies, 3456 fibres |
| fabric_folds_naturally | UNKNOWN | — |
| lighting_is_realistic | UNKNOWN | — |
| shadows_are_coherent | UNKNOWN | — |
| has_ordinary_photographic_imperfection | UNKNOWN | — |
| melted_yarn | UNKNOWN | — |
| synthetic_stitch_texture | UNKNOWN | — |
| catalogue_perfect_sterility | UNKNOWN | — |

### sc 5x5 — PARTIAL (B = 1.11e-07 N m², 6400 iterations, 217.9 s)

| item | status | measured |
|---|---|---|
| stitch_identity | PASS | kinds built ['sc'], mismatches [] |
| certified_flat | PASS | linked 20, shaped 25/25, closest 1.3695 mm |
| bending_rigidity_provenance | PASS | used 1.11e-07; derived (wale) 1.11e-07 = 3.7x committed; curvature-independent to 1.0005 |
| equilibrium_fixed_point | PASS | rms 1.79e-15 mm |
| energy_descends | PASS | -1.706e-06 → -9.527e-06 J; rejections 0; stalled False |
| stationary | UNKNOWN | rms motion 3.15 mm; last-tenth change 0.021; final step 1.54e-03 mm; trace (it: mm) … 5650: 3.06, 5850: 3.08, 6050: 3.11, 6250: 3.13 |
| contacts_the_form | PASS | closest 0.0000 mm to the keep-out; 46765 corrections; form R = 12.7 mm |
| no_structural_drift | PASS | linked 20/20, shaped 25/25, closest 1.3645 mm (floor 1.0), max strain 1.36e-03, linkage opened 1.304 mm, maxOOP 9.14 mm, lock residual 0.011 mm, frame: certified stitch frame carried by each stitch's own rigid motion |
| double_curvature | PASS | contact patch 14 stitches, 4 columns in one row, 5 rows in one column; within-row fraction 0.0738 vs wrap target 0.0919 (rigid rows: 0); articulation 0.30° → 10.76° |
| hand_irregularity | UNKNOWN | — |
| render_consumes_validated_geometry | PASS | sha256 73e4a1a05b95…, unchanged True; worst ply offset 0.651 mm of yarn radius 1.111; 21 strands, 84 plies |
| images_rendered | PASS | flat_camera: 84 plies, 1344 fibres; flat_oblique: 84 plies, 1344 fibres; draped_camera: 84 plies, 1344 fibres; draped_oblique: 84 plies, 1344 fibres |
| fabric_folds_naturally | UNKNOWN | — |
| lighting_is_realistic | UNKNOWN | — |
| shadows_are_coherent | UNKNOWN | — |
| has_ordinary_photographic_imperfection | UNKNOWN | — |
| melted_yarn | UNKNOWN | — |
| synthetic_stitch_texture | UNKNOWN | — |
| catalogue_perfect_sterility | UNKNOWN | — |

**Reading the two tables.** Both swatches keep every Product Truth lock through a real drape (hdc 19.3 mm, sc 9.1 mm of out-of-plane motion) and meet the form over a two-way patch (4×4 and 4×5 stitches). Stationarity missed the 2 % bar by a little on both (2.3 %, 2.1 %) with the motion still creeping ~0.05 mm per 200 iterations at the end; it is UNKNOWN, the bar was not moved, and the trace is on the result. The certified linkages open by up to 1.9 mm (hdc) and 1.3 mm (sc) under load while staying linked — reported, not judged, because no non-invented limit on a link opening exists (wave 5 §4a). The stress the friction lock bore never exceeded 0.06 mm (hdc) / 0.011 mm (sc). Within-row relief sits at 54 % (hdc) and 80 % (sc) of what fully wrapping the form would demand; a stiff cloth lifting off a small sphere is expected to sit below 100 %, which is why the bar is the contact patch and not this ratio.

## 6. Before / after

- **Before** (wave 5, committed scene, tube): `wave5_reconciled_oblique.png` — 0.566 mm of
  drift, rows as bars, smooth tubing.
- **After** (this wave, `research/d/out/`): `hdc_flat_plied_*.jpg`, `hdc_draped_plied_*.jpg`,
  `sc_flat_plied_*.jpg`, `sc_draped_plied_*.jpg` — the draped configuration that re-validates,
  drawn with plies and a sparse fibre halo, same camera, same key, same backdrop, framed by
  the flat reference so the drape is seen to have happened. They are geometry-instrument
  images: `STAGING_PLIED["not_reproduced"]` still lists the fibre normal map, hand tension and
  the Layer 3–5 material stack. **They are not offered as evidence about appearance.**

## 7. What is NOT claimed

- Not PASS. Seven judged items are UNKNOWN. A person can judge the rendered files; no model
  judge was run (spend frozen).
- Morphology under drape is **an input** of the friction lock, not an outcome. Linkage, floor,
  contact, curvature and equilibrium are outcomes and are measured.
- `rigid_stitches` and `support_friction` are infinite-friction limits, BOUNDED by an
  order-of-magnitude argument, not by a measured friction coefficient for this yarn.
- The derived bending rigidity is derived by the committed procedure on a 5×5; wave 3's
  finding that the energy's bending length grows with swatch size is not resolved here.
- Stationarity: the 2 % bar was missed by a little on both swatches (2.3 %, 2.1 %) at 6,400
  iterations; the item is UNKNOWN and the trace is on the result.
- Nothing about `twin.calibrated`, which stays False. No physical calibration exists.
- The ladder: A PASS, B PARTIAL, C PARTIAL are unchanged; D's PARTIAL rests on them as they
  are, which `_ladder` reports.

## 8. Tests

- `tests/test_drape.py`: 144 → 157 (wave-6 block: drift pinned as linear; momentum,
  step multiplier, trace; the sphere; the fixed point with every option on; the polish meets
  the floor; shape matching; rigid stitches through a real drape re-validate in the carried
  frame; a fabric slides on a frictionless slope and stays with friction).
- `tests/test_stitch_identity.py`: 23 → 29 (the carried frame: itself, a 40° rotation, a real
  eversion caught in both frames, the folded-fabric defect pinned, `rigid_rotation`).
- `tests/test_render.py`: 11 → 14 (the plied writer draws the certified strands and nothing
  else; moves no control point; `STAGING_PLIED` differs only in what it admits).
- `tests/test_milestone_d.py`: new, 15 (statuses closed; judged items UNKNOWN; no PASS with an
  UNKNOWN; criteria carry reasons; derived B on the result; friction lock declared; ladder
  UNMEASURED by default; a supplied result flows through gating).
- **Full suite on the isolated branch (commit c6ad3e5 code): 4,239 passing, 1 suite failing** -- `test_cost_governance_wave2`, two checks. One was this wave's: `milestone_d` wrote its curve file under a `TemporaryDirectory` prefix (`brambleloop-d-`) absent from `health.TEMP_PREFIXES`, invisible to the disk signal -- the guard the 2026-09-25 wave verification recorded, catching the same defect again; the prefix is now registered and the check passes. The other, `test_a_spender_the_registry_has_never_heard_of_gets_no_invented_ceiling`, **reproduces on the untouched integrated checkout fcb982d** and is date-dependent: its rows are stamped at a frozen NOW of 2026-09-25 while `spend_report.per_agent_today` reads the wall clock, so from 2026-09-26 the frozen spend is not "today" -- the very defect class the file's next test names. Not Visual's, not touched here, recorded for the integrator. **Rerun with the prefix registered, read from its own TOTAL PASSING line: 4,240 passing, 1 suite failing -- that one pre-existing, date-dependent check and nothing else.**

## 9. Named gaps

`dc` cell, `inc`, joined-rounds construction: not modelled, refused by name
(`UnmodelledStitch`, `UnmodelledConstruction`). Hand tension: builds and certifies
(hdc 5×5 with `HandTension()`: 20/20 linked, 25/25 shaped, floor met; realised stitch-width
CV 2.3 %, row-height CV 3.3 % — under the 3.4 % craft bar at the specified 5 % loop-length CV,
which is a finding about the anchor, not applied to the assessed build). Friction coefficient
for this yarn: UNKNOWN. A judge for the seven UNKNOWN items: none ran.

## 10. Close-out (owner's instruction, 2026-09-26): the UNKNOWNs resolved with the evidence each criterion requires

### 10a. The independent judge on the authoritative instrument renders — FAIL

Judge: `d_judge` → OpenAI `gpt-5-2025-08-07`, image inline at high detail, the seven B-700 fabric items in the vocabulary of the failure, omitted keys UNKNOWN, this module deciding (PASS only when every authoritative view is sound). Views: the draped camera and oblique renders of each swatch at the assessed geometry hash. Cost: **US$0.0552** (hdc 0.0303, sc 0.0249). Full records: `research/d/out/judge_hdc.json`, `judge_sc.json` (prompt, system, raw answers, response ids, usage, image sha256).

**hdc**

| item | status | per view |
|---|---|---|
| fabric_folds_naturally | FAIL | camera: None, oblique: False |
| lighting_is_realistic | UNKNOWN | camera: None, oblique: True |
| shadows_are_coherent | UNKNOWN | camera: None, oblique: True |
| has_ordinary_photographic_imperfection | FAIL | camera: None, oblique: False |
| melted_yarn | FAIL | camera: None, oblique: False |
| synthetic_stitch_texture | FAIL | camera: None, oblique: False |
| catalogue_perfect_sterility | FAIL | camera: None, oblique: False |

- `hdc_draped_plied_camera.png` — gpt-5-2025-08-07, `chatcmpl-ESCc8Ey1n86OlEPkFtUaZhVAYYQdF`, 1007+1500 tokens, US$0.0163: no JSON in the answer (the model spent its 1500 tokens reasoning; budget since raised to 4,000)
- `hdc_draped_plied_oblique.png` — gpt-5-2025-08-07, `chatcmpl-ESCcSQcNU1fJUd6yWxlpYY8wqos2W`, 1007+1280 tokens, US$0.0141: “Swatch floats in space and the yarn appears like smooth, clay-like tubes without fibers. Uniform studio backdrop and procedural-looking loops make it read as CG.”

**sc**

| item | status | per view |
|---|---|---|
| fabric_folds_naturally | FAIL | camera: False, oblique: False |
| lighting_is_realistic | PASS | camera: True, oblique: True |
| shadows_are_coherent | PASS | camera: True, oblique: True |
| has_ordinary_photographic_imperfection | FAIL | camera: False, oblique: False |
| melted_yarn | FAIL | camera: False, oblique: False |
| synthetic_stitch_texture | FAIL | camera: False, oblique: False |
| catalogue_perfect_sterility | FAIL | camera: False, oblique: False |

- `sc_draped_plied_camera.png` — gpt-5-2025-08-07, `chatcmpl-ESCcjwin7NmIslyAwvNkYPngDmI59`, 1007+958 tokens, US$0.0108: “Yarn appears smooth and plastic with no fibers, and the swatch floats on a seamless background with uniform renderer-like noise and highly regular structure.”
- `sc_draped_plied_oblique.png` — gpt-5-2025-08-07, `chatcmpl-ESCcy5dJ4BU1dHtP6g10qERvc46NA`, 1007+1280 tokens, US$0.0141: “The swatch floats in space and the yarn looks like smooth uniform tubes with no fiber detail. The sterile grey background and plastic-like material read as CG.”

**Verdict from the executable criterion after the judgement: D = FAIL on both swatches** — the photographic-presentation items fail. Every mechanical item still passes. The judge's stated reasons are all properties of the *scene*: the yarn drawn without a resolvable fibre population, the form the fabric rests on never drawn ("floats"), a seamless grey backdrop, integrator noise. Three of them are exactly what `STAGING_PLIED["not_reproduced"]` declared.

### 10b. Stationarity — resolved by finishing the solve, not by moving the bar

| | hdc | sc |
|---|---|---|
| 6,400 it (momentum) | 2.3 % → UNKNOWN | 2.1 % → UNKNOWN |
| 12,800 it (momentum) | 2.3 % → UNKNOWN; creep constant at 0.031 mm / 200 it | **1.58 % → PASS** |
| 12,800 + 3,200 momentum-off settle | **0.55 % → PASS**; creep 0.006 mm / 200 it | SC_SETTLE_PLACEHOLDER |

Semantics: the criterion measures whether the fabric has stopped; a constant creep under momentum can never satisfy a bar stated over the last tenth of a growing solve, and should not. The creep was the momentum method's floor, not the force law: with momentum off (how a FIRE minimisation is finished; rest state carried, trace measured from the same origin) it fell fivefold and the unchanged 2 % criterion is met. Every result states `settle_iterations`; the `_12800_settle.json` records are the evidence configurations, and their draped points are saved with their hashes (`*_draped.npz`).

### 10c. The geometric hand-irregularity item — a measurement, not a gate (D-W6-11)

At the sourced 5 % loop-length input the realised variation under the owner's per-row anchor is 2.3 % (stitch width) and 3.3 % (row height); the 3.4 % "half a stitch over a swatch" bar is a gauge-deviation statement the anchor makes unsatisfiable by construction. Reported beside the judged imperfection items; not gated.

### 10d. Presentation iteration on the failing property

PRESENTATION_PLACEHOLDER
