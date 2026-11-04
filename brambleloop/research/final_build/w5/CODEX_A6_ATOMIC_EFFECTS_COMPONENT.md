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
An independent PostgreSQL 16 run on a precommit tree based on `11f29b6`
passed the opt-in test (1/1) and the 12-case atomic-effects suite adapted only
to use fresh PostgreSQL fixtures (12/12). The exact precommit tree has not
been independently matched to the final commit, so those runs are not claimed
as verification of the final SHA. An independent reviewer reran the 12-case
suite on SQLite at code commit `9d3172aa4327409f49d2298ecf3e0698eae582fa`
and confirmed its narrow behavior, not the full authority contract.

## Why the handler remains unwired

The existing owner step-up action calls `review_rule` with a hardcoded owner
identity, but the underlying service accepts a string and its Learning approval
audit is not a signed Learning grant. There is no implemented Learning-specific
grant binding the rule, evaluation and source provenance to an independently
protected current-revocation anchor. The existing generic sealed chain documents
tail truncation and uses separate sessions for append/refusal. Configuring the
storefront signing key alone does not create an approved Learning authority model
or make current revocation trustworthy. The model and anchoring approach need
owner approval, implementation and independent review; exact infrastructure
configuration depends on that design. Existing unsigned approvals must not be
silently converted into new authority.

The decision must specify who may approve and revoke Learning rules, what
independence and step-up are required, the exact rule/evaluation/source digests
and validity period each grant binds, how legacy approvals are handled, and
where the current revocation/chain head is anchored outside the authority
database. Once approved, the implementation needs an owner-only signer, a
worker-only verifier, protected anchor access and explicit fail-closed behavior
when the anchor or key is unavailable. No specific dashboard setting can be
named until that design and infrastructure are selected.

Separately, every protected evidence writer and every consequential certification
and delivery path needs a shared action-time transaction fence. The actual
handler still has its early duplicate return, separate granted audit and release
write, and post-certification consumption gaps. The helper's bounded transaction
is not a substitute. A wiring change before those requirements are met would
leave known races, so this branch leaves the handler unchanged.
