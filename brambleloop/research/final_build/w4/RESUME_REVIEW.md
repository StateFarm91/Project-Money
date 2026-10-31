# W4-RESUMEREVIEW — independent review of the restart-safe test runner (W4-B1)

- Subject: `claude/w4-RESUME` at `f1cde398` — `run_tests.sh` (+58 lines),
  `scripts/suite_checkpoint.py` (new, 311 lines), `tests/test_w4_resume_runner.py` (new).
  Also read: `ops/deploy_guard.py` as of `f1cde398`.
- Question: can this runner and its evidence aggregation enforce the owner's proposed policy for
  counting a resumed run toward release certification?
- Reviewed 2026-10-27, UTC. Evidence: `research/final_build/w4/resume_review_probe.py` (26 probes,
  synthetic suites in throwaway git repos, the real runner and checkpoint tool copied byte for byte,
  `nice -n 19`, one heavy process at a time). Full output, run 2026-10-27T16:14:30Z:
  `research/final_build/w4/RESUME_REVIEW_probe_output.txt` — **10 held, 16 exposed, 0 could not run**.
  The branch's own `tests/test_w4_resume_runner.py` passes 5/5. The 2.7-hour full suite was not run.

## Verdict: NOT SAFE

As written, the runner cannot enforce the proposed policy. It handles the easy case correctly: a
suite killed mid-run is rerun, and tracked-source, commit, lockfile, JOBS and `BRAMBLELOOP_*`
changes are refused. It fails on the rest:

1. `release_eligible=false` for resumed runs fails open, and the deploy guard reads no resume
   provenance (C1). This is a live hole under **today's** policy, not just the proposed one.
2. `RESUME` reruns suites that **completed and failed**, so a run becomes green by retrying until
   it passes, and the failed attempt's evidence is overwritten (C2).
3. Checkpoints have no integrity protection. A forged, edited or copied result is accepted (C3).
4. The key does not bind untracked files, git-ignored inputs, the installed package set or most
   of the environment (H4).
5. A checkpoint is written before the suite's final verdict, so a `TMP_LEAK_STRICT` failure turns
   into a pass on resume (H5).

After fixes F1–F8 below it can be re-reviewed for ADOPT WITH FIXES. Until then, a resumed run
should not count toward certification, and C1 needs fixing even if resume is never adopted.

## Findings

Severity: **Critical** = a failing or unverified run can be certified. **High** = the policy is
violated in a realistic operator or environment sequence. **Medium** = evidence wrong, incomplete or
unrecoverable. **Low** = consistency or forensics.

### C1 — Critical — the resumed-run downgrade fails open, and the deploy guard cannot tell resumed runs apart

- Mechanism: `write_record "$status"` (`run_tests.sh:562`) computes `release_eligible` without
  knowing the run was resumed. A *separate later* step, `finalize` (`run_tests.sh:563`),
  rewrites it to `false`. Three paths leave it `true`:
  - that step's exit status is ignored (`[ -n "$CKPT" ] && …`, with no `set -e`);
  - `cmd_finalize` returns 0 and does nothing when `manifest.json` is unreadable
    (`suite_checkpoint.py:253`);
  - a SIGKILL or container restart between lines 562 and 563 skips `finalize` entirely.

  Any `finalize` failure (ENOSPC, which this repo has had; a crash; a corrupt manifest) leaves a
  resumed, full, clean run marked `release_eligible: true`, with no `resumed` and no `checkpoint`
  key.
- `ops/deploy_guard.py` has no occurrence of `resumed` or `checkpoint`. `latest_suite(...,
  eligible_only=True)` and `_record_problems` trust the `release_eligible` bit alone. `_log_confirms`
  also passes, because the appended log carries the original `RUN ID`/`GIT SHA` and a final
  `TOTAL … suites failing: 0`.
- Reproduction, P09: a full-scope sandbox (106 suites, clean tree), SIGKILL mid-run, then
  `RESUME`. In the resumed segment a suite deletes `manifest.json`, standing in for any
  `finalize` failure.
