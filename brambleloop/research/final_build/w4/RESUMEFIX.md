# W4-RESUMEFIX — fixes F1–F8 for the resumable runner review (RESUME_REVIEW.md)

- Branch: `claude/w4-RESUMEFIX`, cut from `origin/claude/w4-INTEG8-next` (b0133916, Batch 4). The runner
  under review is already merged there, so C1 was a live certification hole in Batch 4.
- Review: `research/final_build/w4/RESUME_REVIEW.md` and its probe, copied from
  `origin/claude/w4-RESUMEREVIEW` (503a29cd). The verdict was NOT SAFE: 26 probes, 10 HELD and 16 EXPOSED.
- Owner decision D-W4-OWNER-RESUME-POLICY (2026-10-27) is recorded verbatim in `DECISION_LOG.md`.
  It says: "retain the existing single-uninterrupted-run certification requirement. Do not permit
  resumed runs to certify releases until all independent review findings are fixed, the attack
  probes pass and a fresh independent review approves the implementation."

## Result

- **After the fix, all 26 probes are HELD and 0 are EXPOSED.** Two sources show it:
  - `tests/test_w4_resume_runner.py` ports every probe as an assertion: 40/40 pass.
  - The review's own probe, adapted to the new layout, was rerun:
    `research/final_build/w4/RESUMEFIX_probe_output.txt`.
- Before the fix (`RESUME_REVIEW_probe_output.txt`): 10 held, 16 exposed.
- **A resumed, checkpointed or sharded run still cannot certify a release.** This is by owner
  decision, not because anything is unfinished here. There is no bypass and no stub that could be
  switched on. Changing it needs new code, a fresh independent review and a new owner decision.
  Certification stays one uninterrupted plain full run, and that path is unchanged (proved by a test).
- The 2.7 h full suite was not run. All runs used small synthetic suites through the slot gate.

## Finding → fix → test

