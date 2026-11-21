# Review request — eng/halt-380

**Branch:** `eng/halt-380`, cut from `claude/w6-release-19d1` (9216d33, which records the
deployed 7b250d61). Not merged, not deployed, no PR. Production is unchanged.

**Trigger:** readback 2026-11-21T03:29Z on 7b250d61:
- systemic halt #380 open since 2026-10-11;
- 12 products in both `rebuild-incomplete` and `stale-artefact`;
- 112 open stale-artefact incidents, and the sentinel reads 111 of 600 stale;
- chain.rebuild over 7 days: 171 done, 12 pending, and the oldest unfinished is 0.13 h old;
- 8 rebuilds verified in 24 h, the newest at 2026-11-20T13:12Z;
- last propagation: 50 already queued, 2 retry waiting.

**Evidence basis.** This session read no production rows, no token-gated readback and no
Railway variable values. The inputs were the readback figures above and the code at 9216d33.
Each finding below is a code fact, reproduced on the real `ops.sentinel` and `chain.rebuild`
handlers by a test. That production holds rows of this shape is inferred from the readback
figures, not observed.

## The hypothesis, tested first: rejected as stated

"Every deploy that changes PDF, listing or layout code re-stales every artefact." It does not.
The only code fingerprint an artefact records is `chain:release`, which is
`fingerprint(CHAIN_VERSION)`. `CHAIN_VERSION` is a hand-set constant, and a deploy that does
not bump it moves nothing. `artefacts.check` compares recorded `inputs` only; `code_commit` is
lineage, not freshness.

There was one legitimate re-stale: CHAIN_VERSION 8 → 9 (924855a, ENG-ESTIMATE-CLAIMS,
2026-11-20). It staled every PDF and every piece of listing copy once. That is correct
behaviour: the estimate wording changed in both. The defect is that the rebuild could not
recover from it.

## Why the rebuild jobs never verify

| # | Candidate | Finding |
|---|---|---|
| H1 | Re-queue | **Cause.** `rebuild_graph.enqueue` keyed each product's job on the estate-wide change set, so any other product's ref moving gave every stale product a new key. That happens whenever a design is re-engineered or a new release is certified, which is hourly in a live catalogue. The new key skipped the in-flight check, RETRY_AFTER and the hold, and stacked a new attempt every hour. That matches pending 12 and an oldest unfinished rebuild 0.13 h old. Round-3 review LOW had seen the key restart and bounded only the DEAD/refused failure count. |
| H2 | A rebuild that re-stales or no-ops itself | **Cause.** The stacked attempt's stage token was sha(artefacts, fingerprints), identical to the first attempt's. Its stage enqueue therefore deduplicated onto the first attempt's stage job, whether that job had finished, died or done partial work. Nothing was rebuilt again. The daily retry, whose token differs, was never reached because H1 kept the product "recent". The verify pass was bound to a stage job it never got, so it could not bind. Its failures reopened `rebuild-incomplete` even after a verified close (reproduced). One stage death in the first attempt (a deploy restart mid-render, for example) was enough to lock the product permanently. |
| H3 | Attempt cap | **Cause, consequence of H2.** Those no-op attempts counted toward REBUILD_MAX_ATTEMPTS and held the product with "the stage ran and did not rewrite them", which was not true, and nothing re-read the hold. |
| — | Lease or timeout | Not a cause. The verify window (3 × 20 min) can expire before a long stage chain finishes. A late-arriving fresh row still closes through the sentinel's positive-evidence rule. Left as is (see Open). |
| — | Handoff never closes the stale-artefact row | Not a cause. A verified, bound rebuild closes the rows it proves (`_close_on_verified_rebuild`), and the sentinel closes FRESH or SUPERSEDED rows. Both are exercised in the end-to-end test. |
| — | Retired products (cloudline-baby-blanket, winter-village-graphghan) | No code reason found. Neither is in `LEGACY_DUPLICATES`, every artefact class maps to a rebuild stage, and a retired image candidate keeps its sha256, so frames stay provable. Superseded-version rows read SUPERSEDED, which settles. Whatever "partly retired" means in production rows is UNVERIFIED here. If one of them still holds after deploy, its `sentinel_read` verdicts on the row will name the key. |

## Fixes

- **H1 (`rebuild_graph.enqueue`, `_prior_attempt_keys`).** A product whose own change
  (`change_id`) already has a first attempt is routed through that attempt's key. If the
  attempt is in flight, the product reads already queued. If it has ended, the product gets
  the daily retry, which honours RETRY_AFTER and the hold. A genuinely new change of the
  product's own still gets a new key and a fresh budget, as before. The query is one per
  sentinel run, bounded to the planned products and REBUILD_FAILURE_WINDOW. Pre-round-3
  attempts (no `change_id`) are not matched, so legacy behaviour and its tests are unchanged.
