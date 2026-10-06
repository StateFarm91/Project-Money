# Lane J audit: AUTONOMY (SHA ddf9c6e, tag final-candidate-ddf9c6e)

Verdict: the protected-action boundary, lease fencing, department isolation and Claude-independence are
SOUND. The "useful work" measurement is NOT trustworthy as built, and no §95 test that needs a hosted
environment can be PASS yet. No LAUNCH-BLOCKING finding for shadow phase. 0 LB / 1 HIGH / 3 MEDIUM / 2 LOW.

All repros: `cd brambleloop && PYTHONPATH=src .venv/bin/python research/final_build/audit_ddf9c6e/<file>`.

## Findings

### H-1 (HIGH) "Useful" is vacuous: did_no_work only flags `ran:false` or `ran:true` + zero counters
- runtime/pipeline.py:2153-2166 (judge), autonomy/kpis.py:57, autonomy/orchestrator.py reconcile_missions, ops/slo.py departments().
- Any output without a `ran` key, or whose counters are not in WORK_COUNTERS, is "useful".
- Repro `J_repro_vacuous_outputs.py` (empty DB, real orchestrator + Worker): support.triage `{"cases":0,...}`,
  physical.upgrade_impact `{"upgrades":0,"measured":0}`, visual.identity_drift `{"batches":0,"measurable":false}`,
  ops.sentinel `{"checked":0,...}`, seasonal.sentinel, growth.distribution `{"products":0,...}`: all did_no_work=False.
- Real runner (J_autonomy_proof_25min.json): 20 missions generated, 20/20 "useful", 0 "noop". Consequence: the
  3-consecutive-noop suppression (orchestrator.py:150-165) can never fire; the `department_useful_work` SLO and
  soak criterion "independent departments did useful work" use the same judge.
- autonomy.department_review and morning_handoff hardcode `"generated": 1` (autonomy/handlers.py:108,187), so they
  are useful by construction. 9 of 20 generated missions in the real run were department_review.
- Fix: a handler-declared `measured_rows`/`work_done` count (UNKNOWN != work); treat all-zero numeric outputs and
  `measurable:false` as no-op; drop the hardcoded `generated:1`.

### M-1 (MEDIUM) KPI anti-gaming hole: self-review output is unique per mission, so it counts as distinct useful work
- autonomy/handlers.py:108 puts `snapshot: kpi:<dept>:<mission>` in outputs; autonomy/kpis.py:34 VOLATILE does not
  strip `snapshot`, so fingerprints differ every run.
- Repro `J_repro_kpi_gaming.py`: 10 reviews of Visual with zero activity -> `useful_completions_24h = 10` (OK, not VOID).
  By contrast 10 identical growth.distribution / scale.trajectory runs fingerprint to 1 (that part of F-918 is sound).
- Fix: exclude autonomy.department_review/morning_handoff from the department's own useful KPI, or strip `snapshot`.

### M-2 (MEDIUM) One failing cadence aborts the whole Scheduler.tick and leads to a self-exit restart loop
- runtime/worker.py:784-808 catches only DuplicateJob per cadence; app/runner.py:303-340 supervisor exits on a tick-less scheduler.
- Repro `J_repro_stale_exit.py`: one cadence raising ValueError -> 5 of 107 cadences enqueued, the rest starve every tick;
  supervisor `os._exit(1)` fires at minute 17 after boot. railway.json has ON_FAILURE max 10 retries, so a
  deterministic fault could leave the service down after 10 cycles (Railway counter semantics not verified, no Railway use).
- No false exit reproduced: threshold 900 s, two strikes, restart-safe state. Fix: try/except per cadence in tick(),
  heartbeat on partial success, incident row for the poisoned cadence.

### M-3 (MEDIUM) Soak criterion "no duplicated external effect" is blind to a SIGKILL duplicate
- ops/slo.py:1180 counts only `queue.stale_lease_refused|unfenced_write_refused` audit rows.
- Repro `J_repro_kill.py`: SIGKILL a worker mid-handler -> successor reclaims, job attempts=2, effect applied twice, queue.* audit rows = [] ->
  criterion would read PASS. Fix: also flag jobs with attempts>1 whose type is an external-effect type.

### L-1 (LOW) At-least-once execution; no effect-boundary lease check
- runtime/worker.py: the fence guards only the DB completion write. A stale-but-alive worker keeps executing its handler after
  reclaim (repro: stale scenario, 2 effects, completion correctly refused, audit queue.stale_lease_refused written).
  The only write-ahead guard is publish/draft_intent.py (at-most-one draft create). Currently latent: no messaging or ad
  integration exists, and activation/publish are shadow-refused. Fix: `ctx.assert_lease()` before any external effect.

