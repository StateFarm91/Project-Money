# Independent integration review INTEG5B: Batch 5 integration `claude/w5-INTEG1` at a8ce0072, 2026-11-02

Reviewer: an independent Claude Code session (branch `claude/w5-SECREVIEW-INTEG5B`).
- The review was read-only. This report is the only file committed.
- Probes ran in the session scratchpad: a detached worktree of 0967c3ee and throwaway SQLite
  databases. The worktree under review stayed clean.
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
- Subject: `git diff 0967c3ee..a8ce0072 -- brambleloop/src brambleloop/tests brambleloop/requirements*`
  (130 files, +17,535 / -790). The baseline is the deployed Batch 4 release.
- Scope: the integration only, meaning the merge resolutions and how the branches interact. Each
  branch's own logic was reviewed separately (OPUS2A–OPUS2M, INTEG5FIX, PHYSFIX delta 11) and is not
  re-reviewed here.

## Verdict

**SHIP for certification (PROVISIONAL until the second regression batch below is recorded green).** a8ce0072 may go to the one uninterrupted full suite
(REQUIRE_CLEAN=1). This verdict is not a deploy approval.

- Every merge resolution is faithful. No hunk was lost, no registration was duplicated, and no
  gate or refusal was dropped.
- No path lets production publish, spend or leave SHADOW. Product Truth and deterministic
  validation are not weakened.
- No HIGH or MED finding. Three LOW items concern rollback and the new index. They should go into
  the deploy request and the rollback runbook. None of them blocks certification.
