# Exact originating gap review

Source assessed: `e087dd4` (includes G2). Read-only investigation; no production source or requirement status changes. Local fake/in-memory SQLite only.

## Confirmed defect

`creative/intake.py::_gap_for` selects the **oldest** CoverageGap ID in the department, with no benchmark/arena/origin predicate. It does not select the latest gap. `advance_gap` can advance this unrelated row through certified/launched and overwrite its product_slug. Intake, re-gating and `intel/mission_runtime.py::advance_pipeline` all call this department-only selector.

The attached `origin_gap_repro.py` executes the exact AST function bodies of `_gap_for` and `advance_gap`, and the exact coverage module blob, at e087dd4. Core SQLAlchemy models/Database dependencies come from the integration checkout, not a claimed clean exact-head suite. A synthetic MjsMissionEvent records the legitimate origin shape (gap 2, benchmark-b, arena-b); this fixture is not a claim of executing the full mission producer. Calling the real advance function for product-b produces:

- gap 1 / benchmark-a: certified, product_slug product-b
- gap 2 / benchmark-b: uncovered, empty product_slug
- returned moves: concepting, engineering, certified; returned gap: 1

One deterministic counterexample passed. No heavy tests or external calls. This can falsely increase answered-gap coverage while leaving the actual gap unanswered. Missing-origin calls currently mutate a row instead of returning UNKNOWN.

## Real producer and consumer chain

`intel/observe.py` creates gap rows with coverage.upsert(benchmark_key, arena=pod.name, pod); its returned ID is discarded there. Multiple benchmark gaps in one pod are legitimate.

`intel/mission_runtime.py::process_listing` looks up CoverageGap by benchmark_key and pod, stores the ID in BOTH MjsMissionEvent.gap_id and steps.coverage.gap. It persists these fields around lines 990-1000. Its initial lookup itself is ambiguous if multiple arenas exist under one benchmark/pod, so repair must refuse ambiguity rather than assume event.arena equals coverage.arena (these currently describe different concepts).

`_enqueue_breakthrough` places mjs_event_id in the real creative.tournament inputs. `runtime/release.py::_winner_intake` forwards that event ID to creative.intake. Intake already persists mjs_event_id and copied brief source_context in its payload/audit. Thus a real originating ID can be recovered without choosing another pod gap. Existing source_context retention alone does not enforce identity.

Later `mission_runtime.advance_pipeline` has the same persisted event and stage evidence, but calls advance_gap(db, ev.pod, ...), ignoring ev.gap_id. Re-gating also omits origin. This is a source-level producer/consumer trace plus a directly executed selection counterexample, not full runtime certification.

## Proposed bounded repair (approval pending)

Own creative/intake.py origin resolution/advance/regate, intel/mission_runtime.py exact gap selection/persisted origin/advance_pipeline calls, and new focused tests. No core schema change appears necessary: CoverageGap identity fields and event/payload JSON already exist. Do not edit shared release handler or Build 2 statuses.

Bind an explicit origin snapshot (gap ID, benchmark, coverage arena, pod, source event ID and fingerprint) from the persisted mission producer into the intake brief/payload. Validate event provenance, candidate pod/topic binding and existing product binding before advancing. Refuse inconsistent caller source_context rather than replacing it silently. Candidate brief must retain exact origin through re-gating; generic non-mission candidates without a validated originating gap remain usable for their own pipeline but cannot advance coverage. Never infer oldest/latest. Mission advancement must verify the same event/winner origin rather than use pod alone. A conflicting product binding must refuse rather than overwrite. Missing/unverified origin returns UNKNOWN and performs no gap update. Existing low-level coverage.advance need not be weakened or bypassed.

Acceptance: two simultaneous same-pod gaps advance only the validated origin; absent origin, wrong event/benchmark/pod/coverage-arena/fingerprint, ambiguous producer selection, tampered brief source context and prior different product binding cause zero mutations. Correct real producer identity survives intake payload and re-gate. Later pipeline consumer uses exact origin; unknown evidence never certifies a gap. Include restart/persisted payload checks. No thresholds or requirement statuses changed.
