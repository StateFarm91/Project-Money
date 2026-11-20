# Fix request: ENG-SALE-PIPELINE (review b19-a, Unit A)

- **Branch:** `eng/sale-pipeline`
- **Verdict addressed:** `origin/review-results/b19-a:VERDICT.md`, Unit A (BLOCK at 1294b143)
- **Fix commit:** `baba3e0` (findings 1-5)
- **Merge commit:** `62fdd1a`, which merges `claude/batch19-approve-all` @ 13585c4f
- **Date (UTC):** 2026-11-20
- **Status:** builder branch. NOT reviewed, NOT integrated, NOT deployed. No PR opened.
  Nothing generated, published or spent.

## Findings

### 1. HIGH: `test_search_hero_publish` was red

**What was wrong.** The blanket's real certified set is 6 frames, because a flat piece has no
ANGLE or CONSTRUCTION frame. Six frames are below `CAMPAIGN_MIN_FRAMES` (7).

**What changed.**
- The merits test now runs the same real chain on `housewarming-key-basket`. That
  release's real certified set is 8 frames: 3 disclosed renders and 5 verified supplements.
  `test_visual_factory_e2e` and `test_disclosed_certified_upload` already use this release.
- A separate test, `test_a_six_frame_certified_set_passes_search_but_is_blocked_before_etsy`,
  keeps the 6-frame blanket. Its hero passes on the merits. It asserts that
  `certified_images` serves nothing and gives the exact "gallery incomplete … 6 of the 7"
  problem, and that `store.publish` is blocked with zero Etsy requests.

**Judgement call: please check.** Even with 7 or more frames, the old assertion "exactly one
draft" cannot pass on this branch without faking. D-OWNER-SALE-PIPELINE (HARD RULE) blocks
`store.publish` unless the release is READY. I drove the real sale-pipeline stages on the
basket, and READY is blocked twice:

- **The listing package is BLOCKED for real reasons.** No physical sample is bound
  (FIRST_CUSTOMER / SAMPLE_PHOTO_REQUIRED), and 4 Etsy remote claims are unverified.
- **The premium PDFs FAIL `slot:gallery7`.** See the new finding below.

`test_visual_factory_e2e::test_b1` already declines to fake READY, so I did not fake it
either. The renamed merits test,
`test_certify_assets_seo_grant_publish_passes_every_gate_up_to_the_sale_rule_with_no_forced_verdict`,
asserts four things:

- the search certificate is PASS on the merits, with nothing forced, and its hero evidence is
  bound to the valid listing-set record;
- the certified set has at least 7 frames;
- every certified frame is served byte for byte, in certificate order;
- `store.publish` gets past the search, listing-set and F-524 image gates, and only the
  D-OWNER-SALE-PIPELINE rule stops it, with zero Etsy requests.

Creating a draft and reading it back for a READY release remains the integration item that
`ENG-SALE-PIPELINE.md` already names.

### 2. MEDIUM: nothing tested that UNKNOWN is never PASS

**What changed.** Added
`test_sale_pipeline_e2e::test_one_unknown_check_among_passes_is_unknown_and_never_certifies`.

- It uses the real premium bytes, where every check is PASS.
- It makes `_cover_logo_check` raise, so `logo:cover` is the only non-PASS check, and it is
  UNKNOWN.
- It asserts that the verdict is UNKNOWN with `failed == []`.
- It then runs `certify_pdfs`, and asserts that both editions are UNKNOWN, `both_pass is False`
  and `certified_premium_pdfs is None`.
- Finally it re-certifies with the real reader and asserts `both_pass` is True again.

### 3. MEDIUM: a certificate was not bound to the checker that issued it

**What changed.** `sale_pipeline.pdf_certificates` now counts a recorded verdict only if both
of these hold:

- `row.checker == PS.CHECKER_VERSION`;
- `row.standard_sha256 == (PS.standard_sha256() or "")`.

Any other row reads as UNKNOWN: `recorded_verdict` keeps the stored value, and
`current_checker` is False. If the standard cannot be read, nothing binds.

**Test:** `test_a_certificate_from_another_checker_or_standard_is_unknown` covers an older
checker, a different standard hash, an empty standard hash and an unreadable standard. It
also checks that `ready_for_sale` is False.

### 4. MEDIUM: a certificate was not bound to the current gallery

**What changed.** `pdf_certificates` now requires
`row.gallery_record_id == gallery_reading(...)["record_id"]`, and only while that reading is
complete. A superseded record, an incomplete gallery, an unreadable gallery or a missing id
all read as UNKNOWN, with `bound_to_gallery` False.

**Test:** `test_a_certificate_for_a_superseded_or_unreadable_gallery_is_unknown`.

**Tests updated (stricter, not weaker):**
- `_certified` now records the real standard hash and gallery record 1.
- `_Gallery` is a labelled test_double for `gallery_reading`, and is always restored.
- Before, the UNKNOWN-edition test recorded `standard_sha256="s"`, so it would have passed
  for the wrong reason. It now binds everything except the verdict, and also covers FAIL.

