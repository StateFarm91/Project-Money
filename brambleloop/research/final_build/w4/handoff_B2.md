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

## In progress
Ledger generator + dashboard summary from closure (see below once committed).
