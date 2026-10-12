# Wave-3 lane K10 — Learn residuals (F-799, F-801, F-805, F-806, F-826)

Branch `claude/w3-K10` from `claude/v11-CANON` @ f0c2d12; merged `claude/visual-investigation` @ cfb19b5
(lanes A,B,E,G,H,I,K,K3,CANON,INT3) with no conflicts — no other lane touched learn/** or improve/**. Worktree `.claude/worktrees/W3-K10`.
Shadow phase, no network, no spend. No shared file edited (app/main.py already mounts
`learn.api.router`; `runtime/worker.py` already has the `learn.scan` and `improve.measure`
cadences).

## Rows

| Row | Status | Evidence (test in `tests/test_w3_k10_learn.py`) | Runtime consumer |
|---|---|---|---|
| F-799 Learn Department | COMPLETE | `test_f799_department_metrics_are_derived_from_rows`, `test_f799_learn_is_an_improvement_cell_measured_nightly`, `test_f799_runtime_consumers_carry_learn_metrics`, `test_f799_metrics_route_is_editor_only` | `learn.scan` handler (`learn/runtime.py`, hourly cadence) audits `metrics` each run; `improve.measure` (daily cadence) records the new `learn` cell via `measure_learn`; `learn.improvement_status.summary()["department"]` (Command Center provider `improvement`); `GET /api/learn/metrics` (editor auth) |
| F-801 Pattern-to-Lesson Trigger | COMPLETE | `test_f801_finishing_seaming_blocking_and_gauge_change_are_topics`, `test_f801_real_launch0_pattern_creates_finishing_gaps_through_scan` (real Launch-0 `basket_small` CIR), `test_f801_toy_cir_without_components_is_unchanged` | `learn.service.scan` (worker `learn.scan`) now uses `pattern_topics`; same function feeds PDF/listing/support help links |
| F-805 Education Product Truth | COMPLETE | `test_f805_*` (6 tests: wrong row total refused, edited text refused by reverse compiler, taught stitch/hook/yarn reconcile, UK terms, stored tamper loses eligibility) | `validate_spec` → `save_lesson` / `eligible` (gates public read, help links); `GET /learn/{slug}` serves `swatch_instructions` written from the compiled CIR |
| F-806 Technique Visual Truth | COMPLETE (diagrams); photos refused | `test_f806_dc_diagram_drawn_as_sc_fails`, `..._wrong_insertion_point_wrong_post_and_orientation_fail`, `..._every_supported_diagram_verifies_and_is_deterministic`, `..._lesson_assets_refuse_photos_generic_images_and_other_stitch_diagrams`, `..._public_route_serves_only_verified_declared_diagram`, `..._human_visual_attestation_is_still_required` | `validate_spec` asset rules; `GET /learn/{slug}/technique/{stitch}.svg` re-renders + verifies before serving (fail-closed 404) |
| F-826 No Content Mill | COMPLETE | `test_f826_draft_without_source_backed_gap_is_refused_422` (the missing 422 test, incl. mixed real+filler topics), `test_f826_scan_never_generates_and_watches_when_all_covered` | `PUT /api/learn/lessons/{slug}` gap check; `scan` decision WATCH |

## What changed

- `learn/service.py`: `pattern_topics()` (fasten-off/weave-in, blocking flat vs upright from
  `cir.geometry` as the writer uses, seam methods, stuffing, colour change, magic ring, holds,
  per-component gauge change); `_asset_problems()` (asset kinds `prose` | `technique_diagram`;
  any other kind or a prose asset claiming `illustrates` is refused; a diagram must hash to
  the canonical generated diagram, be Brambleloop-original, and show a stitch the steps teach);
  swatch check wired into `validate_spec` (fail-closed on exceptions).
- `learn/swatch.py` (new): swatch = CIR; every row declares its total; `compile_cir` clean;
  writer text reverse-compiles clean; optional supplied text must reverse-compile too.
- `learn/technique.py` (new): canonical working sequences for sc/hdc/dc/tr (both/front/back
  loop) and fpdc/bpdc; deterministic SVG; `verify()` re-derives loops-on-hook per panel,
  yarn-overs, insertion point (by drawn position vs the drawn stitch top/post) and
  direction of work from the drawn primitives — labels are not trusted.
- `learn/metrics.py` (new): metrics (gap counts, coverage, oldest queued age from source-row
  timestamps, `None` when undatable), weekly review calendar (`basis: planned`), learn-cell
  experiments; `summary()` UNKNOWN on empty DB.
- `learn/api.py`: `/api/learn/metrics`, diagram route, swatch text + diagram links on public read.
- `learn/runtime.py`, `learn/improvement_status.py`: metrics carried by scan audit and provider.
- `improve/cells.py` + `measure.py` + `freshness.py` + `profiles.py`: 13th cell `learn`
  (`lesson_gap_coverage`, higher is better), measurer, OPERATIONAL world, agent `learn`.
- `improve/governance.py` / `invariants.py`: `learn` added to the protected-constant packages
  (stricter only; test proves every launch policy loop's own tunable still passes).
- Existing tests that hard-coded the cell count 12 now use 13 / `len(cells.CELLS)` (same
  checks, new cell): `test_measure.py` (2), `test_improve.py` (3), `test_improve_director.py`
  (2), `test_improve_handlers.py` (2). No assertion removed or loosened.

## Tests

`tests/test_w3_k10_learn.py`: 23 OK, 0 FAIL (post-merge). test_vacuity 0 FAIL (one loop got a
non-emptiness assertion), test_secret_scan 0 FAIL.

Regression (focused, this worktree, re-run after the merge): test_learn_launch 13, test_learn_input_shapes 3 (unittest),
test_learn_publish_contract 3, test_v11_learn_loops 18, test_fb4_lc 16, test_measure 7,
test_freshness 24, test_profiles 16, test_improve 32, test_improve_director 14,
test_improve_handlers 8, test_cert_learning 15, test_cert_improve_autonomy 20,
test_teardown_audits 21, test_cert_residue 6 — all 0 FAIL. test_cert_wiring 16/16 and test_route_auth_default_deny 7/7 (post-merge).

## Not verified / limits

- Diagram verification checks the structure of our generated SVG, not pixels or photos; a
  photograph still cannot be verified, so it is refused rather than served. Human
  `visual_accuracy` attestation remains required (not loosened).
- Stitches without a canonical sequence (bobble, cables, star family, slst, ch, inc/dec) get no
  diagram; a lesson for them cannot carry one.
- "Adequately covered" is still exact-topic coverage by an approved lesson; search
  opportunities are not yet a gap source (post-launch, per mapping).
- Calendar capacity (2/week) is a planning constant, not measured throughput.

## Wiring requests

None required. Optional (lane F): render `improvement.department` (Learn metrics/calendar) on
the Command Center improvement tab.
