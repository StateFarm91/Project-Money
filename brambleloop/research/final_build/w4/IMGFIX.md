# IMGFIX: two regressions from the image branches, fixed at the root

Status: **DONE**. Branch `claude/w4-IMGFIX`, based on `origin/claude/w4-INTEG2` 16e36ae.

## The two fixes

1. **Temporary directories leaked (`test_cost_governance_wave2`).**
   - `visual/hero_review.py` and `visual/inspect.identify_at_grid` called `mkdtemp`, and
     nothing removed those directories.
   - Both now use `core.workspace.work_dir`. A supplied `work_dir` is used and never deleted.
   - Their prefixes `hero-review-` and `grid-identify-` are added to
     `ops.health.TEMP_PREFIXES`.
2. **`test_launch` failed 15 tests with "2 piece(s) read at 340 px where the pattern makes 1".**
   - Root cause: MULTIPIECE now draws every piece of a flat set, which is correct; the hero
     really does show 2 or 6 pieces.
   - `disclosed_listing.listing_qa` still expected 1 piece for the flat form.
   - The expectation now reads the CIR's `make` for a single-component flat piece, as it
     already did for rounds.
   - The gate is not loosened. Thresholds are unchanged, and the piece counter is unchanged.

## Tests (testslot)

| Test file | Result |
|---|---|
| test_w4_imgfix (new) | 3/3 |
| test_vacuity | 0 fail |
| test_launch | 0 fail |
| test_cost_governance_wave2 | 0 fail |
| test_cert_listing_frames | 0 fail |
| test_v11_autonomy_timeline | 0 fail |
| test_w4_multipiece | 0 fail |
| test_w4_firstimg | 0 fail |
| test_w4_thumbfloors | 0 fail |
| test_w4_herovision | 0 fail |
| test_search_hero_publish | **1 FAIL**: `LISTING_PRICE_NOT_PLAN` (cloudline CA$9.50 vs plan CA$7.50). The same failure occurs on clean INTEG2; it is the product worker's |

## Next

None. Merge this branch.
