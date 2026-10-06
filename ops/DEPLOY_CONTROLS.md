# Deploy controls: what the repository enforces, and what only the owner can (A3-05)

Written 2026-10-06 (UTC). Independent audit finding A3-05: the deploy guard was advisory. A
push with `--no-verify`, a push from a clone that never ran `ops/install_hooks.sh`, or a
redeploy started on the hosting platform reached production without any release proof.

## Layers the repository now enforces

1. **Runtime boot guard** (`brambleloop/src/brambleloop/ops/release_record.py`, called at
   import of `app/main.py` and at the start of `worker_entry` / `scheduler_entry`). On the host
   (any `RAILWAY_*` marker) a build whose deployable tree (`src/**` without bytecode +
   `requirements.lock`) is not named by a committed, release-eligible record in
   `brambleloop/release/` runs as **SHADOW** and opens a **P1** incident
   (`release.unproven_build`, halts publication). With `BRAMBLELOOP_BOOT_GUARD=refuse` it exits
   instead. Nothing in the environment turns it off on the host. It runs whichever path
   produced the build: hook, `--no-verify`, fresh clone, or platform redeploy.
   Production at fcb982d predates it and is unaffected until a new deploy.
2. **Tracked evidence only** (`ops/deploy_guard.py`). `check` no longer believes the
   gitignored `brambleloop/artifacts/suite_runs/`. It reads, from git at the candidate,
   `brambleloop/release/RELEASE_<sha>.json` plus tracked copies of the run record and log
   (sha256-pinned), bound to the deployable tree digest. `ops/deploy_guard.py record --sha <sha>`
   writes them after a clean full run; the operator commits them on top of `<sha>`.
3. **Sanctioned rollback** (`ops/ROLLBACK_RUNBOOK.md`, `ops/deploy.sh --rollback-to`).
4. **SQLite refused by default** on the host or outside shadow (`core/db.py`, A3-08).

Release flow: `REQUIRE_CLEAN=1 ./run_tests.sh` on commit X -> `python3 ops/deploy_guard.py
record --sha X` -> commit `brambleloop/release/` (commit Y, same deployable tree) ->
`ops/deploy.sh` (checks Y) -> host builds Y -> boot guard verifies Y's tree against the record.

Residual: the deployed SHA the guard compares against may still be supplied in
`BRAMBLELOOP_DEPLOYED_SHA` (the hook and `ops/deploy.sh` fill it from production). A wrong
value can only defeat the *descent* rule, not the release proof, and the boot guard still
applies. Server-side protection (below) is the real control.

## OWNER ACTION REQUIRED (batched)

### 1. Protect the production branch on GitHub
- **Exact action:** github.com/StateFarm91/Project-Money -> Settings -> Branches -> Add branch
  protection rule (or ruleset) for `claude/repository-setup-nc9x6o`: require a pull request
  before merging with at least 1 approving review; block force pushes; block deletion; do not
  allow bypass. Optionally require status checks once a CI check exists.
- **Why:** git hooks are per clone and skippable (`--no-verify`); only GitHub can refuse a push
  to the branch the host deploys from. After this, deploys happen by merging a reviewed PR.
- **Maximum cost:** CA$0 on a public repository. If the repository is private on a GitHub
  Free personal account, protected branches need GitHub Pro: about US$4/month (~CA$5.50).
- **Minutes:** 5.
- **Consequence of waiting:** any push to the branch (from any clone or session) builds and
  deploys; the boot guard limits an unproven build to SHADOW plus a P1, but production still
  changes code and an incident page is the only signal.

### 2. Stop the host deploying every push
- **Exact action:** Railway -> project -> each service (web, worker, scheduler) -> Settings ->
  Source: either disable automatic deploys for the connected branch, or point the service at a
  branch only reachable through protected merges (the branch in action 1). Leave "redeploy"
  usage to the integrator and the rollback runbook.
- **Why:** the host builds on push and its own redeploy button bypasses every git-side check.
- **Maximum cost:** CA$0. **Minutes:** 5-10.
- **Consequence of waiting:** same as action 1; a platform-side redeploy of an unrecorded build
  is caught only at boot (SHADOW + P1).

### 3. Confirm Postgres is bound on every service before deploying this code
- **Exact action:** Railway -> each service -> Variables: confirm `DATABASE_URL` references the
  Postgres plugin (not blank) on web, worker and scheduler.
- **Why:** A3-08 makes the build refuse SQLite on the host; a service without `DATABASE_URL`
  will now fail to start instead of silently running on an ephemeral file.
- **Maximum cost:** CA$0. **Minutes:** 2.
- **Consequence of waiting:** if a service lacks the variable, the first deploy of this code
  crash-loops that service (fail-closed, by design) until it is bound.

### 4. (After the first recorded release is live) make the boot guard refuse rather than shadow
- **Exact action:** Railway -> each service -> Variables: `BRAMBLELOOP_BOOT_GUARD=refuse`.
- **Why:** a build that cannot prove itself then does not start at all, rather than running as
  SHADOW. Optional; SHADOW + P1 is the safe default.
- **Maximum cost:** CA$0. **Minutes:** 2.
- **Consequence of waiting:** none beyond the default (unproven builds run as SHADOW + P1).
