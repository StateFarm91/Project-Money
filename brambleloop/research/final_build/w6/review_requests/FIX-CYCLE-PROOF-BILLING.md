# FIX-CYCLE-PROOF-BILLING — review request

- **Branch:** `eng/fix-cycle-proof-billing`, cut from `claude/w6-INTEG8-wip` (511a8c6, = production a4952711 / Batch 18).
- **Fix SHA:** `264def0`. Not deployed; production unchanged. No PR opened.

## Production evidence (2026-11-20 22:05Z)
`paid_call_dedupe` FAIL: `anthropic.messages` db5496af2005 billed 6x (cycle_proof jobs 70594, 70762, 72111, 72527) and
`model.probe` beff7c26565a billed 2x (72529, 72706). `weekly_jobs`: cycle_proof dead after its last success.
`seasonal.cycle_proof:unclassified` x7.

## What raised and read `unclassified`
Only two paths dead-letter a job. `fail()` always writes `Class: msg` or a mapped worker prefix. The other is the
reclaim path: a job whose lease lapsed on its last attempt got `coalesce(last_error,'') + " | lease expired, retries
exhausted"`. After a redrive (`requeue_dead` / `rerun_department_cycle` set `last_error=NULL`), that is the whole error,
and no reader can classify it. The weekly proof is the long, model-and-render handler that a deploy or a stall
kills mid-run. So "something else still raises" is the lease lapsing, not a handler exception. This is inferred:
I did not read production rows. The text match is exact.

A second defect sat in the reader. `error_class` only knows exception classes already loaded in the reading process,
so a fresh process read `PaidCallUnresolved: …` as `unclassified` (reproduced).

A stub reproduction of the full cycle (`_WideGateway`, images usable) completes without raising.

**Fixes:**
- `queue/durable`: the dead letter now reads `LeaseExpired: lease expired on every attempt…`, with ` | previous: <old
  error>` kept after it.
- `ops/production_evidence`: the legacy `| lease expired` maps to `LeaseExpired`, and the exception modules are
  imported before classifying.
- `runtime/release` cycle_proof: `PaidCallUnresolved` and `PaidCallReplayedFailure` are now an audited refusal
  (`paid_call_reconciliation`), never a dead letter. `LeaseLost` re-raises instead of being reported as a balance
  refusal. Refusals carry `error_class`.
- Real defects still dead-letter with their class (tested with `KeyError`).

## Why it re-billed
The paid-call key is `job:<id>:fp:occurrence`, so each new proof job (redrive mode `enqueued`, cadence, recovery) asked
the same question again. `complete_json` also retries a malformed answer under the same prompt (occurrence 1), which
is how 4 jobs produced 6 bills.

**Fixes:**
- `gateway/paid_calls`: `CROSS_JOB_REPLAY = {"seasonal.cycle_proof": 7 days}`. A request with the same effect,
  job_type, fingerprint and occurrence made by an earlier job is served from that job's record:
  - OK → replayed, CA$0, `replays` incremented, audit `across_jobs`;
  - FAILED_BILLED → `PaidCallReplayedFailure`;
  - PENDING or UNCERTAIN → `PaidCallUnresolved` (F-339);
  - DECLINED → asked again.
  No billed row is written for the replaying job.
- F-659, every paid step checkpointed: the cycle's gateway is wrapped (`_CheckpointedGateway`). Each `complete_json`
  answer is checkpointed under its call position plus a digest of the request. The asset maker's record is
  checkpointed per slug. The whole report is still checkpointed as before.
- Redrive guard (`queue/durable.unreplayable_spend`, used by `requeue_dead` and `ops/recovery.rerun_department_cycle`):
  a dead letter is skipped or refused when it has a billed paid call with no replayable outcome (not OK) and no
  checkpoint. Jobs with no paid calls are unaffected.

## model.probe
The probe re-asks when a later paid call contradicts the success. But Anthropic's transport records only DECLINED or
UNCERTAIN, so a 429, a 529 or another job's timeout (the cycle's 4000-token field) re-billed the probe. Now only funding
or a `ProviderUnusable` decline contradicts it; real outages are still read by the shared breaker.
`test_eng_stale_rebuild_loop::test_p2_four_cadence_runs_a_day_bill_once` uses a `ProviderUnusable` DECLINED row instead
of a bare FAILED_BILLED row. This is a semantic change, flagged for review. The trigger in production is inferred,
not read.

## Tests — `tests/test_fix_cycle_proof_billing.py`
11 SQLite + 5 Postgres (disposable cluster): **16 OK / 0 FAIL**. Real worker, queue and guard. The HTTP transport and
the cycle body are stubs.
- The redrive serves the replay and bills 0: three failed attempts, then dead letter, then redrive, then a new job.
  1 send total, the new job bills CA$0, `repeated_billed_requests == 0`, `replays_served >= 1`.
- The fixed error is classified: `LeaseExpired` (new rows, the legacy text, and with a previous error kept).
  Classification in a fresh process. Paid-call refusal → DONE + audit. A real defect still dead-letters.
- Weekly completion holds: a failed paid attempt then a retry gives DONE, 1 send, `completing: True`.
- The spending redrive guard covers both `requeue_dead` and recovery.
- The probe is not re-billed after another job's timeout, and is re-asked after a `ProviderUnusable` decline.
- **Mutations killed:** with `CROSS_JOB_REPLAY` emptied the new job repays (sent 2); with the guard bypassed the
  redrive goes through.

## Suites run
| Suite | Result |
|---|---|
| test_seasonal_cycle, _incidents, _occasion_vocab, _transform, test_cert_growth_seasonal, test_w4_fmbatch1_seasonal_cohort | exit 0 |
| test_provider_trial | exit 0 |
| test_w3_spend_gateway_w8, test_w3_spend_paid_calls | exit 0 |
| test_vacuity | exit 0 |
| test_w4_resume_runner | exit 0 (new suite added to `scripts/suite_final_segment.txt`, F7) |
| test_w4_fml_checkpoint_adoption, test_eng_recovery, test_v11_autonomy_recovery, test_v11_reliability_recovery, test_cert_thrash | exit 0 |
| test_eng_stale_rebuild_loop | p2 probe tests 3/3 OK run alone; the full run timed out at 20 min under 6-way parallel load with 0 FAIL |
| test_eng_stale_round2 | 23 OK / 0 FAIL, then the timeout |
| test_chaos | 32 OK / 0 FAIL, then the timeout |
| test_persistence | `test_pipeline_resumes_across_a_worker_restart_mid_flight` FAILS **identically on the base 511a8c6** (pre-existing); the other 10 OK |

There is no suite named "paid-call-dedupe" or "queue". Those are covered by test_w3_spend_paid_calls, the new suite's
`production_evidence.paid_calls` assertions, and the recovery and persistence suites.

## Not done / open
- The probe and lease triggers are inferred from code and error text. The production rows were not read.
- After deploy, run `requeue_dead(job_types=["seasonal.cycle_proof"])`. Spending rows without a checkpoint will be
  skipped with the reason.
