# A6 caller-owned evidence reads — preliminary contract

Source: `codex/a6-fence-continuation` at
`77d2d415e27f401e75a09e3704ca8f5138daa84f`. The optional
`knowledge_gate.refusal(db, cir, session=...)` and
`design_knowledge.verify_pins(db, pins, session=...)` route nested database
reads through an already-active caller-owned transaction. The caller owns its
commit, rollback and closure. A session bound to a different database or no
active transaction is refused. Existing calls that omit the session retain
their prior behavior. A session with pending ORM edits is refused, without
discarding them, and cached ORM attributes are expired before reading. Callers
must understand their database isolation level: a repeatable-read snapshot
opened before acquiring the fence may still contain stale data.

This is an interface preparation, **not a concurrency fix**. No production
handler uses it yet. Database changes by another transaction are not blocked;
the caller must first acquire a verified evidence fence, re-read evidence in
that same transaction, and perform the authority-bearing write before ending
it. Raw files and external effects need their own protections. Cross-version
design lineage, protected table coverage, real PostgreSQL interleavings and
independent review remain open. Do not integrate or use this alone to certify.
