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
- [x] Closure matrix: `closure_matrix.json` (866 rows, adjudicated; pinned by tests/test_final_closure_matrix.py).
- [x] FINAL BUILD BASELINE AUDIT: `FINAL_BUILD_BASELINE_AUDIT.md`.
- [ ] Begin executable launch-critical work.

## Next action
Wave FB-1: execute clusters per audit §6 in isolated worktrees (disjoint ownership), integrate,
re-run `aggregate.py` after each integration (update worker rows via `overrides.json` with
reasons, or re-map the touched rows). Owner packets per audit §9.

## Assignments (2026-09-28, mapping wave M1)
Nine read-only mapping workers, disjoint slices, brief `mapping/MAPPING_BRIEF.md`, uids in
`mapping/s1..s9_uids.json`, outputs `mapping/s1..s9.json`. If a session reset kills them,
re-dispatch only the slices whose output file is missing or fails `json.load`.

## Wave FB-1 (dispatched 2026-09-28, base be8d416, brief `waves/FB1_BRIEF.md`)
Seven implementation workers, one per cluster, each in worktree `.claude/worktrees/fb1-<X>` on
branch `claude/fb1-<X>` (pushed incrementally): **E** owner visibility/security (first: auth on
customer-data reads), **B** Etsy publish/activate/read-back/observation, **A** listing search
truth, **C** product-truth gates, **D** money/order truth, **F** release/supply chain, **G** IP
firewall/originality. Held for later: **H** Visual structural instrument, **I** Learn skeleton,
**J** certification machinery (after merges). On a session reset: check `git ls-remote origin
'claude/fb1-*'` and each branch's `research/final_build/waves/fb1_<X>.json`; re-dispatch only
clusters with no report, telling the new worker to continue from the pushed branch head.
Integration order when reports arrive: F, E (independent) → C, G (certificate) → A → B → D;
full suite from clean state after each batch; re-aggregate the matrix.

## HANDOFF 2026-09-28 ~14:30Z (weekly usage limit)
Authoritative resume document: `FINAL_BUILD_RESUME_MANIFEST.md`. Integrated: F, D, C, E.
Awaiting integration: A (436f6c4, conflict in publish/release_gates.py). In progress at handoff:
B, G (branches pushed; WIP snapshots in waves/wip/). Unstarted: C2, H, I, J.

- 2026-09-28T16:15Z heartbeat (trig_019rtbCKLSFc8hNajuiWm9E4): production `/api/verify` read-only
  check — 12 checks, 0 failing, ok=true (production still fcb982d). Per the owner's handoff
  instruction no implementation wave and no full-suite run were started, and nothing was pushed to
  `claude/repository-setup-nc9x6o` (a push there can redeploy production). Resume per
  `FINAL_BUILD_RESUME_MANIFEST.md`. Note for the next session: `ops/HEARTBEAT_PROMPT.md` still
  points the heartbeat at the production branch; decide whether heartbeats should operate on the
  Final Build branch instead (owner/integrator decision, not changed here).
- 2026-09-29T00:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-09-29T08:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-09-29T16:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-09-30T00:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-09-30T08:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-09-30T16:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-01T00:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-01T08:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
