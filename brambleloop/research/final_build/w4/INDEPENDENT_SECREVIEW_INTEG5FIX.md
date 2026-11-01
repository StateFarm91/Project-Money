# Independent security review: W5-INTEG1 integrator changes (INTEG5FIX)

- **Reviewed:** `claude/w5-INTEG1` at `5a248a82`. In scope: the integrator's own conflict
  resolutions and fixes in `b593a521`, `4f136bf7`, `fd3487a3` and `5a248a82`, plus the R40
  merge `b9245dc0`. The feature branches themselves were reviewed earlier and are out of scope.
- **Date:** 2026-11-01 (UTC). Read-only: no source change, no deploy, nothing done on Railway
  or in production, no spend.
- **Environment:** Python suites run one at a time from `brambleloop/` with
  `PYTHONPATH=src:tests`. Mutations ran in separate git worktrees at `5a248a82`, and each was
  reverted afterwards (`git status` clean). `run_tests.sh` was not run. Node 22 is present, but
  `pwa_browser` was not in the requested set, so it was not run.

## Verdict: **DO NOT SHIP**

One HIGH finding blocks shipping. The size-claim integration fix (`fd3487a3`) relaxes a publish
gate. "Round" and "row" are common product adjectives, so ordinary multi-size and multi-piece
titles now pass size-claim truth. The basket wording below was refused before the fix and is
accepted after it:

    Round 3 baskets · Round 3-piece basket set · Round 3 basket sizes · Round three sizes ·
    Shop this round 3 basket set. · Our round 3 baskets nest neatly. · round 4 bins ·
    Round two baskets for your shelf · A row 3 baskets wide · Rows 2 bags

Every other resolution checked keeps both sides' behaviour, and no other gate was relaxed.
Once F1 is fixed with a test for these cases, the remaining findings do not block shipping.

## Findings

| # | Severity | Commit | Finding |
|---|---|---|---|
| F1 | **HIGH** | fd3487a3 | The `_PATTERN_REF_BEFORE` exclusion is too broad. "Round" (an adjective) and "row" suppress real `count` and `vessel_count` claims. |
| F2 | MEDIUM | fd3487a3 | P0-PHOTO-ASSET-REVIEW is recorded only in a commit message. It is not in BUILD_STATE or any register, and the production gap is real. |
| F3 | MEDIUM (test gap) | b593a521 | No test exercises the merged `carry_permanent` line in `_persist_release`. Removing it leaves every suite green. |
| F4 | LOW | 4f136bf7 | The owner decision packet `OWNER_ACTIONS.json` (research copy and Command Center snapshot) still lists the deleted `market-basket-small-1.2.0-*` kit files with their hashes. |
| F5 | LOW | 4f136bf7 | `ops/retention.py` has a duplicate dict key `"listing.adopted_manual"` (lines 129 and 135). The values are identical today, so there is no effect now, but a later edit to only one copy would be silently overridden. |
| F6 | INFO | fd3487a3 | With the fixture change, the photo-led suite no longer notices the approval reset in `lead_with_if_qualifying` being removed (mutation M5 survives). |

### F1 (HIGH): the size-claim exclusion lets real multi-size claims through

`gates/size_claims.py` skips any `count` or `vessel_count` match whose preceding text ends in
`\b(?:rnds?|rounds?|rows?)\.?\s*$`. It does not check what follows the number. As a result:

- "Round" as the basket's shape ("Round 3 basket set") is read as a round number.
- The skip applies to the `count` pattern ("N sizes") too, but "Round 3 sizes" is never a
  place in a pattern.
- The new test has no negative case for an adjective "round" or "row".

**Repro** (from `brambleloop/`, `PYTHONPATH=src`). `check_texts({"title": t})["state"]`:

| Text | Before fix (`4f136bf7`) | After fix (`5a248a82`) |
|---|---|---|
| `3 rounds baskets` | FAIL | FAIL (still caught) |
| `Row of 3 baskets` | FAIL | FAIL (still caught) |
| `Rnd 2 3 baskets` | FAIL | FAIL (still caught: the claim is "3 baskets", after "2 ") |
| `Round basket set of 3` | FAIL | FAIL (still caught: `vessel_set` is not excluded) |
| `Rows 2 bags` | FAIL | **PASS** |
| `Round 3 baskets` | FAIL | **PASS** |
| `Round 3-piece basket set` | FAIL | **PASS** |
| `Round 3 basket sizes` | FAIL | **PASS** (both `count` and `vessel_count` suppressed) |
| `Round three sizes` | FAIL | **PASS** |
| `Our round 3 baskets nest neatly.` | FAIL | **PASS** |
| `round 4 bins` / `A row 3 baskets wide` | FAIL | **PASS** |
| `Round, 3 baskets` / `Round. 3 baskets` | FAIL | FAIL |
| `Up to Rnd 10 the basket should lie flat.` (the 1.3.0 tip) | FAIL (false positive) | PASS (intended) |

