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

## Progress 2026-10-05 ~19:00Z
Integrated & pushed after c02b154: 9a5a5a7 (independence test stall-based wait), a387d4a (image
byte check without db), fb3-V fa5ff94 (D-FB-9 disclosed-render presentation standard; one
certified upload path; V1 tests assert F-852 refusal), fb3-S 03673d2 (spend tests were
calendar-bound; new regression: modelled/unknown/unbilled spend counts against ceilings), fb3-D
582c1d2 (PDF lesson URL at brand minimum; stale pins re-derived), c5b387f (Launch-0 size labels
gated; large basket 25 -> 24 cm), fb3-P 5e00905 (bands for 5 job types; durable owner
publication grant D-FB-10; revalidation audit stages). Focused suites of every merged branch green.
Outstanding: fb3-G (gauge-consistent generators/catalogue) — then full lock-matched suite,
re-aggregate closure matrix, BUILD_STATE, RC freeze decision.

OWNER ACTION (batched, not yet requested — only needed at the live-publish gate): per release,
set BRAMBLELOOP_OPS_TOKEN (>=24 chars) and BRAMBLELOOP_PUBLISH_AUTHORISED=1 in the host env,
POST /api/owner/publication/preview then /approve (expected_digest from preview). Cost CA$0,
~5 min/release, grant valid 24 h. Without it every store.publish refuses before any Etsy request.
Owner decision recorded: catalogue_depth needs 8 listable products; Launch-0 has 5 slugs.

## FB-4 wave (dispatched 2026-10-05 ~20:00Z, base cfa5e8a; PUB base acb6c9f)
Matrix after re-mapping 123 launch-critical rows on 6f9a2f7: LC MISSING 11, IMPLEMENTED 6, TESTED 37,
≥INTEGRATED 385. Workers (branches claude/fb4-*): **PUB** store.publish search verdict never PASS at
runtime (F-004/F-005) + physical intake for blocked releases (F-074/F-078); **FIN** spend product
tagging (F-321/324/325/329), break_even from missing data, launch_inventory gauge (F-186), modelled
confidence consumers (F-189), creative cohort label (F-188); **OPS** orders re-auth action closed by
readiness (F-541), credential register wiring (F-160), maturity disagreements (F-125), deploy_guard on
the deploy path (F-461), reliability ledger (F-350/F-344), first-response watch (F-043), defer legal
setup (F-874); **J** closure validator hardening, completion verdict/OPEN count, launch-scope ledger,
scripts/shadow_rehearsal.py, scripts/freeze_candidate.py; **STORE** ranking readiness (F-003), shop
SEO/opening grid/storefront preview/seller identity/search-visibility intake (F-236..F-293);
**LC** Learn graph read + lesson links + asset byte check (F-815/808/821), licence registration
(F-786/787), surface unknowns (F-588), component-gauge refusal (F-754), variant config (F-757).
Integration order: PUB → FIN → OPS → LC → STORE → J (J last: validator + rehearsal on merged head),
full suite, re-aggregate, then freeze candidate with scripts/freeze_candidate.py and start
adversarial certification. On reset: `git ls-remote origin 'claude/fb4-*'`.
- 2026-10-06T00:15Z heartbeat: production `/api/verify` read-only — 12 checks, 0 failing, ok=True. Nothing pushed to the production branch.

## RELEASE CANDIDATE FROZEN — final-candidate-3be3096 (2026-10-06 ~00:45Z)
Candidate SHA 3be3096 (local annotated tag, not pushed). Bound evidence: release-eligible full suite
(5,773 passing / 0 failing; evidence/suite_3be3096.json), production-mode shadow rehearsal on the
exact SHA (evidence/shadow_rehearsal_3be3096.json: certify → assets → listing.seo PASS; shadow
publish refused; orders/support/ledger PASS; past-shadow publish blocked only by gated inputs:
Etsy taxonomy (etsy_api), parity hero (image_vision) + blind review (data), frame review), closure
matrix summary (launch-critical OPEN 300 under the strict definition, rows not yet re-mapped for
FB-4). Files: CANDIDATE_3be3096.json, DEFECT_LEDGER_3be3096.json.
Next (F-846): independent adversarial audit of this exact SHA by a different model; repairs land
on a successor candidate, never on this tag. Commits since 958cb19 are UNSIGNED (signing helper
lost in a disk cleanup) and NOT PUSHED; re-sign after a session restart, or push on owner say-so.

