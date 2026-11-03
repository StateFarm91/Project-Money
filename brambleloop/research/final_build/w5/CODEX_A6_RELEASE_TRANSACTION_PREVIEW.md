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

## Containment experiment rejected

An uncommitted experiment made the existing `knowledge_gate.refusal` always
hold, including for a baseline design with no visible Learning history. Two
Python 3.11, persistent-SQLite tests exercised actual certification, asset,
visual and draft/activation release checks: the checked paths held as intended.
The unchanged Learning acceptance test
`test_approved_knowledge_is_frozen_into_the_draft_and_every_boundary_reverifies_it`
failed because it expects an approved pinned design to pass. No assertion was
altered. This approach stops baseline certification and does not meet Learning
acceptance.

Independent review identified alternate customer delivery paths in
`commerce/deliverables.py`: `render_certified_pdfs` can render from a certified
CIR, and `resolve_pdf` may return stored bytes without the knowledge check.
The experiment therefore was not a universal boundary either. It was discarded;
the test-only changes and blanket refusal are not in this branch. Existing
customer-delivery behavior was not changed. A safe solution needs authenticated
lineage and action-time evidence fencing with an independently reviewed design
for every affected consumer, including obligations to existing customers.
