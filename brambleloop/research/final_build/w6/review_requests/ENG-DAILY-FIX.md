# ENG-DAILY-FIX: eng/daily after the BLOCK on a795be17 (Unit B)

Branch `eng/daily`. **Not merged, not deployed; production unchanged.** No Railway variables or secrets
were read. Everything is measured on fixtures.

- **Tested SHA:** `b77b1feb6cfe113253c2ec0d876df22b6e8d25d6`. The commit after it touches only this file
  and `daily_slice1.md`.
- **Base:** `origin/claude/w6-INTEG4` @ 259e47c4 was merged first (commit ae41c92), so learn and improve,
  including `improve.ecr`, are present.
- **Required suites** (run record `20261120T045050Z-21073`, clean tree, JOBS=6, 98 s): **239 passing,
  0 failing.**

| suite | OK | failed |
|---|---|---|
| test_eng_daily | 27 | 0 |
| test_v11_pwa_static | 86 | 0 |
| test_w4_readback_evidence | 23 | 0 |
| test_s4_p0_board | 18 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |
| test_eng_improve | 24 | 0 |
| test_eng_learn | 13 | 0 |

`test_v11_pwa_browser` is outside the required set. It was run separately: 264 passes, 0 failures, with 4
Daily checks.

## Merge resolution
- **Kept both sides of:** `api.py` (daily, catalogue and operating-evidence routes), `api.js`, `routes.js`,
  `check.mjs` and `charters.py` (`ops.daily_ledger` plus `ops.owner_queue_consolidate`).
- **BUILD_STATE, DECISION_LOG and `suite_final_segment.txt`:** both sides kept. The last two merged
  without conflicts.
- **More list:** `... p0_board, daily, catalogue, agents_evidence ...`.
- **`sw.js`:** `cc-shell-v43`, above INTEG4's v42. SHELL lists `daily.js`, `catalogue.js` and
  `agents_evidence.js`.
- **`autonomy_map.json`:** regenerated at 148 cadences and 180 handlers (INTEG4's 147/179 plus
  `ops.daily_ledger`).

## Findings, one by one
1. **BLOCKER, readback contract: fixed.**
   - `ops/readback.py` has a new `EVIDENCE_ITEMS` row, `("daily production ledger (14 UTC days)", "daily_ledger", None)`.
   - It is judged by `_judge_daily`, which is advisory:
     - missing or unreadable section: UNKNOWN;
     - readable but no stage readings, or an UNKNOWN or zero-output stage: WARN;
     - PASS only when every stage is producing or not yet due.
     - It never PASSes on UNKNOWN.
   - The test adds `"daily_ledger"` to the `advisory` tuple and asserts `len(items) == 19` (18 on INTEG4).
     It also unit-tests the judge's UNKNOWN, WARN and PASS edges.
2. **HIGH, false zeros and the change-request flood: fixed** (D-ENG-DAILY-ZERO-RULE).
   - **New rule.** `stage_readings` gives each stage `zero_output`, `not_yet_due`, `producing` or UNKNOWN.
     A stage is `zero_output` only when three conditions all hold:
     - the UTC day is at least 6 h old;
     - the expected count by now (historical mean × elapsed fraction of the day) is at least 1.0;
     - today's count is at most 0.2 × expected.
   - Otherwise a stage reads `not_yet_due`, never DEGRADED. Because of the 6 h condition, the first
     six-hourly run of a day never diagnoses.
   - **Change requests** are filed only when the estimated last-24-hour window is also 0.
   - **Filing path:** through `improve.ecr.file`.
   - **Dedupe:** by fingerprint, per stage, per UTC day.
     - Today's diagnosis row records the fingerprints it filed.
     - The `ops.ecr_pending` fallback also refuses a second same-day row for that fingerprint, even when no
       diagnosis row exists.
     - A repeated run therefore never inflates `occurrences`.
   - `ops.ecr_pending` is classified in `ops.retention` (windowed, current day).
   - **New tests:**
     - zero history reads not yet due;
     - the 00:30 UTC run, at both a low rate and a high rate, run twice: no diagnosis, no ECR row, no pending
       row, no diagnosis row;
     - partial-day zero with output in the last 24 h: no ECR;
     - repeated runs through `ecr.file`: one row, occurrences 1;
     - repeated runs on the fallback: one pending row per day.
3. **Medium, `concepts_held`: fixed.** A day with no DONE `radar.scan` (by `finished_at`) is UNKNOWN,
   with the reason "no radar.scan completed this day". A stall reading counts as a measurement. Tested.
4. **Low, inverted pills: fixed.**
   - Failures and Dead letters: DEGRADED when non-zero, OK at 0.
   - Spend: a neutral "Recorded" pill.
   - Stage rows follow their reading: "Zero output", or "Not yet due", which is never DEGRADED.
   - Any other 0 reads "None today".
   - Browser-checked against the mock.
5. **Low, retention horizon: fixed.** The horizon day is UNKNOWN (`dd <= horizon`). Tested.
6. **Low, review-request table: fixed.** `daily_slice1.md` now ends with the run table.

## Bundle
INTEG4 plus the Daily view measured 403,169 bytes, over the 400,000 limit. Three changes brought it to
**393,345** bytes:
- `icon-512.png` and `icon-192.png` were re-encoded with zopfli. Their RGBA bytes are identical, verified
  before replacing.
- The Daily row labels and pill modes are now served with the panel (`daily_ledger.PANEL_ROWS`, tested
  against the ledger's metrics), and `daily.js` was compacted.
- `sw.js` drops its per-version comment history, which remains in git.