- Evidence:
  - **P09-control** (finalize intact): `release_eligible=False, resumed=True`, and the guard picks
    nothing. HELD.
  - **P09**: `resumed full run exit 0; record release_eligible=True, resumed=None, checkpoint key
    present=False; deploy_guard.latest_suite(eligible_only=True) returned this resumed run;
    _log_confirms -> None`. EXPOSED.
  - **P09b**: the guard source contains neither string. EXPOSED.

### C2 — Critical — RESUME of a completed, failed run is retry-until-green; the failed attempt is erased

- Mechanism: `cmd_plan` selects every suite whose result is not `passed`, so `failed` is included,
  and it never checks that the previous segment was interrupted. `cmd_finish` overwrites
  `<suite>.json` and `<suite>.out`. The branch's own test asserts this as intended behaviour
  (`test_a_failed_suite_is_rerun_on_resume_and_a_passed_one_is_not`).
- Reproduction, P07: a suite that fails on its first execution and passes afterwards. A normal
  `CHECKPOINT=1` run that is **not** interrupted completes `failed`; then `RESUME=<id>`.
- Evidence: `run 1 completed failed (exit 1, no interruption); RESUME reran only the failure, which
  passed: record now passed, failing_suites=[]; the checkpointed output of the failed attempt was
  overwritten (now: 'OK   test_flaky')`. EXPOSED.
- Policy: a complete failing result was replaced by a later pass. The real suite has many
  timing- and date-sensitive files (68 with `timeout=`, 48 with `sleep`, 136 reading the clock),
  so this is the flake-laundering path.

### C3 — Critical — no authenticity: forged, edited and copied checkpoints are accepted

- Mechanism: a result is plain JSON compared only by `status == "passed"` and `key == manifest
  key` (`passed()`, `suite_checkpoint.py:148`). It holds no run id, host, output hash, chain or
  HMAC. `.out` is not hashed, and nothing compares it to the JSON. `manifest.run_id` is never
  compared to `RESUME`.
- Evidence:
  - **P03d**, full forgery: a suite that failed the only time it ran had its JSON set to
    `status=passed, exit_code=0, ok_count=1` and its `.out` replaced. Result: `resume exit 0, record
    passed, suites_failing 0`. EXPOSED.
  - **P06a**, copied from another run: run B's own result was `failed`. Run A's `passed` result for
    the same SHA, copied over it, was accepted. The suite was not rerun (executions 1→1), and B's
    record lists it as segment 1 of run B. EXPOSED.
  - **P06b**, copied directory: a checkpoint directory copied to `20990101T000000Z-1` was resumed
    and accepted. Its manifest still names the original run id. EXPOSED.
  - **P03b**, edited `.out` (one `SKIP` line rewritten as `OK`): `accepted silently:
    tests_passing=7 (true 6), tests_skipped_reported=0 (true 1)`. EXPOSED.
  - **P03c**, edit of `failed`→`passed` in the JSON only: the suite was **not rerun**. The report
    used the stale `exit_code` and failed the run, but `suite_results` says `'passed'` while
    `failing_suites` lists the same suite. The record contradicts itself. EXPOSED. It failed
    closed only by accident.
- The key has no host field, so a checkpoint from another machine with the same paths and
  interpreter is indistinguishable. No age limit applies.

### H4 — High — binding gaps: what changes a result but is not in the key

The key holds the commit SHA, `git status --porcelain`, `git diff HEAD`, both lock hashes, the
interpreter's real path, version and prefix, JOBS, the scope and shard, a suite-list hash, and env
vars with prefixes `BRAMBLELOOP_ ETSY_ ANTHROPIC_ TMP_LEAK_STRICT REQUIRE_CLEAN`. It does not hold
a per-suite content hash. For tracked files the whole-tree SHA plus the diff covers that, and P04a
confirms it. Gaps:

