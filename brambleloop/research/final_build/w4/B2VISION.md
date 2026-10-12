# W4-B2VISION: Build 2 rows released by the opening of image_vision

Date: 2026-10-12 (UTC). Branch `claude/w4-B2VISION`, from `origin/claude/w4-INTEG2` 85ec5d0.
Domain: Build 2 gate elimination.

**Starting point.** Production opened `image_vision` on 2026-10-12: `vision.probe` was ok at
00:00Z (`GET /api/capabilities/probes`). That moved 14 rows to OPEN-DEFECT in the ledger. The
production runs that followed exposed real defects. They were not data waits. All proofs below
use stub providers, and nothing was spent from here.

## Findings from production (read-only GETs, 2026-10-12)

| Production evidence | Defect | Fix |
|---|---|---|
| `creative.grid_tournament` 2026-10-11T18:05Z | All three judges were sent `/tmp/owned-asset-…/gpt-image-2-….png`. That is the render's path in a container that no longer existed. Every call failed (`ProviderUnusable`), and CA$0.93 bought no reading. The pod "failed" unjudged. | The handler resolves each hero through the artifact store by its digest (`blinded.resolve_image`). An unresolvable render is recorded and never sent. The same fix applies to concept boards. |
| `mjs.seasonal_sentinel` 2026-10-12T00:01Z | Vision was usable and boards were on file, yet nine waiting winners were held with "a vision judgement of the board on file". No `concept.judged` row exists. The same dead board path, so nothing reached `cir.draft` (#277/#281/#309/#88). | `intake.judge_held` now shows the judge the bytes kept under the board's digest. Each held winner now carries the judge's own refusal reason (`judge_said`). |
| `creative.blind_review` 2026-10-12T00:23Z | Every pod read UNKNOWN: "0 judged image(s) … below the floor of 6 images and 3 listings". Gallery vision judges about 4 images per run, and listing-major order spent them on one listing's whole gallery. | `vision.pending(prefer_pods=…)` now drains breadth-first through the pods our catalogue is judged in. `intel.gallery_analysis` passes those pods. |
| #218 dimensions | Desirability, distinctiveness and giftability were unjudged by construction: no reading of our own product existed. | The grid panel's blinded scores are now recorded per product. `blind_review.challenge` reads them, with giftability taken from the gift-buyer judge's desire score. A reading older than 14 days is UNKNOWN. Behind on two of the three returns the product to development. |
| `creative.reference_reading` 2026-10-12T00:24Z | Ran, and stored decompositions for 5 pods. The body names 11 primitives; the store carried 8. | Added `personalization` and `bundle_logic` (both from API option fields and listing structure) and `thumbnail_readability` (from the gallery observation). An absent option block stays absent. |
| `intel.gallery_analysis` 2026-10-12T02:00Z | Judged 4 of 4 images in production (#304 met). | Breadth-first ordering, as above. |

## Rows advanced (registry; ledger regenerated with `build2_ledger.py`)

- **covered:**
  - #67, #218, #126 (blind review and grid)
  - #88, #116 (intake judging, reference primitives)
  - #277, #281, #309 (seasonal capture/response chain, unblocked by the board fix)
  - #304 (met in production)
- **re-parked:** #308 → `model_bearing_render`, which is external. After the intake judgement,
  this is the next binding gate on the cardigan chain (15c5d1b audit). Rendering a model-bearing
  frame of a certified structure is a provider ceiling.
- **next deliverable (same domain):** #15, #44, #86.

## Acceptance evidence

**New test:** `tests/test_w4_b2vision.py`, 7/7. It covers:
- resolving a dead path through the artifact digest;
- the grid handler never sending an unresolvable render and scoring each product;
- the #218 panel reading (behind, level and stale cases);
- breadth-first drain order;
- the 11 #116 primitives;
- the held-board judgement using stored bytes.

**Regression (via `/home/user/bl-runs/testslot.sh`):**
- test_blinded, test_blind_review, test_intel
- test_cert_parity_copy 20/20
- test_cert_preengineering 0 failures
- test_cert_intel_wave2 15/15
- test_fb2_i_repairs
- test_w4_visual_boards 3/3
- test_cert_design_pipeline 17/17
- test_w4_pipe2_candidates
- test_closure, test_w4_b2gates, test_w4_b2_build2_ledger (results appended below)

**Ledger.** Regenerated from production `GET /api/build`, read 2026-10-12T03:35Z
(`evidence_B2VISION/prod_build_2026-10-12.json`), plus the 2026-10-11 derived data gates.
Counts are appended below.

**Production evidence still to come after the next approved deploy.** The fixed handlers record
the first judged grid, the first `concept.judged`, and the first non-UNKNOWN blind review on
their normal cadences. Until then an UNKNOWN still blocks release; that is unchanged.

## Results (appended 2026-10-12)

- **Final regression:** test_closure 27/27, test_w4_b2gates 12/12, test_w4_b2_build2_ledger ALL
  OK, test_cert_design_pipeline 17/17, test_w4_b2vision 7/7, test_w4_pipe2_candidates OK. All
  exit 0, all run through testslot.
- **Ledger** (`BUILD2_LEDGER.json`, as_of 2026-10-12T04:20Z, production reading 03:35Z): PROVEN
  224 (was 215), OWNER-GATED 42, DATA-GATED 41, EXTERNAL-GATED 6 (+#308), NOT-APPLICABLE 3,
  OPEN-DEFECT 4. The 4 remaining OPEN-DEFECT rows:
  - #61 belongs to the image worker, not this lane.
  - #15, #44 and #86 are closed on branch `claude/w4-B2MOAT`.
