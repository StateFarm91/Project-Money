# W4-LEARN — turning the learning loops into measured experiments (LEARN_FIX)

Lane W4-LEARN, branch `claude/w4-LEARN`, based on production's build **0417f35** (fast-forwarded
from the earlier LEARN work, which 0417f35 already contains). Evidence was taken on
2026-10-11 14:40Z using read-only public `GET /api/*` calls only. The snapshot is saved as
`evidence/learn_prod_snapshot_20261011.json`. Nothing was deployed, and nothing was written to
production, Etsy or Railway.

## 1. What production shows now

The old scoreboard said "cells measured 0/12, lessons acted on 0". That reading came from the
fcb982d build. On 0417f35 the rows say something different:

| Signal (production, 0417f35) | Reading |
|---|---|
| Capability cells | **8/13 measured**. The other 5 (pricing, growth, customer_experience, portfolio, finance) are data-gated because they need a sale, order, traffic or a forecast. They are UNKNOWN, not 0. |
| Lessons | 379 recorded, 379 routed, **0 acted on**. 369 of them are `defect` lessons: `improve.mine` read 367 rows, grouped them into 364 groups and published 316 in a single pass. |
| Open incidents | 347, of which **300 are `stale-artefact:<kind>:<slug>@<v>#<n>`**. Each signature became its own lesson. |
| Improvement proposals | **15, all PROPOSED.** 14 are teardown-lab delight hypotheses (#169: "Raising customization on X from 3 to ≥4"). On every pass the sandbox reports "waiting for a trial that can evaluate them". |
| Job-priority replay | A real experiment on **11,958 jobs over 25 days**. All 6 challengers were rejected (gain 0.000 < margin 0.030). The verdict never reaches `experiments_completed` and the loop never re-judges. |
| Retrospective | Names market_radar as "regressed" and as the **bottleneck** because evidence age went from 0.11 h to 0.14 h. Both readings fall inside the 2 h scan cadence. |
| Growth experiments | 80 (64 registered, 16 gated). `growth.conclude` examined 0. No listing is live. |
| Realised benefit | 0 promotions, so nothing has been assessed. |

## 2. The loops: producer → store → metric/baseline/rule → consumer

All of these are readable at `GET /api/improve` under `loops` (`improve/loops.py`, read-only).

| Loop | Producer | Accumulates in | Metric / baseline / decision rule | Consumer | Status |
|---|---|---|---|---|---|
| capability_cells | `improve.measure` | CapabilityPoint | Each cell's metric against its first reading. Direction is judged outside the metric's noise floor. | retrospective | MEASURED (8/13). 5 UNKNOWN, post-launch only. |
| lesson_bus | `improve.mine`, intel findings, learn radar | Lesson (live = not superseded) | Routed live lessons acted on. A consumer acts only when the lesson changes a decision. | radar.score, cir.draft heuristic, listing.seo, support triage, growth content, seasonal daily, learn.scan | WAITING. Defect lessons route to quality/runtime, which have **no consumer**. pattern_engineering acts only on favouring lessons. |
| job_priority_replay | `improve.replay` | ConfigVersion + league runs | Band-weighted on-time share. The baseline is the incumbent on the same jobs. A change is accepted only if it beats the incumbent by the 0.030 margin on shared days **and** holds on the holdout. Otherwise it is retired. **It is now re-trialled after 7 days.** | sandbox → evaluator → scoring tier → `priority_policy` | MEASURED (6 rejected in production) |
| improvement_backlog | teardown delight QA, policy loops, replay, teardown pipeline | Improvement | Each row is judged on its own metric against its proposal-time baseline. **The bounded backlog (below) applies.** | `improve.sandbox` → `improve.backlog.evaluate` + trials | Was WAITING forever. Now each row is decided or expires. |
| realised_benefit | promotions | Improvement + CapabilityPoint | Post-promotion movement against the baseline | runner discipline, role scorecards | UNKNOWN: no promotion assessed |
| growth_experiments | experiment registry | Experiment | Per design (holdout, stop rule) | `growth.conclude` | UNKNOWN: no live listing, so no traffic |
| learn_gap_coverage | `learn.scan` | LearnGap | Gaps covered / gaps total | editor plan | MEASURED in production (0/20). No bus lesson matches a gap topic yet. |

## 3. Fixes (code)

1. **Lessons are grouped by incident family, not by instance** (`improve/mine.py`,
   `incident_family`). A signature keeps its leading tokens up to the first instance token
   (a product slug, `@version`, `#n`, a hex hash or a number). Production's 347 open
   signatures become **53 families**; the 300 stale-artefact rows become 11. Per-signature
   lessons that already exist are **superseded** by their family lesson (`superseded_by`), so
   they leave the live inbox and stay on record. `bus.compounding` now counts live lessons and
   reports `superseded` as a separate number.
2. **Bounded improvement backlog** (`improve/backlog.py`, run on every `improve.sandbox` pass):
   - A delight hypothesis is re-measured with the instrument that raised it
     (`teardown.lab.delight_for` over `measured_self_scores`).
     - If the score moved up, `cells.test_result` moves the row to TESTING (verified).
     - If the score moved down, it is REJECTED.
     - If the score is unchanged after 14 days, it is REJECTED as `expired unexecuted`.
     - If the driver cannot be read, the result is UNKNOWN. That row waits, then expires as
       `expired unmeasured`. It is never given a score.
   - Proposals with no trial expire after 30 days.
   - Each cell may hold at most 8 open proposals with no trial. When it holds more, the oldest
     are deferred on record.
   - Admission control in the producer (`teardown/lab.py`): a hypothesis cannot be re-opened
     within 28 days of being closed, and each cell may hold at most 8 open delight proposals.
     A new proposal also carries `expected_gain`, so the ROI order can rank it.
3. **Replay retrial** (`improve/replay.py`, `reopen_retired`). Once every neighbour is known,
   any neighbour retired at least 7 days ago is re-opened. It is then judged on the current
   30-day window. The retrial is audited as `improve.replay.retrial`.
4. **Noise floor in the retrospective** (`improve/cells.py`). When both freshness readings are
   ≤ 2 h (the `mjs.scan` cadence), the cell is reported as `flat`. That means it is no longer
   the bottleneck. A real staleness, such as 30 h, still reads as regressed.
5. **Scoreboard** (`improve/loops.py`, exposed in `/api/improve.loops`). It shows each loop's
   status (MEASURED, WAITING or UNKNOWN, each with a reason) and totals of accepted, rejected
   and open experiments. A replay winner is counted once.

## 4. End-to-end verification on a scratch DB seeded like production

Script: `scripts/w4_learn_loops_proof.py`. Output: `evidence/learn_loops_proof.json`. The run
used SHADOW mode with the network closed and took about 400 s.

| Step | Result |
|---|---|
| Real chain: 3 Launch-0 CIRs, 51 jobs | The teardown lab itself opened **5 delight proposals, customization = 3**. This is the same shape as production. |
| A. `improve.mine` on 12 production-shaped stale-artefact incidents plus 12 per-signature lessons | Live lessons went from 12 to **2**, with **12 superseded** and 0 acted on (honest). |
| B. `improve.replay` on 29,919 jobs regenerated from production's 114 cadences | 6 challengers were measured and **rejected** (gain 0.000), the same result production recorded. The next day reopened 0 of them. After the retrial window, **6 were reopened, re-judged and rejected again**. |
| C. Accept path. **SYNTHETIC**: a separate DB holding 50 contention jobs | The challenger scored 0.8 against a baseline of 0.5. The sandbox recorded a passed regression test and a passed adversarial test, the evaluator approved, and the scoring tier promoted. The change was executed: **the active priority policy is now the challenger.** 4 losers were rejected. |
| D. Delight backlog through `improve.sandbox` | Inside the TTL, 5 rows were re-measured at 3.0 and are waiting. At TTL + 1 day, **all 5 were REJECTED as `expired unexecuted`** with the measured reading recorded. The backlog went from 5 open to 0. |

Finding from B: the job-priority policy has **no leverage on production's history**. No
production job carries a deadline or a value, so every policy ties. The rejection is correct.
The experiment only becomes informative once customer or seasonal jobs carry deadlines.

## 5. Still UNKNOWN (no real data, so nothing was invented)

- pricing, growth, customer_experience, portfolio and finance cells
- growth experiments, realised benefit and the CA$5K gate. All of these need sales, orders or
  traffic.
- Lessons acted on in production is still 0. Defect families route to cells with no consumer
  (quality, runtime) or to consumers that only act on favouring lessons. Building a consumer
  that acts on defects would need a decision a defect lesson can honestly change, and none
  exists yet. This is reported as structural, not hidden.

## 6. Tests (focused, run one at a time)

- `tests/test_w4_learn_loops.py`: 13/13 pass (new).
- Existing suites, 0 FAIL: test_mine 7, test_improve 32, test_w4_learn_presale 14,
  test_improve_director 14, test_measure 7, test_improve_handlers 8, test_cert_improve_wave 24,
  test_cert_improve_autonomy 20, test_cert_culture_teardown 16, test_cert_unique_value 6,
  test_v11_learn_loops 18, test_w3_k10_learn 23, test_cert_learning 15, test_reachability 11,
  test_vacuity 8, test_secret_scan 7.
- test_w3_tmp_hygiene: 15/16. The one failure is `test_protected_bands` (concurrent claim
  order) failing under shared-CPU load. That test passes 6/6 when run alone, twice, and does
  not touch code changed here.

## 7. After deploy

With the families in place, production's next `improve.mine` should supersede about 316
per-signature lessons into about 53 family lessons. The first `improve.sandbox` pass more than
14 days after a proposal was opened should close all 14 delight rows as `expired unexecuted`.
`director.stop_doing` should then flag the tactic family. The replay should re-judge its 6
neighbours from 2026-10-18.
