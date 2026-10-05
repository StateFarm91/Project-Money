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
- 2026-10-01T16:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-02T00:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-02T08:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-02T16:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-03T00:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-03T08:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-03T16:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-04T00:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-04T08:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-04T16:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-05T00:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.
- 2026-10-05T08:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing [], ok=True. Handoff mode: no work started, nothing pushed to the production branch.

## RESUME 2026-10-05 — Codex reconciliation + FB-2/FB-3 waves (integrator: claude/visual-investigation)
Head at time of writing: c02b154 (pushed). Production unchanged at fcb982d; nothing pushed to
claude/repository-setup-nc9x6o.

Integrated since 85fdca0 (all pushed):
- 219dfde Postgres migration evidence (`POSTGRES_MIGRATION_EVIDENCE.md`: fcb982d schema+data → head,
  51/51 tables preserved, additive only; real-DB rehearsal remains a deploy gate).
- 0f3f5d1 Codex FB verification follow-ups (cost basis in unit_economics/CFO, burn note, certify db).
  Reports: `codex_reconciliation/codex_fb_verification.json` (15 items) and
  `codex_reconciliation/build2_assist_reconciliation.json` (76 entries: 39 still-applicable,
  24 fixed, 10 re-audit, 3 superseded). **C-78 was false**: Orders hardening 3081402 was never
  merged although Build-2 certification claimed it; now ported by fb2-O.
- fb2-R1 9c0e7db: Etsy fixtures satisfy the pre-create check legitimately.
- fb2-I a8a8e16: D01, I01, I04, I05, I07, I10 + fixtures.
- fb2-Q 089bf6c: G02 protected claim tiers, G05, G08, P04, P09 admission lock, P11 stale version refusal.
- fb2-O 3b540fa: Orders/refund truth (Codex adversarial receipts 11/11), O06, O07, O08, P15.
- fb2-H2 3dd0a23: disclosed deterministic renders for Launch-0 (D-FB-7); independent verifier;
  structural_floor PASS only on verifier-PASS bound bytes. Report `waves/fb2_H2.json`.
- fb2-R2 eaec0f5: pre-send refusal no longer parks a version; G-R2 fallback provenance; image
  hash lookup fail-closed.
- c02b154: 17 suites made visible to the harness (PASS→OK), path bootstraps, vacuity guards.

Full suite on 38da162: 5,365 passing, 47 suites failing (16 harness-invisible only). Rerun of the
failing set on f373dd8 → 28 genuinely red, grouped into FB-3 workers (branches claude/fb3-*,
base e0ac882): **G** gauge-consistent generators/catalogue (cert_design, garment_design,
lanes_capacity, preengineering, acceptance_gates, persistence, product_run, shadow,
design_pipeline); **S** spend controls (spend_governance, spend_policy, funding); **V** visual/parity
under D-FB-7 (LIFESTYLE_QUALITY for disclosed renders, disclosed frames in listing-set
certificate, owned_photography/parity/model_photography/motif_fidelity/launch); **D** customer
documents (deliverable_qa, products_adversarial coaster size, provenance_write_path,
pdf_layout_bounds); **P** publish gates + bands + durable owner publication grant (swarm_runtime,
cert_publish_gates, listing_parity_gate, double revalidation audit after R2).
On reset: `git ls-remote origin 'claude/fb3-*'`; integrate pushed branches; re-dispatch only
missing ones from their pushed heads.

Open, not yet assigned: test_cert_claude_independence flaky (different test fails per run —
find cause); gateway/images.generate(db=None) skips benchmark byte check; vacuity scanner strips
loop roots named values/items/keys (false negatives); C-78 certification row must be corrected
in the Build-2 certification record; heartbeat prompt targets production branch (owner decision).
Launch-0 listings remain blocked on HERO (vision gate, owner) and COMPETITIVE (blind review, data).
- 2026-10-05T16:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing, ok=True. Final Build work continues on claude/visual-investigation; nothing pushed to the production branch.
