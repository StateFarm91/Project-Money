# V1 stage-D edit-base truth — review required

`codex/v1-variant-base` continues `codex/v1-anchor-binding` at
`b9eb3e32fcf5cd0d96b9330790e431c1115ab063`. Source branches remain unchanged.

The original stage-D contract permits a lifestyle image as a variant-generation
input when no check has FAILED and the owner has not rejected it. The previous
selection looked only at the aggregate `technical_status` and an individual
row's owner flag. An inconsistent stored failure or a duplicate row for vetoed
bytes could therefore be reused. The continuation checks top-level and nested
fidelity failures, explicit rejection and all same-product/version duplicate
image vetoes. The selection binds to the current run's slug, version and full
release and checks retrieved bytes. A genuine UNKNOWN with no failed check
remains allowed as the documented generation input; it does not become a PASS
or publication approval.

Python 3.11, file-backed SQLite: 78/78 across the new edit-base test, anchor,
V1, owner-image and existing stage-D tests. The reviewer independently reran
the new case and found an initial identity omission that was corrected. No paid
provider, production data or physical evidence was used.

**DO NOT INTEGRATE:** this is ordinary database consistency, not authentication
of the stored verdict, negative decisions, or run metadata. Candidate selection,
negative decisions and artifact reads occur in separate transactions; a writer
can change them after the check. The underlying V1 branch remains blocked on
inherited regressions, explicit experiment authorization and the shared evidence
contract. When unavailable, the edit base is omitted; this does not certify or
publish the generated variant.