| Probe | Change between kill and resume | Result | Fresh run of the same suite |
|---|---|---|---|
| P04b | edit an **untracked** file the suite imports (porcelain lists its name, not its content) | accepted, exit 0 | exit 1 `helper=2` |
| P04c | edit a **git-ignored** fixture | accepted, exit 0 | exit 1 `fixture=2` |
| P05b | change an **installed package** inside the same venv, lockfile untouched | accepted, exit 0 | exit 1 `depmod=2` |
| P05c | set **PYTHONPATH** (not in the fingerprint) | accepted, exit 0 | exit 1 |

Other env vars read by `src/` or `tests/` and outside the fingerprint: `OPENAI_API_KEY`,
`OPENAI_API_KEY_FILE`, `RAILWAY_ENVIRONMENT`, `RAILWAY_GIT_COMMIT_SHA` (hosted-mode markers in
`core/db.py`, `ops/dependencies.py`, `ops/release_record.py`), `DATABASE_URL`, `PATH`, `HOME`,
`TZ`, `CERT_TRACE`. Also unbound: hostname or machine, kernel, system libraries (Pillow
codecs), wall-clock date. A release run normally uses `REQUIRE_CLEAN=1`, which closes P04b
(untracked files make the tree dirty), but nothing requires it for a resume, and P04c, P05b and
P05c are open even on a clean tree.

Held: P04a tracked edit → refused on `dirty_content_sha256`. P04d new commit → refused on
`git_sha`. P05a lockfile → refused on `locks.requirements.lock`. P05d new `BRAMBLELOOP_X` →
refused on `env`. JOBS and suite-set changes are refused (branch tests).

### H5 — High — the checkpoint is written before the suite's verdict is final

- Mechanism: `finish` (`run_tests.sh:465`) records `passed` from the exit code and `OK` count.
  The per-suite TMPDIR leak census runs **after** it (`:466–470`). Under `TMP_LEAK_STRICT=1` the
  report turns a leaking suite into a failure, but the checkpoint already says `passed`, and
  `restore` writes `0 0` as the leak for every reused suite (`suite_checkpoint.py:245`).
- Evidence:
  - **P08**: `a fresh strict run fails the leaky suite (exit 1); the checkpoint wrote 'passed' …
    the resumed run passes (exit 0, tmp_leak_entries=0)`. EXPOSED.
  - **P10b**: `tmp_leak_entries=0 although test_leaky leaked 1 entry in segment 1`. EXPOSED.
- The unit of evidence is therefore not the full suite result. One input to the report's verdict
  is missing from it.

### M6 — Medium — durability: no fsync, non-atomic `.out`, and a stuck state

- `_write` uses temp + `os.replace` with no `fsync` of the file or the directory. `cmd_finish`
  writes `.out` with a plain `write_text`: not atomic, not hashed, written before the JSON. On a
  VM-level kill (the container restarts this tool exists for), the JSON can survive while `.out`
  is torn or empty.
- Evidence:
  - **P02a**: an empty JSON is read as "no result" and rerun. HELD; the JSON side fails safe.
  - **P03a**: a truncated JSON is rerun. HELD.
  - **P02b**: `.out` torn under an intact `passed` JSON gives `resume exit 0, status passed,
    tests_passing=3 (true value 6)`. The JSON's `ok_count=5` disagrees, and nothing compares
    them. EXPOSED.
  - **P02c**: with `.out` missing under a `passed` JSON, resume 1 reports the suite as `never
    ran` and fails. Resume 2 reruns **0 of 2** and fails again. The run can never complete by
    resuming, and `suite_results` still says `'passed'`. EXPOSED.

### M7 — Medium — shared state, ordering and timing (item 5)

