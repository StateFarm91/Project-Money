# handoff_VISUAL2 — W4-VISUAL2 (continuation of W4-VISUAL)

- Branch: `claude/w4-VISUAL2` (worktree `.claude/worktrees/W4-VISUAL2`). Latest pushed SHA:
  `git log origin/claude/w4-VISUAL2 -1`. Resumed 2026-10-07 after a session limit from the
  integrator WIP checkpoint e11d2d5 (reviewed; kept).
- Owned: (1) CONTENTS gallery frame producer + certification; (2) harvest-table-runner
  elongated hero/scale; (3) wiring #7 `commerce.search_evidence._category_for`;
  (4) K9 wiring F-753: generated images carry a `gates/stitch_scale` reading.
- Lane RENDER owns multi-piece + round-base renderer fixes (not here).

## Items → status → evidence
| Item | Status | Evidence |
|---|---|---|
| (3) Wiring #7 sizes/colours from certified CIR | **PROVEN** | `tests/test_w4_visual2.py::test_sizes_and_colours_come_from_the_certified_cir`, test_w3_k1_search, test_w3_wire4 |
| (1) CONTENTS frame | **PROVEN** | `visual/contents_frame.py` (3972616); tests `test_contents_frame_is_the_certified_pdf...`, `test_contents_is_certified_through_the_supplement_path...`; runtime proofs `visual/contents_gallery_proof_*.json` + `certified_gallery_proof_launch0_new_2026-10-07.json` |
| (2) harvest-table-runner diagonal hero/scale | **PROVEN** | `render_contract.diagonal_deg` + `render_verification.flat_rotation`/un-rotation (e11d2d5); `test_the_runner_is_drawn_on_the_diagonal...`, `test_a_recoloured_stitch_on_the_diagonal_fails...`; 25 % gate unchanged; Launch-0 hero/scale/detail bytes identical before/after (21 frames, sha256 compared); test_disclosed_render 27/27 |
| (4) K9 F-753 stitch-scale reading on generated frames | **PROVEN** | `visual/product_authority.stitch_scale_reading` + `structural_floor` (every non-disclosed frame carries `stitch_scale`; wrong scale → FAIL ASSET_STITCH_SCALE_WRONG; right scale stays UNKNOWN); `test_a_generated_frame_carries_a_stitch_scale_reading...` |

## Next (deterministic)
- Runtime proof: `PYTHONPATH=src python research/final_build/w4/visual/proof_contents_gallery.py <slugs> <out.json>`
  for harvest-table-runner + remaining certified-gallery releases; then VISUAL_STATUS + CC snapshot
  (`python -m brambleloop.app.command_center.snapshots`), commit, push.
