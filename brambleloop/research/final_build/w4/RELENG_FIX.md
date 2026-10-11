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

## 5. Offsite backup design (for owner approval; nothing is enabled)

### The problem

The only database backup is `/backup/*.dump` on `db-backup-volume`. That volume is a Railway
volume in the same project and region (us-west2) as the database, so it does not survive losing
the provider or the project. The 1 GB volume (923 MB usable) holds about 3 dumps of 282 MiB,
and the database is growing.

### What already exists

- **`core/offsite.py`** (Build 2 #51/#52, "offsite archive"). It is already written and tested,
  and it runs daily as the job `ops.offsite_archive`. Production `/api/offsite` reports
  `configured:false`, reason "no BRAMBLELOOP_ARCHIVE_URL in this environment".
  - It talks the S3 API, so Backblaze B2, Cloudflare R2, Wasabi and AWS all work by setting a
    URL.
  - It encrypts before upload: AES-256-CBC plus HMAC, with a stretched passphrase held in
    `BRAMBLELOOP_ARCHIVE_ENCRYPTION_KEY`.
  - It reads every upload back and restores it into a scratch database.
  - It keeps 14 archives.
  - It archives the app's logical continuity export, not a `pg_dump`. So it covers the rows,
    not a byte-identical database with sequences, indexes and constraints.
  - Its key is a Railway variable, so anyone who compromises the host can also decrypt.
- **The db-backup job** (proven 2026-10-11T13:00Z): a `pg_dump` plus a real restore check.
  It runs only when someone deploys it, and it has no rotation, no manifest and no offsite step.
- **GitHub is not a fit and is rejected.** `StateFarm91/Project-Money` is a **public**
  repository. Dumps hold customer and OAuth-adjacent rows. GitHub blocks files over 100 MB
  (dumps are 282 MB), and a GitHub token with write access would have to be stored in Railway.
  A separate private repo or Releases would mean storing backups somewhere GitHub's terms
  don't intend, plus a powerful token. Not recommended.

### Options

Monthly cost assumes 30 daily dumps of about 0.3 GB, so about 9 GB stored. Prices are list
prices as I know them; confirm at sign-up. Exchange rate: US$1 = CA$1.38.

| Option | Stored ~9 GB | If the DB doubles (~18 GB) | Restore egress | Notes |
|---|---|---|---|---|
| **A. Backblaze B2** (recommended) | **CA$0.00** (first 10 GB free) | ~CA$0.07 (US$0.006/GB over 10 GB) | free up to 3× stored | S3 API, already supported by `core/offsite.py`'s region logic. Supports lifecycle rules and **app keys with no delete permission** |
| B. Cloudflare R2 | **CA$0.00** (10 GB free) | ~CA$0.17 (US$0.015/GB) | free | S3 API (region `auto`, supported). Lifecycle rules available |
| C. AWS S3 Standard | ~CA$0.29 (US$0.023/GB) | ~CA$0.57 | US$0.09/GB | Most familiar to operators, but costs the most and charges for restore egress |
| D. Owner downloads by hand | CA$0 | CA$0 | n/a | Not repeatable, and Railway has no volume download button. Rejected as the primary copy |

Added Railway cost for any of A to C:
- The daily db-backup run: about 2 min/day of one vCPU and 1 GB, so about CA$0.06/month.
- The existing 1 GB volume: about CA$0.21/month, already being paid.

**Ceiling check.** The last recorded infrastructure spend is about CA$7 of the CA$20/month
ceiling. Option A adds about CA$0.06 to CA$0.13 a month, leaving more than CA$12 of headroom.
The approved object storage for PDFs and images (owner action 1, max CA$5) can share the same
B2 account and still stays under the ceiling. The budget is enforced in code by the existing
infrastructure ceiling, and nothing here can start spending: OFFSITE_UPLOAD defaults to 0.

### Recommended design (Option A)

- **Two copies, one bucket, separate prefixes.**
  - `pgdump/daily/<dump>.gpg`, written by the db-backup job through the new
    `ops/db_backup/housekeep.sh`.
  - `continuity/YYYY/MM/DD/<digest>.blarc`, written by the existing `core/offsite.py` once its
    variables are set.
- **Encryption at rest uses a key only the owner holds.**
  - pg_dump copies are encrypted with gpg to the owner's **public** key
    (`OFFSITE_GPG_PUBKEY_B64`). The private key never reaches Railway or the repo. A full host
    compromise yields ciphertext the host cannot decrypt.
  - The script refuses if a private key is pasted into that variable.
  - B2 also encrypts on its side (SSE-B2) as a second layer.
  - The continuity archive keeps its existing passphrase scheme. That key sits in a Railway
    variable, which is a weaker arrangement and is noted here as such.
- **The bucket key cannot destroy history.** The B2 application key is limited to this bucket,
  with `listFiles, readFiles, writeFiles` and **no `deleteFiles`**. Retention is set by a bucket
  lifecycle rule (hide after 35 days, delete 1 day later), not by the script. The script never
  issues a delete to the bucket, and a test enforces that. A stolen key can add objects but
  cannot wipe backups.
- **Retention.**
  - Locally: the newest `BACKUP_KEEP=2` verified dumps.
  - Offsite: 35 daily copies of the dump. The continuity archive keeps its 14 (`RETAIN_OFFSITE`).
  - Optional: a second lifecycle prefix `pgdump/monthly/` with 365 days. Not implemented; would
    cost about CA$0.05 more.
- **Restore verification, in three layers.**
  1. Every run, before anything is recorded, the existing script does a full `pg_restore` into
     a scratch cluster and compares row counts (`BK restore_ok`, `BK tables 51 …`).
  2. Every upload is read back from the bucket and its ciphertext sha256 compared with what was
     sent (`BK OFFSITE OK … ciphertext_sha256`). That is recorded in `MANIFEST.jsonl`.
  3. A monthly owner drill, about 15 min. It is the only step that exercises the private key,
     by design.
     - Download the newest `.gpg` and run `gpg --decrypt > x.dump`.
     - Check `sha256sum x.dump` equals the manifest's `verified` sha256.
     - Check `pg_restore --list x.dump | grep -vc '^;'` is about the manifest's `toc_entries`.
     - Optionally `pg_restore` into a local Postgres.
     - Record the result in BUILD_STATE.
- **Schedule:** daily, by a cron schedule on the db-backup service (restart policy stays
  NEVER, and the job exits). This replaces "redeploy by hand".

### Implemented in the repo (not deployed, not enabled)

`ops/db_backup/housekeep.sh` wraps the proven script and acts only on its `BK RESULT OK <path>`
line. It does not change the proven script.

| Command | What it does |
|---|---|
| `run` | Runs `precheck`, then the backup script, then `record`, `rotate`, `check` and `ship` |
| `precheck` | Frees the oldest verified dumps until there is room for 120% of the newest dump. **Never** deletes the newest; fails instead |
| `record` | Appends to `MANIFEST.jsonl` (file, bytes, sha256, UTC time, toc entries) and rewrites `SHA256SUMS`, so `sha256sum -c` works on the volume |
| `rotate` | Keeps the newest `BACKUP_KEEP` verified dumps. Removes failed or partial dumps only when a newer verified dump exists |
| `check` | Re-hashes the kept dumps. Exit 4 if one is missing or changed |
| `ship` | **No-op unless `OFFSITE_UPLOAD=1`.** gpg-encrypts to the owner's public key, uploads with SigV4 (credentials go to curl on stdin, never in argv), reads back and compares sha256, and logs to the manifest. Exit 3 means the local backup is fine but the offsite copy failed |

- Test: `brambleloop/tests/test_db_backup_housekeep.py`, 9 checks, all passing. It covers:
  - the manifest and `sha256sum -c`
  - rotation
  - a failed run never deleting the last good dump
  - tamper detection
  - the precheck never deleting the newest dump
  - offsite off by default with no curl call
  - enabled-but-unconfigured failing loudly
  - a full encrypt/upload/read-back round trip against a loopback S3 stand-in, decrypted with
    the owner's private key
  - a pasted private key being refused
  - no bucket delete anywhere in the script
- **Image dependency, checked against the official `postgres` Dockerfile (trixie):**
  - `gnupg` stays in the image.
  - **`curl` is not present**, and `wget` and `ca-certificates` are purged after the build.
  - So enabling `ship` needs a prelude:
    `apt-get update -qq && apt-get install -y -qq --no-install-recommends curl ca-certificates`.
    This adds about 20 s per run. The alternative is a small custom image, which is not
    proposed. `ship` reports `OFFSITE FAIL curl is not installed` rather than failing silently.
- Not verified here: a SigV4 upload to a **real** B2 bucket, since only a loopback stand-in was
  used. The first enabled run is that test, and its log must show `BK OFFSITE OK`.

### Owner action required (batched)

| # | Action | Why | Max cost | Minutes | If you wait |
|---|---|---|---|---|---|
| O1 | Approve Option A (Backblaze B2) | Picks the destination | CA$0.15/mo at the 20 GB worst case (CA$0 today) | 1 | Backups stay on the same provider; losing the project loses every backup |
| O2 | Create a B2 account. Create a **private** bucket `brambleloop-backups` with SSE-B2 and a lifecycle rule (hide after 35 days, delete 1 day later). Create an app key limited to that bucket with `listFiles, readFiles, writeFiles` and no `deleteFiles` | Destination and credential | CA$0 | 10 | Same as O1 |
| O3 | On your own computer: `gpg --quick-gen-key "Brambleloop Backups <you>" default default never`. Store the private key and its revocation certificate offline (password manager plus USB). Give the integrator `gpg --armor --export <id> \| base64 -w0`, the **public** key only | Encryption only you can open | CA$0 | 10 | Same as O1 |
| O4 | Paste the B2 endpoint, bucket, key ID and secret into Railway db-backup variables yourself (`OFFSITE_ENDPOINT/BUCKET/REGION/KEY_ID/SECRET`). Never into chat or the repo | A secret should be entered only by its owner | CA$0 | 5 | Same as O1 |

After O1 to O4, the integrator (Railway writes, with the owner's go-ahead) does the following:
1. Set `HOUSEKEEP_B64` (base64 of `housekeep.sh` at a reviewed commit), `BACKUP_KEEP=2`,
   `OFFSITE_GPG_PUBKEY_B64` and `OFFSITE_UPLOAD=1`.
2. Change the start command to: install curl, decode `SCRIPT_B64` to `/tmp/b.sh` and
   `HOUSEKEEP_B64` to `/tmp/h.sh`, then `bash /tmp/h.sh run /tmp/b.sh /backup`.
3. Add a daily cron schedule to db-backup.
4. Deploy once and require `BK RESULT OK` and `BK OFFSITE OK` in the log.
5. Optionally set `BRAMBLELOOP_ARCHIVE_*` on brambleloop-os so the continuity archive goes to
   the same bucket.
