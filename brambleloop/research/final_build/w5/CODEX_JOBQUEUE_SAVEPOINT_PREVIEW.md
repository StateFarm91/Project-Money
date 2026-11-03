# Caller-owned queue transaction preview

Source: isolated Batch 6 safety preview at
`6cb70e3a90ab4cc84f3ecd73f4fca570e48c1859`.

`JobQueue.enqueue(..., session=...)` formerly rolled back the entire supplied
session after a duplicate-key insert race. A caller could lose its unrelated
release or authority writes while a higher-level handler caught `DuplicateJob`.
The session-owned path now uses a savepoint for the job insert, preserves the
outer transaction on a duplicate, and re-raises a nonduplicate integrity error.
The existing self-owned enqueue path is unchanged. Callers still own commit,
rollback and transaction retries; savepoint establishment may flush pending
ORM state, and failures before it require the caller to roll back normally.

For Python's standard `sqlite3` legacy transaction mode, the code starts a
physical transaction before the savepoint if the driver has not started one.
Without that step, releasing the outermost SQLite savepoint can commit a new
job despite a subsequent session rollback. Alternative SQLite drivers and
other isolation modes have not been certified.

Python 3.11 SQLite: three focused tests and three existing queue tests passed.
A forced real PostgreSQL 16 duplicate race also preserved caller writes in an
independent test; the persisted opt-in PostgreSQL test requires a new empty
disposable database via `BRAMBLELOOP_TEST_POSTGRES_URL`. This checkpoint does
not wire certification, install an authority fence, validate every queue
caller, or prove transaction retry and idempotency in every workflow.
