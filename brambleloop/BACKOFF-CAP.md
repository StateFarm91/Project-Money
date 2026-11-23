# BACKOFF-CAP: cap the free-poll backoff; stop counting never-accepted FLUX calls

Branch `eng/backoff-cap`, from 29b8d03a2 (19i19). Not merged, not deployed.

## Production evidence (19i19, 2026-11-23 03:58Z)

- The scheduler readback listed 19 job types parked by the free-poll backoff in
  `swarm.orchestrate._free_poll_backoff`:
  - `radar.concept_pool` ×32 until 2026-12-01 (the new-product supply);
  - `assets.model_photography` ×32 until 2026-12-25, `assets.owned_photography` ×32 until
    2026-12-24;
  - `assets.photo_review` ×32, `creative.model_reference_pack` ×32;
  - `creative.blinded` until 2028;
  - `listing.package` ×2 and `visual.identity_drift` ×2.
- FLUX `calls_in_window_by_status` was `{UNCERTAIN: 9..30, BILLED: 21}`. UNCERTAIN calls hold
  their reservation against the CA$5 daily ceiling. Yesterday the reserved total reached
  CA$4.90, while BFL billed cents. Most of those calls were `403 not_authenticated` from the
  submit endpoint.

## 1. The backoff cap

### Root cause

The park was `period × min(32, 2^level)`. "A new observation never pulls the deadline
earlier" (`max(until, previous)`) made it ratchet. ×32 of a daily period is a month, and ×32
of `creative.blinded`'s fortnight is more than a year. The breaker exists to stop *hot* idle
loops: a 15-minute poller burning cycles on an unchanged answer. Pipeline jobs whose inputs
change slowly, or only with the clock, look identical for days, and the breaker parked them.

### The cap

`park = min(period × factor, backoff_cap_seconds(job_type))`, where:

- `backoff_cap_seconds = min(4 × period, 6 h)`;
- `factor = min(2^level, MAX_BACKOFF_FACTOR = 4)`;
- `period` is the job type's shortest period in `runtime.worker.CADENCES`.

| Cadence period | Cap | What the breaker still does |
|---|---|---|
| 15 min | 1 h | slows the poller 4× (2× then 4×) |
| 1 h (`creative.model_reference_pack`, `assets.photo_review`, `chain.successors`) | 4 h | slows 4× |
| 6 h (`radar.concept_pool`, `listing.package`) | 6 h | at most one skipped window |
| 24 h and longer (`assets.*_photography`, `visual.identity_drift`, `creative.blinded`) | 6 h | never delays the next window |

The previous deadline still never pulls earlier. It is now also clamped to `now + cap`, so it
cannot ratchet. Paid-loop suspensions (`kind: suspended`) are unchanged: they wait for a
changed hypothesis, as before.

### Rows parked under the old cap

- **On read.** `suspended_job_types` reads every backoff as
  `min(suspend_until, since + cap)` (`capped_until`). A ×32 row cannot hold a job past the
  cap, even before it is rewritten.
- **On boot.** The first `Scheduler.tick` of a process rewrites the rows
  (`clamp_parked_backoffs`, once per database handle), and so does the app startup. A rewritten
  row records `clamped_from`, `clamped_at` and `cap_seconds`.
- **Every sweep.** `ops.thrash` also clamps and reports the result as `backoff.clamped`.

For production: every ×32 row was written more than 6 h ago, so every one expires on the first
tick after deploy, and the jobs are enqueued in their current cadence window.

### Upstream inputs (wake when the input changes)

These are new entries in `UPSTREAM_INPUTS` and `INPUT_PROBES`. Each one is an input the
handler actually reads.

| Job type | Wakes on |
|---|---|
| `assets.owned_photography` | `gate.certify`, `chain.rebuild` made progress; image capability (probe below) |
| `assets.model_photography` | the same, plus `creative.model_freeze` |
| `assets.photo_review` | `assets.owned_photography`, `assets.model_photography`, `assets.physical_upgrade` made frames |
| `creative.model_reference_pack` | `creative.model_freeze`; image capability |
| `creative.blinded` | `gate.certify`, `intel.benchmark_refresh` (the catalogue and the benchmark it judges) |
| `radar.concept_pool` | unchanged (`intel.watchlist_scan`, `research.investigate`). Its clock-driven inputs (staleness, the monthly allowance) are covered by the 6 h cap |

