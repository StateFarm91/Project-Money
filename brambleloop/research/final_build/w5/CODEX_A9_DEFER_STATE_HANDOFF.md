# A9 owner deferral state — review only

Based on `codex/a9-parked-source-change` at
`2a6393ea1b2a09f3c5f470e35a48b2f5fbb70baa`. The real Command Center
`owner_action.defer` action previously returned `state=parked` for a request
already superseded, even though the database kept it closed. It also read the
request without the owner-queue lock used by package source invalidation.

The action now takes that lock before re-reading the row, refuses closed or
inconsistent raw states, parks only an open request, and treats a repeated park
as idempotent. The response reports the actual stored note and `changed` flag.
The action does not approve a listing, publish anything or change owner access.

Python 3.11 persistent SQLite: 45 A9/owner-queue cases passed, including four
focused real-handler cases and a forced source-writer/defer interleaving. The
opt-in PostgreSQL test requires loopback, explicit disposable confirmation and
an empty database; independent precommit testing passed 1/1 on local PostgreSQL
16, including a bounded assertion that deferral waits for the source writer.
The existing PostgreSQL lock-order,
direct/Core SQL and other evidence-writer gaps remain, as does action-time
unpark validation. This is not a full authorization or integration fence.
`app/command_center/approvals.py` is shared integration code and must be
reconciled with other owner-action changes; do not merge or deploy this branch.
