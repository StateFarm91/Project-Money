# Independent security and visual-truth review: W4-PDF1 soft-corner render (38c16035)

- **Reviewer:** an independent Claude Code session on branch `claude/w4-SECREVIEW-RENDER-38c1603`. It did not author the change.
- **Subject:** `git diff 4fb6252d..38c16035` on `claude/w4-PDF1`.
- **Release:** `market-basket-small@1.3.0`, release hash `c4aa14a000e5…`.
- **Date:** 2026-10-31 (UTC).
- **Method:** a detached worktree at 38c16035 and another at 4fb6252d. Every number below was re-measured from bytes in this session; none was copied from the author's evidence.

## Verdict: **DO NOT SHIP (as is)**. The fix is small; see F1 and F2.

The code change is sound:
- the verifier was not loosened;
- other products are byte-identical;
- the version linkage is correct.

The block is about **truth**:
- the softened rim is a guessed shape;
- the change also widens the rim across the flats, which contradicts the construction review it cites;
- the one caption that told the buyer the picture is an approximation was deleted.

Restoring a reworded caption (F1) is enough to ship. F2 should be fixed or disclosed.

## Findings

| # | Severity | Finding |
|---|---|---|
| F1 | **HIGH (blocking)** | The caption was removed for a shape that has not been measured |
| F2 | **MEDIUM** | The model widens the rim across the flats by about 1.06 cm; the cited review says the flats stay about 13.9 cm, and nothing checks the flats |
| F3 | MEDIUM | `rim_corners_cm` can tell "soft" from "prism", but cannot confirm 0.75; the prism margin is thin |
| F4 | LOW | `RENDERER_VERSION`, `VERIFIER_VERSION` and `CONTRACT_VERSION` were not bumped, although output and semantics changed |
| F5 | LOW | The cited source, "CONSTRUCTION_REVIEW_basket §1.3", is not on this branch |
| F6 | LOW | Page 3 still says "rise straight up" next to a schematic whose corners lean in |
| F7 | INFO | The required dependencies `scipy` and `sqlalchemy` were missing from this container. Without scipy, every verification returns UNKNOWN |

### F1: HIGH. The idealised caption was removed for an unmeasured shape

`pdf._render_gap` now returns `None` whenever `rim_softening(cir) > 0`. Its comment says "The renders draw this wall as the pattern makes it", so "there is no gap to caption". That claim is not supported:
- `render_contract.py` itself says `0.75 is a modelling figure … to be replaced by the first physical sample's rim measurement`.
- The cited review (`CONSTRUCTION_REVIEW_basket_small_1.2.0.md` §1.3, on `origin/claude/w4-CONSTRUCTREVIEW-basket`) says only that the rim "relaxes towards a rounded hexagon" and "tends from 16.0 cm towards the 15.3 cm circle figure". It gives no magnitude, and no sample exists.

So the renders went from "an idealised prism, disclosed" to "an estimated shape, undisclosed". The listing disclosure still says "Every stitch in it is drawn from the pattern itself at the stated gauge". The corner softening is not drawn from the pattern; it is a heuristic weight. That breaks the non-negotiable "never claim … until verified".

**Fix (cheap):** keep the soft-corner render, which is closer to the truth than the prism, but replace the deleted caption rather than return `None`. For example: *"The rim is drawn with its corners softening toward a rounder outline, as this construction tends to; how far they soften depends on your tension and has not yet been measured on a made sample."* Then flip the pinning assertion in `test_pdf_premium.test_the_basket_does_not_promise_a_crease…` from "`idealised` absent" to "the rim-estimate caption present".

### F2: MEDIUM. The model widens the rim across the flats, contradicting the review

`wall_outline` moves *every* point radially toward the circle with the same perimeter. With R = 8.0 cm, a = 6.93 cm, Rc = 3R/π = 7.64 cm and w = 0.75 at the rim:

| At the rim | Review (§1.3 table) | Drawn (w = 0.75) |
|---|---|---|
| Across the points | "tends from 16.0 towards 15.3" | 15.46 cm (verified) |
| Across the flats | "stays about 13.9 cm" | **14.92 cm** (+1.06 cm, +7.7 %), **not verified** |

The renderer's own comment confirms the widening: "A softened wall … bows its mid-faces outward toward the rim". The frame is resized to fit it.
- The hero view shows it plainly: the rim reads as a near-round, flared opening wider than the hexagonal foot (`hero` compared with `hero_prism`).
- `rim_corners_cm` measures across the points only, so no check covers the 14.92 figure.
- The scale frame, page 3 and the listing state "13.9 cm across the flats". The caption says that figure is for the *base*, so it is not false, but the picture above it shows a rim about 1 cm wider.