- Survey of the 786 `tests/test_*.py` files at `f1cde398`, by grep (not exhaustive):
  - Every server binds port 0: `test_cert_claude_independence`, `test_db_backup_housekeep`,
    `test_deploy_verify`, `test_w4_laura_unified`, `test_w4_smoke`.
  - Databases are per-suite SQLite under the suite's own TMPDIR.
  - Each suite gets its own TMPDIR.
  - No suite writing to a shared path in the repo was found.
  - 9 suites read the real repository through git (`test_secret_scan`, `test_w3_tmp_hygiene`,
    `test_cert_design`, …). That content is bound by the SHA.
  - **No pair of suites was found that must rerun together because of a port, database or
    TMPDIR.**
- What a restart does change is **load and timing**. A resumed segment runs only the remaining
  suites, so CPU contention for timing-sensitive suites (68 files with `timeout=`, 48 with
  `sleep`) differs from the uninterrupted run. A suite that passed under light load in segment 2
  is not the same test configuration as the full run. A resume that crosses UTC midnight changes
  "today" for the 136 suites that read `date.today()` or `datetime.now()`.
- The runner **cannot express grouping**. The unit is one file, `plan` decides per file, and
  `SHARD` hashes each filename independently. There is no rerun-together set, no
  always-rerun-in-final-segment class, and no clock or date binding.

### L8 — Low — consistency and forensics

- P03c: the record contradicts itself (`suite_results` says `passed`, `failing_suites` lists it).
- Segment history is overwritten per suite. Only `segments[].to_run` shows that a suite ran
  more than once.
- With `ALLOW_PARALLEL=1`, two `RESUME`s of the same id both append segments and write the same
  result files; nothing excludes it. Found by code reading, not probed.
- `start` and `finish` failures are ignored. Both fail safe: the suite stays `running` and
  reruns.

## Item-by-item answers

1. **Unit of evidence.** One suite file. The result is written after the process exits, with
   the exit code, OK count and full output, but **before** the leak census (H5). The JSON swap
   is atomic, with no fsync. `.out` is neither atomic nor hashed, so a partial `.out` is accepted
   as complete (P02b), and a missing one leaves the run stuck (P02c).
2. **Binding.** SHA, tree, dirty diff, locks, interpreter, JOBS, suite set and a subset of env
   vars are bound, and a mismatch is refused (exit 4). Untracked content, ignored inputs, installed
   packages, the rest of the environment and the host are not bound (H4). There is no per-suite
   hash; for tracked files the tree SHA covers it.
3. **Authenticity.** None. No HMAC, hash or chain; forged, copied and edited results are
   accepted (C3).
4. **Interrupted tests.** Held. An in-flight suite is left `running` and is always rerun
   (P01). SIGTERM left no orphaned suite process (P01b). The gap is the opposite case: completed
   **failed** suites are also rerun (C2).
5. **Shared state.** No port, database or TMPDIR coupling was found. Load, timing and date do
   change across a restart, and the runner cannot express grouping (M7).
6. **Aggregation.** Held for counting. `TOTAL PASSING` equals the union, and each suite is listed
   once (P10). It fails for leak figures (P10b), for a torn `.out` (P02b), and for self-consistency
   (P03c). Provenance (`resumed`, `checkpoint.segments`, `gaps`) is visible only when `finalize`
   succeeds, and the deploy guard ignores it (C1).
7. **Deliberate tests.**
   - kill -9 mid-suite: P01, HELD.
   - Kill during a checkpoint write: P02a HELD, P02b and P02c EXPOSED.
   - Corruption: truncation P03a HELD; byte or line edit P03b EXPOSED; `failed`→`passed`
     P03c EXPOSED; full forgery P03d EXPOSED.
   - Source change: tracked P04a and P04d HELD; untracked P04b and ignored P04c EXPOSED.
   - Venv or lockfile: lockfile P05a HELD; package in the same venv P05b EXPOSED; `PYTHONPATH`
     P05c EXPOSED.
   - Copied from another run_id: P06a and P06b EXPOSED.

## Required fixes (all needed before a resumed run may certify)

