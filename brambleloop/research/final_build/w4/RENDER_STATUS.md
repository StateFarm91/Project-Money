# W4-RENDER — VISUAL-blocked candidates rendered (shadow)

Generated 2026-10-07T04:11:16+00:00 at `82e011d` by `research/final_build/w4/render_run.py`. Publication is never advanced.

| candidate | made | frames (form) | verifier vs certified CIR | gallery | listing QA | board stage | next gate |
|---|---|---|---|---|---|---|---|
| first-christmas-stocking | True | hero (assembled), scale (assembled), detail (flat) | hero UNKNOWN, scale UNKNOWN, detail PASS | MATERIALS PASS, COLOUR_CONTEXT PASS | all pass | VISUAL UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 products; promotion is a catalogue decision, see backlog notes) |
| mothers-day-heart-tea-cosy | True | hero (assembled), scale (assembled), detail (rounds) | hero UNKNOWN, scale UNKNOWN, detail PASS | MATERIALS PASS, COLOUR_CONTEXT PASS | all pass | VISUAL UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 products; promotion is a catalogue decision, see backlog notes) |
| snowfall-advent-garland | False | — | — | — | — | VISUAL FAIL | renderer refused: snowfall-advent-garland: 2 round pieces; only one round body with resumed panels is drawable assembled |
| teacher-chevron-pencil-roll | True | hero (assembled), scale (assembled), detail (flat) | hero UNKNOWN, scale UNKNOWN, detail PASS | MATERIALS PASS, COLOUR_CONTEXT PASS | {'layout_qa': False, 'asset_truth': True, 'frame_set': True, 'mobile': True, 'hero_thumbnail': True, 'legibility_340': {'hero': False, 'scale': False, 'detail': True}} | VISUAL UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 products; promotion is a catalogue decision, see backlog notes) |
| housewarming-key-basket | True | hero (rounds), scale (rounds), detail (rounds) | hero PASS, scale PASS, detail PASS | MATERIALS PASS, COLOUR_CONTEXT PASS, CONSTRUCTION PASS | all pass | VISUAL UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 products; promotion is a catalogue decision, see backlog notes) |

Assembled frames: pieces placed only by the CIR's named-edge joins, hidden mirror back layers, structured folds and resumed holds (`visual.assembled_render`); what cannot be placed is listed per frame as not drawn.
- **first-christmas-stocking**: drawn ['leg_front', 'foot_front', 'cuff', 'toe_front']; hidden ['foot_back', 'leg_back', 'toe_back']; not drawn {'loop': 'its seam note folds it, and the fold is not a structured join, so its finished shape is not derivable'}
- **mothers-day-heart-tea-cosy**: drawn ['cosy', 'front', 'back']; hidden []; not drawn {}
- **teacher-chevron-pencil-roll**: drawn ['panel', 'tie']; hidden []; not drawn {}
