# Handoff — W4-RENDER (disclosed renderer: multi-piece + round magic-ring pieces)

- Branch `claude/w4-RENDER` (worktree `.claude/worktrees/W4-RENDER`), from origin/claude/visual-investigation
  (already contains w4-PIPE2), merged `origin/claude/w4-VISUAL` (gallery_frames / launch_imagery / angle view).
- Latest pushed SHA: see `git log -1 origin/claude/w4-RENDER` (resumed 2026-10-07 after session limit at a860302).

## Resume status (2026-10-07, after session limit) — DONE this session
- Reviewed integrator WIP a860302 (pencil roll: panel height = rows above the self-seam fold, tie placed by its
  seam) — correct; tests pass. Merged origin/claude/visual-investigation (VISUAL2 CONTENTS frame, K9) cleanly.
- Fix 9: `visual/gallery_frames` CONSTRUCTION for multi-piece CIRs (one stitch-count profile per piece, make, rows,
  widest row, join count; producer = twin cells, verifier = compiler rows; single-piece path byte-identical,
  VERSION unchanged). Test `test_w4_render_assembled.test_multi_piece_construction` (verify PASS, layout QA clean,
  tampered facts FAIL) for stocking, pencil roll, tea cosy, garland.
- `render_run.py`: per-product required gallery-job ledger (`eligibility.gallery_jobs_for` by search category;
  covered only by frames verified on their bytes vs the certified CIR; ANGLE attempted + verified); gallery frames
  are also produced for the refused garland. RENDER_STATUS + the 5 PIPELINE_BACKLOG rows refreshed.
- Tests run (all pass): test_w4_render_assembled, test_w4_render_corners, test_w4_visual_gallery_frames (10/10),
  test_w4_visual_certified_gallery (7/7), test_vacuity, test_secret_scan, test_reachability, test_w3_tmp_hygiene.

## Row status (5 products)
| product | hero/scale/detail | gallery covered | status / exact gate |
|---|---|---|---|
| housewarming-key-basket | PASS/PASS/PASS (+ANGLE PASS) | all but CONTENTS, LIFESTYLE | DATA-GATED: Launch-0 registry promotion (D-FB-7, catalogue); CONTENTS needs a release PDF; LIFESTYLE owner-spend/photo |
| first-christmas-stocking | assembled UNKNOWN / UNKNOWN / PASS | MATERIALS, COLOUR_CONTEXT, CONSTRUCTION, DETAIL | OPEN: assembled-frame verifier (VISUAL) + Launch-0 promotion; loop not drawn (fold note-only, PIPE CIR); ANGLE not drawn for assembled |
| mothers-day-heart-tea-cosy | assembled UNKNOWN / UNKNOWN / PASS | MATERIALS, COLOUR_CONTEXT, DETAIL | OPEN: assembled-frame verifier (VISUAL) + Launch-0 promotion |
| teacher-chevron-pencil-roll | assembled UNKNOWN / UNKNOWN / PASS | MATERIALS, COLOUR_CONTEXT, DETAIL | OPEN-DEFECT: 340 px legibility hero 10% / scale 12% coverage (< 25%) — the flat object is 92 x 13 cm (60 cm tie straight out); no truthful flat layout reaches 25% (tie turned down: ~23%); gate = CIR design (PIPE: shorter/two ties) or a reviewed depiction rule for free ties. Gate NOT relaxed |
| snowfall-advent-garland | refused (thumb + cord placement note-only) | MATERIALS, COLOUR_CONTEXT (+CONSTRUCTION supporting) | OPEN: CIR structure for thumb-in-opening and cord threading (PIPE2) |

## Next deterministic action
`cd brambleloop && TMPDIR=/home/user/bl-tmp-RENDER PYTHONPATH=src .venv/bin/python research/final_build/w4/render_run.py`
after any CIR/verifier change by PIPE/PIPE2/VISUAL; nothing else in-lane is unblocked.

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