## Adversarial certification of final-candidate-3be3096 (2026-10-06)
Verdict so far: **NOT SHIPPABLE AS FROZEN.** Independent audits (different model) in
research/final_build/audit_3be3096/:
- Audit 1 money/orders/authority: 1 LAUNCH-BLOCKING (store.activate ignores recorded phase rollback),
  5 HIGH (unrecorded model/render spend, billed-failed render released unbilled, sustainable_economics
  passes on assumed sales, phase seal replayable), 8 MEDIUM, 5 LOW.
- Audit 3 runtime/security: 1 LAUNCH-BLOCKING (unauthenticated stored XSS on dashboard → ops token in
  localStorage), 4 HIGH (unauthenticated mutating routes, readiness closes live owner actions, buyer
  id leak on 5 open routes, deploy guard unenforced), 5 MEDIUM, 4 LOW.
- Audit 2 product truth/publishing: 2 LAUNCH-BLOCKING (basket/coaster listings titled, tagged, priced and
  categorised as "Mosaic Blanket"; first-customer gate can never clear), 2 HIGH (same-version content
  replacement at runtime; price from wrong band), 7 MEDIUM, 3 LOW; compile/certify/stitch counts/gauge/
  safety/upload binding confirmed OK. Repairs: claude/rc1-LST, claude/rc1-PAT (base a034a44).
Repair workers (local branches, unsigned, not pushed; base 503190e): claude/rc1-AUTH, rc1-SPEND,
rc1-ORD, rc1-SEC, rc1-OWN. Then: merge → full suite → rehearsal → freeze successor → re-audit.

## v1.1 RESUME — preserved state of the previous run (2026-10-06T06:10Z)
Governing documents (now in repo): spec/10_Brambleloop_FINAL_Master_v1.1_Owner_Command_Center.pdf
(canonical; sha256 36ed45ad…8177; text research/final_build/master_v1.1.txt) and
spec/11_Final_Build_v1.1_Master_Prompt.pdf (execution directive; text
research/final_build/v1_1/EXECUTION_DIRECTIVE_v1.1.txt). v1.0 body (§1–93) unchanged in v1.1;
new §94–96, F-880..F-930. OA-0003 (always-on rented hosting) RESOLVED by the owner in the directive.
Preserved state at v1.1 start:
- Branch claude/visual-investigation, local HEAD 232f739 (signed). origin at 234fe82; 38 commits
  unpushed — push of this branch was refused by the session permission classifier; owner to push
  (`git push -u origin claude/visual-investigation`). Nothing is pushed to the production branch.
- Production = claude/repository-setup-nc9x6o @ fcb982d (Railway). No deploy/merge authorised.
- RC final-candidate-3be3096: frozen, audited, NOT SHIPPABLE (see above). Repairs rc1-SPEND/ORD/
  ORD2/AUTH/OWN/SEC/LST/PAT merged locally → 232f739. Full suite on 232f739: 5,888 passing, 10 suites
  failing (integration interactions) → worker rc1-INT (local branch claude/rc1-INT) repairing.
- Signing: all 38 unpushed commits re-signed tree-identically (commit-tree -S); old tag
  final-candidate-3be3096 still names the pre-resign unsigned object (superseded candidate).
- Codex: build2-assist-01 (5 unique, verification evidence; C-78 ported by fb2-O),
  final-finance-cost-basis-01 (evidence-cache tooling), continuous-operations-audit (2 unique:
  department lanes, fenced recovery, Etsy Ads readiness + integration pack) → reconciled in v1.1
  lanes A/H (reuse, not redo).
