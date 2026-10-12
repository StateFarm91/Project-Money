# W4-SWARMCONTROL: ownership boundaries, resource-aware concurrency, cooperative preemption

Branch `claude/w4-SWARMCONTROL` from `origin/claude/w4-INTEG2` 534f27a. Rows: F-457, F-470, F-473.

## Changes
- **F-457, Ownership Boundaries** (`ops/registry.py`).
  - `Registry.enrol(..., owns=[paths/globs])` records a lane's path manifest. Enrolment is the
    pre-dispatch moment, and it refuses a manifest that overlaps a live lane's with `OwnershipConflict`
    (a ValueError, so the CLI prints `refused:`). A lane is live until it is integrated.
  - `paths_overlap` is segment-aware (`src/a` does not overlap `src/ab`) and conservative for globs.
  - The CLI gains `--owns a,b,c`.
- **F-470, Resource-Aware Concurrency.**
  - New `swarm/resources.py` reads from the kernel with no dependencies: process RSS against the
    cgroup v2/v1 memory limit (falling back to MemTotal), CPU pressure (cgroup PSI
    `cpu.pressure` some avg60), process CPU seconds, and Postgres connections against
    `max_connections`. SQLite connections are reported as not applicable.
  - The load average is reported only as information. It is host-wide inside a container, so it
    must never scale this pool down for a neighbour's load.
  - `saturated` is True, False, or None when unreadable.
  - `swarm.capacity.worker_target` returns to one worker while saturated. An unreadable reading changes
    nothing.
  - `ops.health` gains the `resources` signal: DEGRADED when saturated, UNKNOWN when unreadable.
- **F-473, Priority Preemption** (cooperative). New `swarm/preempt.py`:
  - `preemption_wanted()` is true only when all of these hold:
    - the pool is full (running ≥ worker target; an unknown target never preempts);
    - a runnable job in a strictly better band or protected tier is waiting;
    - that job has waited at least 120 s.
  - `JobContext.should_yield()` checks at most every 30 s.
  - `JobContext.yield_now(why, key, state)` checkpoints (F-659) and raises `Preempted`.
  - `Worker.run_once` puts the job back to PENDING, unleased, with its attempt not counted. The write
    is lease-fenced and audited as `job.preempted`, and stats gain `preempted`.
  - First adopter: `intel.gallery_analysis`. `vision.analyse(should_stop=...)` yields between images
    (never mid-call). The judged images are already recorded, and the job requeues with a
    `gallery_progress` checkpoint.

## Acceptance evidence (testslot)
`tests/test_w4_swarmcontrol.py` 8/8 covers:
- memory and CPU pressure saturate, while host load never does;
- unreadable readings are UNKNOWN;
- `worker_target` returns to one worker while saturated;
- the health signal;
- preemption is wanted only behind a full pool for better, waited work;
- a yielding handler is requeued un-counted with its checkpoint and an audit row;
- gallery analysis is wired to yield;
- overlapping live manifests are refused, while integrated or disjoint lanes are allowed.

Regression suites green: test_health, test_swarm_runtime, test_reliability_ledger, test_waiter,
test_board_restart, test_learn_launch, test_cert_lanes_capacity, test_swarm,
test_w4_fml_checkpoint_adoption, test_lane_admission_concurrency.

`test_cost_governance_wave2` fails on INTEG2 534f27a itself, independent of this branch. Two audit
actions read by name merged without a retention entry: `improve.repeat_refused` (W4-FAILMEM) and
`verify.completed` (W4-OWNERHOME). This is fixed on `claude/w4-RETENTIONFIX`.

## Board rows advanced
F-457, F-470 and F-473 are implemented and tested. They are not deployed.