Whether constant-perimeter widening or the review's "flats stay" is physically right is exactly the open question that 0.75 stands in for. Either:
- (a) model only corner pull-in, keeping the apothem, which is what the review describes; or
- (b) keep this model and add an across-the-flats check plus the F1 disclosure.

### F3: MEDIUM. What `rim_corners_cm` can and cannot prove

**Sweep.** I rendered the basket at softening w, verified it against the contract's 0.75, and cleared the verifier's cache before each run:

| w drawn | hero | scale | angle | rim measured / expected (hero) |
|---|---|---|---|---|
| 0.0 (old prism) | FAIL rim | FAIL rim | FAIL rim+counts | 15.99 / 15.48 |
| 0.2 | FAIL rim | FAIL rim | FAIL | 15.82 / 15.48 |
| 0.3 | PASS | PASS | FAIL (height) | 15.76 / 15.48 |
| 0.4 | PASS | PASS | FAIL (height) | 15.70 / 15.48 |
| 0.5 | PASS | PASS | PASS | 15.63 / 15.48 |
| 0.6 | PASS | PASS | PASS | 15.57 / 15.48 |
| **0.75 (shipped)** | PASS | PASS | PASS | 15.46 / 15.48 |
| 0.9 | PASS | PASS | FAIL (counts) | 15.35 / 15.48 |
| 1.0 | FAIL rim | PASS | FAIL (counts) | 15.16 / 15.48 |

- The verifier accepts any softening from about 0.5 to 0.75 on every view, and from 0.3 to 0.9 on hero and scale. That is expected: the whole prism-to-0.75 difference is 0.51 cm, against a ±2 % (0.31 cm) tolerance.
- So the check proves "corners are drawn soft". It does not prove "softened by 0.75", and it cannot prove anything about the real product (F1).
- **Mutation margin.** The prism is killed only while `EXTENT_REL` is below about 3.3 %.

**Mutation results** on `test_pdf_premium.test_the_basket_render_draws_soft_corners_and_the_old_prism_fails_verification`, with the cache cleared each time:

| Mutation | Result |
|---|---|
| none | test passes |
| skip `rim_corners_cm` (forced PASS) | **killed** (the hero prism passes) |
| `EXTENT_REL` 0.02 → 0.04 | **killed** |
| `EXTENT_REL` 0.02 → 0.03 | **survives** (thin margin) |
| verifier ignores softening (`rim_softening` → 0 in the model) | **killed** |

**Tolerances: not loosened.**
- `EXTENT_REL/PX` and `HEIGHT_REL/PX` are unchanged.
- The wall-height pixel floor is now divided by the softened un-projection `k`, not by cos α. In cm that is ×1.029 (hero) and ×1.079 (angle), but it is still exactly 4 screen px, which is the correct conversion.
- On straight prisms `ws = 0`, so `k = cos α` and the central-column top equals the old minimum: the behaviour is identical.

**Circularity.** The renderer and the verifier both read `K.rim_softening`, so the verifier confirms *render = contract*, not *render = twin*. The twin has no softening. The verifier can therefore pass a render that does not match the twin's straight prism, by design. This is acceptable only as long as F1 discloses that the contract's rim is an estimate.

**Test-harness note.** `render_verification.verify` memoises results by `(VERIFIER_VERSION, png sha, cir fingerprint, view)`. Any in-process mutation test must call `V._VERIFIED.clear()`, or the mutants return the cached verdict and *all appear to survive*. My first mutation run showed exactly that.

### F4: LOW. Versions were not bumped

`RENDERER_VERSION = "disclosed-render/3.0.0"`, `CONTRACT_VERSION = "disclosed-render-contract/3"` and `VERIFIER_VERSION = "render-verification/3.0.0"` are all unchanged.
- **Renderer.** For the same CIR fingerprint, renderer 3.0.0 now produces different hero, scale and angle bytes than it did at 4fb6252d. A manifest stamped "3.0.0" no longer identifies which drawing it is.
- **Verifier.** It added a check and changed un-projection under the same version, and that version is part of its cache key.

**Recommendation:** bump all three, and re-run the chain.

### F5: LOW. The cited source is absent

The source cites "CONSTRUCTION_REVIEW_basket §1.3". That document exists only on `origin/claude/w4-CONSTRUCTREVIEW-basket` (`CONSTRUCTION_REVIEW_basket_small_1.2.0.md`), so a reader of this branch cannot check the claim.

Note also that the review is of **1.2.0**. It predicts the rim behaviour, which 1.3.0's back-loop Rnd 11 does not change, because the wall still has no corner stitch. Applying it to 1.3.0 is reasonable, but it should be said.

### F6: LOW. "Rise straight up" on page 3

Page 3 says "rounds 11 to 22 keep that count and rise straight up to make the wall". The review flagged this phrase for 1.2.0. With back loop only, it is fair for the fold, but it now sits beside renders whose corners visibly lean in toward the rim.

