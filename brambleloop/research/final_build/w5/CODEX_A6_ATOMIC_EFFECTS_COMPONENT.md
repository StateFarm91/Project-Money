# A6 atomic release effects — isolated component

Based on `codex/a6-release-transaction-preview` at
`67b7b73899f91d250a11febf63446a198e425ae5`, plus the tested queue savepoint
change from `ee32f68f05ae0a697b37c52cbb76114694ab965f`.

Optional `_persist_release(..., session=s, atomic_effects=True)` persists the
release, provenance, `gate.recertified` audit, quality follow-on job and its
causal JobLink in one caller transaction. It checks a locked persisted running
certification-job lease, actor, worker and CIR; checks the certificate's grant,
slug, version and recomputed content hash; holds same-hash ambiguity; and holds
an existing follow-on key instead of assuming it denotes a fresh verification.
Missing JobLink schema is a refusal, not an invitation to create tables inside
the transaction. A savepoint prevents caught failures committing a partial
release; the caller must still commit or roll back the outer transaction.

This is **not an authenticated certificate, a knowledge evidence fence, or a
complete certification transaction**. No production handler calls this mode.
The helper does not authenticate whether the supplied certificate was actually
issued by the gate; field/hash consistency alone is insufficient. It checks the
worker lease during the helper, but an outer caller can delay commit past lease
expiry. `gate.certified`, duplicate-certification handling and other follow-on
actions are not part of this transaction. Retired rules and licence changes can
still race existing handlers. Learning authority needs an independently anchored
grant and complete source coverage; existing customer delivery has separate
requirements. No provider, purchase, publication or deployment was performed.

Python 3.11 focused SQLite run: 19 passed, one opt-in PostgreSQL test skipped.
That run covers the new component, its prior transaction preview, queue
savepoint tests and the legacy withholding regression. The PostgreSQL test
requires an empty disposable database via `BRAMBLELOOP_TEST_POSTGRES_URL`.
