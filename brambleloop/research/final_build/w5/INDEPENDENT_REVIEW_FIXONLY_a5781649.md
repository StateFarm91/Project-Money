# Independent delta review: W6 FIX-ONLY rebuild (a5781649, merged at ccd45933)

Branch `claude/w6-fix-only-rebuild`. I reviewed `git diff 9e8665c3 a5781649` line by line and
sanity-checked the merge `a5781649..ccd45933`. Repro and mutants were run in throwaway
worktrees of ccd45933, which have since been removed. `/home/user/bl-runs/wt-fixonly` was not
touched. Python: `/home/user/bl-runs/venv-integ4/bin/python`, run from `brambleloop/` with
`PYTHONPATH=src:tests`.

## Verdict: DO NOT SHIP ccd45933

**N1 (taxonomy-drift leak) is fixed.** It is fixed end to end, and the tests kill its mutants.

**N2 is fixed only on the path its unit test exercises. The fix has two gaps:**
- **R1 (MEDIUM).** A `listing.live_update` card raised by an earlier passing candidate stays
  open after a later candidate is rejected. The card tells the owner to apply "the newest audit
  `listing.fix_candidate`", and that audit is now the rejected, gate-failing candidate. This is
  the same harm N2 described, so the owner can still end up pasting unvalidated copy onto a live
  listing.
- **R2 (MEDIUM, test gap on the core fix).** Remove `blocking=blocking` from the only call site
  (`release.py:1320`) and the whole N2 fix is undone, yet that mutant SURVIVES every
  fix-only test. The N2 test calls `_fix_only_candidate` directly and never goes through
  `listing.seo`. The commit says "the N1 and N2 mutants are each killed". That holds only for
  the helper-side mutant.

Both are small fixes, but between them a gate-failing candidate can still reach the owner as
copy to apply, and the regression guard for the N2 fix is missing.

## Tests run on ccd45933 (clean tree)

| Test | Result |
|---|---|
| tests/test_w6_fix_only_rebuild.py | 11/11 OK, "0 failure(s)", EXIT 0 |
| tests/test_cert_rebuild_chain.py | 10/10 OK, "PASS: 0 failing", EXIT 0 |
| tests/test_w5_v0_paid_provider_gate.py | 52/52 passed, EXIT 0 |
| tests/test_w4_fmbatch1_drift.py (taxonomy_drift) | 10 passing, 0 failing, EXIT 0 |
| tests/test_w4_placemat_reprice.py (`_reprice_on_plan_drift`) | 4 OK, EXIT 0 |
| tests/test_w4_launch_review_card.py | 7 OK, EXIT 0 |
| tests/test_w4_listready.py | 27 OK, 0 FAIL |
| tests/test_w4_launch_review.py (`launch_review.run`) | **12 OK, 6 FAIL, EXIT 1. Pre-existing, not from this delta.** |

The 6 `test_w4_launch_review.py` failures also occur at 9e8665c3. The test is tied to the
clock: `BudgetExceeded('launch review batch launch_image_review_2026_10 is expired:
authorisation expired at 2026-11-05T09:00:00+00:00')`, and today is 2026-11-07. The failing
tests are:
- `test_the_run_queues_each_release_once_...` (KeyError 'queued')
- the three `test_n2_*` tests
- `test_the_ceiling_reverts_when_the_batch_completes`
- `test_a_refused_review_call_...`

The consequence is that `launch_review.run` currently has **no working behavioural test at
all**, so its new `without_fix_only` call is guarded only by a source-text check (see R3). I
did not run the other ~110 tests that import release.py. Their status is UNKNOWN, not PASS.

## Merge sanity (a5781649 to ccd45933)

- `git merge-tree --write-tree a5781649 0b3d54ee` gives `e3653af4...`. That equals
  `ccd45933^{tree}`, so the merge is exactly git's clean automatic merge and has no hand edits.
- The only file both sides changed is `runtime/release.py`. The V0 side changes only
  `handle_support_triage` (support defects escalate and reconcile holds), and that hunk does
  not touch the fix-only code.
- The V0 change to `ops/owner_queue.py` only adds packet text and card enrichment. `ensure()`,
  which N2 relies on, is unchanged.
- `support/defects.py` enqueues only `cir.twin` and `cir.reverse`. It never touches
  `fix_only`.

## Re-check of the prior findings

