# W4-FMEND handoff: end-stage Final Master evidence on candidate c131f07

Lane: `claude/w4-FMEND` (worktree `.claude/worktrees/W4-FMEND`), base
`c131f072b3eb4a9f31fa290c69fd33e8434cf267` + merge of `origin/claude/w4-PACKETREL` (merged
cleanly). Date 2026-10-11 UTC. No Railway, Etsy, spend or customer action. No test or gate
edited. `closure_matrix.json`, `overrides.json` and every row's completion are **unchanged**:
no row reaches COMPLETE under `aggregate.py` / `final_proof.py` from this evidence.

## Notes for the integrator

- **The PACKETREL merge is not records-only.** It also changes `src/brambleloop/launch/packet.py`,
  `app/command_center/launch_packet.py`, `scripts/freeze_candidate.py`, `run_tests.sh` and
  three tests (the release-record citation, the 7421ef6 freeze). None of that is in c131f07.
  All evidence below was produced from a **clean detached worktree at c131f07**, so the merge
  does not affect it.
- The interpreter in the brief (`visual-investigation/brambleloop/.venv/bin/python`) does not
  exist. I used `/home/user/Project-Money/brambleloop/.venv/bin/python`, which is the one the
  running full suite (on c131f07, run `20261011T052428Z-1870`) uses. Each step ran as one process
  with a private TMPDIR.
- No release record and no frozen-candidate file (`CANDIDATE_c131f07.json`) exist for c131f07
  yet. The full suite on c131f07 was still running when this lane finished.

## Produced

Evidence directory: `research/final_build/w4/evidence_FMEND_c131f07/`. `SUMMARY.json` lists
the exact commands and a sha256 for each file.

| file | what |
|---|---|
| `shadow_rehearsal_c131f07.json` | `scripts/shadow_rehearsal.py` on c131f07, production mode, tree clean, 406.5 s |
| `launch_packet_c131f072b3eb_20261011T053329Z.{json,md}` | `scripts/launch_packet.py` on c131f07, using a fresh scratch DB in SHADOW |
| `module_reachability_c131f07.json` | reachability regenerated on c131f07: 656 modules, 564 reached, none lost compared with 2f36fe0 |
| `runtime_packets_c131f07.json` | the first runtime evidence packets: 10 launch-critical rows |
| `final_proof_c131f07.json` | `final_proof.py --matrix closure_matrix.json --reachability module_reachability_c131f07.json` with those packets |

Code on `claude/w4-FMEND` (for the **next** release; **NOT in c131f07**):

- **F-878 wiring:** `GET /api/launch/packet` in `app/main.py`, on the operator credential through
  `security.OPERATOR_GET_ROUTES`. It serves `command_center.launch_packet.view(db)`, which calls
  `launch.packet.build(db, sha=build.commit())`. Test: `tests/test_w4_fmend_packet_route.py`
  (4/4). Regression runs: `test_route_auth_default_deny.py` 7/7 and
  `test_customer_data_auth.py` 9/9.
- **F-834 tooling:** `scripts/emit_runtime_packets.py` with `tests/test_w4_fmend_packets.py`
  (3/3). The emitter claims only what a rehearsal recorded: the producer and live-root receipts
  for rows whose producer is the handler of a job the rehearsal ran. It never writes an
  independent review and refuses a rehearsal from a dirty tree.
- Core tests: `test_compiler`, `test_reverse` and `test_twin` all pass.

## Row status (before -> after) and exact remaining gate

