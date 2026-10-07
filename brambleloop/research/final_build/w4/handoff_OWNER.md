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

## Next deterministic action
1. After related tests finish (one at a time):
   `cd brambleloop && TMPDIR=/home/user/bl-tmp-OWNER PYTHONPATH=src /home/user/Project-Money/brambleloop/.venv/bin/python research/final_build/w4/owner/build_owner_docs.py`
2. Run test_w4_owner_incidents, test_vacuity, test_secret_scan, test_reachability, test_w3_tmp_hygiene.
3. Commit + push; delete /home/user/bl-tmp-OWNER.

## Wiring requests
- STORE lane: emit its OA-* items as OwnerAction rows (producer `store.*`) so the runtime inbox
  batches them; until then they live in OWNER_ACTIONS.json only.
- CC lane: render `approval_inbox()["batches"]` (decision packet) in the approvals view.
