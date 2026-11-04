# A9 listing-package scope — review only

Based on `codex/a9-defer-state-guard` at
`c0252f6fd92fdd670d191f732aec543cde7dd86b`. A partial or malformed
per-release `listing.package` job previously fell through to the global
six-hourly sweep. The actual Worker now records a named no-work refusal instead
of touching other releases.

The established manual empty input, scheduler input
`{"cadence": "listing_package"}`, and post-deploy retry with
`retry_for_commit` still dispatch a sweep. A complete slug/version event stays
scoped, including its release metadata. Unknown or misspelled no-scope inputs
are refused, not guessed. This changes no publication, spending or owner grant.

Python 3.11 persistent SQLite: 52/52 tests passed across real-Worker scope
cases, A9 owner/source regressions and targeted scheduler/ineligibility cases.
Tests mock the downstream dispatch functions for the scope decision; they
exercise the real durable Worker and persisted result/audit, not a full release
build. The A9 event suite passed on the parent checkpoint. PostgreSQL,
noncooperating source writers, action-time unpark and the shared evidence fence
remain separate open issues. Independent review is requested; do not integrate
this as a complete A9 fence.
