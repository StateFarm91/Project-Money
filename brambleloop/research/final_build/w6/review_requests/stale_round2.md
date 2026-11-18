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

---

# Round 3: review of 0d2e6cbc (M-E + LOWs)

Code SHA: **fd43edf2b66e6bf3a30175daf2f119e92f7c3c66** (later commits change only this file). Based on
0d2e6cbc. No deploy, no Railway, no production, no secrets, no spend.

## M-E: pre-branch report_count deadlocked long-open products

**Finding.** `rebuild_exhausted` / `_exhausted` treated `report_count >= 3` as exhausted. After M-A this
applied to legacy rows, whose count had grown once per failed daily attempt under the round-1 bugs. So
products open since before this branch were held on the first sentinel run, never retried and never
rebuilt (deadlock).

**Fix.**
- **One definition of exhaustion.** `ops/rebuild_graph.py` gains `legacy_incomplete(detail)`: no
  `attempts` and no `budget_reset`. Every write since this branch records `attempts`; the pre-branch
  code wrote only `stale`, `reason` and `fingerprints` (checked at 2676274). It also gains
  `incomplete_exhausted(report_count, detail)`, which is True if the row is `held`, False for a legacy
  row, and otherwise `count >= REBUILD_MAX_ATTEMPTS`. `release_gates.rebuild_exhausted` (the retry hold
  and the marketing waiver) and `production_evidence._exhausted` both call it.
- **A fresh, recorded budget.** On a legacy row's first restate, `release._rebuild_incomplete` records
  `detail.budget_reset` and sets `report_count = 1`. `budget_reset` holds:
  - `legacy_report_count`, plus the legacy severity, summary and opened-at;
  - `legacy_detail`, the row's full prior detail (it keeps the history);
  - `at`, and `why` (written before eng/stale-rebuild-loop, the count was loop iterations under the
    bugs that branch fixed, and the legacy count and detail are kept here).

  `_hold_failed_change` records the same reset when it restates a legacy row (M-B path). The key
  survives later restates because the detail is merged. After `REBUILD_MAX_ATTEMPTS` restates under
  the new code, `held` is written and the named hold applies as designed.
- **The same hazard on the M-B bound.** Pre-branch DEAD or refused `chain.rebuild` jobs have no
  `change_id` in their payload, so they spend none of the new budget. The hold records them as
  `legacy_failed_attempts_not_counted`.
- **Visible, not silent.** `production_evidence.stale_rebuilds` adds:
  - `rebuild_incomplete_held_count` (uncapped);
  - `rebuild_incomplete_legacy_budget_pending`: legacy rows awaiting their first restate, which are
    retried, not held;
  - `rebuild_incomplete_budget_reset`: slug mapped to the legacy count.

  The operator `/api/verify` `stale_artefacts_rebuilding` evidence now carries the held count, the held
  reasons and the pending list. The anonymous view is unchanged: name and verdict only.

**Tests** (`tests/test_eng_stale_round2.py`, SQLite + PG16):
- `test_me_legacy_counts_get_a_fresh_recorded_budget_then_hold` is the probe equivalent, with legacy
  counts 1, 3 and 6:
  - Before the sentinel, none of the three holds; evidence lists them as budget-pending and 0 held.
  - The sentinel retries all three once; none is held.
  - Three restates under the new code follow. After each one, `report_count == attempt` and
    `budget_reset.legacy_report_count` is the legacy N, with the legacy detail kept. Nothing holds
    after attempts 1 and 2; all three hold after attempt 3.
  - The next sentinel holds all three ("could not complete"); none is retried. Evidence shows held
    count 3 with a reason per product, and budget_reset `{me-one: 1, me-three: 3, me-six: 6}`.
- `test_me_legacy_dead_jobs_do_not_spend_the_new_budget`: with 4 pre-branch DEAD jobs, the product is
  retried on days 0, 1 and 2 and then held with `KeyError`. 0d2e6cbc held it on day 0 without a retry.

## LOWs

- **M-B bound per product.** Each `chain.rebuild` payload now carries `change_id`, a sha256 over only
  the refs this product's artefacts record and their new fingerprints. Failures are keyed
  `slug|change_id`. The bound is checked before the first enqueue as well, so a new estate-wide job key
  (another product's ref moved) no longer restarts it. Job idempotency keys are unchanged.
  Test: `test_low_mb_bound_is_per_product_not_per_estate_change` (another product's ref moves daily;
  3 jobs, then held; 0d2e6cbc enqueued 6).
- **Failed-attempt query bounded.** It reads only the plan's products (`idempotency_key LIKE
  'rebuild:product:<slug>:%'`, plus the whole-hashed `rebuild:sha256=%` form, filtered by
  `inputs.product_slug`) and only jobs finished inside `REBUILD_FAILURE_WINDOW` (30 days). A change
  already held stays held through the durable rebuild-incomplete row (`retry_hold_reason`) after its
  failures age out.
- **key_fp documented.** The `gateway/anthropic.py::key_fingerprint` docstring states that the value is
  persisted in `model.probe` audit rows, why that is acceptable (32 bits of an unsalted SHA-256 of a
  high-entropy key cannot be inverted or used), and that no other part of the key may be recorded.

## Changed existing tests (semantics changed by M-E, documented in place)

- **Round-2 M-A tests.** The signature-matching property is now pinned on a NULL-slug row exhausted
  under the new budget (`_exhausted_null_slug_row`: `attempts` + `held`), because a legacy count alone
  no longer holds. `test_ma_legacy_null_slug...` also asserts that legacy counts 1, 3 and 6 hold
  nothing and are not refused by the waiver.
- **`test_ma_restating...`** needs `REBUILD_MAX_ATTEMPTS` restates to exhaust (the first one resets),
  and asserts the recorded legacy count.
- **`test_mc...`** gives the ghost row the new-budget exhausted shape.
- **Round-1 `test_b_marketing_rebuild_waives...`** now asserts that a detail-less row at count 3 is
  waived (M-E), and that the row is a never-waived hold once `attempts` reaches the budget.

## Results

- **New checks on 0d2e6cbc.** A worktree of 0d2e6cbc holding only the new test file: the 3 new tests
  **fail 6/6** (3 SQLite + 3 PG16).
- **At fd43edf2** (venv built from `requirements.lock` + `requirements-test.lock`, PG16 via
  `_disposable_cluster`), the command was `JOBS=4 SUITE_REGISTRY=0 SUITES="test_eng_stale_round2
  test_eng_stale_rebuild_loop test_rebuild_graph test_cert_rebuild_chain test_cert_publish_gates
  test_artefacts test_w4_fmgate_rebuild_key test_w4_readback_evidence test_model_spend_paths"
  bash run_tests.sh`. Result: **144 passing, 0 suites failing, 0 skips**; all 9 suites ran.

  | Suite | OK |
  |---|---|
  | test_eng_stale_round2 | 24 (12 SQLite + 11 PG16 + pg_e2e_convergence on PG16) |
  | test_eng_stale_rebuild_loop | 20 (incl. 9 PG16) |
  | test_rebuild_graph | 10 |
  | test_cert_rebuild_chain | 10 |
  | test_cert_publish_gates | 18 |
  | test_artefacts | 23 |
  | test_w4_fmgate_rebuild_key | 4 |
  | test_w4_readback_evidence | 23 |
  | test_model_spend_paths | 12 |

  Run record: `artifacts/suite_runs/20261118T192144Z-3591.json`.
- **First run, at 0b767134** (before the round-1 test update): the only failure was
  `test_b_marketing_rebuild_waives...` (SQLite + PG). That was the expected M-E semantic change,
  addressed above.
