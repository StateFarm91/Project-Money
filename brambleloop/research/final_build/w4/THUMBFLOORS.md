# THUMBFLOORS: F-252 resolution and exposure floors on the first photo

Branch `claude/w4-THUMBFLOORS`, based on `origin/claude/w4-INTEG2` 85ec5d0. Shadow only; no
spend.

## What changed

`commerce/thumbnail.evaluate_thumbnail` now runs `quality_floors(image)` before it judges the
image at grid scale. Each floor reports its own measurement in `measurements`.

- **Resolution:** the short edge must be at least `MIN_SHORT_EDGE_PX` (1000 px). Below that
  the listing cannot be zoomed, and the check reports `THUMB_RESOLUTION_LOW`.
  - Basis: Etsy's published listing-photo guidance that zoom needs at least 1000 px. This is
    recorded as an assumption; I did not re-read the guidance in this session.
- **Exposure:** measured on the subject only (every pixel unlike the corner background), so a
  white or black seamless background is never penalised.
  - `THUMB_UNDEREXPOSED`: more than 50 % of the subject is crushed to black.
  - `THUMB_OVEREXPOSED`: more than 50 % of the subject is blown to white.
  - `THUMB_FRAME_TOO_DARK`: the whole frame's mean luminance is below 0.06.

The existing thresholds (contrast, coverage, text) are unchanged. Comparative click appeal
stays with the `image_vision`-gated grid tournament (F-278).

Both existing callers now apply the floors: the `assets.build` hero and the disclosed
listing QA hero. Every Launch-0 contract colour on the contract background clears them; a
test pins this.

## Acceptance evidence

All test files were run through `testslot.sh`.

| Test file | Result |
|---|---|
| `tests/test_w4_thumbfloors.py` (new) | 7/7 passing |
| `test_commerce` (existing thumbnail tests) | 0 fail |
| `test_cert_hero_title_safe` | 0 fail |

## Board row

- F-252: its software "remaining" item (resolution and exposure floors) is done. Comparative
  click appeal stays gated on the tournament judgement.
