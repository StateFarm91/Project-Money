# Production catch-up: release audit and Railway package (lane W4-RELPKG)

Written 2026-10-10 (UTC) by lane W4-RELPKG. **Read-only audit: nothing deployed, nothing pushed to
`claude/repository-setup-nc9x6o`, no Railway mutation, no test suite run.** The only production
read was the public `GET /health` endpoint.

| | SHA | Branch | Evidence |
|---|---|---|---|
| Production (observed) | `fcb982d57e291c88d9f78eaa091e90904b6c2cc9` | `claude/repository-setup-nc9x6o` | `GET https://brambleloop-os-production.up.railway.app/health` → `status ok`, `build.commit fcb982d…`, read 2026-10-10; `origin/claude/repository-setup-nc9x6o` = fcb982d |
| Candidate base | `52e216cd56789c489ae13f48fd2696c97edff8a4` (committed 2026-10-10T02:43:31Z) | `claude/w4-SHADOWFIX`, also = `origin/claude/visual-investigation` | `git rev-parse` |

Successor candidates are expected to add only small test-fix commits on top of 52e216c. Every
count below is for **fcb982d..52e216c**. Re-run section 1 against the final SHA before deploying.

## 1. Exact counts

| Measure | Command | Value |
|---|---|---|
| Commits | `git rev-list --count fcb982d..52e216c` | **919** |
| First-parent commits | `git rev-list --first-parent --count fcb982d..52e216c` | **348** |
| Non-merge commits | `git rev-list --no-merges --count fcb982d..52e216c` | 711 |
| Merge commits | `git log --merges --oneline fcb982d..52e216c \| wc -l` | 208 |
| Files changed (whole repo) | `git diff --shortstat fcb982d 52e216c` | **2,326 files**, +727,464 / −3,807 (1,989 added, 337 modified, 0 deleted, 0 renamed) |
| Files changed (`brambleloop/src`) | `git diff --shortstat fcb982d 52e216c -- brambleloop/src` | 634 files, +160,327 / −2,948 (436 added, 198 modified, 0 deleted) |
| Fast-forward possible | `git merge-base --is-ancestor fcb982d 52e216c` | **yes** (exit 0): fcb982d is an ancestor of 52e216c; the production branch has no commit the candidate lacks |

## 2. Completed work included (fcb982d..52e216c)

These are grouped from `git log --merges fcb982d..52e216c` and `COMPLETION_BOARD.json` (as of
2026-10-07T08:19Z; its lane statuses lag: AUTO, PIPE, FM2, PIPE3, RENDER and VISUAL2 still read
"running", but their branches are merged, as section 3 shows).

- **Build 2:** the repair clusters (platform C-65/68/69, orders C-64, growth C-66/70, design C-61,
  improve C-62/63, intel C-71, residue wave, platform2 and improve2 hardening, registry 226
  COMPLETE+PROVEN); FB-1 clusters C, D, E and F; the Codex Final Build integration; the fb2, fb3,
  fb4 and rc1 lanes; the J product, finance, security and autonomy audits; the r2 lanes; and
  **W4-B2** (e87534b: ledger 320/320, OPEN-DEFECT 2→0, `closure.dashboard()`), plus 874bad7
  (Build 2 dashboard block degrades to UNKNOWN instead of going blank).
- **Final Master / FM2:** v11-CANON, w3-K (v1.1 closure), w3-TOOLS (closure as a live gate),
  **W4-FM** (c525244: launch-critical OPEN 171→82), **W4-FM2** (553a05b), W4-GATESI (0d21dbe),
  W4-GATESB (adcc495), W4-K9 (bb0f43d and 275be50: 18/18 rows), and ab9b3fe (closure regenerated:
  launch-critical OPEN 15, COMPLETE 351, GATED 124).
