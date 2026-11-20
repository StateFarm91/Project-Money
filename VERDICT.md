# Independent review: eng/motif-backlog a8f56e3e and eng/daily a795be17

Reviewer: independent Claude Code session, 2026-11-20 UTC. No Railway variables or secrets were read.
Environment: fresh venv, `pip install --require-hashes -r requirements.lock`, then
`--no-deps -r requirements-test.lock`, Python 3.13.

---

## Unit A: eng/motif-backlog @ a8f56e3e — **SHIP (the motif-backlog work); do not integrate without 6414630**

The merge's own change, from `git show --remerge-diff a8f56e3`, covers four files:
`tests/test_motif_backlog.py` (the drain bound), plus conflict resolutions in `p0_board.py`,
`autonomy_map.json` and `suite_final_segment.txt`. The first parent e8fe91e touched only the
review request. The merge therefore adds no production behaviour change of its own beyond the
conflict resolutions, and those resolutions are correct:
- `SECTIONS` keeps `motif_recovery`, `owner_queue` and `research_sources`.
- The map counts are 145 cadences and 177 handlers. That is INTEG3's 144/176 plus the one
  motif_backlog cadence and its handler.
- The final segment keeps `test_motif_backlog`, `test_research_flow` and `test_eng_families`.

### (1) Is the hang fix vacuous? No.
- `CHAIN_JOB_TYPES = handlers.known() minus "supply.admit"`. The drain still runs every other
  job type, including `assets.build`, `pricing.position`, `listing.seo`, `launch.plan` and
  `listing.package`. So the three e2e tests still exercise the real chain on the real Worker.
- Every e2e assertion is scoped to the release under test: its slug, its `rebuild` token, or
  `LP.KIND` at `slug@version`. A `supply.admit` job only admits a *different* catalogue product.
  None of these assertions reads `supply.admit` or depends on it.
- `stop_after_assets` already used explicit `job_types`, and it is unchanged.
- The assertions are byte-identical to e8fe91e.

### (2) Suites
Run on a8f56e3e with `JOBS=4 SUITE_REGISTRY=0 SUITES="test_motif_backlog test_motif_reservation test_motif_fidelity test_w5_a7_supply_stall test_eng_supply test_cert_publish_gates test_w4_resume_runner"`. Run record 20261120T041050Z-430, clean tree. Duration 690 s. **No hang.**

| suite | OK | failed |
|---|---|---|
| test_motif_backlog | 26 | 0 |
| test_motif_reservation | 17 | 0 |
| test_motif_fidelity | 14 | 0 |
| test_eng_supply | 17 | 0 |
| test_w5_a7_supply_stall | 7 | 0 |
| test_w4_resume_runner | 40 | 0 |
| test_cert_publish_gates | 17 | **1** |

TOTAL PASSING: 138. One suite fails:
`test_the_qa_stage_stores_the_context_renders_and_publish_only_verifies_them`, at
`assert all(ArtifactStore().exists(r) ...)` (line 240).

