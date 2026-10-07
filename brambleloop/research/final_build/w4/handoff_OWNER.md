# W4-OWNER handoff (owner-action hygiene + incidents)

Branch `claude/w4-OWNER` (worktree .claude/worktrees/W4-OWNER). Latest pushed SHA: `git log -1 origin/claude/w4-OWNER`.

## Done
- Mission B (56ca423): incidents close by rule (`incident_lifecycle.close_duplicates`,
  `close_recovered_cadences`, run on every ops.health truth sweep), remediation owners for every
  production family, backlog close carries resolved_at, coherent seasonal resolution text.
  Test: tests/test_w4_owner_incidents.py (production 18 reproduced: 17 close by rule, backlog true).
- Mission A (1ade34d WIP, reviewed + kept): owner_queue DECISIONS/BATCHES/batch_cards;
  approval_inbox `batches` + `company_opened_not_owner`; UNKNOWN cost None never CA$0; minutes from
  table not invented 10; readiness etsy_shop reads executor gate (no re-ask of an existing shop;
  payout becomes KYC/payout/tax confirmation); trademark knock-out search = company work.
  Test: tests/test_w4_owner_actions.py (5 OK).
- Docs generator: research/final_build/w4/owner/build_owner_docs.py -> OWNER_ACTIONS.{md,json},
  INCIDENTS.{md,json} (store items vendored from INTEG 7631026; visual plans from VISUAL 32332f5).

## Also done (2026-10-07 resume)
- OWNER_ACTIONS.{md,json}: 45 asks -> 25 decisions / 9 batches (~196 min). Store OA-* folded
  (OA-A1 -> transactions_scope, OA-LAUNCH -> leave_shadow, OA-A2 -> company work, OA-STATS
  deferred); visual P1-P3 = one CA$4.01 decision. B2 ledger 58 OWNER-GATED rows: 54 placed on
  exactly one decision, 4 (#242-245) returned to company work; 7 mislabelled rows recorded
  under `mislabelled_company_work` (owning lane B2/growth; ledger mapping is B2's file).
- INCIDENTS.{md,json}: 18 -> 17 closed by rule, 1 true (provenance backlog, company work);
  policy_stale remediation owner corrected owner -> company (test_w3_k7_ops_truth updated).
- owner_queue: `browser_worker` decision for gate rendered_pages (batch infra).
- Tests run (all pass): test_w4_owner_actions 6, test_w4_owner_incidents 6, test_w3_wire4 13,
  test_w3_k7_owner_queue 10, test_w3_k7_ops_truth 16, test_rc1_own_packet 2, test_rc1_own_closer 2,
  test_launch 28, test_fb4_launch 9, test_fb4_ops 12, test_cert_rebuild_chain 10, test_access 8,
  test_w3_k4_launch_verdict 16, test_vacuity, test_secret_scan, test_reachability,
  test_w3_tmp_hygiene.

## Next deterministic action
1. When W4-GATESI / W4-GATESB push, vendor their files and regenerate:
   `git show origin/claude/w4-GATESI:brambleloop/research/final_build/w4/GATE_CLEARANCE_INFRA.json > research/final_build/w4/owner/gate_clearance_infra.json`
   `git show origin/claude/w4-GATESB:brambleloop/research/final_build/w4/GATE_CLEARANCE_BUSINESS.json > research/final_build/w4/owner/gate_clearance_business.json`
   then `PYTHONPATH=src .venv/bin/python research/final_build/w4/owner/build_owner_docs.py`;
   check `gate_clearance.unmapped` (second_market_benchmark has no decision yet: GATESB decides
   whether it is company work) and rerun tests/test_w4_owner_actions.py.
## Wiring requests
- STORE lane: emit its OA-* items as OwnerAction rows (producer `store.*`) so the runtime inbox
  batches them; until then they live in OWNER_ACTIONS.json only.
- B2 lane: reclassify #242-245 (DATA-GATED on orders, not ad_authority), split #165/#54/#10
  per OWNER_ACTIONS.json `mislabelled_company_work`; map tests for #254 #263 #37 #14 #16 #9 #51.
- CC lane: render `approval_inbox()["batches"]` (decision packet) in the approvals view.
