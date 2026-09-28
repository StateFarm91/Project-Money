# FINAL BUILD RESUME MANIFEST

Written 2026-09-28 ~14:30Z by the Claude integrator session at a weekly-usage-limit handoff.
Implementation-grade: a competent engineer (Codex, Opus, or human) with repository access must
be able to continue from this file alone. Read it top to bottom before touching anything.

## 0. Identity

| item | value |
|---|---|
| repository | `StateFarm91/Project-Money` (code under `brambleloop/`) |
| Final Build branch | `claude/visual-investigation` |
| pushed HEAD | see §15 (the commit that adds/updates this file; `git log -1 origin/claude/visual-investigation`) |
| certified Build 2 ancestor | **019ebf0** (5,242 passing / 285 suites / 0 failing at 856186f; closure 218 C+P, 0 OPEN, 58 owner, 37 data, 7 external) |
| production (deployed) | **fcb982d** = `origin/claude/repository-setup-nc9x6o`. NEVER push Final Build work there: that is a production merge (not authorised). |
| spec | Final Master **v1.0 Audited**, `spec/09_Brambleloop_FINAL_Master_v1.0_Audited.pdf` sha256 `526ed69c8cf9b50e8b5ed736301607b0d314f7e80126ebd5a2178e9689471a99`; text `research/final_build/master_v1.0.txt` |
| Visual V2 R&D | `codex/visual-v2-rnd` @ **035ff0c** (frozen, isolated, not integrated) |
| interpreter | `/home/user/Project-Money/brambleloop/.venv/bin/python` (the worktree has no `.venv`; set `PY=` for `run_tests.sh`) |
| authority | NOT authorised: production merge, Railway deploy, Etsy publication, live listings, ads, paid API spend beyond existing authority, banking/KYC, irreversible external actions. Phase = shadow. |

## 1. Durable artefacts (all under `research/final_build/` unless noted)

| file | role |
|---|---|
| `master_registry.json` ← `parse_master.py` | 866 requirement records, 859 IDs (pinned: `tests/test_final_master_registry.py`) |
| `module_reachability.json` | per-module live-root reachability on 019ebf0 + presence in fcb982d. **Stale for modules added in FB-1: regenerate** (snippet in §14) |
| `mapping/s1..s9.json`, `MAPPING_BRIEF.md` | worker mapping proposals (pre-FB-1 code) |
| `aggregate.py` → `closure_matrix.json` | adjudicated matrix; `waves/INTEGRATED.json` adds a `wave` overlay per row (worker-reported, NOT maturity) (pinned: `tests/test_final_closure_matrix.py`) |
| `FINAL_BUILD_BASELINE_AUDIT.md` | Phase-0 audit: supersessions, clusters A–J, dependencies, owner packets, completion plan |
| `FINAL_BUILD_STATE.md` | running state log |
| `waves/FB1_BRIEF.md` | the implementation-worker brief (reuse it) |
| `waves/fb1_<X>.json` | each cluster's own report (requirements, tests, needs_from_others, risks) |
| `waves/fb1_C_strict.patch` | staged gauge-band refusal (do NOT apply alone — §9, D-FB-6) |
| `waves/wip/fb1_{A,B,G}_uncommitted.patch` | safety snapshots of running workers' uncommitted diffs at ~14:20Z |
| `DECISION_LOG.md` D-FB-1..D-FB-6, `BUILD_STATE.md` header | decisions and honest status |

## 2. Requirement / maturity counts (closure_matrix.json, current)

866 rows · LAUNCH-CRITICAL 446 · MATURE 413 · NA 7.

| maturity | all | launch-critical |
|---|---|---|
| MISSING | 165 | 63 |
| IMPLEMENTED | 86 | 34 |
| TESTED | 47 | 26 |
| INTEGRATED | 302 | 129 |
| DEPLOYED | 247 | 175 |
| EXERCISED | 19 | 19 |
| PRODUCTION-OBSERVED / COMMERCIALLY-EVIDENCED | 0 | 0 |