- Every regression suite run here passed. The Commands section lists them all.

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| INTEG5B-1 | LOW | **Rollback to 0967c3ee keeps the new partial unique index `uq_owner_actions_open_requirement`, and 0967c3ee's unguarded owner-queue writers then fail instead of duplicating.** `core.migrate` creates the index on boot whenever no duplicate open keys exist. 0967c3ee's metadata does not declare the index, so its migrate leaves it in place. On rollback, any 0967c3ee read-then-insert writer that races (about 40 such writers per INTEGFIX LOW-3; 0967c3ee has no `owner_queue_guard`) gets `IntegrityError`. Before, it inserted a duplicate. This fails closed: the transaction rolls back and the job retries, but repeated races can dead-letter a job. *Action:* add `DROP INDEX IF EXISTS uq_owner_actions_open_requirement;` to the 0967c3ee rollback runbook as an optional step, and say so in the deploy request. | Probe scenario A: DB created by 0967c3ee, booted with a8ce0072 (`index uq_owner_actions_open_requirement` created), then 0967c3ee inserts a second open row for `probe:k` and gets `REFUSED IntegrityError`, leaving 1 open row. |
| INTEG5B-2 | LOW | **After a rollback, `store.publish`'s gate no longer reads a Batch-5 `quality_reverify` withholding.** 0967c3ee's `release_gates.for_publish` turns only `teardown_qa` and `physical_size_failed` record entries into refusals. 0967c3ee's `withholding.KINDS` lacks `quality_reverify`, and its re-certification does not carry it (`carry_reverification` is Batch 5 code). Other 0967c3ee readers still see the entry: `withholding.reasons()["withheld"]` stays True, so `publication_authority._certification` is FAIL. Production is SHADOW, so nothing can publish. Defence in depth drops from two readers to one for the duration of a rollback. *Action:* note it in the rollback runbook. | `git show 0967c3ee:brambleloop/src/brambleloop/publish/release_gates.py` lines 1534-1545, against `ops/publication_authority.py:162-165`. |
| INTEG5B-3 | LOW (PLAUSIBLE) | **Race between `migrate.apply` checking for duplicates and creating the index.** `conflicts(engine)` is read, then `index.create()` runs unguarded. If the outgoing 0967c3ee container inserts a duplicate open key between the two (Railway overlap), `CREATE UNIQUE INDEX` raises. The exception propagates through `Database.create_all()`, so the `app.main` startup hook fails, the new container fails health, and the deploy fails while the old release keeps serving. This fails closed. The window is milliseconds, so this was not reproduced. *Fix (optional):* catch `IntegrityError` around `index.create` and record `DEFERRED`, as the conflict branch already does. | `core/migrate.py` lines 155-171; `app/main.py:225`. |
| INTEG5B-4 | LOW (PLAUSIBLE) | **`listing.package` adds a frequent writer of `PatternVersion.certificate`, with no row lock.** Every 6 h, `for_publish(read_only=True)` still runs `withholding.reconcile`, and `record_in` writes back the whole certificate JSON when a kind it decides changes. The daily `quality_ops` `record_reverification` writes the same JSON in separate sessions. On PostgreSQL READ COMMITTED, two writes that interleave can lose one: if reconcile commits after reverification wrote `quality_reverify`, the withholding drops until the next daily re-verification. The window is at most 24 h, in SHADOW. The read-modify-write pattern already existed in Batch 4 (store.publish and chain.rebuild). Batch 5 adds a frequent writer and a kind that can be lost. Not reproduced. *Fix (next batch):* `SELECT ... FOR UPDATE` on the PatternVersion row in `withholding.record_in` and `record_reverification`. | Reading: `publish/withholding.py` `record_in` / `record_reverification`; `publish/listing_package.py` `assemble`, then `release_gates.for_publish`. |
| INTEG5B-5 | INFO | **Production may hold duplicate open owner actions; if so, the index is DEFERRED there.** That is designed behaviour (probe scenario B: `DEFERRED: 1 conflicting row group(s)`, boot continues). The readback should state which outcome production took: the migrate change list is in the boot log. Closing duplicates is the explicit `python -m brambleloop.ops.owner_queue_dedupe --apply` (dry run without `--apply`). That is an operator data step, not automatic. | Probe scenario B. |
| INTEG5B-6 | INFO | **Stale docstring.** `ops/owner_queue_guard.py` still says the partial unique index "is proposed to the integrator, not created here". `core/models.py` now declares it. Documentation only. | `ops/owner_queue_guard.py` docstring, last bullet. |
| INTEG5B-7 | INFO | **Known colourwork-claim bypasses are present at a8ce0072.** These are OPUS2M-3, pre-existing at 424d69a9, not introduced by the integration. On plain fabric, "2-Colour Basket", "Two-Tone Basket" and "Bicolour Basket" yield no colourwork claim (`launch0.colourwork_claims` returns `()`). The OPUS2M-2 word-boundary regression is **not** in a8ce0072: d4486b8c is unmerged and 424d69a9's substring match is in force. No Launch-0 title or note is affected: all 8 Launch-0 CIRs read `colourwork_claims: ()`, `fabric_truth.backed` and `title_promise.backed` True. Track the bypasses with OPUS2M-3. | `PYTHONPATH=src python3 -c "from brambleloop.products import launch0 as l; print(l.colourwork_claims('2-colour basket'))"` |

## Merge resolutions (focus 1)

`git log --merges --first-parent 0967c3ee..a8ce0072` lists 18 W5-INTEG1 merges. For each one,
`git show --remerge-diff` was compared with both parents:

| Merge | Conflicts | Resolution |
|---|---|---|
| 12d0ba4 INVENTORY | `sw.js` | Faithful: `cc-shell-v29`, plus `js/views/production.js` in SHELL. |
| 50ef24b CONCEPT | none | Identical to git's automatic merge. |
| b593a52 opus2 fb52cb9e | `withholding.py`, `release_gates.py`, `pipeline.py`, autonomy map | Faithful union. `KINDS` = (teardown_qa, owner_veto, competitive_standard, teardown_requirements, physical_size_failed, quality_reverify); `PERMANENT` and `BUILD_BLOCKING` unchanged. `for_publish` keeps the teardown, re-verification and physical-size refusals, the last read from both the record and `durable_reasons`. `_persist_release` applies `carry_reverification` and then `carry_permanent`; `test_w5_integfix` proves both carry. |
| 4f136bf PDF1 df5ffc4e | ~60 add/add (merge taken before the 0967c3ee merge) | Judged on the net 0967c3ee..a8ce0072 diff. Every removed src block was checked. The supplement-frame validation moved intact to `listing_set._with_supplements` and is reused by `certify_photo_led`. The PHYSFIX lift loop moved to `release.py:3491-3500`, which now covers every measured release (R40). The `_seed_for` / POOL-only removals were replaced by `pool_with_intake` (CONCEPT). |
| 5376bff Batch 4 0967c3ee | none | Identical to git's automatic merge. |
| b9245dc PHYSFIX 43021c1e | none | Identical to git's automatic merge. |
| 5a248a8 listing-package | `registry.py`, `classes.py`, autonomy map, `worker.py` | Faithful union: `chain.successors` and `listing.package` are both in the listing agent, in `JOB_CLASS` (`_B`) and in `CADENCES`. |
| d368800 … 799b3d2 (PR #3/#5/#6/#7/#8) | none | Each is identical to git's automatic merge. |
| 0ef729a colourwork fa02cb49 | `colour_changes.py` (J-7) | Faithful: both field sets are kept. `rounds_instruction` now prints the tapestry sentence even when there are 0 round changes, pinned by `test_a_joined_round_tapestry_piece_prints_its_colourwork_in_the_pattern`. |
| acffb4d, ddc127c, a8ce007 | none | Each is identical to git's automatic merge. e0be7c4d is OPUS2M subject 2 **SHIP**, confirmed on `origin/claude/w5-SECREVIEW-OPUS2M`. |
| 812f63d records | none | No src/tests/requirements change against the first parent. |

Shared registries at a8ce0072 were checked programmatically after `import runtime.pipeline`:
- 169 handlers. Every `CADENCES` job type has a handler, a `JOB_CLASS` entry and an
  allowed-job-type on its agent.
- No duplicate cadence name. The only repeated job type is `improve.role_work` (eight role
  agents), which is intended.
- `python -m brambleloop.autonomy.map --write` regenerates a map identical to the committed
  `autonomy_map.json`, apart from `generated_at`.
- `ops.retention` gains `pricing.refused` ("latest"), `cir.draft_refused` ("windowed") and the
  `radar_concepts` prune.

## Cross-branch interactions (focus 2)

- **Size claims, colourwork, title_promise, fabric_truth.** These are independent readers and
  every one fails closed:
  - `size_claims.for_release` refuses when it cannot read the PDF. An exception becomes UNKNOWN
    with a reason, so it refuses.
  - `first_customer.colourwork_findings` and `launch0.fabric_truth` share `technique_backed`
    (OPUS2I I-2).
  - `title_promise` counts digits and pair/duo/trio/quartet, not "two", so "Two-Colour" does
    not read as a count.
  - On the 8 Launch-0 CIRs, all three readers back the titles.
- **PHYSFIX and REVERIFY withholding.** Both survive re-certification, and both refuse in
  `for_publish`. `physical_size_failed` is also read from its durable audit row. The
  `test_physfix` (48) and `test_w5_integfix` (5) suites pass. Lost-update caveat: INTEG5B-4.
- **listing_package, photo-led gallery, sample withholding.**
  - The package's blockers are `for_publish(stage=activation)`, so they include the size,
    physical-size and re-verification refusals.
  - Its gallery is `etsy_ops.certified_frames`, which reads frames in certificate order and
    knows `physical_photo_lead`.
  - `sample_photo_lead` approves nothing: `asset_truth` requires `lead.approved` and no blocks.
    It requalifies through `sample_photo.qualifying_photos`, bound to a passed full make of
    this release. A size-failed release has no passed make, and `for_publish` refuses it anyway.
  - The open P0-PHOTO-ASSET-REVIEW gap still fails closed.
- **culture.sweep timeout and the paid-call guard.**
  - After the send, a failure is billed only when the guard's own `PaidCallRecord` says
    UNCERTAIN. The failure is then counted once at the estimate, never re-sent, and returns
    `unresolved`.
  - A failure before the send releases the reservation and re-raises.
  - `gateway/` is unchanged in the diff.
- **Family membership and culture concepts.**
  - `family_of(slug, db)` reads `culture_concepts.signal_key`; the columns exist in 0967c3ee.
  - Culture families are never `bundle_ready`, never a navigation group, and amplify records
    `needs_member_route` instead of queueing `radar.score` with an unreadable slug.
- **Owner-queue guard and the new OwnerAction writers.** Every Batch-5 writer is an ORM write
  (`knowledge_gaps`, `listing_package.record`, `chain_successors`, `owner_queue.ensure`), so the
  `before_flush` guard covers it. A grep finds no Core `insert(OwnerAction)`.
  - `listing_package.record` takes `_serialise_owner_queue` first. The guard's later
    `pg_advisory_xact_lock` on the same key re-enters; on SQLite the guard skips because a
    transaction is already open.
  - No writer inserts a duplicate key and then closes the old row in a later flush. That
    pattern would let the guard merge the newcomer away. An AST scan of functions that both
    add and close found none.
- **Chain dead ends.** Incidents are P2 with `halts_publication=False`, so they never feed
  `systemic_evidence`. Successors are re-driven only once per known deployed commit.

## Production publish, spend, SHADOW, Product Truth (focus 4)

- No change touches `store.publish`'s SHADOW refusal, `protected_phase`, publication authority
  or `gateway/`.
- The new jobs are all CA$0: `listing.package`, `chain.successors`, `radar.concept_intake`,
  `intel.scan_evidence`, `improve.commercial_lessons` and `learning.knowledge_gaps`. Their
  classes are B, O or R; none is a spend class. `listing.package` returns `publishes: False`.
- `learning.knowledge_gaps` produces capped owner-approval recommendations and never buys.
- Every new truth reader refuses on UNKNOWN. No gate was loosened in the diff.

## Test integrity (focus 5)

`git diff 0967c3ee..a8ce0072 -- brambleloop/tests | grep '^-.*assert'` finds 26 lines. Each has
an equal or stricter replacement:

| Lines | Where | Replacement |
|---|---|---|
| 13 | `test_pdf_layout_bounds.py` | Re-added byte-for-byte except the font names, which now map the embedded brand faces (whole-file CRLF rewrite). |
| 1 | `test_deliverable_qa` "(120 sts)" | Asserts the pattern's own largest count and its commonest repeat (F8). |
| 1 | `test_deliverable_qa` chart cue | Same assertion, plus a new re-layout assertion. |
| 1 | `test_deliverable_qa` frame px | Pin moved 56 → 58, up, never down. |
| 3 | `test_launch0_gauge` / `test_release_versions` | Versions moved 1.2.0 → 1.2.1 / 1.3.0 (PDF1, D-W4-OWNER-BASKET-1.3.0). |
| 4 | `test_w4_intelrec_watchlist` | The same counts plus the 4 seeded shops. |
| 3 | `test_w4_multipiece` / `test_w4_prodready_contract3` | Contract and renderer version strings bumped to 3.1 / 3.1.0. |

- `release_fingerprints.tsv` moves the versions. Content hashes are unchanged except for
  market-basket-small 1.3.0, whose content changed deliberately.
- `test_fallback_draft_provenance` names the new vessel producer chain.
- No assertion was weakened.

## Database compatibility (focus 3)

**Forward (0967c3ee DB → a8ce0072 code): compatible, additive only.**
1. **New partial unique index** `uq_owner_actions_open_requirement` on
   `owner_actions(requirement_key)`:
   - Applies `WHERE done = false AND requirement_key <> ''` (SQLite: `done = 0`).
   - Created by `core.migrate.apply` only when `owner_queue_dedupe.conflicts()` is 0.
     Otherwise it is DEFERRED with a log line and boot continues.
   - `migrate` never alters data.
   - Probe A: created on a clean 0967c3ee DB. Probe B: DEFERRED on a DB with a duplicate, and
     both rows were kept.
2. **New table `radar_concepts`** (W5-CONCEPT). It is created lazily, with `checkfirst`, on
   first use by `radar.intake`, and pruned by `ops.retention`.
3. **No column added, removed or retyped.** `culture_concepts.signal_key` / `product_slug`
   already exist in 0967c3ee.
4. **New JSON keys inside `PatternVersion.certificate`:** `withholding.quality_reverify`,
   `reverify_failed` and `carried_across_recertification`.
5. **Release data.** Launch-0 versions move (baskets and coaster 1.2.0 → 1.2.1 / 1.3.0), so
   new releases are certified beside the stored 1.2.0 rows and the old rows read as superseded.
   This is new data, not a schema change.

**Rollback (a8ce0072 DB → 0967c3ee code): safe to boot and run, with three caveats.**
- 0967c3ee ignores the extra table and the certificate keys.
- 0967c3ee still treats a `quality_reverify` entry as `withheld` in `withholding.reasons` and
  `publication_authority`.
- Caveat 1: the index remains (INTEG5B-1). Drop it if 0967c3ee's owner-queue races start
  failing jobs.
- Caveat 2: `for_publish` under 0967c3ee does not cite `quality_reverify` (INTEG5B-2).
- Caveat 3: rows that 1.2.1 / 1.3.0 releases wrote stay in the DB. 0967c3ee will re-certify its
  own 1.2.0 versions. Batch 4's sentinel judges an artefact by its own release (W4-LISTREADY
  R1), so the 1.2.1 / 1.3.0 rows read as releases 0967c3ee does not produce. This was not
  exercised against a production snapshot, so it is UNKNOWN, not PASS. The deploy's rollback
  rehearsal (`ops/deploy.sh`) is the place to prove it.