Next: rc1-INT merge → release-eligible suite → rehearsal → freeze successor RC → re-audit, while
v1.1 lanes (A–J) build F-880..F-930 on disjoint files.

## v1.1 integration progress (2026-10-06T07:10Z)
Merged into claude/visual-investigation (local, signed, not pushed — push still classifier-blocked):
rc1-INT (366c705), lanes H (ads readiness + Finance challenge, follow-up 4006b73), G (SEO), E
(double-entry Accountant), C (Command Center API/auth), D (PWA), B (Learn loops + D-B1 monitor
fix), F (Store Foundation + preview), I (SLOs, failover, recovery, CLOUD_HOSTING_PLAN.md).
Lane A (autonomy/orchestrator) still running; wiring of G/E/H/I/B/F jobs into scheduler/worker/
registry waits for A (A owns those files). INT2 repairing test_v11_cc_views (2 fails vs real E).
Interpreter: the only complete one is /home/user/Project-Money/brambleloop/.venv/bin/python;
earlier "environment" failures (numpy/sqlalchemy) were wrong-interpreter, not product defects.

Read-only production evidence (Railway project brambleloop, 2026-10-06T07:05Z):
- brambleloop-os deploys from claude/repository-setup-nc9x6o (rootDirectory brambleloop),
  healthcheck /health, 1 replica us-west2, no App Sleeping/serverless key in config; restart
  policy not set explicitly (Railway default). Service "Project-Money" latest deploy FAILED (stale).
- /api/verify: ok, shadow, postgres, scheduler last_tick 07:04:53Z and worker last_tick 07:05:05Z
  — ticking ~7h after the last heartbeat poke (00:15Z), so the embedded runtime runs without a
  Claude session. BUT store.publish_refused has been 165 across every recorded heartbeat: the
  runtime is alive yet produces no new release work — the Priority Zero "idle company" defect
  that lane A's Executive Orchestrator targets (not deployable without owner approval).
- 2026-10-06T08:15Z heartbeat: production /api/verify read-only — 12 checks, 0 failing; scheduler
  08:15:15Z, worker 08:15:39Z. Nothing pushed to the production branch.

## Full suite on 8ef77e3 (all lanes + WIRE) — 2026-10-06T08:50Z
6,375 passing; 3 suites failing (9 tests), all repo-wide invariants catching new v1.1 code:
temp dirs nothing removes (autonomy/proof, accounting shadow_dataset, seo/_testkit) and an
uncounted prefix; `spend.refused` read by ops.slo with no retention decision; model names outside
routing.TASKS (gateway/failover, accounting shadow_dataset). Fixed in the next commit (no test
or invariant weakened; failover ranks now derive from routing.TIERS; accounting keeps its
no-gateway-import guardrail and uses synthetic labels). Re-running the full suite.

## RELEASE CANDIDATE FROZEN — final-candidate-ddf9c6e (2026-10-06 ~10:05Z)
Successor to the not-shippable 3be3096. Contains rc1 repairs + all v1.1 lanes A–I + WIRE +
invariant fixes. Release-eligible full suite: 6,384 passing / 0 failing / 398 suites
(evidence/suite_ddf9c6e.json). Production-mode shadow rehearsal on the exact SHA
(evidence/shadow_rehearsal_ddf9c6e.json): boot, compile, certify, assets, seo, orders, support,
ledger PASS; shadow publish refused as expected; past-shadow publish blocked only by the gated
Etsy taxonomy read (etsy_api) → category UNKNOWN → search certificate REFUSED → grant snapshot
refused; identical to 3be3096. Files: CANDIDATE_ddf9c6e.json, DEFECT_LEDGER_ddf9c6e.json.
Next: independent adversarial certification (lane J, different model) of this exact SHA.
Repairs land on a successor, never on this tag. Not pushed (classifier); not deployed.
- 2026-10-06T16:15Z heartbeat: production /api/verify read-only — 12 checks, 0 failing; scheduler 16:30:57Z,
  worker 16:31:27Z. Nothing pushed to the production branch.
