# Handoff — W4-CREATIVE

- Branch: `claude/w4-CREATIVE` (worktree `/home/user/Project-Money/.claude/worktrees/W4-CREATIVE`)
- Latest pushed SHA: see `git log -1 origin/claude/w4-CREATIVE` (milestones b9c5e38, 635c142, a6ac61a, r2 docs)
- Mission: Creative Standard 0/11, dominant failure emotional_appeal → diagnose and fix the design process.

## Items → status → evidence
| Item | Status | Evidence |
|---|---|---|
| Root cause of emotional_appeal 11/11 | PROVEN | `CREATIVE_DIAGNOSIS.md`; builder Design lacks function → `concept_from_design` writes `function=""` → critic branch (b) fires for all |
| Gate defect? | NOT-APPLICABLE (no defect; thresholds untouched) | `test_w4_creative_brief.py::test_gate_thresholds_unchanged`, `test_known_bad_candidates_still_rejected` |
| Design process writes emotional briefs | PROVEN | `src/brambleloop/creative/emotional_brief.py`; `audit.briefed_concept` |
| Existing catalogue survival | PROVEN 6/11 needs_taste (was 0/11) | `creative_audit_rerun.json`; dashboard path `dashboard_truth.creative_survivors` → `test_dashboard_reads_the_same_reading` |
| 5 title/motif product-truth conflicts | OPEN-DEFECT (Product decision: retitle/redesign) | `emotional_brief.HELD` |
| New moment-first candidates (jury) | PROVEN 8/8 needs_taste | `audit_candidates`; `test_new_candidates_are_original_and_survive` |
| New candidates, FULL pre-engineering gate | PROVEN 8/8 waiting, 0 failed (was 8/8 refused) | `emotional_brief.gate_candidates`; `test_candidates_fail_no_deterministic_check`, `test_without_the_design_brief_the_same_gate_refuses`; `creative_gate_r2.json` |
| What clears needs_taste | PROVEN (measurable gate, not owner review) | `emotional_brief.NEEDS_TASTE_CLEARS`; `test_needs_taste_clears_only_on_a_recorded_judgement`; CREATIVE_DIAGNOSIS r2 |
| Existing products re-audited with corrected process | PROVEN at runtime | cadence `persist_catalogue_audit` + `dashboard_truth.creative_survivors` on temp DB → 6/11 (creative_gate_r2.json) |
| MJS demand evidence | PROVEN (cited by digest; proxy labelled) | `emotional_brief.MJS_FINDINGS`/`DEMAND_FIT`; `test_demand_is_cited_never_invented` |
| Taste (thumbnail legibility, craft impression) | EXTERNAL-GATED: board (needs CIR → twin board, or image gen) + vision_usable + concept.judged ≥3.5 | `jury.judge`, `intake.judge_held/regate_held` |
| Anti-clone novelty vs competitors | DATA-GATED (production DB has 441 BenchmarkListing rows; shadow none) | `preengineering._novelty` |

## Tests run
r2: test_w4_creative_brief (13 OK), test_cert_preengineering (0 failures), test_creative, test_intake, test_vacuity, test_secret_scan, test_reachability (0 failing), test_w3_tmp_hygiene — all pass.
test_w4_creative_brief (8 OK), test_creative (11 OK, defect test now asserts raw reading + needs_taste-only survivors),
test_fin_truth_closure (pass), test_blinded (pass), test_cert_preengineering (0 failures), test_seasonal_transform (pass),
test_prospecting / test_cert_wiring / guards: see final report.

## Wiring requests
- **W4-PIPE**: engineer in `gate_candidates()['engineering_queue']` order (first-christmas-stocking first); briefs incl. `GATE_BRIEFS`. 8 new concept candidates in `emotional_brief.NEW_CANDIDATES` (housewarming-key-basket,
  reading-nook-cable-wrap, first-christmas-stocking, mothers-day-heart-tea-cosy, teacher-chevron-pencil-roll,
  heart-row-ring-pillow, snowfall-advent-garland, spring-garden-kneeler) need CIR engineering; only
  teacher-chevron-pencil-roll is flat_rows (builder-capable today). Briefs carry premise/function/laura_scene.
- **Product / listing owner**: retitle or redesign the 5 HELD products (proposed titles in `HELD`); once retitled,
  add a brief to `CATALOGUE_BRIEFS` and they rejoin the gate.
- **CC**: `_creative` could add rows for `report["raw_generator"]` survivors and `report["briefs"]["held"]`
  (the dashboard already shows the new survivor count without change). Survivors read `needs_taste`, not approved.
- `catalogue_concepts()` (raw) is still what other consumers (release, seasonal, prospecting sameness) use;
  switching them to `briefed_catalogue_concepts()` is a follow-up for their owners.

## Next deterministic action
Lane work complete. External: CIR for queued candidates (W4-PIPE) → `board.make_board` → vision probe ok (owner credential/spend) → `regate_held` cadence judges and re-presents. Product: retitle the 5 HELD. Re-run proof: `PYTHONPATH=src python <scratch>/proof.py research/final_build/w4/creative_gate_r2.json` (script body in r2 commit message context: persist_catalogue_audit + dashboard_truth.creative_survivors + emotional_brief.gate_candidates on a temp sqlite DB).