**This failure is inherited, not caused by motif-backlog.**
- Commit 6414630 ("INTEG2: disclosed set verifies its stored #66 renders; qa_stage test checks
  the invariant on the current set") bisects this exact failure to the ENG-SUPPLY merge
  5276a42d and fixes it in `release_gates.py` and the test.
- 6414630 is a child of 809107b. It is **not** an ancestor of 39b92619 (INTEG3) or of
  a8f56e3e.
- **Confirmed on the parent.** test_cert_publish_gates at 39b92619 alone (JOBS=1, run record
  20261120T042239Z-25991, 662 s) fails the same test, at the same assertion, with
  byte-identical render refs: 17 passed, 1 failed. a8f56e3e neither introduces nor worsens it.

### (3) Production behaviour and gates, over `git diff 39b92619 a8f56e3e`
- The `_awaiting_motif_frame` and `awaiting_motif` refactors into `motif_eligible_frame` and
  `motif_eligible` are boolean-equivalent at the default `structural=True`. Both still require
  `rejudgeable` and `worth_rejudging`, so no gate is weakened at the existing call sites.
- `structural=False` is used only by the backlog, which treats the structural floor as its
  separate PARKED state.
- `_gallery_handoff` fires only on `made and usable_as_listing_asset`, and its failure never
  fails the photography job.
- The new cadence is six-hourly, the band is `proven_winner` and the job class is build. Its
  retention classifications are present.
- The readback row is advisory: WARN when never swept, never PASS.
- No ceiling, gate or owner exception is changed.

### Findings
1. **Medium (integration, inherited).** As merged, a8f56e3e is not suite-green.
   test_cert_publish_gates fails because it lacks the INTEG2 fix 6414630.
   *Fix:* merge 6414630 (or any branch head that contains it, such as INTEG2's current head)
   into eng/motif-backlog, or land motif-backlog only into an integration branch that already
   carries it. Then rerun test_cert_publish_gates and test_motif_backlog together, plus the full
   suite at the integration point. Do not mark this failure as known or skip the test.
2. **Nit.** `_drain` silently skips `supply.admit` jobs, so a future test whose own chain needs
   admission would quietly under-drain.
   *Fix:* after each `_drain`, assert that no pending `supply.admit` job names the slug under test:
   `assert not [j for j in _jobs(db, "supply.admit") if (j.get("slug") == cir.slug)]`.
   Alternatively, return the count of skipped `supply.admit` jobs so the bound is visible in the
   test.

---

## Unit B: eng/daily @ a795be17 — **BLOCK**

Suites run on a795be17 (`JOBS=2 SUITES="test_eng_daily test_v11_pwa_static
test_w4_readback_evidence test_s4_p0_board"`; run record 20261120T041139Z-9018):

| suite | result |
|---|---|
| test_eng_daily | 20/20 OK |
| test_v11_pwa_static | 85 passed (bundle under 400 KB; BUILD_STATE says 388,682 bytes, about 11 KB of headroom) |
| test_s4_p0_board | 0 failed |
| **test_w4_readback_evidence** | **22/23: FAIL `test_readback_evidence_names_the_checks_the_server_serves`** |

The same suite at the base 6414630 passes 23/23, so the failure is a regression this branch
introduces.

The following checks are correct:
- `sw.js` goes from `cc-shell-v33` to `v42` and lists `js/views/daily.js` in `SHELL`. That is
  above eng/improve's v41 and eng/learn's v40, so no shell collision.
- The route is behind the `/api/cc` owner gate.
- An unreadable source, a day before the first recorded job, a day past the retention horizon,
  or an unregistered shop each gives UNKNOWN, never 0.
- `_sum_days` gives UNKNOWN if any shop is UNKNOWN.
- The readback withholds spend amounts, ids and reason text.
- Re-arm goes only through `rearm_probe` under the cadence key and refuses spending loops.
- A duplicate key surfaces as `enqueued: False`, which is honest.

### Findings
1. **BLOCKER: readback contract broken.** `production_evidence.SECTIONS["daily_ledger"]` is
   added, but `ops/readback.py` `EVIDENCE_ITEMS` is not. The assertion
   `{s for _i, s, _k in readback.EVIDENCE_ITEMS} == set(pe.SECTIONS)` fails
   (`tests/test_w4_readback_evidence.py:617`). The deploy readback would therefore never judge
   the new section.
   *Fix:* add an `EVIDENCE_ITEMS` entry in `ops/readback.py`, for example
   `("daily production ledger (14 UTC days)", "daily_ledger", <kind>)`, judged as advisory
   (WARN/PASS only, UNKNOWN when unreadable; never PASS on UNKNOWN). Add `"daily_ledger"` to the
   `advisory` tuple and bump `len(out["items"])` from 16 to 17 in
   `test_readback_evidence_cli_never_prints_the_token_and_keeps_unknown_apart`, as motif-backlog
   did for its row. Then rerun test_w4_readback_evidence.

2. **High: change-request flood and false zero diagnoses at the start of every UTC day.**
   `zero_stages` diagnoses any stage whose count today is 0
   (`if t == 0 or (last24 == 0 and rate > 0)`), whatever the hour and whatever the expected
   rate. The job runs six-hourly, and the first run of each UTC day sees `today == 0` for almost
   every stage.
   - For a stage with live producers and no upstream or refusal signal (for example `lessons`,
     `scans`, `certifications` after an upstream day with output), the cause is `undiagnosed`,
     and `_file_ecr` runs on every run.
   - Without `improve.ecr`, which this branch does not have, the fallback appends a new
     `ops.ecr_pending` AuditLog row each time with no dedupe. That is up to 4 per stage per day,
     all spurious.
   - With eng/improve, `ecr.file` merges by fingerprint, but it still inflates `occurrences`
     with false evidence.
   - The Daily panel also shows every stage as DEGRADED just after 00:00 UTC.

   *Reproduced* with the suite's own fixtures (`_db`, `_observing`, one pending `learn.scan`),
   by calling `diagnose(db, JobQueue(db), now=2026-11-20T00:30Z)` twice. All 9 stages were
   diagnosed, and the two runs left **2** `ops.ecr_pending` rows for the same `lessons` stage.

   *Fix:*
   - Diagnose `t == 0` only when the expected count by now is meaningful. For example, require
     `rate > 0 and rate * frac >= 1`, or use the `last24` rule alone. A zero against a 13-day
     rate of 0 stays a reading, not a diagnosis.
   - File `undiagnosed` and `failing_loop` ECRs only when the 24-hour window, not the partial
     day, is zero.
   - Dedupe the fallback by checking for an existing `ops.ecr_pending` row with the same
     `artifact` key (`ecr:<class>:<module>`) for the same day before adding one.
   - Add tests: at 00:30 UTC with yesterday > 0 there is no ECR, and two runs on the same day
     produce one pending row.

3. **Medium (honesty): "0" for days the source did not measure.**
   - `concepts_held` sums `radar.supply_stall` readings, which are written only on days the
     scan found a stall. A day with no `radar.scan` at all shows 0 held, not UNKNOWN.
   - In the same way, `scans_succeeded` per shop is 0 on a day the scanner never ran. That
     zero is measured-absent output, which is acceptable for "succeeded", but the panel labels
     both cases the same way.

   *Fix:* for `concepts_held`, give UNKNOWN on days with no DONE `radar.scan` job, from
   `Job.finished_at`. Alternatively, rename the basis to "stalled scans' held concepts (0 when
   the scan found supply or did not run)" and show the scan-ran flag per day.

4. **Low (UI honesty): inverted status pill for the bad-is-high rows.** `line()` gives
   `today ? "OK" : "DEGRADED"` for every row, so Failures, Dead letters and Spend read OK in
   green when non-zero and DEGRADED when zero.
   *Fix:* pass an `invert` flag for `failures` and `dead_letters`, and a neutral pill for
   `spend_cad`, in `ROWS`, and have `line` use it.

5. **Low: retention-horizon edge.** `_series` marks a day UNKNOWN only when `dd < horizon`, but
   the horizon day itself is partly pruned. This cannot happen at `DAYS=14` (retention is 45 and
   90 days), but it would under-count if `days` were raised.
   *Fix:* use `dd <= horizon`.

6. **Low (process): the review request is incomplete.** `daily_slice1.md` says "Required
   suites: see the table below", but no table follows. The table would have shown the
   test_w4_readback_evidence failure.
   *Fix:* add the run-record table, from `artifacts/suite_runs`, after fixing finding 1.

To SHIP: fix 1 and 2 (with their tests), rerun test_eng_daily, test_w4_readback_evidence,
test_v11_pwa_static and test_s4_p0_board, and record the results in the review request.
Findings 3 to 6 may follow in slice 2, but finding 3 should be fixed before the panel is shown to
the owner.
