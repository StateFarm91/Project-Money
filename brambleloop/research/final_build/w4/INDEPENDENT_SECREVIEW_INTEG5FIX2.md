# Independent review INTEG5FIX2: commit 2cb2a409 on `claude/w5-INTEG1`

- **Reviewed:** `2cb2a409` ("W5-INTEG1: fix review INTEG5FIX F1-F5"), diffed against `5a248a82`.
- **Prior review:** `INDEPENDENT_SECREVIEW_INTEG5FIX.md` (origin/claude/w5-SECREVIEW-INTEG5FIX).
- **Date:** 2026-11-01 (UTC). Read-only review. No deploy, no Railway, no production, no spend, no PR.
  Mutations were run in a throwaway `git worktree` and reverted. The worktree was then removed.

## Verdict: **SHIP**

All five findings are fixed. Each new test fails under the mutation it is meant to catch. No gate is
relaxed and no test is weakened. Every changed hunk is accounted for. One LOW residual and two INFO
notes follow. None of them blocks.

## Scope check: what the commit changes

| File | Change | Assessment |
|---|---|---|
| `gates/size_claims.py` | `count` is never exempted. `vessel_count` is exempted only when it follows a round/row label **and** a determiner comes right after the number (`_REF_THEN_DET`). | Narrower than at 5a248a82. This is a strict tightening. |
| `tests/test_w5_integfix.py` | +2 tests (15 shape/row bypass texts; re-certification carry). Existing test unchanged. | Additive only. |
| `ops/retention.py` | Removes the second `"listing.adopted_manual"` literal. | At 5a248a82 the two entries were byte-identical (lines 129 and 135). The dict value is unchanged. |
| `OWNER_ACTIONS.json` x2 | Kit 1.2.0 → 1.3.0 (version, content_hash, two PDF names and hashes). | Verified. See F4. |
| `BUILD_STATE.md` | New top paragraph for Batch 5 (says NOT certified, NOT deployed) and the open P0 gap. | Honest. |
| `COORDINATION.json` | New entry `P0-PHOTO-ASSET-REVIEW` (unowned). 9 lines re-serialised with `§` written as a literal `§`. | The re-serialisation does not change meaning. I checked each pair: they are equal once the escape is decoded. The file parses as JSON. See INFO-2. |

Nothing else changed.

## Findings

### F1 (HIGH, prior): size-claim exemption. **FIXED**

**Fuzzing** (`gates.size_claims.check_texts({"listing title": t})`):

| Text | State | Note |
|---|---|---|
| Round 3 baskets the set | FAIL (3) | |
| round 2 bowls and a basket | FAIL (2) | |
| Round-3 the baskets / Round. 3 the baskets / round: 3 the baskets | FAIL (3) | The punctuation breaks `_PATTERN_REF_BEFORE`, so the exemption does not apply. |
| Round 2 baskets, each a size | FAIL (2) | |
| Round 3 the basket sizes | FAIL (3) | Caught by `count`, which is never exempted now. |
| Round 3 the nesting baskets / Round 3 the trio of baskets | FAIL | Caught by other patterns. |
| Round 2 the baskets and 3 bowls | FAIL (3) | |
| Round 3 sizes / Round 3-piece basket set | FAIL (3) | |
| **Round 3 the baskets set**, **Row 2 a basket each**, **Rnd 3 your baskets**, **ROUND 3 THE BASKETS**, **Round 3 each basket**, **Round 3 every basket**, **Round 3 a basket set**, **Round 2 its baskets**, **Rnd 3-the baskets**, **Round 10-piece the set**, **Round 2 a basket set for each** | PASS | Residual R1 (below). |
| If it ruffles or cups Up to Rnd 10 the basket should lie flat. | PASS | Correct: this is the 1.3.0 tip, not a claim. |
| Up to Rnd 10 the basket should lie flat. / Row 3 the bowl should cup. | PASS | Correct. |

**Mutations on `test_w5_integfix.py`:**

