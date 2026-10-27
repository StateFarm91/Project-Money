# Independent security and integrity review: W4-INTELREC fix range (720b291)

- **Date:** 2026-10-27 (UTC).
- **Reviewer:** an independent Claude Code session. It did not write the code under review, and this review fixes nothing.
- **Scope:** `git diff f8379deb..720b2915` on `claude/w4-INTELREC`. That is 3 commits: b71ee0b, d84a630 and 720b291. The review covers `brambleloop/src`, `brambleloop/tests` and `research/final_build/w4/intel`.
- **Prior review:** `INDEPENDENT_SECREVIEW_INTELREC.md` on `claude/w4-SECREVIEW-INTELREC` (1e9648d). Its verdict was CONDITIONAL, with H-1 and M-1 required before merge.
- **Constraints:** no production calls, no secrets, no deploys. The venv was built from `requirements.lock` plus `requirements-test.lock`. Every run used `nice -n 19`. The probes and the revert harness live in the session scratchpad, not in the repo.

## Verdict

| Question | Verdict | Basis |
|---|---|---|
| **Merge into the next SHADOW release** | **YES** | H-1 and M-1 are closed. Reverting either fix makes its new test fail. No new paid, outward or Etsy-writing call site exists. The three new Medium findings are a latent crash after about 197 days (N-1), a CA$0 daily repetition (N-2), and an H-1 residual that the current pool does not reach (N-3). None of them writes false state in SHADOW today. Fix all three before LIMITED PRODUCTION. |
| 1. Prior findings closed? | **13 of 14 closed**, plus 1 partly | 15 of the 16 single-fix reverts were caught by their tests. The one miss is L-3: the code is fixed but its test is vacuous (N-9). L-7 is only partly closed (N-10). M-2 is closed for direct origination, but its label over-claims (N-4). |
| 2. New paid, outward or Etsy-writing? | **No** | The added lines contain no new network, Etsy-write, model, vision or budget call. The only new `enqueue` targets are `radar.score`. Non-anchor missions do hold back the paid types (revert check M-3 was caught). Caveats are N-4, N-5 and N-7. |
| 3. `replication.study`: paid calls or copying? | **No** | `commerce/replication.py` imports only `dataclasses` and `datetime`. It is pure arithmetic over our own certified SKUs and order counts. No competitor data enters it. Caveat N-8: its outputs steer nothing yet. |
| 4. Watchlist test: 3 failures changed to 2 | **Stricter** | The third scan is no longer forced, so the new backoff applies and no third read happens. That is why the count is 2. The test also adds two assertions: ZKBDESIGNER is not called inside the window, and the shop is reported `deferred` with `backoff`. Removing the backoff makes it fail. |
| 5. Deliverables claim only what `evidence/` supports? | **Mostly** | The 4/101 figure (4.0 %) matches `TRACEABILITY.json` exactly: valid evidence yes=4, unknown=97, on rows B2#207, #208, #212 and #313. The CA$81.35 figure is now in `evidence/prod_verify…`. OWNER_REPORT labels b2e49455 as needing operator readback, but TRACEABILITY.md/.json state it as fact (N-10). The claim that the jobs "queue no paid work" is too broad (N-4). |
| 6. Bounded, idempotent, loop-free? | **Mostly** | The parked-gap revisit is bounded: one re-decision per gap per 7 days, or sooner on a new corroboration fingerprint. The backoff overflows and crashes the whole scan after 33 consecutive failures (N-1). Amplification never holds a family whose attempt *progressed*, and re-scores the same member every day (N-2). |

### Test runs

| Suite | Result |
|---|---|
| `tests/test_w4_intelrec_watchlist.py` | 12 ok, 0 fail |
| `tests/test_w4_intelrec_amplify.py` | 7 ok, 0 fail |
| `tests/test_cert_mjs.py` | 19 OK, 0 failed |
| `tests/test_w3_laura_core_executive.py` | 7 OK, "PASS: 0 failing" |
| `tests/test_w4_agents.py` | 14 OK, 0 failed |
| `tests/test_w4_agents_secfix.py` | 13 OK, 0 failed |

