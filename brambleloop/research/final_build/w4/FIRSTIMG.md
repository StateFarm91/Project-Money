# FIRSTIMG: the first image must show what is sold (F-027, F-031, F-041)

Branch `claude/w4-FIRSTIMG`, based on `origin/claude/w4-INTEG2` 85ec5d0. Shadow only: no
deploy, no spend. Every vision call in the tests goes to a stub provider.

## What changed

`image_vision` is now open in production, so the hero review in `assets.build`
(`runtime/release._review_frames`) does more than `#61`'s finished/chart comparison.

- **F-027: identify the product.** The hero's claim now carries `identifies_as`: the product
  families the certified CIR names (`inspect.product_families`, using the
  `gates.first_customer.PRODUCT_TYPE_FAMILIES` vocabulary).
  - `inspect.compare` reports `product_identity` when the blind description (which never sees
    the claim) names none of those families.
  - A misidentified hero is `FRAME_REVIEW_BLOCKED` and stops the chain.
- **F-031: identifiable at grid size.** `inspect.identify_at_grid` downscales the hero to
  `commerce.thumbnail.GRID_PX` (230 px) and makes one blind description call.
  - The call goes through the same reserve → call → bill → release discipline as
    `inspect_image` (agent `quality_director`, purpose `asset_inspection`; a spent daily
    permission refuses before the provider is called).
  - Result is `blocked` (`FRAME_REVIEW_HERO_NOT_IDENTIFIABLE`) when the description at
    230 px is any of these: not identified as the product, `ambiguous`, `unreadable`, or
    showing a third-party mark.
  - Result is `unjudged` when any of these holds: the call failed, the CIR names no product
    family, or clarity is outside the vocabulary.
- **F-041:** a hero whose review is otherwise clear stays `unjudged` until identification is
  made, both on the full frame and at grid size. `frame_review_state` already reads anything
  but `clear` as not reviewed, so publication stays closed.

No threshold or gate was loosened. When `image_vision` is closed, behaviour is unchanged:
every frame is recorded `unreviewed`.

## Fixture change to an existing test, with reasons

In `tests/test_cert_listing_frames.py::test_unjudged_stays_unjudged_and_only_a_bound_all_clear_review_opens_publication`
the fake describer called the hexagon coaster set's hero "a blanket". Under F-027 that is a
misidentified hero, so the fixture now says "a set of hexagon coasters". The grid call is
stubbed `clear` inside that test. **No assertion changed.**

## Acceptance evidence

All test files were run one at a time through `testslot.sh`.

| Test file | Result |
|---|---|
| `tests/test_w4_firstimg.py` (new) | 12/12 passing |
| `test_visual_inspection` | 0 fail |
| `test_model_spend_paths` | 0 fail. The new grid call site `inspect.py::_call` is guarded; `inspect_image` was left unchanged |
| `test_cert_listing_frames` | 0 fail |
| `test_vacuity` | 0 fail |

## Board rows

- F-027 is advanced from software-pending to vision-ready.
- F-031 is advanced, and gains the grid-scale identification check.
- F-041 is advanced; it needed nothing beyond the F-027 step.
- In production, each row closes on the first real vision call recorded for a release. That
  call is owner-funded through the existing budget and is not made from here.
