# V2-P06 result — explicit yarn coupon rejected
Date: 2026-09-27. Resumed from `d38e471`; initial failed trials checkpointed at `d9d5006`. All changes are in Visual V2. External spend **$0**.

**STRUCTURAL TRUTH: FAIL. PHOTOGRAPHIC REALISM: UNKNOWN. Full-throw stage: BLOCKED.**
This experiment made the next representation testable and rejected its current implementation. It did not deliver a correct crochet asset or a certified product image.

## What ran

A complete source contract was derived from the unchanged Heirloom CIR: 17,424 cells, 18 cable columns, 540 crossing groups, width900mm and nominal height1288.8889mm. Its Product Truth SHA256 remains `cf3b9d1a9e92cff41ca2e461b9795cecbaa12d42d89ddb47420aad6307d85808`.

The geometric test fixture contains one eight-stitch repeat over rows1–9: SC8, FPDC24, BPDC32 and cable cells8, plus eight foundation-chain and seventeen turning-chain hypotheses. It is a **coupon**, not a smaller replacement throw. Its artificial boundary does not certify the actual product edges.

The new representation has one ordered yarn centerline, explicit prior-post attachments, two proposed DC closing stages, tops, turns and foundation paths. SC uses the existing `_sc_cell` implementation. DC/chain spatial embeddings are research hypotheses, not published or independently approved stitch assets. The hook-count sequence1→2→3→2→1 establishes intended operations only; it cannot certify that a spline realizes those operations.

No AI image model was used. A neutral Blender Cycles diagnostic renders the exact dense polyline measured by the instrument, at the same fixed1.8mm yarn diameter. Its low-detail plastic appearance is intentional for inspection; no material, fuzz, photographic, drape or listing qualification was attempted.

## Results

| Trial | Depth parameter* | Failed segment pairs | Body/body pairs | Longest connector | Post winding proxies | Structure |
|---|---:|---:|---:|---:|---:|---|
| baseline_top |2.2mm|34,182|28,578|51.000mm|56/56|FAIL|
| wider_top |4.0mm|32,236|24,374|51.000mm|56/56|FAIL|
| routed_top |2.2mm|29,483|27,056|7.877mm|56/56|FAIL|
| routed_post_hypothesis |2.2mm|30,003|27,576|7.877mm|56/56|FAIL|

*The parameter controls wrap depth and the reused SC cell depth; it is not measured finished-fabric thickness. Yarn diameter, nominal pitch6.25mm, original row heights, counts and contact floor stayed fixed.

The contact threshold is the existing0.45×diameter = **0.81mm**, with1e-9mm numerical tolerance. Minimum separation is0 in the first two trials and approximately3.52e-10mm after repair: effectively an intersection. Failed-pair counts are dense segment pairs, **not distinct defects** and not a certification score. Several pairs can describe one collision.

The routing revision corrected foundation travel so row1 no longer needs a full-width return strand, and opened coincident/near-closed chain and closure arcs. That removes a real builder defect; it does not make the DC construction correct. Increasing depth alone did not resolve intersections. Most failing pairs remain inside/between stitch bodies, so edge fixes alone cannot make this coupon pass.

All four trials pass nine source/fixture checks, six adversarial checks and four analytic segment-distance controls. The56 post tests include signed front/back winding and deliberate wrong-anchor/wrong-face controls. The winding test closes an open arc with a fictitious chord around a prior-post axis; **it is a local geometric proxy, not a complete crochet entanglement invariant**. Winding and hook-count checks passing while contact fails is the decisive negative result.

The spatially different cable hypotheses preserve the same counts but differ by up to **9.1069mm** at corresponding cable control points. The post version is deliberately non-authoritative; it is evidence that a count-only contract cannot select construction.

The revised top-loop diagnostic's approximate tube bounds are56.779×95.466×10.599mm. Those are actual proxy bounds, not a measured gauge or finished coupon size. Product silhouette, gauge, edge identity and full18-column physical construction remain unqualified. The full source count is not an18-column rendered-product PASS.

## Construction ambiguity

