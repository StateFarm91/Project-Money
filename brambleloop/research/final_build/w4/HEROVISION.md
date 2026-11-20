# HEROVISION: parity HERO judged for the disclosed hero (F-253; F-027/F-031 on the D-FB-7 path)

Branch `claude/w4-HEROVISION`, built on `claude/w4-FIRSTIMG`. It uses `inspect.identification`
and `identify_at_grid`, so **merge FIRSTIMG first**. Shadow only: no spend, and stub providers
in the tests.

## The defect

`visual.parity` HERO reads `inspection.semantic.finished_or_in_progress_agrees`. No producer
ever wrote that key: `inspect.compare` returned only `communicates/problems`. On top of that,
the disclosed renders every Launch-0 listing carries were never described at all. As a result,
parity HERO was unjudged for every product, whether or not `image_vision` was open, and
F-253's "parity HERO judgement" could never close.

## The fix

- `inspect.compare` now writes two readings:
  - `finished_or_in_progress_agrees`: True, False, or None when unclear or not claimed.
  - `identified`: the CIR's product family, None when there is nothing to compare.
- `inspect.describe_image` is a blind description in one call, with no realism call (D-FB-9:
  a disclosed render says it is not a photograph). It goes through the same budget guard as
  `inspect_image` (agent `quality_director`, purpose `asset_inspection`, reserve → release).
- `visual.hero_review.review_disclosed_hero` runs only while `image_vision` is open.
  - It describes the usable disclosed hero's exact stored bytes against the hero claim plus
    the product families, and adds the 230 px grid reading (F-031).
  - It files the result as `visual.hero_review`, bound to the frame's sha256.
  - `latest_for` returns a review only for those exact bytes.
- Wiring:
  - `disclosed_listing.frames_with_presentation` attaches the review to the hero frame.
  - `release._disclosed_render_set` runs the review after filing a set and audits
    `assets.disclosed_hero_review`. When the gate is closed, nothing is called.
- Parity HERO now applies these rules:
  - It fails when `identified` is False.
  - It stays unjudged when `identified` is None.
  - It passes only when `finished_or_in_progress_agrees` and `identified` are both True.
  - Records that carry no `identified` key are read exactly as before.

## Acceptance evidence

- `tests/test_w4_herovision.py` (new) covers:
  - the gate closed: no call, and HERO stays unjudged;
  - a clear blind review: HERO passes;
  - a misidentified or grid-ambiguous hero: HERO fails;
  - a review of other bytes is never attached.
- Existing tests also run: test_parity, test_blind_review, test_w4_firstimg and
  test_model_spend_paths. Results are in the commit message for the pushed head.

## Board rows

- F-253: the software for parity HERO on Launch-0 disclosed renders is done. The competitive
  blind review still waits on observed benchmark data (data gate).
- F-027 and F-031: now also applied to the disclosed hero.

## Test results (testslot, 2026-10-12)

| Test file | Result |
|---|---|
| test_w4_herovision | 6/6 |
| test_parity | 0 fail |
| test_blind_review | 0 fail |
| test_w4_firstimg | 12/12 |
| test_model_spend_paths | 0 fail |
