# Review b18-b: verdict (2026-11-20, UTC)

The base is Batch 17, `b098fcce` (eng/colourwork head). This review was done locally only:
- no PR was opened;
- no Railway variables or secrets were read;
- no real Etsy call was made.

Each suite run used a fresh virtualenv built from `requirements.lock` and `requirements-test.lock`, and this command:
`JOBS=4 SUITE_REGISTRY=0 SUITES=... bash run_tests.sh`

| Unit | Head | Verdict |
|---|---|---|
| A `eng/etsy-publish` | 04e1200d | **SHIP** (A-1 is a LOW follow-up) |
| B `eng/seo-price` | 79588ed9 | **BLOCK** (B-1: the B1 fix breaks `test_w4_seo_packages`, which passes on the base) |

## Merge onto b098fcce

- **A:** conflicts in `BUILD_STATE.md`, `DECISION_LOG.md` and `autonomy_map.json`.
  - Keep both sides of the two documents (they are append-only).
  - Regenerate the map with `python -m brambleloop.autonomy.map --write src/brambleloop/autonomy/autonomy_map.json`. The result is 149 cadences, 181 handlers and 95 follow-on edges.
  - Note: `--write` with no path raises `IndexError`.
  - There are no code conflicts.
- **B:** conflicts in `BUILD_STATE.md` and `autonomy_map.json`. Resolve them the same way. The regenerated map has 149 cadences, 181 handlers and 96 follow-on edges. There are no code conflicts.

## Suites (merged trees)

- **A: 18 suites, 366 passing, 0 failing.** Run record `20261120T140328Z-802`. Suites:
  - test_etsy_publish, test_etsy_publish_e2e, test_etsy
  - test_draft_creation_durability, test_draft_intent_precreate_refusal
  - test_eng_approvals, test_w4_listready
  - test_cert_publish_gates, test_publish_execution_gate
  - test_w3_etsy_upload_readback, test_etsy_readback_observe
  - test_w4_rollback_rehearsal, test_w4_fmbatch1_rollback
  - test_etsy_transport, test_w4_c13_etsy_ops, test_deliverable_qa
  - test_vacuity, test_w4_resume_runner
- **B: 11 suites, 134 passing, 1 suite failing** (`test_w4_seo_packages`, 6 tests). Run record `20261120T140329Z-828`. Suites:
  - test_eng_seoprice, test_vacuity, test_w4_resume_runner
  - test_w4_readback_evidence, test_v11_autonomy_timeline
  - test_v11_seo_taxonomy, test_v11_seo_truth, test_w3_seo_constraints
  - test_w4_cap1_placemat_price, test_w4_placemat_reprice
  - test_w4_seo_packages
- **Bisect for B-1.** `test_w4_seo_packages` was run on four trees:
  - base `b098fcce`: 0 failures;
  - pre-fix `110d050`: 0 failures;
  - `79588ed9` alone: fails;
  - merged tree: fails.

## Mutants (one line each, run in a separate worktree)

- **A:** in `etsy_ops.image_hash_checks`, `sent = uploaded.get(rank, "")` was changed to `uploaded.get(rank) or sha256(data)`. This reverts A1, so the hash comes from the bytes the job intended to send. **KILLED** by `test_etsy_publish::test_image_readback_compares_sent_hashes_with_the_certificate_and_etsy_dimensions`.
- **B:** in `market_fit.originality`, `if not shelf_titles:` was changed to `if False:`, so an empty shelf passes again. **KILLED** by `test_eng_seoprice::test_an_empty_shelf_is_unknown_originality_and_fails_the_certificate` (26/27).

## Unit A: b17-d findings

