# FIX-ETSY-SEO: review fixes for eng/etsy-publish (b17-d Unit A) and eng/seo-price (b17-a Unit B)

2026-11-20 UTC. No PR opened. No Railway variables or secrets read. No real Etsy call.
Both branches merge `claude/w6-INTEG6` @ dde3ea62 (merge commits, no force push).
The run environment was a fresh virtualenv from `requirements.lock` and `requirements-test.lock`.
Each run used `JOBS=n SUITE_REGISTRY=0 SUITES=... bash run_tests.sh` on a clean tree.

| unit | branch | head (tested) | suites | result | run record |
|---|---|---|---|---|---|
| A | eng/etsy-publish | `b091cca1` (this file is the next commit) | 18 | **366 passing, 0 failing** | 20261120T134317Z-10127 |
| B | eng/seo-price | `79588ed9` | 10 | **134 passing, 0 failing** | 20261120T132622Z-1859 |

## A suites

test_etsy_publish, test_etsy_publish_e2e, test_etsy, test_draft_creation_durability,
test_eng_approvals, test_w4_listready, test_cert_publish_gates, test_publish_execution_gate,
test_w3_etsy_upload_readback, test_etsy_readback_observe, test_w4_rollback_rehearsal,
test_w4_fmbatch1_rollback, test_draft_intent_precreate_refusal, test_etsy_transport,
test_w4_c13_etsy_ops, test_vacuity, test_w4_resume_runner, test_deliverable_qa.

## B suites

test_eng_seoprice, test_vacuity, test_w4_resume_runner, test_w4_readback_evidence,
test_v11_autonomy_timeline, test_v11_seo_taxonomy, test_v11_seo_truth, test_w3_seo_constraints,
test_w4_cap1_placemat_price, test_w4_placemat_reprice.

The autonomy map was regenerated: 148 cadences, 180 handlers, follow_on 94.

## Unit A fixes (b17-d)

- **A1 (MEDIUM).**
  - `PublishOutcome.image_sha256_by_rank` records the SHA-256 of each image payload the client accepted.
  - `_complete_draft(..., force_images=True)` re-sends every rank with `overwrite` and returns `sent_ranks`. The adopt path always forces. A completion round also forces when the image read-back is unverified.
  - `etsy_ops.image_hash_checks(sent_images, remote, uploaded)` hashes only bytes uploaded in this job. A rank that was not uploaded is a problem. A missing Etsy `full_width`/`full_height` is a problem.
  - Tests:
    - A unit test covers the rank-not-uploaded case, a hash taken from the uploaded bytes, and a missing dimension.
    - A unit test checks that a forced re-send hits every rank.
    - The e2e test (`test_package_to_draft_rollback_adoption_and_refusals` step 4) seeds the hand-made draft with certified alt text, the same pixel size and different bytes. It asserts that every rank was overwritten and that `by_rank.sent_sha256` equals the bytes received.
- **A2 (LOW), fixed by escalation.** The client has no file delete. An adopted draft that already holds a file named like ours is therefore escalated (`store.draft_adoption_escalated`, PermanentError) and never verified on name and size. Unit test included.
- **A3 (LOW).** After `MAX_CONSECUTIVE_UNREAD = 5` UNREAD refusals in a row for the release, the job is dead-lettered with one P2 incident, `store.draft_adoption:unread:<slug>@<version>`. That incident is deduplicated while open. An adoption, an escalation or a publish record ends the streak. Unit test included.
- **A4 (INFO).** Recorded in BUILD_STATE as an owner action for when this lands: re-sign the publication grant.
- The first merged run had 10 failures in test_etsy_readback_observe. They came from an extra rule I had added that went beyond the review: certified bytes whose dimensions cannot be decoded were treated as a failure. I removed that rule in b091cca, since the rank hash is what proves the bytes. The rerun is green.

## Unit B fixes (b17-a)

- **B1 (HIGH).**
  - `originality()` with no titles returns `ok: None, status: "UNKNOWN"`.
  - `seo_package` adds `TITLE_ORIGINALITY_UNKNOWN`, and the release blocking prefixes now include `CATEGORY_`.
  - `search_certificate` fails `market_fit` unless `originality is True`.
  - Test: an empty shelf gives `market_fit.ok is False` and REFUSED.
- **B2 (MEDIUM).** Added a killing test for the trigram rule: "Cosy Chunky Granny Basket Tote" against "Chunky Granny Basket Tote" has a run of 4 and a Jaccard of 0.667, so it is copied. With the rule disabled the same pair passes.
- **B3 (LOW).** `release._refuse_deceptive_discount` calls `market_fit.discount_problems` on both live price paths.
- **B4 (LOW).** Originality evidence records `scope` (`pod` or `all`).
