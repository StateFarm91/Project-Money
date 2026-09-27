# Persisted Visual evidence coverage — 2026-09-27

Audit source checkpoint: Claude/Fable branch `4edacff1f8b445a84749464dc1d7271e6c71173e`; original V2 evidence base `0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56`; pre-audit V2 `49e5b0a1e289906a7c89dd386c6733ed0c2a63cc`. Read-only fetch; no Claude worktree or Build 2 status changed. All edits under Visual V2. No experiments repeated. Spend $0.

## Inventory and coverage boundary

Inventory: 768 selected paths / 1003 blob versions at inspected tips, plus four historical depth arrays; 1401 historical path-change entries. All482 prior entries covered. No central D/E1-E5/Bench1/Bench2/V1grad experiment path changed between0d42f2f and Claude4edacff.

[inventory.json](inventory.json) enumerates selected path/blob versions across every fetched remote tip, the original evidence base and pre-audit V2. It includes SHA256, Git blob ID, refs, classification, matching text locations, comparison with the original 482-entry manifest, and a historical change index. [audit_coverage.py](audit_coverage.py) reproduces discovery using Git blobs, not live services. The historical index is discovery, not a claim every intermediate revision was semantically reread.

This is a complete inventory under the recorded path/content selectors, with broader discovery of Visual-related text and branch/history artifacts. It cannot prove existence or completeness of uncommitted Claude scratchpads, external model packs, remote provider outputs, or references never persisted to Git. Keyword hits include incidental integration context; they are not additional experiments. The four working-memory documents were compared at the pre-audit checkpoint; being hashed or mentioned is distinct from having findings extracted.

Persisted families found:
- Visual investigation, architecture decision, Waves 2–5, yarn-slip research, governance; Milestone D, E1–E5, Bench1, Bench2 and Product-Only Visual V1 reports.
- D/E1–E5/Bench1/Bench2/V1grad builders, runners, inputs, manifests, gates, judge records, spend records, reference and provider images/previews.
- Visual topology, linkage, drape, PBR/yarn, gates, identity/reference packs; CIR/product definitions; image-provider gateways; corresponding tests and adversarial fixtures.
- BUILD_STATE and DECISION_LOG revisions, publication QA/crossing ambiguity records, catalogue calibration limits, Build 2 closeout/certification/resume reports and persisted cluster patches.
- Root topology/PBR/ply/fibre/fuzz/drape/Wave5 images, previously outside the 482-file inventory.
- Four E3 float32 depth arrays recovered by reading Git blobs at `0f7bc237c3240696e72a6a5de7ef4fafdfb27a5f`: sc/hdc camera/oblique, each 1000x1000 and entirely finite. Not restored into historical directories. These are existing reference depth outputs, not evidence the provider consumed native depth control.

**Central experiment trees have zero changed paths from original base to fetched Claude tip**: D, E1, E2, E3, E4, E5, Bench1, Bench2, V1grad. The existing raw-evidence reconstruction remains applicable. No new certified Heirloom hero was found.

## Previously missed, versus merely under-extracted

1. Absent from original inventory: YARN_SLIP_RESEARCH.md; 34 root PNG/SVG artifacts; test_photoreal_calibration.py, test_reference_pack.py, and broken-stitch-count regression record. Broader context was also absent: creative/reference.py, publishing photography, reference/identity/spend tests, DELIVERABLE_QA1–3, catalogue and integration records. Full path list is machine-readable.
2. Waves 2–5 and VISUAL_GOVERNANCE.md were hashed, but the durable V2 findings did not adequately retain their mechanisms, failures, corrections and limitations. Hash coverage was insufficient.
3. New since original base: gallery live-gate escalation, inspect text/chart-preview checks, parity gate forwarding, release/pipeline wiring and Build 2 resume/cluster records. Persisted mbox/diff files are evidence snapshots; they were not applied and must not be confused with integrated code.
4. Historical E3 depth arrays were absent at inspected tips, but persisted blobs remain recoverable. The missing frozen D PNG required by E4/E5 is not among these recovered objects. Full Bench2/V1grad generated originals remain unavailable in the inspected Git evidence; half previews do not replace them.

## Ingested findings and underlying evidence

