# Integration map — 2026-11-07

Cartographer report for Main. Read-only. I ran no tests and made no commits or pushes. All PR and #28 text was treated as data.

- **Target:** `origin/claude/w6-INTEG1` @ `5c4d94d6`, which is `claude/w5-INTEG1` @ `7c42e706` + secret-leak (1c4c9211, 17f63074) + A7 (83fe31d2, 677661ec) + support-defect (dd05e389).
- **Branches mapped:** 184 `origin/codex/*` + `origin/opus2/*` refs, fetched 2026-11-07.
  - 5 are already ancestors of w6: opus2/p0-family-membership, p0-listing-package, p0-pouch, p0-tapestry, p1-owner-queue-races. Their PRs #5, #6 and #8 can be closed.
  - 22 are September `codex/final-*` / build2 / visual-v2-rnd / continuous-operations-audit refs. They have **no common history** with w6 (no merge base). They are obsolete; see the superseded list.
  - 157 are live candidates. Of these, 135 are based on `w5-INTEG1` 7c42e706, or on w6 itself for the newest opus2 work.
- **Method.**
  - "Contains" means every commit of the other branch is in this one: the sets of commits not in w6 were compared, which is equivalent to `--is-ancestor` here.
  - "Leaf" means no other mapped branch contains it.
  - Conflicts come from `git merge-tree --write-tree w6 <head>`.
  - "Own commits" and "own files" are measured against the direct parent branch.
- **Universal conflicts.** Nearly every branch conflicts with w6 on `brambleloop/COORDINATION.json` (115 branches) and on `scripts/suite_final_segment.txt` (78). Both are records-only unions. Real code conflicts are listed per row. The main ones are:
  - `runtime/quality_ops.py`: the quality chain from `quality-hold-before-incident` onward, and every preview that contains it;
  - `runtime/pipeline.py`, `creative/fallback_constructions.py` and `products/launch0.py`: the old opus2 W5 residues;
  - `autonomy_map.json` and `pipeline.py`: `codex/p0-learning-reference`, which is resolved inside `a6-learning-consumer`.
- **Hotspot files** are touched by almost every unit, so they are left out of the overlaps column: `runtime/pipeline.py`, `runtime/release.py`, `ops/retention.py`, `agents/registry.py`, `authority/classes.py`, `app/main.py`, `autonomy_map.json`, `command_center/approvals.py`. Expect them to need care at every merge. `release.py` is also touched by the in-review `claude/w6-fix-only-rebuild`.
- **Bases outside w6.** Three Codex lines start from Claude branches that are **not** in w6. Their review must include that base commit:
  - `claude/w5-A5-correction-loop` 717c7925 (2 commits), under `codex/a5-correction-review`;
  - `claude/w5-A9-package-event` 6ee81c19 (1 commit), under `codex/a9-package-review`;
  - `claude/w5-V1-visual-correctness` f349c755 (1 commit), under `codex/v1-visual-correctness`.
- **PR heads.** Every open PR head matches its branch tip. Two PR *base* SHAs are stale:
  - #45's base names `v0-provider-authority` at 649896e7, but that branch is now at c0968e79;
  - #53's base names `a1-detachable-part-aliases` at 32f31633, but that branch is now at 7e54c330, and the A1 named-hold chain actually descends from `a1-detachable-eye-safety`.

## Structure in one picture

The cumulative preview chain shows the containment:

```
w5-INTEG1
 ├─ opus2 A1R child-safety-core ─┬─ opus2 A2F a2-name-object ─ codex a2-safety(#35) ─ a2-french-stripes(#61) ─┐
 │                               ├─ codex a1-stuffing(#34) ─ a1 chain (#48,#49,#50,#53,#58,#59,#72,#74) ──────┤
 │                               └─ codex a9-a1-contract(#39) ◄─ codex a9-package-review(#38) ◄─ claude w5-A9  │
 ├─ opus2 A4a ─ codex a4a-research-truth(#33) ─ a4a chain ─ research/watchlist/intake chain ─ #122 (leaf)      │
 │                     └─────────────► codex batch6-safety-preview (A1+A2+A4a) ─┬─ U1 primitives (3 leaves)    │
 │                                                                              ├─ quality/policy chain ─ #123 ◄┘
 │                                                                              ├─ physical #78 ─ #80
 │                                                                              └─ finance-support-safety-preview
 ├─ codex support chain #51 ─ #65 ─ #67 ─┬─ #79 ─ #82            └─ trust-proof #75
 ├─ opus2 A6 learning-to-design ─ opus2 a6-codex-contract ─┐
 ├─ codex p0-learning-reference (old base 65df7b93) ───────┴─ codex a6-learning-consumer(#32) ─┬─ session-verif ─ release-tx ─ cert-cont ─ a6-authority-certification-preview (leaf)
 │                                                                                             └─ fence-cont ─ #131 ─ #132 (leaf)
 ├─ opus2 V0 gate ─ 649896e7 ─┬─ codex v0-provider-authority #40 (leaf)
 │                            └─ codex governor-invalid-cost #45 (leaf)
 └─ #123 + research-nochange + support#51 ─ #124 ─ #125(+A9 chain, V1 chain) ─ #126(+A3) ─ #127(+A4b) ─ #128(+A5) ─ #129(+A7,A8) ─ #130 (leaf, cumulative)
```