These maturity numbers describe **019ebf0-era code**; they were NOT raised for FB-1 work
(no promotion without re-mapping, F-867). FB-1 integrated clusters report, per row, in the
`wave` overlay: **34 DONE, 25 PARTIAL, 1 NOT_STARTED** (clusters C, D, E, F). 123 worker claims
were lowered by the integrator's evidence rules (D-FB-3). 111 rows carry a pre-FB-1 defect note;
FB-1 fixed many of them (see §8) but the defect fields are only cleared by re-mapping.

## 3. Clusters

| cluster | scope | state | branch head | integrated as |
|---|---|---|---|---|
| F release/supply chain | lock+hashes, secret scan, credential register, suite run records, deploy guard, waiter, vacuity gate | **COMPLETE, integrated** | `claude/fb1-F` ed7c2b1 | merge **973318d** (+ heartbeat rule 267b183) |
| D money/order truth | UNMEASURED sales, ledger basis columns, Etsy payment-ledger fees, attribution unknown, Offsite Ads fee, OAuth owner action, sustainability gate | **COMPLETE, integrated** | `claude/fb1-D` 1784386 | merge **2186184** (+ vacuity fix b4c52da) |
| C product-truth gates | physical evidence bound to content hash, risk-class downgrade refusal, Launch-0 publication scope, legacy excluded from readiness, unknowns register, construction overview, children's parts from CIR, owner≠tester | **COMPLETE, integrated** (strict gauge refusal staged, see §9) | `claude/fb1-C` 9641582 | merge **daf43d5** |
| E owner visibility/security | opsauth on customer-data reads + route-enumeration test, probe-based health, one owner queue, stale-action verify check, truthful headline grid, CA$5K UNMEASURED | **COMPLETE, integrated** | `claude/fb1-E` 1049c23 | merge **787895a** |
| A listing search truth | taxonomy snapshot cadence, deepest category, property payload, tag/attribute truth, 13 tags, copy gate, search certificate in claims_of | **FINISHED, AWAITING INTEGRATION** | `claude/fb1-A` **436f6c4** | — (report `fb1_A.json` on branch; head field says SEE_GIT_LOG → use 436f6c4) |
| B Etsy publish/read-back/observation | images into publish, store.activate with execution-time revalidation, read-back incl. files, credential health, shop snapshot, listing census, owner_queue seeding, readiness etsy_integration | **FINISHED (checkpoint), AWAITING INTEGRATION** — DONE F-542 F-593 F-547; PARTIAL (all wired to live roots) F-524 F-543 F-559 F-541 F-540 F-515@v0.16 F-577 F-585 F-553 F-544 F-568 F-594 | `claude/fb1-B` **8cb7abc** (last commit 5ef5031 is 'WIP (not green)' harness change in test_cert_commerce, 12/13 re-confirmed; report `waves/fb1_B.json`, head field placeholder → use 8cb7abc) | — |
| G IP firewall/originality | provenance required at certify (gates/originality.py), licence records, benchmark-image refusal, design-difference ledger, redesign gate, similarity review incl. benchmark 2 | **FINISHED (checkpoint), AWAITING INTEGRATION** — DONE F-783 F-788 F-785 F-791; PARTIAL F-798 F-786 F-787 F-794 F-795 F-792 | `claude/fb1-G` **ddc4d34** (report `waves/fb1_G.json`; its head field says f2bc6f4 → use ddc4d34) | — |
| H Visual structural truth (main line) | port stitch-identity instrument, structural floor in parity, no-redraw policy, product-region preservation | **UNSTARTED** | — | — |
| I Learn launch architecture | learn/ package, LessonSpec, knowledge graph, gap scan, lesson QA, PDF links | **UNSTARTED** | — | — |
| J certification machinery | closure validator (consumer/fixture/proxy checks), s92 acceptance tests, shadow rehearsal, RC freeze, re-audit | **UNSTARTED** (only the matrix + its test exist) | — | — |
| C2 Launch-0 re-engineering | re-derive Launch-0 gauges from yarn band per D-FB-6, then apply `fb1_C_strict.patch` | **UNSTARTED (new, from C's finding)** | — | — |

Worker worktrees (local to the old container, may not exist on resume — branches are the
source of truth): `/home/user/Project-Money/.claude/worktrees/fb1-{A..G}`.

## 4. Commits integrated on `claude/visual-investigation` since 019ebf0 (oldest → newest)

fb50480 registry · e156720 mapping brief · 676a787 aggregator · 9564dec/0aa6ac9/1cf7547/9c02f44/460844b/3b93c6f/3288380/f80ebc6 mapping slices · be8d416 baseline audit + matrix (**FB-1 base**) · d9f863e FB1 brief · 1440d6e dispatch record · **973318d merge F** · 267b183 heartbeat rule · **2186184 merge D** · **daf43d5 merge C** · b4c52da vacuity fix · **787895a merge E** · e7e5807 wave overlay + D-FB-6 + WIP snapshots · (this manifest commit, §15).

Awaiting integration: `origin/claude/fb1-A` 436f6c4, `origin/claude/fb1-B` **8cb7abc**,
`origin/claude/fb1-G` **ddc4d34**. Trial merges on 787895a: **A conflicts in
`src/brambleloop/publish/release_gates.py`** (C added ~10 lines to `for_publish`; A added
`search_gate` to `for_publish` and fields to `claims_of` — keep BOTH); B and G merge cleanly.

## 5. Uncommitted / WIP work and recovery

- Integrator worktree: clean after §15 commit.
- B: `tests/test_cert_commerce.py` modified, uncommitted at 14:20Z. Recovery: if `origin/claude/fb1-B`
  has a newer head with a WIP commit, use it; else `git apply research/final_build/waves/wip/fb1_B_uncommitted.patch`
  on top of 80c7770 in a fresh worktree. (The patch also contains B's untracked `research/final_build/waves/` files.)
- A: only the report dir was untracked at snapshot; A has since pushed 436f6c4 containing it.
- G: nothing uncommitted at snapshot.
- Note: the snapshot ran `git add -A -N` (intent-to-add) in the A/B/G worktrees; harmless, but
  a worker's next `git status` shows untracked files as added-intent.

## 6. Tests actually run (exact results)

Baseline: 019ebf0/856186f full suite **5,242 passing, 0 failing, 285 suites** (log
`research/b2_resume/evidence/full_suite_856186f_5242_passing_0_failing.log`).

**No full suite has been run on any FB-1 integration commit.** Targeted results on the integration branch:
- after F merge (973318d): test_dependency_lock 7, test_secret_scan 6, test_credential_register 6,
  test_deploy_guard 7, test_run_tests_script 10, test_vacuity 7, test_waiter 11,
  test_final_closure_matrix 5, test_final_master_registry 5 — all OK, 0 FAIL.
- after D+C merges (daf43d5): test_money_truth 18, test_finance 21, test_launch 27, test_launch0 52,
  test_gates 40, test_eligibility 33, test_certification 12, test_physical 18, test_secret_scan 6,
  test_dependency_lock 7, test_final_closure_matrix 5 — all OK; test_vacuity 6 OK / **1 FAIL**
  (new loop in test_money_truth.py:344) → fixed in b4c52da (vacuity 7/7 after fix).
- after E merge (787895a): test_customer_data_auth 6 OK, test_cert_dashboard 18 OK. A background
  run of test_deploy, test_health, test_scale, test_executor, test_launch, test_finance,
  test_cert_orders, test_vacuity, test_closure was in progress at handoff; its output was not
  persisted — **re-run them**.
Worker-side results (on their own branches, not the integration branch) are in each
`waves/fb1_<X>.json` `tests_run`. Worker-reported timeouts under load ~15: C — test_cert_wiring
(drain hit 1200 s), test_shadow (killed at 1500 s); A — test_product_run (timed out 1500 s),
test_cert_commerce and test_cert_rebuild_chain never run.

## 7. Tests still required (in this order)

1. On current HEAD: `SUITES="tests/test_deploy.py tests/test_health.py tests/test_scale.py tests/test_executor.py tests/test_cert_orders.py tests/test_closure.py tests/test_cert_wiring.py tests/test_shadow.py tests/test_cert_publish_gates.py tests/test_product_run.py" PY=$PY bash run_tests.sh` on a QUIET machine (no workers).
2. Then the full suite from a clean tree: `REQUIRE_CLEAN=1 PY=$PY bash run_tests.sh` (new F tooling writes `artifacts/suite_runs/*.json`; first real run of the restructured script — watch the header/footer and exit code).
3. After merging A: test_product_run, test_cert_commerce, test_cert_rebuild_chain, test_search_truth, test_cert_parity_copy, test_cert_publish_gates first.
4. After merging B and G: their own `tests_run` list, then full suite again.

## 8. Open defects (launch-critical, current reality)

Fixed by integrated FB-1 work (pending re-mapping to clear matrix `defect` fields):
unauthenticated `/api/support` (F-696); env-var health (F-128/131); two owner-action sources and
cards unblocking nothing (F-179/181/196); CA$5K "effectively zero" (F-189); unsplit dead letters
(F-185); vanity headline (F-206); P&L CA$0.00 as measured (F-608); modelled fees stored as
charged (F-609); blanket `etsy` attribution (F-283/289); Offsite Ads fee ignored (F-273);
physical evidence unbound (F-078); legacy counts toward readiness and publishable (F-111/119);
owner-crochet wording (F-071); unpinned dependencies (F-158); no secret scan (F-159).

Still open:
- **Publish path cannot produce a live listing**: no images to Etsy, no activation, no read-back, no file verification (F-524/F-543/F-542/F-559) — cluster B, in progress.
- **One hard-coded taxonomy 66, attributes never sent** (F-005/F-007) — fixed on A (awaiting integration); transmission is B's (`needs_from_others` in fb1_A.json).
- **Gauge outside declared yarn band on every product incl. Launch-0** (F-112/F-116) — D-FB-6; C2 re-engineering + `fb1_C_strict.patch`.
- **Listing-image PRODUCT TRUTH is an LLM motif judgement; generative product redraw is the main-line photoreal path** (F-752/F-852/F-853/F-677) — cluster H.
- **Design provenance optional; no licence records; no redesign gate; similarity excludes benchmark 2** (F-783/F-786/F-791/F-794/F-795) — cluster G, in progress.
- **No Learn department** (F-799…) — cluster I.
- **No closure validator for consumer/fixture/proxy; no end-to-end shadow rehearsal** (F-834/F-836/F-837/F-848) — cluster J.
- Owner inbox duplicate 19/20 and 275 unproven artefacts in production clear only on deploy (F-663/F-665).
- Duplicate-spend cache and cost-downgrade guard are test-only (F-306/F-311/F-313); per-usable-asset cost excludes judging (F-322).
- Etsy ledger `ledger_type` strings and cents divisor in `finance/reconcile.py` unverified until a real read (risk from D).

Cross-cluster follow-ups requested by workers (not yet done):
- F: add `credential_register.owner_requests()` to the owner-queue list in `runtime/release.py` (after B merges); dashboard card via E's inbox.
- D: public `EtsyClient` method for the payment-account ledger + SCOPES_REQUIRED entries (B); render `sales_reading`/`sales_why`, `platform_fees_basis`, `sales_by_source` on the dashboard, attribution POST + first-sale GET (E-owned `app/main.py`); fix `api_finance` docstring; add fees/first_sale/auth_failure to the `commerce.orders_ingested` audit summary (`runtime/orders.py`); pass `product_slug` to `spend_report.record` in maintenance jobs.
- C: `runtime/release.py::handle_physical_record`/`_load_cir` must allow recording against a release blocked only on physical evidence and stamp the tested content hash; score handler must stop refusing Class C promotion; persist listing frames for first-customer imagery check; F-073 risk matrix.
- E: canonical `launch_cleared(product)` in `launch/readiness.py` including gauge-band check; show `reported_probability`/`state` in finance/reinvestment, growth/weekly, scale/evidence; operator scripts calling `/api/support` need a Bearer token.
- A: B must send `commerce.category.publish_inputs(...)['taxonomy_id']` (refuse on None) and its `properties` via updateListingProperty; E to show `listing_search_profiles` on `/api/catalogue` and label `Listing.seo_score` a proxy.
- F vacuity allow-list: 110 legacy vacuous loops listed in `tests/test_vacuity.py`; shrink as touched.

## 9. Shared-file conflicts and integration order

Hot files: `runtime/pipeline.py` (B: handle_store_publish; C: concept_to_cir/handle_certify),
`runtime/release.py` (A: handle_listing_seo + taxonomy cadence; B: cadences; F follow-up),
`runtime/worker.py` CADENCES (A, B), `publish/release_gates.py` (A: claims_of/search_gate/
for_publish; C: for_publish Launch-0 lines — **known conflict**), `launch/readiness.py`
(B etsy_integration item, C catalogue/unknowns, D sustainable_economics — C and D merged),
`core/models.py` + `core/migrate.py` (A, D, G additive), `gates/certificate.py` (C merged; G one
call into originality), `app/main.py` (E only; others' render needs queue to E).

**Order:** (done) F → D → C → E. Next: **A** (resolve release_gates: keep C's Launch-0 eligibility
lines AND A's search_gate/claims_of) → run §7.3 → **G** → **B** (then wire A's taxonomy/properties
into store.publish and D's ledger method into EtsyClient) → full suite → **C2** (re-engineer
Launch-0 gauges + apply `fb1_C_strict.patch` in one change) → **H**, **I** in parallel → **J** →
RC freeze.

## 10. Exact next deterministic action per unfinished item

- **A**: `git merge --no-ff origin/claude/fb1-A`; resolve `publish/release_gates.py` keeping both sides; run §7.3; commit; add `A` to `research/final_build/waves/INTEGRATED.json`; `python3 research/final_build/aggregate.py`; commit; push.
- **B**: merge `origin/claude/fb1-B` 8cb7abc (trial merge at 80c7770 was clean; re-check). `waves/wip/fb1_B_uncommitted.patch` is SUPERSEDED by 5ef5031 — do not apply. First run test_cert_commerce (confirm 13/13, esp. the deliverable-QA test left running), then test_etsy_readback_observe (37), test_etsy*, test_cert_publish_gates, test_shadow, test_acceptance_gates, test_cert_wiring. **Defect to fix before RC (security, F-835/F-703):** `store.activate` accepts any non-empty `launch_authorisation` string — bind it to an owner-approved record (executor approval / OwnerAction id with approver + timestamp) and refuse otherwise. Follow-ups: D calls `etsy_ops.record_auth_needs_owner(db, e, where="orders_ingest")`; E adds an owner route to queue store.activate with authorisation and `POST /api/policy-violation`; readiness item reading the shop snapshot; remaining F-594 items (file verification, search readiness, first_customer); A's taxonomy/properties flow through `etsy_ops.certified_payload`. Risks: daily refresh-token rotation never run unattended; shop-incomplete P1 holds readiness until the owner fills the shop; census raises P2 for pre-existing listings not created by this system.
- **G**: merge `origin/claude/fb1-G` ddc4d34 (trial merge on 787895a was clean). Then on a quiet machine run test_originality (28), test_certification, test_cir_roundtrip, test_cert_wiring (3/16 failed under load on G's branch — unconfirmed vs base), test_cert_design_pipeline and test_shadow (1 failure each under load; pass alone — verify), test_cert_commerce, test_chaos, test_product_run, test_platform, test_model_photography (timed out under load). Risk: provenance backfill changes every catalogue CIR's fingerprint/release hash → one re-draft/re-certify on deploy. G's follow-ups: C must stamp provenance in `concept_to_cir` (raw-geometry CIRs are now refused at certify) and pass ledgers/wording hashes/licence state from `handle_certify`; B runs the similarity review as a job before store.publish; E accepts licence terms at the upload route; teardown callers pass `db=`; creative carries `brief.benchmarks_consulted` into provenance.
- **C2**: new worker. For each Launch-0 product (see `products/launch0.py` LAUNCH0_SLUGS): derive gauge from declared yarn via `creative.prototype.gauge_for`, recompute counts to keep declared finished dimensions, re-run compiler/twin/reverse/certify; then `git apply research/final_build/waves/fb1_C_strict.patch`; tests `test_cert_publish_gates`, `test_products`, `test_launch0`, `test_certification` green. Legacy non-Launch-0 products stay quarantined (not re-engineered now).
- **H**: new worker, audit §6 row H; start with porting `research/bench2/star_identity.py` into `src/brambleloop/visual/stitch_identity.py` as the structural leg of `visual/parity.py` PRODUCT TRUTH, UNKNOWN blocks; then the no-redraw policy.
- **I**: new worker, audit §6 row I (launch architecture only, per v0.24 s84).
- **J**: after A/B/G/C2 merged: closure validator (consumer reached + reads producer's state; non-test writer for each evidence table; proxy refusal), s92 acceptance tests, `scripts/shadow_rehearsal.py`, then regenerate `module_reachability.json`, re-map every row touched by FB-1 (use `mapping/MAPPING_BRIEF.md` on the uids listed in each `waves/fb1_*.json`), re-aggregate, RC freeze (tag), independent re-audit by a different model.

## 11. Owner / data / external gates (separate from executable work)

Owner (request at latest responsible moment; packet format F-870; none blocks executable work):
1. Re-authorise Etsy app with `transactions_r` — ~5 min, $0 — unlocks order/fee truth (D's ledger read, F-501/558/608/609).
2. Browser/vision acceptance ruling for Build 2 #189/#221/#222/#320 — ~5 min, $0.
3. Model/vision provider headroom: CA$76.40 of CA$100 ceiling spent — proposed ≤ CA$25 top-up.
4. After B: authorise one controlled Etsy write round trip (`/api/etsy/exercise`: draft create → read back → delete; never activated) — ~2 min, $0 expected.
5. After RC freeze: authorise production deploy + unattended window (`production_window`), offsite bucket (`offsite_storage`).
6. Before any Class C product: independent tester (`tester_roster`/`physical_proof`); owner is never the tester.
7. Rotate the Anthropic key exposed in chat 2026-09-19 (now in `credential_register`).
8. Launch step: Etsy identity/banking/tax, live-listing approval (F-874: not before needed). Post-launch: ads authority, Insights/Stats exports, bounded Visual spend packet (F-877).
Data: `customers`, `live_listings`, `insights_access`, benchmark/second-market data.
External: `model_bearing_render` (no provider renders certified structure), `rendered_pages`
(Etsy 403 to automated policy/search pages), Etsy has no Messages/Customer-Service-Stats API,
Visual V1 provider capability.

## 12. Master-spec errata (preserve)

- F-631..F-650 do not exist (v0.18 ends F-630, v0.19 starts F-651; section numbers jump 64→67).
- F-514..F-520 defined twice (v0.15 "Registry additions" vs v0.16 Etsy shop OS); both in force as `F-5xx@v0.15` / `F-5xx@v0.16` (D-FB-2).
- Declared 879 IDs = 859 present + 20 absent; 866 records including the 7 duplicates.
- v0.15 and v0.16 both use section numbers 53–59 (v0.16 restarts at 53).
- Supersessions: F-789..798 over F-781..788 where conflicting; F-831..840 over weaker completion; F-851..860 over generative product redraw; line 1079 identity scores. Adjudications S5–S10 in the baseline audit §2 (Ads countdown, Etsy Plus credit, owner≠tester wording, P1 = mature, Learn launch subset, V2 graduation vs launch).

## 13. Visual status

Product-Only Visual V1: **NOT LOCKED**. Visual V2: R&D only on `codex/visual-v2-rnd` @ 035ff0c —
B+C recommended; V2-P06 continuous-yarn topology **FAIL**; V2-P07 structural truth **UNKNOWN**
(13.6 mm unaccounted feed); photographic realism **UNKNOWN**; spend $0; Heirloom cable direction
awaits owner clarification. Main line still uses generative product redraw (superseded, F-852)
with an LLM product-truth floor; cluster H makes it honest (refuses more), not better. Launch does
not wait on V2 unless photoreal heroes are required (D-FB-4). Proposal on record: graduate V2 first
on an sc/hdc original (certified topology exists) rather than the cable Heirloom.

## 14. Exact next-session procedure

1. `git fetch origin && git checkout claude/visual-investigation && git pull` (or a fresh worktree of it). Confirm `git log -1` equals the §15 SHA or a descendant; `git status` clean.
2. Read this file, then `FINAL_BUILD_BASELINE_AUDIT.md`, `DECISION_LOG.md` D-FB-1..6, `BUILD_STATE.md` header. Do not re-litigate decisions.
3. `git ls-remote origin 'claude/fb1-*'` — compare with §3; read any new `waves/fb1_<X>.json` on those branches.
4. Run §7.1 on a quiet machine. Fix any red before merging more.
5. Integrate per §9/§10 (A → G → B), targeted tests after each, full suite (`REQUIRE_CLEAN=1`) after the batch; append each merged cluster to `waves/INTEGRATED.json`; `python3 research/final_build/aggregate.py`; run `tests/test_final_closure_matrix.py`; commit; push.
6. Regenerate reachability after merges:
   `PYTHONPATH=src $PY -c "import json,subprocess;from pathlib import Path;from brambleloop.build2 import reachability as r;pkg=Path('src/brambleloop');dep=set(subprocess.run(['git','ls-tree','-r','--name-only','fcb982d','--','src/brambleloop'],capture_output=True,text=True).stdout.split());m={str(p.relative_to(pkg)):p for p in pkg.rglob('*.py') if '__pycache__' not in str(p)};out={k:{'reached':bool(r.reached(k).get('reached')),'why':str(r.reached(k).get('why',''))[:200],'in_production_fcb982d':('src/brambleloop/'+k) in dep} for k in sorted(m)};json.dump({'basis':'HEAD reachability; production fcb982d','modules':out},open('research/final_build/module_reachability.json','w'),indent=1)"`
   (run from `brambleloop/`; basis line should name the HEAD SHA).
7. Dispatch C2, H, I (and J after merges) with `waves/FB1_BRIEF.md` adapted (<X>, base = current HEAD). Keep ≤ 7 concurrent workers on this 4-CPU machine; heavy suites time out under load ~15 — run heavy suites only in the integrator after workers finish.
8. Re-map FB-1-touched rows, re-aggregate, then J → RC freeze → independent re-audit → owner launch packet (F-878). Stop at the consequential gate: no deploy/publish/spend without owner authority.

## 15. Handoff commit

This file is committed and pushed on `claude/visual-investigation`; the exact SHA is reported in
the session's final message and is `git log -1 origin/claude/visual-investigation` at handoff.