These are titles and descriptions a listing writer would actually use, and the gate exists to
refuse them for a release that delivers one size.

**Suggested fix (not applied; this review is read-only).** Never exempt the `count` pattern.
Exempt `vessel_count` only when the round/row number is followed by a determiner, which is what
the 1.3.0 tip looks like ("Rnd 10 **the** basket"):

```python
_REF_THEN_DET = re.compile(r"^\S+(?:\s+|-)(?:the|a|an|your|this|each|every|it|its)\b", re.I)
...
if name == "vessel_count" and _PATTERN_REF_BEFORE.search(read[:m.start()]) \
        and _REF_THEN_DET.match(m.group(0)):
    continue
```

I tested this against all 10 probes in a scratch copy:
- The three sentences in `test_w5_integfix` pass (no claim).
- "Includes 3 baskets." and "Work Round 4, then make 2 bowls." are still counted.
- Every bypass in the table above is refused again.

Add the bypass strings to `test_w5_integfix.py` as must-refuse cases.

### F2 (MEDIUM): P0-PHOTO-ASSET-REVIEW exists only in a commit message

`git grep "PHOTO-ASSET-REVIEW"` over the whole tree returns nothing. The only mention is the
message of `fd3487a3`. The gap is real:

- `physical_upgrade.upgrade_on_receipt` creates the photo frame with `approved=False`.
- `lead_with_if_qualifying` sets `approved=False` again after the owner attests the photo.
- No production code path ever sets a `PHYSICAL_PRODUCT_PHOTO` frame to `approved=True`. I
  searched `src/` for `.approved =` and `approved=True`. The only setter, `_persist_frames`,
  rewrites frames by position from a new render plan; it is not an asset-truth review.

Mutation M4 removes the fixture's post-attestation approval. Then both photo-led tests fail with
`listing-set certificate (#70) … cannot certify`. So in production a photo-led listing set never
certifies. This fails closed: it is a liveness defect, not a way to publish something unsafe.

**On question (c): is the fixture change honest?** Yes. The original OPUS2 fixture already
inserted an approved frame by fiat. The change only moves that fiat to after the PHYSFIX reset,
and the unapproved-photo test still exercises the unapproved path. It does not mask a safety
defect. But a P0 that is not recorded anywhere tracked breaks the non-negotiable "BUILD_STATE
must stay honest about what does not exist". Add P0-PHOTO-ASSET-REVIEW to BUILD_STATE and the
P0 register before release.

### F3 (MEDIUM, test gap): the merged `carry_permanent` line is never exercised

Mutation M6b replaces `existing.certificate = _withholding.carry_permanent(existing.certificate,
certificate)` with `existing.certificate = certificate`. Both PHYSFIX re-certification tests
still pass:
- `test_the_failed_release_never_publishes_again_after_an_owner_lift`
- `test_a_restated_halt_keeps_every_failed_release_and_the_lift_withholds_them_all`

A probe inside the first test counted 0 `gate.recertified` audit rows, so its "re-certify"
steps never reach the certificate-replacement branch. That test's publish refusal also holds
through `durable_reasons`, independently of the carry. The `blocks_build` reading after
re-certification (True with and without the carry) therefore proves nothing about the carry.

**On question (a): does a re-certification preserve both carries?** Yes, by inspection and by a
direct probe of the two functions:
- `carry_reverification(prev, new)` followed by `carry_permanent(prev, ·)` keeps
  `physical_size_failed`, `quality_reverify`, `reverify_failed={pdf: …}` and the build-blocking
  summary.
- The reverse order gives the same result.
- Both calls read the old certificate. `existing.certificate` is not reassigned until after
  `carry_reverification`.
- The OPUS2 side is covered: mutation M6a, which drops `carry_reverification`, is killed.

What is missing is a test that re-certifies a size-failed version under a new release hash and
asserts `blocks_build` and `physical_size_failed` afterwards. Ideally that release also carries
a re-verification failure, so both carries are tested together.

