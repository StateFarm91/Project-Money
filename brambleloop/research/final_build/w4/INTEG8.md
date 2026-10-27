# INTEG8 / Batch 4 (2026-10-27)

Integrator: W-INTEG5.
- **Branches:** `claude/w4-INTEG8` holds the first pass. `claude/w4-INTEG8-next` holds the full Batch 4, and `claude/w4-INTEG8` fast-forwards to it once it is green.
- **Base:** the certified INTEG7 candidate 2aeb177f.
- **Scope:** no deploy and no production write. Every activation switch stays OFF in code.

## 1. Merges

All are merged with `--no-ff`, in this order:

| # | Branch | Commit | Note |
|---|---|---|---|
| 1 | CLOSE6b | 31510b44 | |
| 2 | RESUME | f1cde398 | |
| 3 | INTELREC | 4e2baef4, then f525e3f1 | |
| 4 | AGENTS2 | 6ebe7103 | includes C1 |
| 5 | RETFIX | c972bdc0 | |
| 6 | C03 | d3b1b315 | |
| 7 | C04 | 92b75144 | the F-607/F-579 commits fef3990d, 9e86e842, a44a0e3e and b74df8b5 are excluded |
| 8 | C11 | c32c7c48 | |
| 9 | C14 | d062fb95 | |
| 10 | C10 | 6dfde764 | |
| 11 | C12 | ccde9980 | |
| 12 | C08 | a2cc7da8 | |
| 13 | C09 | 77c345ac | |
| 14 | C12wire | 3c3ad7e6 | |
| 15 | C07 | 0d7da718 | |
| 16 | C01 | aad5ebf9 | |
| 17 | F454 | 04685f31 | `claude/w4-INTEG8` ends here, at abf94bdf |
| 18 | C12 | 58317cc3 | the retention-safety fix |
| 19 | C03 | e5dc33ec | the retention-safety fix |
| 20 | C13 | 1c5a069c | |
| 21 | WIRE1 | f16a0c07 | |
| 22 | D2 | 39df91c3 | |
| 23 | FMBATCH2 | 90381df5 | merged whole |

### Conflicts and how each was resolved

- **DECISION_LOG** (C10 and FMBATCH2): both sides kept. The log is append-only.
- **`commerce/search_visibility.py`** (C09): both kept. The F-560/F-561 sections and C09's F-038 section are independent.
- **`agents/registry.py`** (F454): both kept, C07's `cir.reengineer` bar and F454's two agents.
- **`static/sw.js`** (WIRE1): both sides were at v26, so it was bumped once to v27.
- **`api_routes` pin** (WIRE1):
  - it moves to 7f715ba78ff283a8;
  - the only difference from WIRE1's route set is CLOSE6b's two operator-only POST routes, `/api/ads/eligibility` and `/api/finance/ads-credit`;
  - both are declared in `ops/CONTRACT_CHANGES.md`.
- **FMBATCH2 tests** (`test_w4_fmbatch2_hq_job_process`, `test_w4_fmbatch2_research_docs_absent`, `test_w3_hq_independence`): the INTEG7 versions are taken. Those carry the `OK` line counters, and their ALLOWED map is a superset of FMBATCH2's.
- **Cherry-picks already in INTEG7:** R-2 (3bdb475b) and F-095 (8111ce1d) were cherry-picked earlier, and their files are unchanged by the FMBATCH2 merge.
- **Generated files:**
  - `autonomy_map.json` was regenerated after every merge that conflicted on it, and is kept wherever only `generated_at` differed;
  - `decision_index.json` was regenerated, adding D-W4-CLOSE6-OVERRIDES and D-W4-FMBATCH2-DECISIONS.

## 2. Integration defects fixed

1. **Retention decisions** (3b00043d, then 21d672e1). Four audit actions read by name had no decision, and each reads every row of its action. They are classified `lifetime_total`:
   - `finance.statement_archived` (C04);
   - `research.fetch` (INTELREC);
   - `portfolio.strategic_overlap` (C09);
   - the F-666 `brief.py::_audits` window (CLOSE6b), recorded as an unresolved site.

   Two entries were removed: `listing.learning_window` and `improve.method_version`. C12 58317cc3 and C03 e5dc33ec moved those reads to `operating_readings`, which retention does not prune.
2. **Accounting docstring** (f9fdca3e). C04's `statements` module is now named in the accounting package docstring.
3. **`quality/benchmark_e2e.py` reading `research/bench2`** (d3a2494e). Recorded as an ALLOWED entry; see §3.
4. **FM2's OpenAPI re-verify test against F454's cadence owner** (5e49c0ad). See §3.

## 3. Items for the Batch 4 independent review, and why none is a weakening

- **5e49c0ad: FM2's expected cadence owner changes from `orchestrator` to `integration_steward`.**
  - F454 (04685f31) deliberately moved `etsy_openapi_reverify` to the integration domain's focused agent, as F-454 asks. Its commit says the orchestrator keeps its permissions. F454 did not update FM2's pinned test.
  - The test still asserts the cadence exists and that its period is 7 days.
  - It now also asserts that the actual owner is authorised for the job type, and keeps the original check that the orchestrator is authorised too. So the authorisation guarantee is checked against the agent that really runs the job.
  - The handler, the band and the work-judgement assertions are unchanged.
- **d3a2494e: ALLOWED entry for (`quality/benchmark_e2e.py`, `research`).**
  - Nothing in the runtime calls `run()`. A search of `src/` and `ops/` finds no job type, route, schedule or registry string.
  - Where the freeze is absent, as it is in the image, `run()` returns UNKNOWN with a reason, never PASS. C07's own `test_f678_...` asserts this.
  - The freeze holds page-cited facts from the purchased Benchmark 2, so promoting it into the image would be the wrong fix.
  - `test_every_allowance_is_still_needed` will flag the entry as soon as the read goes away.
- **Also for review** (not changed by the integrator): C07 329d0566 (spend-path pin extended for F-464's deferred render submit/poll) and the C01 hook.

## 4. B0 ledger

`b0_reconcile.py` was re-run with INTEG8 read as `origin/claude/w4-INTEG8-next`.

| Class | vs INTEG7 2aeb177f | vs INTEG8-next |
|---|---|---|
| (a) engineering-complete, integrated | 745 | 871 |
| (b) built and tested on a branch, awaiting integration | 126 | 0 |

## 5. Suites

Focused suites only. No full suite runs until it is scheduled after the 2aeb177f release. Results are in the commit messages and the coordinator reports.
