# Review request — WS4-8 Stage A wiring (`eng/ws4-8-stage-a-wiring`, base `claude/w6-INTEG2` @ f34c25ae)

## Fix round 1 (answers main's DO NOT SHIP on be45c37c, MEDIUM-1)

**Merges.** `origin/claude/w6-INTEG2` was already an ancestor (still f34c25ae on origin when
this ran). Main reported `opus2/stage-a-lows-3` 50242d0c as merged in INTEG2, but it was not
yet on origin, so 50242d0c was merged here directly with a merge commit (no rebase, no force).
It is the same reviewed commit, so INTEG2 will see no duplicate.

### MEDIUM-1: a crash after the listing goes live no longer loses lineage silently

1. **The retry reaches reconcile** (`runtime/pipeline.py::handle_store_activate`).
   - The `local_state == "active"` stop now applies before the Etsy read **only to owner
     jobs**.
   - A standing job reads the listing, then runs `grant_for_job`, then:
     - stops with "already active" when `activation_verified` already names this listing and
       grant (`standing_activation_flow.lineage_recorded`);
     - otherwise runs `reconcile`, which sends nothing to Etsy.
   - `reconcile` (needs this job's claimed intent and an Etsy read-back `active`) now writes
     `store.activated` only when no standing `store.activated` names this listing and grant.
     That covers a crash between the active commit and `store.activated`, as well as a
     `record_activated` failure after it.
   - When the row is active, there is no lineage, and nothing can be reconciled while Etsy
     reads it active (for example, the intent is not this job's), the job sends nothing and
     opens the P1 incident.
2. **`record_live` wraps `record_activated`.**
   - Any exception opens P1 `standing_activation.lineage_unrecorded:<listing>`, best effort.
     An incident write that fails is logged and never raised over the result.
   - It is idempotent: it returns True without a second row when the lineage is already
     recorded.
   - Once a retry records the lineage, it resolves the incident.
3. **Tests** (`tests/test_ws4_8_stage_a_wiring.py`):
   - `test_record_activated_raising_once_opens_an_incident_and_the_retry_repairs_lineage`:
     - first attempt: `OperationalError` once, incident open, no lineage;
     - retry: reconciled, 1 `activation_verified`, 1 `store.activated`, 1 send, 1 fee,
       `plan()` live == [lid], `lineage_of_live` names the grant, incident resolved;
     - a third run returns "already active".
   - `test_record_activated_raising_on_every_attempt_is_never_silent`: the incident stays
     open across retries.
   - `test_record_live_reports_even_when_the_incident_cannot_be_written`.
   - `test_a_crash_between_the_active_commit_and_store_activated_is_repaired_by_the_retry`:
     `SystemExit` at the `store.activated` audit; the retry writes 1 reconciled
     `store.activated` and then the lineage, with 1 send and 1 fee.
   - `test_an_active_listing_this_job_cannot_reconcile_is_an_incident_not_silence`.
   - `a_retried_job_never_activates_or_charges_twice` now also asserts 1 `activation_verified`
     and 1 `store.activated`.

### Semantic merge conflict with opus2's guard

`test_ws4_stage_a_activation.py::test_the_activation_handler_records_the_verified_activation_once_it_handles_seg_grants`
now accepts either of two calls in the handler, and still requires the call to follow
`"store.activated"`:
- a direct `record_activated(` call;
- `stage_a.record_live(`, in which case `inspect.getsource(record_live)` must contain
  `SA.record_activated(`.

### Auto-renew functional gap

- `ListingPayload.to_dict()` now always carries `"should_auto_renew": False`. It is not a
  parameter, so nothing can ask for renewal. Renewal costs US$0.20 per 4 months.
- So `create_draft` sends it, and the F-542 read-back (`etsy_ops.read_back` →
  `etsy_verify.verify`) compares it like every other sent field: True is a MISMATCH, absent
  is NOT_RETURNED.
- The activation readiness re-check (`sent_fields`) does the same.
- `tests/fake_etsy.py` honours the field on create. A create that omits it gets
  `create_auto_renew_default = True`, conservatively, so a client relying on a default is
  caught.
- The wiring tests' `_world` no longer forces the flag: it asserts the draft was created with
  it off. The new test is `test_the_draft_is_created_with_auto_renew_off_and_the_read_back_proves_it`.
- `test_w4_launchfix` D1 changed from "not in payload" to "payload says False". Its no-source-
  sets-True scan is unchanged.

### Mutants (fix round; PYTHONDONTWRITEBYTECODE=1, `__pycache__` cleared, each alone, file restored)

All 14 killed (M1–M11 against the wiring suite, G1b–G3 against `test_ws4_stage_a_activation`):

| Mutant | Killed by |
|---|---|
| M1 "already active" stop before reconcile for standing jobs too | raising-once test |
| M2 `record_live` lets the exception propagate | raising-once test |
| M3 exception opens no incident | raising-once test |
| M4 `record_live` not idempotent | retried-job test |
| M5 reconcile always writes `store.activated` | retried-job test |
| M6 no "lineage recorded → already active" stop | retried-job test |
| M7 unreconcilable active listing opens no incident | unreconcilable test |
| M8 payload omits `should_auto_renew` | lineage test (`_world` assertion) |
| M9 fake ignores the sent field | lineage test |
| M10 repair does not resolve the incident | raising-once test |
| M11 incident write failure propagates | incident-cannot-be-written test |
| G1b handler drops the `record_live` call | the opus2 guard |
| G2 `record_live` no longer calls `SA.record_activated` | the opus2 guard |
| G3 `record_live` named before `"store.activated"` | the opus2 guard |

The first G1 attempt failed with a SyntaxError, which does not count as a kill. It was re-run
with valid code (G1b) and killed by the guard's assertion.

SUITES_PLACEHOLDER

Wires a Stage A standing activation grant (`seg:<id>`, from `standing_activation.issue`) into
`runtime/pipeline.py::handle_store_activate`, which is the only path that uses it. Adds the
deterministic scheduler that queues standing activations. **`STAGE_A_ENABLED` stays `False`**
and was not touched, so in the shipped state every new path is a recorded refusal or a no-op.
No Railway, production, Etsy, spend or phase change. No slot-table or role-model code was
touched (L-A belongs to opus2).

## What changed

- **`ops/standing_activation_flow.py` (new): the use path around the grant.**
  1. `schedule` is the `policy.activation_schedule` job.
     - It is a recorded no-op (`standing_activation.schedule_skipped`, with the reason) when any of these holds:
       - Stage A is off in code;
       - no approved standing policy is EFFECTIVE;
       - the effective policy does not name `store.activate`.
     - Otherwise it walks the certified releases whose verified draft is `published` (`candidates`), keeps only drafts in SP lineage, and calls the real `standing_activation.decide` (every gate, pace and fees).
     - Stage A shadow decisions:
       - It records at most one decision (`standing_activation.shadow_decision`) per (approval, release, decision).
       - The would-decision ignores only Stage A's own shadow gate.
       - Until now nothing in `src` wrote these rows, so `a_shadow` could never pass.
     - It queues **at most one** standing `store.activate` per pass, and none while a standing job or an unanswered request is outstanding.
     - The queued job runs no earlier than `run_after = now + 3 min`.
     - It writes `policy.activation_grant_requested`. That row is a request only and carries no authority.
  2. `pending_requests` and `answer` run in the policy-issuer service only (`app/issuer_entry.tick` now answers these too).
     - `job_refusal`: the job must be a live `store.activate` job for this exact release that set `standing_activation` and has no owner approval.
     - It then calls `standing_activation.issue`, which re-derives every fact.
     - Any failure becomes `policy.activation_grant_held`, so each request is answered once.
  3. `grant_for_job` finds the grant from the grant store by its signed `job_id`. It never reads job inputs.
  4. `claim` consumes the grant once. A retry of the same job finds it already consumed by itself; any other job is refused.
  5. `record_live` calls `record_activated`. If a listing reads live but its lineage cannot be recorded, it opens a P1 incident (`standing_activation.lineage_unrecorded:<listing>`).
  6. `reconcile` handles a crash after the Etsy request. It reads the listing back, records the activation and sends nothing.
- **`runtime/pipeline.py::handle_store_activate`.** A job marked `standing_activation`:
  - is refused if it also names an owner approval (one authority per job);
  - finds its grant, then reconciles first (retry after a crash).
  - After that it runs the **same** steps as the owner path, unchanged: readiness read-back, release gates and parity, the client's ACTIVATE refusal (kill switch / credentials), the daily ceiling with the listing fee, re-checks of gates, phase and the publishing grant before and after the spend reservation, the phase immediately before the request, the `etsy.activate` effect guard (idem `<listing>:seg:<id>`, CLAIMED, job-bound), the client's `use_refusal` with the intent, and the read-back.
  - Where the owner path calls `activation_authority.validate`, it calls `use_refusal(..., at_effect=False)`, because the intent cannot exist yet at those points.
  - `OwnerGrant` now gets `job_id`.
  - `store.activated` carries `authority: standing|owner` (and `grant_id`).
  - **L-B:** only when `live` (read-back state `active`) and after `store.activated` is the listing recorded in SP lineage.
- **`ops/standing_activation.py` (small).**
  - `use_refusal(at_effect=True)`: `at_effect=False` skips only the intent lookup. The client always calls with the default.
  - `issue(request_id=None)`: the id is written into `policy.activation_grant_issued`.
  - Docstring updated.
- **Plumbing for the new job.**
  - `worker.CADENCES`: hourly, `publishing`.
  - `WORK_KEYS`, registry `publishing.allowed_job_types`, `authority/classes` (`_O`), `charters` (store_commerce), `orchestrate.JOB_BANDS`.
  - `autonomy_map.json` regenerated (cadences 142, handlers 174).
- **Retention.** New entries: `policy.activation_grant_requested`, `…_issued` and `…_held` (windowed, like the publish request rows), and `standing_activation.schedule_skipped` and `.scheduled` (windowed, owner record). `ops.retention.unknown_read_actions() == []`.
- **`scripts/suite_final_segment.txt`:** adds `tests/test_ws4_8_stage_a_wiring.py`, because grants are signed against the clock with a 15-minute life. `test_product_run` is still last.

## Guards (requirement → evidence in `tests/test_ws4_8_stage_a_wiring.py`)

The handler tests run the real `Worker` against stub Etsy, with real Ed25519 grants, the real
snapshot, consume, intent and `use_refusal`.

| Requirement | Tests |
|---|---|
| 1. Route through the handler, all guards | `…activates_through_the_handler_and_enters_lineage` (consumed by its job, intent APPLIED with idem `<lid>:seg:<gid>`, one fee row); `…shipped_switch_refuses_a_consumed_grant` (OFF at the handler, nothing spent); `shadow_refuses_before_any_etsy_read_or_grant_use` (DEAD, no request, grant unconsumed); `no_grant_for_this_job_is_no_authority`; `a_standing_job_carries_one_authority`; `the_client_refuses_a_standing_grant_without_the_handlers_intent` |
| 2. L-B, appears in `plan()`; failed read-back records nothing | lineage test asserts `standing_withdrawal.plan()` `live == [lid]`, `lineage_of_live` names the grant, and the `ACTIVATED` row id is after `store.activated`; `a_failed_read_back_records_nothing_as_activated`; `record_activated_refuses_a_read_back_of_another_listing_or_state` |
| 3. Owner-activated never in lineage | `an_owner_activated_listing_is_never_in_stage_a_lineage` |
| 4. Idempotence and crash safety | `a_retried_job_never_activates_or_charges_twice` (one send, one fee even with the local record lost); `a_crash_after_the_etsy_request_reconciles_from_the_read_back` (UNCERTAIN intent, reconciled, `effect.reconcile` incident resolved); `a_crash_before_etsy_applied_is_never_resent` (EffectRefused, one send); `claim_consumes_once_and_only_for_its_own_job` |
| 5. Scheduler | `while_stage_a_is_off_the_scheduler_is_a_recorded_no_op`; `queues_one_standing_activation_and_asks_the_issuer`; `never_queues_more_than_one_a_pass`; `policy_decision_pace_and_fee_ceilings_bind_the_scheduler`; `the_real_pace_ceiling_holds_the_scheduler` (real `decide` and `_counts`); issuer `job_refusal`, `answer` and `tick` tests |
| 6. Retention | `every_new_audit_action_has_a_retention_decision` |

## Mutants (each applied alone, suites re-run, file restored)

Killed: 17 of 18 mutants. The survivor is argued equivalent below.

| Mutant | Killed by |
|---|---|
| grant check: handler does not consume | lineage, failed read-back, retry, crash tests |
| grant check: handler pre-checks skip `use_refusal` | shipped-switch test |
| grant check: "no grant for this job" not a refusal | no-grant test |
| phase gate: SHADOW not refused | shadow test |
| read-back: `live = True` | failed-read-back test |
| `record_activated` never called | lineage / `plan()` test |
| pace: more than one per pass, or while outstanding | queues-one, more-than-one tests |
| pace: scheduler ignores `decide` | ceilings, real-pace tests |
| pace: `decide`'s per-day ceiling removed | real-pace test (and `test_ws4_stage_a_activation`) |
| scheduler: off is not a no-op | off test |
| scheduler: lineage not required | ceilings test |
| issuer: job not validated before `issue` | `answer_refuses_a_job_that_is_not_live…` (added after this mutant first survived) |
| reconcile: never reconciles | retry, crash tests |
| reconcile: reconciles a listing not active | crash-before-applied test |
| claim: lets another job's retry through | claim test |
| one authority per job removed | one-authority test |
| `at_effect=False` also skips the renewal check | client-intent test |
| **Survived (equivalent):** `record_live` called when not live | `record_activated` itself refuses any read-back that is not this listing `active` (pinned by `record_activated_refuses…`), so the outer `and live` is defence in depth. |

## Suites

`JOBS=4 SUITE_REGISTRY=0 run_tests.sh` with the venv from `requirements.lock` and
`requirements-test.lock`, no PYTHONPATH: run `20261119T060444Z-9117`, exit 0, **TOTAL PASSING: 340; suites failing: 0**; environment failures 0.
The run was on checkpoint 8a1a8eb0 plus one uncommitted path, the issuer-answer test, which this
commit adds. Requested suites plus the four that cover the touched plumbing (c12 wiring, both
retention guards, readback_observe). Per-suite counts as each suite prints them:

| Suite | Passing |
|---|---|
| test_ws4_8_stage_a_wiring (new) | 23 |
| test_ws4_stage_a_activation | 14 |
| test_ws4_stage_a_withdrawal | 11 |
| test_ws4_7_issuer | 34 |
| test_activation_authority | 2 |
| test_etsy_exercise | 43 |
| test_w4_listready | 41 |
| test_w4_close5_rows3 | 3 |
| test_w4_resume_runner | 40 |
| test_w3_tmp_hygiene | 16 |
| test_vacuity | 8 |
| test_route_auth_default_deny | 8 |
| test_cert_spend_hosts | 7 |
| test_etsy_oauth_callback | 41 |
| test_w4_c12_wiring | 4 |
| test_w4_fmbatch1_retention_guard | 5 |
| test_w4_retfix_retention_keys | 4 |
| test_etsy_readback_observe | 37 |

These printed counts add up to 341. The runner's own total (340) is the authoritative figure;
one suite's printed lines are probably counted twice by my log scrape. The full suite was not
run (as instructed).

## Notes for the integrator (not fixed here, outside this scope)

- **should_auto_renew.** Fixed in fix round 1 (see above).
- **Mode T roles.** The issuer now reads `jobs` (`job_refusal`) and writes `policy.activation_grant_held`, `standing_grants` and `standing_activation_slots`. The worker consumes activation grants. The Mode T role grants for these belong to opus2's L-A work.
- **Shadow evidence.** Shadow decisions are de-duplicated per (approval, release, decision), so `MIN_A_CANDIDATES` counts releases rather than scheduler ticks. Whether `a_shadow` should also count distinct releases is a Stage A design point, left unchanged here.
- **Retries.** A standing job uses the queue's default `max_attempts`. A retry that outlives the grant's 15-minute signed life is refused by `use_refusal`, and the next pass schedules afresh.