## Commands

Run from `brambleloop/`, with dependencies from `requirements.lock` and
`requirements-test.lock` (`--require-hashes`; SQLAlchemy 2.0.54). Each suite ran alone, as
`PYTHONPATH=src:tests python3 tests/<suite>.py`. Results:

| Suite | Result | Time |
|---|---|---|
| test_w5_integfix | 5/5 | 3 s |
| test_physfix | 48/48 | 712 s |
| test_opus2_reverify_withhold | 6 OK / 0 failed | 40 s |
| test_opus2_cir_colourwork | 17 / 0 | 0 s |
| test_opus2_size_claims | 13 / 0 | 177 s |
| test_opus2_listing_package | 14 / 0 | 715 s |
| test_opus2_photo_led_gallery | 9 / 0 | 539 s |
| test_opus2_owner_queue_races | 14 / 0 | 10 s |
| test_w4_owner_queue_race | 3 / 0 | 104 s |
| test_opus2_family_membership | 5 / 0 | 4 s |
| test_opus2_culture_sweep_timeout | 8 / 0 | 8 s |

**Second batch: RUNNING at commit time, results not yet recorded (UNKNOWN, not PASS):** test_first_customer_gate, test_launch0, test_launch0_listing_truth, test_compiler, test_reverse, test_twin, test_w4_auditfix_migrate, test_culture, test_culture_feed, test_cost_governance_wave2, test_opus2_draft_constructions, test_opus2_chain_deadends, test_physfix_photo_first. This report is updated when they finish.

Other commands:
```
git log --merges --first-parent --format='%h %p %s' 0967c3ee..a8ce0072
git show --remerge-diff <merge> -- brambleloop/src brambleloop/tests
git diff 0967c3ee..a8ce0072 -- brambleloop/tests | grep '^-.*assert'
git diff 0967c3ee..a8ce0072 -- brambleloop/src/brambleloop/core/{migrate,models,db}.py
PYTHONPATH=src python3 -m brambleloop.autonomy.map --write <scratch>/map.json   # equal to the committed map
# DB probe (scratch SQLite; probe script in the session scratchpad):
#   A: 0967c3ee create_all -> a8ce0072 create_all ("index uq_owner_actions_open_requirement")
#      -> 0967c3ee duplicate insert: IntegrityError, 1 open row
#   B: 0967c3ee DB with a duplicate open key -> a8ce0072: "DEFERRED: 1 conflicting row group(s)"
#   C: a8ce0072 duplicate ORM insert: merged by the guard, 1 open row
```
The full suite was not run. Per the certification path, that is the next step: one uninterrupted
run with REQUIRE_CLEAN=1.
