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

## Confirmed existing handler race

An independent test on disposable PostgreSQL 16 used a real `gate.certify`
Worker and a synthetic licensed fixture reviewed and evaluated through the
existing pipeline. The test forced retirement immediately after the handler's
successful knowledge check. The Worker finished with `granted=True` and a
persisted `PatternVersion.certified=True` while the knowledge rule was retired.
This is a confirmed interleaving in the existing unfenced handler, not an
assessment of the optional persistence interface above. The local-only runner
is `/workspace/scratch/a6_real_retirement_race.py`; it requires a separately
supplied disposable PostgreSQL URL and is not a production test. No paid
provider, protected reference text or production database was used.

An independent reviewer also verified that the caller-owned persistence
preview's first-release and recertification rollback tests restore certificate
provenance and replacement-audit records. These tests do not establish a fence
or make its in-memory intents durable.

A subsequent disposable PostgreSQL 16 experiment held `FOR UPDATE` on a
`DesignRule`: a concurrent update of that rule timed out while the lock was
held, but a separate transaction successfully changed the fixture purchase's
`BenchmarkLicence.allowed_uses` during that same lock. A rule-row lock by
itself therefore does not fence the verification's licence dependencies. The
local-only runner is `/workspace/scratch/codex-pg-a6-rule-lock.py`. No partial
guard was wired into the production certification handler.