### Revert checks (question 1)

Method: a scratch copy of `src/` and `tests/`. Each fix was reverted on its own, and only the tests named for it were run.

| Prior finding | What was reverted | Test(s) | Result |
|---|---|---|---|
| H-1 | `score_outcome` books `not_attempted` as `failed` | `test_design_outcomes_are_classified_from_what_the_job_produced` | caught |
| H-1 | a promotion ignored (`if promoted:` → `if False:`) | same | caught |
| M-1 | `summary()` without the unobserved branch (the original logic) | `test_summary_is_unknown_when_unconfigured_or_refused` | caught |
| M-1 | key-wide refusal not recorded per shop | same | caught |
| M-3 | the scan passes the raw `enqueue` to the mission (no `unpaid` wrapper) | `test_no_paid_job_types_are_queued_by_the_scan_or_the_review` | caught |
| M-2 / M-4 | the review queues `creative.tournament` for an unanswered pod | same | caught |
| M-2 | `amplify` queues `creative.tournament` with no declared member | `test_no_declared_member_records_needs_original_design_and_queues_no_paid_job` | caught |
| L-1 | stale figures graded with their original basis | `test_stale_and_unmeasured_figures_are_not_measured` | caught |
| L-2 | zero reviews stored as 0 themes | same | caught |
| **L-3** | anchor label `rows_present` changed back to `ok` | same | **NOT caught** (N-9) |
| L-4 | `_parked` always False | `test_parked_gaps_are_not_redecided_daily`, `test_design_outcomes_…` | caught (both) |
| L-4 | fingerprint change ignored | `test_parked_gaps_are_not_redecided_daily` | caught |
| L-5 | `amplify` counts `not_attempted` as failed | `test_a_refused_or_dead_follow_on_is_not_a_failed_attempt` | caught |
| L-6 | no backoff | `test_refused_shops_back_off_…`, `test_duplicates_retries_outage_and_restart` | caught (both) |
| L-6 | `_OnceReader` removed (three resolves per scan) | `test_refused_shops_back_off_…` | caught |

Fixes that are documentation only:

- **M-5:** verified by reading the generator (`COUNT_EVIDENCES`) and the regenerated JSON. There is no unit test.
- **L-7:** verified against `evidence/`.
- **I-1:** verified in the diff.
- **I-2:** verified by the presence of the new tests above.

### Probes

These are offline, against temporary SQLite databases, using the test modules' own fixtures.

| Probe | What it showed |
|---|---|
| P-A | Real `radar.score` jobs from `review()`, run by the real `Worker`. **hats** and **blankets:** a concept is promoted, `cir.draft` is queued, and the gap moves to `concepting`. No downstream job other than `cir.draft` appeared. **garments:** both attempts score identically (0.5577 and 0.5254 on day 1 and on day 2). The two attempts become `failed_attempts=2`, the gap moves to `not_pursuing`, and an `observed` lesson is published. |
| P-B | A `radar.score` output with a numeric score, `promoted: False` and gate `decision: waiting` (`grid_tournament` unmeasured) is classified `failed`. Two of those produce `stopped_after_failures`, `not_pursuing` and an `observed` lesson. |
| P-C | A permanently failing shop is scanned on the 6-hourly cadence. At **day 197**, with `consecutive_failures=33`, `scan_all` raises `OverflowError: days=1073741824; must have magnitude <= 999999999`. |
| P-D | `amplify` runs 5 times, and each time the follow-on `radar.score` is promoted. Every run queues another `radar.score` for the same member (`nordic-star-ornaments`), with attempts 1 to 5. `last_outcome` is `progressed` and the family is never held. |
| P-E | `preengineering.gate_concept` on all 34 pool concepts in the fixture: every one is `refused` or `established`, and none is `waiting` or `request_grid`. So P-B's path and N-4's path are not reached by the current pool in the fixture. |

