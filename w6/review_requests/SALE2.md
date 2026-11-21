# Review request — claude/batch19d-sale2

**Branch:** `claude/batch19d-sale2`, from `claude/batch19d` 76d0525, with
`origin/claude/w6-release-19d1` (production 7b250d61) merged in. Not merged to the main branch,
not deployed, no PR. Production is unchanged.

**Owner decision (D-OWNER-PRIVATE-DRAFT-BEFORE-SAMPLE, 2026-11-21T03:55Z, verbatim):**
"yes, private drafts before sample photo are fine".

## 1. Merge of w6-release-19d1

- `listing_package.py`: kept HeroUnjudged / `_try_payload` and `pdf_standard_blocker`.
- `production_evidence.py`: kept `factory_visibility`.
- `app/main.py`: kept the boot owner directive, the Etsy exercise and the `listing.package`
  sweep. Git merged these three files without a conflict; each part is checked present.
- `pdf_standard.py` conflicted. Batch19d had renamed the old premium standard to
  `premium_standard.py` and made `pdf_standard.py` the sale checker. 19d1's LEARN-PROOF-2
  changes (chenille yarn class and care note, eye options, `EYE_AGE_GUIDANCE`) were made to
  the old file, so they are applied to `premium_standard.py`. `pdf_template` imports
  `EYE_AGE_GUIDANCE` from there.
- `test_w4_readback_evidence`: 23 rows. 19d1 added none; batch19d added the sale row.
- `DECISION_LOG.md`: both sides' entries kept.
- `autonomy_map.json` and `decision_index.json` regenerated.

## 2. Why READY was still blocked

`for_publish` already applied the photo only at `stage=activation`, so the draft gate did not
need it. The listing package, however, runs `for_publish(stage=activation)`. Its
`SAMPLE_PHOTO_REQUIRED` blocker made the package BLOCKED. `sale_pipeline._attach` and
`ready_for_sale` required a blocker-free package. `store.publish` requires `ready_for_sale`.
So the photo blocked READY and, through it, the private draft.

## 3. The change

- `release_gates.ACTIVATION_ONLY_CODES = {"SAMPLE_PHOTO_REQUIRED"}` is an explicit allow-list.
- `release_gates.activation_only_reasons(verdict)` returns only reasons that meet all of:
  - the verdict is activation-stage;
  - the reason is in the verdict's own `sample_photo` part and in its reasons;
  - it carries the code prefix;
  - its code is on the allow-list.

  The photo-copy truthfulness problems (`copy_problems`) are not included, so they still
  block a draft.
- `listing_package.assemble` tags those blockers `activation_only`. The package **stays
  BLOCKED**, so no owner-review request is raised and the package is not "ready for owner
  review".
- `sale_pipeline` has three new functions:
  - `publication_blockers` re-checks the source (`release_gates.for_publish`), the
    allow-list and the code prefix;
  - `draft_blockers` is every other blocker;
  - `package_ready_for_sale` is true for exactly this release when the package is READY, or
    BLOCKED with only publication-only blockers.

  `_attach` and `ready_for_sale` use them. `ready_for_sale` adds `publication_blockers` and
  `publishable`. READY records `publication_waits_on`. The board counts
  `ready_publication_waits_on`. Lifecycle LISTING_READY names the wait.
- **Unchanged:**
  - `for_publish(stage=activation)` still refuses on the photo, and `store.activate` reads it
    three times (pinned by `test_w4_launchfix`).
  - The `BRAMBLELOOP_PUBLISH_AUTHORISED` kill switch, the owner grant and the listing-fee cap
    in activation.
  - The Etsy exercise client is still `owner_authorised=False`.
  - Image admission and every other gate.
- No photograph was forged. Laura and `laura-r2-a42aeac7` were not touched.

## 4. Tests (test_vis_gallery_e2e)

- **test_3** (now passes): the real sale chain reaches READY with `publication_waits_on ==
  ["SAMPLE_PHOTO_REQUIRED"]`. `store.publish` creates the draft. Every image and both premium
  PDFs are uploaded and read back byte for byte. The Etsy state is `draft`.
- **test_7** (now passes): production evidence counts the gallery and the read-back draft.
- **test_7a** (new): publication is refused without the sample photo.
  - `for_publish(activation)` blocks on `SAMPLE_PHOTO_REQUIRED`.
  - The real `store.activate` at LIMITED_PRODUCTION on the loopback fake refuses on it, sends
    no request that changes the listing, and leaves it a draft.
  - After the package is reassembled, `ready_for_sale` is READY, with publishable False
    because of `SAMPLE_PHOTO_REQUIRED`.
- **test_7b** (new): mutation test. `for_publish` is recompiled with the activation-stage
  photo gate removed, and test_7a's check fails against it. The real gate then passes again.
- Ordering note: the new tests are named `7a`/`7b` because the runner sorts by name, and
  `test_3`'s publish is correctly not repeatable ("already on Etsy").
- Test-only finding: storing the draft changes the Listing row, so `listing_package_fence`
  withdraws the reviewed package. This is existing behaviour. test_7a reassembles the package
  as the sweep would, under test_3's held gates.

## 5. Suite run

The run was `JOBS=4 SUITE_REGISTRY=0 SUITES=... bash run_tests.sh`, run id
20261121T041814Z-2448, on a clean tree at ec20dcb (the code under review; later commits change
only documents). It covered 25 suites: the 17 requested plus test_w4_launchfix,
test_learn_proof, test_w3_decision_index, test_b19_pdf_blocker_admission, test_pdf_diagrams,
test_w6_listing_chain_e2e, test_w4_c12_lifecycle and test_v11_autonomy_timeline.

**Result: 309 passing, 2 suites failing.** All 17 requested suites pass, including all 15
tests of test_vis_gallery_e2e.

The two failing suites are **pre-existing**. They fail identically, before this change, on
`claude/batch19d` 76d0525 and on the merge commit 387be20:
- `test_w4_launchfix`: `test_img_refuses_unbound_other_release_edited_or_not_first_photos` and
  `test_img_a_bound_unedited_first_sample_photo_passes_this_gate_only`. Their fixtures certify
  a 2 or 3 frame set, which D-OWNER-GALLERY-COMPLETE (7 frames) now refuses.
- `test_w6_listing_chain_e2e`: `test_c` and `test_d`. Their expected blocker sets predate the
  sale pipeline's `pdf_standard` blocker.

These are fixture and expectation drift from batch19's own rules, not from this change. They
are not fixed here, because fixing them means rewriting those tests' fixtures, which is
outside this task; they are recorded in BUILD_STATE. (Production 7b250d61 comparison pending at commit time.)

## 6. Owner actions

None new. Publication still needs a real unedited photograph of a sample (owner, physical).