- **H2 (`_targeted_rebuild`).** The stage stamp also carries the attempt's own idempotency
  key, so every attempt runs a stage of its own whichever path enqueued it: sentinel, retry,
  hold release, legacy restart or growth.steer. A re-run of the same job stays idempotent.
- **H3 (`rebuild_graph.held_without_own_stage`, sentinel).** An exhausted `_rebuild_incomplete`
  hold is released once, onto a fresh recorded budget (`hold_released`), when the hold's own
  final verify passes show that fewer than REBUILD_MAX_ATTEMPTS of its attempts ran a stage of
  their own and at least one did not. The passes are read at the same fingerprints, inside the
  window, from each pass's recorded `stage_job`. The release comes with one targeted rebuild
  at the hold's own fingerprints and `change_id`. The row stays OPEN and halting, and only
  verified evidence closes it. A DEAD/refused hold (`failed_attempts`) is never released here.
  There is one release per distinct hold text. The hold text now says "ran no stage job of
  its own" when that is what happened.
- **The systemic halt.** No change was needed. Once the per-product rows close on their own
  evidence, `incident_lifecycle.escalate_systemic` (run by `ops.truth`) resolves
  `systemic-halt:publication` with a resolution. The end-to-end test asserts this.

## Not touched

- Binding rule: a verify pass still binds only rows written by its own stage job or later,
  carrying the requested new fingerprints.
- REBUILD_MAX_ATTEMPTS, RETRY_AFTER, REBUILD_VERIFY_ATTEMPTS and the verify delay.
- The systemic-halt rule (3 products and 50%), release_gates and the publication gate.
- The kill switch, fee cap, budget, child safety, grants, the #39 rule, Product Truth and AI
  disclosure.
- No test was weakened or skipped.

## Tests

New suite: `tests/test_eng_halt_380.py`, 6 tests. **All 6 fail on the base** (src stashed) and
pass with the fix.

- `test_production_state_converges_and_the_systemic_halt_closes`: production's shape. The 12
  slugs are stale after a chain move. Every first-attempt stage dies. Another product's design
  moves every hour. A simulated 40 h runs on the real sentinel and chain.rebuild handlers. At
  hour 3 the 12 `rebuild-incomplete` rows and the systemic halt are open. On the base, all 12
  read "never rebuilt". With the fix, all 12 verify, no stale-artefact or rebuild-incomplete
  row of theirs is open, nothing is pending, and the systemic halt is resolved with a
  resolution.
- H1: another product's change never stacks an attempt on one in flight. There are no
  unbound verify passes, and no rebuild-incomplete reopens after a verified close. An ended
  attempt waits for its retry and honours a hold even under a shifted estate key.
- H2: two attempts at the same change each get their own stage job.
- H3: the production-shaped hold (1 attempt with a stage, 2 without) is released once, stays
  open and halting, and gets exactly one rebuild that runs its own stage. A genuine hold (3
  attempts with a stage) and a DEAD-kind hold stay held. There is no second release. The hold
  text is honest.

Runner (targeted, dirty tree, not release-eligible): run 20261121T034404Z-3412, 15 suites (the new one, test_publish_unhalt, test_eng_stale_rebuild_loop, test_cert_rebuild_chain, test_vacuity, test_rebuild_graph, test_eng_stale_round2, test_w4_fmgate_rebuild_key, test_w6_fix_only_rebuild, test_w4_autonomy_idle_departments, test_w4_finhealth, test_cert_publish_gates, test_artefacts, test_eng_recovery, test_w4_readback_evidence): **214 passing, 1 suite failing**. The failure is `test_w4_autonomy_idle_departments::test_a_wide_rebuild_fits_the_varchar_200_key_column`, which fails identically on the base: it expects 14 enqueued, and PUBLISH-UNHALT U2 deliberately skips the 2 retired slugs. It is not fixed here.

## Open

1. **UNVERIFIED in production.** After deploy, the first sentinel should show each of the 12 in
   `rebuild_retried` or `rebuild_incomplete_holds_released`, not stacked every hour. Within
   about a day, `rebuilds_verified_24h` should rise and `open_rebuild_incomplete` should fall.
   If a product still holds after a real stage of its own, the stage genuinely fails. Its
   named reason is then on the row (the hold text no longer claims a stage that did not run),
   and that is a separate defect.
2. The verify window (60 min) can be shorter than a long stage chain under queue contention.
   An attempt then counts as failed even though its stage later succeeds. The sentinel still
   closes the rows on fresh evidence, but a slow product could be held after 3 such attempts.
   Should the verify wait while the attempt's stage job is still in flight? Not done here,
   because it changes a bound.
3. A product with **no** prior `rebuild:product:` attempt in the window, which has a held
   `_rebuild_incomplete` row at the same change, still gets a new-key attempt without the hold
   being consulted. That is pre-existing behaviour. It is unreachable in normal flow once H1
   is in place, because every hold has a prior attempt.
