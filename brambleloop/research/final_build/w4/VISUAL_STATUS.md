# VISUAL_STATUS — W4-VISUAL (2026-10-07, branch `claude/w4-VISUAL`)

Machine-readable twin: `VISUAL_STATUS.json`. Every status below was measured on this branch
on 2026-10-06/07; nothing is carried over from the dashboard.

## The ladder (visual/milestones.py; owner rule: stop at the first failure)

| Stage | Status | Evidence (measured) | Why not PASS | Next |
|---|---|---|---|---|
| A pattern → deterministic fabric | **PASS** | benchmark cardigan S: 4 components, 0 errors, body 8556 stitches, surface "checkered" | — | — |
| B panels → assembled geometry | **PARTIAL** (DATA-GATED) | 4 pieces placed, 3 of 5 joins checkable, 0 mismatched, silhouette 95.8×64.8 cm | The benchmark is a third-party commercial pattern. It states no neckline length and no pocket placement, so those 2 joins name no edges (`cir/benchmarks.py` notes this). Inventing them would be fabricating benchmark facts. **This does not affect launch products**: every Launch-0 product is one component with no seams, so B has no joins to check for them. | Needs a benchmark that states those measurements, or a Brambleloop garment CIR with named edges (cir/** lane). Not a launch dependency. |
| C object ↔ benchmark photographs | **PARTIAL** (DATA-GATED) | 11 correspond, 0 contradict, 3 not observable | Pocket placement (unstated), individual stitch identity (listing photos do not resolve stitches), drape (no mechanics claimed). None is contradicted. | Needs close-up photography of a worked sample. Not a launch dependency. |
| D realistic presentation, no drift | **PARTIAL** (dashboard said FAIL; that reading is stale) | `milestone_d.assess('hdc')` run 2026-10-06: 10 PASS, 0 FAIL, 9 UNKNOWN. Structural locks all PASS: stitch identity, certified flat, rigidity provenance, equilibrium (5.7e-15 mm), energy descends, contact, no drift, double curvature, render uses validated geometry | 2 UNKNOWNs are local: `stationary` (motion still 3.9% in the last tenth of the solve; needs <2%) and `images_rendered` (no render directory was passed). 7 UNKNOWNs are photograph judgements (`d_judge`, a paid gpt-5 vision call). UNKNOWN is never PASS. | Local re-run with momentum-off settle and Mitsuba renders: see `d_rerun` in the JSON. Then judging under owner spend approval (plan P1). |
| E listing asset clears every floor | **NOT_STARTED** for photographic assets; disclosed path is **live** | Photographic E waits on D. The D-FB-7 route (disclosed deterministic renders, where truthful imagery is required and photorealism is not) covers all 3 Launch-0 listings: hero/scale/detail verified PASS on every variant | Photographic realism has no judged frame. Owned photography: 0 accepted (no sample photographs on file). | P2 (lifestyle composites) or a physical sample photo session. |

## Launch-0 imagery (what the listings actually need)

Produced by `visual/launch_imagery.py` (all disclosed and deterministic, $0). Every frame is
verified on its bytes: disclosed renders by `render_verification`, gallery frames by an
independent re-derivation of their facts plus an identical redraw (`visual/gallery_frames.verify`).

| Listing | Variants | Hero | Jobs covered (K1, F-030/F-254) | Missing → blocker |
|---|---|---|---|---|
| nursery-nesting-baskets | S/M/L, each with disclosed hero/scale/detail PASS | **ready** | DESIRE, SCALE, DETAIL, MATERIALS, COLOUR_CONTEXT, CONSTRUCTION, SIZING | ANGLE (needs a verifier-measured projection; engineering), CONTENTS (PDF preview path, publish.pdf), LIFESTYLE (photo or paid composite) |
| cloudline-baby-blanket | 1 | **ready** | DESIRE, SCALE, DETAIL, MATERIALS, COLOUR_CONTEXT | CONTENTS, LIFESTYLE |
| hexagon-coaster-set | 1 | **ready** | DESIRE, SCALE, DETAIL, MATERIALS, COLOUR_CONTEXT (+ CONSTRUCTION as a supporting frame) | CONTENTS, LIFESTYLE |

Not in launch scope: `harvest-table-runner`. It is in `launch0.BUILDERS` but not in
`LAUNCH0_SLUGS`, and the renderer refuses it because its gold yarn is 39.4 RGB from its own
raised tone, inside the contract's 40 minimum separation. Left refused. A palette change is a
product decision, and a contract change is the integrator's call.

## Visual R&D loop (shadow, local sqlite; `visual.rnd.loop.cycle` ×2)

- 14 experiments over 8 classes: 1 PROMOTED (coasters `hero_gap_ratio` 0.18→0.06; hero
  prominence 0.6256→0.7238), 5 REJECTED, 8 GATED_SPEND (never executed).
- 6 lessons persisted (encode_png_level 6 and post_grain_sigma 1.5 rejected for baskets and
  blankets; hero_gap 0.0 rejected for coasters).
- Hero challengers on coasters: `disclosed_finished_render_close` 0.8425, `_airy` 0.8134,
  both accepted. Lifestyle and flat-lay heroes are queued behind spend.
- Status provider: DEGRADED. 5 of 8 classes have no free producer, and there is no marketplace
  evidence because there are no live listings.
- `cycle()` now also refreshes the Launch-0 imagery ledger (registered as `assets.gallery_frames`).

## Owner-ready costed plans (not executed; no paid call made)

| Plan | Provider/model | Calls | Max CA$ | Unlocks |
|---|---|---|---|---|
| P1 D photograph judging | gpt-5-2025-08-07 (`d_judge`, worst case US$0.045/call) | ≤16 (4 renders × up to 4 attempts) | **1.00** | D's 7 judged items. D becomes PASS or FAIL, and the result is then measured |
| P2 LIFESTYLE protected composites, 3 Launch-0 listings | flux-2-pro (US$0.02/image) for background + realism judge | 12 generations + 12 judgements | **2.00** | LIFESTYLE job on all 3 listings and the first E candidate. Product pixels are preserved and verified by `visual.compose.verify`, and the frames are disclosed |
| P3 R&D GATED_SPEND queue, launch classes only (coasters, baskets, blankets) | cheapest listed (flux-2-pro), 6 images × 2 arms | 36 | **1.01** (3 × 0.3357) | first judged photographic challenger per launch class |
| Alt (no API spend) | physical sample photo session | — | yarn ≈ CA$30 (estimate) | LIFESTYLE + owned-photography hero + C/D ground truth |
