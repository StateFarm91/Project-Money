# V2-P07 — named-loop construction graph and draw-through instrument

Executed locally on 2026-09-27 after the persisted-evidence audit checkpoint `089f78e`. No paid services or historical experiment reruns. This is a new representation/instrument increment toward the one-post DC experiment; **a complete DC asset was not built**.

**STRUCTURAL TRUTH: UNKNOWN. PHOTOGRAPHIC REALISM: UNKNOWN. Full-product emission: BLOCKED.**

## Question and scope

Can named, ordered loop consumption plus explicit spatial passage distinguish a two-stage DC operation from a diagram that merely reports three, two, then one loop?

The operation graph records yarn-over, pull-up from the specified prior-post target, first draw-through of drawn-up/wrap loops, then second draw-through of intermediate/original-live loops. Each loop has a creation and consumption event. Seven adversarial traces keep or corrupt counts while changing target, face, order, lifetime or closure arity.

The spatial controls are **idealized closed rings** and an open folded yarn bight, not real parent-stitch strands. Stage1 tests passing through two of three named loop openings while retaining the third. Stage2 separately tests two of two. Each has 33 frames, exact polygonal centerlines and fixed 1.8 mm research yarn diameter. These fixtures intentionally isolate the instrument; they do not establish a hook, parent post, material transfer, connected stitch, neighbor or return row.

This narrower step is justified by the newly ingested Wave4/5 linkage limitations and P06's 56 passing axis-winding proxies despite tens of thousands of intersections. It is not another P06 embedding or a changed product.

## Measured results

| Fixture | Target passage | Sampled minimum separation | Conservative continuous lower bound | Local result |
|---|---|---:|---:|---|
| stage1_two_of_three | two required, third untouched | 2.199337 mm | 1.986837 mm | PASS |
| stage2_two_of_two | two required | 2.199337 mm | 1.986837 mm | PASS |
| miss_second_loop | second omitted | 2.199337 mm | 2.080587 mm | FAIL |
| consume_third_loop | retained loop consumed | 2.199337 mm | 1.893087 mm | FAIL |
| outside_targets | no opening entered | 2.200000 mm | 1.987500 mm | FAIL |
| rim_collision | yarn intersects target rim | 0 mm | -0.212500 mm | FAIL |

The original compressed-contact floor stays **0.81 mm**. Both nominal controls also exceed the full 1.8 mm diameter. A negative lower bound is an unhelpful conservative bound, not negative physical distance.

The bound is specific and checkable: all corresponding moving vertices are affine functions of frame time, target rings are fixed, and distance changes by at most the largest moving-point displacement. Minimum sampled segment distance minus maximum interframe displacement bounds the entire interval. A separate saved-artifact verifier remeasures this and confirms affine interpolation error at most 2.22e-15 mm. This is not a general cloth collision solver and does not assess complete-stitch self-contact.

- Named-loop graph: PASS at semantic scope; seven mutations rejected.
- Spatial instrument: two positive controls and four negative controls behave as specified.
- Existing `visual.linkage.linking_number`: returns **zero** for the whole closed bight both inside and outside the target rings. A folded bight has oppositely signed passages and can withdraw; zero is the correct invariant. Requiring nonzero linking of the whole bight would be the wrong certificate. Existing SC/HDC gates use selected strand relations and were not changed.
- Saved-artifact checks: nine hashes pass, Product Truth unchanged, deliberate geometry-byte mutation detected.
- Generation/measurement runtime: 2.809 seconds in the final run; geometry byte hash unchanged after source/manifest reproducibility repair. Saved verification is a separate invocation.

## Why local PASS cannot become a stitch PASS

The independent assembly check finds:

1. Visible bight length grows from **11.253285 to 24.853285 mm** with stationary end positions: **13.6 mm of material feed** must be accounted for. There is no material-coordinate or feed ledger. Assigning fixed material IDs to these vertices would silently stretch yarn.
2. The retained `live_0` ring is independently restaged by **3 mm** between fixtures; no transition trajectory exists.
3. The first fixture's intermediate open bight is replaced by an unrelated closed ring in the second. There is no persistent intermediate yarn identity.
4. Prior-post attachment, actual loop strands, continuous complete yarn, self-contact/relaxation, gauge and independent crochet review remain unqualified.

The assembly boundary therefore blocks emission. These are **instrument controls**, not physically fabricated DC, not an 18-column throw and not a photographic candidate. They cannot replace the rejected P06 coupon or satisfy any existing Product Truth gate. The fixture ring size and spacing are test-harness dimensions, not modifications to product gauge.

## Files and reproduction

- [experiment.py](experiment.py): operation graph, adversaries, geometry and local measurements.
- [verify_saved.py](verify_saved.py): separate saved-geometry, provenance and assembly-boundary check; reuses the unchanged exact segment-distance instrument, not a wholly separate distance algorithm.
- [result.json](out/result.json), [validation.json](out/validation.json), [operation graph](out/operation_graph.json), [all centerlines/frames](out/geometry.json).
- Per-case JSON contains every frame's clearance and named-target signed passages.
- [diagnostic.svg](out/diagnostic.svg): geometric test-fixture diagram, explicitly not a crochet render.

From repository root with the already available bundled Python:

```powershell
& $v2Python brambleloop/research/visual_v2/pullthrough/experiment.py
& $v2Python brambleloop/research/visual_v2/pullthrough/verify_saved.py
```

A successful runner exit means the instrument experiment behaves as specified. Read structural_truth and the assembly blockers. No new dependency, renderer install, paid call, Build2 test, or historical test rerun is required.

## Next bounded work

Build **one persistent material yarn state** spanning the prior anchor, original live loop, wrap, drawn-up loop, intermediate and new live loop. Each operation must reference material intervals of that same strand; unused working yarn must remain in a measured reservoir/feed ledger. The output of stage1 must be the literal input of stage2, with no ring replacement or unmeasured repositioning.

Start with a single operation handoff and verify material conservation, target passage, collision/clearance and endpoint motion before assembling a whole DC. Actual crochet construction still requires a verified source asset or independent crochet review. Cable target/direction clarification remains unanswered and frozen; it does not prevent this lower-level DC work. Do not add materials/fuzz, shrink yarn, alter gauge, relax thresholds or tile across the full throw to hide these missing construction steps.

Architecture B+C remains recommended but unqualified. Protected composition remains unchanged. All 18-column/540-crossing Product Truth and ownership restrictions remain in force. Paid spend remains **$0**.
