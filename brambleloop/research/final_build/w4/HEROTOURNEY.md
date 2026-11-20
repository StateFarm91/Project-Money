# HEROTOURNEY: F-278 hero thumbnail tournament with at least two truthful candidates

Branch `claude/w4-HEROTOURNEY`, based on `origin/claude/w4-INTEG2` 9fd62cc. Stub judges only;
no spend.

## Defect found and fixed

- `creative.grid_tournament` handed the judges each hero's `image_ref`. For a disclosed
  render that is a content address (`sha256:...`).
- `gateway.anthropic._image_block` refuses anything that is neither a URL nor a file. So
  every judge call on a Launch-0 hero failed, and no pod grid containing one could ever be
  judged. This blocks both #126's release half and F-278.

## What changed

- `visual/hero_candidates.py`. Every candidate is verified on its bytes; nothing is
  generated. The candidates per product are:
  - the hero on file, resolved from the artifact store to a local file a judge can be shown;
  - for a vessel (baskets), the disclosed ANGLE view, verified by `render_verification`;
  - for a multi-piece round hero (the coaster set), the same pieces at the Visual R&D
    challenger spacing (`hero_gap_ratio` 0.06), also verified.
  - A flat single piece (blanket, throw) has one candidate and is reported
    `insufficient_candidates`. It is never padded.
- `blinded.render_grid` and `blinded.grid_tournament` place every candidate in the same
  blinded grid.
  - Only cells marked `counts_for_verdict` (the hero on file) feed the pod's #126 verdict.
  - `candidate_scores` reports each candidate's panel scores, read through the key only
    after judging.
- `handle_grid_tournament` records `products[slug]["hero_tournament"]` using
  `hero_candidates.winner`:
  - `decided` with a winner when at least two candidates were fully scored;
  - otherwise `insufficient_candidates` or `unjudged`.

## Acceptance evidence (testslot)

| Test file | Result |
|---|---|
| `tests/test_w4_herotourney.py` (new) | 4/4 |
| test_blinded | 0 fail |
| test_cert_intel_wave2 | 0 fail |
| test_cert_preengineering | 0 fail |
| test_cert_wiring | 0 fail |
| test_w4_autonomy_idle_departments | 0 fail |
| test_vacuity | 0 fail |

## Board row

- F-278: the software item "keeping candidates per product ≥2 at the tournament" is done
  wherever a second truthful candidate exists.
- The judgement still waits on a funded vision provider (owner).
- Flat single-piece products have one truthful hero. A second needs a new verified
  deterministic view or an owned photograph. This is recorded, not padded.

## Checkpoint (2026-10-12, controlled pause)

- Status: **DONE (code); the re-test after the last change is not run.**
- Since the tests above:
  - `handle_grid_tournament` wraps `_grid_tournament_in` in
    `core.workspace.work_dir(prefix="grid-tournament-")`, which is removed on return or on
    raise. The prefix is added to `TEMP_PREFIXES`.
  - IMGFIX is merged in.
- Next step: run test_w4_herotourney, test_blinded and test_cost_governance_wave2, plus the
  required set.

### Correction (same checkpoint)

- Commit f40c7f9 was pushed with merge-conflict markers in `runtime/release.py` and
  `creative/blinded.py`. They came from the IMGFIX/INTEG2 merge, where W4-B2VISION had added
  `resolve_image`, `unresolvable` and `by_product`.
- The next commit resolves both files and keeps both behaviours:
  - candidates plus `unresolvable` for products with no showable candidate;
  - `candidate_scores` plus `by_product`, where only the hero on file speaks for the product,
    so #218 is unchanged.
- An import check passes. **Tests are NOT re-run.**
- Next step: run test_w4_herotourney, test_blinded, test_w4_b2vision (if present),
  test_cost_governance_wave2 and the required set.
