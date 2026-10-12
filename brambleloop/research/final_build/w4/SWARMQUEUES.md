# SWARMQUEUES (F-656, F-630) - PARTIAL (WIP)

Status: PARTIAL. Rows advanced, not closed: F-656 (RUN/GROW/IMPROVE pull order), F-630 (WATCHING spans).

Built in swarm/orchestrate.py: work classes RUN/GROW/IMPROVE/WATCHING, PULL_ORDER, CLASS_BY_BAND_KIND,
work_class_for, LAUNCH_SERVES, open_readiness_items (newest launch.assessed), backlog_order(db)
(class, then launch rank in shadow, then index), watching spans (audit swarm.watching_started/ended,
watching_spans). feed_idle uses backlog_order and returns pull_plan/watching. Retention entries added for
the two watching actions.

Last test results (this branch):
- test_w4_swarmqueues: 4 passed, 2 failed (incl. test_pull_order_is_run_then_grow_then_improve_stably).
- test_swarm_runtime: 3 FAIL (lane ceiling spent backlog skip; idle queue takes highest-value standing
  items once; backlog idempotent within window) - regression caused by the feed_idle/backlog_order change.
- test_cert_wiring 16/16; test_swarm OK; test_cost_governance_wave2 only the pre-existing mkdtemp failure.
- Required regression set: not run on this branch.

Known defects: feed_idle reordering breaks the three test_swarm_runtime backlog tests; two own tests fail.
Next executable step: run test_w4_swarmqueues and test_swarm_runtime with tracebacks, fix backlog_order so
feed_idle keeps ceiling-skip and idempotency semantics, then run the required regression set and push.
