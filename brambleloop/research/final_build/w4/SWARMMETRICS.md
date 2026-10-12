# W4-SWARMMETRICS: starved READY work, untouched opportunities, parallelism, agents view

Branch `claude/w4-SWARMMETRICS` from `origin/claude/w4-INTEG2` 534f27a. Rows: F-655, F-730, F-489, F-487.

## Changes
- New `src/brambleloop/swarm/metrics.py`.
  - **F-655:** `starved_ready()` finds runnable PENDING jobs past their band's READY SLA. SLAs run from
    15 min for a customer incident to 72 h for housekeeping. Such work counts as *starved* only while
    the pool has idle capacity (running < worker target). Late work behind a full pool is reported as
    `queueing`, and an unknown target as UNKNOWN. This is a new `ops/health` signal, `starved_ready`:
    DEGRADED when starved, UNKNOWN when it cannot be read.
  - **F-730** (the F-719 untouched-opportunity reading): `untouched_opportunities()` counts coverage gaps
    still UNCOVERED after 7 days, weighted by score. With no gaps discovered it reports UNKNOWN.
  - **F-489:** `parallelism()` reports:
    - pool busy and idle seconds, from new `RunnerState.busy_seconds` / `idle_seconds` accumulated by the
      pool loop (per-lane counters too);
    - utilisation;
    - duplicate work avoided: idempotency refusals counted by job type in `queue.durable.DEDUPE_HITS`.
    - Merge delay is the new `ops/registry.merge_delay()`, read from git: integration commit time minus
      the lane tip commit time. A lane that is not yet integrated has no delay (None), not zero.
  - **F-487:** `agents_view()` gives one row per agent: running job, ready and deferred pending counts,
    parked job types (from the thrash breaker), last completion, month spend (`spend_report`) and an
    idle flag.
- APIs: `/api/swarm/runtime` gains `starved_ready`, `untouched_opportunities` and `parallelism`. A new
  public read-only `/api/departments` serves the agents view.

## Acceptance evidence (testslot)
`tests/test_w4_swarmmetrics.py` 8/8 covers:
- starved vs queueing vs UNKNOWN, with deferred and fresh jobs ignored;
- the health signal;
- untouched opportunities, value-weighted;
- pool counters and dedupe hits;
- the runner state fields;
- merge delay against a real temporary git repository;
- the agents view;
- the routes.

Regression suites green: test_swarm_runtime, test_health, test_reliability_ledger,
test_route_auth_default_deny 7/7, test_customer_data_auth 9/9.

## Board rows advanced
F-655, F-730, F-489 and F-487 are implemented and tested. They are not deployed. F-655 also asks to
"deploy" and F-489's counters are process-local, so both read in production only after the next
release.
