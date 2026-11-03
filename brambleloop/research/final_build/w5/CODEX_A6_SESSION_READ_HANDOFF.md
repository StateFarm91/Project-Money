# A6 caller-owned evidence reads — preliminary contract

Source: `codex/a6-fence-continuation` at
`77d2d415e27f401e75a09e3704ca8f5138daa84f`. The optional
`knowledge_gate.refusal(db, cir, session=...)` and
`design_knowledge.verify_pins(db, pins, session=...)` route nested database
reads through an already-active caller-owned transaction. The caller owns its
commit, rollback and closure. A session bound to a different database or no
active transaction is refused. Existing calls that omit the session retain
their prior behavior. A session with pending ORM edits is refused, without
discarding them, and cached ORM attributes are expired before reading. PostgreSQL
sessions require READ COMMITTED; a repeatable-read snapshot opened before a
fence may be stale. This check does not itself acquire a fence.

This is an interface preparation, **not a concurrency fix**. No production
handler uses it yet. Database changes by another transaction are not blocked;
the caller must first acquire a verified evidence fence, re-read evidence in
that same transaction, and perform the authority-bearing write before ending
it. Raw files and external effects need their own protections. Cross-version
design lineage, protected table coverage, real PostgreSQL interleavings and
independent review remain open. Do not integrate or use this alone to certify.

Python 3.11 focused tests: five session-read plus four existing freeze-history
cases passed on SQLite. The opt-in `test_codex_a6_session_reads_pg.py` also
passed against an empty disposable PostgreSQL 16 database: READ COMMITTED
refresh saw a concurrent committed retirement, and a pre-existing REPEATABLE
READ snapshot was refused. That narrow test does not test retirement *after*
verification, complete evidence coverage, or an authority-bearing handler.
