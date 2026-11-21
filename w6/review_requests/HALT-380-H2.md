REFUTED

# HALT-380 H2 — "the rebuild produces an artefact whose fingerprint never equals what the sentinel expects"

- Branch: `eng/halt-380-h2` (from `claude/w6-release-19d1`)
- Test: `brambleloop/tests/test_halt_380_h2.py` (new; no source file changed)
- Date: 2026-11-21 (UTC)

## The incident
Production 7b250d61 has systemic publishing halt #380, open since 2026-10-11. Twelve products
are both stale-artefact and rebuild-incomplete. There are 112 open stale-artefact incidents
and 12 `chain.rebuild` jobs that keep getting re-queued. No rebuild has verified since
2026-11-20T13:12Z. (These figures come from the brief. I did not read production myself.)

## What the test does
The test runs the real chain on SQLite for one product, `cloudline-baby-blanket`. That
product is one of the 14 the 2026-11-18 production evidence listed as halted on
stale-artefact.

1. `cir.compile` → certify → assets → pricing → marketing. This records 28 provenance rows
   across 12 classes: certificate, chart, listing_copy, marketing_asset, pdf, pricing,
   release_bundle, reverse_result, seo, support_knowledge, twin, visual_truth.
2. Move `chain:release`, the way a deploy does by bumping `CHAIN_VERSION`. Then run the real
   `ops.sentinel`, followed by the `chain.rebuild` request, the stage jobs and every verify
   check, with the 20-minute delays treated as elapsed.
3. For every artefact that got a `chain.rebuild_requested` audit, compare three things:
   - the row's recorded inputs against `current_from_db` (what the sentinel expects);
   - the row's recorded inputs against the `fingerprints[ref].new` the request carried (the
     binding the verify path at `release.py` ~5807-5826 checks);
   - whether the verify pass wrote `chain.rebuild_completed` or `chain.rebuild_unbound`.
4. **Determinism:** move `chain:release` a second time and rebuild again. Then check that
   each row's inputs changed only in `chain:release`, and that the new value equals the
   published current value. If time, randomness or ordering leaked into a recorded input,
   this check would fail.
5. **The restart shape:** the legacy and hold-released restarts enqueue `fingerprints: {}`.
   A rebuild request in that shape still binds a fresh row; it does not leave it unbound.

## Result (output of the test, 2/2 OK)
```
built classes: [certificate, chart, listing_copy, marketing_asset, pdf, pricing,
                release_bundle, reverse_result, seo, support_knowledge, twin, visual_truth] rows: 28
rows whose fingerprint != sentinel/request after rebuild: []
still stale: {}
requested but not completed: []
open incidents: []
determinism: second rebuild moved only chain:release on 25 rows
```
Twenty-five artefacts were requested: chart 2, listing_copy 1, marketing_asset 9, pdf 2,
pricing 1, release_bundle 1, seo 1, support_knowledge 1, visual_truth 7. All 25 were
rewritten. After the rebuild, each one reads FRESH and records exactly the sentinel's
fingerprint and the requested fingerprint. Each one was bound to this attempt's stage job and
completed. Nothing was unbound, and no stale-artefact or rebuild-incomplete incident is left
open. The other three rows (certificate, reverse_result, twin) carry no `chain:release` input
by design, so they were correctly not requested.

Each of H2's three sub-causes is refuted on this path:
- **Code / version / layout identity not reproduced: refuted.** The only code identity in
  the inputs is `chain:release = fingerprint(CHAIN_VERSION)`. Both the writers and the
  sentinel take it from the one `artefacts.chain_fingerprint()` / `current_from_db`.
  `cir:`/`release:` come from the same stored `PatternVersion` row on both sides.
  `design_inputs` and `current_from_db` both fingerprint the stored `cir_json`, and
  `(product_id, version)` is unique, so they cannot read different rows.
- **Non-determinism: refuted.** The second rebuild changed nothing except `chain:release`.
- **Verify compares against a different binding: refuted.** The request's `new` equals the
  sentinel's current value, which equals the rebuilt row's value. The `fingerprints: {}`
  restart shape also binds.

## Consequence
I made no fix, because H2 does not hold and changing code would only add risk. Every gate is
unchanged. The systemic halt already closes when its causes close: `escalate_systemic`
reconciles on `systemic_evidence`. `test_c_staleness_families_never_hold_and_the_systemic_halt_resolves_after`
already pins that, and it passes on this branch.

The production loop must therefore come from something that stops the stage from rewriting
the row, or stops the verify pass from binding to it. It is not a mismatch between the
fingerprint the rebuild produces and the one the sentinel expects. Leads for the other
hypotheses, none verified here:
- a stage job that is refused or deduplicated, which writes nothing (an idempotency-key
  collision, or a withheld release or policy refusal recorded as `chain.rebuild_refused` /
  `marketing.blocked`);
- `job_bound`: `row_job >= stage_job` is false when the row is written by an older job that
  the idempotent enqueue handed back;
- a moved ref that the local chain does not exercise, such as production-only
  `asset:image_candidate_*` / `asset:physical_photo_*` frames, or a `cir:`/`release:`
  re-certification move. This test covers only a `chain:release` move.

The next step is to compare the production audit trail for one of the 12 products
(`chain.rebuild_requested` → its `stage_job` → that job's status and outputs →
`chain.rebuild_unbound` detail) against this run.

## Suites run on this branch
All five suites ran on SQLite in this container, 2026-11-21 ~04:00-04:13Z. All passed:
- `test_halt_380_h2`: 2 OK, 0 failures.
- `test_eng_stale_rebuild_loop`: 20 OK, 0 failures. No local PostgreSQL, so its PG pass was
  skipped.
- `test_cert_rebuild_chain`: 10 OK, 0 failing.
- `test_publish_unhalt`: 10 OK, 0 failures.
- `test_vacuity`: 8 OK. Its first run flagged the determinism loop in the new test. I fixed
  that by adding a non-emptiness assertion, and the rerun was green.