### L-2 (LOW) Department block is a manual flag, not derived from real owner gates, and does not stop that department's cadences
- Repro `J_repro_block.py`: Support blocked -> 10/10 other departments GENERATED on 3 consecutive ticks (F-894 holds), but
  Scheduler still ran support.triage; block has no default expiry. `charters.gates` is used only for display (autonomy/status.py).

## Answers to the eight questions
1. Real runner, 11 min (J_autonomy_proof.json, 242 jobs) and 25 min (J_autonomy_proof_25min.json, 273 jobs, 0 worker restarts,
   $0 spend, closed network, no human enqueues). The first 14 min never reached an empty queue: 99 cadence jobs pending at boot kept 10/11
   departments BUSY and the orchestrator generated 1 mission. After the backlog drained (10:28), idle_wake fired: 10 + 8 missions,
   then SATURATED (11/11), and the queue sat empty for the last ~8 min. So: real but bursty, and "useful" is overstated (H-1, M-1).
2. Protected enqueue: SOUND. `J_repro_protected.py`: hostile provider output (job_type store.publish/ads.campaign/support.reply, NUL bytes,
   oversized keys) on all four next_work providers -> 0 protected jobs; adapters hardcode the job type (only learn accepts one, from a 3-item
   allowlist); `_enqueue_mission` re-checks PROTECTED + generatable + SAFE_GENERATED; charters are frozen. Protected work only becomes OwnerAction rows.
3. Kill/lease: DB fencing SOUND (stale completion refused and audited, successor's job intact, tokens per claim). Effects: L-1, M-3.
4. Blocked department: SOUND for generation (L-2 caveats).
5. Stale self-exit: no false exit found; M-2 loop risk.
6. KPI gaming: M-1 (identical outputs count once only when no per-run id leaks into outputs).
7. Claude/heartbeat/owner-PC dependence: none in runtime. test_cert_claude_independence 4/4 (662 s: real uvicorn start command,
   scrubbed env, SIGKILL + resume, split services). External uptime probe/watchdog is not deployed, so availability stays UNKNOWN (correct, GATED).

## §95 acceptance map (strict)
| # | Test | Status | Evidence |
|---|------|--------|----------|
| 1 | PC off + chats closed 24 h | GATED | no hosted 24 h soak exists; 11/25 min local runs + test_cert_claude_independence; soak_report correctly returns INCOMPLETE <24 h |
| 2 | Kill worker, no duplicate effects | PASS-locally (queue) / PARTIAL (effects) | fencing + test_v11_autonomy_recovery pass; effects at-least-once (L-1, M-3) |
| 3 | Phone browser tabs usable | PASS-locally (static) / GATED (real device) | test_v11_pwa_static 78/78; test_v11_pwa_browser not rerun |
| 4 | Unauthenticated high-impact approval refused+audited | PASS-locally | test_v11_cc_auth 16/16 |
| 5 | Revoke authority before execution | PASS-locally | test_v11_cc_actions 7/7 |
| 6 | Accounting source disconnected -> UNKNOWN | PASS-locally | test_v11_cc_views 13/13 |
| 7 | Duplicate fee/payment/refund | PASS-locally | test_v11_accounting_reconciliation 7/7 |
| 8 | Trace profit to sources | PASS-locally | test_v11_accounting_drill 5/5 |
| 9 | Growth spend vs Finance policy | PASS-locally | test_v11_ads_challenge 15/15 |
| 10 | Block one dept, others continue | PASS-locally | J_repro_block.py + test_v11_autonomy_overnight |
| 11 | Notification noise vs real incident | PASS-locally | test_v11_cc_views notification test |
| 12 | Ask why product blocked, source-linked | PASS-locally | test_v11_cc_views ask tests |

## Checked and SOUND
Protected-action boundary (above); lease_token fence on complete/fail/heartbeat; claim/reclaim conditional UPDATE; lane_hold; orchestrator
idempotency (existing SIGKILL test passes); per-department try/except isolation; autonomy suites (kpis, orchestrator, overnight, recovery,
timeline) and reliability suites all pass; stale-exit requires two strikes at 15 min.
Not tested: Postgres, real Railway, the two other lanes' code paths beyond the listed tests, ops.queue_check re-driving non-publish dead letters.