| Finding | Fix (where) | Regression test(s) in `tests/test_w4_resume_runner.py` |
|---|---|---|
| **C1** downgrade fails open; guard blind to resume | **F1.** `run_tests.sh` `write_record`: in any CHECKPOINT/RESUME/SHARD mode the record carries `checkpoint_mode`, `checkpoint` and `resumed`, and `release_eligible: false` with a reason citing D-W4-OWNER-RESUME-POLICY, **from the first write**. `finalize` now runs *before* the single terminal record write and produces a fragment that `write_record` folds in; a finalize failure adds a failing suite and prints `CHECKPOINT FINALIZE FAILED`. `seal` (closing the segment in the chain) runs after the record. A kill before `seal` leaves a terminal, never-eligible record, which F2 refuses to resume. `ops/deploy_guard.py` `resume_provenance()` refuses a record when any provenance key is present (presence, not value), when its log has a column-0 `CHECKPOINT`/`RESUME` line, or when its `run_id`/`job_id` has a checkpoint directory. This applies in `latest_suite(eligible_only)`, `_log_confirms`, `record_release` and `_record_problems`, and in `check` through `release_proof(record_dir=…)`. `brambleloop.ops.release_record.check_record` mirrors this: same keys and log pattern, plus `checkpoint_root`, defaulting to `artifacts/suite_runs`. **No override exists.** | `test_f1_kill_between_the_terminal_record_write_and_the_checkpoint_seal` (the review's required kill test: SIGKILL while `seal` hangs; also forges `release_eligible: true` and is still refused), `test_f1_kill_during_finalize_leaves_a_never_eligible_record`, `test_f1_a_failing_finalize_fails_the_run`, `test_f1_tracked_records_with_resume_provenance_are_refused_by_both_guards` (7 provenance variants plus the checkpoint-dir case, for both guards), `test_f1_both_guards_share_the_provenance_rule_and_neither_has_an_override`, `test_p09_*`, **`test_f1_an_ordinary_full_run_is_still_certified_and_a_checkpoint_run_is_not`** (a plain 100-suite full run is eligible, `record_release` ok, `check` → ALLOW; a checkpointed run of the same tree with its bit forged true is refused) |
| **C2** RESUME of a completed failed run is retry-until-green | **F2.** `plan --resume` refuses unless the last segment has no `end` chain entry, the record is `running`/`interrupted`, and the log has no `EXIT n` other than 130. A suite with any `failed` chain entry is never rerun (`classify`), its failure is restored into the report, and the run stays failed. Attempts are append-only `<suite>.s<N>.json`/`.out`, created with `link()` so they cannot be overwritten. | `test_p07_a_completed_failed_run_cannot_be_resumed_to_green`, `test_f2_an_earlier_failure_is_never_rerun_in_a_resumed_segment`, `test_p02b` (the torn attempt is kept beside the rerun) |
| **C3** forged, edited or copied checkpoints accepted | **F3.** A per-run 32-byte secret at `$SUITE_RUNKEY_DIR/<run_id>` (default `~/.brambleloop/runkeys`; on this host set `SUITE_RUNKEY_DIR=/home/user/bl-runs/runkeys`). The file is mode 600 in a 700 directory, checked for mode and owner, and refused if it is inside the repo, the working tree or the record dir. The manifest header is HMACed, and every event (begin, result, end) is a hash-chained, HMACed entry. Each result records `run_id`, segment, host (hostname, machine-id hash, kernel), key digest, `.out` sha256 and OK/FAIL/SKIP counts, and its own MAC. `plan`, `restore` and `finalize` verify all of it, and `manifest.run_id` must equal `RESUME`. An unverifiable pass is treated as no result and rerun; a failure in the chain stays failed, whatever the files say. | `test_p03c`, `test_p03d`, `test_p06a`, `test_p06b`, `test_f3_the_run_secret_lives_outside_the_repo_mode_600_and_tampering_is_refused` (chain tamper, key mode 644, key dir inside the repo) |
| **H4** binding gaps | **F4.** The key adds: content hashes of every untracked file and every git-ignored file under the tree, excluding venvs, `__pycache__`/bytecode and the `artifacts/` output store (see below); the content of every file in the interpreter's site-packages directories, which covers unpackaged modules; the **whole environment, deny-by-default** (only the run-local plumbing in `RUN_LOCAL_ENV` is excluded, and values are HMACed with the run secret, never stored); and hostname, machine-id and kernel. Mismatches name the field, for example `env.PYTHONPATH` or `tree_inputs.ignored`. | `test_p04a`–`test_p04d`, `test_p05a`–`test_p05d` |
| **H5** checkpoint written before the final verdict | **F5.** `schedule()` runs the leak census first. `finish` gets the leak counts and applies `TMP_LEAK_STRICT` (and exit≠0 / no passes) to the stored status. Leak counts are stored and restored, no longer `0 0`. | `test_p08_a_tmp_leak_strict_failure_survives_resume`, `test_p10_*` (P10b `tmp_leak_entries=1`) |
| **M6** durability | **F6.** Every write is temp + fsync + rename or link + directory fsync. `restore` verifies `.out` against its hash and counts. A `passed` attempt with a missing or mismatched `.out` is no result and is rerun, which clears the P02c stuck state. A failed attempt whose files are gone is still reported as failed, with a placeholder. A checkpoint `finish` that fails marks the suite failed (exit 70). | `test_p02a`, `test_p02b`, `test_p02c`, `test_p03a`, `test_p03b` |
| **M7** grouping and timing | **F7.** `scripts/suite_final_segment.txt` is the declared rerun-together / final-segment set: 213 suites derived from the review's criteria (`timeout\s*=`, `sleep`, `date.today(`/`datetime.now(`/`datetime.utcnow(`). The tool also applies those patterns at run time. On resume every final-set suite reruns in the new segment even if it passed earlier, and `finalize` fails a run that counts one from an earlier segment. A resume whose UTC date differs from segment 1's is refused, and a resumed run that finishes on another UTC date fails. | `test_f7_clock_sensitive_suites_rerun_together_in_the_final_segment`, `test_f7_a_resume_that_crosses_the_utc_date_is_refused`, `test_f7_the_declared_final_segment_set_covers_every_matching_suite` |
| **L8** consistency and concurrency | **F8.** The report writes one verdict per suite. `failing_suites` and `suite_results[].status` both come from it, and `finalize` fails the run if the checkpoint disagrees. Every checkpoint-mode segment takes an exclusive `flock` on `locks/run-<id>.flock` before reading anything, regardless of `ALLOW_PARALLEL`. The kernel releases it on death, and suites inherit it. A second resume exits 75. | `test_p03c` (record self-consistent), `test_f8_a_second_resume_of_the_same_run_is_refused_even_with_allow_parallel` |

## Replacing the branch's own test, and why it is a correction

W4-B1's `test_a_failed_suite_is_rerun_on_resume_and_a_passed_one_is_not` ran a checkpointed run to
**completion** with a failing suite, resumed it, and asserted that the failed suite ran again. That
is finding C2 written down as intended behaviour. A completed failing result could be replaced by a
later pass, so a flaky failure could be retried until green inside one "certification" run. The
owner's policy and the review both require the opposite. The test is therefore replaced by:

- `test_p07_a_completed_failed_run_cannot_be_resumed_to_green`: resume of a completed run is
  refused, the failure is not rerun, and its output is kept.
- `test_f2_an_earlier_failure_is_never_rerun_in_a_resumed_segment`: within an interrupted run, a
  suite that already failed is never rerun.

The replacement asserts strictly more. The other half of the old test, that a passed suite is not
rerun, is still asserted by `test_p01` and `test_f7` (the test_multi segment is 1). No other W4-B1
test was weakened. `test_a_mismatched_lock…`, `test_shards…` and `test_without_the_flags…` are kept,
and the last two assert more than before.

## Notes and limits (stated, not hidden)

- **What the MAC does and does not protect.** It defeats copied, edited, torn and forged checkpoints
  from anything that does not read the key file. It does not defeat a same-uid process that reads the
  key. That is one more reason F1 refuses resumed runs whatever the checkpoint says.
- **`artifacts/` is excluded from the ignored-input hash.** It holds run records, checkpoints and a
  content-addressed blob store (`artifacts/<xx>/<sha256>`) that suites write during runs; the store
  was observed growing during runs on 2026-10-27. Its blobs are named by their hashes. Binding it
  would refuse every real resume. Every other ignored path under the tree is bound, including
  `*.db`, `backups/` and `reports/shadow_release/_store/`. If a suite writes there, resumes are
  refused, which fails closed.
- **Deny-by-default environment.** A resume from a shell with different variables (for example
  `TERM` or `SSH_*`) is refused and the differing names are listed. Resume from the same
  environment, for example the same wrapper script.
- **Host binding.** Hostname (`vm`), machine-id and kernel are bound. If a container restart
  changes any of them, resume is refused. That fails closed but would make resume useless on that
  platform; this was not observed.
- **Cost.** Hashing site-packages (5,393 files, 383 MB venv-integ4) took 0.55 s. Tree inputs took
  0.01 s. Both are paid once per segment.
- **Probe adaptations**, listed in the probe's docstring:
  - the attempt-file layout;
  - harness state moved outside the sandbox repo;
  - P03c given a HELD branch (it printed EXPOSED unconditionally);
  - P09 given the same environment in both segments, with the flaky counter pre-seeded;
  - P01 reading the `.running` marker instead of an attempt the killed suite never wrote.

  HELD details keep the reviewer's EXPOSED-case prose with the observed values filled in, and are
  marked as such.

## Validation run (2026-10-27, slot gate, `venv-integ4`, on the tree of this branch)

- **Probe, before:** `RESUME_REVIEW_probe_output.txt` (f1cde398 runner): 10 held, 16 exposed, 0 could not run.
- **Probe, after:** `RESUMEFIX_probe_output.txt` (adapted probe, fixed runner): **26 held, 0 exposed, 0 could not run**.
- **21 suites, 182 tests, 0 failing.** Each line gives OK / FAIL / exit code:
  - Runner and the owner of the probes:
    - `test_w4_resume_runner`: 40 / 0 / 0
    - `test_run_tests_script`: 11 / 0 / 0
    - `test_vacuity`: 8 / 0 / 0
  - Deploy guard:
    - `test_deploy_guard`: 7 / 0 / 0
    - `test_deploy_path`: 9 / 0 / 0
    - `test_w3_deploy_evidence`: 3 / 0 / 0
    - `test_w4_rollback_rehearsal`: 5 / 0 / 0
    - `test_w4_fmbatch1_rollback`: 14 / 0 / 0
    - `test_w4_c01_integration_authority`: 3 / 0 / 0
    - `test_w4_c01_review`: 3 / 0 / 0
  - Release record and its readers:
    - `test_w4_fm2_lock_boot_guard`: 3 / 0 / 0
    - `test_w4_packetrel`: 6 / 0 / 0
    - `test_w4_relfix_release_log`: 4 / 0 / 0
    - `test_rc1_own_release`: 10 / 0 / 0
    - `test_freeze_candidate`: 9 / 0 / 0
    - `test_w4_ccrel`: 8 / 0 / 0
    - `test_w4_plact`: 8 / 0 / 0
    - `test_w3_final_master_gate`: 13 / 0 / 0
    - `test_cert_claude_independence`: 4 / 0 / 0
  - Supply chain and signing:
    - `test_w3_supply_chain`: 6 / 0 / 0
    - `test_w4_fmbatch1_signing`: 8 / 0 / 0
- **Not run:**
  - The 2.7 h full suite (by instruction). The change touches `src/brambleloop/ops/release_record.py`, so the deployable tree digest changes and a release from this tree needs its own uninterrupted full run, as always.
- **Next step required by D-W4-OWNER-RESUME-POLICY:** a fresh independent review of this branch.
  Until it approves, nothing here may be read as permission for a resumed run to certify, and the code refuses one regardless.