### F4 (LOW): the owner packet points at deleted kit files

`research/final_build/w4/OWNER_ACTIONS.json` and its byte-identical Command Center copy
`app/command_center/snapshots/OWNER_ACTIONS.json` (lines 211–212) still list
`market-basket-small-1.2.0-TEST.pdf` and `-RECORD-SHEET.pdf` with hashes. `4f136bf7` deleted
those files, and the owner's instruction is "no tester against obsolete versions". The packet is
dated 2026-10-11, but the Command Center serves it. Regenerate it, or mark the basket kit
section superseded by 1.3.0.

### F5 (LOW): duplicate retention key

Both sides of `4f136bf7` added `"listing.adopted_manual"` to `KNOWN_READ_ACTIONS`, and the
resolution kept both copies. Python keeps the last one. Both say `lifetime_total` today, so
there is no behavioural effect yet. Remove one copy.

### F6 (INFO)

Mutation M5 turns `frame.approved = False` in `lead_with_if_qualifying` into a no-op, and the
photo-led suite still passes 8/8. The reset is pre-existing PHYSFIX behaviour. Its only coverage
is the `first.approved is False` assertion in `test_physfix_photo_first`, and that holds anyway
because the frame was created unapproved. This is acceptable once F2 is tracked.

## Answers to the review questions

**(a) Was any behaviour dropped, or a gate relaxed, in the merges?** No.
- `KINDS` holds both `PHYSICAL_SIZE_FAILED` and `QUALITY_REVERIFY`.
  `BUILD_BLOCKING = (TEARDOWN_QA, OWNER_VETO, PHYSICAL_SIZE_FAILED)`. `QUALITY_REVERIFY` is
  publish-only, as designed.
- `reconcile` never touches either kind.
- `for_publish` refuses both. Mutations M7a and M7b are each killed.
- Re-certification preserves both carries (see F3 for the coverage gap).
- `listing.package` is `BUILD` (`_B`, the same class as `chain.rebuild`). Mutation M8
  (BUILD → OBSERVE) is killed.
- I diffed the key sets against each merge's parents: `JOB_CLASS` (key=class), `CADENCES` and
  every agent's `allowed_job_types`. Nothing was dropped and no class changed, for
  `5a248a82` vs `b9245dc0` and `e93b16e`, and for `b593a521` vs `50ef24b` and `fb52cb9e`.
- The PHYSFIX `physical_size.lift` action is present in `approvals.py`, which is unchanged
  from the integration-side parent.
- The R40 merge `b9245dc0` had no conflicts, and `test_physfix` passes 48/48 on the tip.

**(b) Is the size-claim exclusion too broad?** Yes: see F1.

**(c) Is the photo-led fixture change honest?** Yes, it does not hide a safety defect. The
production gap it works around is real and is untracked: see F2.

**(d) Is the digest re-pin justified?** Yes. I rebuilt `launch0.cir_for("basket_small")` at
`b593a521` (release 1.2.0, digest `b65d57e9…`) and at `5a248a82` (1.3.0, digest `54758cbf…`) and
diffed the full `design_geometry` JSON. The only difference is
`pieces[0].rows[10].stitches[0..59]`: loop `both` → `back`. That is Rnd 11, all 60 stitches,
and nothing else changed. Mutation M3, which reverts the back loop in `vessels.py`, makes
`test_hold_free_products_are_unchanged_except_for_halts` fail on `basket_small`.

**(e) Are the test changes stricter or equal?** Yes for each, except that the new size-claim
test is too narrow (F1).

| Change | Assessment | Mutation |
|---|---|---|
| `test_w5_integfix` (new) | New. Covers only false positives, with no adjective-"round" negatives. | M1: fix reverted → 0/1. M2: regex widened to `\w+` → 0/1. **Killed**, but the F1 bypass passes it. |
| `test_physfix` digest re-pin | Equal. Correct for 1.3.0. | M3 **killed**. |
| `test_physfix` kit / listing-package paths 1.2.0 → 1.3.0 | Equal. Points at the current files. | n/a (the old files are gone) |
| `test_opus2_photo_led_gallery` fixture | Equal. Same fiat approval, applied after the reset. | M4 (approval removed) → 6/8. M5 survives (F6). |
| `test_opus2_size_claims` pin 1.2.0 → 1.2.1 | Equal. Follows PDF1's 1.2.1 release. | n/a |
| `test_pdf_premium` non-emptiness | Stricter. | M10a (no render frames) → the renders test fails. M10b (empty page list) → the NOT-FOR-SALE test fails. **Killed.** |
| `cc_mock/check.mjs` More-menu pin | Equal or stricter (adds "production"). | Not run (browser suite out of scope). |

