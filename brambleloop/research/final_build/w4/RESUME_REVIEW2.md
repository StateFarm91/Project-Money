# W4-RESUMEREVIEW2: fresh independent review of W4-RESUMEFIX (F1–F8)

- Subject: `claude/w4-RESUMEFIX` at `e634e6fc`, compared with `origin/claude/w4-INTEG8-next`. The
  merge base is `b0133916`. Files in scope: `run_tests.sh`, `scripts/suite_checkpoint.py`,
  `scripts/suite_final_segment.txt`, `src/brambleloop/ops/release_record.py`,
  `ops/deploy_guard.py`, `tests/test_w4_resume_runner.py` and the adapted probe.
- Prior review: `RESUME_REVIEW.md` (on `origin/claude/w4-RESUMEREVIEW`). Its verdict was NOT SAFE.
- Owner decision D-W4-OWNER-RESUME-POLICY: a resumed, checkpointed or sharded run never certifies,
  and there is no bypass. A plain uninterrupted full run certifies exactly as before.
- Reviewed 2026-10-31 (UTC). I judged the code, not `RESUMEFIX.md`. Every run used `nice -n 19`,
  one heavy process at a time, synthetic suites in throwaway git repos, and the branch's real
  `run_tests.sh` and checkpoint tool. The 2.7 h full suite was not run.
- My harnesses are in `research/final_build/w4/resume_review2/`, with their raw output.

## Verdict A, Batch 4 safety: **SHIP**

I found no gating hole and no regression. No checkpointed, sharded or resumed run became
release-eligible through partial forgery or a kill at any step boundary. None passed
`record_release`, `release_record.check_record` or the deploy check (`_record_problems`, which
`check` uses). The only way through was to remove every piece of evidence: the provenance keys,
the log lines, the checkpoint directory and the run id. At that point the record is a hand-forged
*plain* run record. Run records are unauthenticated, so that was already possible before this
branch, and this branch does not change it.

The plain uninterrupted full run is byte-identical to the base runner after normalisation, and
it still passes every gate. Before Batch 4, merge in `INTEG8-next` (see A-5).

## Verdict B, resume trustworthiness: **NOT SAFE** (to adopt resume for certification)

F4–F8 are largely sound, and I reproduced all 26 of the original probes as HELD. However,
**F2 and F3 can be bypassed without the run secret**. The HMAC chain has no externally pinned
head, so a truncated chain is still a valid chain. Cutting off a recorded failure turns a failed
run green on resume (B-1, reproduced). That is the C2 retry-until-green finding again, under a
MAC. The fix is small (see B-1). After it, plus B-2, the runner could be re-reviewed for ADOPT
WITH FIXES. None of this affects Verdict A, because resumed runs never certify regardless.

---

## 1. Release gating: evidence

Harness: `resume_review2/attack.py`, output `attack_output.txt`. Each generated record and log
was evaluated by four gates:

- `record_release`: the composition `record_release` performs before writing anything, namely
  `latest_suite(eligible_only)`, then `_log_confirms`, then `resume_provenance(rec, record_dir)`.
- `boot_guard`: `release_record.check_record`, run against the tracked copies (`summary_log` of
  the portable log, as `record_release` writes them), with the checkpoint root present.
- `boot_in_container`: the same check with no checkpoint root, as in the image.
- `deploy_check`: `deploy_guard._record_problems`, which `check` uses through `release_proof`.

There were three run modes, each of a 101-suite full-scope tree:

- `CHECKPOINT=1`, completed.
- `SHARD=0/1`, completed.
- `CHECKPOINT=1` killed with SIGKILL, then resumed with `RESUME`.

Each mode was then attacked as follows:

| Variant | All 3 modes |
|---|---|
| as written (`release_eligible: false`, provenance keys present) | refused everywhere |
| `release_eligible` and `status` forged true/passed | refused everywhere |
| forged bit, all `RESUME_PROVENANCE_KEYS` and `release_eligible_reason` deleted | refused everywhere (log lines) |
| ... and the checkpoint directory deleted | refused everywhere (log lines) |
| ... and the run id renamed (files, `run_id`, `job_id`, `RUN ID:` line) | refused everywhere (log lines) |
| forged bit, keys deleted, `CHECKPOINT`/`RESUME` log lines deleted, directory kept | passes **only** `boot_in_container`; refused by `record_release`, `boot_guard` and `deploy_check` (directory) |
| forged bit, directory deleted, log lines deleted, keys kept | refused everywhere (keys) |
| everything deleted and renamed, which is a hand-forged plain record | passes all four, as a forged plain record always could |

