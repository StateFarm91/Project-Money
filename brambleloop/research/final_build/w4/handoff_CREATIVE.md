# Handoff — W4-CREATIVE

- Branch: `claude/w4-CREATIVE` (worktree `/home/user/Project-Money/.claude/worktrees/W4-CREATIVE`)
- Latest pushed SHA: see `git log -1 origin/claude/w4-CREATIVE` (first milestone b9c5e38)
- Mission: Creative Standard 0/11, dominant failure emotional_appeal → diagnose and fix the design process.

## Items → status → evidence
| Item | Status | Evidence |
|---|---|---|
| Root cause of emotional_appeal 11/11 | PROVEN | `CREATIVE_DIAGNOSIS.md`; builder Design lacks function → `concept_from_design` writes `function=""` → critic branch (b) fires for all |
| Gate defect? | NOT-APPLICABLE (no defect; thresholds untouched) | `test_w4_creative_brief.py::test_gate_thresholds_unchanged`, `test_known_bad_candidates_still_rejected` |
| Design process writes emotional briefs | PROVEN | `src/brambleloop/creative/emotional_brief.py`; `audit.briefed_concept` |
| Existing catalogue survival | PROVEN 6/11 needs_taste (was 0/11) | `creative_audit_rerun.json`; dashboard path `dashboard_truth.creative_survivors` → `test_dashboard_reads_the_same_reading` |
| 5 title/motif product-truth conflicts | OPEN-DEFECT (Product decision: retitle/redesign) | `emotional_brief.HELD` |
| New moment-first candidates | PROVEN at concept stage 8/8 needs_taste | `audit_candidates`; `test_new_candidates_are_original_and_survive` |
| Taste (thumbnail legibility, craft impression) | EXTERNAL-GATED (vision judgement; no paid calls in shadow) | `jury.judge` NEEDS_TASTE |

## Tests run
test_w4_creative_brief (8 OK), test_creative (11 OK, defect test now asserts raw reading + needs_taste-only survivors),
test_fin_truth_closure (pass), test_blinded (pass), test_cert_preengineering (0 failures), test_seasonal_transform (pass),
test_prospecting / test_cert_wiring / guards: see final report.

## Wiring requests
- **W4-PIPE**: 8 new concept candidates in `emotional_brief.NEW_CANDIDATES` (housewarming-key-basket,
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
Push; W4-PIPE picks up candidates; Product resolves HELD titles.