| Evidence | Extracted result | Implication |
|---|---|---|
| YARN_SLIP_RESEARCH.md, sources/sections 1,6,12–14 | Distinguishes Lagrangian free contacts (material discretisation fixed but yarn can slide through contact) from EoL contact nodes with sliding material coordinates. No verified crochet-specific simulator supplied. Stage0 physical measurement/Stage1 redistribution was a proposal, not a successful experiment. | Do not repeat welded-node bending as a cloth solution, and do not equate all fixed material coordinates with prohibited sliding. |
| Same report, literature inventory | Persisted crochet-specific leads include Guo et al. SCF2020 *Representing Crochet with Stitch Meshes* (only abstract obtained) and CT2Yarn (report records a full-text read). | Correct the implication that all prior asset literature was knitting-only. These are research leads, not available/validated post/DC/cable assets. External claims were not freshly verified during this repository audit. No Heirloom finished photo supplied. |
| VISUAL_WAVE2.md, corrected by WAVE3 | Solver segment median4.0860mm, not filtered3.1427mm; B/l^3=.43976N/m, not .9665. Bounded prestress1.010x gravity, not2.22x. Old cantilever force was Laplacian/string-like, not gradient of documented bending energy. | Do not reuse stale calibration numbers or interpret more iterations as a solution. |
| VISUAL_WAVE4.md; drape.py; crochet_topology.certified_linkage_pairs | Tensile linkage reduced opening1.75 to.040mm but worsened edge eversion. Zero-load motion exposed instability; successful attachment constraints did not establish cloth-like drape. Actual target-strand relationships already exist for SC/HDC. | Reject axis winding alone as a topology certificate. Reuse actual strands and test closing conventions; do not redo tensile-link sweeps. |
| VISUAL_WAVE5.md; drape.py options and tests | 99.99996% of injected co-rotational energy was on artificial path hops/joins. Gradient force, rest contacts and genuine-yarn masking restored zero-g equilibrium1.58e-17mm/2.43e-17mm. SC/HDC locks remained; drape still rigid-bar-like, not a D pass. New options were off by default. | Distinguish material yarn from bookkeeping connectors; require zero-load controls if adding mechanics. A solver correction is not photographic qualification. |
| Same report sections6/6d; yarn.py vs crochet_topology.py | Best ply/fuzz pictures and topology/mechanics experiments represented different geometry. Strong-deformation _encirclement false negatives remained unresolved. | Render and measure identical geometry. Treat existing linkage instruments as useful bounded tools, not universal oracles. P06 did bind measured/rendered centerline; it still failed. |
| Root pbr_sourced, yarn_layer5_hand_surface_fuzz_ply_bsdf, wave5_reconciled_camera images visually inspected; other root outputs inventoried | Ply/fuzz progress is real; images still show rigid/open tube-like construction. Wave5 neutral diagnostic lacks the earlier yarn material detail. | Neither file presence nor prettier yarn certifies actual product topology/realism. No new numerical grade assigned from these views. |
| DELIVERABLE_QA.md section12; QA2 remaining findings; frozen stitch registry | Cable direction was already an explicit publishing/CIR gap (PDF_CABLE_DIRECTION_UNSPECIFIED). Later registry field exists but frozen cable value remains None. | P06 ambiguity is corroborated by earlier independent product QA, not a new reason to rewrite Product Truth. |
| test_photoreal_calibration.py; test_reference_pack.py; reference/photoreal source | Mocked tests distinguish real-photo judge control, unavailable evidence, reference contamination, byte/version provenance and pack identity. | These prove gate behavior, not a real-photo PASS or a certified canonical-model render. Do not infer provider outcomes from test doubles. |
| VISUAL_GOVERNANCE.md and spend-path tests | Historical image/certain model paths bypassed parts of common pre-call reservation; fibre_content intentionally unknown for11 existing CIRs. | Old configured ceilings are not spending authority; cream/acrylic truth does not calibrate a yarn BSDF. |
| BUILD2_CLOSEOUT_REPORT sectionQ; new resume design report; gallery/inspect/parity diff | Product V1 remains NOT LOCKED, model-bearing rendering external-blocked. New code adds live-gate escalation and QA wiring; design report keeps photography external. No new native conditioning or stitch-faithful generator is evidenced. | Does not change zero-hero blind test or justify changing Build2 statuses. |

Historical test totals quoted in these sources remain historical. This audit did not rerun provider trials, physics solves, or Build2 tests. Existing V2 record of151 offline checks plus two missing-evidence suites remains unchanged.

## Decision and continuation

**REPLACE Visual V1's product-redrawing stage with B+C remains the recommendation.** Missed evidence materially improves the implementation constraints, not the architecture selection or certification verdict. Prior deterministic work is substantially deeper than a schematic swatch; it disproves several tempting shortcuts.

Next bounded work remains a single DC construction, before neighbor/turn/full throw. Add an operation graph with explicit intermediate loops and test the *actual strands* participating in two successive pull-throughs. First discriminate a loop-count-only trace from the correct ordered consumption of named loops and from a spatial linkage certificate. Use existing linkage code only on valid disjoint closed control curves with adversarial controls; open-arc closure ambiguity must stay visible. No claim of actual crochet until spatial yarn routing, clearance, construction and independent review all pass. This is a new instrument/representation increment, not a repeat of P06 hand-shaped loop candidates.

Frozen Heirloom:18 columns,50mm pitch,540 crossings,144x121 cells; same truth hash and original thresholds. Structural truth and photographic realism remain separate; UNKNOWN never becomes PASS. No paid generation is needed for this next increment.
