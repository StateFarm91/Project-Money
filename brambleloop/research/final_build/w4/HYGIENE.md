# W4-HYGIENE: test and disk hygiene rows (F-145 to F-150)

**Status: PARTIAL (WIP checkpoint, owner pause 2026-10-12).** The code and the tests are
written. Not one test in this file has completed: two runs through the slot gate were
interrupted, one by the container restart and one by the pause.

- **Rows:** none closed. Advanced: F-146, F-149, F-150 (new code and tests) and F-145, F-147,
  F-148 (existing evidence identified).
- **Known risks:**
  - The new `run_tests.sh` lines (`classify_env`, `RR_ENVFAIL`) have passed `bash -n` and have
    never been executed.
  - `disk_growth` thresholds are first values.
- **Next executable step:** run `tests/test_w4_hygiene.py`, `test_run_tests_script`,
  `test_w3_tmp_hygiene`, `test_spend_governance`, then the required regression set; fix
  anything that fails; drop "WIP" from the commit.

Branch `claude/w4-HYGIENE`, based on `origin/claude/w4-INTEG2` 083c9fc. No production change.

## Rows

### F-145 Single Test Scratch Root and F-148 Direct-Test Hygiene

These already exist on INTEG2; the matrix mapping is stale.

- `run_tests.sh` gives every run a scoped `brambleloop-run-*` TMPDIR, and gives every suite its
  own TMPDIR.
- `tests/_tmp.py` (W3-HYG) gives direct `python tests/x.py` runs the same isolation.
- `tests/test_w3_tmp_hygiene.py` covers success, failure, SIGTERM/INT and SIGKILL sweeps. A
  static guard requires every temp-creating test to install the sandbox.

No code change. Re-map evidence: `test_w3_tmp_hygiene` (see results).

### F-146 Single Cleanup Trap

The trap already exists. New test:
`tests/test_w4_hygiene.py::test_run_tests_has_exactly_one_exit_trap_and_int_term_only_mark_the_exit`.
It fails if a second `trap ... EXIT` is ever added to `run_tests.sh`.

### F-147 Leak Postcondition

Already in `run_tests.sh`. The per-suite leak census reports `tmp_leak_entries` and
`tmp_leak_bytes` in the run record; `TMP_LEAK_STRICT=1` fails a leaking suite. Covered by
`test_w3_tmp_hygiene` (`test_tmp_leak_strict_makes_a_passing_but_leaking_suite_fail`).

### F-149 Disk Pressure Monitor (growth, not only level)

**New in `ops/health.py`:**

- `record_disk_sample` stores one `operating_readings` `disk.sample` row per health sweep:
  temp dirs left behind and free GB. A filesystem that cannot be read is stored as None, never 0.
- `disk_growth` returns OK, ALARM or UNKNOWN (UNKNOWN when there are fewer than 3 samples in
  24 h). It raises ALARM in two cases:
  - sustained temp-dir growth of at least 5 per hour, rising in at least 80% of steps;
  - the temp filesystem is projected to be full within 24 h at the observed rate.

**Wiring:** `runtime/release.py::handle_health_sweep`, which runs every 15 minutes, records the
sample. It opens or restates a P2 incident `disk:growth` while the state is ALARM and resolves it
when the state reads OK again. This is guarded, so it can never fail the sweep.

### F-150 Failure Classification Before Revert

New in `run_tests.sh`: `classify_env` reads each failing suite's output for environment causes:

- disk: ENOSPC, quota
- permissions: EACCES, read-only file system
- network: DNS, unreachable, refused, reset
- provider: credit balance, quota, rate limit, overloaded

When it matches, the log prints `ENVIRONMENT FAILURE (<class>)` beside the failure. The run record
gains `environment_failures` (a list of `suite:class`). The suite still counts as failing.

## Acceptance evidence (all through the shared slot)

| test | result |
|---|---|
| `tests/test_w4_hygiene.py` | not run (pause) |
| `test_run_tests_script` | not run (pause) |
| `test_w3_tmp_hygiene` | not run (pause) |
| `test_spend_governance` | not run (pause) |

The new `test_w4_hygiene.py` checks:

- the single trap;
- disk growth: UNKNOWN with too few samples, OK when steady, ALARM on temp growth, ALARM on
  projected fill, one sample per minute, unreadable free space stored as None;
- the sweep wiring;
- an environment-failure line plus a record entry, while a plain assertion failure is not
  classified.

Required regression set: not run (pause).
