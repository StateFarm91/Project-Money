# W-READINESS: deployment-readiness matrix for the work finished after the listings release

- **Date:** 2026-10-26 (UTC).
- **Author:** W-READINESS. Read-only analysis; this file is the only change.
- **Rules kept:** no deploy, no production write, no paid call, no secret. No test was run,
  because a full certification suite is running. Every test count below is the count the branch
  itself reports, or a static count of `def test_` in a new file, marked "(static)".
- **Method:** `git log`, `git diff A...B` and `git merge-tree --write-tree` (a read-only trial
  merge) against each base. Each branch's own report was read, and so was every
  `origin/claude/w4-SECREVIEW-*` review file.

## 0. Baseline

| Item | Value |
|---|---|
| **Production** | `15800536` (the b997efd release, INTEG4), SHADOW. Source: `evidence_FMBATCH1/prod_health_20261026T0103Z.json`, `build.commit`, `known: true` |
| **Next release (listings)** | `origin/claude/final-candidate-82a3b7a` = **82a3b7a**. This is LISTREADY d69a3ec plus the owner-approved `test_cert_wiring` limit (58b2e98, D-W4-CERTWIRING-LIMIT) and its decision index. It descends from 1580053, so it fast-forwards from production (deploy_guard rule 1) |
| **Review covering 82a3b7a** | `INDEPENDENT_SECREVIEW_LISTREADY_d69a3ec.md`: NO BLOCKER (S1 LOW). 58b2e98 and 82a3b7a change one test limit and the generated index only |
| **Deploy rule that shapes batching** | `ops/deploy_guard.py check` refuses any SHA without a GREEN, release-eligible full-suite record for that exact SHA, and any SHA that does not descend from production. **Every batch below costs one full certification suite.** That is the price of small batches |
| **CC shell version on 82a3b7a** | `cc-shell-v24`. Every batch that touches `static/sw.js` must bump it (INTEG6-prep's v22 is now stale) |

**Relationship of each branch to 82a3b7a.** The merge base is shown, and the result of
`git merge-tree` onto 82a3b7a.

| Branch @ head | Merge base with 82a3b7a | Commits not in 82a3b7a | Trial merge onto 82a3b7a |
|---|---|---|---|
| `w4-LAURAONE-freeze` @ **2c29b42** | 6531769 (INTEG4 checkpoint) | 41 | 6 conflicts: `BUILD_STATE.md`, `DECISION_LOG.md`, `sw.js`, `decision_index.json`, `gateway/credentials.py`, `tests/test_cert_spend_hosts.py` (the same code conflicts INTEG6-prep already resolved) |
| `w4-INTEG6-prep` @ **73e1580** | b9137b5 (LISTREADY run 3) | 44 | 3 conflicts: `DECISION_LOG.md` (append-only), `sw.js` (version), `decision_index.json` (generated). **No code conflict** |
| `w4-LAURAONE-freeze` 2c29b42 onto `w4-INTEG6-prep` 73e1580 | — | 1 (2c29b42) | **Clean** |
| `w4-FMBATCH1` @ **871b84a3** | b997efd | 28 | 2 conflicts: `BUILD_STATE.md`, `autonomy/autonomy_map.json` (generated) |
| `w4-FMBATCH1` prefix @ **be3fdd6a** (F-010, F-381) | b997efd | 2 | 1 conflict: `autonomy_map.json` (generated) |
| `w4-AGENTS` @ **a14c9ef8** | d69a3ec | 25 | **Clean** |
| `w4-CLOSE6` @ **ff788bd** | ee244a1 (CLOSE5) | 10 | **13 conflicts**, 2 of them in code: `commerce/shop_observations.py` and `launch/readiness.py` (against W4-FIRSTSALE2's collectors). The rest are generated boards, ledgers, `final_master_closure.json`, `DECISION_LOG.md` and `sw.js` |
| `w4-LAUNCHPREP` @ **fcc6d961** | d69a3ec | 3 | **Clean** (5 new files under `research/`, no code) |

**Cross-branch trial merges** (they matter for ordering):
- **AGENTS × INTEG6-prep:** only DECISION_LOG, sw.js and decision_index conflict.
  `laura/executive/loop.py` is changed on both sides and auto-merges. The tree needs an
  integration test, because AGENTS adds a `storefront` PROVIDER where LAURACEO adds model ranking.
- **FMBATCH1 × CLOSE6:** `ops/deploy.sh` conflicts, plus the generated boards. FMBATCH1.md §2
  gives the resolution: keep CLOSE6's `rb_json` path as the `--json` file of F-381's block.
- **FMBATCH1 × AGENTS:** only BUILD_STATE and autonomy_map conflict.

**INTEG6-prep's three failing suites are fixed on 82a3b7a.**
- INTEG6-prep reported 50/53. The three failures were `no such table: launch_review_batches` in
  `continuity.export`.
- The root fix is LISTREADY 58aea40 (`core/db.py` imports `finance.launch_review` in
  `create_all`), which is in 82a3b7a, and the LISTREADY-8d520ed review covered it.
- INTEG6-prep was cut from b9137b5, before that fix. Re-basing the Laura merge on 82a3b7a picks
  it up. The three suites must be re-run on the merged tree to confirm this; it has not been run.

## 1. Readiness matrix

Abbreviations:
- **AO** = always on.
- **RO / DET / MF / SF** = read-only / deterministic / model-free / spend-free.
- "Additive" means new tables or nullable columns only, and no existing column changed.

### 1a. Laura: `w4-LAURAONE-freeze` 2c29b42 and `w4-INTEG6-prep` 73e1580

The Laura features ship together. INTEG6-prep is the prepared merge of freeze **f87e430** onto
LISTREADY b9137b5; it does **not** contain 2c29b42. 2c29b42 adds the R-1, R-2 and R-3 fixes from
the f87e430 review: 11 files, +118/−30.

| Feature (requirement IDs) | Branch and commit | Tests (as reported) | Independent review | Dependencies | Production compatibility | Feature flag | Rollback path | Ship independently |
|---|---|---|---|---|---|---|---|---|
| **L1. Business Laura, model-backed CEO** (LAURACEO): ADD-LCEO-01..07; D-W4-LAURA-CEO, D-W4-LAURACEO-ROUTE | freeze ade047d..c217faa; switch 2c750a1; briefing gate **2c29b42** | `test_w4_laura_ceo` 14/14 at f87e430 (14 static at 2c29b42) | SECREVIEW-LAURAONE-f87e430: NO BLOCKER for (a) merge-with-switches-OFF and (d) OA-LCEO-1. Its R-2 fix in 2c29b42: **NONE** | L3's shared routing and credentials; integration onto 82a3b7a (INTEG6-prep conflict resolutions) | +1 lazy table `laura_cost_events`. Additive and rollback-safe: proven on PG16 to LISTREADY, 1580053 and b931d17 (`evidence_INTEG6prep/pg_migration_output.txt`). New allocation stops inside the unchanged CA$0.50/day | `BRAMBLELOOP_LAURA_CEO_MODEL`, default **OFF**. OFF gates converse, executive, exec_rank and, from 2c29b42, the briefing synthesis | `ops/deploy.sh --rollback-to <predecessor>`. The schema is left in place and ignored by older code | **AFTER-review** (see §2, N-L1). **Behaviour change:** with 2c29b42 and the switch OFF, the CC briefing that production synthesises today with Anthropic (`laura.ceo_briefing@4`, since hotfix 7bbbe72) becomes deterministic. It is safe (no spend), but it is a visible regression unless the owner sets the switch (OA-LCEO-1) |
| **L2. Private Laura on Venice** (VENICE): ADD-PLV-01..08; D-W4-VENICE, D-W4-PL-VENICE, D-W4-PL-VENICE-ADULT | freeze f535597..98110d8; adult register fcb2bcd; fixes 89860a1 and later | `test_w4_venice` 19/19; pl_* suites | SECREVIEW-LAURAONE (BLOCKER for activation, later fixed), -c13e20d, -f87e430: NO BLOCKER for (b) OA-LCONT-3. bcce679 (integration on b997efd): NO BLOCKER | L3's private store | Private store: no schema change (the `xing` row kind is ignored by old code) | `BRAMBLELOOP_PRIVATE_PROVIDER`, unset = **OFF** (no provider, no reply). Activation also needs `BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1`, `BRAMBLELOOP_PRIVATE_MEMORY_KEY`, `VENICE_API_KEY` and the daily CAD limit | Unset the provider (deny). After use, follow the S-2 rollback steps (LAURAONE.md §10b) **before** going below this release | **AFTER-L-batch reviews** (it ships dark). ADD-PLV-07 stays OPEN until the production runbook passes |
| **L3. Unified Laura thread** (LAURAONE): ADD-LCONT-01..13; D-W4-LAURA-UNIFIED | freeze 72ca645..f87e430; R-1 and R-3 in **2c29b42** | `test_w4_laura_unified` 53/53 at f87e430 (54 static at 2c29b42) | f87e430 review: NO BLOCKER for (c); "fix R-1 before OA-LCONT-1, R-3 before OA-LCONT-2". The R-1 and R-3 fixes in 2c29b42: **NONE** | L2 | +1 lazy table `laura_boundary_crossings`, additive (PG16 proof as L1). **Privacy, not schema:** after use, older code ignores the sealed `label`/`excluded` flags (bcce679 S-2) | `BRAMBLELOOP_LAURA_UNIFIED=venice`, default **OFF** (the split routes keep working) | S-2 operator steps, then deploy rollback | **AFTER-review** of 2c29b42 |
| **L4. Restricted business-context feed to Venice**: ADD-LCONT-10, -12, -13; D-W4-LAURA-UNIFIED-FEED | 3b7e6d0, 3dc3ced; S-3 752cb53 | in `test_w4_laura_unified` | f87e430: NO BLOCKER for OA-LCONT-2 once R-3 is fixed (in 2c29b42, unreviewed) | L2, L3 | none beyond L3 | `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1`, default **OFF**. The feed-preview route is AO but needs the live private grant (S-3) | as L3 | **AFTER-review** of 2c29b42 |
| **L5. Laura transport hardening** (N-9 no-redirect opener on keyed Anthropic and BFL calls; Venice credential card S-4) | 752cb53, 2c750a1 | `test_w4_fluxapi` 13/13, `test_w4_close5_vision_timeout`, `test_cert_spend_hosts` (S-6 per-URL allowlist) | f87e430: N-9 YES (test gap R-9) | none | none | **AO.** It changes the *existing* paid transports' redirect behaviour. DET, MF, SF (it refuses redirects; it never adds a call) | deploy rollback | **YES with L-batch.** It cannot ship without L1–L4 (same commits) |
| **L6. Laura-on-listings integration** (INTEG6-prep: merge 84a5e10, harness fix b857233, migration proof d58686a) | **73e1580** | 50/53 focused. The 3 failures have a known cause, fixed on 82a3b7a by 58aea40 | **NONE.** bcce679 reviewed the same Laura code merged onto b997efd, not onto listings | 82a3b7a deployed first; 2c29b42 merged on top | 147 tables: +2 listings, +2 Laura. Additive; rollback-safe to LISTREADY, 1580053 and b931d17 (PG16, local) | n/a | as L1 | **NO until re-integrated on 82a3b7a.** Its base b9137b5 is older than the listings release; a redo is needed with a sw.js bump past v24 |

### 1b. `w4-FMBATCH1` @ 871b84a3

The branch is linear, so its first two commits (be3fdd6a) form a cut point.

| Feature (requirement IDs) | Commit | Tests (reported) | Independent review | Dependencies | Production compatibility | Feature flag | Rollback path | Ship independently |
|---|---|---|---|---|---|---|---|---|
| **F1. Attribute drift monitor**: F-010 | 89bc962a | `test_w4_fmbatch1_drift` 9/9 (mutation-checked) | **NONE** | the taxonomy refresh in production since b997efd | No schema change (existing `EtsyTaxonomySnapshot`, incidents) | **AO.** It runs on the daily `listing.taxonomy_refresh`. DET, MF, SF. **Not RO:** a CHOSEN profile on a changed node opens a **halting P1** and re-queues `listing.seo` (the existing handler). FMBATCH1 §2 says production's first property-schema read is itself a "new snapshot", so expect re-queues on day 1 after the listings release | deploy rollback; resolve the incidents | **AFTER-review**. Most valuable once listings are live |
| **F2. Severity-based auto-rollback**: F-381 | be3fdd6a | `test_w4_fmbatch1_rollback` 9/9 (4 real `deploy.sh` runs against a bare remote); test_deploy_guard, test_deploy_path, test_w4_rollback_rehearsal, test_w4_smoke | **NONE** | none (CLOSE6 edits the same `deploy.sh` lines) | ops tooling only | `AUTO_ROLLBACK`, default **1 (on)**. A P0 readback regression rolls production back automatically; `AUTO_ROLLBACK=0` reports only | `git revert` of `deploy.sh`; `AUTO_ROLLBACK=0` at once | **AFTER-review**. It is on the deploy path, so it acts on its own release |
| **F3. Research discipline**: F-405, F-408, F-411, F-419, F-420, F-426, F-432, F-435, F-444, F-449, F-412 | 024897cc, 13a32db7 | `test_w4_fmbatch1_research` 13/13; `test_w4_research` 10/10 (updated) | **NONE** | none | **+2 nullable columns** `research_tasks.deadline` and `detail`, added by `core.migrate.apply`. Additive; old code does not map them, so rollback is safe by inspection. **No PG proof** | AO, DET, MF, SF | deploy rollback | **AFTER-review** (and an `apply` check on PG, as INTEG5/6 did) |
| **F4. Research run fetch step + promotion**: F-431 | 2716d560 | `test_w4_fmbatch1_research_run` 5/5 (sockets refused) | **NONE** | F3 | none | `BRAMBLELOOP_RESEARCH_FETCH`, default **OFF** (allowlisted, respects robots) | unset | AFTER-review |
| **F5. Signal hygiene**: F-139, F-140, F-149 | 8350270f | `test_w4_fmbatch1_hygiene` 6/6 | **NONE** | none | stored as `ops.disk_sample` records; no new table | AO in the 15-min `ops.health` sweep. DET, MF, SF; opens and resolves incidents, never fails the sweep | rollback | AFTER-review |
| **F6. Provider dependency**: F-092, F-093, F-094, F-095 (partial), F-099 | da81fe71 | `test_w4_fmbatch1_providers` 6/6 | **NONE** | none | none | AO on the daily `ops.dependencies`. DET, MF, SF. **F-095 changes `failover.decide`:** a fallback whose contract FAILs is no longer routed. That is fail-closed, but it is a live routing change | rollback | AFTER-review |
| **F7. Test failure classification**: F-150 | 3921d9d7 | `test_w4_fmbatch1_failclass` 2/2 | **NONE** | none | tooling (`run_tests.sh`) | AO, tooling | revert | AFTER-review |
| **F8. Dashboard order and folds**: F-200, F-201; **CC gaps** F-621, F-661, F-668, F-729; **F-621 KPI trend** | 7efbec9b, 252ad896, d73c318a | `_dashboard` 3 (static), `_cc` 4/4, `_pwa` 3/3 | **NONE** | none | none | AO. RO, DET, MF, SF | rollback | AFTER-review |
| **F9. Ranking, capacity and compression**: F-394, F-470, F-489 (F-457 target proposed) | 0b004389 | `test_w4_fmbatch1_swarm` 5/5 (4 static) | **NONE** | none | none | AO, RO/DET | rollback | AFTER-review |
| **F10. Improvement audit record**: F-398 | 1f78dcee | `_audit` 3/3 | **NONE** | none | none | AO, RO/DET | rollback | AFTER-review |
| **F11. Commit-signing truth**: F-153, F-156, F-157 | 418d59c8 | `_signing` 7/7; test_deploy_guard | **NONE** | none | `RELEASE_<sha>.json` gains `signing` | `BRAMBLELOOP_SIGNING_REQUIRED`, default **OFF** | revert | AFTER-review. Signing is **not** in place; this row proves honest reporting only |
| **F12. Spend by requirement**: F-107 | d2fd5071 | `_value_units` 3/3 | **NONE** | none | none (attribution in existing rows) | AO, RO/DET/SF | rollback | AFTER-review |
| **F13. Physical truth dashboard**: F-089 | fccea594 | `_physical_truth` 4; `test_route_auth_default_deny` 7/7 | **NONE** | none | new GET `/api/physical-truth`, operator-only | AO, RO | rollback | AFTER-review |
| **F14. Provider compatibility pack**: F-096 | ae9d7b89 | `_compat` 6/6 | **NONE** | F6 | none | Scoring is AO and DET. **A live run is a paid drill**, on demand only, reserved through the ceilings | rollback | AFTER-review |
| **F15. Provider boundary**: F-091 (**partial**) | e97bd813, 06510fd2 | `_provider_boundary` 4/4; spend-discipline suites | **NONE** | none | none | `BRAMBLELOOP_MODEL_VENDOR`, default `anthropic`. It refactors the **existing paid** `intel/serp` and `intel/vision` paths (same ceilings) | rollback | AFTER-review. A paid-path refactor needs review |
| **F16. Evidence share, seasonal cohort, owned surfaces, pricing shadow trial, cost learning**: F-190, F-194, F-198, F-374, F-389 | b555f5f1, 07807184, 7f4a898f, c26c58f0, 04ac701f | 1 + 3 + 2 + 4 + 3 tests | **NONE** | none | none | AO, DET, MF, SF. The pricing trial has no executor; cost learning only proposes | rollback | AFTER-review |
| **F17. Department records and pull order**: F-601, F-454, F-656 | 871b84a3 | `_departments` 4 (static) | **NONE** | none | WATCHING spans in `company_memory` | **AO. Changes the orchestrator's pick order** (RUN, then GROW, then IMPROVE, ahead of value). DET, MF, SF | rollback | AFTER-review |
| **F18. Ledger, triage, override and re-gate proposals** (records) | a0ade849, 752221f1, 8ea27596 | n/a | n/a | coordinator decisions; CLOSE6 for 9 rows | records only | n/a | n/a | YES as records. Nothing in them is applied |

### 1c. `w4-AGENTS` @ a14c9ef8

| Feature (requirement IDs) | Commit | Tests (reported) | Independent review | Dependencies | Production compatibility | Feature flag | Rollback path | Ship independently |
|---|---|---|---|---|---|---|---|---|
| **A1. Storefront Director agent, gated storefront writes**: MP v1.2 §6/§16, F-233, F-515, F-584, F-526 (proposals), F-454/F-890 | 8a97fbf..b5226f7 | `test_w4_agents` 13/13 plus 25 focused suites | **SECREVIEW-AGENTS-b5226f7: PASS**, M-1 and M-2 MEDIUM, L-1..L-3 LOW | LISTREADY (merged, d69a3ec) | No new table (grant ledger and job rows) | Writes are denied unless **all** of these hold: `BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED=1` (unset = deny); a publishing phase (SHADOW holds, and no client is built); a per-proposal sealed owner grant. The daily `storefront_review` cadence is **AO** (DET, MF, SF, CA$0 ceiling) and writes review rows and owner cards | unset the kill switch; deploy rollback | **AFTER-review** of the fixes (A2) |
| **A2. M-1/M-2 fixes**: owner-session plus step-up approval; Ed25519 web-only signing key | **a14c9ef8** | `test_w4_agents_secfix` 6 (static) | **NONE** (fixes after b5226f7) | A1; `cryptography` is already locked (50.0.1) | Grants are now Ed25519. No production grant exists, so nothing needs migrating | New env vars `BRAMBLELOOP_STOREFRONT_SIGNING_KEY` (web only) and `_VERIFY_KEY`. Unset means every write stays held | as A1 | **AFTER-review** |
| **A3. Owner-card changes** (OA-D1 and OA-E superseded, OA-C drops C5; the Director never asks for `policy_additional`) | 527720b, bd9c6cd | in `test_w4_agents`, `test_w4_listready` | b5226f7 (partly); bd9c6cd **NONE** | LISTREADY | none | **AO.** Owner-visible change to the launch card set. DET, SF | rollback (cards re-derive) | AFTER-review |
| **A4. Quality and Compliance agents** (gate.quality, cir.twin, cir.reverse, gate.asset_truth, gate.policy) as re-verification, never a verdict path; `cir.revise`; no photography request for a CIR-less slug; `radar.competitor_snapshot` (aggregates only, no competitor content); gate.quality into COO and Laura priorities | 5544762c, 33903f47, 475a2055, 8c6d0fbd, 499842e4 | `test_w4_departments` 11/11 (12 static) | **NONE** | none | none | AO, DET, MF, SF (the report states CA$0, no network, no model) | rollback | AFTER-review |
| **A5. Product Family Engine** (s33, F-359, s5); F-789 conflict reported, not built | a702834d | in `test_w4_departments` | **NONE** | none | none | AO, RO/DET | rollback | AFTER-review |
| **A6. Baby and children's priority family**: F-351, F-353, F-358, F-359, F-365, F-366 | 71fbab29 | `test_w4_children` 5 (static) | **NONE** | none | none | AO, daily `intel.children_portfolio`. Reads observed listings; DET, MF, SF | rollback | AFTER-review |
| **A7. VISNEXT2 staged FLUX method** (stage A identity anchor, stage D edit base); Cloudline acceptance harness and definition; 1K fidelity disproof | merge 13bd73e3 (VISNEXT2 5d16506) | `test_w4_visnext2` 11/11 | **NONE.** 7f6dbe8 reviewed VISNEXT, not VISNEXT2 | the paid image path (owner image-spend authority) | none (controlled-experiment tables already exist) | Stage A is **AO inside the image pipeline**, which runs only under image-spend authority. **It adds one generation call per run**, inside existing ceilings. The Cloudline `--live` run is owner-run, with a CA$5 cap shared across the group | rollback | AFTER-review. It is spend-adjacent |
| **A8. Visual batch**: F-126 benchmark superseded (stops the daily benchmark re-runs), F-218 sentinel; F-515 trace | 4766be8a, 7b4e29f3 | `test_w4_departments`, `test_image_bench`, `test_w4_close5_rows` | **NONE** | A7 | none | AO, DET; it *reduces* spend | rollback | AFTER-review |

### 1d. `w4-CLOSE6` @ ff788bd

| Feature (requirement IDs) | Commit | Tests (reported) | Independent review | Dependencies | Production compatibility | Feature flag | Rollback path | Ship independently |
|---|---|---|---|---|---|---|---|---|
| **C1. Etsy Ads eligibility, recheck, credit**: F-685 (closed on b931d17), F-686, F-688 | 01b1c8cf | `test_w4_close6_ads` 5 | **NONE** | none | **+1 table `ads_credit_cycles`** (`finance.credits`, created at boot). Additive; **no PG proof** | AO, RO/DET, SF | rollback | **NO** until re-integrated (§2, N-C1) |
| **C2. Ask intents and overnight brief**: F-664, F-666 | c8fcf17c | `_ask` 4, `_brief` 3 | **NONE** | none | none | AO, RO/DET/MF/SF | rollback | NO until re-integrated |
| **C3. Readback gate**: F-144 (board rule, 6 more readback features, evidence persisted) | 30fdd210 | `_readback` 4; `test_w4_smoke` 10 | **NONE** | the deploy path; FMBATCH1 F2 edits the same lines | `ops/readback.py`, `ops/deploy.sh` | AO on deploy (tooling) | revert | NO until re-integrated |
| **C4. Consumer receipts**: F-834 (TESTED override accepted, D-W4-CLOSE6-OVERRIDES) | a9e5395a, 8e4efd39 | `_proof` 3 | **NONE** | none | scripts and records | tooling | n/a | NO until re-integrated |
| **C5. Causal timeline**: F-662 | 5d248cff | `_timeline` 3 | **NONE** | none | **+1 lazy table `job_links`.** One best-effort write on every `JobContext.enqueue`. Additive. **Residual risk (LOW):** this is the same lazy pattern behind the launch_review export defect. It is mitigated because `record()` calls `ensure_table` right after the import. Registering it in `Database.create_all` would remove the risk | **AO, not RO:** a new row per follow-on job. DET, MF, SF; a failure never blocks the enqueue | rollback (the table is ignored) | NO until re-integrated |
| **C6. Shop About reading**: F-040 | e93b2fc3 | `_shop` 4 | **NONE** | **conflicts with FIRSTSALE2** (in 82a3b7a) in both files it changes | none | **AO: a new launch-readiness hold.** Launch is held while the owner's dated About reading is missing or stale. The owner says the About was done on 2026-10-11 (LAUNCHPREP), but evidence still needs the reading POSTed | rollback | NO until re-integrated; it then adds one owner observation |
| **C7. F-872 production closure; F-273/F-538 re-gate; B2 #11/#12 re-gate; F-145..F-148 overrides; F-846 at TESTED; registry titles** | e93b2fc3, 6faba33f, 0784fe1e, ff788bd9 | `_scope` 3, `_titles` 3, `_hygiene` 3 | n/a (records) | coordinator acceptance (recorded) | records | n/a | n/a | NO until re-integrated. The boards conflict and must be **regenerated with the generator**, not hand-merged |

### 1e. `w4-LAUNCHPREP` @ fcc6d961 (documents only)

| Feature | Commit | Tests | Review | Dependencies | Compatibility | Flag | Rollback | Ship |
|---|---|---|---|---|---|---|---|---|
| Smallest legitimate physical test; reconciled Etsy owner checklist; paste text; observation and physical-test templates; readiness of the 8 opening products and a seasonal launch order (LAUNCHPREP E1–E7 were built in LISTREADY 7eec363) | 22fe73db, fcc6d961 | none (documents) | not needed (no code) | none | none | n/a | revert | **YES**: a clean merge. Every push to the production branch is a deploy, so ride it with the next batch rather than spend a suite on it alone |

## 2. Every NO, and every AFTER-X, with the smallest action that resolves it

| ID | Blocks | Specific technical dependency | Smallest resolving action |
|---|---|---|---|
| **N-L1** | L1, L3, L4 | 2c29b42 (R-1 one-tap clause split, R-2 briefing gate, R-3 audit by `sent`) changes security-relevant code after the last review (f87e430) | **Delta review** of `git diff f87e430..2c29b42 -- brambleloop/src brambleloop/tests` (11 files, +118/−30) |
| **N-L2** | L6 | INTEG6-prep is based on b9137b5, not 82a3b7a. It has never been tested with 58aea40 and the rest of the listings release | **Re-integrate:** a new branch from 82a3b7a; merge 73e1580 (resolve DECISION_LOG append-only, regenerate the decision index, sw.js to **v25**); merge 2c29b42 (clean); re-run INTEG6-prep's 53 focused suites, expecting 53/53; re-run the PG16 migration proof |
| **N-L3** | L-batch deploy | No review covers Laura merged onto listings (bcce679 was Laura on b997efd) | **Integration review** of the re-integrated tree vs 82a3b7a: credentials `_effective_model` resolution, `anthropic.py` (launch-review batch grant together with N-9), the cert-spend-hosts allowlist |
| **N-L4** | owner experience after the L-batch | With 2c29b42 and `BRAMBLELOOP_LAURA_CEO_MODEL` OFF, the CC briefing stops calling Anthropic | **Owner decision** (OA-LCEO-1, 2 min, inside the existing CA$0.50/day): set the switch, or accept a deterministic briefing. Not a blocker |
| **N-F1** | F1, F2 | No review | **Review** of `b997efd..be3fdd6a` (2 commits, 8 files, +1020/−3): `taxonomy_drift.py`, the `release.py` hooks, `deploy.sh`, `rollback_decision.py` |
| **N-F2** | F3–F17 | No review; 26 commits; it touches routing (`failover.decide`), the orchestrator pick order, paid-path refactors (serp, vision), `deploy_guard` and a schema migration | **Review** of `be3fdd6a..871b84a3` (it can be split by batch letter), plus the `core.migrate.apply` check on PG16 for the two `research_tasks` columns |
| **N-A1** | A1–A8 | b5226f7 is reviewed; 15 commits after it are not: the M-1/M-2 fixes (`approvals.py`, `sealed_chain.py`, `storefront_authority.py`), the department batches, VISNEXT2 (image pipeline), children | **Delta review** `b5226f7..a14c9ef8`, with priority on a14c9ef (closing M-1/M-2) and the VISNEXT2 merge. L-2 (DIFFERS overwrites the owner's live text) is unfixed and is LOW: fix it before any storefront write leaves SHADOW, not before deploy |
| **N-C1** | C1–C7 | 13 conflicts onto 82a3b7a. Two are code (`shop_observations.py` and `launch/readiness.py`, against FIRSTSALE2's per-surface collectors). The boards and ledgers are generated artefacts | **Fix plus merge:** rebase or re-merge CLOSE6 onto the release head; hand-merge the `about` page into FIRSTSALE2's `PAGES` table (and decide whether it joins `OWNER_ATTESTED_PAGES`, the session-plus-step-up rule LISTREADY R1 set for owner attestations) and the readiness hold into `first_sale_surfaces.readings`; **regenerate** boards, ledgers and `final_master_closure` with their generators; then a **review** (none exists). CLOSE6 §11's finding (5 surfaces with no collector) is already resolved by FIRSTSALE2 on 82a3b7a, so drop it there |
| **N-C2** | C3 with F2 | Both edit the `deploy.sh` readback block | Ship them in **separate batches**, F2 first. Merge CLOSE6's `rb_json` path into F-381's `--json` as FMBATCH1.md §2 says, and re-run `test_w4_fmbatch1_rollback`, `test_w4_close6_readback` and `test_w4_smoke` |

## 3. Runtime credit: what needs Anthropic (or other) credit, and how each degrades

| Feature | Needs at runtime | Without the credit or key |
|---|---|---|
| L1 Business Laura (switch ON) | Anthropic, inside `laura` CA$0.50/day (converse 8%, executive 5%, exec_rank 2%; about CA$12/month) | The report says the model path refuses on budget or availability, and Laura answers deterministically from records with an honest message. ADD-LCEO-07 is not yet proven in production. **Switch OFF (the default) makes no Anthropic call at all from 2c29b42 onward** |
| L1 briefing (switch ON) | Anthropic (existing `laura.ceo_briefing`) | `synthesize` returns `unavailable`; the deterministic briefing is shown |
| L2/L3/L4 Venice | **Venice** API credit (not Anthropic); `VENICE_API_KEY` | Laura says so. There is no silent fallback to a business provider (LAURAONE §2 rule 9). The register OFF sends nothing |
| F14 compat pack live run | Anthropic (a paid drill) | On demand only; the reservation refuses before any call |
| F15 serp and vision (existing paths, refactored) | Anthropic, as today | Same as today: `check_budget` refuses before the call |
| F1 drift → `listing.seo` | the existing handler | No new model path is added by F-010 |
| A7 stage A anchor and judges | BFL (generation) and Anthropic (vision judges), only under image-spend authority | An UNKNOWN verdict sends an owner review card and **the run holds**; every image is kept (fail closed) |
| A1–A6, A8, F3–F13, F16–F17, C1–C7, LAUNCHPREP | none | n/a: deterministic, model-free |
| (82a3b7a itself) D-W4-LAUNCH-VISION-BATCH | Anthropic, max CA$7.07, after an owner step-up | Not activated until the owner steps up. Out of scope here |

## 4. Proposed release batches, in order (after the listings release 82a3b7a)

**Each batch:**
- is cut from the previous released head;
- gets one full certification suite on its exact SHA (deploy_guard);
- is deployed with `ops/deploy.sh`;
- rolls back on its own with `ops/deploy.sh --rollback-to <previous head>`, because every
  schema change in these batches is additive.

Batches 1 and 2 share no source files, only generated ones. If F-381's review returns first,
they may swap.

### Batch 1: Laura, all switches OFF (+ LAUNCHPREP documents)

- **Contents:** 82a3b7a → merge `w4-INTEG6-prep` 73e1580 → merge `w4-LAURAONE-freeze` 2c29b42 →
  merge `w4-LAUNCHPREP` fcc6d961.
- **Merge order:**
  1. INTEG6-prep. Resolve DECISION_LOG append-only, LISTREADY block first; regenerate
     `decision_index.json`; sw.js to v25.
  2. 2c29b42. A clean merge.
  3. LAUNCHPREP. A clean merge.
- **Reviews still needed:**
  - the delta review f87e430..2c29b42 (N-L1);
  - an integration review of the merged tree vs 82a3b7a (N-L3).
- **Before the suite:**
  - the 53 focused Laura and listings suites from INTEG6-prep §5, expecting 53/53 now that 58aea40
    is in;
  - the PG16 migration proof re-run: expect +2 Laura tables over 82a3b7a, additive, rollback-safe
    to 82a3b7a and 15800536.
- **Owner:**
  - no action is needed to deploy;
  - decide OA-LCEO-1 (N-L4) so the briefing keeps its model synthesis;
  - all other Laura activations (OA-LCONT-1..3) stay separate, post-deploy decisions.
- **Rollback:** the deploy rollback. If any unified or private switch was used, follow the S-2
  steps first.

### Batch 2: FMBATCH1-A (F-010 drift monitor + F-381 auto-rollback)

- **Contents:** the release head → merge `w4-FMBATCH1` at **be3fdd6a**, the first two commits
  only. Regenerate `autonomy_map.json` (one new edge: taxonomy_drift → listing.seo).
- **Review still needed:** N-F1.
- **Why early:**
  - F-010 protects live listings from Etsy taxonomy changes, and matters as soon as listings
    exist;
  - F-381 then guards every later batch's deploy.
- **Watch after deploy:** the first property-schema read is a new snapshot. Expect `listing.seo`
  re-queues, and halting P1s for any CHOSEN profile on a changed node.

### Batch 3: AGENTS (Storefront Director in SHADOW; departments; VISNEXT2)

- **Contents:** the release head → merge `w4-AGENTS` a14c9ef8. It is clean against 82a3b7a.
  Against batch 1 the resolution is DECISION_LOG, decision index and sw.js only. Regenerate the
  autonomy map.
- **Review still needed:** the delta review b5226f7..a14c9ef8 (N-A1).
- **Before the suite:** the integration tests of `laura/executive/loop.py` with both PROVIDER
  changes: `test_w3_laura_core_*`, `test_w4_laura_ceo`, `test_w4_agents`.
- **Operator (CA$0):** generate the Ed25519 key pair only when storefront writes are to be
  enabled. It is not needed to deploy.
- **Possible split:** VISNEXT2 (13bd73e3) could be split out, but later commits (4766be8a) build
  on it. Keep it whole unless review finds a problem in VISNEXT2.

### Batch 4: CLOSE6, re-integrated

- **Contents:** a new branch from the release head with CLOSE6 re-applied (N-C1).
  - The code conflicts are resolved against FIRSTSALE2.
  - The boards, ledgers and closure are regenerated.
  - The `deploy.sh` readback block is merged with F-381 (N-C2).
- **Review still needed:** a full review of the re-integrated CLOSE6 diff.
- **Recommended in the same change:** register `runtime.lineage` in `Database.create_all` (C5
  residual).
- **Owner:** after deploy, one About observation POST (F-040), or launch readiness holds. The
  template sits beside LAUNCHPREP's `observation_templates.json` pattern.

### Batch 5: FMBATCH1-B (the rest of FMBATCH1)

- **Contents:** the release head → merge `w4-FMBATCH1` 871b84a3 (`be3fdd6a..871b84a3`). Resolve
  BUILD_STATE and regenerate the autonomy map.
- **Reviews still needed:**
  - N-F2;
  - the PG16 `core.migrate.apply` proof for the two `research_tasks` columns.
- **Possible split if review is slow:**
  - 5a: records and observability (F5, F7–F13, F16, F18);
  - 5b: behaviour changes (F6 routing contract, F15 paid-path refactor, F17 pull order, F3/F4
    research schema).

  The commits interleave, so a split needs a cherry-pick branch and its own focused run.
- **Coordinator decisions** (not blockers to deploy): `OVERRIDES_PROPOSED_FMBATCH1*.json` and
  `FM_REGATE_PROPOSED_FMBATCH1.json`, best taken after batch 4, because 9 rows depend on CLOSE6.

## 5. Summary of blockers

1. **Every branch lacks at least one independent review of its head.**
   - Laura has the smallest gap (118 lines plus an integration review).
   - FMBATCH1 and CLOSE6 have none at all.
2. **INTEG6-prep must be redone on 82a3b7a.** Its 3 failures are expected to clear with 58aea40,
   but that is unverified.
3. **CLOSE6 has two real code conflicts with FIRSTSALE2** and must be regenerated, not
   hand-merged.
4. **FMBATCH1 F-381 and CLOSE6 F-144** edit the same deploy lines, so ship them in different
   batches.
5. **There is no owner blocker to deploying any batch with its switches OFF.**
   - **Behaviour changes the owner will see:**
     - the briefing becomes deterministic (batch 1) unless OA-LCEO-1 is set;
     - the drift monitor may halt a listing (batch 2);
     - the storefront card set changes (batch 3);
     - a new About-reading hold (batch 4);
     - a new orchestrator pull order (batch 5).
   - **Activations needing credit:** Venice credit for Private or Unified Laura; Anthropic inside
     `laura`'s CA$0.50/day for Business Laura's model. Each is a separate owner action.