In the one partial pass, the boot check in the container has no checkpoint directory to see. A
tracked record can only reach the image through `record_release`, which refuses it. A hand-written
tracked record is still refused by the deploy check on the push host, as long as the directory
exists there.

**Kill at every step boundary.** A wrapper `CHECKPOINT_TOOL` sent SIGKILL to the whole process
group immediately before and after each of `plan`, `begin`, `start`, `finish`, `restore`,
`finalize` and `seal`, giving 14 kill points.

- At `plan:*`, no record exists.
- At every other kill point, the record left behind is `release_eligible: false` with provenance.
  It is refused everywhere as left, refused with the bit forged, and refused after a later
  `RESUME` attempt.
- How to read `attack_output.txt`: its "then RESUME: ... status passed, eligible True" lines
  show the harness's *own forged* record, written in the step before. The `RESUME` was refused
  (exit 4) and left that record untouched, and the next line shows every gate still refusing it.
  The refusals were for "not interrupted" (the forged status) or "no run secret" (killed before
  `begin` created it). Both are fail-closed.
- The record is non-eligible from its first write (`write_record running` already carries
  `checkpoint_mode`). No window exists in which a checkpoint-mode record is eligible.

**Other attempts considered:**

- `CHECKPOINT_TOOL` pointing at a stub cannot help. `CKPT_MODE` is set in `run_tests.sh` before
  the tool runs, and `write_record` forces the bit false.
- `CHECKPOINT=yes` (any value other than `1`) is simply a plain run, which is legitimate.
- `release_record.check_record` and `deploy_guard._record_problems` produced identical results on
  all 10 tracked `release/RELEASE_*.json` records before and after the change (`cmp_tracked.py`).

## 2. No regression: evidence

- **Plain full run, base runner (`b0133916`) compared with the RESUMEFIX runner.** Same 101-suite
  tree, timestamps, paths and pids normalised.
  - Exit code, stdout and the log are identical.
  - The record has the same keys and the same values, with one exception: `lock`, a hash that
    includes the git SHA, which differs because the two sandboxes commit different
    `run_tests.sh` bytes.
  - No provenance key and no `release_eligible_reason` is written.
  - The record directory holds only `locks/`, so no checkpoint directory is created.
- **Both plain records pass all four gates under the new guards.** This includes the record
  written by the *old* runner.
- **The only plain-mode code change** is that `.code` is now written after the leak census
  instead of before it. Nothing reads `.code` until after `wait`, so this cannot be observed.
- **Repo suites, run singly with `nice -n 19`:**

  | Suite | OK | FAIL | Note |
  |---|---|---|---|
  | `test_run_tests_script` | 11 | 0 | |
  | `test_deploy_guard` | 7 | 0 | |
  | `test_deploy_path` | 9 | 0 | |
  | `test_vacuity` | 8 | 0 | |
  | `test_w4_relfix_release_log` | 4 | 0 | |
  | `test_w4_fm2_lock_boot_guard` | 3 | 0 | |
  | `test_w3_deploy_evidence` | 2 | 1 | The failure is `ModuleNotFoundError: sqlalchemy`. This container's system Python has no `sqlalchemy` and no project venv, so it is environmental, not this diff. |

  `test_w4_resume_runner` results are given in §3.

## 3. Probe and tests

- **Probe rerun** (`research/final_build/w4/resume_review_probe.py`, adapted version,
  `probe_rerun_output.txt`): **26 held, 0 exposed, 0 could not run**, in 1 min 45 s. This matches
  `RESUMEFIX_probe_output.txt`.
