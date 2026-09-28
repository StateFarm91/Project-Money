# Exact coverage origin handoff

Base: 8e2dbf3. Branch: codex/final-origin-gap-01. Scoped changes only; no requirement status changes or certification claim.

## Implementation and runtime trace

`mission_runtime.coverage_target` selects a unique benchmark+pod gap or returns no target. Multiple matching arenas are ambiguous; no oldest/latest inference. The existing process_listing producer stores gap ID, benchmark, coverage arena, pod, event ID and content fingerprint in event.steps.coverage.origin, alongside event.gap_id. Mission arena remains separate.

Existing tournament enqueue carries mjs_event_id. Actual creative.intake verifies the event's tournament job matches the current job, candidate pod matches event/gap, and producer snapshot matches current gap identity. It binds candidate original key and product slug in brief.source_context.coverage_origin, preserving other G2 source fields. Conflicting supplied origin is withheld. This exact brief reaches the audited payload and cir.draft queue.

`advance_gap` requires the caller's event and candidate key as well as the full origin. It verifies exact event/gap/product identities and refuses missing, altered or contradictory provenance with UNKNOWN and no gap mutation. The update is conditional on prior state/product identity; PostgreSQL row locking is requested, and the conditional write also prevents silent binding overwrite where SQLite ignores FOR UPDATE. Lifecycle transition rules are unchanged.

Re-gating uses the persisted brief origin and original key. `advance_pipeline` reads the persisted winner intake and passes its origin plus the current event ID, rather than choosing by pod. Existing different product bindings are never overwritten. No generic non-mission candidate is guessed to answer a coverage gap.

## Local validation

- 7/7 new test_exact_coverage_origin.py tests pass.
- 13/13 existing test_response.py checks pass.
- git diff --check passes.
- Interpreter: bundled Codex Python; runtime-build2 inserted on sys.path. Local in-memory SQLite only.

Controls include two same-pod gaps; intended gap alone advances. The integration control executes the actual producer helper, intake, queued payload, persisted AuditLog winner reader and advance_pipeline consumer. Unrelated creative gates and later stage success are explicitly mocked premises; this proves origin routing, NOT actual creative or release certification. Negative cases cover every snapshot field, missing origin, wrong event/candidate/job, ambiguous producer selection, changed event fingerprint and conflicting product binding. Tests do not weaken any existing assertions.

## Limits and integration warnings

Legacy events without producer snapshots remain UNKNOWN. Do not backfill origins by selecting a nearby gap. A tournament worker racing before process_listing persists its final event also remains UNKNOWN; no automatic mutation retry was added. Existing events with already-wrong product bindings require deliberate reconciliation, not overwrite. No full mission suite or heavy cert_wiring run here; coordinator should run affected suites on the integrated final source. No PostgreSQL or multi-process concurrency execution claimed. Snapshot identity verifies lineage and candidate department/job, not a new semantic judge proving the design answers the market gap.

No paid APIs, external calls, deployment, production mutations, Visual changes, status promotion or threshold changes.