1. **A1: FIXED.**
   - `image_hash_checks` hashes only `uploaded` (rank to SHA-256 from `PublishOutcome.image_sha256_by_rank` and `_complete_draft`'s `sent_ranks`). A rank that was not uploaded is a problem, and so is a missing Etsy dimension.
   - `_adopt_and_complete` passes `force_images=True`, and the completion rounds force images when the image read-back is unverified.
   - A test was added for an adopted draft with matching alt text and different bytes.
   - Commit b091cca no longer counts *undecodable certified* bytes as a dimension failure. That is acceptable, because the rank hash is what proves the bytes; a missing Etsy dimension still fails.
2. **A2: FIXED.** `_refuse_held_pattern_files` escalates an adopted draft that already holds a file with one of our names. The client has no file-delete path. Tested.
3. **A3: FIXED.**
   - After `MAX_CONSECUTIVE_UNREAD = 5`, the job raises `PermanentError` and dead-letters.
   - One P2 incident `store.draft_adoption:unread:<slug>@<version>` is raised, deduplicated while open, and nothing is created. Tested.
   - See A-1 for one gap.
4. **A4: FIXED.** The owner action to re-sign the publication grant is recorded in BUILD_STATE.

### Checklist A (re-verified)

| Requirement | Result |
|---|---|
| Tokens never logged | **OK.** The diff adds no token, header or credential logging. |
| Kill switch, fee budget, Shadow refusals | **OK.** `BRAMBLELOOP_PUBLISH_AUTHORISED` is unchanged. The per-listing cap (US$0.20 at the assumed rate) sits inside `_budget_refusal` together with the CA$6 cumulative cap, and an e2e test covers both. The Shadow refusals are unchanged. |
| Exact release bound | **OK.** `pa.resolve(db, slug, version, release)` checks it, and the job key carries the release and the grant. |
| Idempotent duplicate recovery | **OK.** The check runs inside `before_create` after revalidation, and adoption checkpoints the intent. |
| Real PDFs uploaded | **OK.** `attach_file(data=docs[t].pdf_bytes)` uploads US and UK, and the e2e test checks the server-side sha256. |
| Readback verifies hashes | **OK now.** It hashes only bytes uploaded in this job (A1). |
| Signed owner grant | **OK.** The scheduler calls only `pa.resolve`, which checks the Ed25519-sealed grant. `first_public_listing:` is a GENUINE kind. A test pins that no grant writer is imported. |
| `STAGE_A_ENABLED` | **False** at `ops/standing_activation.py:63`. |

### Findings, unit A

**A-1. LOW: the A3 "consecutive" streak is not reset by a successful read.**
- `_unread_streak` stops counting only at `store.draft_adopted`, `store.draft_adoption_escalated`, `store.published` or `store.publish_incomplete`.
- A readable shop with no existing draft (verdict NONE) writes nothing. Suppose the create then fails transiently before anything is published. The earlier UNREAD refusals still count.
- As a result, 5 *non*-consecutive UNREADs can dead-letter the job. It still fails closed: nothing is sent.
- **Fix:**
  1. On `verdict == NONE` in `_duplicate_check`, call `ctx.audit("store.duplicate_check_read", artifact=f"{slug}@{version}", detail={"release": release})`.
  2. Add `"store.duplicate_check_read"` to `ends` in `_unread_streak`.
  3. Add a test with 4 UNREAD outcomes, then NONE, then 4 UNREAD, and assert there is no dead letter.

## Unit B: b17-a findings

1. **B1: FIXED as specified.** Behaviour now:
   - `originality([])` returns `ok: None, status: UNKNOWN`.
   - `TITLE_ORIGINALITY_UNKNOWN` is added to the problems.
   - `CATEGORY_` is a blocking prefix.
   - `search_certificate` fails `market_fit` unless `originality is True`.
   - The mutant above is killed.
   - **However, this fix breaks an existing suite. See B-1.**
2. **B2: FIXED.** There is now a killing test for the trigram-Jaccard rule.
3. **B3: FIXED.** `_refuse_deceptive_discount` calls `discount_problems`, which wraps `check_no_fake_discount`, on both live price paths. The flagship rule is inert while `was_price` is always None, and the docstring says so.
4. **B4: FIXED.** The originality evidence records `scope` (`pod` or `all`), and the certificate records `originality_scope`.

### Findings, unit B

**B-1. HIGH: a regression on the integrated tree, where `test_w4_seo_packages` fails 6 tests.**
- Failing tests:
  - `test_certified_branch_with_fixture_taxonomy_and_staleness`
  - `test_listing_seo_persists_a_package_the_consumer_reads`
  - `test_mjs_findings_flow_into_the_package`
  - `test_packages_make_the_seo_search_cell_measurable`
  - `test_search_evidence_consumes_the_package`
  - `test_stats_arrival_updates_the_package_through_the_seo_cycle`
- The suite passes on `b098fcce` and on `110d050`.
- **Cause:** the three B1 fail-closed changes together.
  - The suite's fixtures have no research-shelf titles and/or no assigned category. `listing_seo` therefore blocks, and no SEO package is persisted, so the consumers read `None`.
  - Turning off both the `TITLE_ORIGINALITY_UNKNOWN` and the `CATEGORY_` blocking leaves 3 failures. Also turning off the `originality is True` certificate guard leaves 0 failures.
  - The gate is correct, so do not relax it.
- b17-a did not run this suite. Add it to the unit's suite list.
- **Fix:**
  1. In `tests/test_w4_seo_packages.py`, seed the fixture pod with research-shelf listings that `market_fit.research_listings` reads. Use at least two original, non-overlapping competitor titles, so originality is `PASS` with `checked > 0`.
  2. In the same fixtures, assign the product a taxonomy node so that `CATEGORY_UNKNOWN` is not raised.
  3. Add one negative assertion: with the shelf removed, `handle_listing_seo` reports `TITLE_ORIGINALITY_UNKNOWN` in its blocking list and the certificate's `market_fit.ok` is False.
  4. Rerun `test_w4_seo_packages`, `test_eng_seoprice`, `test_v11_seo_cycle` and `test_w4_c09_seo` on the merged tree.
- **Before landing**, also confirm that production has research rows for every pod that has listings due for SEO. Otherwise those listings stop at SEO, which is the intended fail-closed outcome but should be visible on the board, not silent.

## Order of integration

A now. B after B-1, with `test_w4_seo_packages` green on the merged tree.
