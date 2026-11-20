# FIX-SECURITY-B19: fixes for the Batch 19-B security review (eng/autocoder, eng/autopromote)

- Fixed: 2026-11-20 (UTC). Review being answered: `review-results/b19-b:VERDICT.md`.
- Both branches merged `origin/eng/colourwork` @ `9479c0e` (production `b098fcce` plus the
  COLOURWORK-B17 review request). Docs kept from both sides; `autonomy_map.json` regenerated
  with `python3 -m brambleloop.autonomy.map --write` (eng/autocoder: the conflict was taken
  from production, then regenerated; eng/autopromote: only the timestamp changed).
- Pushed with ordinary (non-force) pushes. No PR opened. No Railway variables or secrets read.

| Unit | Before | Fix commit | Branch head (includes this file) |
|---|---|---|---|
| A: eng/autocoder | `caa9a6f1` | `f5b3ecd02b1e427cd434ac112ca4c8481ec71f00` | see `git log origin/eng/autocoder` |
| B: eng/autopromote | `6c3cecd5` | `5b029eb3b9fc0ce9006e667f60745881a9cf6c98` | see `git log origin/eng/autopromote` |

## Test results (on the committed fix commits, clean tree)

| Branch @ fix commit | Command | Result |
|---|---|---|
| eng/autocoder @ `f5b3ecd0` | `PY=python3 JOBS=4 SUITE_REGISTRY=0 SUITES="test_eng_autocoder test_w4_readback_evidence test_swarm_runtime test_deploy_guard test_vacuity test_w4_resume_runner test_eng_improve" bash run_tests.sh` | **7/7 suites green, 147 passing, 0 failing** (128 s, exit 0, tree clean, run record passed) |
| eng/autopromote @ `5b029eb3` | `PY=python3 JOBS=4 SUITE_REGISTRY=0 SUITES="test_autopromote test_deploy_guard test_vacuity test_w4_resume_runner" bash run_tests.sh` | **4/4 suites green, 74 passing, 0 failing** (113 s, exit 0, tree clean, run record passed) |

`test_eng_autocoder` alone: 0 failed. `test_autopromote` alone: 19/19. An intermediate
autopromote run went red on `test_vacuity` (a possibly-empty loop in the new dispatch test). It
was fixed by adding non-emptiness assertions before the fix commit; the counts above are from the
committed tree.

actionlint 1.7.12 (`pip install actionlint-py`) is clean on `.github/workflows/autocoder-ci.yml`
(eng/autocoder) and on `certify-and-promote.yml` and `dispatch.yml` (eng/autopromote).
`test_workflow_lint` now runs actionlint instead of printing SKIP when it is installed.

## (A) eng/autocoder

**A1 (HIGH): model-written code never executes in the production worker.**
- New order of operations in `improve.autocoder.run`:
  1. deterministic rails: refspec allowlist, path denylist, test-weakening detector, secret
     scanner, spend/exec paths, source weakening (new), size;
  2. the independent reviewer returns SHIP for exactly this diff;
  3. only then is `auto/ecr-<id>` pushed. The commit carries an `Autocoder-Suites:` trailer.
- Removed: `run_suite`, `_clean_env`, the `runner` hook on `Workspace` and `run`, the
  `Limits.test_timeout_s` field, and the `subprocess`/`sys` imports. The `test` action is now
  answered ("test not run ... runs in CI") and never executed. `gate()` runs nothing. The
  Dockerfile's `git` addition is reverted, because the worker no longer runs
  `test_w4_resume_runner`.
- New `.github/workflows/autocoder-ci.yml`:
  - Triggers only on a push to `auto/**`. There is no `pull_request`, `pull_request_target` or
    `workflow_run` trigger.
  - The `test` job has `contents: read`, no secrets and `persist-credentials: false`. It runs the
    trailer's suites (each must match `^tests/test_[A-Za-z0-9_]+\.py$`) plus `test_vacuity` and
    `test_w4_resume_runner`.
  - A separate `report` job checks nothing out and runs no repository code. It holds only
    `statuses: write` and posts the commit status `brambleloop/autocoder-ci` on the pushed SHA.
