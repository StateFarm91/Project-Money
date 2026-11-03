# V1 visual correctness continuation

Branch `codex/v1-visual-correctness` starts at Main's
`claude/w5-V1-visual-correctness` `f349c755a17d3792241249a49d0884262c8fd60b`.
The original branch is unchanged. The V1 base tests and `test_w4_visnext` passed
10/10 and 21/21 respectively before this delta; no paid provider was called.

The old `pattern_refs._ribbing` identified ribbing whenever front- and back-post
stitches appeared anywhere, including a real, compiled flat CIR with one front-post
row and one back-post row separated by 19 plain rows. This omitted the prompt's
`ribbing anywhere` prohibition even though there was no repeating rib pattern.
The continuation proves a post-stitch rib only from repeated alternating,
aligned front/back runs on nearby non-fold rows. Other post layouts are UNKNOWN,
not a claim that ribbing is absent. Unknown does not inject a false "no ribbing"
prompt, and the actual craft-fidelity check returns UNKNOWN and holds rather than
passing. Tests exercise real compiled CIRs, the prompt and fidelity comparison,
including isolated posts, separated blocks, shifted columns, fold rows, sparse
loop-only stitches and the existing genuinely ribbed scarf. Python 3.11: V1 15/15,
targeted fidelity UNKNOWN/FAIL checks, FLUX texture 9/9 and rim negative 2/2 passed.
The full fidelity suite was interrupted for a reviewer-requested fix; it has not
been claimed as passed. The reference version advances to
`pattern-refs/3.1.2` so changed references are identifiable. This conservative
reader does not prove other valid ribbing geometries; independent review is
required. No image or physical fidelity claim is established.

The parent V1 handoff already says its Cloudline experiment definition changed and
requires fresh owner authorization. This continuation does not authorize it.
Independent review, integration and production verification are still required.

Review follow-up: a ribbed design cannot PASS craft fidelity when ribbing is
reported absent (FAIL) or unclear (UNKNOWN). Component-level evidence is now
aggregated conservatively: mixed/unknown pieces remain UNKNOWN and cannot cause
a global "no ribbing" claim. Real-CIR small-ribbed-component and actual blind
reading tests pass. V1 focused suite: 17/17 on Python 3.11. Independent review
and the full fidelity regression remain open; this checkpoint is not accepted.

The expected-ribbing check also leaves an obscured/unclear fabric view UNKNOWN:
only a clear reading can establish that required ribbing is absent. Independent
scoped review confirmed this distinction; the V1 suite passed 17/17 afterwards.
