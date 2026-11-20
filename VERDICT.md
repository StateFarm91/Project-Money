VERDICT: SHIP 96f5b294202ce5dbe774369f339d277bb710333f

# Independent review: eng/vis-identity @ 96f5b294 (FULL), slice 1, onto claude/w6-INTEG3 @ 39b92619

Reviewed 2026-11-20 (UTC).

## The merge

- `claude/w6-INTEG3` (39b92619) is an ancestor of 96f5b294, so the merge is a fast-forward to
  96f5b294. There are no conflicts.
- The diff to the base also carries `eng/visual-factory` (c774d740) and `eng/motif-reservation`.
  Those already have a SHIP verdict on `review-results/visual-c774d740`.
- This review covers the ENG-VIS-IDENTITY commit 96f5b294. Its review request and
  `IDENTITY_OWNER_DECISIONS.md` were both read.

## Suites, run on the merged tree

The dependencies were installed from `requirements.lock` and `requirements-test.lock`.

**Merged tree: 52 of 52 suites pass (rc=0).** They are every suite named for identity, laura,
vision_judges, outfit, model_photography or canonical, plus:

- test_model_spend_paths
- test_cost_governance_wave2
- test_w4_resume_runner
- test_v11_autonomy_timeline
- test_w4_fmbatch1_retention_guard
- test_etsy_oauth_callback
- test_vacuity
- test_visual_*
- test_v2_gallery_consistency
- test_w4_readback_evidence
- test_compiler, test_reverse and test_twin

**Base (39b92619): the same set passes, 47 of 47.** The five extra suites on the merge are the
new ones.

**With the real face models installed** (`scripts/fetch_face_models.py`; both pinned SHAs
verified; onnxruntime 1.29.0):

- `test_eng_vis_identity` passes 38 of 38.
- An independent rerun of `calibrate()` on the committed set reproduces the committed evidence
  exactly: `evidence_sha256` 6884612e649a8afc…, match_at 0.64, refuse_below 0.54, FAR 0/10,
  FRR 0/12, FAR upper bound 25.9%, production_ready False.
- Flipping one bit of one canonical reference makes `calibrate()` raise `ReferenceMismatch`.
- `test_v3_identity_qualification` fails 1 of 24 in this configuration. See F1.

## Critical checks

- **Laura's references: OK.**
  - No canonical asset is in the diff. `test_canonical_references_untouched` passes.
  - Calibration refuses on any reference SHA mismatch (verified above).
  - `measure_biometric` re-hashes every reference before use. A mismatch is UNMEASURED, never PASS.
  - `trial_validity` now makes all three references (face, torso, full body) mandatory.
  - There is no model substitution: the embedder name, version and weights SHA must equal the
    qualification record's, and unpinned weights are refused at load.
- **Identity PASS: OK.**
  - `assess()` gives PASS only when `_assess` says PASS **and** the biometric certification is
    `qualified` **and** the judges agree.
  - A qualified certification needs a record that meets all of these:
    - it is on `PRODUCTION_QUALIFICATIONS`, which is still empty;
    - it carries a production-scoped owner decision;
    - it cites production-ready calibration: at least 30 genuine samples, at least 300
      impostors, a FAR upper bound of 1% or less, and FRR of 10% or less.
  - `gate_status()` maps any non-PASS `verdict` to UNKNOWN.
  - The legacy `QUALIFIED_EMBEDDERS` path and fixture records cannot reach a consumer PASS.
  - With the models installed but unqualified, production `RealJudges` reads
    `UNKNOWN / HOLD / UNMEASURED` (probed).
- **Licensing: OK.**
  - YuNet is MIT and SFace is Apache-2.0. InsightFace is explicitly rejected.
  - The training-data caveat is disclosed as part of owner Decision 1.
  - All 16 calibration samples are Brambleloop- or owner-generated images, with no real
    person's photograph. A test asserts this on the licence field.
- **Second judge: OK.**
  - It is OpenAI gpt-4.1-2025-04-14, a different provider from the Anthropic first judge.
  - It has a distinct judge id, and the same judge twice counts as one reading
    (`person_readings` and `_judges`).
  - It spends through `GatewayVisionJudge`: `check_budget` reserves before the call, then
    releases to actual, against the ceilings. gpt-4.1 is priced, so an unpriced model would be
    refused. OpenAI's own `openai-vision` paid-provider gate also applies.
  - With no key it is `None`, so identity HOLDs with "1 independent judge reading(s)".
  - Disagreement gives HOLD with the reason. Drift gives REFUSE.
