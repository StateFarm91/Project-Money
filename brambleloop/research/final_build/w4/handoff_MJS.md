# Handoff: lane W4-MJS (Mrs J / competitor intelligence)

Branch: `claude/w4-MJS` (from `claude/visual-investigation` fee1cfe). Worktree:
`/home/user/Project-Money/.claude/worktrees/W4-MJS`. Latest pushed SHA: see `git log -1` on
the branch (updated at each commit).

## Done
- Audit of what ran in production (public `/api/audit` GET reads), recorded in MJS_FINDINGS.md.
  `mjs.scan` / `mjs.reviews` / `learning.ingested` run; gallery analysis is stalled because the vision probe
  fails; SERP, panel discovery, benchmark refresh, the mission pipeline, pod capability and the seasonal
  sentinel have never run in production, because deployed `fcb982d` is 666 commits behind.
- `src/brambleloop/intel/findings.py`: gather → synthesize → refresh, plus `latest`, and a
  public-snapshot adapter.
- `runtime/release.py` `_run_mjs_mission` calls `findings.refresh` on every `mjs.scan` run. It sits on
  the existing 2-hourly `mjs_scan` cadence, so no new cadence was needed.
- `intel/market_map.py`: two defects fixed. An unaudited `has_video` now reads None instead of False,
  and an empty `seasonal` is now derived from the title and tags instead of reading "none stated".
- `research/final_build/w4/MJS_FINDINGS.{json,md}` and `mjs/snapshot_findings.py` +
  `mjs/raw_snapshot.json` (aggregates only).
- `tests/test_w4_mjs_findings.py` (4 OK): runtime cadence proof, consumer path (radar.score and
  ideation brief), supersede/idempotence, UNKNOWN≠0.

## Status
- MJs intel continuously productive in shadow: PROVEN on this branch (test plus runtime
  path). It becomes live in production only after a deploy, which is integrator/owner-gated and outside this lane.
- Gallery vision: EXTERNAL-GATED (the vision probe is failing in production).
- SERP capture in production: needs the deploy.
- Rendered Etsy pages: EXTERNAL-BLOCKED (HTTP 403, not scraped).

## Wiring requests
- **AUTO** (`runtime/pipeline.py` productive-keys map): add `"findings"` to the `"mjs.scan"` entry so
  the findings count counts as productive output. Optional; the audit row `mjs.findings` already records it.
- **CC** (`app/main.py`): add a GET `/api/mjs/findings` that returns `intel.findings.latest(db)` for the
  Owner Command Center.

## Next steps to resume
1. Re-run the focused tests listed in the final report.
2. After any production deploy, run `snapshot_findings.py` (online) and confirm an `mjs.findings`
   audit row appears in `/api/audit?action=mjs.findings`.

## Tests run (2026-10-07, all exit 0)
test_w4_mjs_findings 4 OK; test_intel 41; test_cert_mjs 19; test_cert_intel_wave 9;
test_cert_intel_wave2 15; test_vacuity 7; test_secret_scan 7; test_reachability 11;
test_w3_tmp_hygiene 16. Next deterministic action: integrator merge, then the wiring requests above.
