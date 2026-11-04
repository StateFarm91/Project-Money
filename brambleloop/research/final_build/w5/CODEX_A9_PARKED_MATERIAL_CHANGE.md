# A9 parked review and material source changes — review only

Based on `codex/a9-owner-action-fencing` at
`e1974a6dae46e49099a8b56d32b3b8c2c8a3198f`. A parked owner review previously
remained parked after a committed ORM edit changed its listing copy or design,
even though recording a changed ready package supersedes the earlier question.

This continuation supersedes the parked old question for a proven persisted
listing/design/identity change within the existing owner-queue transaction.
It compares stored values, so assigning an unchanged deferred field does not
disturb an owner decision. Temporary uncertification or source disappearance
retains the parked decision. READY packages record a listing-only material
digest; a replacement listing supersedes only when that digest establishes a
material change. Legacy or missing digests retain the park and blocked package
until reassembly can establish the current question. Temporary certificate and
listing-status differences do not count as changed copy. No approval is created.

For a READY reassembly, the durable rendered owner-document hash identifies the
owner's question independently of the internal source snapshot. An identical
document preserves a single parked decision; a different document supersedes
it. A missing or ambiguous legacy question identity stays blocked and parked
instead of inferring an answer. These hashes reside in the mutable application
database and are not independently authenticated evidence or owner authority.

Python 3.11 persistent SQLite: focused parked-decision cases plus the existing
owner-fence and source-binding suites passed 31/31. These tests exercise actual
database transactions, owner-action lifecycle and the package recorder; their
synthetic READY fixtures are not publication-eligibility evidence.

**Do not integrate as a complete evidence fence.** SQL bulk updates and other
gallery/PDF/policy/physical writers still bypass the existing ORM listener;
PostgreSQL and shared lock-order/retry coverage remain open. In particular,
owner action unpark/action-time revalidation while a package is blocked remains
unresolved. The wider A9 and A1 blockers remain. No owner grant, Etsy listing,
purchase, paid provider or production state was changed.
