# W4-IMPROVEMETRICS: value ranking, audit trail, learning health, withdrawn lessons

Branch `claude/w4-IMPROVEMETRICS` from `origin/claude/w4-INTEG2` 85ec5d0. Rows: F-394, F-398, F-399, F-605.

## Changes
- **F-394, Improvement Value Ranking.** `roi.prioritise` accepts two new fields:
  - `blocks_launch`: must name the readiness item. `True` is refused as a bare claim.
  - `tier`: the risk tier, which sets the reversibility rank. An unknown tier is refused.

  The ordering is: launch blockers first, then the existing order (free changes first, then impact per
  dollar, then expected impact), then the lower risk tier as a tie-break. Candidates without the new
  fields order exactly as before. `runner.order` passes each proposal's tier (from what it touches) and
  its `blocks_launch`.
- **F-398, Improvement Audit Trail.**
  - New nullable columns `Improvement.build_sha` and `Improvement.spend_cad`, added by the additive
    migration. Both are stamped at promote time.
  - `build_sha` comes from `core.build.identity` and is None when unknown.
  - `spend_cad` is the recorded cost attributed through `detail.improvement_id`. It is None when nothing
    is attributed, never CA$0.00.
  - `cells.history()` is exposed as `/api/improve` → `history`.
- **F-399, Learning Health Metrics.** `cells.retrospective()["learning_health"]` reports:
  - adoption and rejection rates over decided improvements (None until there is a verdict);
  - regressions caught (reverted);
  - repeated failures avoided: the `improve.repeat_refused` audit rows from W4-FAILMEM. Where that
    mechanism is absent the value is None with the reason;
  - cost per adopted change, only when every adopted change carries attributed spend.
- **F-605, Company Learning Memory.**
  - New `Lesson.withdrawn_at` and `withdrawn_reason`.
  - `bus.withdraw()` needs a reason and an evidence ref, and is audited as `lesson.withdrawn`.
  - `bus.inbox`, and therefore `consume.matching`, skip withdrawn lessons. The lesson stays on file.

## Acceptance evidence (testslot, one file at a time)
`tests/test_w4_improvemetrics.py` 9/9. Regression suites: test_roi, test_improve, test_improve_director,
test_improve_handlers, test_cert_improve_wave, test_cert_learning, test_v11_wiring. Results are in the
commit message.

## Board rows advanced
F-394, F-398, F-399 and F-605 move from engineering_open to implemented and tested on this branch. They
are not deployed. F-399's "repeated failures avoided" reads as a measurement once W4-FAILMEM is
integrated.
