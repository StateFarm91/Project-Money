# Handoff W4-B2 (Build 2 completion)

Branch `claude/w4-B2` (worktree `.claude/worktrees/W4-B2`). Owner: build2/closure.py, maturity.py,
requirements.json mapping, research/final_build/w4/*ledger*.

## Finding 1 (proven) — where the dashboard's "227/320, 45 / 28 / 20" comes from
`build2.requirements.coverage()` served by `/api/build2` (and the `/console` Build-2 tile). Read-only
GET of production `/api/build2` on 2026-10-07 returned exactly
`complete 227, partial 45, owner_gated 28, data_gated 20, percent 70.9`; production `/health`
reports commit `fcb982d` (branch claude/repository-setup-nc9x6o). `git show fcb982d:.../requirements.json`
has those counts (first seen at af3a12f/53227fa, 2026-09-22). So the figure is
(a) STALE: production runs the 2026-09-22 registry; the integrated branch's registry is
covered 218 / partial 85 / owner 9 / data 8 after the 2026-09-27/28 certification reopened rows; and
(b) MISCALCULATED in meaning: `executable_remaining = partial + missing` counts partial rows parked
on owner/data/external gates as executable work, and "complete" is the registry's claim, not proof.

## Finding 2 — closure on current code
`closure.matrix()` at fee1cfe (offline): 218 COMPLETE+PROVEN / 58 OWNER / 37 DATA / 7 EXTERNAL / 0 OPEN.
Re-evaluated with production's live gate readings (/api/build at fcb982d): still 0 OPEN — every
gate open in production (benchmark_observation, etsy_shop, etsy_api, canonical_model, culture_feed)
parks no current row.

## Done (2026-10-07, after container restart)
- Reviewed integrator WIP a5cdc1b: closure.dashboard()/ledger(), #280 colour signals via culture
  feed, browser_vision note corrections -- kept as correct; tests/test_w4_b2_build2_ledger.py 18/18 OK.
- BUILD2_LEDGER.json/.md regenerated (build2_ledger.py + evidence_B2/prod_gates_fcb982d.json):
  PROVEN 215 / NOT-APPLICABLE 3 / OWNER 58 / DATA 37 / EXTERNAL 7 / OPEN-DEFECT 0.
- Note-level scan of all gated rows for executable remainders: found #147 (Content + Seasonal
  Planning never read culture lessons). FIXED: seasonal/daily.culture_lessons,
  growth/content.apply_cultural_timing (+ marketing.schedule call in runtime/release.py);
  tests/test_w4_b2_culture_consumers.py 9/9 OK.
- B2_OPEN_CLUSTERS.json: before OPEN 2 (#147, #280) -> after 0.
- Tests run (all rc=0): test_w4_b2_build2_ledger, test_w4_b2_culture_consumers, test_colour,
  test_culture_feed, test_cert_growth_seasonal, test_cert_improve_wave, test_cert_growth_ops,
  test_build2, test_closure, test_vacuity, test_secret_scan, test_w3_tmp_hygiene, test_reachability.

## WIRING REQUEST (lane CC, app/main.py)
1. `/api/build2`: add `"reconciled": closure.dashboard(db)` and label `coverage` as
   "registry claim (not proof)". 2. `/console` `_build2()` tile: headline from
   `closure.dashboard(db, m=closure.matrix(db))` (it already computes matrix -- reuse it):
   complete/proven/NA, owner/data/external gated, executable_remaining = OPEN only; demote
   `reqs.coverage()` cards to a "registry claim" row. Production also needs a redeploy (owner
   decision) -- it serves fcb982d's 2026-09-22 registry, which is why the owner sees 227/45/28/20.

## Remaining
None executable in B2 scope; every non-PROVEN row is parked on a named gate (ledger `gate`).
Next action if resumed: none beyond integrator merge + CC wiring.
