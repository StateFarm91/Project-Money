# Handoff H2: Visual R&D, commercial merchandising objective (D-FB-16 items 4, 5, 6)

Branch `claude/w3-H2` (base `claude/visual-investigation` @ f7003ec). Scope: `visual/rnd/**`.
No edits to `visual/canonical.py`, `visual/assets/**`, `model_photography.py`, `reference_pack.py`, `freeze.py`.
No paid call, no network, no image generation of Laura.

## Requirements and status

| Item | Status | Where |
|---|---|---|
| Objective = intersection of Product Truth + Laura identity + realism/anatomy + brand + desirability + commercial; gates cannot be traded | COMPLETE (code + tests) | `visual/rnd/objective.py` |
| (1) Listing image SEQUENCE policy per class: aspirational hero first, then clarity, dimensions, yarn, charts, construction, skill, colours, verification, contents. Diagrams and engineering renders demoted to evidence, never deleted | COMPLETE as policy + planner + checker | `visual/rnd/sequence.py` |
| (2) Desirability/brand judge interface labelled PROXY: thumbnail desirability, brand palette, blind-benchmark slot (UNKNOWN) | COMPLETE (deterministic proxies) | `visual/rnd/judges.py` |
| (3) Slow loop impressions→CTR→favourites→carts→purchases→conversion→refunds/feedback from K3 `ListingOutcome`; can overturn proxy promotions | COMPLETE in code; carts, refunds and feedback stay UNKNOWN until a writer puts them in `ListingOutcome.detail` | `visual/rnd/commercial.py`, `hero.calibrate` |
| (4) Autonomous hero challengers per class: free deterministic ones run, paid ones queued GATED_SPEND | COMPLETE. Free challengers exist only for coasters (layout) plus the disclosed classes' incumbent; other classes have no free producer, so their hero stays UNKNOWN | `visual/rnd/hero.py`, `loop.cycle(hero=True)` |
| Three-month evolution report in `visual.rnd.status` | COMPLETE: `summary()["evolution"]` and `summary()["commercial"]` | `visual/rnd/evolution.py`, `status.py` |
| Item 6: Laura is centre of brand but not forced into every listing | Encoded in `sequence.CLASS_POLICY` (garments: preferred; baskets/coasters: not_default). The Laura treatment conditions only on canonical references, and the identity gate is hard | `sequence.py`, `hero.py` |

## Runtime proof (executed)
- `hero.challenge` on hexagon coasters: the incumbent render scored 0.8318, the "close" variant 0.8529 and the "airy" variant 0.8235. Every hard gate passed (product_truth, structure, disclosure, mobile_thumbnail). "close" was promoted with basis=proxy. lifestyle_scene and styled_flatlay were queued GATED_SPEND. owned_photo_hero is UNAVAILABLE because no photo exists.
- Synthetic `ListingOutcome` rows showing CTR 0.010 against 0.030 overturned that promotion. The parent hero was restored with basis=market, proxy trust was halved (the required margin doubled to 0.04), and re-promoting the same treatment was refused.

## Tests
- `tests/test_w3_visual_commercial_sequence.py`: 5/5
- `tests/test_w3_visual_commercial_objective.py`: 6/6
- `tests/test_w3_visual_commercial_slowloop.py`: 4/4
- Regression: `test_w3_visual_rnd_guard.py` 6/6, `test_w3_visual_rnd_loop.py` 8/8.

Run: `cd brambleloop && PYTHONPATH=src /home/user/Project-Money/brambleloop/.venv/bin/python tests/<file>`

## WIRING REQUESTS
1. **core.db (lane D)**: import `brambleloop.visual.rnd.models` in `create_all` so the new table `visual_rnd_hero_variants` is created. It is already created lazily by `ensure_tables`.
2. **Listing frame record (lane I, plus K3's `creative.style_learning.listing_styles`)**: the hero frame's style tag must equal `VisualHeroVariant.style_key` (`<class>:<treatment>:<digest8>`). Without it, `ListingOutcome.hero_style` cannot be credited to a hero.
3. **ListingOutcome writer (K3)**: put `carts`, `refunds` and `reviews` into `detail` when the Stats or Orders data carries them. They stay UNKNOWN until then.
4. **publish.eligibility (lane I)**: the sequence slots construction, colours and verification have no eligibility JOB yet (`ELIGIBILITY_JOB` = None). Proposed new jobs: CONSTRUCTION, COLOURWAYS, TRUST.
5. **Brand (lane A)**: export `identity_system.OWNER_CONCEPT_PALETTE`. Until then `judges.brand_palette()` uses a provisional palette sampled from the owner concept images, and the provisional label is shown on every reading.
6. **Runtime (lane D)**: `visual.rnd.cycle` already runs hero calibrate and challenge. `next_work` adds `visual.rnd.hero_calibrate` (72) and `visual.rnd.hero_challenge` (55), both with job_type `visual.rnd.cycle`.

## Not verified / open
- The proxy judges are not calibrated against real buyers. No marketplace data exists, so every promotion so far is PROXY.
- Etsy photo cap: `MAX_FRAMES=10` is conservative and should be verified against current Etsy limits.
- Paid hero challengers (lifestyle, flat-lay, Laura-on-model, seasonal) need owner spend authority. None was executed.
- `owned_photo_hero` needs a real photograph of a made sample.
