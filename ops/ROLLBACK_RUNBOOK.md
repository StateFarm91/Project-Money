# Production code rollback runbook (A3-06)

Status: written 2026-10-06 (UTC). The repository side is implemented and tested
(`brambleloop/tests/test_rc1_own_release.py`); it has **not** been exercised against the real
host, because nothing in this build is authorised to deploy.

## When to use it

Production is running a release that misbehaves and the owner (or the integrator, with the
owner's stated reason) decides to return to a commit that has run in production before. The
default target is **fcb982d** (`fcb982d57e291c88d9f78eaa091e90904b6c2cc9`), the production
commit recorded in `brambleloop/research/final_build/CANDIDATE_3be3096.json`.

A rollback is not an accident the guard should block, and it is not an exemption from the
guard either. It is a separate door with its own checks:

- the target must be listed in `brambleloop/release/DEPLOYED_HISTORY.json` **as committed in
  the deployed commit** (tracked, reviewed; never edited to make a rollback pass);
- the rollback commit's tree must be *exactly* the target's tree;
- it is written on top of the deployed commit (a fast-forward, so the forward release stays in
  history and the next forward deploy is an ordinary descendant);
- the owner's reason is stated, at least 10 characters, and carried in the commit as
  `Rollback-To:` / `Rollback-Reason:` trailers, so the pre-push hook and anyone reading the
  branch history see the same justification.

## Steps

1. Read the deployed commit: `python3 ops/deployed_sha.py` (production `/api/status`
   `build.commit`). Call it `<deployed>`.
2. Rehearse (no push, no deploy):

   ```sh
   DRY_RUN=1 ops/deploy.sh --rollback-to fcb982d --reason "<owner's reason>" --deployed <deployed>
   ```

   Expect `ALLOW <commit>`; the JSON on stderr shows `"mode": "rollback"` and the reason.
   A REFUSE names why (target not in history, tree mismatch, no reason, deployed unknown).
3. Execute (integrator only, with the owner's go-ahead):

   ```sh
   ops/deploy.sh --rollback-to fcb982d --reason "<owner's reason>" --deployed <deployed>
   ```

   This pushes the rollback commit to `claude/repository-setup-nc9x6o`; the host builds it.
   The installed pre-push hook re-checks it from the commit's trailers.
4. Verify: production `/api/status` `build.commit` is the rollback commit, `/health` is 200,
   `/api/verify` is green for the phase, and the queue is draining.
5. Append nothing to `DEPLOYED_HISTORY.json` for the rollback commit itself (its tree *is*
   fcb982d's); record the incident and the reason in `brambleloop/BUILD_STATE.md`.

If the host must be rolled back without git (for example the platform's own "redeploy previous
deployment" button), that path does not pass through this guard. It is an owner action, and
the boot guard does not protect fcb982d (which predates it): after such a redeploy, run step 4.

## Database: no down-migration, and none is needed

`core/migrate.py` is additive only. Per
`brambleloop/research/final_build/POSTGRES_MIGRATION_EVIDENCE.md` (Run 1 and Run 2, local
Postgres 16, 2026-10-05): the Final Build head adds 21 schema changes (new tables, added
columns, indexes) to the fcb982d schema, drops/renames/retypes nothing, and preserved every row
of every one of the 51 production tables.

fcb982d's ORM does not map the added columns or tables, so it ignores them: rollback is
"redeploy fcb982d code", with no schema change. Two consequences to know about:

- rows fcb982d writes during the rollback window leave the added columns at their database
  defaults (or NULL where a column has no server default). The ledger's `basis`,
  `fees_basis` and `reconciliation_state` then read as `unknown` / `unreconciled` once the
  forward release returns -- i.e. as unmeasured, never silently as measured
  (`finance/books.py` tolerates `ledger.basis` NULL). NULL tolerance of every other added
  column has not been verified; treat rows written in the window as unknown provenance.
- new tables (for example `draft_creation_intents`) are not read or written by fcb982d. Draft
  creations fcb982d performs during the window have no durable intent row; reconcile them
  against the shop before rolling forward.

The migration evidence is synthetic (one row per table) and was not run against a snapshot of
the real production database. A pre-deploy rehearsal against such a snapshot remains an owner
gate.

## A push that did not deploy (RELENG, 2026-10-11)

`ops/deploy.sh` now waits after pushing (`ops/verify_deploy.py`, default 900 s) for production
`/health` `build.commit` to equal the pushed sha. Exit 3 (`NO DEPLOY`) means production still
runs the old commit; exit 4 means `/health` never answered with a commit.

On exit 3 or 4 the branch already holds a guard-approved commit that production is not running.
Do not push again and do not rewind the branch. Instead:

1. Read the host's deployment list for the service (read-only). If a deployment for the sha
   exists and FAILED or CRASHED, it is a build or boot failure. Read its logs and treat it as
   an incident.
2. If no deployment for the sha exists at all, the host did not act on the push (as with
   0417f35 at 13:34:43Z on 2026-10-11). The integrator, with the owner's go-ahead, uses the
   host's "Deploy Latest Commit" for brambleloop-os, then runs
   `python3 ops/verify_deploy.py <sha>` again. Record the miss in BUILD_STATE with the sha
   and UTC time, because the host's support will ask for both.

## Pre-release database backup (RELENG, 2026-10-11)

Run this before every deploy that changes `core/migrate.py`, and in any case at most 24 h
before a release. The `db-backup` service (image `postgres:18`, restart policy NEVER, volume
`db-backup-volume` 1000 MB mounted at `/backup`) runs one dump and then exits each time it is
deployed. Never delete the service or its volume.

1. Integrator or owner (this is a host write): redeploy the `db-backup` service once.
2. Read its deploy log (read-only). It must end with `BK RESULT OK /backup/brambleloop_prod_<ts>.dump`
   and must contain `BK restore_ok`, `BK file ... bytes N sha256 H`, `BK toc_entries`, and
   `BK tables 51 restored_rows ...`. A `BK drift` line for live tables (`audit_log`, `jobs`) is
   normal. Any other drift, or no `RESULT OK`, means there is no backup, so do not deploy.
3. Record the file name, bytes, sha256 and UTC time in BUILD_STATE next to the release sha.
   The dump time must come before the push.
4. Capacity check: the log's `BK volume` line gives free space. Each dump is currently about
   282 MiB (2026-10-11), so a dump needs free space greater than 1.2 times the last dump. If
   there is less, that is an owner action: prune old dumps or grow the volume.
