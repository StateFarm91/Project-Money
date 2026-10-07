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
- Deploy-readiness package: research/final_build/w4/CC_DEPLOY_PACKAGE.md (updated for wiring).
- Merged origin/claude/w4-INTEG (MJS + STORE). COMPLETION_BOARD.json conflict resolved to the
  integrator's version; `company.normalize_board` reads its `wave4.completion_board.v1` schema
  (lowercase status, responsible/started/last_update, rows_closed id list; an empty list on a
  non-DONE lane = UNKNOWN, never 0) plus the owner-dashboard baseline as a dated snapshot.
- Wiring (a) W4-MJS: operator-only `GET /api/mjs/findings` (main.py, OPERATOR_GET_ROUTES);
  `company.competitor_intel` section (provenance + confidence grade) on Company and Store.
- Wiring (b) W4-STORE: `POST /api/store/live_observation` (security.OWNER_SESSION_PAGES ->
  owner session + CSRF + nonce; audited row `store.live_observation`, actor owner:cc:<sid>;
  no Etsy write); Store tab `live_drift` (repo_proposals = ADOPT_LIVE_INTO_REPO only, owner
  instructions separate, writes_performed 0) + `store_readiness` (counts + non-PROVEN items,
  10-min memo) + record-observation form in the PWA (sw shell v6).
- Wiring (c) W4-VISUAL: `company.visual_stages` reads VISUAL_STATUS.json
  (`BRAMBLELOOP_VISUAL_STATUS` overrides); stage display "STATUS (basis)", D = PARTIAL
  (measured) with the stale dashboard value as `superseded_display`; absent file = UNKNOWN.

- Wiring W4-B2 (integrator 2026-10-07): merged origin/claude/visual-investigation (e87534b).
  `/api/build2` adds `headline` = `closure.dashboard(db, m=closure_matrix_shared())`, ledger
  path, and labels `coverage` as "registry claim". Dashboard `/` Build 2 card headline =
  PROVEN / OWNER-GATED / DATA-GATED / EXTERNAL-GATED / NOT-APPLICABLE / OPEN-DEFECT /
  executable remaining (OPEN only); registry counts shown as "registry claim: ..." (test_cert_dashboard
  label updated accordingly, same equality). CC Build 2 card uses the same headline
  (company._compute_build2 -> `headline`).
- Integrator board free-text statuses ("running (resumed...)", "complete; merged ...",
  "stopped") normalised by leading word; unreadable -> UNKNOWN with `status_text` verbatim.

- Resume 2026-10-07: WIP checkpoint 96e9442 reviewed and kept; visual-investigation merged
  (fbad855). Wiring W4-OWNER: Approvals `decision_batches` (OWNER_ACTIONS.json, live fallback,
  non-costed = UNKNOWN). Wiring W4L-2: `company.learn_outcomes` (pre-sale N / 9, post-launch-only
  cells DATA-GATED, CA$5K UNMEASURED) + dashboard Improvement rows. F-914: `/api/cc/money` and
  `/money/drill` accept `period`/`window` -> `tabs.money_window` -> accounting
  `summary(window=)`; bad period 400 BAD_PERIOD. Tests: test_w4_cc_company 21/21
  (test_owner_decision_batches_in_approvals, test_learn_outcomes_presale_post_launch_and_ca5k_unmeasured,
  test_money_period_reaches_accounting_window). CC_DEPLOY_PACKAGE §7 now includes GATESI owner
  actions (credits, Backblaze env vars, policy snapshots).
- Note: F-914 asked for "7d"; the accountant's grammar has no 7d (30d/mtd/ytd/all/YYYY-MM), so
  7d is refused 400 rather than silently answered with 30d. Adding 7d is a finance-lane change.

## Tests run
test_w4_cc_company 12/12; test_v11_pwa_browser 108/108; test_route_auth_default_deny 7/7;
test_rc1_auth 11/11; others: see final report.

## WIRING REQUESTS
1. **Dockerfile (integrator):** add `COPY research/final_build/w4/COMPLETION_BOARD.json ./research/final_build/w4/COMPLETION_BOARD.json`
   after `COPY release ./release`. Without it the production Completion tab is UNKNOWN
   ("board not found"), honestly, but useless. (Alternative: set
   `BRAMBLELOOP_COMPLETION_BOARD` to a path that is in the image.)
3. **Dockerfile (integrator):** also `COPY research/final_build/w4/VISUAL_STATUS.json` (after
   W4-VISUAL merges) so the Company "Visual pipeline stages" card is not UNKNOWN in production.
2. **Integrator:** keep COMPLETION_BOARD.json current (bump `updated_at`; a RUNNING lane with
   `last_update_at` older than 3 h is shown STALE).

## Remaining / next deterministic action
- Merge origin/claude/visual-investigation again once the integrator has merged W4-GATESI; rerun test_w4_cc_company.
- DONE: MEDIUM availability finding mitigated (main.closure_matrix_shared / maturity_report_shared).
- Owner actions (deploy approval, variables): CC_DEPLOY_PACKAGE §7.
