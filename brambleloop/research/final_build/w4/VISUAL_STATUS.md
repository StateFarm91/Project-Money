# VISUAL_STATUS — W4-VISUAL/VISUAL2 (updated 2026-10-07T12:00Z, branch `claude/w4-VISUAL2`)

**2026-10-07 update (W4-VISUAL2):** CONTENTS is now PROVEN on every certified gallery (`visual/contents_frame.py`, preview of the release's real US PDF, verified on exact bytes). harvest-table-runner is now certified: hero/scale are drawn on the contract diagonal (`render_contract.diagonal_deg`) and verified un-rotated; the 25 % fill gate is unchanged; Launch-0 frames are byte-identical. Proof: `visual/contents_gallery_proof_all_2026-10-07.json` (runner, blanket, basket S/M/L, pet mat: certificate valid, upload path serves DESIRE..CONTENTS, first_customer PASS). K9 F-753: generated frames carry a stitch-scale reading (`product_authority.structural_floor`). Rows below that say CONTENTS missing or the runner refused are superseded by this paragraph. LIFESTYLE stays OWNER-GATED. Assembled multi-piece hero/scale (W4-RENDER) are now measured (`render_verification._verify_assembled`): first-christmas-stocking and mothers-day-heart-tea-cosy PASS; teacher-chevron-pencil-roll FAILs the unchanged 25 % fill gate at 340 px.

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

## Certified gallery (F-030 / F-254): the verified frames are now in the listing-set certificate

Before this change the gallery frames existed, but no certificate carried them, so
`search_evidence.gallery` still read the certified set as hero/scale/detail only. Now
`release_gates.disclosed_supplements` offers each verified frame to `listing_set.certify_disclosed`
as kind `disclosed_gallery_frame`, at positions after the disclosed set. A frame is offered only
when all of these hold:
- it is re-rendered from the certified CIR, and its bytes are identical;
- it re-verifies on those bytes (`launch_imagery.check_supplement`);
- it passes `layout_qa.inspect` (text expected);
- it is bound to the release CIR fingerprint.

Its readings are ANDed into DATA_TRUTH, LAYOUT_QA and COMMERCIAL_QA, never replacing the set's
own. The upload path (`etsy_ops.certified_images`) re-verifies each frame on its bytes and checks
its alt text (disclosure first). `first_customer.disclosed_imagery` still requires the disclosed
set exactly, and re-verifies any further frame. The MATERIALS card read 95% background, which
layout QA refused as FRAME_FLAT, so it was recomposed (`gallery-frames/1.1.0`). No threshold
was changed.

Shadow runtime proof (real `gate.certify` and `assets.build` handlers, then
`release_gates.listing_set`, then the upload path, with sockets refused). Artefacts:
`visual/certified_gallery_proof_2026-10-07.json` and `..._baskets_2026-10-07.json`.

| Product (release slug) | Certificate | Frames served by upload path | Certified jobs | Still missing → gate |
|---|---|---|---|---|
| market-basket-small | valid | 8 | DESIRE SCALE DETAIL ANGLE CONSTRUCTION COLOUR_CONTEXT SIZING MATERIALS | CONTENTS, LIFESTYLE |
| market-basket-medium / -large | valid | 7 each | as small, without SIZING (each sells one size) | CONTENTS, LIFESTYLE |
| cloudline-baby-blanket | valid | 5 | DESIRE SCALE DETAIL COLOUR_CONTEXT MATERIALS | CONTENTS, LIFESTYLE |
| hexagon-coaster-set | valid | 5 | same | CONTENTS, LIFESTYLE |
| **pet-snuggle-mat** (new) | valid | 5 | same | CONTENTS, LIFESTYLE |
| **harvest-table-runner** | **refused** | 0 | (COLOUR_CONTEXT and MATERIALS verified; hero not usable) | hero and scale fail 340 px legibility (product fills 13–14%; the gate needs 25%). A 32×122 cm runner is 3.8:1, which reads as a thin strip in a square frame. **OPEN, company engineering**: a diagonal or folded hero layout, with the matching verifier un-projection. The gate is not loosened and the frame is not padded. |

What unblocked pet-snuggle-mat and harvest-table-runner's renders:
- `render_contract.relief`: gold #C49545 sat 39.4 RGB from its own raised tone. A tone inside
  MIN_SEPARATION now steps 5% further. The minimum stays at 40, and Launch-0 tones are
  byte-identical (tested).
- `render_verification.authoritative_cir` now also answers from the engineered design registry
  (`pipeline._engineered_cir`), at the builder's released version only. This applies D-FB-7 to
  every product with a defined design, not to Launch-0 alone. Launch scope itself is unchanged.
- `listing_asset.has_render_authority` replaces the Launch-0-only gate for disclosed renders.

Status of the gallery rows:
- F-030 / F-254: the applicable drawable jobs are certified on all 6 renderable viable releases.
- CONTENTS has no producer yet. It is open company work: a PDF-page preview frame from
  `publish.pdf`.
- LIFESTYLE is OWNER-GATED: VB-1 P2, or physical sample photographs.
- Caveat for the integrator: `commerce.search_evidence._category_for` hard-codes sizes=1 and
  colours=1. That under-counts applicable jobs; see wiring request 7.

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
contract colour (harvest-table-runner, spooky-garland, pet-snuggle-mat). (Update 05:30Z: the relief-tone fix makes gold palettes renderable, and pet-snuggle-mat now has a verified hero. The boards have not been regenerated in this pass.) Tests:
`tests/test_w4_visual_boards.py`, 3/3 passing.

## Visual R&D loop (shadow, local sqlite; `visual.rnd.loop.cycle` ×3)

- 17 experiments: 1 PROMOTED (coasters `hero_gap_ratio` 0.18→0.06; prominence
  0.6256→0.7238; the cycle-3 monitor retained it), 8 REJECTED, 8 GATED_SPEND (never
  executed). 9 lessons persisted.
- Cycle 3 refreshed the Launch-0 imagery ledger through the scheduled path (method
  `disclosed-angle/1`), and baskets gained ANGLE.
- Status provider: DEGRADED. 5 of 8 classes have no free producer, and there is no
  marketplace evidence.

## Owner decision VB-1: the single costed plan for paid vision and generation (not executed; CA$0 spent)

Reconciled with W4-GATESI (`GATE_CLEARANCE_INFRA.md` on `origin/claude/w4-GATESI`). There are
three owner actions, in this order. Budget reservations (`visual.spend_plan.guard`) and the code
cap of CA$100/month enforce every ceiling.

| # | Owner action | Provider | Max CA$ | Minutes | Opens / unlocks |
|---|---|---|---|---|---|
| 1 | Top up Anthropic credits (console → Billing). This is OWNER_ACTIONS `fund_model`. | Anthropic | min US$5 (≈6.85); CA$25 recommended | 5 | `model_provider` **and** `image_vision` (one balance). The production probes at 00:01Z and 00:03Z failed with "credit balance is too low". |
| 2 | Deploy W4-GATESI (fixes the `image.probe` work_dir defect). This goes in the CC deploy package and needs no spend. | — | 0 | 0 | `image_generation` evidence gate (flux-2-pro / gpt-image-2 / nano-banana-2 are credentialled; the BFL balance stays UNKNOWN until the probe runs) |
| 3 | Approve VB-1 spend, ceiling **CA$4.76**: V0 0.75 + P1 1.00 + P2 2.00 + P3 1.01 | see rows | 4.76 | 3 | see rows |

| Item | Provider/model | Calls | Max CA$ | Unlocks |
|---|---|---|---|---|
| V0 vision probe + concept-board judging | claude-haiku-4-5 probe (~0.009/call), claude-sonnet-5 judge (~0.03/board) | 3 probes, 11 boards ×2 | **0.75** | CREATIVE `needs_taste` judged; MJS gallery analysis restarts. Needs action 1 |
| P1 D photograph judging | gpt-5-2025-08-07 via `d_judge` (**OpenAI** key, not Anthropic; OpenAI credit balance UNKNOWN) | ≤16 | **1.00** | D's 7 judged items → D measured PASS or FAIL |
| P2 LIFESTYLE protected composites | flux-2-pro + realism judge | 24 | **2.00** | LIFESTYLE on the Launch-0 listings, plus the first photographic E candidate. Needs action 2 |
| P3 R&D gated queue (launch classes) | flux-2-pro | 36 | **1.01** | first judged photographic challenger per class. Needs action 2 |
| Alt (no API spend) | physical sample photo session | — | yarn ≈ 30 (estimate) | LIFESTYLE, an owned hero, and C/D ground truth |

OWNER_ACTIONS `visual_paid_generation` lists CA$4.01, which is P1+P2+P3. V0's CA$0.75 runs on
the Anthropic balance and is inside the same VB-1 ceiling. The two numbers describe the same
plan.

If the owner waits:
- D stays PARTIAL (7 UNKNOWN).
- LIFESTYLE stays missing on every listing, so F-030/F-254 keep one OWNER-GATED job.
- Creative survivors cannot clear `needs_taste`.
- MJS gallery analysis stays stalled.
