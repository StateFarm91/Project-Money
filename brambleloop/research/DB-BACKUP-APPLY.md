# DB-BACKUP-APPLY: Railway configuration for the `db-backup` service

ENG-DB-BACKUP, 2026-11-28 (UTC). Branch `eng/db-backup`. **Nothing here has been applied.**
No Railway write was made, and no variable value was read, in preparing this. The owner
applies the settings below (or the integrator does, with the owner's go-ahead).

## Why

- The `db-backup` volume (`db-backup-volume`, 5 GB, mounted at `/backup`) is 99.7% full.
- The service runs only when someone redeploys it. It has no rotation, so every dump stays.
- Each dump also carried `continuity_archives`: `core/continuity.py` `retain()` keeps 3 gzip
  whole-database exports there, about 100 MB+ each, so every backup held copies of earlier
  exports of the same data.

## What changes

| Piece | Where in the repo | Railway |
|---|---|---|
| Dump + restore check | `ops/db_backup/backup.sh` | variable `SCRIPT_B64` (replaced) |
| Precheck, manifest, rotation, offsite (off) | `ops/db_backup/housekeep.sh` | variable `HOUSEKEEP_B64` (new) |
| Payload builder | `ops/db_backup/encode.sh` | not deployed |
| Tests | `brambleloop/tests/test_db_backup_housekeep.py` | not deployed |

`backup.sh` is the proven 2026-10-11 script with one change: `pg_dump` gets
`--exclude-table-data=continuity_archives`.

- The table's schema is still dumped, so a restored database has the table, but it is empty.
- The row-count comparison expects `restored=0` for that table.
- The run fails (`BK RESULT FAIL`) in three cases, any of which would mean the dump is
  carrying the archives again:
  - archive rows are restored;
  - the table is missing from the restore;
  - the archive's table of contents has a `TABLE DATA` entry for it.
- The restore target is a scratch cluster on port 5499 in `/tmp`. It is removed on exit.

## 1. Variables (names only; never paste values into chat or the repo)

| Name | Action | Where the value comes from |
|---|---|---|
| `SRC_URL` | **Leave unchanged** (already set) | The production Postgres connection URL. It should be a Railway reference variable to the Postgres service's `DATABASE_URL`, not a pasted string. |
| `SCRIPT_B64` | **Replace** | Output of `ops/db_backup/encode.sh --print SCRIPT_B64` at the reviewed commit of `eng/db-backup` |
| `HOUSEKEEP_B64` | **Add** | Output of `ops/db_backup/encode.sh --print HOUSEKEEP_B64` at the same commit |
| `SCRIPT_B64_LEGACY` | **Add (optional, recommended)** | Copy the current value of `SCRIPT_B64` here **before** replacing it. It is the rollback copy. Delete it once a week of runs has passed |

These values contain code only, never a secret. Each is a single line of base64, about 8 KB
and 15 KB.

Do **not** set any of these:
- `BACKUP_KEEP`: it is set in the start command.
- `OFFSITE_UPLOAD` or `OFFSITE_*`: offsite stays off until the owner approves the separate
  RELENG_FIX section 5 design.
- `BACKUP_HEADROOM_PCT`: see the fallback in section 5.

To build the payloads, run this on a checkout of `eng/db-backup`:

```bash
ops/db_backup/encode.sh            # writes both payload files to a temp dir and prints a summary
```

It prints the commit, plus the bytes and sha256 of each script. At this commit they must be:

| Variable | Source | sha256 of the decoded script |
|---|---|---|
| `SCRIPT_B64` | `ops/db_backup/backup.sh` (6032 bytes) | `f882011432cbaae12293cd4fbc51e59dadcf4dbc70cb344331e4574458743e80` |
| `HOUSEKEEP_B64` | `ops/db_backup/housekeep.sh` (15432 bytes) | `9bd7a36231241fe291e323ab55567f0c6fd9af256e5888ddb0cc5fa23e76bc2c` |

If `encode.sh` prints a WARNING about uncommitted changes, stop. The payload would not match
a reviewed commit.

There are two ways to set them:
- **Dashboard.** db-backup, then Variables. Paste each file's contents. Before overwriting
  `SCRIPT_B64`, copy its old value into `SCRIPT_B64_LEGACY`.
- **CLI** (from the repo root, linked to project `brambleloop`, environment `production`):

  ```bash
  railway variables --service db-backup --skip-deploys \
    --set "SCRIPT_B64=$(ops/db_backup/encode.sh --print SCRIPT_B64)" \
    --set "HOUSEKEEP_B64=$(ops/db_backup/encode.sh --print HOUSEKEEP_B64)"
  ```

## 2. Start command

Go to db-backup, then Settings, then Deploy, then Custom Start Command. Replace the current
`bash -c 'echo "$SCRIPT_B64" | base64 -d > /tmp/b.sh && bash /tmp/b.sh'` with:

```bash
bash -c 'set -o pipefail; printf %s "$SCRIPT_B64" | base64 -d > /tmp/b.sh && printf %s "$HOUSEKEEP_B64" | base64 -d > /tmp/h.sh && sha256sum /tmp/b.sh /tmp/h.sh | sed "s/^/BK payload /" && BACKUP_KEEP=2 bash /tmp/h.sh run /tmp/b.sh /backup'
```

The command does five things, in order:
1. It decodes both scripts.
2. It logs their sha256 values as `BK payload` lines.
3. It runs housekeep's `precheck`.
4. It runs the backup (dump, restore check and row counts).
5. It runs `record`, then `rotate` with `BACKUP_KEEP=2`, then `check`, then `ship` (a no-op
   while offsite is off).

The exit code is housekeep's:

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | backup failed, or no room |
| 3 | local OK but offsite failed |
| 4 | a kept dump is missing or changed |

So a failed run shows as a failed deployment or cron run in Railway. Keep the restart policy
at **NEVER**.

**Compressed variant.** `ops/db_backup/encode.sh --print-gz HOUSEKEEP_B64` gives
`gzip -9n | base64 -w0` (deterministic, about a third of the size). If `HOUSEKEEP_B64` is set
from that, decode it with `printf %s "$HOUSEKEEP_B64" | base64 -d | gunzip > /tmp/h.sh` in
place of `... | base64 -d > /tmp/h.sh`. The `BK payload` sha256 is of the decoded script
either way, so it must still equal the table in section 1.

This exact command was run locally against the payloads `encode.sh` produced, with the dump
tools stubbed, and logged the sequence in section 4. Its `run` path against a real local
PostgreSQL 16 cluster is covered by the test suite.

## 3. Cron schedule

Go to db-backup, then Settings, then Cron Schedule, and enter `17 9 * * *`.

That is daily at 09:17 UTC (02:17 in Vancouver, 04:17 in Toronto during standard time), when
the shop is quiet. Railway cron times are UTC. A run takes a few minutes, and Railway skips a
start while the previous run is still active. Cost: about 2 to 5 min/day of one small
container, roughly CA$0.06 to CA$0.15/month. There is no new volume or spend.

## 4. Verify (read the deployment log)

A good run logs these lines, in this order (values vary):

```
BK payload f882011432cbaae12293cd4fbc51e59dadcf4dbc70cb344331e4574458743e80  /tmp/b.sh
BK payload 9bd7a36231241fe291e323ab55567f0c6fd9af256e5888ddb0cc5fa23e76bc2c  /tmp/h.sh
BK adopt ... / BK rotate removed|deleted ... (first run only; see section 5)
BK precheck ok free <bytes> need <bytes>      (or: BK precheck no previous dump; proceeding)
BK start <ts>
BK server_version <N>
BK pg_dump_version pg_dump (PostgreSQL) 18.x
BK excluded_table_data continuity_archives
BK file /backup/brambleloop_prod_<ts>.dump bytes <n> sha256 <h>
BK toc_entries <k>
BK restore_ok
BK excluded continuity_archives restored=0 source_now=<3 or so> (data excluded by design; expect restored=0)
BK tables <T> restored_rows <R> tables_changed_since_snapshot <D>
BK volume <size> total <free> free
BK ls ...
BK RESULT OK /backup/brambleloop_prod_<ts>.dump
BK manifest recorded brambleloop_prod_<ts>.dump sha256 <h>
BK rotate kept 2 verified (keep 2)
BK check ok brambleloop_prod_<...>.dump       (one per kept dump)
BK offsite disabled (OFFSITE_UPLOAD is not 1; no destination approved)
```

The run is good when **all** of the following hold:
- the two `BK payload` hashes equal the table in section 1;
- `BK RESULT OK` is present;
- `BK excluded continuity_archives restored=0` is present;
- `BK check ok` appears for each kept dump;
- there is no `BK RESULT FAIL` and no `BK check MISSING|CHANGED`.

`BK drift` lines are normal for live tables (`audit_log`, `jobs`, `cost_entries`), with
`source_now` at least `restored`. Expect `<n>` in `BK file` to be well below the last old dump,
by roughly the size of the 3 archives.

On the volume:
- `/backup/MANIFEST.jsonl` holds every verified, deleted and offsite event.
- `/backup/SHA256SUMS` lists the kept dumps, so `sha256sum -c SHA256SUMS` works there.

`ops/autopromote.py` still finds the `BK RESULT OK` line as before. Housekeep's own failure
line now reads `BK RESULT FAIL housekeep: ...`, so it can never be mistaken for OK.

## 5. First run: cleanup of the old dumps, step by step

**Incident, 2026-11-28 (first production run, housekeep 1371167887bb).** The volume was full.
- Every manifest append failed with `No space left on device`.
- The precheck then read the empty manifest as "no previous dump" and deleted nothing.
- `pg_dump` hit ENOSPC, and the run ended `BK RESULT FAIL`.
- It probably left a second partial dump, `20261128T060409Z`, next to `20261128T051026Z`.

Housekeep 9bd7a3623124 fixes this. Its precheck now works in three steps, and a test
reproduces the incident on a real 1 MiB tmpfs (six legacy dumps, both partials, a cut-short
manifest, a full disk) and shows it recovering. The owner approved this cleanup: keep the
newest 2 verified dumps, and delete older dumps and partial ones.

1. **Classify, writing nothing.** Until the manifest holds an `adopt-done` event, dumps not
   in it are legacy.
   - Newest first, `pg_restore --file=/dev/null` reads each one back in full, every data
     block, so a truncated dump is refused.
     - A dump that reads back is verified: `BK adopt verified legacy <file> (<bytes> bytes,
       reads back in full)`.
     - Any other is refused: `BK adopt refused <file> (does not read back in full)`.
   - Once 2 dumps are known good, the older ones are not read at all:
     `BK adopt skipped <file> (older than the newest 2 verified)`.
   - A truncated line left in the manifest by a failed append is ignored.
2. **Delete, still writing nothing.** This step runs only while at least one verified dump
   remains.
   - Every refused, skipped or partial dump is removed: `BK rotate removed unverified <file>`.
   - Verified dumps beyond the newest 2 are deleted: `BK rotate deleted <file> (older than the
     newest 2 verified)`.
   - Then, if the volume still lacks 1.2 times the newest dump, housekeep deletes the oldest
     verified dumps beyond the newest one: `BK rotate deleted <file> (making room for the next
     dump)`. The newest one is never deleted.
   - With no verified dump at all, nothing is deleted: `BK precheck no verified dump on the
     volume; <n> unverified left untouched`.
3. **Write the manifest.**
   - It records the adopted dumps (`"adopted":true`, oldest first), then the `adopt-done`
     event, then `SHA256SUMS`: `BK adopt recorded 2 legacy dump(s)`, then
     `BK precheck ok free <bytes> need <bytes>`.
   - **A failed write is fatal.** The log shows `BK manifest write FAILED ...`, then
     `BK precheck FAIL the manifest could not be written; no dump attempted`, then
     `BK RESULT FAIL precheck`. No dump is attempted, and the run never falls back to "no
     previous dump".

What the next steps leave on the volume:
- **Backup.** The new dump is written without the archive data and restore-checked:
  `BK RESULT OK`.
- **Rotate (`BACKUP_KEEP=2`).** It keeps the new dump and the newest legacy dump,
  `20261120T121953Z` (about 661 MB). The other legacy dump that was kept for the precheck
  (`20261119T165654Z`) is deleted: `BK rotate kept 2 verified (keep 2)`.
- Expected first-run deletions, given the production log:
  - partials `20261128T060409Z` (if present) and `20261128T051026Z`;
  - legacy `20261112T013853Z`, `20261117T032249Z`, `20261119T132003Z`, `20261119T155212Z`
    (these are skipped, not read);
  - `20261119T165654Z`, after the new dump is verified.
- **Second run** (the next day at 09:17 UTC, or a manual redeploy). There are no `BK adopt`
  lines. `20261120T121953Z`, the last dump that carries the archives, is rotated out. From
  then on the volume holds exactly the newest 2 verified dumps, both without archive data,
  plus `MANIFEST.jsonl` and `SHA256SUMS`.

Files on the volume that are not `brambleloop_prod_*.dump`, if any, are never touched. The
`BK ls` lines list them.

**Fallback if the first run logs `BK precheck FAIL free <x> < need <y> with only the newest
verified dump left`.**
- Nothing was deleted beyond what is logged, and the newest legacy dump is intact.
- This happens only if the newest old dump is larger than about 45% of the volume (2.2 GB).
- The new dump is much smaller, so for **one** run add the variable `BACKUP_HEADROOM_PCT=50`
  and redeploy.
- After `BK RESULT OK`, delete that variable.
- If it still fails, the volume must grow. That is an owner action (cost shown in Railway
  before you confirm).

## 6. Order of operations (owner)

| # | Action | Minutes | Cost |
|---|---|---|---|
| 1 | On a checkout of `eng/db-backup`, run `ops/db_backup/encode.sh`. Confirm the two sha256 values match section 1 and that there is no WARNING | 2 | CA$0 |
| 2 | db-backup, Variables: copy the current `SCRIPT_B64` value into a new `SCRIPT_B64_LEGACY`. Set `SCRIPT_B64` and add `HOUSEKEEP_B64` (section 1). Leave `SRC_URL` alone | 3 | CA$0 |
| 3 | db-backup, Settings: replace the start command (section 2). Leave the restart policy at NEVER | 1 | CA$0 |
| 4 | Deploy the staged changes. This runs the first job now | 1 | about CA$0.01 |
| 5 | Read that deployment's log against sections 4 and 5. Record the dump name, bytes, sha256 and UTC time in BUILD_STATE | 3 | CA$0 |
| 6 | db-backup, Settings: Cron Schedule `17 9 * * *`, then deploy. If Railway runs the job once more on this deploy, that is harmless: rotation still keeps 2 | 1 | about CA$0.10/month |
| 7 | The next day, read the 09:17 UTC run's log. Expect no `BK adopt` lines, `BK rotate kept 2 verified` and both kept dumps from the new job | 2 | CA$0 |

**If you wait:** the volume stays 99.7% full, and the next manual backup will most likely fail
for lack of space. That leaves no fresh pre-release backup, so releases that change
`core/migrate.py` are blocked by `ops/ROLLBACK_RUNBOOK.md`.

**Rollback of this change:**
1. Set the start command back to the old one quoted in section 2.
2. Copy `SCRIPT_B64_LEGACY` back into `SCRIPT_B64`.
3. Remove the cron schedule.

The dumps and `MANIFEST.jsonl` on the volume are unaffected by the rollback.
