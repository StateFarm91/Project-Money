# Batch 6 transaction retry — isolated review checkpoint

This narrow building block starts from `codex/batch6-safety-preview` at
`6cb70e3a90ab4cc84f3ecd73f4fca570e48c1859`. It does not install triggers,
activate itself, alter existing callers, or establish an evidence contract.

`core.evidence_transaction.run_db_transaction` reruns a DB-only callback in a
fresh session/transaction after bounded PostgreSQL 40P01, 40001 or 55P03
failures. A disconnect or unknown result is not retried. It guards ordinary
SQLAlchemy `Session.commit()` and `Connection.commit()` calls and detects a
callback ending the transaction. This is not a security boundary: a callback
can issue SQL COMMIT or use a raw driver, another session, or external I/O.
An error cannot prove rollback when a callback violates these requirements.
The trusted callback must not use raw connection commits, external effects, nested
commits, or suppress database errors. The session factory must return a fresh
session. Separate invocations still need durable idempotency; the helper does
not provide it. Callers must reread and reauthorize all evidence on each try.

Python 3.11: six persistent SQLite tests pass in
`brambleloop/tests/test_codex_evidence_transaction.py`; opt-in real disposable
PG16 deadlock and serialization retry scenarios pass 2/2 in
`brambleloop/tests/test_codex_evidence_transaction_pg.py`. Set
`BRAMBLELOOP_TEST_POSTGRES_URL` only to a disposable test database. These do not
prove application handler integration or durable idempotency.

DO NOT INTEGRATE as a complete contract: mutation coverage, DB-role protection,
evidence identity and authority, external side effects and integration with real
workers remain unproven. A global epoch/statement-trigger prototype protects
against direct SQL mutations only when trigger coverage and privileges hold;
real PostgreSQL tests demonstrated reverse-lock-order deadlocks and require full
transaction retry. Application call paths do not yet all use this helper.