### F7: INFO. Environment

`scipy` and `sqlalchemy`, both in `requirements.txt` and `requirements.lock`, were not installed in this container. Without scipy, `verify()` fails closed to UNKNOWN on every frame, which is correct fail-closed behaviour. I installed `scipy==1.17.1` from the lock file and the rest of `requirements.txt` before running anything below.

## Q2: Other products

I rendered every `launch0.BUILDERS` product × {hero, scale, angle, detail} (44 frames) at 4fb6252d and at 38c16035 and compared the SHA-256 hashes:
- **Only `basket_small/hero`, `/scale` and `/angle` changed.**
- `basket_small/detail` is unchanged (`a2010fcd…`).
- All other 40 frames are byte-identical, including 7 identical refusals.

Other hexagon vessels pass for the right reason: `rim_corners_cm` measures 2R exactly on a straight prism.

| Product | View | Extent | Rim corners (measured / expected) | Height | Verdict |
|---|---|---|---|---|---|
| basket_medium 1.2.1 | hero | 20.77/20.8 | 20.77/20.8 | 15.91/15.94 | PASS |
| basket_medium 1.2.1 | scale | 20.77/20.8 | 20.77/20.8 | 15.91/15.94 | PASS |
| basket_medium 1.2.1 | angle | 20.76/20.8 | 20.76/20.8 | 15.90/15.94 | PASS |
| basket_large 1.2.1 | hero | 25.6/25.6 | 25.6/25.6 | 23.16/23.19 | PASS |
| basket_large 1.2.1 | scale | 25.55/25.6 | 25.55/25.6 | 23.14/23.19 | PASS |
| basket_large 1.2.1 | angle | 25.53/25.6 | 25.53/25.6 | 23.11/23.19 | PASS |

The round `key_basket` (sides 0) takes the round-vessel path, untouched. `hexagon_coasters` is flat.

**Gap:** the `construction_diagrams` change was not separately byte-compared for other products. `wall_outline` returns `_path` unchanged when w = 0, so by inspection there is no effect; `test_deliverable_qa` covers the PDFs (results below).

## Q4: Version linkage

The six listing assets in the chain evidence are all `version: 1.3.0`, `approved: 1`, `blocked_reasons: []`. Their hashes are **unchanged** from before the render change, and that is correct:
- position 1 is the top-down `render_round_fabric` hero, not the 3D disclosed render (`listing_assets._hero`);
- the others are infographics, a preview and a chart.

The listing-set certificate is `state: valid` at `release_hash c4aa14a0…`, version 1.3.0, with all four gates passed. Its eight frames, checked against bytes I rendered independently at 38c16035:

| # | Frame | Certificate SHA-256 | Independently rendered | Match |
|---|---|---|---|---|
| 1 | disclosed hero | `f5ff019b…` | `f5ff019b78c3dc1f` | ✅ |
| 2 | disclosed scale | `3189554b…` | `3189554b2537d854` | ✅ |
| 3 | disclosed detail | `a2010fcd…` | `a2010fcd661eb2bf` | ✅ |
| 4 | gallery angle | `d62a93d9…` | `d62a93d9a0513913` | ✅ |
| 5 | gallery construction | `cf85fb50…` | not re-rendered | n/a |
| 6 | gallery colour_context | `803bac30…` | not re-rendered | n/a |
| 7 | gallery materials | `31b76a7c…` | not re-rendered | n/a |
| 8 | gallery contents | `ed69e7f1…` (changed, embeds thumbnails) | not re-rendered | n/a |

- The PDFs carry "version 1.3.0" and `market-basket-small@1.3.0` in the header and footer of every page I inspected (1, 3, 7 and 12).
- **Caveat:** the evidence is from a scratch SHADOW run, and its own caveat says production must re-render. The certificate is valid for these bytes. Given F4, a re-render under bumped versions should re-issue it.

## Q3: Visual inspection (hero, angle, scale, detail; PDF pages 1, 3, 7, 12)

- **Hero:** the base front reads as a hexagon; the rim reads as a nearly round, slightly flared opening (F2). The old prism reads as a crisp hexagonal tub.
- **Angle:** plausible; the back rim is rounded and the front lower faces are flat.
- **Scale:** the side silhouette leans inward slightly toward the rim, and the edge stitch columns are visibly sheared. This is cosmetic.
- **Detail:** unchanged.
- **Page 1:** the cover is the soft hero.
- **Page 3:** schematic plus "rise straight up" (F6).
- **Page 7:** construction-stage thumbnails; the stage outlines are drawn as a fraction of the finished wall, as specified.
- **Page 12:** gallery. There is **no "idealised" caption anywhere** (F1).

## Tests

Each was run one at a time as `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>.py` at 38c16035.

TESTS_PENDING