The frozen registry leaves `cable2x2.crossing=None`. The [written method](../../../src/brambleloop/publish/abbreviations.py) names a cable needle and ordinary DC, while [design notes](../../../src/brambleloop/products/texture.py) describe the held pair in front. The existing reference's left-pair-front convention is not a complete yarn/anchor definition.

The strict adapter therefore refuses authoritative full-product compilation. It must not silently substitute a front-post cable, infer new design intent or change the pattern. The owner has been asked whether an existing authoritative stitch-level definition resolves attachment targets and crossing order. Even with that clarification, the failed DC/chain geometry still needs replacement.

The primary [Yarnspirations post-stitch instructions](https://www.yarnspirations.com/en-row/blogs/how-to/ultimate-guide-to-crochet-post-stitches) support attachment around a prior stitch body and two successive DC draw-through operations. They do not validate these new centerlines. The [cited crochet modelling paper's scope](https://fis.tu-dresden.de/portal/en/publications/topology-based-modelling-of-crochet-structures%2807ed0619-0cd8-4216-a2d4-c099f759017b%29.html) covers chain/slip/SC; it supplies no ready verified DC/post/cable asset.

## Decision and next action

**Reject the current manually shaped DC/chain embedding.** Do not smooth, shrink yarn, change gauge, add fuzz or use AI repaint to make the failure harder to see. Do not instantiate this asset across the full throw.

The next minimum engineering target is one DC attached to a known prior post, with a spatially validated two-stage pull-through, then its neighbor and return-row transition. Validate actual anchor strands, self-contact and knot construction before growing another complete coupon. A fabrication-operation graph with explicit intermediate loops must drive the spatial embedding; another decorative pair of loops is insufficient. Independent crochet review remains UNKNOWN and is required before coupon acceptance. Cable clarification can proceed separately while this lower-level work continues.

Architecture B+C remains the recommendation, but this **implementation** failed. Protected foreground composition from P03 is unchanged; no generator acquired authority over the product.

## Files and reproduction

- [Initial protocol](EXPERIMENT.md), [builder](build_coupon.py), [verifier](verify_coupon.py), [diagnostic renderer](render_coupon.py).
- [Full source contract](out/source_contract.json).
- Raw geometry and measurements in `out/{baseline_top,wider_top,routed_top,routed_post_hypothesis}/`.
- [Visible diagnostic](out/routed_top/diagnostic.png), [render record](out/routed_top/render.json).
- [Closeout validation](out/closeout.json). The earlier V2 `out/final_validation.json` is a historical first-pass snapshot, not a digest manifest for subsequently edited working-memory files.

From repository root, using the existing bundled Python and SciPy path documented in the parent README:

```powershell
& $v2Python brambleloop/research/visual_v2/coupon/build_coupon.py --tag baseline_top --spread 2.2 --cable-mode top --route-revision 0
& $v2Python brambleloop/research/visual_v2/coupon/build_coupon.py --tag wider_top --spread 4 --cable-mode top --route-revision 0
& $v2Python brambleloop/research/visual_v2/coupon/build_coupon.py --tag routed_top --spread 2.2 --cable-mode top --route-revision 1
& $v2Python brambleloop/research/visual_v2/coupon/build_coupon.py --tag routed_post_hypothesis --spread 2.2 --cable-mode post --route-revision 1
& $v2Python brambleloop/research/visual_v2/coupon/verify_coupon.py --tag routed_top --deps ..\runtime-python
& $v2Blender --background --factory-startup --python brambleloop/research/visual_v2/coupon/render_coupon.py -- --tag routed_top
```

Run the verifier once for each tag. It exits successfully when the experiment/instruments behave as specified; **read `structural_truth`**, which is FAIL for every candidate. A successful experiment runner is not product certification. Current code exactly regenerates all four recorded centerline hashes. Historical builder byte hashes for the initial runs resolve at d9d5006.

The renderer's first diagnostic was overexposed; exposure was corrected to−5 stops for inspection without modifying geometry. Final diagnostic setup/render13.828s. No full-resolution hero, garment, drape, canonical-model, paid-provider or Build2 test was run. The151 earlier offline assertions and two missing-evidence suites remain historical results, not claims about this new asset.
