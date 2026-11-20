# ENG-GALLERY-FIXTURES — review request

- **Branch:** eng/gallery-complete
- **Fixture commit under test:** `8b38de47689d00706ce1a6d13907a288f3eba64d` (this file is added in the commit after it)
- **Rule:** D-OWNER-GALLERY-COMPLETE. A valid listing-set certificate needs at least
  `CAMPAIGN_MIN_FRAMES` (7) frames. With fewer, `certified_frames` reports "gallery incomplete",
  and lifecycle LISTING_READY needs a complete gallery.

## Result (2026-11-20, UTC)

The 27-suite set was run with `JOBS=8 SUITE_REGISTRY=0 SUITES="…" bash run_tests.sh`:

**TOTAL PASSING: 360; suites failing: 0; environment failures: 0** (821 s).
The run record is `brambleloop/artifacts/suite_runs/20261120T132116Z-25251.json` (passed).
The record says "tree dirty at start" and SHA 20e8183. The run began before the commit, so the
fixture edits were not yet committed, but the files on disk were the same as in 8b38de4.
Tests ran in a venv installed from `requirements.lock` + `requirements-test.lock`.

This run's starting point was 6 failing suites (327 passing). Two of those were environment
failures: an unpinned starlette needed httpx2, which affected test_ranking_readiness and
test_w4_readback_evidence. The lock-pinned venv fixed them, with no code change.

## Changes in this commit (earlier ones: 1296a6b, d27bcaa, 6c33484)

- **test_search_hero_publish.** The blanket's certified set has 6 frames and still passes the
  hero check. Its publish is now asserted BLOCKED: the reason is "gallery incomplete", no
  createDraftListing is sent and no image is uploaded. The sibling draft-creating test now uses
  the key basket, which has a complete certified gallery. It asserts that uploaded == certified
  and that there are >= CAMPAIGN_MIN_FRAMES images.
- **test_w4_fmbatch1_lifecycle.** A draft with no certified gallery, or one with 6 frames,
  stays at VISUAL. A 7-frame valid certificate reaches LISTING_READY. All later stages are
  unchanged.
- **test_w6_listing_chain_e2e.**
  - The observed package-blocker set C adds `("certified_frames", "gallery incomplete")`, and
    the test asserts that the packaged gallery is partial.
  - Pre-existing failure: test_a and test_b also failed at `8d26893^`, before the gallery rule.
    Running the worker drain with `supply.after_chain_job` enabled seeded all eight Launch-0
    chains. The refill, which has its own trigger and its own tests, is now held during the
    one-product drain. Every chain assertion is unchanged.
- **test_owner_gallery_complete.** Adds a non-emptiness assertion so that test_vacuity passes.

No assertion was removed or loosened. No production code changed.
