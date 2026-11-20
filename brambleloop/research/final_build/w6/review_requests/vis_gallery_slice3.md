# [ENG-VIS-GALLERY] slice 3 — review request

Branch `eng/vis-gallery`, on top of slice 2. It is not integrated and not deployed.

## What changed
| Area | File | Change |
|---|---|---|
| Evidence | `ops/production_evidence.py` | `visual_pipeline.generated_galleries` (`_vp_generated`) is counted from rows only. It reports: gallery runs; images generated and recovered; `independently_verified` (a PASS with no `test_double` and no fixture reading) against `verified_with_test_doubles`; failed and unmeasured frames; Laura `identity_passed` against `identity_held` (a stub or fixture identity never counts as passed); `completed_seven_image_galleries` (valid certificates of 6 `generated_render` frames plus CONTENTS); blocked galleries, grouped by gate name; `awaiting_publication`; `etsy_drafts_verified`; spend; and `cost_per_completed_gallery_cad` (UNKNOWN when nothing is completed). It emits no ids, prompts or text. The certified-PDF, listing-package and draft counts that already existed are unchanged. |
| Tamper proof | `tests/test_vis_gallery_e2e.py::test_8` | `listing_set` re-judges the set on every call. It blocks when a reading drops to UNKNOWN, when the selection names other bytes, or when the CONTENTS preview is missing. Tampering invalidates the stored certificate (claims fingerprint), and only a fresh full pass re-issues it. |

## Proof
- `test_vis_gallery_e2e` 8/8: the full chain to the FakeEtsy draft with a byte-for-byte read-back of 7 images and the US/UK PDFs. Also covered: a failing frame with bounded repair, UNMEASURED blocking, recovery, the evidence counts and tampering.
- Mutants: `tests/_vis_gallery_mutants.py` (unit, 22/22 killed) and `--e2e` (chain-level; result below).

## e2e mutant result
`tests/_vis_gallery_mutants.py --e2e`: 6 of 6 killed. The chain mutants are: refused frame does not block the set; selected bytes not compared; generated path not dispatched; certify ignores blockers; Laura publication passes unapproved; recovery ignores Laura.
A seventh mutant, "stub readings count as independent", survived at chain level because a second label check (on the fidelity reading) still caught it. Both checks are now killed directly in the unit list: `tests/_vis_gallery_mutants.py` 24 of 24.