---

## Findings

Severity scale, as in the prior review:

- **High:** durable false state or a control gap; blocks merge.
- **Medium:** fix before production.
- **Low** and **Info:** hygiene.

### N-1. The backoff overflows after 33 consecutive failures and crashes the whole watchlist scan

- **Severity:** Medium (runtime safety). CONFIRMED by P-C.
- **Location:** `intel/watchlist.py:192` (`BACKOFF_BASE * (2 ** (fails - 1))`, evaluated before `min`). The call is outside the `try` at `:199`. `scan_all` at `:285` is a bare list comprehension. `runtime/intel_ops.handle_watchlist_scan` does not catch the error.

**Scenario.**

1. A watchlist shop closes or is renamed, so every read fails.
2. The backoff reaches its 7-day cap after about 5 failures. The counter keeps rising by one per week.
3. At failure 33, roughly 197 days in, the `timedelta` multiplication raises before `min()` applies the cap.
4. Members later in the list (TheEasyDesign) are not scanned.
5. `intel.watchlist_scan` fails on every run, is retried and dead-letters. The docstring promises "A per-shop outage is recorded and never fails the job".

**Fix.**

- Cap the exponent before multiplying, for example `BACKOFF_BASE * 2 ** min(fails - 1, 5)`.
- Isolate each member in `scan_all` with a `try`, recording an unexpected error as that shop's state.
- Add a test with `consecutive_failures=40`.

### N-2. A *progressed* amplification is never held and re-scores the same member every day

- **Severity:** Medium (the fix brought this back: "no endless repetition"). CONFIRMED by P-D.
- **Location:** `creative/family_engine.py:145-220` (`amplify`).

**Scenario.**

1. After `progressed`, `job_id` is cleared, `attempts` is incremented and `failed_attempts` is unchanged.
2. On the next daily run, `next_members[0]` is still the same seed, because it is not yet certified.
3. So a fresh `radar.score` is queued under key `amplify:{family}:{seed}:{attempt+1}`, and a fresh `investigate()` runs.
4. This continues until the member is certified. If its `cir.draft` is refused downstream, it continues forever, because a progressed attempt never counts toward `AMPLIFY_MAX_ATTEMPTS`.

Before this range, a DONE attempt with no follow-on member counted as failed, so the family was held after 2. Each repeat is CA$0 and one job per family per day. But it is the repetition the docstring rules out. Each promotion also re-runs the gate, which can request a grid tournament (N-4).

**Fix.**

- On `progressed`, record the promoted seed.
- Do not queue it again until its `cir.draft` or certification outcome is known.
- Count a promotion that has not certified within N days as a failed attempt.
- Add a test with three consecutive promoted runs.

### N-3. H-1 residual: a gate that is *waiting* on an unmeasured judgement counts as a measured failure, and identical re-scores count as independent attempts

- **Severity:** Medium (assertion integrity, durable lesson). PLAUSIBLE: P-B reproduced it with a synthetic output, and P-E shows the current pool does not reach it in the fixture.
- **Location:** `intel/watchlist.py:577-614` (`score_outcome`) and `:690-695` (the lesson is still published `confidence="observed"`).

**Scenario 1: the gate is waiting.**

1. `handle_radar_score` sets `promote = gate["engineer"]`. The gate returns `engineer=False` when its decision is `WAITING`, for example for a LONG or FLAGSHIP concept whose `grid_tournament` judgement is UNMEASURED (`creative/preengineering.py:609-616`, `:399-417`).
2. `score_outcome` looks only at `isinstance(score, number)` and `promoted`, so it books the result as `failed`.
3. Two such routes publish an `observed` lesson saying the attempts "did not clear promotion" and move the gap to `NOT_PURSUING`.
4. Nothing was measured: the gate was waiting for a judgement that had not been made. This is the class H-1 named ("a refusal or park is not an attempt").