| Prior | Status at ccd45933 | Evidence |
|---|---|---|
| N1 HIGH taxonomy-drift leak | **FIXED** | Repro P1: `_last_seo_inputs carries fix_only: None`. The drift re-queue jobs are `['listing.seo','launch.plan','marketing.schedule']`. Mutants M1 and M3 are KILLED. |
| N2 MED rejected candidate still carded | **PARTIAL** | Repro P2 (through the handler, with a gate forced to block): `ok: False`, `rejected` recorded, no card. But see R1 and R2. |
| N3 LOW Etsy-id draft guard untested | **FIXED** | M6 KILLED. |
| N4 LOW old live branch in `_persist_listing` | **OPEN** (not claimed) | `release.py:2188-2208` still writes the weak audit (`description_chars`) and the old card text under the same key. |
| N5 LOW flow_health reads a fix-only `ok: True` as a handoff | **OPEN** (not claimed) | `ops/flow_health.py:62` is unchanged. It does not consult `stopped_before` or `candidate_only`. |
| N6 LOW consumer-side strips untested | **PARTIAL** | A source-text pin now exists (M2, M7 and M8 are KILLED), but it is not behavioural (R3). |
| F5-F8 and the INFO items from 6cbc08e6 | OPEN (not claimed) | Unchanged. |

The commit message claims N1, N2, N3 and N6, not N1 to N6. N4 and N5 were not addressed.

## Findings (ranked)

### R1 — MEDIUM: a stale open `listing.live_update` card points the owner at a rejected candidate
- **Where.**
  - `release.py:2138-2144` is the rejected path. It returns before the card, but it neither
    closes nor restates an **already open** card for the same key.
  - `release.py:2149-2158` holds the card text: "the full candidate ... is in the newest audit
    'listing.fix_candidate' ... If it is better, apply it in Shop Manager".
  - `owner_queue.ensure` (`ops/owner_queue.py:180`) keeps one open row per key, and the card is
    open until the owner acts.
- **Scenario.**
  1. Fix-only run A on a live listing produces a passing candidate. The card opens.
  2. Before the owner acts, fix-only run B (a new token, for example after a policy or tag-truth
     update) produces a candidate the gates block. Run B writes a newer `listing.fix_candidate`
     audit with `rejected: [...]`.
  3. The owner follows the open card to "the newest audit" and applies run B's gate-failing
     copy to the live Etsy listing.
- **Repro** (`repro_fixonly4.py` P3, on ccd45933):
  ```
  P3 after passing candidate, open cards: [(1, 'Compare the rebuilt listing copy for cloudline-baby-blanket@1.2.0 ...')] ok True
  P3 after rejected candidate, open cards: [(1, 'Compare the rebuilt listing copy ...')]
  P3 newest listing.fix_candidate rejected: ['TITLE_OVER_LIMIT: forced by repro']
  RESULT ... P3_STALE_CARD_POINTS_AT_REJECTED True
  ```
- **Why the test misses it.** `test_a_rejected_candidate_is_never_put_to_the_owner`
  (`tests/test_w6_fix_only_rebuild.py:262-264`) first marks every existing card `done`, so it
  never sees this case.
- **Fix.** Use one of these, or both:
  - Have the card name the specific audit id (or a candidate hash) it refers to, not "the
    newest".
  - On the rejected path, restate or close an open card for the key. For example, mark it done
    with a note, or rewrite it to say that the latest candidate was refused and the earlier
    audit is id N.
- **Test.** A passing fix-only run, then a blocked one, with the card left open in between.

### R2 — MEDIUM (test gap): the N2 call-site wiring is unprotected
- **Where.** `release.py:1320` passes `blocking=blocking`. The helper defaults to
  `blocking=None` (`release.py:2111`), so dropping the argument silently disables the gate.
- **Mutant M4.** I removed `, blocking=blocking`. It **SURVIVES** three tests:
  - `test_a_rejected_candidate_is_never_put_to_the_owner`
  - `test_a_fix_only_rebuild_never_touches_a_live_listing_and_never_reaches_publish`
  - `test_a_live_listing_keeps_its_search_profile_and_the_candidate_is_complete`

  Under M4, repro P2 shows the exact pre-fix N2 behaviour: `rejected: []`, card opened,
  `listing.seo ... {'ok': True, 'candidate_only': True}`.
- **Fix.**
  - Make `blocking` a required keyword with no default.
  - Add an end-to-end test that drives `listing.seo` through a real fix-only chain with a
    forced gate failure. Monkeypatching `seo_mod.check_listing_limits` is enough, as in
    `repro_fixonly4.py`. The test should assert `ok False`, a non-empty `rejected` and no card.

### R3 — LOW (test gap): the N6 source pin does not prove the strip is applied
- **Where.** `test_every_chain_re_drive_strips_the_bound` (`tests/test_w6_fix_only_rebuild.py:238-249`)
  only asserts that the text `"without_fix_only("` appears in each function's source.
- **Mutant M2b.** In `launch_review.py:530` I replaced `{**without_fix_only(last), INPUT_KEY`
  with `{**last, **without_fix_only(last), INPUT_KEY`. The `fix_only` key survives the merge,
  and the mutant **SURVIVES**.
