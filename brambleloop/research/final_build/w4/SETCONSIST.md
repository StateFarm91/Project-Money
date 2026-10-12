# SETCONSIST: F-746 listing-set consistency in parity GALLERY

Branch `claude/w4-SETCONSIST`, based on `origin/claude/w4-INTEG2` 534f27a. Deterministic; no
vision call and no spend.

## What changed

`visual.parity.set_consistency(frames)` checks each pair of frames in a listing set against
facts the frames already carry. The pictures are not re-judged. The checks:

- **Product identity:** the product, release, CIR fingerprint and represented configuration
  (`represented_variant.key`) must be the same in every deterministic frame's manifest.
- **Colours:** every colour a deterministic frame draws must be one of the certified CIR's
  colours (`render_verification.authoritative_cir`). A frame drawing a colour the product
  does not have is refused.
- **Model identity:** model-bearing frames must all be conditioned on the same identity pack.

Parity GALLERY now FAILs on any mismatch. Previously it checked only that each frame had a
declared job and that an evidence frame was present. Frames without a manifest add nothing
here; the photographic floors still apply to them. No threshold changed.

## Acceptance evidence (testslot)

| Test file | Result |
|---|---|
| `tests/test_w4_setconsist.py` (new) | 6/6. Includes "a set with one mismatched colour is refused", the row's named acceptance test |
| `test_parity` | 0 fail |

## Board row

- F-746: the software item "pairwise set-consistency check … test a set with one mismatched
  colour is refused" is done.
- The row's external gate (model-bearing frames) is unchanged.