**(f) Do the regenerated kits match `--check`?**
`python3 research/final_build/w4/tester_kit_coaster.py --check` exits 0, with
`matches_committed: true` for both `basket_small` 1.3.0 and `hexagon_coasters` 1.2.1. No 1.2.x
basket kit files remain in `tester_kit/`.
- The kit doc and the listing package state one all-inclusive ceiling, CA$66.00 (CA$65.90 to
  the tester plus a CA$0.10 allowance).
- The remaining "CA$59.65" (`BASKET_KIT_FOR_OWNER_APPROVAL.md:155`) is labelled as the risk
  matrix's basis, "not a second ceiling", which is acceptable.
- `test_the_kit_ceiling_is_checked_from_above_and_no_stale_figure_remains` passes.

## Mutation results

| ID | Mutation | Test | Result |
|---|---|---|---|
| M1 | Remove the round/row skip in `claims_in` | test_w5_integfix | 0/1: **killed** |
| M2 | `_PATTERN_REF_BEFORE` → `\w+\.?\s*$` | test_w5_integfix | 0/1: **killed** |
| M3 | Basket Rnd 11 loop back → both | test_physfix::test_hold_free_products… | FAIL (basket_small): **killed** |
| M4 | Fixture approval after attestation removed | test_opus2_photo_led_gallery | 6/8: **killed** |
| M5 | `lead_with_if_qualifying` no longer resets approval | test_opus2_photo_led_gallery | 8/8: survived (F6) |
| M6a | Drop `carry_reverification` in `_persist_release` | test_opus2_reverify_withhold::…f21… | 0/1: **killed** |
| M6b | Drop `carry_permanent` in `_persist_release` | test_physfix (both re-cert tests) | 2/2: **survived** (F3) |
| M7a | Drop the re-verification refusal in `for_publish` | test_opus2_reverify_withhold | 4/5: **killed** |
| M7b | Drop the physical-size refusal in `for_publish` | test_physfix::…after_an_owner_lift | 0/1: **killed** |
| M8 | `listing.package` BUILD → OBSERVE | test_opus2_listing_package | 12/13: **killed** |
| M9 | `PHYSICAL_SIZE_FAILED` removed from `BUILD_BLOCKING` | test_physfix | 47/48: **killed** |
| M10a | `test_pdf_premium` renders filter → a kind that matches nothing | test_pdf_premium (renders) | FAIL: **killed** |
| M10b | `test_pdf_premium` page list emptied | test_pdf_premium (NOT FOR SALE) | FAIL: **killed** |

## Test table (tip `5a248a82`, unmutated)

| Suite | Result | Time |
|---|---|---|
| test_w5_integfix.py | 1/1 pass | <1 s |
| test_opus2_size_claims.py | 11 OK, 0 failed | 249 s |
| test_opus2_photo_led_gallery.py | 8 OK, 0 failed | 459 s |
| test_opus2_reverify_withhold.py | 5 OK, 0 failed | 40 s |
| test_opus2_listing_package.py | 13 OK, 0 failed | 642 s |
| test_physfix.py | 48/48 pass | 463 s |
| test_pdf_premium.py | 27 OK, 0 FAIL | 133 s |
| test_launch0_listing_truth.py | 14 OK, 0 FAIL | 450 s |
| test_v11_autonomy_timeline.py | 7 OK, "PASS: 0 failing" | 94 s |
| test_w4_fmbatch1_retention_guard.py | 5 OK, 0 FAIL | 31 s |
| test_vacuity.py | 8 OK, 0 FAIL | 10 s |
| tester_kit_coaster.py --check | rc 0, both kits `matches_committed: true` | n/a |
| pwa_browser | not run (not in the requested set; Node 22 is present) | n/a |

Every requested suite exits 0. All the suites passing does not clear F1: none of them contains
a case for the adjective "round".

## Required before SHIP

1. Fix F1, using the suggested fix or an equivalent, and add the bypass strings above to
   `test_w5_integfix.py` as must-refuse cases.
2. Record P0-PHOTO-ASSET-REVIEW in BUILD_STATE and the P0 register (F2).

Recommended: add the both-carries re-certification test (F3), regenerate or supersede the owner
packet (F4), and remove the duplicate retention key (F5).
