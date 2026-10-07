# Handoff — W4-RENDER (disclosed renderer: multi-piece + round magic-ring pieces)

- Branch `claude/w4-RENDER` (worktree `.claude/worktrees/W4-RENDER`), from origin/claude/visual-investigation
  (already contains w4-PIPE2), merged `origin/claude/w4-VISUAL` (gallery_frames / launch_imagery / angle view).
- Latest pushed SHA: see `git log -1 origin/claude/w4-RENDER` (resumed 2026-10-07 after session limit at a860302).

## Resume status (2026-10-07)
- a860302 (integrator WIP): pencil roll now RENDERS assembled — panel height = rows above the self-seam fold (row 11),
  tie placed by its seam. Under review; next: merge origin/claude/visual-investigation (raised-stitch tone step +
  released-version verification), rerun focused tests, re-run render_run.py, fix pencil roll 340px legibility
  (hero/scale False), garland (2 round pieces refused), refresh PIPELINE_BACKLOG rows.
- Next command: `cd brambleloop && PYTHONPATH=src .venv python tests/test_w4_render_assembled.py`

## Fixes
1. `cir/geometry.corners`: magic-ring opening rounds (>half of the round below increase-produced) are evidence for
   neither shape; a circle needs >=2 judged rounds all unstacked. Polygon verdicts unchanged; mixed shapes still None.
   Catalogue diff: only None->0 for key basket, tea cosy, ring pillow (top+bottom). `tests/test_w4_render_corners.py`.
2. `visual/disclosed_render`: vessel wall rounds drawn as tall as their stitches (`_wall_levels`; all-sc walls
   byte-identical) and relief posts on wall tiles (`_post`; market baskets are all-sc, unchanged). Was: relief walls
   drawn at sc height while the scale view lettered the twin's taller height.
3. `visual/render_verification`: per-row wall heights (gauge arithmetic, dimension line, wall height); new
   `_verify_round_vessel` (0-corner vessels: exact counts in a central band cut between stitch centres, colours,
   angular pitch, diameter, height) — was UNKNOWN; `body_component` + `expected_model(cir, component)`: a
   multi-piece CIR's detail frame is verified as its body piece; assembled hero/scale are UNKNOWN (fail-closed).
4. NEW `visual/assembled_render.py`: multi-piece hero/scale composed only from named-edge planar Seams, mirrored
   back layers (proven, hidden), rings (front rows only), structured folds, resumed Holds; unplaceable pieces listed as
   `not_drawn`; detail = body piece via the single-piece renderer. Version `disclosed-render-assembled/1.0.0` is NOT in
   `product_authority.QUALIFIED_RENDERERS` → assembled frames' structural truth UNKNOWN until a verifier measures them.
   `tests/test_w4_render_assembled.py`.
5. `visual/render_contract.annotation_lines`: form "assembled" scale line.
6. `publish/disclosed_listing`: alt text for assembled frames; `listing_qa` models a multi-piece CIR (body piece +
   all pieces' colours for 340 px legibility; asset truth depicts the drawn pieces).
7. `visual/gallery_frames` (VISUAL's): MATERIALS / COLOUR_CONTEXT for multi-piece CIRs (every piece x make, two
   independent count paths); CONSTRUCTION stays single-piece.
8. `products/pipeline_board._visual` (PIPE's): next-step texts name the real refusal (palette contract / unplaced
   pieces / unnamed outline) and the assembled-verifier gate.

## Products → stage → next gate
See `RENDER_STATUS.{json,md}` (written by `research/final_build/w4/render_run.py`) and the 5 rows in PIPELINE_BACKLOG.

## WIRING REQUESTS
- Catalogue/integrator: promotion to Launch-0 registry (D-FB-7 authority) is what turns rendered frames from UNKNOWN to
  verified; key basket hero/scale/detail/angle already PASS the verifier against its CIR.
- W4-PIPE/PIPE2 (CIR): garland — thumbs (into the chain-span opening) and cord threading are note-only; add structure
  or accept a per-piece set. Pencil roll — gold #C49545 vs its relief shade is 39.4 < MIN_SEPARATION 40 (palette or
  reviewed contract decision); also its tie is placed at rows 12-14 (behind the folded pocket) while the note says
  "just above the pocket". Stocking — the hanging loop's fold is only in the note (not drawn).
- Visual verifier owner: measure assembled frames (re-derive placement from the CIR) so assembled hero/scale can PASS.