- **Why it matters.** No test exercises `launch_review.run` behaviourally with `fix_only`.
  `test_w4_launch_review.py` is currently red anyway, because it is tied to the clock.
  `launch_review` copies a build's **inputs**, which carry the flag, so this strip is a real
  guard, not defence in depth.
- **Fix.**
  - Add a behavioural `launch_review.run` test that follows a fix-only build and asserts the
    enqueued inputs lack `fix_only`.
  - Fix the clock dependence in `test_w4_launch_review.py`: inject `now` or set the batch
    expiry relative to now.

### R4 — LOW: live-row candidates still skip the post-persist validations before being put to the owner
- **Where.** `release.py:1318-1322` returns before these checks:
  - `_judge_search_hero`
  - `listing_disclosure_finding` (owed disclosures)
  - `_support_knowledge`'s PDF/listing/FAQ terms-divergence check (`release.py:1414-1422`),
    which is itself a stop condition on the ordinary path
- **Effect.** A live-row candidate is carded once the pre-persist `blocking` list is empty,
  even if its description would fail the terms-consistency or owed-disclosure check. N2
  covers only `blocking`. This is a residual of the original N2 concern, which named these
  checks explicitly.
- **Fix.** Either run the read-only parts of these checks against the candidate text, or have
  the card state that these checks were not run.

### R5 — LOW: N4 and N5 are still open
- **N4.** The duplicate live branch in `_persist_listing` is at `release.py:2188-2208`. It uses
  the same card key with the old text and the weak audit.
- **N5.** At `ops/flow_health.py:62`, a fix-only `listing.seo` returns `ok: True` with no
  `launch.plan`. Both the candidate path and the draft path do this, so flow health reports a
  stall. Fix: add `and not o.get("stopped_before")`.

### INFO
- **F5.** `LIVE_STATES` still duplicates `core/listing_state`.
- **F6.** The draft lineage and `release_hash` still advance while the old price is kept.
- **F7.** `fix_only` is still not part of the idempotency key.
- **F8.** There is still no production caller of `fix_only`.
- **Rejected path audit.** The rejected path writes `listing.fix_candidate` (with `rejected`)
  and `chain.fix_only_stopped`, but not `listing.seo_blocked`. Readers that key on
  `listing.seo_blocked`, such as production_inventory, do not see the rejection. It is
  recorded, though, so this is acceptable.

## Mutation results (each applied alone in a fresh throwaway worktree of ccd45933)

| Mutant | Change | Tests run | Result |
|---|---|---|---|
| M1 (N1) | `taxonomy_drift._last_seo_inputs` returns `dict(i)` | drift-requeue test, re-drive test, plus repro P1 | **KILLED** (both tests fail; P1_OK False) |
| M2 (N1/N6) | `launch_review.py:530` uses `{**last, ...}` | re-drive source test | **KILLED** (source pin) |
| M2b (N6) | `{**last, **without_fix_only(last), ...}` (the call is present but has no effect) | re-drive source test | **SURVIVED** (R3) |
| M3 (N1) | `without_fix_only` returns its input unchanged | re-drive, drift-requeue, ordinary re-price | **KILLED** (2 of 3 fail; the ordinary re-price test passes alone) |
| M4 (N2) | the call site drops `blocking=blocking` (`release.py:1320`) | rejected-candidate, live-listing, live-profile tests, plus repro P2 | **SURVIVED** (all 3 pass; P2 shows a card raised with ok True) (R2) |
| M5 (N2) | `if rejected:` becomes `if False:` in the helper | rejected-candidate test | **KILLED** |
| M6 (N3) | draft guard becomes `row.state == "draft"` (drops `not _is_live`) | etsy-id-or-state test | **KILLED** |
| M7 (N6) | `_reprice_on_plan_drift` uses `{**built, ...}` | re-drive source test | **KILLED** (source pin only) |
| M8 (N6) | `_targeted_rebuild` uses `{**built, ...}` | re-drive source test | **KILLED** (source pin only) |

Repro, runner and mutant scripts are in
`/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/fo3/`:
`repro_fixonly4.py`, `runsel.py`, `mutants.py`, `mut_*.json` and `base_*.log`.

## Minimum to reach SHIP
1. **R1.** Bind the card to a specific audit id or candidate hash. On the rejected path, close or
   restate any open `listing.live_update:<slug>@<version>` card. Add a pass-then-reject test.
2. **R2.** Make `blocking` required. Add an end-to-end blocked-candidate test through
   `listing.seo`, so that M4 is killed.
3. Recommended: R3 (a behavioural launch_review test, and fixing the clock-dependent test file)
   and N5 (a one-line flow_health fix).
