# A9 event release binding — review only

Based on `codex/a9-event-scope-validation` at
`ed915230d0bd47bc00071d460f0eebdd17fdafe6`. A targeted event already carries
the release hash from `launch.plan`, but the package handler formerly ignored
it and could assemble a different current release under the same slug/version.

For a nonempty event release, each assembled package must match that exact hash
before entering the existing locked recorder. A mismatch produces a named,
no-work refusal; after a record-time source race, the retry checks the event
hash again. Missing or empty legacy release values remain unbound. An ineligible
event can still conservatively reconcile/withdraw a stale review, so an old
event is not universally side-effect-free. Sweeps retain their prior behavior.

Python 3.11 persistent SQLite: 56/56 focused real-Worker event/scope, owner
fence/source and targeted scheduler/ineligibility tests passed. Independent
review reran 3/3 release-binding Worker tests. Those three patch assembly to
synthetic packages while exercising real recording and persistent state; they
do not prove a full live assembly. No owner approval, publication or spend is
granted by this change.

**Do not integrate as a complete A9 fence.** PostgreSQL interleavings, release
events without a hash, direct/Core SQL and other gallery/PDF/policy/physical
writers, action-time unpark, and post-commit evidence changes remain open.