- **Command Center (cc):** lane C (owner API, auth, approvals, emergency, Ask), lane D (mobile PWA),
  INT2, WIRE, w3-F (Laura Phase 1 and CC wiring), w3-K7 (ops truth and owner surfaces), w3-K11
  (authority and governance), w3-WIRE4, **W4-CC** (d6d7f45: Company, decision batches, Learn
  outcomes, money periods, estimate drift, completion board, deploy package), and **W4-OWNER**
  (6d446bb: 45 asks became 25 decisions in 9 batches).
- **Store/SEO:** lane F (Store Foundation), lane G (continuous SEO), w3-B, w3-C, w3-G, w3-I (Etsy
  technical readiness), w3-K1 and w3-K4, fb4-STORE, fb4-PUB, fb4-LAUNCH, **W4-STORE** and
  **W4-MJS** (via INTEG aa2fbbe and 7631026, b1a9e8e), and **W4-SEO** (c2386df: search packages
  for 7 viable products).
- **Product pipeline (PIPE/PIPE2/PIPE3/CAND):** **W4-PIPE** through 1de40ba (merged into PIPE2 and
  PIPE3; see section 3 for the excluded tail), with its tea-cosy worked-on-join fix carried
  separately in 711b0be; **W4-PIPE2** (411fd84: 8 candidates engineered, 5 certified);
  **W4-PIPE3** (3219a13: 9 non-viable products made viable); **W4-CAND** (472fcc9 via INTEG:
  pencil roll, stocking loop and advent garland 0.2.0); rc1-PAT and rc1-LST; w3-K3
  (listing-outcome intake); w3-K6 (physical evidence).
- **Visual/VISUAL2:** w3-H and w3-H2 (Visual R&D loop), w3-K12 (model-photography gates), w3-A,
  w3-A2 and w3-A3 (brand identity), **W4-VISUAL** (3591fa3), **W4-VISUAL2** (4839486 partial,
  then 77fc9a6), and **W4-RENDER** (5a586c0: multi-piece rendering).
- **Creative/CREATIVE2:** **W4-CREATIVE** (b2ec9c7: 0/11→6/11 needs_taste), **W4-CREATIVE2**
  (cbca1af: 11/11 needs_taste), and b528a2d (creative audit verdict follows the measurement).
- **Learn:** lane B (five launch policy loops), w3-K10, **W4-LEARN** (29459bb).
- **Autonomy/AUTO:** lane A (Executive Orchestrator and 11 charters), r2-AUTO, w3-D (orchestrator
  wiring), w3-HANG (CPU fix), INT3, **W4-AUTO** (6007899 via INTEG: `autonomy.status.agents`,
  `autonomy.rule1.measure`, judge fixes), **W4-CHAIN** (e9ef4c7: boot stall), 11c2720 (shadow
  invariant: the store.publish gate read writes nothing before it refuses), and 9274d00
  (deploy-blocker lane fixes).
- **Spend/Finance:** lane E (double-entry ledger, reconciliation, close, tax pack), lane H (ads
  readiness), r2-FIN, fb4-FIN, rc1-SPEND, rc1-ORD, w3-SPEND, **W4-SPEND** (98b10b5: K5b),
  **W4-SPENDA** (4fd143d: K5a attribution, credits), **W4-FIX-DSPEND** (fe5d7f2), and
  **W4-FIX-ORDERS** (662bba7).
- **Security:** r2-SEC, rc1-SEC, rc1-AUTH, rc1-OWN (release and rollback guard), w3-PRIV
  (encrypted owner-private context), FB-1 cluster F (hashed dependency lock, secret scan, deploy
  guard), w3-E (Laura memory permissions), and w3-HYG (test temp-dir hygiene).

## 3. Pushed work not included

`git fetch origin` (2026-10-10), then `git rev-list --count 52e216c..<b>` for all **87**
`origin/claude/*` branches. 80 branches have 0 commits outside the candidate. Every `origin/claude/w4-*`
branch except PIPE is fully contained, including AUTO 56b06a3, CAND 5c7130b, FM2 427b69d, PIPE3
04dd773, RENDER d07ca81, VISUAL2 6f1f471, CREATIVE2 56f73c7, FIX-DSPEND 874bad7, FIX-ORDERS d1d9fb0
and INTEG 9148bd7. Seven branches have commits outside the candidate:

| Branch | Head | Ahead of 52e216c | Classification | Evidence |
|---|---|---|---|---|
| origin/claude/fb4-FIN | c876ce8 | 1 | **Superseded (content included)** | `git cherry 52e216c origin/claude/fb4-FIN` = `-` (a patch-equivalent commit is in the candidate); merged as d581327 |
| origin/claude/fb4-J | f204e18 | 2 | **Superseded (content included)** | cherry `-` for d85ee19 and f204e18; merged as c0bf7f8 |
| origin/claude/fb4-LAUNCH | 4ae820c | 1 | **Superseded (content included)** | cherry `-`; merged as 9406404 |
| origin/claude/fb4-OPS | 0e0999c | 1 | **Superseded (content included)** | cherry `-`; merged as 0ede969 |
| origin/claude/fb4-PUB | 4b5ea2f | 1 | **Superseded (content included)** | cherry `-`; merged as 1872df7 |
| origin/claude/fb4-STORE | 7e47ad9 | 1 | **Superseded (content included)** | cherry `-`; merged as 68a5cb0 |
| **origin/claude/w4-PIPE** | **27105c6** | **5** | **Known exclusion (PIPE head 27105c6, backlog conflict). Note: the excluded tail also carries completed code, see below** | cherry `+` for 618befc, b7d21c1, 8e5f825 and 27105c6; dac2a72 is a merge of visual-investigation with no new content |

The fb4 rows are cosmetic: each branch head is a pre-rebase SHA whose patch is already in the
candidate.

**The W4-PIPE exclusion is wider than the backlog file.** The candidate holds PIPE through
1de40ba, plus the launch0.py change from 27105c6 (worked-on-join for the tea cosy), which 711b0be
carried in. `launch0.py` is identical to the PIPE head. These completed, pushed commits are
**not** in the candidate:

| Commit | What it holds | Files |
|---|---|---|
| 618befc | Reserves held to the Launch-0 standard in the inventory; the board's SEARCH is read from the drafted listing; a reproducible chain runner | `products/inventory.py` (+67), `products/pipeline_board.py` (+27), `w4/pipe_chain_run.py` (new, absent from the candidate), `tests/test_w4_pipe_board.py` (+51), `product_inventory_run.py`, `handoff_PIPE.md` |
| b7d21c1 | A fresh chain run over 9 products; the inventory honours the #297 evergreen pivot and verified reserve imagery | `products/inventory.py`, `PRODUCT_INVENTORY.json/.md`, `evidence_PIPE/chain_run_20261007.json`, test |
| 8e5f825 | Checkpoint | `products/pipeline_board.py`, `w4/pipeline_run.py` |
| 27105c6 | Backlog rows refreshed for 9 launch products; renderer asks routed to W4-RENDER (launch0.py part already in the candidate) | `PIPELINE_BACKLOG.json/.md`, `pipeline_board.py`, test, `handoff_PIPE.md` |

`git merge-tree --write-tree 52e216c origin/claude/w4-PIPE` conflicts in `PIPELINE_BACKLOG.json`,
`PIPELINE_BACKLOG.md` and **`products/pipeline_board.py`**. `inventory.py` and the test file merge
cleanly. So this is not only a data conflict. The inventory and board code changes, along with
their tests, are completed work that the release leaves out. **Deploy impact: low.** The change
covers the inventory and board reporting surfaces and research runners, not a publishing,
spend or security path, and production stays SHADOW. **Recommendation:** treat it as a deliberate
exclusion for this release, then fold it in afterwards: merge the PIPE tail, resolve
`pipeline_board.py` against PIPE2, PIPE3 and CAND, and regenerate the backlog. If the integrator
did not intend to drop the inventory and board changes, this is the one finding to act on before
freezing.