- Production reads the result back: `ci_readback` runs at the start of every job run, before any
  spend. It moves a request to `code_certified` (and the ECR to REVIEWED) **only** on `success`
  posted by `github-actions[bot]` on the exact pushed SHA. `failure`/`error` refuses the request
  (`ci_failed`); no result within 24 h refuses it (`ci_no_result`). A status from any other
  account is ignored. `mark_certified` raises `NotCertified` without a green result. A push no
  longer advances the ECR lifecycle.
- Prompts bumped to `autocoder.step@2` and `autocoder.review@2`. The model names `targets`
  instead of running tests, and the reviewer is told the tests have not run yet.
- Regression guard (`test_d_the_job_never_spawns_or_imports_the_modified_code`):
  - Static: `autocoder.py` names no process, exec or import machinery.
  - Dynamic: a full run on a toy ECR with `subprocess.Popen`, `os.system`, `os.execv`,
    `__import__` and `importlib.import_module` trapped. The model asks to run tests, and the
    modified test would write a marker if executed. Only `git` plumbing is spawned, never in the
    workspace. A mutant that runs the suite inside `gate()` is **killed** (verified).
- Defence beyond code (the review's fix items 2 and 3): `OWNER_ACTIONS_AUTOCODER.md` now
  - makes the server-side ruleset (the production branch, `main` and `claude/w6-release-*`)
    **mandatory** before the switch is turned on;
  - advises minting the token from a machine-user account (or using a GitHub App) so the owner's
    own bypass does not cover it;
  - adds the "Commit statuses: read" token permission.

  The rails are documented as lint, not a security boundary. `PR_SET_DUMPABLE` is moot now,
  because no untrusted code runs in the worker.

**A2 (HIGH): extended path denylist.**
- Explicit additions:
  - child safety: `intel/childrens.py`, `creative/children.py`, `publish/pdf.py`,
    `publish/release_gates.py`, `seasonal/childrens_demand.py`;
  - auth, session, TOTP and OAuth: `core/opsauth.py`, `core/readbackauth.py`,
    `core/oauth_store.py`, `integrations/etsy_oauth.py`, `integrations/etsy_authorise.py`,
    `app/command_center/private_context.py`, `app/command_center/api.py`,
    `commerce/shop_security.py`;
  - spend ceilings and authority: `visual/spend_plan.py`, `visual/product_authority.py`,
    `visual/approval_record.py`, `intel/insights_budget.py`, `ops/standing_policy.py`,
    `build2/gate_clearance.py`;
  - the release card;
  - every `tests/_*.py` helper (by prefix);
  - `test_autopromote.py` and `test_workflow_lint.py`.
- Already covered and still covered: `gates/`, `gateway/` (the reservation), `finance/`,
  `authority/`, `approvals`, `app/security.py`, `command_center/auth.py`, `ops/` (`deploy_guard`
  and `deploy.sh`), the boot guard (`app/main.py`, `worker_entry`, `scheduler_entry`),
  `ops/release_record.py` and `.github/` (CI workflows).
- New by-name rule `SENSITIVE_NAME`. It protects any path whose directory or file stem contains
  child, minor, kid, auth, oauth, secret, credential, token, session, totp, mfa, password, login,
  security, spend, ceiling, budget, reserv, authority, approv, guard, gate, boot, release_,
  deploy, kill_switch, safety, permission, consent, casl or workflow.
- Tests:
  - `PROTECTED_SAMPLES` gains every path above, plus hypothetical `app/session_totp.py`,
    `new/kill_switch.py`, `ops/deploy_guard.py` and `app/boot_guard.py`.
  - `test_b_every_sensitive_module_in_the_tree_is_protected_by_name_or_list` walks all ~976
    source modules and fails on any editable match of the review's regex.
  - Mutant "name rule removed" is killed.

**A3 (MEDIUM): source deletions.** New `source_weakening_findings`, part of `check_changeset`.
In non-test source it refuses:
- a removed or rewritten `raise`, `assert`, `return False` or refuse/reject/forbid/deny/block line;
- any change to a module-level UPPER_CASE constant.

Lines that are only moved are allowed. Tested, and the mutant is killed.

**A4 (LOW): test-weakening gaps.**
- Test functions are keyed by qualified name (`Class.test_x`).
- A `return` reachable before the first assertion at any depth (`if True: return`) is refused.
- An existing assertion may not be rewritten (fingerprint per test), only added to.
- `tests/_*.py` helpers are protected by prefix.

Each case is in `WEAKENED` or the class case.

**A5 (LOW): per-ECR spend from the ledger.**
- The job records its id in `evidence.autocoder.jobs` before any spend.
- `ecr_ledger_spend` sums `CostEntry` by those job ids, and the budget uses the greater of that
  and the note.
- Test: a crashed run's ledger rows (no note) bind the per-request cap, and no model call is made.

## (B) eng/autopromote

**B1 (HIGH): the backup gate fails the job on REFUSE.**
- `defaults: run: shell: bash` makes every step run as `bash -eo pipefail`.
- The backup step also has `shell: bash` and `set -o pipefail`.
- After the `tee`, the step requires `json.load(backup.json)['ok'] is True`.
- `test_backup_gate_fails_the_step_when_the_backup_refuses` **executes** the shipped step script
  against a stand-in `autopromote.py`:
  - REFUSE (exit 1) fails the step;
  - `ok:true` with exit 0 passes;
  - `ok:false` with exit 0 fails the step;
  - the old form (`bash -e`, no pipefail) is shown to continue, so the test can tell them apart.

**B7 (MEDIUM, merge regression).** `tests/test_autopromote.py` is declared in
`brambleloop/scripts/suite_final_segment.txt`, and `test_w4_resume_runner` is green.

**B2.** Certify concurrency is `brambleloop-certify` (repository-wide, no cancel). Promote runs
`git merge-base --is-ancestor <deployed> <release>` and refuses otherwise.

**B3.** The job is split three ways:
- `certify` (the suite plus `deploy_guard record`) has `contents: read` only and uploads the
  record as an artifact;
- `record` is a fresh checkout that runs no tests and is the only job that can write. It verifies
  that `RELEASE_<sha>.json` names the SHA and that only `brambleloop/release/` and
  `research/release_evidence/` changed, then commits and pushes with `core.hooksPath=/dev/null`;
- `promote` needs `record`.

**B4.** The `push` trigger is removed. The workflow runs only by `workflow_dispatch`, and the
first step refuses unless `github.ref_name` is the default branch, so the reviewed copy of the
file always runs. `OWNER_ACTIONS_AUTOPROMOTE.md`:
- makes the `production` environment's required reviewers and a ruleset on `claude/w6-release-*`
  **REQUIRED**;
- updates the release flow to "push the branch, then dispatch".

**B5.** `dispatch.yml` checks out the pinned commit `07a41bf15621df3cbd3dd9624feedc934bd0d305`
(the current `claude/w4-INTEG8-next` head; its `ops/dispatch_board.py` only calls the GitHub
issues API), not the mutable branch. The default branch does not carry the board's files, so
"check out the default branch" was not possible without moving them. `${{ github.repository }}`
moved into `env:`.

**B6.** `workflow_failures()` pins:
- the trigger set (exactly `workflow_dispatch`, no `pull_request*` or `workflow_run`);
- the default-branch check;
- bash/pipefail on every step;
- the backup verdict check;
- no `|| true` in the backup or deploy steps;
- no `${{ github.event.* }}` or `${{ inputs.* }}` inside `run:`;
- the concurrency group, the ancestry check and the job split with its permissions;
- hooks off on the record push.

Ten mutants are killed, including both survivors from the review (`|| true` on the backup and
an added `pull_request_target`).

## Not done or still open
- **Neither workflow has ever run on GitHub.** `autocoder-ci.yml` will first run on the first
  `auto/**` push after it reaches the base the autocoder branches from (production).
  certify-and-promote's `workflow_dispatch` appears only once the file is on the default branch.
- The `auto/*` restriction is still enforced server-side only after the owner creates the
  ruleset (mandatory owner action, `OWNER_ACTIONS_AUTOCODER.md` item 1).
- B3 limits what a suite can do to the push, but a hostile suite in the `certify` job can still
  shape its own release record. The `record` job checks that the record names the SHA, but it
  cannot re-derive the suite's result. The guard and the required reviewer remain the later gates.