| Mutation | Result |
|---|---|
| M1: restore `size_claims.py` from 5a248a82 (broad exemption) | **KILLED**: `test_round_as_a_shape_or_row_never_hides_a_real_size_claim` fails on `'Round 3 baskets'`. Exit 1, 2/3. |
| M2: drop only the `_REF_THEN_DET` condition | **KILLED** (same test, `'Round 3 baskets'`). |
| M3: remove the exemption entirely | **KILLED**: `test_a_round_or_row_number_is_a_place_in_the_pattern_not_a_count` fails on the 1.3.0 tip (`'10 the basket'`, count 10). |

So the exemption is pinned from both sides.

**R1 (LOW, residual, not blocking).** If a round/row label is followed by a number and then a
determiner (`the/a/an/your/this/each/every/it/its`), the `vessel_count` match is still exempted,
whatever the determiner is followed by. Examples: "Round 3 the baskets set", "Round 3 each basket",
"Round 3 a basket set". In each of these, putting the same words after a neutral prefix ("Lovely 3 the
baskets set", "Lovely 3 each basket", "Lovely 2 a basket set for each") gives FAIL. So the exemption
is what lets them through, not a gap in the pattern.

I rate this LOW because every residual is ungrammatical as a size promise. The natural shape-adjective
forms ("Round 3 baskets", "Round 3-piece basket set", "Round three sizes") are all refused, and
`count`, `vessel_set`, `nesting` and `several_sizes` still fire inside the same sentence. A grep of
`src/brambleloop` finds only one live string in this shape: "Rnd 10 the".

Optional hardening, if wanted: exempt only when the vessel noun directly follows the determiner and
something verb-like comes after it (for example `should|will|is|must`). Alternatively, exempt only the
abbreviation `Rnd`/`Row`, never the word `Round`, which doubles as a shape adjective.

Words that are not exempted: "Round three the baskets" also PASSes. `_NUM` accepts number words and
`\S+` takes "three", so number-word variants are in the same residual class.

### F3 (MED, prior): re-certification carry test. **FIXED, meaningful**

`test_a_recertified_release_keeps_both_permanent_and_reverify_withholdings` calls the real
`pipeline._persist_release` twice with different release hashes on a fresh SQLite DB. It asserts that
`gate.recertified` was audited, which shows the `elif existing.release_hash != release_hash` branch
ran. It then asserts that both `PHYSICAL_SIZE_FAILED` and `QUALITY_REVERIFY` survive, with
`blocks_build` and `blocks_publish` both true.

**The stub context is honest.** I read everything `_persist_release` touches (lines 1537 to 1640):
`ctx.db`, `ctx.enqueue`, `ctx.audit`, `ctx.job.agent`, `ctx.job.id` and `ctx.phase`. It does not use
`ctx.job.inputs`. The stub supplies exactly these, with a real `Job` row for provenance. Its signatures
match `runtime/worker.JobContext.enqueue(agent, job_type, inputs, **kw)` and `audit(action, **kw)`. The
withholdings come from the real `withholding.record` and `record_reverification`, not from hand-built
dicts.

| Mutation (in `runtime/pipeline.py`) | Result |
|---|---|
| M4: `existing.certificate = certificate` (no `carry_permanent`) | **KILLED**: `physical_size_failed` is missing. Exit 1. |
| M5: `carried = False` (no `carry_reverification`) | **KILLED**: `quality_reverify` is missing. Exit 1. |
| M6: `elif False:` (skip the re-certification branch) | **KILLED**: `gate.recertified` is not audited. Exit 1. |
| M7: `if False:` in front of the `reverify-after-recert` enqueue | **SURVIVES** (3/3). See INFO-1. |

**INFO-1.** The test does not assert that `gate.quality` is enqueued when a re-verification is carried.
That enqueue is what lets the new content clear the carried hold promptly. This is a liveness gap, not
a safety one: without the enqueue the hold stays in place. Suggested one-line addition:
`assert any(a[1] == "gate.quality" for a, _ in ctx.enqueued)`.

### F2 (MED, prior): P0-PHOTO-ASSET-REVIEW recorded. **FIXED (accurate, actionable), with one addition**

I checked each claim in the entry against the code:

- `physical_upgrade.upgrade_on_receipt` creates the frame with `approved=False` (`publish/physical_upgrade.py:173`). Confirmed.
- `lead_with_if_qualifying` resets it to `approved=False` with the quoted reason (`:396-397`). Confirmed.
- No production path approves a photo frame. Confirmed.
- The entry says this fails closed, so it is a liveness gap and not a safety one. Confirmed: `release_gates` and `physical_upgrade:291` require `frame.approved`.

The `needed` text is actionable. It names step-up, a reason, an audit row, binding to the frame's sha256
and to the owner attestation, a `qualifying_photos` verdict, refusal tests and the files involved.
BUILD_STATE carries it as an open P0 with honest status. It is unowned in COORDINATION.

**Addition for whoever builds it:** the entry says "only visual/gallery_persist approves". That is
incomplete. `runtime/release._persist_frames` (`:2617-2645`) also writes `row.approved = not reasons`
by **position**, and it overwrites `asset_class`, `sha256` and `claims` on whatever row holds that
position. It has no guard for `PHYSICAL_PRODUCT_PHOTO`. If a render rebuild runs after the photo has
moved to position 1, it would replace the photo row with an approved render rather than approve the
photo. That cannot lead to a falsely approved photo, so it is not a safety issue for this commit. I
have not verified it end to end, and it predates this commit. The asset-review work should guard it
and test it.

### F4 (LOW, prior): owner packet kit 1.3.0. **FIXED, verified**

| Item | OWNER_ACTIONS.json | Actual |
|---|---|---|
| version | 1.3.0 | `launch0.cir_for("basket_small").version` = 1.3.0; KIT_MANIFEST 1.3.0 |
| content_hash | c4aa14a0…c659c | `quality.tester_kit.content_hash()` = c4aa14a0…c659c; KIT_MANIFEST same |
| market-basket-small-1.3.0-TEST.pdf | fcdded05…a51a499 | `sha256sum tester_kit/…-TEST.pdf` = fcdded05…a51a499 |
| market-basket-small-1.3.0-RECORD-SHEET.pdf | 83298112…23bc9 | `sha256sum` = 83298112…23bc9 |
| OUTREACH.md | bed9dbe2…7b3f | `sha256sum` = bed9dbe2…7b3f |

The two copies (`research/final_build/w4/OWNER_ACTIONS.json` and
`app/command_center/snapshots/OWNER_ACTIONS.json`) are **byte-identical**: `cmp` agrees and both
sha256 hashes are e02d1fe4…a21f. No `1.2.0` remains in the file.

### F5 (LOW, prior): duplicate retention key. **FIXED**

At 5a248a82 the two `"listing.adopted_manual"` entries (lines 129 and 135) had identical values and
comments. Python keeps the last one, so removing one changes nothing at runtime. The retention guard
suite passes.

### INFO-2: COORDINATION.json re-serialisation

The commit rewrites 9 unrelated lines, changing the escape `§` to a literal `§`. The JSON value is
identical, but the diff is noisy. Use `ensure_ascii=True` next time, or keep it.

## Repro

```
git fetch origin && git checkout 2cb2a409 && cd brambleloop
PYTHONPATH=src python -c "from brambleloop.gates import size_claims as SC
for t in ['Round 3 baskets','Round 3 the baskets set','Up to Rnd 10 the basket should lie flat.']:
    print(SC.check_texts({'listing title': t})['state'], t)"
# mutation M1
git show 5a248a82:brambleloop/src/brambleloop/gates/size_claims.py > src/brambleloop/gates/size_claims.py
PYTHONPATH=src:tests python tests/test_w5_integfix.py; echo $?   # 1
git checkout src
```

## Tests (run one at a time from `brambleloop/` with `PYTHONPATH=src:tests` on 2cb2a409; run_tests.sh not run)

| Suite | Result | Exit |
|---|---|---|
| test_w5_integfix.py | 3/3 passed | 0 |
| test_opus2_size_claims.py | 11 OK, 0 failed | 0 |
| test_w4_b2close.py | 18 passing, 0 failing | 0 |
| test_w4_fmbatch1_retention_guard.py | 5 OK | 0 |
| test_physfix.py | 48/48 passed | 0 |
| test_vacuity.py | 8 OK | 0 |
