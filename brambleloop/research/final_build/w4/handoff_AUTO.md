# handoff W4-AUTO (Rule #1 autonomy)

Branch `claude/w4-AUTO` (from claude/visual-investigation fee1cfe; merged origin/claude/w4-INTEG
7631026 for MJS + STORE handlers). Phase stays shadow. Latest pushed SHA: see `git log -1`.

## Done
- `autonomy.status.agents(db)` per-agent visibility provider (envelope status/as_of/basis/items/sources).
- `autonomy.rule1.measure(db)` per-department useful/no-op/distinct + idle-with-eligible-work test;
  wired into `autonomy.proof` (`rule1`, `agents` keys; `--keep-db PATH`).
- Baseline proof evidence `evidence/AUTO_before_proof.json` (16 min, fee1cfe, no rule1 key) and
  `evidence/AUTO_before2_proof.json` (10 min, post-INTEG merge, with rule1).
- Judge/discovery fixes (runtime/pipeline.py):
  - cir.draft success paths now set the declared work key `drafted: True` (Product & Design was
    judged 0% useful although it drafted every CIR).
  - gate.certify WORK_KEYS += `reasons` (a deterministic refusal is QA output).
  - launch.plan declared: `launch_on`, `held`, `withheld`.
- Wiring requests applied: (a) mjs.scan WORK_KEYS += `findings.changed` (only changed findings
  count; `{"error":..}` does not); (b) CADENCES `store_live_drift` daily after
  `etsy_shop_snapshot`, orchestrator allowed `store.live_drift`, WORK_KEYS
  (`findings`,`proposals`,`incidents_opened`); (c) visual_rnd_job.summarise counts
  `launch_imagery` refreshed listings (`imagery_refreshed`, `imagery_errors`) in work_done.
- autonomy_map.json regenerated (cadences 112, handlers 130).
- Tests: tests/test_w4_auto_status.py (8 OK).

## In progress / next deterministic actions
1. After-proof: `python -m brambleloop.autonomy.proof --seconds 600 --out $TMPDIR/after.json --keep-db $TMPDIR/after.sqlite`
   -> copy to evidence/AUTO_after_proof.json.
2. Write research/final_build/w4/RULE1_OUTPUT_AUDIT.md/.json (prod read-only GETs captured in
   scratch: /api/jobs, /api/audit, /api/queue/cadences, /api/catalogue, /api/status).

## WIRING REQUEST (lane CC, app/command_center/providers.py)
- Add `"agents": ("brambleloop.autonomy.status", "agents")` to the provider table so the owner
  dashboard renders per-agent status (doing now, current job, last useful result, produced /
  rejected, blockers, next work/wake, useful & no-op rates, cost, state, as_of).

## Dashboard QUEUE PENDING 0 / RUNNING 0 (finding)
Production runs fcb982d (2026-09-25, 678 commits behind this branch): 46 cadences, no autonomy
orchestrator (work discovery) package. Its queue drains in seconds after each cadence tick and
nothing generates work between ticks; most cadence runs are no-ops because of external blockers
(Anthropic credit balance exhausted -> vision/model/tournament/cycle-proof refused; no image
generation; no browser URL; no archive URL) and shadow. The current build has 112 cadences plus
the orchestrator; a fresh 10-min shadow run ends with ~68 pending (boot burst, bounded aging).
Closing the production gap is a deploy (integrator/owner) plus OWNER ACTION #19/#20 (credits).