- **Diff against the original** (`origin/claude/w4-RESUMEREVIEW`, 503a29cd): +67/−41. Every
  change falls into one of these groups:
  1. The attempt-file rename from `X.json` to `X.s1.json`, which is mechanical.
  2. Harness counters, gate files and the run secret moved outside the sandbox repo. This is
     necessary because F4 binds ignored and untracked files, and it does not weaken the probe.
  3. P01 reads the `.running` marker instead of a json that the killed suite never wrote.
  4. P03c gained a HELD branch. The original printed EXPOSED unconditionally. The new HELD
     predicate is strict: not rerun, nonzero exit, `failed` in both `suite_results` and
     `failing_suites`.
  5. P09 passes the same environment to both segments and pre-seeds the flaky counter. I checked
     that this does not neuter it. `GATE_ACTION` runs only after the gate opens, and the first
     segment is killed before that, so the manifest is still deleted only in the resumed
     segment. Pre-seeding makes every suite pass, which makes P09 a *stronger* fail-open test:
     a green resumed run must still be non-eligible.
  6. A "[observed values; prose describes the pre-fix EXPOSED case]" prefix on HELD lines. This
     is cosmetic.

  **The adaptation did not weaken the probe.**

  One caveat that is inherited, not new: several of the original predicates are "EXPOSED only if
  this specific bad thing happens" (P02c's `stuck`, and P09b is a static string search), so they
  could turn HELD vacuously if the message text changed. The ported assertions in
  `tests/test_w4_resume_runner.py` are positive and do not have this weakness.
- **Replaced test.** The base `test_a_failed_suite_is_rerun_on_resume_and_a_passed_one_is_not`
  ran a checkpointed run to completion with a failing suite, resumed it, and asserted that the
  failed suite was rerun. That is finding C2 encoded as intended behaviour. Its replacements are
  `test_p07_a_completed_failed_run_cannot_be_resumed_to_green` and
  `test_f2_an_earlier_failure_is_never_rerun_in_a_resumed_segment`. They assert the policy the
  owner decided. This is a **legitimate correction**.
  - `test_without_the_flags_nothing_changes` was strengthened. It now checks every provenance key
    and `release_eligible_reason`, the absence of a runkey, and the absence of column-0
    `CHECKPOINT`/`RESUME` log lines.
  - The other W4-B1 tests are kept.
- **`tests/test_w4_resume_runner.py`:** **40 / 40 OK**, exit 0, 126 s.

## 4. Findings

Severity is given for the context it matters in. "A" findings bear on Batch 4. "B" findings bear
only on trusting resume in the future.

### Batch 4 (Verdict A): none blocking

- **A-1 (Low, defence in depth).** A run id outside `[A-Za-z0-9TZ-]` skips the checkpoint
  directory check in both `resume_provenance` functions.
  - Cause: the id is filtered by `_RUN_ID` and silently ignored. `_BRAMBLELOOP_SUITE_JOB` is
    accepted from the environment unvalidated in non-RESUME modes, for example
    `_BRAMBLELOOP_SUITE_JOB=a_b CHECKPOINT=1`.
  - Why it is Low: the keys and log lines still refuse the record.
  - Fix: refuse, rather than skip, an id that does not match. Alternatively, validate the id in
    `run_tests.sh` for every mode.
- **A-2 (Low).** Some evidence that a checkpoint-mode run leaves behind is not consulted:
  - `release_eligible_reason`, which the tests assert plain runs never write;
  - `locks/run-<id>.flock`;
  - the runkey file.

  Adding `release_eligible_reason` to `RESUME_PROVENANCE_KEYS`, and treating an existing
  `locks/run-<id>.flock` like a checkpoint directory, would make the "everything but the
  directory" forgery in §1 fail in the container case as well.
- **A-3 (Info).** `check` pins the tracked full log (`full_log`) by hash only. It applies neither
  `resume_provenance` to it nor `summary == summary_log(full_log)`. A hand-edited summary with the
  full log left intact is caught only by the other checks. This is a forgery-class gap, but
  cheap to close.
- **A-4 (Info, pre-existing).** Run records and logs are unauthenticated, so a complete forgery
  passes, with or without resume. This is out of scope here and is unchanged by this branch.
