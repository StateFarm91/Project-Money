# A6 release persistence transaction preview

Source: `codex/a6-session-verification` at
`529978d5629a0f7a70b3fd818770024e576e7a51`. `_persist_release` optionally
accepts an active session bound to the same database. In that mode it does not
commit, enqueue work or write through `ctx.audit`; it returns recertification
enqueue/audit intents to the caller. The default legacy path is unchanged.

This is **not an installed authority fence, not a durable outbox, and not a
complete certification transaction**. An in-memory intent can be lost after
commit; a caller must discard it after rollback. The existing `gate.certify`
handler still checks knowledge and records a granted audit outside this
transaction, and the duplicate path can return a grant independently. No
handler uses this optional interface. Never treat it as proof that a retired
rule cannot race certification or that downstream artefacts stay valid.

The eventual implementation must validate an authenticated current CIR and
all required evidence under a verified shared fence, atomically persist the
certificate, authority audit, and durable work intents, and resolve existing
lock-order, retry, cross-version lineage and source-coverage findings. Real
PostgreSQL interleaving and independent review are required.
