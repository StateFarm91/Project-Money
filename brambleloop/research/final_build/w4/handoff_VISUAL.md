# handoff_VISUAL — W4-VISUAL

- Branch: `claude/w4-VISUAL` (worktree `.claude/worktrees/W4-VISUAL`). Latest pushed SHA: see `git log origin/claude/w4-VISUAL -1`.
- Status: `research/final_build/w4/VISUAL_STATUS.md` / `.json`.

## Done
- `visual/gallery_frames.py`: disclosed deterministic frames for MATERIALS, COLOUR_CONTEXT, CONSTRUCTION and SIZING, derived from the certified CIR. The verifier re-derives the facts by an independent path (compiler rows, not twin cells) and redraws the frame. A frame passes only on byte identity plus agreement of the facts. LIFESTYLE and FIT are never drawn.
- `visual/launch_imagery.py`: per Launch-0 listing it builds the disclosed set (all variants) plus the gallery frames, then a job ledger against `eligibility.gallery_jobs_for`. Each missing job carries its exact blocker. `register`/`last` use AuditLog `assets.gallery_frames`. `refresh(db)` skips a listing when it is unchanged.
- `visual/rnd/loop.cycle(imagery=None)`: a whole-catalogue cycle also refreshes the imagery ledger, so the work is reachable from the `visual.rnd.cycle` scheduled job.
- Result: hero ready on all 3 Launch-0 listings. Covered jobs per listing are listed in VISUAL_STATUS.
- R&D loop run in shadow: 2 cycles, 14 experiments, 1 promoted, 6 lessons, 8 GATED_SPEND.

## Tests run
- tests/test_w4_visual_gallery_frames.py (new), tests/test_w3_visual_rnd_loop.py, test_vacuity, test_secret_scan, test_reachability, test_w3_tmp_hygiene.

## WIRING REQUESTS
1. AUTO (`autonomy/visual_rnd_job.summarise`): count `report["launch_imagery"]` refreshed listings in `work_done`.
2. publish/listing_set owner + integrator: `listing_set.disclosed_frames`/`certify_disclosed` should accept verified `assets.gallery_frames` frames (kind `disclosed_gallery_frame`, medium DIGITAL_TWIN_RENDER, alt text with the disclosure). Then `search_evidence.gallery` will see MATERIALS/COLOUR_CONTEXT/CONSTRUCTION/SIZING coverage. `product_authority.structural_floor` needs a branch that calls `gallery_frames.verify`.
3. CC: show `VISUAL_STATUS.json` stage D as PARTIAL (measured), not FAIL.
4. Integrator/product: harvest-table-runner gold #C49545 sits inside the render contract's separation against its raised tone. Change the palette or make a reviewed contract decision. It is not in launch scope.

## Next deterministic actions
- Finish the D re-run with settle and Mitsuba renders (scratch script md2.py) and record whether `stationary` and `images_rendered` clear.
- ANGLE for vessels: add a 60° oblique view that `render_verification` measures.
- Owner: plans P1–P3 in VISUAL_STATUS (CA$1.00 / 2.00 / 1.01).
