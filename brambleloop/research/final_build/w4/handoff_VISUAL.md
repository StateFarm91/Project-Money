# handoff_VISUAL — W4-VISUAL

- Branch: `claude/w4-VISUAL` (worktree `.claude/worktrees/W4-VISUAL`), merged with
  `origin/claude/visual-investigation` @ aa2fbbe. Latest pushed SHA: see `git log origin/claude/w4-VISUAL -1`.
- Status: `research/final_build/w4/VISUAL_STATUS.md` / `.json`. Spend: CA$0.

## Items → status → evidence
| Item | Status | Evidence |
|---|---|---|
| A fabric | PROVEN (PASS) | VISUAL_STATUS stage A |
| B assembly | DATA-GATED (benchmark states no neckline/pocket measurements; not a launch dependency) | VISUAL_STATUS stage B |
| C benchmark correspondence | DATA-GATED (needs sample close-ups) | VISUAL_STATUS stage C |
| D local items (stationary, images_rendered) | PROVEN, 12 PASS / 0 FAIL | `visual/milestone_d_hdc_2026-10-07.json` |
| D judged items (7) | EXTERNAL-GATED (owner VB-1 P1, CA$1.00) | same |
| E disclosed path, Launch-0 hero/scale/detail | PROVEN, hero ready on 3/3 | `launch_imagery`, test_w4_visual_gallery_frames |
| Gallery MATERIALS/COLOUR_CONTEXT/CONSTRUCTION/SIZING | PROVEN | `visual/gallery_frames.py`, test_w4_visual_gallery_frames 10/10 |
| ANGLE (vessels) | PROVEN, baskets covered | `disclosed_render` view `angle`, `render_contract.ANGLE_DEG`, test_w4_visual_angle 5/5 |
| CONTENTS | owner of publish.pdf preview path (not a drawing) | wiring request 5 |
| LIFESTYLE x3 / E photographic | EXTERNAL-GATED (VB-1 P2, or sample photos) | VISUAL_STATUS |
| Concept boards for CREATIVE | DEFECT FIXED; 3/6 survivors have boards, 3 refused (palette vs contract) | `creative/board.py`, test_w4_visual_boards 3/3 |
| R&D loop in shadow | PROVEN: 3 cycles, 17 experiments, 1 promoted (retained), 8 rejected, 8 gated, 9 lessons | VISUAL_STATUS rnd_shadow |

## Tests run (all passing)
test_w4_visual_angle 5/5, test_w4_visual_boards 3/3, test_w4_visual_gallery_frames 10/10,
test_disclosed_render 27/27, test_disclosed_render_runtime 3/3, test_w3_visual_rnd_guard 6/6,
test_w4_creative_brief 13, test_creative 11, test_cert_preengineering 19, test_intake 20,
test_vacuity, test_secret_scan, test_reachability (0 failing), test_w3_tmp_hygiene.

## WIRING REQUESTS
1. AUTO (`autonomy/visual_rnd_job.summarise`): count `report["launch_imagery"]` refreshed listings in `work_done`.
2. publish/listing_set owner + integrator: `listing_set.disclosed_frames`/`certify_disclosed` should accept verified
   `assets.gallery_frames` frames (gallery frames + `angle_frames`, disclosed, DIGITAL_TWIN_RENDER) so
   `search_evidence.gallery` sees the coverage. `product_authority.structural_floor` needs branches for
   `gallery_frames.verify` and for view `angle` (its role check already accepts it via VIEWS).
3. CC: show `VISUAL_STATUS.json` stage D as PARTIAL (12 PASS / 7 judge-only UNKNOWN), not FAIL. Show owner decision VB-1.
4. Product/integrator: harvest-table-runner, spooky-garland, pet-snuggle-mat and autumn-oak palettes sit inside the
   render contract's separation, so they get no hero and no concept board. This needs a palette change (Product) or a reviewed contract decision.
5. CREATIVE/publish: `intake.board_for` reads `listing_asset.frames_for`, but `board.make_board` only stores the
   artefact. For catalogue survivors, file the board where `board_for` finds it (or let `board_for` fall back to
   `board/{slug}.png` in ArtifactStore). Then `regate_held` can judge once vision works.
6. CONTENTS job: publish.pdf owner to expose the PDF preview page as a gallery frame.

## Next deterministic actions
- None blocked on this lane's code. Remaining: owner VB-1 (CA$4.76 ceiling), wiring requests above.
- Re-run D proof: `PYTHONPATH=src python <scratch>/md2.py <dir>` (milestone_d.assess('hdc', settle_iterations=4000,
  render_dir, spp=32, save_dir)); ~13 min under load.
