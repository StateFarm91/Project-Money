# VISUAL_STATUS — W4-VISUAL (2026-10-07T01:45Z, branch `claude/w4-VISUAL`)

Machine-readable twin: `VISUAL_STATUS.json`. Every status below was measured on this branch
on 2026-10-06/07; nothing is carried over from the dashboard.

## The ladder (visual/milestones.py; owner rule: stop at the first failure)

| Stage | Status | Evidence (measured) | Why not PASS | Next |
|---|---|---|---|---|
| A pattern → deterministic fabric | **PASS** | benchmark cardigan S: 4 components, 0 errors, body 8556 stitches, surface "checkered" | — | — |
| B panels → assembled geometry | **PARTIAL** (DATA-GATED) | 4 pieces placed, 3 of 5 joins checkable, 0 mismatched, silhouette 95.8×64.8 cm | The benchmark is a third-party commercial pattern. It states no neckline length and no pocket placement, so those 2 joins name no edges (`cir/benchmarks.py` notes this). Inventing them would be fabricating benchmark facts. **This does not affect launch products**: every Launch-0 product is one component with no seams, so B has no joins to check for them. | Needs a benchmark that states those measurements, or a Brambleloop garment CIR with named edges (cir/** lane). Not a launch dependency. |
| C object ↔ benchmark photographs | **PARTIAL** (DATA-GATED) | 11 correspond, 0 contradict, 3 not observable | Pocket placement (unstated), individual stitch identity (listing photos do not resolve stitches), drape (no mechanics claimed). None is contradicted. | Needs close-up photography of a worked sample. Not a launch dependency. |
| D realistic presentation, no drift | **PARTIAL** (EXTERNAL-GATED on judge spend; the dashboard FAIL is stale) | `milestone_d.assess('hdc', settle_iterations=4000)` with Mitsuba 3.9.1 renders, 2026-10-07: **12 PASS, 0 FAIL, 7 UNKNOWN**. `stationary` now PASS (0.52% change over the last tenth, needs <2%; 7200 iterations). `images_rendered` now PASS (flat/draped × camera/oblique, 4 plies, bound to geometry sha256). Artefact `visual/milestone_d_hdc_2026-10-07.json` | All 7 UNKNOWNs are photograph judgements (`d_judge`, a paid gpt-5 vision call). UNKNOWN is never PASS. | Owner decision VB-1, item P1 (CA$1.00) |
| E listing asset clears every floor | **NOT_STARTED** for photographic assets; disclosed path is **live** | Photographic E waits on D. The D-FB-7 route (disclosed deterministic renders, where truthful imagery is required and photorealism is not) covers all 3 Launch-0 listings: hero/scale/detail verified PASS on every variant | Photographic realism has no judged frame. Owned photography: 0 accepted (no sample photographs on file). | P2 (lifestyle composites) or a physical sample photo session. |

## Launch-0 imagery (what the listings actually need)

Produced by `visual/launch_imagery.py` (all disclosed and deterministic, $0). Every frame is
verified on its bytes: disclosed renders by `render_verification`, gallery frames by an
independent re-derivation of their facts plus an identical redraw (`visual/gallery_frames.verify`).

| Listing | Variants | Hero | Jobs covered (K1, F-030/F-254) | Missing → blocker |
|---|---|---|---|---|
| nursery-nesting-baskets | S/M/L, each with disclosed hero/scale/detail PASS | **ready** | DESIRE, SCALE, DETAIL, MATERIALS, COLOUR_CONTEXT, CONSTRUCTION, SIZING, **ANGLE** (new: verified 50° view showing the inside and base) | CONTENTS (PDF preview path, publish.pdf), LIFESTYLE (photo or paid composite) |
| cloudline-baby-blanket | 1 | **ready** | DESIRE, SCALE, DETAIL, MATERIALS, COLOUR_CONTEXT | CONTENTS, LIFESTYLE |
| hexagon-coaster-set | 1 | **ready** | DESIRE, SCALE, DETAIL, MATERIALS, COLOUR_CONTEXT (+ CONSTRUCTION as a supporting frame) | CONTENTS, LIFESTYLE |

Not in launch scope: `harvest-table-runner`. It is in `launch0.BUILDERS` but not in
`LAUNCH0_SLUGS`, and the renderer refuses it because its gold yarn is 39.4 RGB from its own
raised tone, inside the contract's 40 minimum separation. Left refused. A palette change is a
product decision, and a contract change is the integrator's call.

## Vessel ANGLE view (new, PROVEN)

`disclosed_render` view `angle` (vessels only, `render_contract.ANGLE_DEG` = 50°). The
`render_verification` module measures it with the same un-projection it uses for the hero:
stitch counts, colour placement, wall height and extent. Flat and plan-form products refuse
the view. A frame verified at the wrong camera angle, or with a recoloured round, does not
pass. Tests: `tests/test_w4_visual_angle.py`, 5/5 passing.

## Concept boards (shared with CREATIVE): defect fixed

`creative.board.make_board` drew every concept from a design-blind prototype, a single-colour
fabric corner, so 5 catalogue designs had byte-identical boards. A judgement bound to the
board digest would have judged none of them. A catalogue design is now drawn from its own
verified disclosed hero. An undrawable design gets no board (fail closed). Of the 6 creative
survivors, 3 have boards (cloudline-baby-blanket, mosaic-placemat-pair,
valentine-heart-garland). The other 3 have none, because the palette is too close to a
contract colour (harvest-table-runner, spooky-garland, pet-snuggle-mat). Tests:
`tests/test_w4_visual_boards.py`, 3/3 passing.

## Visual R&D loop (shadow, local sqlite; `visual.rnd.loop.cycle` ×3)

- 17 experiments: 1 PROMOTED (coasters `hero_gap_ratio` 0.18→0.06; prominence
  0.6256→0.7238; the cycle-3 monitor retained it), 8 REJECTED, 8 GATED_SPEND (never
  executed). 9 lessons persisted.
- Cycle 3 refreshed the Launch-0 imagery ledger through the scheduled path (method
  `disclosed-angle/1`), and baskets gained ANGLE.
- Status provider: DEGRADED. 5 of 8 classes have no free producer, and there is no
  marketplace evidence.

## Owner decision VB-1: one approval covers Visual and Creative (not executed; CA$0 spent)

**Ask:** approve one vision bundle with a ceiling of **CA$4.76**. The existing budget
reservations enforce it. About 5 owner minutes.

| Item | Provider/model | Calls | Max CA$ | Unlocks |
|---|---|---|---|---|
| V0 vision probe + concept-board judging | claude-haiku-4-5 probe (~0.009/call), claude-sonnet-5 judge (~0.03/board) | 3 probes, 11 boards ×2 | **0.75** | `vision_usable` is the precondition for: CREATIVE `needs_taste` judged on the 3 boards now (8 more once W4-PIPE writes CIRs), and MJS gallery analysis restarting (stalled since 09-24). Prereq: a working, funded production Anthropic credential. Why the probe fails in production is not verified from this lane |
| P1 D photograph judging | gpt-5 via `d_judge` | ≤16 | **1.00** | D's 7 judged items, so D becomes a measured PASS or FAIL |
| P2 LIFESTYLE protected composites | flux-2-pro + realism judge | 24 | **2.00** | LIFESTYLE on all 3 listings, and the first photographic E candidate |
| P3 R&D gated queue (launch classes) | flux-2-pro | 36 | **1.01** | first judged photographic challenger per class |
| Alt (no API spend) | physical sample photo session | — | yarn ≈ 30 (estimate) | LIFESTYLE, an owned hero, and C/D ground truth |

If the owner waits: D stays PARTIAL, photographic E is not started, all 3 listings lack
LIFESTYLE, creative survivors cannot clear `needs_taste`, and MJS gallery analysis stays
stalled.