**Scenario 2: the same measurement counted twice** (P-A, garments).

1. Route 2 re-scores the same pool concepts one day after route 1.
2. The score is deterministic, so it produces the same number. The two "attempts" are one measurement repeated.

**Fix.**

- In `score_outcome`, classify `gate.decision == "waiting"` (or a non-empty `gate.unmeasured`) as `not_attempted`.
- Count a second failed attempt only when its inputs differ from the first: a new corroboration fingerprint, a different scoring date window, or a changed evidence discount. Otherwise record it as a repeat.
- Add tests for both cases.

### N-4. "Queues only radar.score (non-spending)" over-claims: radar.score's gate can queue a paid grid tournament

- **Severity:** Low (label and downstream spend; the spend stays inside the creative ceilings). PLAUSIBLE: P-E shows it is not reached in the fixture.
- **Location:**
  - `creative/preengineering.py:689-698`: `record()` enqueues `creative.grid_tournament`, which is in `worker.MODEL_JOB_TYPES` and is YELLOW-light judge spend, when `request_grid` is set.
  - The claims: `autonomy/charters.py:36-39` (SAFE_GENERATED for `intel.opportunity_review`); `:88-91` (SAFE_GENERATED for `creative.family_engine`); `OWNER_REPORT.md:292` ("queue no paid work").

**Scenario.**

1. A routed concept clears the score threshold and is in an expensive make lane.
2. `make_board` gives it a board, so the gate requests a grid tournament.
3. Promotion then queues `cir.draft` and the rest of the engineering chain.

`test_no_paid_job_types_are_queued_by_the_scan_or_the_review` checks only the jobs queued directly. This is the same vacuity the prior review noted for M-3. The chain existed before this range for answered pods, but the range adds a new absolute "non-spending" claim.

**Fix.** Choose one:

- reword the claim to "queues radar.score only; its gate may request a creative.grid_tournament inside the creative ceilings";
- or pass a context flag that stops the gate requesting a grid for watchlist and amplification routes.

### N-5. A withheld paid step is recorded as "already queued", and the listing is consumed

- **Severity:** Low (a false durable record). CONFIRMED by reading the code.
- **Location:** `intel/watchlist.py:243-247` (`unpaid` returns `None`); `intel/mission_runtime.py:703-711` (`None` is read as a duplicate).

**Scenario.**

1. For a non-anchor shop's breakthrough step, the wrapper returns `None`.
2. `_enqueue_breakthrough` records `{"enqueued": False, "why": "a breakthrough tournament for this arena is already queued this week"}` in the `MjsMissionEvent`.
3. That event is keyed by listing fingerprint, so the listing is never processed again. If the owner later authorises this spend, these events will not be revisited.

The truth, "withheld: paid work not authorised for non-anchor shops", appears only in that one job's `paid_work_withheld` output.

**Fix.** Let the mission take a `withhold` predicate, or a sentinel return, and record `why="withheld (paid, non-anchor)"`. Optionally do not mark the step done.

### N-6. UNKNOWN takes precedence over DEGRADED in Laura's provider

- **Severity:** Low.
- **Location:** `intel/watchlist.py:497`; `laura/executive/loop.py:291-298` (UNKNOWN scores 35 against 60 for DEGRADED) and `:793-799` (UNKNOWN plus a recent run gives `monitoring`).

**Scenario.**

1. One shop is unobserved, for example because of a per-shop credential refusal under backoff.
2. Another shop is in `source_outage`, and validated opportunities are waiting.
3. The provider reads UNKNOWN, so the priority drops from 60 to 35 and is parked as `monitoring` once the review has run inside `PROVIDER_FRESH_HOURS`.

The reasons are kept, but the status understates the outage.

**Fix.** Return DEGRADED when `outages`, `stale` or `waiting` is non-empty, and keep `unobserved` in the reason. Alternatively, keep UNKNOWN only when nothing else is wrong.

