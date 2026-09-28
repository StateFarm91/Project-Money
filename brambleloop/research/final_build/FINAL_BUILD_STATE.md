# FINAL BUILD — durable state (context is a cache; this file is the memory)

Read this first after any compaction/restart (F-861..F-864).

## Fixed facts
- Canonical spec: `spec/09_Brambleloop_FINAL_Master_v1.0_Audited.pdf` (sha256 526ed69c…a99);
  text extract `research/final_build/master_v1.0.txt`.
- Certified engineering baseline (F-841): `claude/visual-investigation` @ **019ebf0**
  (5,242 passing / 285 suites / 0 failing; closure 218 C+P, 0 OPEN, 58 owner, 37 data, 7 external).
- Production: **fcb982d** (== origin/claude/repository-setup-nc9x6o). Build 2 not merged or deployed.
- Final Build working branch: `claude/visual-investigation` (commits after 019ebf0). The
  designated `claude/repository-setup-nc9x6o` stays at production fcb982d: pushing there is a
  production merge, which is not authorized.
- Visual V1 NOT LOCKED. Visual V2 R&D frozen at `codex/visual-v2-rnd` @ 035ff0c (B+C).
- Not authorized: production merge, Railway deploy, Etsy publication, live listings, ads,
  paid API spend beyond existing authority, banking/KYC, irreversible external actions.

## Phase 0 progress
- [x] Baseline verified (019ebf0 == origin, clean tree).
- [x] Master read in full (F-001..F-879, supersessions s78-79 and s91).
- [x] Machine-readable registry: `master_registry.json` via `parse_master.py`, pinned by
      `tests/test_final_master_registry.py`. 866 records / 859 distinct IDs / F-631..F-650 absent
      (numbering jump v0.18→v0.19) / F-514..F-520 defined twice (v0.15 and v0.16; both kept as
      `F-5xx@v0.15` and `F-5xx@v0.16`).
- [x] Module evidence: `module_reachability.json` (live-root reachability on 019ebf0 + presence in
      production tree fcb982d) for 378 modules.
- [ ] Closure matrix: F-req → maturity/producer/state/consumer/effect/tests/gate/next action.
- [ ] FINAL BUILD BASELINE AUDIT document.
- [ ] Begin executable launch-critical work.

## Next action
Map every registry record to evidence (slices under `research/final_build/mapping/`), then
aggregate into `closure_matrix.json` and `FINAL_BUILD_BASELINE_AUDIT.md`.

## Assignments (2026-09-28, mapping wave M1)
Nine read-only mapping workers, disjoint slices, brief `mapping/MAPPING_BRIEF.md`, uids in
`mapping/s1..s9_uids.json`, outputs `mapping/s1..s9.json`. If a session reset kills them,
re-dispatch only the slices whose output file is missing or fails `json.load`.
