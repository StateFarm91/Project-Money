# handoff — lane W4-CC (Owner Command Center online)

Branch `claude/w4-CC` (base fee1cfe). Latest pushed SHA: see `git log -1 origin/claude/w4-CC`.
Worktree `/home/user/Project-Money/.claude/worktrees/W4-CC`. TMPDIR `/home/user/bl-tmp-CC`.

## Done (PROVEN unless stated)
- `GET /api/cc/company` (app/command_center/company.py): company status, departments
  (active/sleeping/blocked/unhealthy/UNKNOWN from `autonomy.status.summary` + live `jobs`:
  current job, last useful result, next wake), agents (registry + jobs + worker.CADENCES; an
  agent with no recorded job is UNKNOWN, not sleeping), owner actions, approvals, store,
  store visibility, product pipeline, finance, autonomy, learn, Build 2 closure + maturity
  (background thread, 30-min TTL, UNKNOWN "computing" until ready), Final Master closure,
  visual, Laura (+ Talk link), blockers, completion summary. Every section an envelope with
  status/as_of/basis; UNKNOWN carries a reason. Evidence: tests/test_w4_cc_company.py 12/12;
  runtime proof research/final_build/w4/cc_runtime_proof.json (fresh shadow DB: Build 2
  218/58/37/7/0 OPEN closed_out, FM 73/66/300 of 439, all departments UNKNOWN because no job
  ever ran there).
- `GET /api/cc/completion` + committed `research/final_build/w4/COMPLETION_BOARD.json`
  (schema in the file's `schema` key; validated by `company.validate_board`).
- PWA: `company` and `completion` views (More menu + Home quick links), sw shell v5,
  phone-size Playwright check extended (tests/fixtures/cc_mock): 108/108.
- Deploy-readiness package: research/final_build/w4/CC_DEPLOY_PACKAGE.md.

## Tests run
test_w4_cc_company 12/12; test_v11_pwa_browser 108/108; test_route_auth_default_deny 7/7;
test_rc1_auth 11/11; others: see final report.

## WIRING REQUESTS
1. **Dockerfile (integrator):** add `COPY research/final_build/w4/COMPLETION_BOARD.json ./research/final_build/w4/COMPLETION_BOARD.json`
   after `COPY release ./release`. Without it the production Completion tab is UNKNOWN
   ("board not found"), honestly, but useless. (Alternative: set
   `BRAMBLELOOP_COMPLETION_BOARD` to a path that is in the image.)
2. **Integrator:** keep COMPLETION_BOARD.json current (bump `updated_at`; a RUNNING lane with
   `last_update_at` older than 3 h is shown STALE).

## Remaining / next deterministic action
- DONE: MEDIUM availability finding mitigated (main.closure_matrix_shared / maturity_report_shared).
- Owner actions (deploy approval, variables): CC_DEPLOY_PACKAGE §7.