### N-7. `PAID_JOB_TYPES` is a hand-copied list

- **Severity:** Low.
- **Location:** `intel/watchlist.py:60-63`; compare `runtime/worker.py:200-203`.

**Detail.** `PAID_JOB_TYPES` already lacks `seasonal.cycle_proof`, which is in `MODEL_JOB_TYPES`. The mission does not queue it today, but the two lists will drift.

**Fix.** Derive it: `MODEL_JOB_TYPES | {"assets.owned_photography", "assets.model_photography"}`. Or invert the wrapper into an allow-list of known non-spending types.

### N-8. The #22 study is recorded but steers nothing

- **Severity:** Low / Info.
- **Location:** `creative/family_engine.py:201`, `:223-283`.

**Detail.**

- `amplify_holds` is not read anywhere in `src/`: `radar.score` ignores it, and `commerce.replication.adjacent()` is never called. The test name `…the_follow_on_holds_its_causes` checks only the job input.
- `study(starts=today)` is re-run on every attempt, so its 45-day `ends` resets each time.
- `weeks_live` is measured from the first order, not from certification.
- `_skus` takes a `today` parameter it never uses.

None of this spends money or copies anything.

**Fix.** Either describe the field as "recorded for the follow-on; not yet enforced", or check the follow-on with `replication.adjacent()`. Persist the first `starts` for the family and keep it.

### N-9. The L-3 test is vacuous

- **Severity:** Low (test integrity).
- **Location:** `tests/test_w4_intelrec_watchlist.py:514` (`state in ("rows_present", "never")` on `rep["shops"][0]`).

**Detail.** Reverting the fix (`rows_present` → `ok`) still passes. The fixture's anchor has no rows, so `never` satisfies the assertion either way.

**Fix.** Seed Mrs J listing rows, select the anchor by role rather than by position, and assert `== "rows_present"`.

### N-10. L-7 is partly closed: TRACEABILITY states the production SHA as fact, while the captures name a different build

- **Severity:** Low (report honesty).
- **Location:** `TRACEABILITY.md:6` ("**Production:** b2e49455.") and every per-row "production b2e49455"; `TRACEABILITY.json` `"production": "b2e49455"`; `OWNER_REPORT.md:178`.

**Detail.**

- `OWNER_REPORT.md:6` now labels b2e49455 correctly, as coming from the coordinator's record and needing operator readback.
- The git history agrees with that record. b2e49455 is 051dbee2 plus SECPATCH (f88f056, 4ff953d, 5abc967) plus a record commit. At b2e49455, `intel/benchmarks.REGISTRY == (MJS,)`, so the code fact in CHAIN holds.
- But `evidence/prod_gates_2026-10-26T1724Z.json` says the 17:24Z captures came from **051dbee2 (pre-SECPATCH)**. TRACEABILITY attributes those same captures to "production b2e49455" with no qualifier.

**Fix.** In TRACEABILITY, label the build "b2e49455 per the coordinator's deployment record (needs readback); the 17:24Z captures name 051dbee2". Use the same label in the JSON `production` field.

---

## Prior findings: status

