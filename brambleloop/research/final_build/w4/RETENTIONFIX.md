# W4-RETENTIONFIX: retention entries for two audit actions merged in W4

Branch `claude/w4-RETENTIONFIX` from `origin/claude/w4-INTEG2` 534f27a.

## Defect
On INTEG2 534f27a, `tests/test_cost_governance_wave2.py::test_only_dead_letters_that_are_refusals_working_are_ever_removed`
fails with `RetentionRefused`. Two audit actions are now read by name in `src/` without an
`ops.retention.KNOWN_READ_ACTIONS` entry:
- `improve.repeat_refused`, from W4-FAILMEM and W4-IMPROVEMETRICS (mine);
- `verify.completed`, from W4-OWNERHOME (mine).

## Fix
- `improve.cells.learning_health` now counts `improve.repeat_refused` inside the retrospective window, not
  over all time. A lifetime count over a pruned table silently shrinks.
- The action is registered as `windowed`.
- `verify.completed` is registered as `latest`: the owner overview reads only the newest self-check.

## Evidence (testslot)
- `test_cost_governance_wave2`: the retention test now passes. One other test in the file still fails:
  `test_no_production_module_creates_a_directory_nothing_removes`, on `visual/hero_review.py:57` and
  `visual/inspect.py:320` (plus the allowed `app/main.py` continuity download). These are leaked
  `mkdtemp` calls in visual lanes, outside this domain, and are reported to the integrator.
- `test_w4_improvemetrics` 9/9, `test_w4_failmem` 10/10, `test_w4_ownerhome` 10/10.
