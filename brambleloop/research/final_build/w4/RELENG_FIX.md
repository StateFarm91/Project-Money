# RELENG: a push that did not deploy, post-push verification, backup status, patch fb2a90a1

Lane RELENG, 2026-10-11 (UTC). Base `0417f35`, branch `claude/w4-RELENG`. I only read from
Railway and GitHub. I made no deploys, no redeploys, no variable, service or volume changes,
and accepted nothing.

## 1. Why the 0417f35 push did not deploy

### Established facts

| Fact | Source |
|---|---|
| Push `fcb982d -> 0417f35` (fast-forward, 992 commits, 16 days after the previous push) by `StateFarm91` at **2026-10-11T13:34:43Z** | GitHub `repos/.../activity?ref=refs/heads/claude/repository-setup-nc9x6o` |
| The same actor pushed to the same branch 29 times between 2026-09-24 and 2026-09-25. Every one of those pushes produced a Railway (`railway-app[bot]`) GitHub deployment within about 4 s | Same activity list, compared with `GET /repos/.../deployments` |
| No Railway deployment exists for 0417f35 until **69b50565 at 13:58:09Z**, which was triggered manually. GitHub's deployment record for it is from 13:58:12Z | Railway `list-deployments`, GitHub deployments |
| **Neither** service sourced from this repo and branch got a deployment from the push: `brambleloop-os` and the second service `Project-Money` (4dff24df, no root directory). On 09-25 both deployed on every push | Railway `list-deployments` |
| No SKIPPED deployments exist, so watch paths did not filter the push | `list-deployments status=SKIPPED` returned empty |
| `checkSuites: false`, so "Wait for CI" was not holding the deployment | `describe-service` |
| The service source is correct: repo `StateFarm91/Project-Money`, branch `claude/repository-setup-nc9x6o`, root `brambleloop` | `describe-service` |
| The Railway GitHub App still has write access to the repo: at 13:58 it created a deployment and a commit status on 0417f35 | GitHub deployments and `commits/0417f35/status` |
| A separate redeploy, **a7d81580 at 13:32:27Z** (commit fcb982d), ran 2 minutes before the push. It has **no** GitHub deployment record, unlike every push-triggered deployment, so it was a redeploy from the dashboard or API, not a push | Railway compared with GitHub deployments |

### Conclusion

The push reached GitHub, but Railway never turned it into a deployment for **any** service on
that repo and branch. That makes the cause repo-level, at the webhook or ingestion stage. It is
not a service setting: watch paths, Wait for CI, the branch and the root directory are all ruled
out above. App access is also ruled out, because the app wrote to the repo 24 minutes later.

I **cannot** see the exact cause read-only from here:
- Railway receives pushes through its GitHub App, and only the app owner (Railway) can see the
  app's webhook delivery log.
- `repos/.../hooks` is blocked by this session's proxy (403), and `repos/.../installation`
  needs an app JWT (401).
- Railway's own agent confirmed it could not name a trigger for a7d81580 and found no record
  of the push.

Two coincidences may be contributing factors, but neither is proven:
- An in-flight redeploy (a7d81580, 13:32:27 to about 13:33:43) overlapped the push window.
- This was an unusually large push (992 commits) after a 16-day gap.

### Owner action required

1. **Check the Railway GitHub App for pending permissions.** github.com → Settings →
   Applications → Installed GitHub Apps → Railway → Configure.
   - Confirm that `StateFarm91/Project-Money` is in "Repository access".
   - Accept any "permission update requested" banner.
   - Why: Railway's docs list a pending permission update as a cause of autodeploy silently
     not firing.
   - Cost: $0. Time: about 2 minutes.
   - If you wait: the next push to production may also not deploy. The new `deploy.sh` check
     will now catch that.
2. **If nothing is pending, open a Railway support ticket.** Give them:
   - project `0d61d9ec-76ca-42e3-aa69-918728845b29`
   - service `brambleloop-os` (`c14774b3-0df2-409e-9721-fd7045099c53`), environment production
   - repo `StateFarm91/Project-Money`, branch `claude/repository-setup-nc9x6o`
   - sha `0417f3516f30bb7c52926187fc475a0f46536e86`, pushed at 2026-10-11T13:34:43Z, with no
     deployment created for either linked service.

   Ask them to check the webhook delivery. Cost: $0. Time: about 5 minutes.