| row | before | after | remaining gate |
|---|---|---|---|
| **F-848** Shadow Rehearsal | OPEN (TESTED/PARTIAL) | OPEN, unchanged | The rehearsal on c131f07 is `complete:false`, the same as on 7421ef6. Of its 14 steps, 11 PASS and `store.publish[shadow]` is REFUSED_AS_EXPECTED. `owner_publication_grant` and `store.publish[past-shadow]` are BLOCKED. None of the `not_complete_because` items can be fixed locally (see below). |
| **F-834** Consumption Required | OPEN | OPEN, unchanged | Packets now exist (10 rows), so "missing run identity" no longer applies to them. All 917 rows are still BLOCKED and 0 are REVIEWABLE. The packet rows still lack durable_state, consumer, decision, effect and result receipts, production_producer, failure_test, the suite receipt and execution_gate (protected rows). An **independent review** is also needed, and the emitter can never supply it. |
| **F-878** Launch Packet | OPEN (INTEGRATED/PARTIAL) | OPEN, unchanged | (b) The packet for c131f07 has been generated and committed. Verdict UNKNOWN: 7/7 products UNKNOWN on the scratch DB, owner queue FAIL with 8 actions, phase shadow (agrees), recorded_suite UNKNOWN. c131f07's packet.py quotes RUN_6f9a2f7, and no release record exists for c131f07. (a) Correction to the matrix's missing_part: on c131f07, `launch/packet.py` **is reached** from a live root (`app/main.py` -> CC router `/api/cc/launch/packet`, W4-CCPACKET; see `module_reachability_c131f07.json`). The operator-gated GET that next_action asks for is on this branch and goes into the next release. To close: a candidate that contains PACKETREL + this route, its release record, and a packet generated against production-shaped state. |
| F-839 Final-Head Re-Audit | OPEN | OPEN | Reachability has been regenerated on c131f07 (evidence dir). Still needed: freeze c131f07 or a successor (F-845) on a green full suite, then aggregate and an independent function-level re-audit on that SHA. |
| F-840 Green Suite Necessary, Not Sufficient | OPEN | OPEN | A final_proof report for c131f07 exists. Still needed: c131f07's own green full-suite record (in progress) cited together with that report, and a report that is not all BLOCKED. |
| F-169 Clean-Tree Full Suite | OPEN | OPEN | Needs `REQUIRE_CLEAN=1 ./run_tests.sh` release-eligible on the final candidate (running on c131f07), then `ops/deploy_guard.py check --candidate <RC> --deployed fcb982d` committed. |
| F-846 Audit-Repair Loop | OPEN | OPEN | DEFECT_LEDGER_7421ef6 is open: D-1 and L-1..L-3 are in flight on w4-AUDITFIX, and the 4 rehearsal blockers below remain. Still needed: a full suite and an independent re-audit on the successor candidate. |

## F-848 `not_complete_because` on c131f07: why none can be fixed locally

1. **`owner_publication_grant` BLOCKED** (`grant_snapshot_refused`): `runtime/etsy_ops.py`
   raises "certified listing taxonomy UNKNOWN; default fallback prohibited". No stored Etsy
   taxonomy snapshot names a node, and none may be assumed. **Gate: external
   `etsy_taxonomy_snapshot`.** It clears when `listing.taxonomy_refresh` runs against Etsy's
   read-only taxonomy, which needs the deployed app's Etsy credentials (PRODUCT_INVENTORY).
   `search_certificate_not_pass` (stored search verdict REFUSED, category UNKNOWN) depends on
   the same gate.
2. **`store.publish[past-shadow]` BLOCKED** (`past_shadow_publish_blocked`). The first cause is
   that there is no grant (item 1). There is also a **latent rehearsal gap**, found here:
   `handle_store_publish` resolves `protected_phase` = the more restrictive of the env and the
   owner's *recorded* phase transition (`core.phase.effective`). The rehearsal sets only
   `BRAMBLELOOP_PHASE=limited_production` and records no transition, so this step would still
   refuse even with a grant. Recording an upward transition needs a ready `launch.assessed` and a
   held rollback rehearsal (`core.phase.EVIDENCE_MUST_PASS_FROM`). So the step clears only after
   item 1 and the owner-gated launch readiness. Fix for the rehearsal script (next release,
   after item 1): record the simulated owner phase transition in its throwaway DB, the same way
   it simulates the grant.
3. **`order_version_unmapped`**: downstream. The fixture receipt has no draft listing id
   to map because nothing was published. It clears with item 2.

## Not done / not claimed

- No row was marked COMPLETE. No overrides were proposed, because no row's completion changes
  under the matrix's rules from this evidence.
- The independent review that F-834/F-840 need has not been done; it must come from a
  different session.
- The committed `research/final_build/module_reachability.json` was left at basis 2f36fe0. The
  c131f07 regeneration sits in the evidence dir until a candidate is frozen.