| ID | Status | Notes |
|---|---|---|
| H-1 | **Closed**, with residual N-3 | `score_outcome` classifies attempts from `radar.score` outputs. The review and amplification no longer queue tournaments, so the ceiling-refusal and wrong-arena paths are gone. The lesson wording now matches what was measured. Revert checks caught. |
| M-1 | **Closed** | Unobserved, not-configured or refused reads UNKNOWN, and the key-wide refusal is recorded per shop. Revert checks caught. See N-6 for precedence. |
| M-2 | **Closed** for direct origination; label residual N-4 | The SAFE_GENERATED reasons are rewritten. `needs_original_design` queues nothing. |
| M-3 | **Closed**, with residual N-5 | The `unpaid` wrapper drops the paid types for non-anchor missions. The worker comment and the handler docstring are corrected. |
| M-4 | **Closed by construction** | The review queues no tournament, so there is no arena for it to mis-book. |
| M-5 | **Closed** | `COUNT_EVIDENCES` is restricted to #207, #208, #212 and #313. The regenerated JSON has valid evidence yes=4 of 101. OWNER_REPORT row 12 reads "4.0 % by record; 0 % by acceptance readback" and explains the change. |
| L-1 | **Closed** | `STALE` when the latest read failed. |
| L-2 | **Closed** | `None` when zero reviews were read, which grades UNKNOWN. |
| L-3 | **Closed in code**; test vacuous (N-9) | — |
| L-4 | **Closed** | `_parked`: a 7-day re-decision, or sooner on a fingerprint change. Bounded, and dropped from `waiting`. |
| L-5 | **Closed**, but see N-2 | — |
| L-6 | **Closed**, but introduces N-1 | Exponential backoff, and one resolve per scan. |
| L-7 | **Partly closed** (N-10) | `/api/verify` is captured (CA$81.35 of CA$100 matches). The 403 is labelled with its source. The SHA is labelled in OWNER_REPORT only. |
| I-1 | **Closed** | The comment is restored to the `research.sweep` line. |
| I-2 | **Closed** | Tests exist for every listed gap. The downstream-cost test checks direct enqueues only (N-4). |

## Answers to the six questions

1. **Prior findings.** See the two tables above. 15 of the 16 reverts fail their tests, and the miss is L-3 (N-9).
2. **Paid, outward or Etsy-writing.**
   - Nothing new does any of these.
   - The scan wraps `enqueue` only for non-anchor members. `mjs.scan` is untouched. Each `PAID_JOB_TYPES` entry is dropped and reported. The only types the mission queues (`creative.tournament`, `assets.owned_photography`) are both in the set.
   - Indirect spend is still possible through `radar.score`'s gate (N-4). The withheld step is recorded inaccurately (N-5).
3. **`replication.study`.**
   - It makes no paid call and no I/O: it is deterministic arithmetic over our own `Sku` records, built from certified `PatternVersion` rows, our `Order` counts and our radar pool traits.
   - It reads no competitor content.
   - It is bounded by `MAX_CAPACITY_SHARE` (0.35) and `MAX_STUDY_DAYS` (45). The handler asks for 0.2.
4. **The test change.** It is stricter (see the verdict table). The old `== 3` would now describe a defect, a read inside the backoff window.
5. **Deliverables against `evidence/`.**
   - These figures check out: 4/101, CA$81.35, 3 `intel.panel_discovery` runs (last 27000), 16 `intel.serp_capture` runs and 266 `mjs.scan` runs all match `evidence/prod_job_counts…` and `prod_verify…`. The `second_market_benchmark` gate reads open in `prod_gates…`.
   - The seed-shop section claims only that *some* non-US panel member is observed, and marks which one as needing readback. That matches the gate definition.
   - Gaps: the SHA labelling in TRACEABILITY (N-10), and "queue no paid work" (N-4).
6. **Boundedness, idempotency and loops.**
   - Parked-gap revisit: at most one re-decision per gap per `REDECIDE_AFTER` (7 days), or on a new corroboration set. A refused route is retried on a fresh `routes` key at most weekly, with at most 10 CA$0 `radar.score` jobs. A progressed gap leaves `_open_gaps` (P-A: no third decision).
   - Backoff: correct up to its cap, then it overflows at 33 failures (N-1). A forced scan bypasses it by design.
   - Amplification: no endless repetition only on the failure path. The success path repeats daily (N-2).

## Minimum before LIMITED PRODUCTION

1. **N-1:** cap the exponent and isolate each member in `scan_all`.
2. **N-2:** stop re-queuing a promoted member, and age out a promotion that never certifies.
3. **N-3:** a waiting gate is `not_attempted`, and an identical re-score is not a second attempt.
4. In the same pass, because they are small: N-4 (label), N-5 (record), N-9 (test) and N-10 (label).
