# A3 excluded-supplement gallery gap — review only

Based on `codex/a3-fencing-followup` at
`c888769bb0a0003f97701c589a751052f90fb630` (the existing A3 partial-fence
continuation). Source branches are unchanged.

An independently approved supplement whose owner photo attestation was later
removed became nonqualifying, but its exclusion left effective gallery
positions `[1, 3, 4, 5]`. The candidate parks excluded frames after included
frames within the photo review transaction, preserving approval and hold
fields. It only rearranges a previously contiguous complete ordering with a
sole position-one leader that is an approved, unheld physical photograph.
It takes NOWAIT row locks on existing gallery frames and referenced photo rows;
unavailable/malformed state is held. The existing review path invalidates
listing-set certificates in the same transaction.

This is **not** a complete concurrency fence or authority approval. PostgreSQL
phantom inserts, noncooperating writers, other evidence sources, bytes and
post-commit changes remain open; lock ordering still requires combined review.
No owner veto is cleared, physical proof fabricated, listing published or
production modified. Do not integrate until those independent blockers close.

Python 3.11 persistent SQLite: full photo review and photo-first regression
with the three new focused cases passed 40/40 before the final large-gallery
guard; the three focused tests passed again after that guard. The focused tests
cover repeated sweeps, held/malformed leaders and preserved vetoes; separate
review independently reran 3/3 prior to the idempotency assertion. PostgreSQL
concurrency remains untested for this delta.