`_image_capability_since` is a row probe. It fires on a paid-image activation recorded after
the backoff, or on an `image.probe` that turned OK after a refused one. A routine OK probe
after an OK probe is not new input.

## 2. FLUX UNCERTAIN

### Root cause

`gateway.images._gated.classify` returned UNCERTAIN for every exception raised before
`billing["accepted"]`. That covered a 403 from the submit endpoint. Its reasoning ("once the
transport is entered, … HTTP error does not prove the provider did not accept work") holds
for a timeout. It does not hold for a 4xx: the provider refused the request and returned no
task id.

### The rule (`paid_provider_gate.never_accepted`)

The gate releases a reservation (`RELEASED`, the gate's existing not-billed status) only on
proof from the submit call that it was never accepted:

- an HTTP 4xx from the submit endpoint (401, 402, 403, 404, 422, 429, …);
- a `URLError` before any answer: DNS, connection refused or connect timeout, TLS handshake.
  `_post` renders it as "<label> unreachable: …". urllib raises it only while connecting or
  sending.

Everything else stays UNCERTAIN (counted):

- a read timeout or a reset after the request was sent;
- an unreadable 2xx;
- **a 5xx** (a 502 or 504 can sit in front of a backend that did accept);
- anything after a task id came back. That is BILLED, as before.

This rule is narrower than "any error before a task id is returned". Releasing a 5xx or a
read timeout could release a call that was billed, so the rule does not.

### Existing rows

`reclassify_uncertain(db)` applies the same judge to the stored `error`, which is the
"<Exception>: <label> <code>: <detail>" string the gate records. These are the HTTP status and
detail that the paid-refusals readback already classifies. It runs on the first scheduler
tick of a process and at app startup.

It skips:

- rows with `actual_cad` set;
- conflicting-outcome escalations;
- invalid-usage rows;
- any error that does not match.

A reclassified row reads `reclassified: never accepted (http_403) | <original>`. The function
is idempotent and runs under the budget lock.

## Tests

- `tests/test_backoff_cap.py`:
  - the cap for every cadence;
  - a ×32 park clamps on read and in the rows;
  - clamping on the boot tick, and the job is enqueued;
  - paid suspensions are untouched;
  - a hot 15-minute idle loop is still slowed, and stops at 4×;
  - a daily job is parked at most 6 h;
  - the image-capability wake;
  - a routine OK probe is not input;
  - the photo-review wake.
- `tests/test_flux_uncertain.py`:
  - the judge on the recorded strings;
  - end to end through `images.generate` with a scripted transport: 403, 401, 422, 429 and
    unreachable are RELEASED; a timeout, a 503 and a reset are UNCERTAIN; accepted-then-poll
    failures are BILLED and never released;
  - legacy rows are reclassified from the stored evidence;
  - reclassification on the boot tick.
- `tests/test_watchlist_cadence.py`: the production-magnitude test asserted ×32 and a park of
  eight periods, which is the defect. It now asserts ×4 within the cap.
- Existing fixtures that built a multi-day park and needed it to stand as a precondition:
  - `test_eng_improve` (3 tests) and `test_eng_learn_wiring` (1 test) now record the park
    within the cap: `since` is 3–4 h ago instead of days.
  - `test_eng_recovery` (6), `test_redrive_fire` (2) and `test_watchlist_cadence` (4) prove
    a lift (rearm, input probe, gate change) that is independent of the cap. They now run
    under a `_uncapped` decorator that restores the old 32× constants for that test only,
    so each lift is still proved on its own.

  No assertion about what lifts a park, or what keeps it, was weakened.

## Not done / not verified

- Not deployed. The production clamp and reclassification are verified only on fixtures that
  reproduce the stored rows' shape, not against the production database.
- `listing.package` and `visual.identity_drift` (×2) get the cap only. No new upstream probe
  was added for them.