**Local-only branches (not pushed, so outside the pushed-work scope, listed for completeness):**
- `claude/rc1-*` (AUTH, ORD, OWN, SEC, SPEND) are each 20 commits ahead. Every non-merge commit
  shows as patch-equivalent (`-`). Superseded.
- `claude/b2r-orders2` has 2 unique commits (bd3eb18 "WIP orders2 (recovered)" and 3081402
  "Orders cluster CB2-O01..O10", 2026-09-27) and was never pushed. It appears superseded by the
  orders repair cluster 9931ebf (C-64) and the "orders2 in-progress snapshot" saved in 3d12491.
  Nobody has confirmed this line by line.

**Accidentally omitted completed work: none found**, other than the W4-PIPE tail above, which is
a known exclusion whose scope is wider than its label.

## 4. Database migration effect

The method is static and quick, not a test suite. `git archive` of each SHA's `brambleloop/src`
went into a scratch directory. `Database("sqlite:///…").create_all()` ran for each, and then the
candidate's `create_all()` (= `Base.metadata.create_all` + `core.migrate.apply`) ran on a copy of
the fcb982d database. SQLAlchemy `inspect` compared the results.

| Measure | fcb982d | 52e216c |
|---|---|---|
| Tables from `create_all()` | 51 | **126** |
| Columns | 557 | 1,441 |
| fcb982d DB upgraded by 52e216c `create_all()` | — | 126 tables; **0 columns missing** relative to a fresh 52e216c schema |

`core/migrate.py` is unchanged between the two SHAs. `core/db.py` changes in two ways.
`create_all` now imports 16 more model modules (Learn, draft intent, search visibility, autonomy,
SEO, accounting, ads readiness, SLO, Command Center, Laura core, cost attribution, credits, Visual
R&D, paid calls, authority). `resolve_url` now refuses SQLite by default on Railway, meaning when
any `RAILWAY_*` marker is set, or when the phase is not shadow. **On the host, a missing
`DATABASE_URL` therefore crash-loops instead of falling back to SQLite.**

**75 new tables:** `acct_challenges acct_exceptions acct_journal_entries acct_period_locks
acct_postings acct_statement_lines ads_finance_challenges ads_spend_proposals authority_policies
benchmark_fingerprints benchmark_licences brand_knowledge cc_kv cc_nonces cc_notifications
cc_owner_sessions cc_security_events cohort_memberships company_memory company_timeline
company_work_items competitive_standards cost_attributions culture_concepts culture_ip_elements
customers design_difference_ledgers draft_creation_intents etsy_taxonomy_snapshots
insights_snapshots job_checkpoints laura_challenges laura_identity_versions laura_priorities
learn_decisions learn_edges learn_gaps learn_lessons learn_nodes learn_policy_lessons
learn_proposals listing_outcomes listing_search_profiles listing_set_certificates
marketplace_capabilities mjs_mission_events operating_readings ops_leases ops_runtime_samples
order_versions orders owner_vetoes paid_call_records physical_photos pod_capability_readings
provider_credits registered_experiments search_visibility_items search_visibility_readings
season_harvests seasonal_teams seo_cycles seo_keyword_evidence seo_proposals seo_search_packages
serp_snapshots swarm_allocations trend_provenance visual_rnd_experiments visual_rnd_hero_variants
visual_rnd_identity_reviews visual_rnd_judgements visual_rnd_lessons visual_rnd_market
visual_rnd_pipelines`

**38 columns added to 11 existing tables:**
- `artefact_provenance`: code_commit, cost_cad, created_by, evidence, job_id, model, parents,
  provider, publication_authority, sha256, source, validation_status
- `benchmarks`: market
- `config_versions`: tests_declared
- `cost_entries`: evidence_ref, image_count, listing_id, observed_cad
- `growth_loops`: contribution_cad
- `jobs`: lease_token
- `ledger`: amount_original, basis, classification, currency, external_id, fees_basis,
  reconciliation_state, source
