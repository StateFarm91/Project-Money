# Review request: ENG-AUTOPROMOTE

Branch `eng/autopromote` (no PR, by instruction). Base: production `5496bc4a`. Implementation
commit: `9a77515` (see the latest commit on the branch for this file).

## What it is
The release loop now runs on GitHub Actions with zero Claude usage. The guard is untouched:
`ops/deploy_guard.py` is not modified and has no override.

- `.github/workflows/certify-and-promote.yml`
  - Triggers: `workflow_dispatch` (`sha`, `branch`) and a push to `claude/w6-release-*`.
  - **certify** (timeout 350 min, overridable with `vars.CERTIFY_TIMEOUT_MIN` and
    `vars.CERTIFY_RUNNER` for a self-hosted runner). It checks out the exact SHA, confirms
    HEAD == SHA, a clean tree, and that SHA is the release-branch head. It uses Python 3.11 (as
    the Dockerfile and run records do), installs from `requirements.lock` +
    `requirements-test.lock` with `--require-hashes`, then runs one plain
    `REQUIRE_CLEAN=1 bash run_tests.sh` with CHECKPOINT/RESUME/SHARD/SUITES unset. Next comes
    `deploy_guard.py record`, then a commit of `brambleloop/release/` and
    `research/release_evidence/` (the same paths as the fa139a7 / 577ae44 release commits) and a
    fast-forward push to the release branch. The suite runs with no push credential on disk; the
    token is used only in the push step.
  - **promote** (concurrency group `brambleloop-promote`, `cancel-in-progress: false`,
    environment `production`). It reads the production SHA with `ops/deployed_sha.py`. If
    production reports a SHA missing from DEPLOYED_HISTORY, it appends it as observed, so the
    rollback rehearsal can pass. Then: `DRY_RUN=1 ops/deploy.sh`, the backup gate,
    `ops/install_hooks.sh`, `ops/deploy.sh --deployed <prod>`, and finally the deploy is
    recorded in DEPLOYED_HISTORY on the release branch (exit 0/5/6, only when production
    reports the SHA).
  - Readback: if the `BRAMBLELOOP_READBACK_TOKEN` secret is absent, `READBACK=0` is set, with a
    `::warning::` and the step summary `READBACK: SKIPPED (WARN)`. It is never reported as a PASS.
  - Permissions: `contents: write` only.
- `ops/autopromote.py`: the backup gate (`backup`), `history-append`, and `release-subject`.
  - Backup rule: no `RAILWAY_TOKEN` means REFUSE. Freshness cannot be read without the token
    either, which is stated in code and docs.
  - With the token: redeploy `db-backup` through the Railway GraphQL API (project token
    header), then wait for `BK RESULT OK` in the new deployment's logs. A FAIL line, or the
    deployment ending FAILED/CRASHED, means REFUSE. If there is no verdict (API error or
    timeout), it falls back to the newest `BK RESULT OK` within `BACKUP_MAX_AGE_HOURS`
    (default 24, the runbook's limit); otherwise REFUSE.
- `brambleloop/tests/test_autopromote.py`: 15 tests. They cover every backup branch, history
  idempotency and byte-exact format, the subject from the real Batch 11 record, guard
  invariants in the workflow text, and actionlint (skipped if not installed).
- `OWNER_ACTIONS_AUTOPROMOTE.md`: the secrets, the bypass for the Actions push, the optional
  reviewer gate, and cost and runtime.

## Verified
- `actionlint` 1.7.12 with shellcheck: clean.
- `test_autopromote.py`: 15/15. `test_deploy_guard.py`: 0 FAIL.
  `test_compiler`/`test_reverse`/`test_twin`: exit 0.
- The action pins were checked with `git ls-remote`: checkout v4.2.2 = 11bd7190, setup-python
  v5.3.0 = 0b93645e.
- The Railway ids (project brambleloop, env production, service db-backup) were read with the
  Railway list-services call. No variables or secrets were read.

## NOT verified (honest status)
- **The workflow has never run.** No Actions run exists yet. The first push to a
  `claude/w6-release-*` branch that contains it is the first test.
- **The Railway GraphQL calls** (`serviceInstanceRedeploy`, `deployments`, `deploymentLogs`)
  are untested against the live API, because there is no token in this session. They are
  covered only by fakes.
- **Runtime on hosted runners is unmeasured.** The repository is public (4 vCPU runner). The
  VM took 2.1-2.9 h, with one 4.3 h outlier, against a 350 min cap. If a hosted run comes close
  to the cap, use a self-hosted runner (owner doc).
- **Font package version.** The runner gets Ubuntu `fonts-dejavu-core`, unpinned, while the
  Dockerfile pins Debian trixie 2.37-8. Any render test that is sensitive to the font build
  would show up on the first run.
- **Full-suite record on this branch:** none. The change adds no deployable code (`src/`
  untouched), but `test_autopromote.py` joins the full suite.

## Review asks
1. Is the auto-append of the *observed* production SHA to DEPLOYED_HISTORY acceptable?
   The file's rule is "append after every verified deploy", and production's own
   `/api/status` is the evidence.
2. Trust model of the `push` trigger (see the file header and owner action 3).
