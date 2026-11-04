# Release-scoped quality cadence

Stacked on product identity re-verification PR #94 (`3b74e9a`). `quality_ops.next_work` previously keyed recent re-verification readings only by slug, version and check. Synthetic real Worker readings for an old release hash incorrectly made a newly recertified hash under the same slug/version look fresh for up to 24 hours.

The scheduler now requires all four checks' recent reading hashes to match the current certified release hash. Missing hashes, malformed audit objects and invalid check names do not establish freshness. Malformed historical audit objects no longer crash the quality sweep's unverifiable-report reader. An unknown reading still counts as a check having run, never as a passing safety verdict. Releases with no hash remain stale and can generate repeated work until repaired.

Real Worker tests use synthetic release records: run four checks for the old hash, change release identity, verify new work is offered, then run the new hash's four checks and verify freshness. Additional malformed/hashless audit data must not satisfy freshness or crash the quality sweep. No physical evidence, owner decision, purchase, publication or deployment is created.

This is scheduler correctness only. Audit `release_hash` is supplied by the job and is not independently authenticated or revalidated at the consequential write; concurrent release changes and false audit claims remain outside scope. PostgreSQL and production integration are not established.

Python 3.11 tmpfs SQLite quality/withholding regression passed 27/27; independent reviewer reran final Worker/malformed-audit cases 2/2. Existing department fixture was updated to include the release hash that scheduled jobs already carry; hashless readings no longer establish freshness.