### 5. LOW: a flapping gate reset the stall clock

**What changed.** `_update` now sets `progressed_at` only on a move past the run's
high-water state.

- The high-water state is stored as `evidence.progress_high_water` and is ordered by
  `STATES`.
- PARKED and REJECTED count as progress.
- `try_admit` records GALLERY.
- `release_reservation` resets the high-water state, because giving the reservation back
  restarts the run, and a later re-admission is real progress.
- So AWAITING_ADMISSION → AWAITING_PRE_IMAGE → AWAITING_ADMISSION does not move
  `progressed_at`.

**Test:** `test_a_flapping_gate_does_not_reset_the_stall_clock` flaps three times, then
asserts that `progressed_at` is unchanged and that the sweep opens the stall incident. It also
asserts that a forward move to GALLERY does reset the clock.

## Mutations: each new test fails on its mutant

The source was restored after every mutant.

| Mutant | Test | Result |
|---|---|---|
| M1a: `etsy_ops.certified_frames` gallery-complete check set to `if False` | six-frame blocked test | **KILLED**: the blanket's 6 images are served |
| M1b: `CAMPAIGN_MIN_FRAMES = 9` | merits test | **KILLED**: 8 < 9 frames |
| M2: `_finish` folds UNKNOWN into PASS | one-UNKNOWN test | **KILLED**: `('US', 'PASS')` |
| M3: `current = bool(row is not None)` | checker/standard test | **KILLED** |
| M4: `on_gallery = bool(row is not None)` | gallery test | **KILLED** |
| M5: every state change counts as progress | flapping test | **KILLED** |

## Merge of `claude/batch19-approve-all` (13585c4f)

These are the eight conflicts the reviewer predicted:

- **`BUILD_STATE.md`, `DECISION_LOG.md`, `suite_final_segment.txt`:** kept both sides.
  There are no duplicate suite lines.
- **`sw.js`:** took batch19's side (`cc-shell-v44`, the Demand view). This branch never
  bumped the shell. The verdict's "keep v43" was written against b098fcce, which predates
  v44.
- **`autonomy_map.json`:** regenerated. The result is 150 cadences, 183 handlers and 95
  edges, matching the verdict.
- **`ops/readback.py` and `test_w4_readback_evidence.py`:** kept the sale_pipeline,
  daily_ledger and engine_demand rows, all advisory. There are now **22** items. The
  verdict's 21 predates engine_demand.
- **`publish/pdf_standard.py`:** kept the branch side, the D-OWNER-PDF-STANDARD bytes
  checker. Ported the ENG-PLUSH `_LABEL` fix into `publish/premium_standard.py`.
  Upstream's family `test_pdf_standard.py` is identical to the branch's
  `test_premium_standard.py` apart from the rename, so it was not duplicated.

## Tests (merged head 62fdd1a)

`JOBS=4 SUITE_REGISTRY=0 SUITES="…" bash run_tests.sh` ran on these 23 suites:

- sale_pipeline, sale_pipeline_e2e, pdf_standard, pdf_template, premium_standard,
  owner_gallery_complete, search_hero_publish;
- vacuity, eng_plush, w4_resume_runner, compiler, twin, reverse, w4_c12_wiring;
- every test file this branch modifies relative to batch19: disclosed_certified_upload,
  etsy_readback_observe, launch0_listing_truth, motif_backlog, opus2_photo_asset_review,
  visual_factory_e2e, w4_disclosedqa, w4_ownerimg, w4_readback_evidence.

Result: SEE_RESULT

## New finding, not fixed here: HIGH, please triage

**An 8-frame certified gallery can never reach READY.**

- `gallery_reading` and D-OWNER-GALLERY-COMPLETE accept **≥ 7** frames, and the disclosed
  basket certifies 8.
- `pdf_standard._gallery7` (D-OWNER-PDF-TEMPLATE) requires **exactly 7** gallery frames.
- So the basket's real premium editions FAIL `slot:gallery7` ("names 8 frames, 7 required")
  and `template:gallery`. The pipeline then parks at `pdfs_built` with the blocker
  `pdf_standard_fail`.
- I reproduced this by driving the real `sale.pipeline` stages on the real chain fixture.
- The fix needs a product decision on which 7 of the 8 frames fill the template's gallery
  slots, so I did not make it here:
  - option (a): the first seven in certificate order;
  - option (b): cap the campaign gallery at seven;
  - option (c): let `slot:gallery7` take a template with 8 slots.
- Until it is decided, a disclosed-render release with 8 frames cannot be sold.

## Still open (unchanged)

- Creating a draft and reading it back for a READY release (an integration item).
- The verdict's Unit B note: confirm that `pdf_template.build_customer_pdf` renders graded
  wearables before garment releases depend on `require_template=True`.
