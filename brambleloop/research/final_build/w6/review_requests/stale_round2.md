# Review request — eng/stale-rebuild-loop, round 2

Branch `eng/stale-rebuild-loop`, continued from 4b683993 (head was f04d769, which only added
`REVIEW_REQUEST.md`). Final code SHA: 784b8dc855d2c3a0945dbfd9e8c12fc1c931ea5b (later commits only change this file).

Scope: the four MEDIUMs and L1/L3 from the independent review of 4b683993. No deploy, no Railway, no
production, no secrets, no spend. New regression file: `tests/test_eng_stale_round2.py`. Every check in
it **fails on 4b683993** (17/17: 9 SQLite + 8 PG16, run in a worktree of 4b683993 holding only the
new test files) and passes on the fix.

## M-A: legacy NULL-slug rebuild-incomplete rows were invisible

**Finding.** Production's rows were written with `product_slug` NULL. `retry_hold_reason`,
`_halting_other_than_staleness` and `systemic_evidence` matched on `product_slug`, so an exhausted row
held nothing and the daily retry looped.

**Fix.**
- `runtime/release.py::_rebuild_incomplete`: a restate now sets `inc.product_slug = slug`.
- `publish/release_gates.py`: new `incident_slug(row)` (the slug, or for `rebuild-incomplete:<slug>`
  the slug from the signature). `retry_hold_reason` and `_halting_other_than_staleness` also select
  `signature == rebuild-incomplete:<slug>`, and `exhausted` matches via `incident_slug`.
- `ops/incident_lifecycle.py::systemic_evidence`: falls back to the signature slug for
  rebuild-incomplete.
- The sentinel files legacy rows against their product (`product_slug` taken from the signature)
  as it reads them.
- `production_evidence.stale_rebuilds`: `rebuild_incomplete_held` now counts rows exhausted by count
  (legacy rows have no `held`), and a new `rebuild_incomplete_held_reasons` shows the named reason.

**Tests** (SQLite + PG):
- `test_ma_legacy_null_slug_exhausted_row_holds_the_retry`: a legacy row (NULL slug, count 3)
  holds, is not waived, counts in systemic evidence and shows up in production evidence. A row with
  attempts left still holds nothing.
- `test_ma_restating_a_legacy_row_files_its_product_slug`.
- `test_ma_sentinel_holds_a_legacy_exhausted_product_instead_of_retrying`: end to end through
  `ops.sentinel`. The legacy product is in `rebuild_retry_held` with the named reason and the
  others are retried.

## M-B: rebuilds that never reach verify looped daily

**Finding.** A chain.rebuild that goes DEAD, or is refused with "no stored release", never reaches
verify, so nothing bounded it.

