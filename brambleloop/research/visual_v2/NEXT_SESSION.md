# Visual V2 independent R&D — recovery checkpoint

Work in progress, 2026-09-27. Branch `codex/visual-v2-rnd`; base `0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56` from a fresh clone of StateFarm91/Project-Money. Claude's checkout/branch was never modified. Prior audit handoff and pack index read directly from `e6c397656d42406d9da338264f15bb36fadab5cf`.

Only change `brambleloop/research/visual_v2/`. No Build 2 status changes, merge, deployment, publication, Etsy, production, canonical-model changes or paid calls. User explicitly authorized local zero-cost proofs and commit/push to this branch. Finish report, artifacts, checks, commit and push.

Findings already verified from raw records and source:

- Bench1: 14 actual draws (12 OpenAI + 2 Gemini), one contemporary gate PASS; prose's 1/12 overall is wrong. The gate accepts texture `other`; hero is not proof of exact waffle identity.
- E5: sum raw mode judge passes; report says 18/21 but its own table appears 17/21. Reconstruct with `evidence_audit.py`.
- V1 graduation: 15 FAIL + 1 UNKNOWN, no hero; exact column count is NON-MATERIAL in gate.py and explicitly tested that way. Pitch tolerance alone cannot certify exactly 18 columns or crossing phase.
- Frozen Product Truth: 144 x 121 cells, 18 columns, 540 crossings, cream #FAF6EB, 90 x 128.9 cm, uncalibrated; crossing direction unspecified, old reference declares left pair in front. Actual crossing row height uses cable2x2 2.0, plain rows 1.9, relative to sc. Frozen `crossing_period_cm=4.222` omits the taller crossing row; actual CIR schedule yields 4.27778. Do not change old truth/gates: preserve and report discrepancy.
- Milestone D tried actual Mitsuba plies/fibres, hair scattering, continuous paths, drape/friction controls. It failed realism, not all deterministic rendering in principle. `crochet_topology.CELLS` supports only sc/hdc, so a certified cable renderer does not already exist.
- E5 masks made product editable. No protected-foreground/restoration compositor was tested. A/B references + masks/normals as images are not native depth/normal controls.
- V1grad and Bench2 full generated images absent from git, only half-size previews + full hashes. Cannot claim full-size raw pixel remeasurement.
- E1 C0 automated stripes_found=0; prose stripe positions include visual observations, not all instrument measurements. E2 three manifests total eight draws / $0.24, no independent quantitative certification located; generic woman prompt does not establish canonical identity.

Environment: bundled Python 3.12 with numpy/Pillow. SciPy 1.17.1 downloaded to sibling `runtime-python` (outside git, within workspace); its inherited ACL was repaired after pip temporary-directory permissions prevented sandbox access. Add absolute path to sys.path (bundled Python ignores PYTHONPATH). GTX1070 8GB. Portable Blender 4.5.0 downloaded from official archive, checksum `2ee75e9466d293a784fdf020f60fe1309c1e0610ecf73c64f1fc09b01e5eec56`; extracting to sibling runtime-blender. No paid spending.

Proposed architecture, not yet final: replace product-redrawing stage with CIR -> semantic structure compiler -> verified stitch/material assets -> LOD procedural PBR product -> renderer alpha/depth/normal/IDs/shadow -> background-only AI proposal -> deterministic recomposition. Macro geometry/pixels authoritative; any relight or new pose requires re-render + revalidation. Treat exact physical appearance as UNKNOWN while gauge/material uncalibrated. ControlNet is a distinct untested alternative, not an exact lock; UV-space bounded material synthesis possible later.

Next actions: finish raw audit; run existing offline tests with network disabled; build 18-column procedural structure/PBR/compositor proof (explicitly label any proxy stitches UNKNOWN, not certified); adversarially verify locks and old instrument blind spots; write VISUAL_V2_ARCHITECTURE.md with cited research/acceptance/economics and replace this checkpoint with final handoff.