- **F1 (C1). Fail closed.**
  - Pass the resume state into `write_record`, so `release_eligible` is false for any
    `CHECKPOINT`, `RESUME` or `SHARD` run from its first write.
  - Make a `finalize` failure fail the run.
  - Make `ops/deploy_guard.py` (and `release_record.check_record`) refuse records that carry
    `checkpoint`/`resumed`, or whose `job_id` has a checkpoint directory, unless the
    owner-approved verification in F3 passes.
  - Add a test that kills the run between `write_record` and `finalize`.
- **F2 (C2). Rerun only what was interrupted.**
  - Refuse `RESUME` unless the prior segment ended interrupted: record `running` or
    `interrupted`, with no `EXIT 0..n` sentinel other than 130.
  - A suite with a terminal `failed` result is never rerun inside the same certification run.
    The run stays failed.
  - Keep every attempt as an append-only `<suite>.<segment>.json` / `.out`.
- **F3 (C3). Authenticate.** Each result records `run_id`, `segment`, host or machine id, and the
  sha256 of `.out` plus its OK, FAIL and SKIP counts. The manifest keeps a hash chain over
  results in completion order, MACed with a per-run key held outside `artifacts/` and the repo.
  `plan`, `restore` and `finalize` verify all of this. A mismatch reruns that suite, and
  `manifest.run_id` must equal `RESUME`.
- **F4 (H4). Bind every input.**
  - Hash untracked file contents, or require `REQUIRE_CLEAN=1` and no untracked files for a
    certifying resume.
  - Hash git-ignored inputs under the tree (fixtures, `.venv` excluded or hashed separately).
  - Hash the installed distribution set (name, version and RECORD hashes for the interpreter's
    `site-packages`).
  - Fingerprint the whole environment, deny-by-default, minus an explicit list of run-local
    variables.
  - Add hostname, machine id and kernel.
- **F5 (H5). Final verdict first.** Write the terminal checkpoint only after the leak census and
  the `TMP_LEAK_STRICT` decision. Store the leak counts and restore them.
- **F6 (M6). Durable evidence.**
  - Write `.out` as temp + fsync + rename, and fsync the JSON and the directory.
  - `restore` verifies `.out` against the stored hash and counts.
  - A `passed` result with a missing or mismatched `.out` is treated as no result and rerun.
    This also clears the P02c stuck state.
- **F7 (M7). Express grouping and timing.**
  - Add a declared rerun-together / always-rerun-in-final-segment set for timing- and
    clock-sensitive suites, and refuse a resume that crosses the UTC date.
  - The owner should decide whether a segment run at lower load counts for those suites at all.
- **F8 (L8).** Make the record self-consistent (`suite_results` derived from the same verdicts as
  `failing_suites`), and exclude concurrent `RESUME`s of one id regardless of `ALLOW_PARALLEL`.

## Estimated hours saved per restart if adopted (after the fixes)

- Measured full runs at JOBS=3 in `release/suite_runs/*.json`: 5,875 s, 7,627 s, 7,665 s,
  8,299 s, 9,612 s (1.6–2.7 h).
- With a restart at a uniformly random point, resume saves on average about half the run, less
  the rework of the ≤3 in-flight suites (run concurrently, bounded by the slowest suite: 342 s
  measured 2026-09-18, not re-measured), less seconds of plan and verify overhead.
- **Estimate: about 0.7–1.3 h saved per restart on average, up to about 2.6 h for a late
  restart; 0 h for a restart in the first minutes.**
- At the two restarts observed in about 17 h (2026-10-26T08:17Z, 2026-10-27T01:29Z), that is
  roughly 1.5–2.6 h a day.
- F4's hashing of the installed set and untracked or ignored inputs adds seconds per segment.
  F2 removes nothing a legitimate restart needs.

---
Probe: `nice -n 19 python3 research/final_build/w4/resume_review_probe.py [P01 …]` from `brambleloop/`.
It exits 0 when every probe ran, whatever it found.