**Fix.** `ops/rebuild_graph.py`:
- `_failed_attempts_by_change(db)`: one query per enqueue call. It finds non-verify chain.rebuild
  jobs that ended DEAD, or DONE with `refused`/`withheld`, and keys them by the change they
  attempted (the first attempt's idempotency key, or `retry_of_key` on a retry).
- In the retry path, once a change has `>= REBUILD_MAX_ATTEMPTS` such failures, the retry is not
  enqueued. The product goes into `retry_held` with a named reason: the DEAD job's `last_error`
  class plus an excerpt, or the refusal text.
- `_hold_failed_change` makes the hold durable. It opens or restates `rebuild-incomplete:<slug>`
  as P1, halting, with `held`, `failed_attempts`, `stale` (the artefacts) and `fingerprints`.
  `retry_hold_reason`, the publish gate and `production_evidence` already read this family. It
  closes the way every rebuild-incomplete row does: on a verified rebuild, or under the M-C rule.

**Tests** (SQLite + PG). Six simulated days through `rebuild_graph.enqueue` with the sentinel's
`hold`:
- `test_mb_dead_rebuilds_are_bounded_then_held_with_the_error_class`: 2 products go DEAD daily.
  Each is retried on days 1–2 only (on 4b683993: days 1–5) and held after that. That leaves 6 DEAD
  jobs, not 10. The hold reason names `KeyError`, and the row appears in
  `rebuild_incomplete_held(_reasons)`.
- `test_mb_refused_no_stored_release_is_bounded_then_held_with_the_refusal`: the real handler
  refuses (no PatternVersion). There are 3 attempts, then a hold naming "no stored release".

## M-C: the sentinel closed rebuild-incomplete without positive evidence

**Fix.** `runtime/release.py` (`ops.sentinel`) closes a rebuild-incomplete row only when all of
these hold:
- every key in `detail["stale"]` has a verdict reading FRESH or SUPERSEDED (a row naming nothing
  falls back to the product's non-retired recorded artefacts);
- that set is non-empty;
- no artefact of the product reads STALE.

Otherwise the row stays open. Its `detail.sentinel_read` records the verdicts actually read
("no provenance row", "unproven (retired)", …), and the sentinel output adds
`rebuild_incomplete_open`.

**Test** (SQLite + PG): `test_mc_sentinel_does_not_close_without_positive_evidence`.
- A "ghost" product (no provenance rows, exhausted) stays open and still holds.
- An "unproven" product (the named artefact has no row) stays open.
- A "fresh" product closes.
- On 4b683993 all three closed.

## M-D: model.probe reuse not tied to model or key

**Fix.** `gateway/anthropic.py`:
- `key_fingerprint()` is the first 8 hex of the sha256 of `ANTHROPIC_API_KEY`, or None when no
  key is set. The key itself is never recorded or logged.
- `probe` records `key_fp`.
- `probe_if_due` reuses a success only if `last.model == PROBE_MODEL`, a key is configured, and
  `last.key_fp` equals the current fingerprint. Otherwise it calls `probe`. With no key, that
  records `NO_KEY_REASON` and `usable()` goes False. Legacy probe rows without `key_fp` are
  re-asked once.

**Tests:**
- `test_md_probe_reuse_requires_the_probe_model_and_the_same_key` (SQLite + PG). With no key,
  nothing is reused and `usable()` is False alongside `key_present` False. Another model, another
  key or no recorded fingerprint means re-asked. Same model and key means reused at CA$0, and the
  key is absent from the record. Rotating the key ends the reuse.
- `test_md_the_real_probe_records_a_non_secret_key_fingerprint`.

The round-1 `_stub_probe` helper in `test_eng_stale_rebuild_loop.py` was updated to record what the
real probe now records (`PROBE_MODEL` and `key_fp` under a dummy key, which is removed on restore).
Its assertions are unchanged.

## L1: one withholding function

`release_gates.rebuild_withheld(db, slug)` returns the newest release plus
`withholding.current(stage="chain.rebuild")`. `retry_hold_reason` and `_targeted_rebuild` both use
it. Before, the hold read the stored record (`withholding.reasons`) while the rebuild re-read the
owner's ruling.

**Test** (SQLite + PG): `test_l1_hold_and_rebuild_read_the_same_withholding`. An owner veto is ruled
but not yet written to the record. Before the fix the hold returned None while the rebuild refused.
Now both refuse.

## L3: PG run of the e2e convergence test

`pg_e2e_convergence` in `test_eng_stale_round2.py` (PG list only, since it already runs on SQLite in
round 1) runs round 1's `test_end_to_end_a_moved_chain_converges_in_one_attempt` on a disposable PG16
database. This covers the real chain: compile, build, move the chain, sentinel, rebuild, verify,
resolve. **OK on PG16.**

## Suites

1. **57 related suites** at 962d628 (every suite that references retry_hold_reason, probe_if_due,
   rebuild-incomplete, systemic_evidence, stale_rebuilds, ops.sentinel, rebuild_graph, withholding,
   model.probe or chain.rebuild), plus round 2. Venv was built from the unpinned `requirements.txt`:
   714 passing, 17 suites failing. 16 of the 17 failed only because that venv had a starlette that
   needs `httpx2`, which is an environment issue.
2. **Rerun of the 17 + both stale-loop suites** at 784b8dc, venv built as the lock files prescribe
   (`requirements.lock` + `requirements-test.lock`, `--require-hashes`): **365 passing, 1 suite
   failing**:
   - `test_w4_listready::test_f8_every_etsy_write_call_site_is_classified...` reports
     "unclassified Etsy write call sites: approvals.py `_standing_policy`".
   - This is **pre-existing**: it fails identically on 4b683993 (checked in a worktree). It comes from
     the WS4 standing-policy merge and is not touched by this change.
3. `test_eng_stale_round2`: 9/9 SQLite, 9/9 PG16 (8 checks + the e2e). `test_eng_stale_rebuild_loop`
   (round 1): all OK on SQLite and PG16.
4. On 4b683993: the round-2 file fails 17/17 (9 SQLite + 8 PG; the e2e was added after that run and
   passes on the base by design).

PG status: PostgreSQL 16 via the `_disposable_cluster` pattern. M-A and M-C (plus M-B, M-D and L1)
are proven on PG.

No deploy, no Railway, no production, no secrets, no spend.