3. Optional cleanup, owner decision: the `Project-Money` service (4dff24df) builds the repo root.
   It FAILED on every push on 09-25 and serves nothing. Disconnecting or removing it stops it
   from making noise. It is not the cause of this incident.

## 2. `ops/deploy.sh` now checks that production is running the pushed commit

- New `ops/verify_deploy.py <sha>` polls production `/health` until `build.commit` equals the
  pushed sha, and only counts it when `build.known` is true.
  - Defaults: 900 s timeout, polled every 15 s. Override with `DEPLOY_VERIFY_TIMEOUT` and
    `DEPLOY_VERIFY_INTERVAL`.
  - Exit codes: `0` DEPLOYED, `3` NO DEPLOY (production still reports another commit, which is
    the 2026-10-11 case), `4` UNVERIFIED (`/health` never gave a commit).
  - `/health` errors part-way through a deploy are tolerated, and polling continues.
- `ops/deploy.sh` resolves the candidate to a full sha, pushes it, then runs the verifier and
  passes its exit code through. `VERIFY_DEPLOY=0` skips the check and says
  "production NOT checked".
  - The branch is never rewound.
  - What to do after exit 3 or 4 is in `ops/ROLLBACK_RUNBOOK.md`, section
    "A push that did not deploy".
- Test: `brambleloop/tests/test_deploy_verify.py`, 9 checks. The end-to-end checks run the real
  `deploy.sh` against a scratch repo, a local bare origin and a loopback `/health` server. One
  shows "production never moves" giving exit 3, and one shows "production reaches the sha"
  giving exit 0. Both pass.
- The existing suites `test_deploy_path` and `test_rc1_own_release` still pass. I did not run
  the full suite, per the lane rules.
- Live read-only check against the real host:
  - `verify_deploy.py 0417f35… --timeout 0` gives DEPLOYED.
  - `verify_deploy.py fcb982d… --timeout 0` gives exit 3, NO DEPLOY.

## 3. Backup status, and a repeatable procedure

There is a verified backup from 2026-10-11T13:00:44Z. This is from `db-backup` deployment
52d12793 (read-only from its logs):

- Location: `/backup/brambleloop_prod_20261011T130044Z.dump`
- Size: 295,502,844 bytes
- sha256: `413959335ff9709040dae77d101254ff52410473b6b979015cb69a301cda9172`
- Contents: 527 table-of-contents entries. A restore succeeded (`restore_ok`), with 51 tables
  and 40,579 rows restored.
- Drift is only in the live tables `audit_log` (+16) and `jobs` (+9) between the snapshot and
  the check.
- The dump came before the 0417f35 deploy (13:58Z), so it is that release's pre-release backup.

About the service and its volume:
- `db-backup` runs image `postgres:18` with restart policy NEVER. Its start script comes from
  the `SCRIPT_B64` variable. I did not read the value, because the same listing would expose
  `SRC_URL` credentials.
- The volume `db-backup-volume` is 1000 MB, mounted at `/backup`. After this dump it had
  923 MB total and 625 MB free.

Limits:
- The dump is on a Railway volume in the same project and region (us-west2) as the database,
  so it is **not offsite**.
- With dumps of about 282 MiB, the volume holds roughly two more before it fills.
- I did not verify whether the script prunes old dumps.

The repeatable procedure is in `ops/ROLLBACK_RUNBOOK.md`, section "Pre-release database
backup". In short:
1. The integrator redeploys `db-backup`. This is a Railway write.
2. Read the log and require `BK RESULT OK`, `restore_ok`, `tables 51`, and drift only in live
   tables.
3. Record the file name, sha256 and UTC time in BUILD_STATE against the release sha.
4. Check free space is more than 1.2 times the last dump, or treat it as an owner action to
   prune or grow the volume.

## 4. Empty staged patch fb2a90a1

Railway's agent (read-only query) reports:
- fb2a90a1 was staged at **2026-10-11T13:57:43Z**. That is 26 s before the manual deployment
  69b50565 (13:58:09Z), and its change list is empty.
- `get-staged-changes` for production returns `staged: null` with no resources.

The most likely explanation is that the Railway agent opened a working patch while preparing
the manual deploy of 0417f35. It then deployed directly, through "deploy latest commit", which
does not go through a patch, and left the empty patch behind. I cannot see who created it.

It changes nothing: accepting it would apply zero changes, and leaving it has no effect. Do not
accept it as part of any other change. If the owner wants a tidy dashboard, discarding it in
Railway's staged-changes panel is safe. That is optional, costs $0 and takes 1 minute.
