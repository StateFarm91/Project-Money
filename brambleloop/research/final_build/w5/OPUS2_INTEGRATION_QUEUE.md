# Batch 5 integration queue: Secondary (opus2) PRs

Owner: integrator (Main Opus). Target branch: `claude/w5-INTEG1`. Updated every check-in.
Last updated: 2026-11-02T03:35Z.

Rule: a head merges into W5-INTEG1 once an independent review has said SHIP (or ACCEPT) for it
and it is compatible. Accepted work is never held behind unrelated unfinished work.

| PR | Branch | Subject | In W5-INTEG1 | Pending head(s) | Review state | Next action |
|---|---|---|---|---|---|---|
| #3 | opus2/p0-revenue-workforce | P0 clusters 1-9 + title multiplicity (J-1) | up to 6d6d83d9's parent (all clusters merged; H1/I-1 fixes 558e7ca9, 6d6d83d9 and J-1 chain pending) | 558e7ca9, 6d6d83d9, 771e1e1a, c3074241, 6769e696 | OPUS2K: J-1 DO NOT SHIP; K-fixes 6769e696 under OPUS2M | merge the chain to 6769e696 on OPUS2M SHIP |
| #5 | opus2/p0-listing-package | automatic listing-package job | yes (be96a598) | none | accepted | done |
| #6 | opus2/p1-owner-queue-races | owner-queue race guard | yes (23935b58) | none | accepted | done |
| #7 | opus2/p1-culture-sweep-timeout | culture.sweep timeout dead letter | yes, to 3468fe73 (merged 03:29Z) | e0be7c4d (K-4 tests) | 3468fe73 ACCEPT (OPUS2K); e0be7c4d under OPUS2M | merge e0be7c4d on SHIP |
| #8 | opus2/p0-family-membership | culture-family membership | yes (d8d80301) | none | accepted | done |
| #9 | opus2/p0-cir-colourwork | per-stitch colour in the CIR | yes, to 424d69a9 (merged 03:29Z) | d4486b8c (K-5/K-6a) | 424d69a9 ACCEPT (OPUS2K), J-7 satisfied (J7B); d4486b8c under OPUS2M | merge d4486b8c on SHIP |
| #10 | opus2/p0-pet-bed | pet basket bed | no | 7d220e01 + pending OPUS2K-7 fix | DO NOT SHIP (OPUS2K-7 HIGH) | Secondary fixing; then delta review |
| #11 | opus2/p0-stocking | two-panel stocking | no | 563c0436, 0ef8a716 + pending OPUS2L fixes | DO NOT SHIP (OPUS2L-1 HIGH) | Secondary fixing; then delta review |

Not Secondary: #4 (reference only, do not merge), #12/#13 (review reports), #1 (Codex draft,
superseded), #2 (LAURAONE review). Codex owns P0-LEARNING-REFERENCE (`codex/p0-learning-reference`,
claim only, not started); no one else implements it.

## Certification path for Batch 5
1. OPUS2M verdicts merged (J-1 chain, K-4, K-5).
2. Pet bed + stocking after their delta review (or Batch 5 certifies without them, and they
   ride Batch 6, if they are not SHIP by the time 1 is done: they are not held, and they do
   not hold).
3. Affected regression suites on W5-INTEG1, one independent integration review of the
   W5-INTEG1 delta since 0967c3ee, then ONE uninterrupted full suite (REQUIRE_CLEAN=1).
4. deploy_guard record, DRY_RUN, rollback rehearsal, then owner approval of the exact SHA.