- `model_identities`: predecessor_key, retired_at
- `owner_actions`: expires_at, max_cost_basis, state, state_at, state_reason, why_software_cannot
- `teardown_findings`: confidence, raw_notes

**Additive only: confirmed.** No table is dropped, no column is dropped or renamed, no existing
column's type changes, and no existing column's nullability changes. `migrate.apply` adds each
missing column with `ALTER TABLE … ADD COLUMN <type>`, which is nullable at the database level,
and backfills literal ORM defaults. Columns the ORM declares NOT NULL therefore stay nullable on
a migrated database. That is what keeps rollback to fcb982d safe: fcb982d's INSERTs leave those
columns NULL rather than failing. The cost is that the forward code must tolerate NULL in rows
written during a rollback window, as `ops/ROLLBACK_RUNBOOK.md` already states.

**Refreshing `POSTGRES_MIGRATION_EVIDENCE.md` (2026-10-05): its counts are stale.** It reported
"21 changes, 51→83 tables" for the Final Build head at that date. Against 52e216c the delta is
**75 new tables and 38 added columns (51→126 tables)**. Because this lane commits only this file,
the refreshed figures live here; that document's method and limits still apply. This refresh used
SQLite on a schema-only database. It did **not** repeat the Postgres 16 data-preservation run
(Run 2), and nobody has rehearsed against a snapshot of the real Railway Postgres. That rehearsal
remains the recommended owner-gated pre-deploy step. Tables that modules create lazily outside
`create_all` (each lane's `ensure_tables`) are additive by the same rule but were not part of this
inventory.

## 5. Command Center status

There are 17 CC providers (`src/brambleloop/app/command_center/providers.py` `PROVIDERS`):
`autonomy, timeline, agents, improvement, accounting, accounting_drill, store_foundation, seo,
ads, slo, visual_rnd, visibility, search_evidence, laura_roadmap, ops_truth, authority_dag,
authority_policy`. Tabs (`static/js/routes.js` `TABS`): Laura, Home, Approvals, Money, Store,
Company, Completion effort, Operations, Autonomy & Learn, Insights, Notifications, Timeline, Ask
Company, Account, and Emergency/Drill views (`static/js/views/*.js`). The Company tab is
`company.company()`, served at `GET /api/cc/company`.

Providers registered but never called by any tab: `agents` (`autonomy.status.agents`, from
W4-AUTO), `authority_dag` and `authority_policy`. A grep for `providers.call("…")` finds no
reader for them. The Company tab uses its own `company.agents()`, and authority is POST-only
(`/api/cc/authority/approve/{key}`, `/authority/grant`).

| Owner item | Status | Evidence |
|---|---|---|
| Departments | **PRESENT** | `company.departments()` → section `departments`; `views/company.js`, `operations.js` |
| Agents | **PRESENT** | `company.agents()` (registry + jobs + `worker.CADENCES`) → `company.js`; `readers.agents` → Operations |
| Agent status | **PRESENT** | active/sleeping/blocked/unhealthy/UNKNOWN in `company.agents`/`department_state`; `company.js` |
| Current work | **PRESENT** | `current_job` (`company._current`) → `company.js` |
| Useful output | **PRESENT** | `last_useful` (`company._useful`) → `company.js`, `learn.js` ("Last useful action") |
| Blockers | **PRESENT** | `company._blockers` → section `blockers`; `company.js`, `operations.js` |
| Owner actions | **PRESENT** | `readers.owner_actions_summary` → `owner_actions`; `company.js`, `home.js` |
| Decision batches | **PRESENT** | `company.owner_decision_batches` (snapshot `OWNER_ACTIONS.json`, live fallback) → `approvals.js` (plus `not_yet_askable`) |
| Build 2 closure | **PRESENT** | `company.build2_snapshot` (30-min background TTL) → `build2_closure`; `company.js` |
| Final Master closure | **PRESENT** | `company.final_master` → `final_master_closure`; `company.js` |
| Completion board | **PRESENT, stale content** | `company.completion` + `GET /api/cc/completion` → `completion.js`. The shipped snapshot `snapshots/COMPLETION_BOARD.json` matches the research file, but `updated_at` is 2026-10-07T08:19Z, so 6 lanes show "running" and will read STALE (over 3 h). **Refresh the board and its snapshot before freezing.** |
| Product/listing pipeline | **PRESENT** | `company.pipeline` → `product_pipeline`; `company.js` |
| Store/launch readiness | **PRESENT** | `store_foundation` + `visibility` + `search_evidence` providers → `tabs.store`; `company.store_readiness`/`store_live_drift` → `store.js`, `company.js` |
| Visual | **PRESENT** | `visual_rnd` provider → `tabs.visual_rnd_section`; `company.visual_stages` (snapshot `VISUAL_STATUS.json`) → `company.js`, `learn.js` |
| Learn | **PRESENT** | `improvement` provider + `company.learn_outcomes` → `company.js`, `learn.js` |
| Money by period | **PRESENT** (no 7d window) | `tabs.money_window` → `accounting` provider `summary(window=)`; `GET /api/cc/money?period=`; `money.js`. "7d" is refused with 400 BAD_PERIOD by design (handoff_CC) |
| Estimated vs actual spend | **PRESENT** (settlement OWNER-GATED) | `tabs.estimate_drift_reading` (`finance.spend_report.estimate_drift`) → `money.js`; provider-bill settlement needs usage-API keys |
| Incidents | **PRESENT** | `readers.incidents` → Company status, Home, Operations; `operations.js`, `home.js`, `timeline.js` |
| Autonomy state | **PRESENT** | `autonomy` provider → Company, Operations, Autonomy & Learn (`learn.js`, `operations.js`) |
| Rule #1 state (per-department useful-work / idle-with-eligible-work defect) | **MISSING** | `autonomy/rule1.py` `measure()` is called only from `autonomy/proof.py` (offline proof). No CC provider, endpoint or view reads it. The per-agent provider `agents` (`autonomy.status.agents`) is **PROVIDER-ONLY**: registered, never called. |
| Authority DAG / policy (not on the owner's list; noted) | **PROVIDER-ONLY** | `authority_dag` and `authority_policy` are registered with no GET view; only the POST approve/grant routes exist |
| Timestamps / data freshness | **PRESENT** | every section is a `providers.envelope` carrying `as_of`/`basis`/`status`; `_shared.js` renders `as_of` and `stale`; `generated_at` on Company/Home |

**CC MISSING list:** Rule #1 state (only the autonomy summary is shown, not the Rule #1 defect
measurement). **PROVIDER-ONLY:** `agents` (W4-AUTO per-agent visibility), `authority_dag`,
`authority_policy`. **Weak spot:** the completion-board content is stale until it is refreshed.

## 6. Railway deploy action and rollback (commands only; NOT run)

`ops/deploy.sh` is the one sanctioned deploy. A push to `claude/repository-setup-nc9x6o` is the
deploy, because Railway service `brambleloop-os` builds on push. The script pushes the
**current checkout's HEAD**, and only after `ops/deploy_guard.py check` returns ALLOW. The guard
needs a **tracked** `brambleloop/release/RELEASE_<sha>.json`. **None exists in 52e216c**: only
`release/DEPLOYED_HISTORY.json`, which lists fcb982d. Without that record, deploy.sh refuses.
Even if the push were forced, the runtime boot guard would start SHADOW with a P1
`release.unproven_build`.

Let `FINAL` be the frozen candidate: 52e216c plus the test-fix commits, on branch `<final-branch>`.
Let `Y` be the release-record commit on top of it.

```sh
# 0. Clean checkout of the final candidate (never in a lane worktree)
cd /home/user/Project-Money && git fetch origin
git worktree add --detach .claude/worktrees/DEPLOY origin/<final-branch>
cd .claude/worktrees/DEPLOY
git merge-base --is-ancestor fcb982d HEAD && echo "fast-forward OK"
python3 ops/deployed_sha.py                     # expect fcb982d57e291c88d9f78eaa091e90904b6c2cc9

# 1. Release record (needs the validation lane's clean, full, release-eligible suite run on FINAL
#    in brambleloop/artifacts/suite_runs/ of THIS checkout)
python3 ops/deploy_guard.py record --sha FINAL
git add brambleloop/release/
git -c user.name=Claude -c user.email=noreply@anthropic.com commit -m "Release record for FINAL"   # = Y
git push origin HEAD:<final-branch>

# 2. Dry run (guard check only; never pushes)
DRY_RUN=1 ops/deploy.sh --deployed fcb982d57e291c88d9f78eaa091e90904b6c2cc9
#    expect: "deploy.sh: ALLOW <Y> (dry run; nothing pushed)"

# 3. OWNER ACTION REQUIRED first (CC_DEPLOY_PACKAGE.md section 7): approve the deploy; set the
#    BRAMBLELOOP_OWNER_PASSPHRASE_HASH / _TOTP_SECRET / TRUSTED_PROXY_HOPS=1 / PUBLIC_ORIGIN
#    variables; confirm DATABASE_URL on web, worker and scheduler (52e216c refuses SQLite on Railway).
#    Then the real deploy (fast-forward push of Y to claude/repository-setup-nc9x6o):
ops/deploy.sh --deployed fcb982d57e291c88d9f78eaa091e90904b6c2cc9

# 4. Verify (read-only)
python3 ops/deployed_sha.py                     # = Y
curl -s https://brambleloop-os-production.up.railway.app/health        # 200, build.commit Y
curl -s -o /dev/null -w '%{http_code}\n' https://brambleloop-os-production.up.railway.app/cc/          # 200
curl -s -o /dev/null -w '%{http_code}\n' https://brambleloop-os-production.up.railway.app/api/cc/company  # 401 without session
#    then: /api/verify ok; no release.unproven_build incident; append Y to release/DEPLOYED_HISTORY.json
```

Rollback to fcb982d follows `ops/ROLLBACK_RUNBOOK.md`. The script writes a commit on top of the
deployed Y that carries exactly fcb982d's tree, with `Rollback-To:` and `Rollback-Reason:`
trailers, and pushes it as a fast-forward. fcb982d qualifies as a target because it is listed in
`DEPLOYED_HISTORY.json`, which Y carries.

```sh
cd /home/user/Project-Money/.claude/worktrees/DEPLOY && git fetch origin
git checkout --detach origin/claude/repository-setup-nc9x6o      # the deployed Y
DRY_RUN=1 ops/deploy.sh --rollback-to fcb982d --reason "<owner's reason, >=10 chars>" --deployed Y
#    expect ALLOW <rollback commit>; stderr JSON shows "mode": "rollback"
ops/deploy.sh --rollback-to fcb982d --reason "<owner's reason>" --deployed Y   # owner go-ahead only
python3 ops/deployed_sha.py                     # = rollback commit (tree == fcb982d)
```

Rollback notes:
- No down-migration is needed. Section 4 shows the change is additive; fcb982d ignores the 75 new
  tables and 38 new columns, and the migrated columns are nullable, so its INSERTs succeed.
- Rows written during the rollback window have NULL in the new columns, and
  `draft_creation_intents` rows are missing. Reconcile them before rolling forward again.
- fcb982d predates the boot guard. Owner sessions created on Y simply go unused, because
  fcb982d has no `/cc/`.
- Railway's "redeploy previous deployment" button bypasses the guard. It is an owner action;
  run step 4's checks after it.
- Budget about 10 minutes, including the Railway rebuild.

**Before freezing FINAL:** (a) refresh `COMPLETION_BOARD.json` and its CC snapshot; (b) decide on
the W4-PIPE tail (section 3); (c) optionally rehearse the migration on a snapshot of the real
Railway Postgres (owner-gated).
