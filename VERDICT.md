# Review b17-d: verdict (2026-11-20, UTC)

Base `claude/w6-INTEG6` @ dde3ea62. Reviewed locally only: no PR, no real Etsy call, no Railway variables or secrets read.

| Unit | Head | Verdict |
|---|---|---|
| A `eng/etsy-publish` | f06b1e73 | **BLOCK** (one MEDIUM finding, small fix; see A1) |
| B `eng/pdf-premium` | de81ce8c | **SHIP** (follow-ups B1 to B3 in the next slice) |

## Merge onto dde3ea62

- **A:** conflicts only in `BUILD_STATE.md` and `DECISION_LOG.md`. Both are append-only, so keep both sides.
- **B:** the same two documents, plus `autonomy/autonomy_map.json`. In that file only `generated_at` differs, so take the base or regenerate.
- No code conflicts in either unit.

## Test runs

All runs used `JOBS=4 SUITE_REGISTRY=0 SUITES=... bash run_tests.sh`, a fresh virtualenv with the requirements and test lockfiles, and the merged trees.

- **A:** 18 suites, 362 passing.
  - Suites: test_etsy_publish, test_etsy_publish_e2e, test_etsy, test_draft_creation_durability, test_eng_approvals, test_w4_listready, test_cert_publish_gates, test_publish_execution_gate, test_w3_etsy_upload_readback, test_etsy_readback_observe, test_w4_rollback_rehearsal, test_w4_fmbatch1_rollback, test_draft_intent_precreate_refusal, test_etsy_transport, test_w4_c13_etsy_ops, test_vacuity, test_w4_resume_runner, test_deliverable_qa.
  - test_draft_intent_precreate_refusal first failed for an environment reason: `httpx` was missing. After `requirements-test.lock` was installed it passed 12/12, so all 18 are green.
- **B:** 11 suites, 209 passing, 0 failing.
  - Suites: test_pdf_standard, test_pdf_premium, test_pdf_layout_bounds, test_w4_ccgap_pdfium, test_etsy, test_w3_etsy_upload_readback, test_cert_publish_gates, test_publish_execution_gate, test_vacuity, test_w4_resume_runner, test_deliverable_qa.
  - The Etsy-publish suites do not exist on B.

## Mutants

- **A:** in `publish/draft_adoption.judge`, the price-equality condition was dropped, so a draft at another price would be adopted.
  - It **survives** `test_etsy_publish.py`.
  - It is **KILLED** by `test_etsy_publish_e2e::test_two_matching_drafts_or_a_live_one_escalate_and_nothing_is_created`, which adopted a CA$0.01 draft.
- **B:** in `publish/pdf_standard._counts`, a row with no printed count was no longer reported. **KILLED** by `test_pdf_standard::test_each_rule_fails_when_its_evidence_is_removed` (row_counts).

## Checklist A

| Requirement | Result |
|---|---|
| OAuth tokens are never logged | **OK.** The diff adds no token, header or credential logging. Error text is `type(exc).__name__` plus truncated `str(exc)`. |
| Kill switch | **OK.** `BRAMBLELOOP_PUBLISH_AUTHORISED` is unchanged and is re-checked in `resolve` and `queue_publication`. |
| CA$6 fee budget | **OK.** The cumulative check is intact. The new per-listing cap sits inside the same lock. |
| Shadow refusals | **OK.** They are unchanged. |
| Exact release bound | **OK.** `resolve(slug, version, release)` checks the snapshot digest. The job key carries `release[:24]` and the grant id. |
| Idempotent duplicate-draft recovery | **OK.** The check runs inside `before_create`, after revalidation. Adopting checkpoints the intent, and the second scheduler tick queues nothing. |
| Real PDFs uploaded, never a link page | **OK.** `attach_file(data=docs[t].pdf_bytes)` uploads both US and UK. The e2e asserts the server-received sha256 equals the certified hash. |
| Readback verifies every hash | **NOT MET on the adopt path.** See A1. |
| Publish only with a signed owner grant | **OK.** The scheduler only calls `resolve`, which checks an Ed25519-sealed grant, and then the owner's door. It imports no grant writer. |
| `STAGE_A_ENABLED` stays False | **OK.** `ops/standing_activation.py:63`. |

## Findings, unit A