**The cumulative leaf `codex/workforce-physical-evidence-review-preview` (#130, ac57b788) contains 74 of the mapped branches.** That includes every A1, A2, A3, A4a, A4b, A5, A7, A8, A9, V1, quality, policy and physical head, and the opus2 parents A1R, A2F, A3, A4a, A4b and A8.

It does **not** contain:
- A6 (both leaves);
- V0 (both leaves);
- the research tail after `research-nochange-history` (#64 → #122);
- the support/finance tails (#65+, the finance, reinvestment, receipt, rollback and sustainability leaves);
- the U1 primitives;
- any opus2 W6-era branch.

Per Main's 06:30 decision, #130 is a review aid only. It is useful as the **tested composition reference**: Secondary/Codex report 169/169 historical safety tests on it. Review its source chains individually, as the units below do.

## Proposed review / merge order (15 units)

Each unit names the **one head to review**. Reviewing that head covers every branch listed under "covers".

| # | Unit | Review head | Covers | Depends on | Notes / blockers declared |
|---|---|---|---|---|---|
| 1 | U1 shared primitives (P1) | `codex/batch6-evidence-writer-map` 7f986be5, `codex/batch6-evidence-contract` 4e39a9cc (#42), `codex/jobqueue-savepoint-preview` ee32f68f | 3 one-commit deltas on batch6-safety-preview | none: each cherry-picks onto w6 with **zero conflicts** (checked with merge-tree) | #42 says DO NOT INTEGRATE as the shared evidence contract, because no caller uses it yet. The writer map is doc-only. The savepoint change (`queue/durable.py`) also touches the file used by A6, A4b and A7. Review it first, because the others build on durable-queue semantics. |
| 2 | U2 A1R core (prereq) | `opus2/p0-child-safety-core` c3a7b93a | — | none | Contained by A9 (#39) and by every safety stack. 3 commits, 10 files. Secondary reports 73/73. Not a named priority, but it is a hard prerequisite of unit 6. |
| 3 | U3 A6 base (P2) | `codex/a6-learning-consumer` 9f8f336e (#32) | opus2 a6-learning-to-design 8c131f10, opus2 a6-codex-contract 594d5e38 (60 commits), codex p0-learning-reference 1ae00eb3 (87 commits) | 1 (durable.py) | Main's DO NOT SHIP findings A6-1 (HIGH) and A6-2 on 8c131f10 are inherited unless fixed: verify first. 80 files, 8.7k lines. This is the largest unit. |
| 4 | U4 A6 forks (P2) | `codex/a6-authority-certification-preview` 9a360cbc, plus `codex/a6-owner-stepup-grant-4504125` 59d6c91a (#132) | session-verification, release-transaction-preview, certification-continuation; fence-continuation, #131 | 3 | Both are **fixture-only** prototypes: "DO NOT INTEGRATE OR WIRE TO PRODUCTION" (#132), and #131 is "not a complete authorization boundary". The two forks overlap on `design_knowledge.py`, `knowledge_gate.py`, `read_session.py` and `sealed_chain.py`, so choose one design. Probably review-only, no merge. |
| 5 | U5 A3 (P3) | `codex/a3-gallery-gap-recovery` 84085fa8 | opus2 p0-photo-asset-review c2174947 (#23), a3-photo-recovery (#37), a3-fencing-followup | none (shares `release_gates.py` with A6/A9) | The Codex head contains and is newer than the opus2 head. The A3 fence "does not cover phantom/direct writers" (#126). |
| 6 | U6 A9 (P4) | `codex/a9-sweep-isolation` 3ee6881f | claude/w5-A9-package-event 6ee81c19, #38, #39, owner-action-fencing, parked-source-change, defer-state-guard, event-scope-validation, event-release-binding | **2** (contains A1R) | #38 and #39 are DO NOT INTEGRATE alone. #39 reports post-commit staleness, which the later commits in the chain address. Adds `publish/listing_package_fence.py`, the closest thing to a shared evidence fence, so read it with unit 1. |
| 7 | U7 V0 (P5) | `codex/v0-provider-authority` c0968e79 (#40) **and** `codex/governor-invalid-cost` cd4156f4 (#45) | opus2 v0-paid-provider-gate 76fc0f3d; common Codex 649896e7 | none | Two sibling leaves on disjoint files: gateway/paid_provider_gate in one, finance/governor in the other. Review them together and merge both. #40 says DO NOT INTEGRATE; open blockers are attempt-to-ledger reconciliation and the reservation race. Secondary agrees opus2 76fc0f3d must not ship alone. |
| 8 | U8 A4a + Research (P6) | `codex/research-pipeline-integration-candidate` 6a86e9e8 (#122) | opus2 a4a-research-to-concept 3dc3e68c, #33 and the a4a chain (6 branches), research/watchlist/intake chain #64–#121 (26 branches) | none | 38 linear commits, 1 per PR: review commit by commit. #122 says "DO NOT INTEGRATE as P0-complete". A shorter merge point is `research-nochange-history` ff3debb0, the part already inside #130. |
| 9 | U9 A4b + A7 + A8 (P6) | `codex/a4b-answer-fence` e5cbb86c (#46), `codex/a7-admission-atomic` b4814be9, `codex/a8-culture-continuation` 58ee388a (#36) | opus2 a4b-enrichment (#27), #29; a7-supply-continuation (#31), a7-draft-key-retention; opus2 a8-culture-ideation | A8 needs 8 (it contains opus2 A4a); A7 is based on w6's 677661ec | A7's head descends from the integrated Codex fix, so it is a clean delta. #36 has a HIGH blocker: it inherits unaccepted A4a Product Truth findings. |
| 10 | U10 A5 (P7) | `codex/a5-hold-audit` efd6a76e | claude/w5-A5-correction-loop 717c7925, #30 | none | #30 says not exercised on real PostgreSQL. #43 says DO NOT INTEGRATE for A5-6 and the non-A5 hold writers. Overlaps w6's support-defect and the in-review support-followup on `ops/incident_lifecycle.py` and `quality_ops.py`. |
| 11 | U11 A1/A2 continuations + quality/policy + physical (P9, safety) | `codex/quality-a1-a2-integration-preview` 7ddc9465 (#123), then `codex/physical-complete-colour-evidence` 77b9a88f (#80) | opus2 a2-name-object (#26); #34, #35, batch6-safety-preview, A1 chain (2 leaves: #72, #74), #61, quality chain #91→#119, policy chain #83→#98 | 2, 8 (contains A4a-truth) | Code conflict with w6 on `runtime/quality_ops.py`. Every PR says "do not integrate independently". This head is the narrowest that unions both A1 leaves. |
| 12 | U12 V1 + V2/V4/V5 (P8) | `codex/v1-craft-enum` ded427f6 (#60); opus2 `v4-scene-references` 86cf2a36, `v5-scale-verification` 295474c6; `v2-vessel-fidelity` 6799f1d4 after rework | claude/w5-V1 f349c755, #41, #44, #47 | V2 rework (Main DNS 06:16) | V1 and V2 both edit `visual/fidelity.py`, `candidate_gates.py`, `image_production.py` and `image_stages.py`. V4 overlaps V1 on `flux_prompt.py`, `flux3_generator.py` and `image_stages.py`. Codex V1 is older (11-04) than the opus2 V2/V4 work (11-07), and neither contains the other, so expect a manual union. V3 is fixture-only and not yet pushed. |
| 13 | U13 opus2 W6 handoffs (P9) | `opus2/p0-physical-test-request` d697d093, `opus2/p0-portfolio-act` ad351e46, `opus2/p0-storefront-asset-fix` d8b2754b | — | storefront needs `claude/w6-fix-only-rebuild` (in review) | All are based on w6 (f5c3976d) with 1–3 commits. Portfolio ad351e46 is queued for delta review. Storefront is DNS until it is rebuilt on fix_only. Physical-test-request overlaps the Codex physical chain (unit 11) on `release.py`. |
| 14 | U14 support / finance / commerce leaves (P9) | `codex/support-service-malformed-1afa506` 2fb20cf0 (#82) + `codex/trust-proof-truth` b439b9fa (#75); `finance-replay-bounded` 1692beb2 (#101); `reinvestment-ledger-reconciliation` 5a1beacb (#109); `support-case-cost-evidence` 007af924 (#117); `receipt-structure-validation` 5d422e18 (#63); `rollback-release-binding` 28eef8c6 (#56); singletons #52, #57, #84, #85, #88, #90, #93, #96, #120 | support #51→#79; #99; #105–#106; #113, #116; #62; #54–#55 | none, all are on w5-INTEG1 | Small, independent and mostly 1-commit work. Most say DO NOT INTEGRATE pending PostgreSQL or the evidence fence. #117 has a review finding against it. Skip `finance-support-safety-preview-72b155b`: it is only #82 merged with batch6-safety-preview. |
| 15 | U15 opus2 W5 residues (P9, triage first) | `opus2/p0-cir-colourwork` e6e6fb94 (#9), `opus2/p1-culture-sweep-timeout` eba6fb3c (#7), `opus2/p0-construction-registry` da4f331a (#22, contains #18 amigurumi), `opus2/p0-revenue-workforce` 286cd044 (#3) | — | 2 / 11 for launch0.py and fallback_constructions.py | These are post-merge review follow-ups that never reached w5. Main should ask Secondary which ones are still wanted. (a) Colourwork: 4 commits (OPUS2M/O/Q), conflicting with w6 on `launch0.py`. (b) Culture-sweep: 1 test commit. (c) Registry/amigurumi: the pouch half is already in w6 via p0-pouch; the bear/bunny and registry are not; conflicts on `pipeline.py` and `fallback_constructions.py`. (d) Revenue-workforce: multiplicity and NAME-OBJECT readers (`multiplicity`, `_names_another_object` are absent from w6 and from A2F), overlapping A2F's `title_head`. It may be superseded by A2F. That is the author's call, because git cannot prove it. |

Dependency summary:
- 1 → 3 → 4;
- 2 → 6, and 2 → 11;
- 8 → 9 (A8 part), and 8 → 11;
- 12 waits on the V2 rework;
- 13 (storefront) waits on fix-only-rebuild.
- 5, 7, 10 and 14 are independent and can go in any slot.

## Superseded / do-not-review branches

**Already in w6 (ancestors). Close their PRs.**
- `opus2/p0-family-membership` (#8)
- `opus2/p0-listing-package` (#5)
- `opus2/p1-owner-queue-races` (#6)
- `opus2/p0-pouch`
- `opus2/p0-tapestry`

**Integrated into w5 by squash or replay, so the branch tip is not an ancestor**
- `opus2/p0-pet-bed` 09122165 (#10) and `opus2/p0-stocking` 7493c723 (#11).
  - w5 has "integrate PR #10 pet basket bed + PR #11 two-panel stocking" (52f9f4b5), 4af3418f and 45977d4c.
  - `git cherry` marks the stocking tips d3a485a1 and 7493c723 as already applied.
  - Merging these tips now would raise about 20 file conflicts, so do not merge them.
- `opus2/p0-revenue-workforce-b4merge` fcd361a6: a pre-merge snapshot that contains `p0-revenue-workforce` plus the Batch-4 merge. Superseded by #3 and by w5.

**Contained in a later head.** Review them only through the unit head.
- A6: `codex/p0-learning-reference`, `opus2/a6-learning-to-design`, `opus2/a6-codex-contract` → U3; `a6-session-verification`, `a6-release-transaction-preview`, `a6-certification-continuation`, `a6-fence-continuation`, `a6-anchored-authority-contract` (#131) → U4.
- A3: `opus2/p0-photo-asset-review` (#23), `codex/a3-photo-recovery` (#37), `codex/a3-fencing-followup` → U5.
- A9: `codex/a9-package-review` (#38), `a9-a1-contract` (#39), `a9-owner-action-fencing`, `a9-parked-source-change`, `a9-defer-state-guard`, `a9-event-scope-validation`, `a9-event-release-binding` → U6.
- V0: `opus2/v0-paid-provider-gate` → U7.
- A4a/Research: `opus2/a4a-research-to-concept`, 6 `codex/a4a-*` branches, 26 research/watchlist/intake branches (#33, #64–#73, #76, #77, #81, #86, #89, #92, #97, #100, #103, #107, #110, #114, #118, #121) → U8.
- A4b/A7/A8: `opus2/a4b-enrichment` (#27), `codex/a4b-enrichment-continuation` (#29), `codex/a7-supply-continuation` (#31), `codex/a7-draft-key-retention`, `opus2/a8-culture-ideation` → U9.
- A5: `codex/a5-correction-review` (#30) → U10.
- A1/A2/quality: `opus2/a2-name-object` (#26), `codex/a1-*` (10 branches), `codex/a2-*` (2), `codex/batch6-safety-preview`, 8 `quality-*`, 4 `policy-*`/`proof-*`, `certification-malformed-listing-tags`, `physical-numeric-input-validation` (#78) → U11.
- V1: `codex/v1-visual-correctness` (#41), `v1-anchor-binding` (#44), `v1-variant-base` (#47) → U12.
- Support/finance: the `support-*` chain #51, #65, #67, #79; `finance-nonfinite-receipts` (#99); `reinvestment-*` (#105, #106); `sustainability-*` (#113, #116); `receipt-boolean-validation` (#62); `rollback-*` (#54, #55) → U14.
- `opus2/p0-amigurumi` (#18) → contained in `opus2/p0-construction-registry` (#22).

**Cumulative previews. Do not merge; use them only as test-composition references.**
- `codex/combined-safety-workforce-preview` (#124)
- `workforce-a9-visual-review-preview` (#125)
- `workforce-a3-gallery-review-preview` (#126)
- `workforce-a4b-enrichment-review-preview` (#127)
- `workforce-a5-correction-review-preview` (#128)
- `workforce-a7-a8-supply-review-preview` (#129)
- `workforce-physical-evidence-review-preview` (#130, leaf)
- `codex/finance-support-safety-preview-72b155b`: a redundant merge of #82 with batch6-safety-preview. (#112 `quality-policy-integration-preview` is an intermediate link of the U11 chain, not a stray preview.)

**Records only:** `opus2/checkpoint` bccab560 (50 checkpoint commits, no source).

**Obsolete, unrelated history from 2026-09-27/28, with no merge base with w6.** There are 22 branches, listed below. PR #1 belongs to `continuous-operations-audit`.
- `codex/build2-assist-01`
- `codex/continuous-operations-audit`
- `codex/visual-v2-rnd`
- 19 `codex/final-*` branches:
  - a-integration-01, ab-properties-01, b-owner-auth, build-integration-01, chain-fixtures-01, chart-tiles-01, continuity-01
  - draft-durability-01, finance-cost-basis-01, gauge-01, graph-cache-01, learn-01, learn-input-01, lineage-01
  - origin-gap-01, originality-01, proof-01, publish-recheck-01, visual-gates-01

## Per-priority tables

"(leaf)" means no other mapped branch contains it. "Contains" counts branches already listed. Overlaps leave out the hotspot files listed above; for multi-parent merge branches, see their parents.

### 1. Shared evidence/authority fencing

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U1 | `codex/batch6-evidence-contract` **(leaf)** | `4e39a9cc` | #42 | batch6-safety-preview | 7 branches | 1 | src/core/evidence_transaction.py | - | - | DO NOT INTEGRATE | Batch 6: bounded database transaction retry building block |
| U1 | `codex/batch6-evidence-writer-map` **(leaf)** | `7f986be5` | - | batch6-safety-preview | 7 branches | 1 |  | - | - | - | Map shared evidence writers and action boundaries |
| U1 | `codex/jobqueue-savepoint-preview` **(leaf)** | `ee32f68f` | - | batch6-safety-preview | 7 branches | 1 | src/queue/durable.py | - | U3: durable.py; U4: durable.py; U9: durable.py | - | Preserve caller transaction on duplicate job insert |
| U2 | `opus2/p0-child-safety-core` | `c3a7b93a` | - | w5-INTEG1 | - | 3 | src/creative/fallback_constructions.py, src/gates/small_parts.py, src/products/launch0.py (+4) | - | U11: fallback_constructions.py,launch0.py,listing_package.py; U14: fallback_constructions.py,launch0.py,listing_package.py; U15: fallback_constructions.py,launc... | Secondary: 73/73 suites; review Codex heads too | A1R: fixes for review A1R (A1R-1 HIGH; A1R-2..7) |

### 2. A6 Learning certification/delivery safety

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U3 | `codex/a6-learning-consumer` | `9f8f336e` | #32 | p0-learning-reference + a6-codex-contract | codex/p0-learning-reference, opus2/a6-codex-contract, opus2/a6-learning-to-design | 12 | src/agents/registry.py, src/app/command_center/approvals.py, src/app/main.py (+43) | - | composite: see parents | draft | A6: review scoped frozen-knowledge consumer |
| U3 | `codex/p0-learning-reference` | `1ae00eb3` | - | old 65df7b93 | - | 87 | src/agents/registry.py, src/app/command_center/approvals.py, src/app/main.py (+34) | autonomy_map.json, pipeline.py | U1: durable.py; U10: incident_lifecycle.py; U15: worker.py,writer.py; U4: design_eval.py,design_knowledge.py,durable.py; U5: worker.py; U8: bus.py; U9: durable.... | - | Refresh autonomy map for technique follow-on |
| U3 | `opus2/a6-codex-contract` | `594d5e38` | - | a6-learning-to-design | opus2/a6-learning-to-design | 60 | src/agents/registry.py, src/app/command_center/approvals.py, src/app/main.py (+35) | - | U10: engineering_ops.py,quality_ops.py; U11: quality_ops.py,release_gates.py; U14: release_gates.py; U15: worker.py,writer.py; U4: design_eval.py,design_knowled... | - | A6 x I-A6-FROZEN-KNOWLEDGE-CONTRACT: freeze approved design knowledge at drafting, re-veri |
| U3 | `opus2/a6-learning-to-design` | `8c131f10` | - | w5-INTEG1 | - | 3 | src/improve/consume.py, src/ops/retention.py, src/runtime/engineering_ops.py (+1) | - | U10: engineering_ops.py | Main: DO NOT SHIP (A6-1 HIGH, A6-2 MED) | A6: retention decisions for lesson.design_approved and lesson.acted_on |
| U4 | `codex/a6-anchored-authority-contract` | `98452be6` | #131 | a6-fence-continuation | 5 branches | 2 | src/improve/learning_authority.py | - | - | DO NOT INTEGRATE | Prototype anchored Learning authority verifier |
| U4 | `codex/a6-authority-certification-preview` **(leaf)** | `9a360cbc` | - | a6-certification-continuation | 7 branches | 2 | src/core/sealed_chain.py, src/improve/learning_authority.py, src/improve/owner_grant_append.py | - | - | - | Exercise retired Learning rule refusal in preview |
| U4 | `codex/a6-certification-continuation` | `0f28a403` | - | a6-release-transaction-preview | 6 branches | 4 | src/agents/registry.py, src/queue/durable.py, src/runtime/pipeline.py | - | U1: durable.py; U3: durable.py; U9: durable.py | - | Clarify PostgreSQL verification scope |
| U4 | `codex/a6-fence-continuation` | `1fc3141b` | - | a6-learning-consumer | codex/a6-learning-consumer, codex/p0-learning-reference, opus2/a6-codex-contract, opus2/a6-learning-to-design | 5 | src/core/sealed_chain.py, src/improve/design_knowledge.py, src/improve/knowledge_gate.py (+2) | - | U3: design_knowledge.py,knowledge_gate.py | - | Fail closed on inconsistent sealed revocations |
| U4 | `codex/a6-owner-stepup-grant-4504125` **(leaf)** | `59d6c91a` | #132 | a6-anchored-authority-contract | 6 branches | 1 | src/improve/design_knowledge.py, src/improve/knowledge_gate.py, src/improve/owner_grant_append.py (+2) | - | U3: design_eval.py,design_knowledge.py,knowledge_gate.py | DO NOT INTEGRATE | Prototype exact-owner Learning grant append |
| U4 | `codex/a6-release-transaction-preview` | `67b7b738` | - | a6-session-verification | 5 branches | 6 | src/runtime/pipeline.py | - | - | - | Record A6 authority and atomicity prerequisites |
| U4 | `codex/a6-session-verification` | `529978d5` | - | a6-learning-consumer | codex/a6-learning-consumer, codex/p0-learning-reference, opus2/a6-codex-contract, opus2/a6-learning-to-design | 5 | src/improve/design_knowledge.py, src/improve/knowledge_gate.py, src/improve/read_session.py (+3) | - | U3: design_eval.py,design_knowledge.py,knowledge_gate.py | - | Hold stale PostgreSQL snapshots in knowledge reads |

### 3. A3 photo evidence/gallery approval

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U5 | `codex/a3-fencing-followup` | `c888769b` | - | a3-photo-recovery | codex/a3-photo-recovery, opus2/p0-photo-asset-review | 1 | src/publish/photo_asset_review.py | - | - | - | Fence existing photo evidence during review and certification |
| U5 | `codex/a3-gallery-gap-recovery` | `84085fa8` | - | a3-fencing-followup | codex/a3-fencing-followup, codex/a3-photo-recovery, opus2/p0-photo-asset-review | 1 | src/publish/photo_asset_review.py | - | - | - | Keep excluded photo supplements after effective gallery |
| U5 | `codex/a3-photo-recovery` | `0ace3808` | #37 | p0-photo-asset-review | opus2/p0-photo-asset-review | 8 | src/publish/photo_asset_review.py, src/publish/physical_upgrade.py, src/publish/release_gates.py (+1) | - | U11: release_gates.py; U14: release_gates.py; U3: release_gates.py; U6: release_gates.py | stacked draft | A3 continuation: recover a qualified photo after leader lapse |
| U5 | `opus2/p0-photo-asset-review` | `c2174947` | #23 | w5-INTEG1 | - | 12 | src/agents/registry.py, src/authority/classes.py, src/autonomy/autonomy_map.json (+8) | - | U11: release_gates.py; U14: release_gates.py; U15: worker.py; U3: release_gates.py,worker.py; U6: release_gates.py; U9: worker.py | do not merge directly | OPUS2: P0-PHOTO-ASSET-REVIEW — a deterministic review approves attested sample photo frame |

### 4. A9 listing-package/owner-review fencing

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U6 | `codex/a9-a1-contract` | `d506cb10` | #39 | a9-package-review + p0-child-safety-core | codex/a9-package-review, opus2/p0-child-safety-core | 36 | src/core/models.py, src/creative/fallback_constructions.py, src/gates/small_parts.py (+8) | - | composite: see parents | DO NOT INTEGRATE | A9/A1 preview: bind owner review to locked release and listing |
| U6 | `codex/a9-defer-state-guard` | `c0252f6f` | - | a9-parked-source-change | 5 branches | 1 | src/app/command_center/approvals.py | - | - | - | Serialize owner deferral with listing question changes |
| U6 | `codex/a9-event-release-binding` | `5e7dc903` | - | a9-event-scope-validation | 7 branches | 1 | src/publish/listing_package.py, src/runtime/listing_package_ops.py | - | U11: listing_package.py; U14: listing_package.py; U2: listing_package.py | - | Bind listing package events to their release |
| U6 | `codex/a9-event-scope-validation` | `ed915230` | - | a9-defer-state-guard | 6 branches | 1 | src/runtime/listing_package_ops.py | - | - | - | Refuse malformed listing package event scopes |
| U6 | `codex/a9-owner-action-fencing` | `e1974a6d` | - | a9-a1-contract | codex/a9-a1-contract, codex/a9-package-review, opus2/p0-child-safety-core | 4 | src/core/db.py, src/publish/listing_package_fence.py | - | - | - | Preserve parked-review test ordering with source fence |
| U6 | `codex/a9-package-review` | `28a7befd` | #38 | w5-INTEG1 | - | 4 | src/publish/listing_package.py, src/runtime/listing_package_ops.py, src/runtime/release.py | - | U11: listing_package.py; U14: listing_package.py; U2: listing_package.py | DO NOT INTEGRATE | A9: keep owner review aligned with recorded listing package |
| U6 | `codex/a9-parked-source-change` | `2a6393ea` | - | a9-owner-action-fencing | codex/a9-a1-contract, codex/a9-owner-action-fencing, codex/a9-package-review, opus2/p0-child-safety-core | 2 | src/publish/listing_package.py, src/publish/listing_package_fence.py | - | U11: listing_package.py; U14: listing_package.py; U2: listing_package.py | - | Record A9 event regression and review scope |
| U6 | `codex/a9-sweep-isolation` | `3ee6881f` | - | a9-event-release-binding | 8 branches | 1 | src/publish/listing_package.py | - | U11: listing_package.py; U14: listing_package.py; U2: listing_package.py | - | Isolate listing sweep release failures and preserve retries |

### 5. V0 paid-provider budget safety

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U7 | `codex/governor-invalid-cost` **(leaf)** | `cd4156f4` | #45 | v0-paid-provider-gate | opus2/v0-paid-provider-gate | 11 | src/agents/registry.py, src/app/main.py, src/finance/governor.py (+7) | - | - | DO NOT INTEGRATE | Hold Governor reports on invalid recorded costs |
| U7 | `codex/v0-provider-authority` **(leaf)** | `c0968e79` | #40 | v0-paid-provider-gate | opus2/v0-paid-provider-gate | 14 | src/agents/registry.py, src/finance/reservations.py, src/gateway/anthropic.py (+5) | - | - | DO NOT INTEGRATE | Codex V0: paid-provider authority and accounting hardening (blocked) |
| U7 | `opus2/v0-paid-provider-gate` | `76fc0f3d` | - | w5-INTEG1 | - | 4 | src/app/command_center/api.py, src/core/db.py, src/creative/flux3_generator.py (+7) | - | U12: flux3_generator.py,image_production.py; U15: paid_calls.py; U3: image_production.py | Secondary: must not integrate as is (Codex findings accepted) | V0: the remaining six priority suites pass against the owner gate |

### 6. A4 research-to-product supply/enrichment (A4a, A4b, A7, A8, Research)

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U8 | `codex/a4a-brief-job-recovery` | `5ee9bed5` | - | a4a-evidence-ref-integrity | 7 branches | 1 | src/radar/ideation.py | - | U11: ideation.py; U14: ideation.py; U9: ideation.py | - | Recover missing initial research handoff |
| U8 | `codex/a4a-census-price-validation` | `abba1984` | - | a4a-research-truth | codex/a4a-research-truth, opus2/a4a-research-to-concept | 1 | src/radar/ideation.py | - | U11: ideation.py; U14: ideation.py; U9: ideation.py | - | Hold malformed prices out of research census |
| U8 | `codex/a4a-evidence-dates` | `b057f544` | - | a4a-intake-owner-recheck | 5 branches | 1 | src/radar/intake.py | - | U11: intake.py; U14: intake.py | - | Hold stale or invalid research evidence at intake |
| U8 | `codex/a4a-evidence-ref-integrity` | `fb9d590b` | - | a4a-evidence-dates | 6 branches | 1 | src/radar/intake.py | - | U11: intake.py; U14: intake.py | - | Hold ambiguous research evidence references |
| U8 | `codex/a4a-intake-owner-recheck` | `230f148d` | - | a4a-proposal-audit-recovery | codex/a4a-census-price-validation, codex/a4a-proposal-audit-recovery, codex/a4a-research-truth, opus2/a4a-research-to-concept | 1 | src/radar/intake.py | - | U11: intake.py; U14: intake.py | - | Hold stale research-owned concepts from intake |
| U8 | `codex/a4a-proposal-audit-recovery` | `29c10e90` | - | a4a-census-price-validation | codex/a4a-census-price-validation, codex/a4a-research-truth, opus2/a4a-research-to-concept | 1 | src/ops/retention.py, src/radar/ideation.py | - | U11: ideation.py; U14: ideation.py; U9: ideation.py | - | Recover research proposal audit with gap progress |
| U8 | `codex/a4a-research-truth` | `bc65dd88` | #33 | a4a-research-to-concept | opus2/a4a-research-to-concept | 4 | src/gates/certificate.py, src/gates/object_truth.py, src/intel/etsy_public.py (+7) | - | U11: certificate.py,eligibility.py,etsy_public.py; U14: certificate.py,eligibility.py,etsy_public.py; U15: eligibility.py; U2: text_fold.py; U6: eligibility.py,... | review requested | A4a continuation: hold untruthful designs and bind evidence |
| U8 | `codex/intake-approved-handoff-recovery` | `618ceca5` | #86 | intake-proposal-restart-recovery | 21 branches | 1 | src/ops/retention.py, src/radar/intake.py | - | U11: intake.py; U14: intake.py | DO NOT INTEGRATE | Recover interrupted research concept score handoffs |
| U8 | `codex/intake-family-handoff-recovery` | `d158fd93` | #89 | intake-approved-handoff-recovery | 22 branches | 1 | src/radar/intake.py | - | U11: intake.py; U14: intake.py | DO NOT INTEGRATE | Recover interrupted family concept score handoffs |
| U8 | `codex/intake-proposal-restart-recovery` | `1f252187` | #81 | research-answer-reuse-freshness | 20 branches | 1 | src/ops/retention.py, src/radar/intake.py | - | U11: intake.py; U14: intake.py | DO NOT INTEGRATE | Recover interrupted concept intake proposals |
| U8 | `codex/research-answer-reuse-freshness` | `59747f75` | #77 | research-expired-prior-evidence | 19 branches | 1 | src/intel/research.py, src/intel/research_agent.py | - | - | review requested, stacked draft | Apply shared freshness checks to research answer reuse |
| U8 | `codex/research-expired-prior-evidence` | `a2c67d6c` | #76 | watchlist-score-revalidation | 18 branches | 1 | src/intel/research_agent.py | - | - | draft | Exclude expired prior answers from current research evidence |
| U8 | `codex/research-expiry-isolation` | `bcd655bf` | #114 | research-fetch-provenance-atomic | 29 branches | 1 | src/intel/research.py | - | - | draft | Isolate malformed expired research handoffs |
| U8 | `codex/research-expiry-reopen-recovery` | `f6da25ba` | #103 | research-lesson-consumer-hold | 26 branches | 1 | src/intel/research.py | - | - | DO NOT INTEGRATE | Recover interrupted research expiry replacements |
| U8 | `codex/research-failed-audit-recovery` | `d22785bf` | - | research-sweep-new-evidence | 9 branches | 1 | src/intel/research_agent.py | - | - | - | Ignore unsuccessful investigation audit duplicates |
| U8 | `codex/research-fetch-followup-handoff` | `b7dcb8da` | #118 | research-expiry-isolation | 30 branches | 1 | src/intel/research_fetch.py, src/learn/runtime.py | - | - | DO NOT INTEGRATE | Queue Research follow-up atomically with fetched evidence |
| U8 | `codex/research-fetch-provenance-atomic` | `cea451f3` | #110 | research-transient-fetch-recovery | 28 branches | 1 | src/intel/research_fetch.py | - | - | DO NOT INTEGRATE | Commit fetched research sources with checksum audit |
| U8 | `codex/research-followup-retention` | `3316a840` | #121 | research-fetch-followup-handoff | 31 branches | 1 | src/ops/retention.py | - | - | DO NOT INTEGRATE | Preserve Research source follow-up job references |
| U8 | `codex/research-future-observations` | `971b40a1` | #66 | research-sweep-fairness | 12 branches | 1 | src/intel/learning.py | - | - | DO NOT INTEGRATE, review requested | Keep future-dated signals from masking stale research |
| U8 | `codex/research-lesson-consumer-hold` | `ee3cec42` | #100 | research-lesson-restart-recovery | 25 branches | 1 | src/improve/bus.py, src/intel/research_fetch.py | - | U3: bus.py | DO NOT INTEGRATE | Hold research lessons whose source is no longer current |
| U8 | `codex/research-lesson-restart-recovery` | `ebee75ea` | #97 | research-reused-answer-handoff | 24 branches | 1 | src/intel/research_fetch.py, src/learn/runtime.py | - | - | DO NOT INTEGRATE | Recover orphan research lessons before Learn calendar consumption |
| U8 | `codex/research-nochange-history` | `ff3debb0` | - | research-failed-audit-recovery | 10 branches | 1 | src/intel/research_agent.py | - | - | - | Preserve completed research history past failed audits |
| U8 | `codex/research-pipeline-integration-candidate` **(leaf)** | `6a86e9e8` | #122 | research-followup-retention | 32 branches | 1 |  | - | - | DO NOT INTEGRATE | Exercise the isolated Research-to-product pipeline candidate |
| U8 | `codex/research-reused-answer-handoff` | `d9648f6e` | #92 | intake-family-handoff-recovery | 23 branches | 1 | src/runtime/intel_ops.py | - | U11: intel_ops.py; U14: intel_ops.py; U9: intel_ops.py | draft | Return reused research conclusions to requesters |
| U8 | `codex/research-sweep-fairness` | `e50251f3` | #64 | research-nochange-history | 11 branches | 1 | src/runtime/intel_ops.py | - | U11: intel_ops.py; U14: intel_ops.py; U9: intel_ops.py | DO NOT INTEGRATE, review requested | Prevent duplicate keys from starving the research sweep |
| U8 | `codex/research-sweep-new-evidence` | `7b34ed08` | - | a4a-brief-job-recovery | 8 branches | 1 | src/intel/research_agent.py, src/radar/ideation.py, src/runtime/intel_ops.py | - | U11: ideation.py,intel_ops.py; U14: ideation.py,intel_ops.py; U9: ideation.py,intel_ops.py | - | Retry open research on new sufficient evidence |
| U8 | `codex/research-transient-fetch-recovery` | `e81b0d4c` | #107 | research-expiry-reopen-recovery | 27 branches | 1 | src/intel/research_fetch.py, src/ops/retention.py | - | - | DO NOT INTEGRATE | Recover transient research fetch failures with bounded backoff |
| U8 | `codex/research-trend-freshness` | `032f6511` | #68 | research-future-observations | 13 branches | 1 | src/radar/provenance.py | - | - | DO NOT INTEGRATE | Recalculate trend freshness when scoring opportunities |
| U8 | `codex/watchlist-current-corroboration` | `837f3cb8` | #69 | research-trend-freshness | 14 branches | 1 | src/intel/watchlist.py | - | - | review requested, stacked draft | Require current shop reads for new arena corroboration |
| U8 | `codex/watchlist-review-current-evidence` | `e06e8b8b` | #71 | watchlist-scan-bound-listings | 16 branches | 1 | src/intel/watchlist.py, src/runtime/intel_ops.py | - | U11: intel_ops.py; U14: intel_ops.py; U9: intel_ops.py | DO NOT INTEGRATE, review requested, stacked draft | Revalidate market corroboration before reviewing existing gaps |
| U8 | `codex/watchlist-scan-bound-listings` | `12356bc2` | #70 | watchlist-current-corroboration | 15 branches | 1 | src/intel/watchlist.py | - | - | review requested | Bind opportunity corroboration to current shop scans |
| U8 | `codex/watchlist-score-revalidation` | `095f0de5` | #73 | watchlist-review-current-evidence | 17 branches | 1 | src/intel/watchlist.py, src/runtime/pipeline.py | - | - | DO NOT INTEGRATE, review requested, stacked draft | Recheck watchlist evidence for queued opportunity scores |
| U8 | `opus2/a4a-research-to-concept` | `3dc3e68c` | - | w5-INTEG1 | - | 3 | src/radar/ideation.py, src/runtime/intel_ops.py, src/runtime/pipeline.py | - | U11: ideation.py,intel_ops.py; U14: ideation.py,intel_ops.py; U9: ideation.py,intel_ops.py | - | A4a: the research concept continues through compile to a certificate (Main handoff item) |
| U9 | `codex/a4b-answer-fence` | `e5cbb86c` | #46 | a4b-enrichment-continuation | codex/a4b-enrichment-continuation, opus2/a4b-enrichment | 1 | src/agents/registry.py, src/authority/classes.py, src/creative/enrichment_requests.py (+2) | - | U1: durable.py; U15: enrichment_ops.py,enrichment_requests.py; U3: durable.py; U4: durable.py | DO NOT INTEGRATE | A4b: serialize enrichment answer and sweep transitions |
| U9 | `codex/a4b-enrichment-continuation` | `f19b878d` | #29 | a4b-enrichment | opus2/a4b-enrichment | 7 | src/creative/enrichment_requests.py, src/runtime/pipeline.py | - | U15: enrichment_requests.py | DO NOT INTEGRATE | A4b continuation: bound retry and duplicate work (review requested) |
| U9 | `codex/a7-admission-atomic` | `b4814be9` | - | a7-draft-key-retention | codex/a7-draft-key-retention, codex/a7-supply-continuation | 2 | src/runtime/pipeline.py | - | - | - | Record A7 admission review claim |
| U9 | `codex/a7-draft-key-retention` | `d0437a5f` | - | a7-supply-continuation | codex/a7-supply-continuation | 3 | src/ops/flow_health.py, src/ops/retention.py, src/queue/durable.py (+1) | - | U1: durable.py; U3: durable.py; U4: durable.py; w5..w6 integrated: flow_health.py | - | Report held draft admissions as holds |
| U9 | `codex/a7-supply-continuation` | `4213b2ac` | #31 | w6@677661ec (A7 Codex fix) | - | 2 | src/ops/flow_health.py | - | w5..w6 integrated: flow_health.py | draft | A7 continuation: reconcile recovered supply status |
| U9 | `codex/a8-culture-continuation` | `58ee388a` | #36 | a8-culture-ideation | opus2/a8-culture-ideation | 2 | src/culture/ideation_bridge.py | - | - | DO NOT INTEGRATE, review requested, stacked draft | A8 continuation: distinguish signal identity and valid momentum |
| U9 | `opus2/a4b-enrichment` | `e230545c` | #27 | w5-INTEG1 | - | 3 | src/agents/registry.py, src/authority/classes.py, src/autonomy/autonomy_map.json (+6) | - | U15: enrichment_ops.py,enrichment_requests.py,worker.py; U3: worker.py; U5: worker.py | draft | A4b: a refused draft returns to Research and comes back as a new draft (Q26) |
| U9 | `opus2/a8-culture-ideation` | `4f99bd8f` | - | w5-INTEG1 | - | 4 | src/agents/registry.py, src/authority/classes.py, src/autonomy/autonomy_map.json (+8) | - | U11: ideation.py,intel_ops.py; U14: ideation.py,intel_ops.py; U15: worker.py; U3: worker.py; U5: worker.py; U8: ideation.py,intel_ops.py | - | A8: retention decisions for the two culture ideation audit actions |

### 7. A5 correction/recovery

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U10 | `codex/a5-correction-review` | `e68c9316` | #30 | w5-INTEG1 | - | 12 | src/autonomy/autonomy_map.json, src/ops/incident_lifecycle.py, src/ops/retention.py (+4) | - | U11: quality_ops.py; U3: engineering_ops.py,incident_lifecycle.py,quality_ops.py; support-followup(in review): incident_lifecycle.py; w5..w6 integrated: inciden... | DO NOT INTEGRATE | A5: preserve evidence and certified releases during correction |
| U10 | `codex/a5-hold-audit` | `efd6a76e` | #43 | a5-correction-review | codex/a5-correction-review | 3 | src/runtime/engineering_ops.py | - | U3: engineering_ops.py | DO NOT INTEGRATE | A5: keep correction hold audits idempotent |

### 8. V1-V6 visual

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U12 | `codex/v1-anchor-binding` | `b9eb3e32` | #44 | v1-visual-correctness | codex/v1-visual-correctness | 4 | src/visual/candidate_gates.py, src/visual/fidelity.py, src/visual/image_production.py | - | U3: image_production.py; U7: image_production.py | DO NOT INTEGRATE | Hold visual anchors without exact release identity |
| U12 | `codex/v1-craft-enum` | `ded427f6` | #60 | v1-variant-base | codex/v1-anchor-binding, codex/v1-variant-base, codex/v1-visual-correctness | 32 | src/app/command_center/api.py, src/creative/flux3_generator.py, src/runtime/release.py (+4) | - | U3: image_production.py; U7: flux3_generator.py,image_production.py | DO NOT INTEGRATE | Harden visual evidence and recovery workflows |
| U12 | `codex/v1-variant-base` | `100f0649` | #47 | v1-anchor-binding | codex/v1-anchor-binding, codex/v1-visual-correctness | 9 | src/visual/candidate_gates.py, src/visual/fidelity.py, src/visual/image_production.py (+1) | - | U3: image_production.py; U7: image_production.py | DO NOT INTEGRATE, fixture-only, stacked draft | Bind variant and gallery inputs to their production run |
| U12 | `codex/v1-visual-correctness` | `d125a3ba` | #41 | w5-INTEG1 | - | 7 | src/creative/flux_prompt.py, src/creative/image_stages.py, src/creative/pattern_refs.py (+5) | - | U3: image_production.py; U7: image_production.py | DO NOT INTEGRATE | Codex V1: component-aware visual truth and repair holds (blocked) |
| U12 | `opus2/v2-vessel-fidelity` **(leaf)** | `6799f1d4` | - | w6@f5c3976d | - | 3 | src/creative/image_stages.py, src/runtime/chain_successors.py, src/visual/candidate_gates.py (+3) | - | U3: image_production.py; U7: image_production.py | Main: DO NOT SHIP 06:16; fix assigned | V2 / P1-d per Main decision I-V2-UNJUDGED-PAIRS; prominence-floor test and reasoning |
| U12 | `opus2/v4-scene-references` **(leaf)** | `86cf2a36` | - | w6@c83d9516 | - | 1 | src/creative/flux3_generator.py, src/creative/flux_prompt.py, src/creative/image_stages.py (+2) | - | U7: flux3_generator.py | Main review queue #3 | V4 / audit P1-a: owner-approved room references reach every in-room request; same-room che |
| U12 | `opus2/v5-scale-verification` **(leaf)** | `295474c6` | - | w6@c83d9516 | - | 1 | src/visual/scale.py | - | - | Main review queue #4 (stays unwired) | V5 / audit P1-c: product scale against the CIR's finished size, from known-size anchors |

### 9. Other handoffs (A1/A2 safety + quality/policy, opus2 W6 handoffs, support, finance, commerce, opus2 W5 residues)

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| U11 | `codex/a1-audience-shorthand` | `88c47c69` | #48 | a1-stuffing-continuation | codex/a1-stuffing-continuation, opus2/p0-child-safety-core | 1 | src/products/launch0.py | - | U14: launch0.py; U15: launch0.py; U2: launch0.py; U6: launch0.py | draft | A1: hold explicit child audience shorthand |
| U11 | `codex/a1-detachable-eye-safety` | `ec2dee66` | #49 | a1-audience-shorthand | codex/a1-audience-shorthand, codex/a1-stuffing-continuation, opus2/p0-child-safety-core | 1 | src/intel/childrens.py | - | - | draft | A1: hold explicit detachable toy-eye synonyms |
| U11 | `codex/a1-detachable-part-aliases` | `7e54c330` | #50 | a1-detachable-eye-safety | codex/a1-audience-shorthand, codex/a1-detachable-eye-safety, codex/a1-stuffing-continuation, opus2/p0-child-safety-core | 6 | src/gates/small_parts.py, src/intel/childrens.py | - | U14: small_parts.py; U2: small_parts.py; U6: small_parts.py | draft | A1: hold explicit detachable part aliases |
| U11 | `codex/a1-hold-atomic` | `b628be5e` | #58 | a1-named-safety-hold | 5 branches | 1 | src/runtime/release.py | - | - | DO NOT INTEGRATE | A1: write safety hold and owner action atomically |
| U11 | `codex/a1-hold-snapshot` | `3b1251b0` | #59 | a1-hold-atomic | 6 branches | 2 | src/publish/pdf.py, src/runtime/release.py | - | U14: pdf.py; U15: pdf.py; U2: pdf.py; U6: pdf.py | DO NOT INTEGRATE | A1: recheck safety hold source before recording |
| U11 | `codex/a1-named-safety-hold` | `2e856b80` | #53 | a1-detachable-eye-safety | codex/a1-audience-shorthand, codex/a1-detachable-eye-safety, codex/a1-stuffing-continuation, opus2/p0-child-safety-core | 2 | src/intel/childrens.py, src/publish/pdf.py, src/runtime/release.py | - | U14: pdf.py; U15: pdf.py; U2: pdf.py; U6: pdf.py | draft | A1: record unsafe child designs as named holds |
| U11 | `codex/a1-stuffing-continuation` | `ec9dc9a8` | #34 | p0-child-safety-core | opus2/p0-child-safety-core | 22 | src/gates/small_parts.py, src/products/launch0.py, src/publish/eligibility.py (+4) | - | U14: eligibility.py,launch0.py,listing_package.py; U15: eligibility.py,launch0.py,pdf.py; U2: launch0.py,listing_package.py,pdf.py; U3: release_gates.py; U5: re... | do not merge directly, stacked draft | A1 continuation: bind child decisions and hold explicit stuffing |
| U11 | `codex/a1-waist-drawcord-unknown` | `4800b597` | #74 | a1-hold-snapshot | 7 branches | 1 | src/intel/childrens.py | - | - | DO NOT INTEGRATE, stacked draft | A1: hold unassessed child waist drawstrings |
| U11 | `codex/a1-whole-toy-fit` | `2af2a48e` | #72 | a1-detachable-part-aliases | 5 branches | 1 | src/publish/pdf.py | - | U14: pdf.py; U15: pdf.py; U2: pdf.py; U6: pdf.py | DO NOT INTEGRATE | A1: hold unassessed whole toys for under-three audience |
| U11 | `codex/a2-french-stripes` | `251ee95d` | #61 | a2-safety-continuation | codex/a2-safety-continuation, opus2/a2-name-object, opus2/p0-child-safety-core | 1 | src/publish/eligibility.py | - | U14: eligibility.py; U15: eligibility.py; U6: eligibility.py; U8: eligibility.py | draft | A2: check explicit French stripe claims |
| U11 | `codex/a2-safety-continuation` | `94d165ec` | #35 | a2-name-object | opus2/a2-name-object, opus2/p0-child-safety-core | 13 | src/creative/fallback_constructions.py, src/publish/eligibility.py | - | U14: eligibility.py,fallback_constructions.py; U15: eligibility.py,fallback_constructions.py; U2: fallback_constructions.py; U6: eligibility.py,fallback_constru... | do not merge directly, stacked draft | A2 continuation: enforce listing motif and tote size truth |
| U11 | `codex/batch6-safety-preview` | `6cb70e3a` | - | a1-stuffing-continuation + a2-safety-continuation + a4a-research-truth | 6 branches | 35 | src/creative/fallback_constructions.py, src/gates/asset_truth.py, src/gates/certificate.py (+16) | - | composite: see parents | - | Record combined Batch 6 safety regression evidence |
| U11 | `codex/certification-malformed-listing-tags` | `a83cf092` | #119 | policy-reverify-malformed-tags | 19 branches | 1 | src/gates/policy.py, src/runtime/pipeline.py | quality_ops.py | - | DO NOT INTEGRATE, stacked draft | Refuse malformed stored listing tags at certification |
| U11 | `codex/physical-complete-colour-evidence` | `77b9a88f` | #80 | physical-numeric-input-validation | 8 branches | 1 | src/quality/physical.py | - | U14: physical.py | DO NOT INTEGRATE, stacked draft | Require complete physical sample colour measurements |
| U11 | `codex/physical-numeric-input-validation` | `2a9ce57e` | #78 | batch6-safety-preview | 7 branches | 1 | src/quality/physical.py, src/runtime/release.py | - | U14: physical.py | DO NOT INTEGRATE | Reject boolean physical sample measurements |
| U11 | `codex/policy-finite-price-reverify` | `0daf9bed` | #98 | policy-missing-proof-hold | 9 branches | 1 | src/gates/policy.py | - | - | DO NOT INTEGRATE, stacked draft | Reject nonfinite listing prices in policy checks |
| U11 | `codex/policy-missing-proof-hold` | `f8e8fe2c` | #87 | proof-claim-normalization | 8 branches | 1 | src/gates/policy.py | - | - | DO NOT INTEGRATE, stacked draft | Fail closed when listing proof position is missing |
| U11 | `codex/policy-reverify-malformed-tags` | `ab61eeca` | #115 | quality-policy-integration-preview | 18 branches | 1 | src/runtime/quality_ops.py | quality_ops.py | U10: quality_ops.py; U3: quality_ops.py; w5..w6 integrated: quality_ops.py | DO NOT INTEGRATE, stacked draft | Keep policy holds on malformed listing tags |
| U11 | `codex/proof-claim-normalization` | `93d8b7c9` | #83 | batch6-safety-preview | 7 branches | 1 | src/quality/proof.py | - | - | DO NOT INTEGRATE | Normalize existing Product Truth proof claims |
| U11 | `codex/quality-a1-a2-integration-preview` | `7ddc9465` | #123 | a1-waist-drawcord-unknown + a1-whole-toy-fit + a2-french-stripes + certification-malformed-listing-tags | 29 branches | 21 | src/creative/fallback_constructions.py, src/gates/asset_truth.py, src/gates/certificate.py (+20) | quality_ops.py | composite: see parents | DO NOT INTEGRATE | Isolated safety, quality and policy integration preview |
| U11 | `codex/quality-asset-truth-tags` | `d272e8fb` | #91 | batch6-safety-preview | 7 branches | 1 | src/runtime/quality_ops.py | - | U10: quality_ops.py; U3: quality_ops.py; w5..w6 integrated: quality_ops.py | DO NOT INTEGRATE | Reverify listing tags and preserve holds without a listing |
| U11 | `codex/quality-hold-before-incident` | `2339771b` | #108 | quality-reverify-stale-job-hold | 12 branches | 1 | src/runtime/quality_ops.py | quality_ops.py | U10: quality_ops.py; U3: quality_ops.py; w5..w6 integrated: quality_ops.py | DO NOT INTEGRATE, stacked draft | Preserve failed quality holds when incident recording fails |
| U11 | `codex/quality-policy-integration-preview` | `6f2c3cda` | #112 | policy-finite-price-reverify + quality-reverify-publish-name-truth | 17 branches | 5 | src/creative/fallback_constructions.py, src/gates/asset_truth.py, src/gates/certificate.py (+19) | quality_ops.py | composite: see parents | DO NOT INTEGRATE | Isolated quality and policy integration preview |
| U11 | `codex/quality-product-identity-reverify` | `3b74e9a7` | #94 | quality-asset-truth-tags | 8 branches | 1 | src/runtime/quality_ops.py | - | U10: quality_ops.py; U3: quality_ops.py; w5..w6 integrated: quality_ops.py | DO NOT INTEGRATE, stacked draft | Reverify product identity in quality workflow |
| U11 | `codex/quality-reverify-publish-name-truth` | `cb02f5e5` | #111 | quality-hold-before-incident | 13 branches | 1 | src/runtime/quality_ops.py | quality_ops.py | U10: quality_ops.py; U3: quality_ops.py; w5..w6 integrated: quality_ops.py | DO NOT INTEGRATE, stacked draft | Reverify publication name and audience truth |
| U11 | `codex/quality-reverify-release-freshness` | `63b3f98d` | #95 | quality-product-identity-reverify | 9 branches | 1 | src/runtime/quality_ops.py | - | U10: quality_ops.py; U3: quality_ops.py; w5..w6 integrated: quality_ops.py | DO NOT INTEGRATE, stacked draft | Scope quality re-verification cadence to release hash |
| U11 | `codex/quality-reverify-stale-job-hold` | `d373da8b` | #104 | quality-unverifiable-current-release | 11 branches | 1 | src/runtime/quality_ops.py | - | U10: quality_ops.py; U3: quality_ops.py; w5..w6 integrated: quality_ops.py | DO NOT INTEGRATE | Reject stale quality jobs before changing holds |
| U11 | `codex/quality-unverifiable-current-release` | `b7add45e` | #102 | quality-reverify-release-freshness | 10 branches | 1 | src/runtime/quality_ops.py | - | U10: quality_ops.py; U3: quality_ops.py; w5..w6 integrated: quality_ops.py | DO NOT INTEGRATE, stacked draft | Scope unknown quality readings to current release |
| U11 | `opus2/a2-name-object` | `52f83cf7` | #26 | p0-child-safety-core | opus2/p0-child-safety-core | 10 | src/creative/fallback_constructions.py, src/gates/asset_truth.py, src/products/launch0.py (+1) | - | U14: asset_truth.py,eligibility.py,fallback_constructions.py; U15: eligibility.py,fallback_constructions.py,launch0.py; U2: fallback_constructions.py,launch0.py... | draft; Secondary: 84/84 suites; review Codex heads too | A2 (P0-NAME-OBJECT): one fail-closed name/object contract across every construction route |
| U13 | `opus2/p0-physical-test-request` **(leaf)** | `d697d093` | - | w6@f5c3976d | - | 1 | src/ops/retention.py, src/quality/physical_sample.py, src/runtime/pipeline.py (+1) | - | - | Main review queue #5 "when green" | P0-PHYSICAL-TEST-REQUEST: one per-release sample request for class-C designs with no bound |
| U13 | `opus2/p0-portfolio-act` **(leaf)** | `ad351e46` | - | w6@f5c3976d | - | 3 | src/autonomy/autonomy_map.json, src/growth/portfolio_act.py, src/runtime/pipeline.py | - | - | f3bea437 DNS; ad351e46 queued for delta review | P0-PORTFOLIO-ACT: fix review PORTFOLIO f3bea437 (F1-F8) |
| U13 | `opus2/p0-storefront-asset-fix` **(leaf)** | `d8b2754b` | - | w6@f5c3976d | - | 2 | src/autonomy/autonomy_map.json, src/runtime/storefront_ops.py, src/store_foundation/asset_health.py | - | - | Main: DO NOT SHIP; rebuild on fix_only | P0-STOREFRONT-ASSET-FIX: regenerate the committed autonomy map (storefront.review -> asset |
| U14 | `codex/artifact-corruption-recovery` **(leaf)** | `82caf19b` | #57 | w5-INTEG1 | - | 1 | src/commerce/deliverables.py | - | - | draft | Recover certified PDF bytes when local cache is corrupt |
| U14 | `codex/benchmark-sample-integrity-2affa42` **(leaf)** | `fdc240a1` | #88 | w5-INTEG1 | - | 1 | src/commerce/benchmarks.py | - | - | review requested | Require distinct measured listings for commercial benchmarks |
| U14 | `codex/benchmark-source-truth-bf7439e` **(leaf)** | `a1b09310` | #90 | w5-INTEG1 | - | 1 | src/runtime/growth_ops.py | - | - | review requested | Keep unknown benchmark sources and incidents unmeasured |
| U14 | `codex/bundle-attribution-evidence-a198e94` **(leaf)** | `698e87d3` | #85 | w5-INTEG1 | - | 1 | src/commerce/attribution.py | - | - | draft | Require complete evidence before declaring bundle winners |
| U14 | `codex/finance-nonfinite-receipts-61f266c` | `e6cdf291` | #99 | w5-INTEG1 | - | 1 | src/commerce/orders_ingest.py, src/finance/currency.py | - | - | DO NOT INTEGRATE | Reject nonfinite receipt values without skipping replay |
| U14 | `codex/finance-replay-bounded-679514f` **(leaf)** | `1692beb2` | #101 | finance-nonfinite-receipts-61f266c | codex/finance-nonfinite-receipts-61f266c | 1 | src/commerce/orders_ingest.py | - | - | DO NOT INTEGRATE, review requested | Bound refused receipt replay across restarts |
| U14 | `codex/finance-support-safety-preview-72b155b` **(leaf)** | `58c031c7` | - | batch6-safety-preview + support-service-malformed-1afa506 | 12 branches | 13 | src/app/main.py, src/commerce/attribution.py, src/commerce/benchmarks.py (+28) | - | composite: see parents | - | Review-only safety, support and finance integration preview |
| U14 | `codex/kill-table-evidence-7383eed` **(leaf)** | `815e8585` | #84 | w5-INTEG1 | - | 1 | src/commerce/kill_table.py | - | - | review requested | Hold scaling recommendations until defect rates are measured |
| U14 | `codex/listing-outcome-atomic-provenance-3ffa5f7` **(leaf)** | `3998c16f` | #120 | w5-INTEG1 | - | 1 | src/commerce/listing_outcomes.py, src/creative/style_learning.py | - | - | DO NOT INTEGRATE | Write listing outcomes with current import provenance |
| U14 | `codex/offer-retirement-evidence-9fcc25a` **(leaf)** | `37cb1171` | #93 | w5-INTEG1 | - | 1 | src/commerce/offers.py | - | - | draft | Hold offer retirement without complete measured evidence |
| U14 | `codex/pdf-delivery-completeness` **(leaf)** | `a16f0b2c` | #52 | w5-INTEG1 | - | 1 | src/commerce/deliverables.py | - | - | review requested | Require both certified PDF editions for delivery readiness |
| U14 | `codex/receipt-boolean-validation` | `1030caf4` | #62 | w5-INTEG1 | - | 1 | src/commerce/deliverables.py | - | - | draft | Reject ambiguous receipt flags in delivery rehearsal |
| U14 | `codex/receipt-structure-validation` **(leaf)** | `5d422e18` | #63 | receipt-boolean-validation | codex/receipt-boolean-validation | 1 | src/commerce/deliverables.py | - | - | draft | Report malformed receipt evidence as failed rehearsal |
| U14 | `codex/reinvestment-action-recovery-12410d1` | `b81cc316` | #105 | w5-INTEG1 | - | 1 | src/commerce/order_readings.py | - | - | DO NOT INTEGRATE | Supersede stale reinvestment owner actions |
| U14 | `codex/reinvestment-evidence-validity-5ddaee7` | `2c6d58ba` | #106 | reinvestment-action-recovery-12410d1 | codex/reinvestment-action-recovery-12410d1 | 1 | src/commerce/order_readings.py | - | - | DO NOT INTEGRATE, review requested | Hold reinvestment on invalid sale evidence |
| U14 | `codex/reinvestment-ledger-reconciliation-6b138b1` **(leaf)** | `5a1beacb` | #109 | reinvestment-evidence-validity-5ddaee7 | codex/reinvestment-action-recovery-12410d1, codex/reinvestment-evidence-validity-5ddaee7 | 1 | src/commerce/order_readings.py | - | - | DO NOT INTEGRATE | Reconcile reinvestment sales against booked orders |
| U14 | `codex/rollback-artifact-integrity` | `cdc5aaff` | #54 | w5-INTEG1 | - | 1 | src/commerce/deliverables.py | - | - | draft | Verify artifact bytes in rollback rehearsal |
| U14 | `codex/rollback-missing-evidence` | `de8135ad` | #55 | rollback-artifact-integrity | codex/rollback-artifact-integrity | 1 | src/launch/rollback.py | - | - | draft | Refuse rollback when artifact hashes are incomplete |
| U14 | `codex/rollback-release-binding` **(leaf)** | `28eef8c6` | #56 | rollback-missing-evidence | codex/rollback-artifact-integrity, codex/rollback-missing-evidence | 1 | src/launch/rollback.py | - | - | draft | Bind rollback assets to current certified release |
| U14 | `codex/scale-future-events-365c1d1` **(leaf)** | `8e8de8cf` | #96 | w5-INTEG1 | - | 1 | src/scale/runrate.py | - | - | DO NOT INTEGRATE | Hold historical scale readings without prior order evidence |
| U14 | `codex/support-case-cost-evidence-279288f` **(leaf)** | `007af924` | #117 | sustainability-maintenance-evidence-5fed445 | codex/sustainability-maintenance-evidence-5fed445, codex/sustainability-unknown-costs-58a9605 | 1 | src/finance/sustainability.py | - | - | DO NOT INTEGRATE | Measure support cost by linked case rather than calls |
| U14 | `codex/support-delivery-timing-13d7887` | `a5775abc` | #79 | support-refund-impact-40d9a64 | codex/support-first-response-truth, codex/support-refund-impact-40d9a64, codex/support-service-truth-611f6e4 | 1 | src/support/response_watch.py, src/support/service.py | - | - | DO NOT INTEGRATE | Hold support service measurements without matching sent evidence |
| U14 | `codex/support-first-response-truth` | `35306511` | #51 | w5-INTEG1 | - | 8 | src/app/main.py, src/runtime/release.py, src/support/department.py (+3) | - | - | draft | Preserve support response, intake and defect-signal truth |
| U14 | `codex/support-refund-impact-40d9a64` | `4ea3edfb` | #67 | support-service-truth-611f6e4 | codex/support-first-response-truth, codex/support-service-truth-611f6e4 | 1 | src/support/service.py | - | - | stacked draft | Keep support refund impact unmeasured without linked evidence |
| U14 | `codex/support-service-malformed-1afa506` | `2fb20cf0` | #82 | support-delivery-timing-13d7887 | codex/support-delivery-timing-13d7887, codex/support-first-response-truth, codex/support-refund-impact-40d9a64, codex/support-service-truth-611f6e4 | 1 | src/support/service.py | - | - | draft | Keep malformed support evidence unmeasured |
| U14 | `codex/support-service-truth-611f6e4` | `ac5b375c` | #65 | support-first-response-truth | codex/support-first-response-truth | 1 | src/support/service.py | - | - | stacked draft | Keep incomplete support service measurements unknown |
| U14 | `codex/sustainability-maintenance-evidence-5fed445` | `f80bfabe` | #116 | sustainability-unknown-costs-58a9605 | codex/sustainability-unknown-costs-58a9605 | 1 | src/finance/sustainability.py | - | - | review requested | Keep missing listing maintenance costs unmeasured |
| U14 | `codex/sustainability-unknown-costs-58a9605` | `f0b9af01` | #113 | w5-INTEG1 | - | 1 | src/finance/sustainability.py | - | - | draft | Hold sustainability gate when scenario costs are unmeasured |
| U14 | `codex/trust-proof-truth` **(leaf)** | `b439b9fa` | #75 | support-refund-impact-40d9a64 | codex/support-first-response-truth, codex/support-refund-impact-40d9a64, codex/support-service-truth-611f6e4 | 1 | src/commerce/trust.py, src/quality/physical.py, src/runtime/growth_ops.py | - | U11: physical.py | DO NOT INTEGRATE, stacked draft | Withhold unlinked proof from traffic trust gate |
| U15 | `opus2/p0-amigurumi` | `98d216b0` | #18 | old 71e26e6f | - | 9 | src/cir/assembly.py, src/cir/writer.py, src/creative/fallback_constructions.py (+3) | fallback_constructions.py, pipeline.py | U11: fallback_constructions.py,launch0.py,pdf.py; U14: fallback_constructions.py,launch0.py,pdf.py; U2: fallback_constructions.py,launch0.py,pdf.py; U3: writer.... | do not merge directly | OPUS2: amigurumi (ball-body bear/bunny) and drawstring pouch constructions, plus two flagg |
| U15 | `opus2/p0-cir-colourwork` **(leaf)** | `e6e6fb94` | #9 | old 424d69a9 | - | 4 | src/products/launch0.py | launch0.py | U11: launch0.py; U14: launch0.py; U2: launch0.py; U6: launch0.py | draft | OPUS2: P0-CIR-COLOURWORK (proposal): stitches worked in their own colour |
| U15 | `opus2/p0-construction-registry` **(leaf)** | `da4f331a` | #22 | p0-amigurumi | opus2/p0-amigurumi | 14 | src/agents/registry.py, src/authority/classes.py, src/autonomy/autonomy_map.json (+10) | fallback_constructions.py, pipeline.py | U11: eligibility.py,fallback_constructions.py,launch0.py; U14: eligibility.py,fallback_constructions.py,launch0.py; U2: fallback_constructions.py,launch0.py; U3... | do not merge directly | OPUS2: research → Product Development contract — construction request, registry, held brie |
| U15 | `opus2/p0-revenue-workforce` | `286cd044` | #3 | old 13d67502 | - | 11 | src/creative/fallback_constructions.py, src/gates/size_claims.py, src/products/launch0.py | fallback_constructions.py | U11: fallback_constructions.py,launch0.py; U14: fallback_constructions.py,launch0.py; U2: fallback_constructions.py,launch0.py; U6: fallback_constructions.py,la... | do not merge directly | OPUS2-P0: size claims, Laura's home, rim negative, performance lessons, chain successors,  |
| U15 | `opus2/p1-culture-sweep-timeout` **(leaf)** | `eba6fb3c` | #7 | old e0be7c4d | - | 1 | src/gateway/paid_calls.py | - | U7: paid_calls.py | draft | OPUS2: P1-CULTURE-SWEEP-TIMEOUT: a classifier timeout no longer dead-letters culture.sweep |

### 0. Cumulative previews and superseded (do not review as units)

| Unit | Branch | Head | PR | Direct base (parent) | Contains | Own commits | Top own src files | Code conflicts vs w6 (beyond COORDINATION/suite list) | Overlaps (other units, non-hotspot files) | Declared status | Purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CUM | `codex/combined-safety-workforce-preview` | `899deba9` | #124 | quality-a1-a2-integration-preview + research-nochange-history + support-first-response-truth | 40 branches | 56 | src/app/main.py, src/commerce/attribution.py, src/commerce/benchmarks.py (+41) | quality_ops.py | composite: see parents | DNI as P0-complete | Isolated safety and workforce integration preview |
| CUM | `codex/workforce-a3-gallery-review-preview` | `d4cde0e4` | #126 | a3-gallery-gap-recovery + workforce-a9-visual-review-preview | 58 branches | 24 | src/agents/registry.py, src/app/command_center/api.py, src/app/command_center/approvals.py (+66) | quality_ops.py | composite: see parents | DNI as P0-complete | Isolated workforce A3 gallery review preview |
| CUM | `codex/workforce-a4b-enrichment-review-preview` | `33e741de` | #127 | a4b-answer-fence + workforce-a3-gallery-review-preview | 62 branches | 13 | src/agents/registry.py, src/app/command_center/api.py, src/app/command_center/approvals.py (+69) | quality_ops.py | composite: see parents | DNI as P0-complete | Isolated workforce A4b enrichment review preview |
| CUM | `codex/workforce-a5-correction-review-preview` | `1dc4fb75` | #128 | a5-hold-audit + workforce-a4b-enrichment-review-preview | 65 branches | 17 | src/agents/registry.py, src/app/command_center/api.py, src/app/command_center/approvals.py (+71) | quality_ops.py | composite: see parents | DNI as P0-complete | Isolated workforce A5 correction review preview |
| CUM | `codex/workforce-a7-a8-supply-review-preview` | `64edede9` | #129 | a7-admission-atomic + a8-culture-continuation + workforce-a5-correction-review-preview | 71 branches | 14 | src/agents/registry.py, src/app/command_center/api.py, src/app/command_center/approvals.py (+74) | quality_ops.py | composite: see parents | DNI as P0-complete | Isolated workforce A7 and A8 review preview |
| CUM | `codex/workforce-a9-visual-review-preview` | `38599c1d` | #125 | a9-sweep-isolation + combined-safety-workforce-preview + v1-craft-enum | 53 branches | 82 | src/app/command_center/api.py, src/app/command_center/approvals.py, src/app/main.py (+57) | quality_ops.py | composite: see parents | DNI as P0-complete | Isolated workforce A9 and V1 review preview |
| CUM | `codex/workforce-physical-evidence-review-preview` **(leaf)** | `ac57b788` | #130 | physical-complete-colour-evidence + workforce-a7-a8-supply-review-preview | 74 branches | 4 | src/agents/registry.py, src/app/command_center/api.py, src/app/command_center/approvals.py (+75) | quality_ops.py | composite: see parents | DNI as P0-complete | Isolated workforce physical sample review preview |
| SUP | `opus2/checkpoint` **(leaf)** | `bccab560` | - | old d230e8fd | - | 50 |  | - | - | records only; never integrate | opus2 checkpoint 05:50Z: PORTFOLIO fix, V2/V4/V5 review-requested; V3/V6 await Main |
| SUP | `opus2/p0-pet-bed` | `09122165` | #10 | old 13d67502 | - | 6 | src/app/command_center/approvals.py, src/app/command_center/policy_readings.py, src/app/command_center/snapshots/OWNER_ACTIONS.json (+23) | BUILD_STATE.md, DECISION_LOG.md, OWNER_ACTIONS.json +more | - | draft | OPUS2: pet basket bed: pet beds drafted as a wide, low vessel |
| SUP | `opus2/p0-revenue-workforce-b4merge` **(leaf)** | `fcd361a6` | - | p0-revenue-workforce | opus2/p0-revenue-workforce | 11 | src/app/command_center/approvals.py, src/app/command_center/policy_readings.py, src/app/command_center/snapshots/OWNER_ACTIONS.json (+22) | BUILD_STATE.md, DECISION_LOG.md, OWNER_ACTIONS.json +more | - | - | Merge remote-tracking branch 'origin/opus2/p0-revenue-workforce' into opus2/p0-revenue-wor |
| SUP | `opus2/p0-stocking` **(leaf)** | `7493c723` | #11 | p0-pet-bed | opus2/p0-pet-bed | 9 | src/creative/fallback_constructions.py, src/runtime/pipeline.py | BUILD_STATE.md, DECISION_LOG.md, OWNER_ACTIONS.json +more | - | draft | OPUS2: two-panel Christmas stocking: stockings drafted instead of refused |