- **Outfits: OK.**
  - `claim()` is idempotent: it returns the held outfit.
  - Claims survive a restart: tested with a file-backed DB that is disposed and reopened.
  - Exact twins and near-duplicates of another listing's outfit or of the reference clothing
    are skipped, so a listing gets UNKNOWN rather than a reused outfit.
  - The claim is a compare-and-set `UPDATE … WHERE listing=''`. My interleaved race probe
    showed the loser falls through to the next free outfit (A got o-navy, B kept o-rust).
  - A per-frame blind reference check is added. Identity records are append-only and
    idempotent (unique on image_sha256 and evaluation_sha256), and they survive a restart.
- **Owner decisions doc: honest, with one understatement (F4).**
  - It says plainly that identity cannot PASS today.
  - It does not claim anything was generated or spent.
  - The licence and cost tables match the code's pinned prices.

## Mutation testing

My own mutants, run against test_eng_vis_identity, test_v3_identity_qualification,
test_model_photography and test_visual_campaign_standard:

| mutant | result |
|---|---|
| qualification hold removed in `assess` | KILLED |
| production calibration floors removed from `validate_qualification` | KILLED |
| disagreement counted as agreement | KILLED |
| `gate_status` ignores `verdict` | KILLED |
| biometric reference SHA check removed | KILLED |
| three-references rule removed | KILLED |
| calibration reference SHA check removed | KILLED |
| outfit distinctness skip removed | KILLED |
| outfit idempotence removed | KILLED |
| "one judge is enough" (`len(verdicts) < 2` → `< 1`) | SURVIVED, equivalent: the older guard in `trial_validity` (`missing_judge_pair`, line 157) still holds the frame. Defence in depth, not a gap. |
| outfit CAS removed (`AND listing=''` dropped) | SURVIVED, a real test gap (F3). The code is correct; nothing pins it. |

## Findings (none blocking)

**F1 (medium): fix before slice 2 bakes the models into the image.**
- `test_v3_identity_qualification::test_production_configuration_stays_unknown` asserts
  `prod.embedder is None`.
- That assertion fails whenever `BRAMBLELOOP_FACE_MODEL_DIR` points at the installed models.
  It will therefore fail on the production image once `fetch_face_models.py` runs in the build.
- The behaviour is still safe: the frame reads HOLD and UNMEASURED.
- The fix is to assert `qualification is None` and the HOLD verdict, not `embedder is None`.

**F2 (medium): the calibration methodology must change before owner Decision 4.**
- `match_at` is set to the highest impostor score plus a margin, and FAR is then measured on
  those same impostors. So FAR is 0 by construction (in-sample).
- At 300 impostors, 0/300 gives an upper bound of 0.99%, which just clears the 1% floor. A
  production-ready claim could therefore rest on an in-sample threshold.
- Before Decision 4, require a held-out split: thresholds fixed on one part of the set, FAR and
  FRR reported on the rest.

**F3 (low).**
- No test exercises the compare-and-set outfit claim, so the mutant that drops it survives.
  Add an interleaved-claim test like the race probe above.
- Edge case: if two claims for the same listing race and the losing outfit already has `uses`,
  it is not released, and the listing then holds two outfits. Downstream reservation checks
  catch this and the frame goes UNKNOWN.

**F4 (low): the doc understates the reservation.**
- The doc says "CA$0.024 reserved" per second-judge read.
- The actual reservation is about CA$0.092 per read: `GatewayVisionJudge` reserves
  `providers.IMAGE_TOKENS_ESTIMATE` (6000) × 4 images on gpt-4.1.
- The actual cost of about CA$0.012 is right. Over-reserving is the safe direction, but it
  holds about 4× more ceiling headroom while a call is in flight.

**F5 (info).**
- `transports_independent()` is not called by production code. Independence is actually
  enforced by distinct judge ids.
- It also returns True when either model is unknown. If it becomes a gate, require both
  models to be known and different.

## What is not verified

- No live OpenAI, BFL or Railway call was made.
- `onnxruntime` is not in the lock, which the request acknowledges as slice 2.
- Production identity correctly remains HOLD.
