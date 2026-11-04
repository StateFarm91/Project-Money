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

## Gallery readiness run scope

An explicit production or controlled-run gallery previously fell back to any
candidate on the listing. A controlled experiment's candidate could thus appear
on a production run's owner card. The run-bound selection now requires the
stored run's product/version/full release, keeps controlled runs separate, and
permits matching unscoped owner uploads only in production. An unscoped
dashboard filters controlled runs and holds if its production candidates have
more than one or malformed product/release identity. Conflicting records, more
than 255 distinct identity/run/method combinations, and missing full release IDs cause conservative
holds; they are not silently combined.

An explicit unknown or mismatched run is also marked not ready with a named
blocker, even if some disclosed-render fallback entries can be displayed. The
separate no-run/no-candidate disclosed-gallery behavior is unchanged.

Gallery readiness now also requires the existing listing-set check to pass: a
plan whose only disclosed frame is a detail without a hero no longer reports
`gallery_ready=True` while `set_check.ok=False`. This corrects a status reading;
it does not authorize publication or create a listing-set certificate.

Python 3.11/file-backed SQLite: 82/82 V1, anchor, owner-image, stage-D and new
gallery tests. The independent reviewer reran the gallery cases 4/4. The
identity scan and later role reads remain separate transactions; metadata is
not authenticated and later writes can change the result. This is not an
action-time approval or publication fence. DO NOT INTEGRATE remains.

## Obscured blind craft readings

When the judge says fabric is not clearly visible, contradictory guesses about
craft, ribbing or edging now remain UNKNOWN rather than producing a definite
craft failure and a potentially futile paid repair. A clear mismatch still
fails, and independent deterministic image failures are unchanged. Since stage
D otherwise allows some UNKNOWN generation inputs, an explicit obscured-fabric
reading also holds that image as an edit base; legacy readings with the same
visibility field are covered. Other UNKNOWN readings without visibility evidence
retain the existing policy. This is not proof that a judge or any owner approval
is authentic.

The final Python 3.11 SQLite V1, anchor, gallery, owner-image and stage-D suite
passed 83/83. A separate reviewer reran the obscured and edit-base cases and
checked the legacy-visibility follow-up. No paid calls or deployment occurred.
