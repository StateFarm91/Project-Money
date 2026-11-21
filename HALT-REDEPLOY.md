# eng/halt-380-redeploy: an attempt-cap hold filed under an earlier build is re-armed once per deploy

**Production (19h14, evidence at 22:50Z):** the halt-chain fix was live but had never run. The
12 halted products' `rebuild-incomplete` incidents were HELD at REBUILD_MAX_ATTEMPTS (3). All
three attempts ran under the old code, whose chain stopped at gate.certify. Nothing re-reads a
held row, so the daily retry stays stopped and halt 380 can never close.

**Fix.** Attempts are bounded per deployed build, like RETRY_AFTER (`_current_deploy`):

- `_rebuild_incomplete` records `held_commit`, the build that reached the cap.
- `rebuild_graph.held_before_deploy` decides when a hold is re-armed. An attempt-cap hold whose
  `held_commit` differs from the running commit, or was never recorded (legacy), gets one
  fresh, recorded budget per deploy. The record goes to `hold_released`, with
  `reason: attempt_cap_previous_deploy`, the deploy and the previous build. The sentinel then
  enqueues one targeted rebuild at the hold's own change (keyed on row, hold and commit, so
  once per deploy). The sentinel audit lists `rebuild_incomplete_redeploy_rearmed`.
- A hold re-reached under the running build stands, so the cap still stops a rebuild that
  cannot complete after 3 attempts per build.
- These are never re-armed:
  - parked holds (a real gate refused, e.g. listing.seo_blocked);
  - `refused_by` and `failed_attempts` (DEAD) holds, which keep their cleared-cause release;
  - any hold whose wording names child safety or the owner;
  - anything when the deploy is unknown.
- The row stays open and halting. Only a verified rebuild closes it.

**Tests.** `tests/test_halt_redeploy_rearm.py` checks that a hold from an earlier build is
re-armed once, a legacy hold is re-armed, a hold under the running build stands, and
parked, refused, DEAD, child-safety and owner holds and an unknown deploy are never re-armed.
The halt suites are listed in the release record.
