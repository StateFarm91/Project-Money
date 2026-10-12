# DISCLOSEDQA: #61 Visual Semantic QA on the frames a disclosed listing actually uploads

Branch `claude/w4-DISCLOSEDQA`. It sits on HEROVISION (it uses `inspect.describe_image`), and
INTEG2 534f27a has been merged in. Shadow only: stub providers, no spend.

## The defect

- `release._review_frames` (#61) reviews the frames `assets.build` stores as `ListingAsset`
  rows.
- `store.publish` and the publication grant read `release.frame_review_state` over those
  rows.
- A Launch-0 listing under D-FB-7 does not upload those frames. Its only upload path
  (`etsy_ops.certified_images`) sends the listing-set certificate's disclosed set plus its
  verified gallery supplements (ANGLE, CONSTRUCTION, COLOUR_CONTEXT, SIZING, MATERIALS,
  CONTENTS).
- As a result, nothing ever semantically reviewed the frames a buyer sees, and the frames
  that were reviewed are never shown.

## The fix

- `visual/exported_review.py` is new.
  - `review(db, slug, version)` runs only while `image_vision` is open. For each exported
    frame, it describes the exact upload bytes blind (`inspect.describe_image`, budgeted)
    against the claim registered for the frame's job (`JOB_CLAIMS`).
  - A job with no registered claim is UNCLAIMED and blocks (the C-80 rule).
  - DESIRE and ANGLE must also be identified as the CIR's product family. DESIRE also needs
    the 230 px grid reading.
  - The review is filed with every exported frame's sha256.
- `review_state(db, slug, version)` counts the review only while it covers exactly the
  frames the valid certificate exports now and every one is `clear`. It returns
  `applies: False` for a release with no disclosed set.
- Wiring:
  - `listing.seo` runs the review after the hero is judged (gated; closed = no call).
  - `pipeline._listing_parity` (store.publish) and `ops/publication_authority._parity` now
    both also read `review_state`. This only tightens. While the gate is closed, publication
    already reads Launch-0 as unreviewed.

## Acceptance evidence (testslot, merged with INTEG2 534f27a)

| Test file | Result |
|---|---|
| `tests/test_w4_disclosedqa.py` (new) | 8/8. Covers: starts unreviewed; every exported job has a registered claim; a clear blind review of the exact bytes opens the gate; a review of other bytes does not count; a misidentified hero blocks; a text frame without text blocks; an unregistered job is unclaimed; the publish read includes the review; a release with no disclosed set is unaffected |
| test_w4_herovision | 0 fail |
| test_w4_firstimg | 0 fail |
| test_cert_listing_frames | 0 fail |
| test_vacuity | 0 fail |
| test_listing_parity_gate | 0 fail (run on 85ec5d0) |
| test_cert_publish_gates | 0 fail (run on 85ec5d0) |
| test_w3_k11_authority | 0 fail (run on 85ec5d0) |
| test_publish_execution_gate | 0 fail (run on 85ec5d0) |
| test_search_hero_publish | 1 FAIL, pre-existing on the base without this change: `LISTING_PRICE_NOT_PLAN` (cloudline CA$9.50 vs plan CA$7.50). Assigned to the product worker. That test holds `_listing_parity`, so this change does not reach it |

## Board row

- B2 #61: the remaining work is the review of the uploaded frames, and that is now built.
  Production clears it on the first funded vision run, through the existing budget.

## Checkpoint (2026-10-12, controlled pause)

- Status: **DONE (code); the re-test after the last change is not run.**
- Since the tests above:
  - `exported_review` now uses `core.workspace.work_dir` with prefix `exported-review-`,
    which is added to `TEMP_PREFIXES`.
  - IMGFIX is merged in.
- Next step: run test_w4_disclosedqa and test_cost_governance_wave2, plus the required set,
  through testslot.
