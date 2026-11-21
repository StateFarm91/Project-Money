CERT: FAIL

Commit: d8751850be060daf92215780f27c8bcf56d7d030 (claude/batch19c)
Run ID: 20261121T011615Z-499 (record: cert/20261121T011615Z-499.json, log: cert/20261121T011615Z-499.log)
Command: cd brambleloop && JOBS=8 PY=/tmp/v/bin/python bash run_tests.sh   (plain full run, SCOPE: full, 1038 suites)
Venv: python3.13 venv, requirements.lock then requirements-test.lock (--require-hashes, test lock --no-deps)
Tree: clean (0 changed paths)
Started: 2026-11-21T01:16:15Z
Ended: 2026-11-21T03:16:15Z (duration 7200 s)

## Result: run did not complete. This is not a pass.

The runner was killed by the session's 2-hour limit on background commands. The run record says
status "interrupted", exit_code 130 and release_eligible false. run_tests.sh prints suite output
in canonical order only at the end, and its trap removes the per-suite output directory when it
exits. So no suite verdicts survived: the log holds only the run header, and the record's
failing_suites list is empty because no suite was ever counted, not because they passed.

## Failing suites

None identified. No suite results exist, so none can be listed with a first error line.

## Pre-existing vs new (511a8c63)

Not done. There are no failing suites to re-run on 511a8c63.

## Notes for the next runner

- The container has 4 CPUs (nproc=4), and JOBS=8 oversubscribes it. 1038 suites did not finish
  within 7200 s.
- The 2-hour background limit can't be extended in this environment. A certifying run needs a
  host or session where one plain full run can go beyond 2 h. Under run_tests.sh's own rules,
  CHECKPOINT, RESUME and SHARD runs are never release-eligible, so they can't stand in for it.