- **A-5 (Process, must do before Batch 4).** `claude/w4-RESUMEFIX` is 4 commits behind
  `origin/claude/w4-INTEG8-next`:
  - d11d494, the INTEG8 owner-queue race fix, which also touches `runtime/release.py`;
  - three records-only commits.

  `git merge-tree` reports a clean merge. I did the merge in a scratch worktree, where `test_w4_owner_queue_race` gave 2 OK / 0 FAIL (the same as on `INTEG8-next` itself), `test_deploy_guard` 7/0, `test_run_tests_script` 11/0, and `test_w3_deploy_evidence` 3/0 (run in a scratch venv built from `requirements.lock`).
  RESUMEFIX changes `src/brambleloop/ops/release_record.py`, so the deployable tree digest
  changes, and a Batch 4 release needs its own uninterrupted plain full run on the merged tree.

### Resume trustworthiness (Verdict B)

- **B-1 (High): chain truncation defeats F2 and F3 without the run secret.** This is
  retry-until-green again.
  - Cause: each chain entry is MACed and linked to its predecessor, but nothing outside
    `manifest.json` records the chain's length or head. Any prefix of a valid chain is therefore
    a valid chain. `classify` decides "failed" only from chain entries, so dropping a `result:
    failed` entry turns the suite into "no result", and it is rerun. The orphaned `*.s1.json` /
    `.out` attempt files are never cross-checked against the chain.
  - Reproduction (`resume_review2/truncate.py`, output `truncate_output.txt`):
    - **Control.** Kill after `test_flaky` FAILED, then `RESUME`. The flaky suite is not rerun
      and the run fails. F2 holds.
    - **Attack 1.** Same kill, then truncate `manifest.json`'s chain to its `begin` entry, with no
      key and no other edit, then `RESUME`. The suite is **rerun and passes**: exit 0, record
      `passed`, `failing_suites: []`.
    - **Attack 2 (P07 bypass).** An *uninterrupted, completed, failed* run is first refused, as
      it should be. Then truncate the chain, which also drops the `end` entry, set the run
      record's `status` to `interrupted` and delete the log's `EXIT 1` line. Both of those files
      are unauthenticated. `RESUME` is accepted and the run ends **passed**.
  - In both attacks the record stays `release_eligible: false` with provenance, so the guards
    still refuse it (Verdict A holds).
  - Fix, two parts:
    1. Pin `(chain length, head MAC)` outside the checkpoint directory, in a mode-600 file next
       to the runkey that is rewritten on every `_append`, and refuse when the manifest does not
       end at the pinned head.
    2. Refuse any attempt file `*.s<N>.json` that has no chain entry.

    Add a regression test for both attacks.
- **B-2 (Medium): the checkpoint tool itself is not bound.**
  - Cause: `CHECKPOINT_TOOL` is in `RUN_LOCAL_ENV`, and the run key binds neither the tool's path
    nor its hash. The default tool is tracked, so it is bound through `git_sha`, but an override
    path outside the tree is not bound at all.
  - Effect: a later segment can run a different tool, for example one that ignores F2, and
    nothing records that.
  - Fix: bind the tool's sha256 into the run key, or refuse `CHECKPOINT_TOOL` in RESUME mode.
- **B-3 (Low): F2 trusts unauthenticated files.**
  - Cause: the "was the last segment interrupted" decision falls back to the run record's
    `status` and the log's `EXIT` line when the authenticated `end` entry is absent, and both are
    unauthenticated. This is safe only once B-1's pinned head makes the `end` entry
    unremovable.
  - Fix: write `seal`'s `end` entry durably before the terminal record, or pin it as in B-1.
- **B-4 (Info, documented).** A same-uid process can read the runkey and forge anything.
  `RESUMEFIX.md` states this. It is acceptable only because F1 keeps resumed runs out of
  certification.
- **Sound as implemented** (probed or read, not re-litigated):
  - F4: deny-by-default env, untracked and ignored inputs, site-packages content and host.
  - F5: verdict after the leak census, with leak counts restored.
  - F6: atomic, exclusive attempt files, with `.out` verified against hash and counts.
  - F7: final-set rerun and UTC-date refusal.
  - F8: one verdict source and the per-run flock.
  - P01–P10 are all HELD on rerun.

## Bottom line

- **Batch 4: SHIP**, after merging `INTEG8-next` (A-5) and doing the usual uninterrupted plain full
  run on the merged tree. A-1 and A-2 are worth a small follow-up but do not block.
- **Resume: NOT SAFE.** B-1 reopens C2 without the key. Fix B-1 and B-2, add regression tests,
  and get another fresh independent review before any owner decision to let a resumed run
  certify.
