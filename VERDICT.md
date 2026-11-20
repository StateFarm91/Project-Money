VERDICT: SHIP 82b947622bee4f05d5da145d49b7d681be724946

Unit: origin/eng/benchbuy @ 82b947622bee4f05d5da145d49b7d681be724946, merged into origin/claude/w6-INTEG3 (39b92619).

## Merge
Conflicts in BUILD_STATE.md and DECISION_LOG.md (both-sides doc appends; kept both) and autonomy_map.json (regenerated via `python3 -m brambleloop.autonomy.map --write`; the committed map must be regenerated on merge, since the base map and the unit's map each add a cadence and handler). Nothing in code conflicted.

## Suites on the merged tree (all green)
- test_benchbuy: ALL PASSED (17 tests)
- test_v11_pwa_static: 84 passed, 0 failed
- test_v11_pwa_browser: 236 passes, 0 failures
- test_s4_p0_board: 0 failed
- test_route_auth_default_deny: 8/8
- test_w4_resume_runner: all OK
- test_v11_autonomy_timeline: PASS after regeneration (fails before it, as expected after a merge)
- test_vacuity: all OK
(Dependencies were installed from requirements.txt to run the DB-backed suites.)

## Findings
- Coverage and quotas: all nine watchlist shops are iterated. Quota is 3 per shop and 5 for MadelineMaeCo. Gap and demand facets rank ahead of the old facets. Digital means `listing_type == "download"` plus a pattern word; unobserved is excluded as `digital_status_unknown`.
- Budget: ceiling = SET_BUDGET_CAD (300) minus recorded BenchmarkProduct spend. Every price is checked at x1.158. Owned items are excluded. The reserve for a first pick per shop falls back to a plain cap check, so the ceiling is never exceeded.
- No auto-purchase path: the module has no network, enqueue or checkout code. The test also runs the selection with sockets disabled. Selection reads BenchmarkListing metadata only.
- Visibility: a shop with no listings is shown with a counted reason. No scan data gives UNKNOWN and no card is raised.
- Owner card: one consolidated card (key benchmark_shopping:set), restated in place and closed when nothing is left. The panel has no button, form or POST; route-auth default-deny passes, so it is owner-auth.

## Mutations (each caught by the unit's tests)
- Budget cap loosened (budget*3): 2 tests fail.
- Quota raised (3 to 9): variety/quota test fails.
- Contingency set to 1.0: budget test fails.
- "import urllib" added to the module: test_no_auto_purchase_path_exists fails.

## sw.js
The unit does not touch sw.js. The merged tree is at `cc-shell-v35`, so there is no VERSION collision from this unit. The next number is v37 per the batch note. (The brief says batch 13 is at v36 but this base reads v35. Whoever bumps next should take v37 and check for a collision when merging.)