### A1. MEDIUM: adopted drafts pass image-hash verification without our bytes ever being sent

Three behaviours combine here:

- `etsy_ops.image_hash_checks` hashes `sent_images`, which are the certified bytes this job *would* send. It does not hash what was actually sent.
- On the adopt path, `_complete_draft` uploads nothing when the image count and alt text already match.
- The dimension check is skipped when Etsy omits `full_width` or `full_height`.

**Failure scenario.** A stale or hand-made draft has the certified title and price, the same alt texts and the same pixel size, but different images. Its read-back is `verified`. The first-listing card is then raised, stating that "every image rank's hash matches the certificate". That breaks the "never claim verified until verified" rule.

**Fix:**

1. In `_adopt_and_complete`, always re-send every rank with `overwrite=True`. Pass a `force_images=True` argument to `_complete_draft`.
2. Have `_complete_draft` return `sent_ranks` together with the sha256 of each payload actually uploaded.
3. Change `image_hash_checks` so it hashes only bytes that were really uploaded in this job, keyed by rank. Treat a rank that was not uploaded in this job, or a missing Etsy dimension, as a problem rather than a skipped check.
4. Add an e2e test: seed a draft with matching alt text and different image bytes, then assert that the image ranks are overwritten and that the hashes come from the bytes actually uploaded.

### A2. LOW: adopted drafts accept existing PDFs on filename and size alone

`_complete_draft` treats a held file of the same name as present, and the read-back compares only name and size. An earlier release's PDF with the same name and size would pass.

**Fix:** on adoption, delete and re-attach any held file whose name matches, using `deleteListingFile` under the same grant. If no delete path exists, escalate when held files are present.

### A3. LOW: an unreadable shop retries forever

An UNREAD verdict raises `TransientError` with no bound, which is the review request's question 3.

**Fix:** after N consecutive UNREAD outcomes for the same release (N = 5 is suggested), dead-letter the job and open a single P2 incident `store.draft_adoption:unread:<slug>@<version>`. It still fails closed.

### A4. INFO: existing publication grants are voided by the text change

Changing the `ROLLBACK_PATH.remove_draft` text voids every publication grant recorded before this change. This is by design, but the owner must re-sign. Add that to the owner action batch when this lands, so the void is not discovered later as a silent "waiting_for_owner_grant".

## Checklist B

| Requirement | Result |
|---|---|
| Stitch count on every row | **OK as a gate, with gaps.** Every printed `Row` or `Rnd` label needs a compiler-certified count. See B1 to B3. |
| Deterministic | **OK.** The reproducible-bytes test passes for US and UK, and `pdf_standard` uses no clock, randomness or uuid. |
| Missing facts block the build | **OK.** `enforce_standard` defaults to True, so `build_pattern_pdf` raises `PremiumStandardRefused`, and a static test keeps `False` out of `src/`. |
| Nothing copied from benchmarks | **OK.** The rules encode structure only. The About, Disclaimer and licence text is original Brambleloop copy, and nothing reads `research/benchmarks` at run time. |

## Findings, unit B

### B1. MEDIUM: certified counts are keyed by row index only, mixing components

`_counts` builds `valid[r.index]` across *all* components. On a multi-piece pattern, a wrong count printed for piece A's Row 5 passes whenever any other piece certifies that number at Row 5.

**Fix:**

1. Key the certified counts by `(r.component, r.index)`.
2. Split the instructions body per component heading, and check each label against its own component.
3. Add a mutation test that swaps one component's count for another component's count at the same index.

### B2. LOW: no coverage check, and ranges are checked only at their first row

A row the renderer drops is never reported, because only printed labels are checked. A label such as "Rows 2–10" is checked only against row 2.

**Fix:**

1. Expand ranges and check each row in the range.
2. Require the printed indices to cover the compiler's indices for each component.

### B3. LOW: the count matched may not be the row's ending count

`_COUNT.search(seg)` takes the *first* `(N sts)` in a row's text. A mid-row parenthetical, such as a cluster note, would be read as the row's count.

**Fix:** use the last match in the segment, or anchor the pattern to the end of the row.

### B4. INFO: the licence change still needs owner and legal confirmation

The licence change (`permitted_small_scale_with_credit`) is selected and flagged as not legally reviewed. It is not an engineering blocker. Keep it in the owner queue before the first public listing.
