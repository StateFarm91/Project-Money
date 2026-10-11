# W4-CCGAP: Command Center feature gap audit of release candidate c131f07

Date: 2026-10-11 (UTC). Lane CCGAP. Branch `claude/w4-CCGAP`, based on c131f07. No Railway, Etsy,
spend or customer action was taken. Fixes are for the **next** release; c131f07 itself is
unchanged.

## 1. How it was exercised

| Item | Setup |
|---|---|
| App | The real FastAPI app (`brambleloop.app.main:app`) at c131f07, served by uvicorn on `127.0.0.1:8911`. Loopback-only network. |
| DB | Temporary **SQLite** (`BRAMBLELOOP_DATABASE_URL=sqlite:///…`), shadow phase, embedded worker off. The DB was seeded the way the CC tests and CC_VERIFY seed it: `Registry.seed_defaults()`, an MJS findings reading, one real offline Launch-0 chain (`hexagon-coaster-set` 1.2.0: gate.certify → listing.draft → assets.build → pricing.position → listing.seo → launch.plan; store.publish was refused in shadow → 1 dead letter), plus 25 **test** cost rows (22 this month, estimated CA$0.010 and recorded CA$0.016 each; 3 in 2026-09). |
| Owner credentials | **TEST only.** They were generated locally into a scratch file and never printed or committed. |
| Browser | Playwright (`/opt/node22/lib/node_modules/playwright`) with `executablePath=/opt/pw-browsers/chromium`. Every page was checked at 1280 px, then 11 pages at **390×844**. |
| Evidence | `evidence_CCGAP/`: `drive_c131f07_before.json` (c131f07), `drive_ccgap_after.json` (this branch), the drive script and the harness (env/seed). |

Every page loads with no JS error at c131f07; the RB-1 Store crash is fixed there. The only
failing visit is `money?period=7d`, which returns a 400 BAD_PERIOD by design.

## 2. Feature matrix (c131f07)

Key. **Real** = read live from the production DB or providers. **Snapshot** = a committed
JSON shipped in the image (`app/command_center/snapshots/`), shown with its own date.
**Freshness** = each card shows "as of"; the page header shows the generation time.

| # | Owner requirement | Route / tab | Data source | Real / stub | Freshness shown | Unknown handling | Phone 390 px | Covering test |
|---|---|---|---|---|---|---|---|---|
| 1 | Every agent/department with activity status | Company (Departments, Agents); Autonomy & Learn (Agents, Rule #1); Operations (Departments) | `autonomy.status.summary` / `.agents`, `jobs`, `worker.CADENCES` | Real | yes | Company: never-run agents show **UNKNOWN**. **c131f07 gap:** Learn showed the same agents as SLEEPING; fixed on this branch. | ok | test_w4_cc_company (departments UNKNOWN, agent active); test_w4_ccfin; **test_w4_ccgap_views** |
| 2 | Current tasks, progress, last useful output, blockers, next actions | Company departments/agents rows; Learn agents; Blockers card | `jobs` (RUNNING/DONE, last 400 finished), provider `next_work`, gate blockers | Real | yes | "None recorded" / Unknown, never 0. **c131f07 gap:** the provider's `next_work` (queued next actions) was never rendered; fixed. | ok | test_w4_cc_company; **test_w4_ccgap_views** |
| 3 | Build 2 closure | Company → Build 2 closure | `build2.closure` (computed off-request, 30 min TTL) | Real (computed) | yes | UNKNOWN "computing (started …)" on a cold process, never 0 | ok | test_w4_cc_company (build2 ×4) |
| 4 | Final Master closure | Company → Final Master | `build2.final_master.summary` (snapshot bound to the tree digest) | Snapshot (honest) | `read_at` + as_of_basis | n/a | ok | test_final_master_section_reads_packaged_snapshot |
| 5 | Completion-team progress | Completion (+ Company tile) | `snapshots/COMPLETION_BOARD.json` | **Snapshot.** It is only as fresh as the last release, read "as of 1 d ago". | yes | Lanes that did not report rows closed are "not counted as 0". **c131f07 gap:** lanes were not labelled as Claude development workers (FU-9); fixed. | ok | test_w4_cc_company (board ×4); test_w4_cc_snapshots |
| 6 | Products and listings | Store → Products, releases & listings; Company → Product pipeline | `products`/`pattern_versions`/`listings` | Real | yes | n/a | ok | test_v11_cc_views; test_w4_cc_company |
| 7 | Etsy launch readiness | Store (readiness, launch verdict, visibility, publication candidates); Completion → Launch-0 packet | `launch.readiness`, `launch.packet.build` (background, 5 min TTL) | Real | yes ("as of: unknown" when never run) | UNKNOWN "launch.readiness has never run" / "being generated" | ok | test_w4_ccpacket; test_w4_cc_company |
| 8 | Creative / visual pipeline | Company (Visual pipeline stages, Visual R&D); Learn (Visual R&D ×2) | `snapshots/VISUAL_STATUS.json` (stages); `visual.rnd.status` (live) | Stages: snapshot, dated (4 d ago). R&D: real. | yes / "as of: unknown" for R&D | UNKNOWN "no image has been judged" | ok | test_visual_stages_show_partial_measured_or_unknown |
| 9 | Mrs J (MJs) competitor intelligence | Store + Company → Competitor findings | `intel.findings.latest` (operating_readings `mjs.findings`) | Real (DB reading) | yes ("4 d ago") | UNKNOWN until a reading is stored | ok | test_mjs_findings_route_is_operator_only_and_unknown_until_a_reading |
| 10 | Learn and measurable improvements | Learn (Improvement loops, Improvements, Experiments, Lessons); Company (Learning pre-sale/post-launch) | `learn.improvement_status`, `improvements`, `experiments`, `lessons` | Real | yes. "as of: unknown" on Improvement loops. | 5/5 loops UNMEASURED, never 0% | ok | test_learn_outcomes_presale_post_launch_and_ca5k_unmeasured |
| 11 | Revenue / expenses / profit / spend by period | Money (`?period=month,last_month,30d,ytd,all,YYYY-MM`), drill | `finance.accounting.dashboard`, `ledger`, `cost_entries` | Real | Accounting yes. The Headline, Source health and Period cards have none. | Revenue/profit **UNKNOWN** (order source not connected); the headline says "(all time)". | ok | test_money_period_reaches_accounting_window; test_w4_ccfin; test_v11_accounting_* |
| 12 | Estimated vs actual model/provider cost | Money → "Model spend: estimated vs actual" | `estimate_drift_reading` (cost_entries est vs recorded) | Real | yes | DEGRADED when drift is out of tolerance; UNKNOWN on an empty DB; provider-billing settlement is labelled OWNER-GATED | ok | test_estimate_drift_on_verify_and_money_labelled_settlement_owner_gated |
| 13 | Incidents and system health | Operations (Incidents, SLOs, Queue, Truth); Home tiles | `incidents`, `ops.slo.summary`, `ops.truth`, `jobs` | Real | yes | **c131f07 gap:** the SLO card read **OK** with 5 of 7 objectives UNKNOWN (incl. P1 scheduler freshness); fixed. | ok | test_v11_reliability_slo; **test_w4_ccgap_views** |
| 14 | Owner decisions and approvals | Approvals (batches + live cards); Home/Company "Your actions"; Notifications | `build2.executor.approval_inbox` (live) + `snapshots/OWNER_ACTIONS.json` (batch plan) | Live cards are real; the batch plan is a dated snapshot. | Batch plan yes; per-card none (page header only) | max cost UNKNOWN when not costed. **c131f07 gap:** 13 vs 14 vs 26 with no explanation; Home/Company now reconcile it. | **c131f07 gap: 413 px overflow**; fixed | test_owner_decision_batches_in_approvals; test_v11_cc_actions; **test_w4_ccgap_views**; cc_mock check.mjs |
| 15 | Autonomy / scheduling / worker activity | Learn (Rule #1, Autonomous company, Jobs 24 h, Last useful action); Operations (SLO scheduler/worker liveness, Departments) | `autonomy.rule1`, `jobs`, `ops.slo` liveness | Real | yes | Overdue wakes were shown as plain sleep; this branch flags them. | ok | test_w4_ccfin (rule1); test_v11_reliability_slo; **test_w4_ccgap_views** |
| 16 | Data freshness | Every card (`freshness()`), page header, Truth (`observation_window`), stale flags | per-envelope `as_of` | Real | — | as_of null shows "as of: unknown", never "now" | ok | test_v11_pwa_static; cc_mock check.mjs |
| 17 | Phone usability | All tabs, bottom bar | — | — | — | — | 10 of 11 pages fit at 390 px; Approvals was 413 px (fixed) | cc_mock check.mjs (390 px per tab) |
| — | Process stability while serving the CC | all | `visual.contents_frame` (PDFium) | — | — | **c131f07 gap: the web process crashed** (see F1) | — | **test_w4_ccgap_pdfium** |

## 3. What I fixed (branch `claude/w4-CCGAP`, NOT in c131f07)

| ID | Gap (live symptom at c131f07) | Fix | Regression test (fails before the fix) |
|---|---|---|---|
| **F1** (most severe) | **The web process died while serving the CC.** It crashed twice during the drive: `bad_variant_access was thrown in -fno-exceptions mode` (SIGABRT), and a SIGSEGV in `libpdfium.so` (dmesg). PDFium is not thread-safe. `visual.contents_frame` rasterises the certified PDF, and three paths reach it concurrently: the CC launch-packet background thread, request threads (readiness/publication verification) and worker threads. In production this takes down the whole web service, not only one page. | `contents_frame.PDFIUM_LOCK` (an RLock) wraps every PDFium call. Documents, pages and bitmaps are closed inside the lock. Pixels are unchanged; `test_w4_visual2` passes 8/8. | `tests/test_w4_ccgap_pdfium.py`: 8 threads in a child process. Before the fix it exits −6 (abort); after, it exits 0 with one PNG sha. A static scan also checks that every pypdfium2 user opens documents under the lock. |
| F2 | The Operations SLO card read **OK** "every judged objective is met" while 5 of 7 objectives, including P1 `scheduler_freshness`, had no evidence (FU-5). | `tabs.slo_card`: OK only when every objective is judged; otherwise DEGRADED with "only N of M objectives have evidence … UNKNOWN: … (P1 with no evidence: …)". The provider's status is kept as `provider_status`. The provider itself is unchanged: Laura's executive loop reads it. | test_w4_ccgap_views |
| F3 | Learn's agents card showed 28 agents SLEEPING, including agents that never ran, while Company said UNKNOWN for the same agents. An agent whose wake was long past also read as sleeping. The provider's `next_work` (queued next actions) was never shown (FU-3). | `tabs.agents_card`: never-run → UNKNOWN with the reason; a wake more than 15 min past is flagged "nothing has run since"; counts and status are recomputed. `learn.js` shows the reason and "Next work". The Operations registry card is retitled "Agent registry (configuration, not activity)". | test_w4_ccgap_views |
| F4 | "Your actions" said 13 while "Decisions for you" and Approvals said 14, and the batch plan said 26 (FU-4). | `tabs.reconcile_owner_actions` (Home and Company): "13 gate/owner-action decision(s) + 1 publication approval(s) = 14 open on Approvals", plus a note that the batch plan is a dated snapshot. | test_w4_ccgap_views |
| F5 | Claude development lanes were not distinguished from company agents (FU-9). | Company tile: "Claude dev lanes running (board)". Completion: "Claude development lanes … (not company agents)". | test_w4_ccgap_views |
| F6 | **Phone:** Approvals was 413 px wide at 390 px because a repo path in a proposal did not wrap. | `.card { overflow-wrap: break-word; }` | The cc_mock proposal now carries a long path. check.mjs fails before the fix ("scrollWidth 773 > 390") and passes 123/0 after. Also test_w4_ccgap_views. |

After the fixes, the re-drive (`drive_ccgap_after.json`) found no JS errors on any page. Every
phone page measured scrollWidth = 390. The server stayed up through the drive and the extra
probes.

Tests run, one process at a time with a private TMPDIR:
- New: test_w4_ccgap_pdfium 2/2 and test_w4_ccgap_views 8/8.
- Existing, all still passing: test_w4_visual2 8/8, test_w4_cc_company 23/23, test_v11_cc_views
  13/13, test_w4_ccfin 9/9, test_v11_wiring_cc (0 failing), test_v11_pwa_static 81/0,
  test_cc_h_attributes 6/0, and cc_mock check.mjs 123/0.
- The full suite was not run because of the lane constraint.

## 4. What remains (not fixed here)

1. **Cold start (FU-8).** The Build 2 closure reads UNKNOWN "computing" for over a minute after
   boot. In the warm drive it was still computing about 90 s in. The launch packet took about
   2 min to generate its first copy. Both are honest UNKNOWN, but slow.
2. **Snapshot-backed sections are only as fresh as the last release.** These are
   COMPLETION_BOARD, OWNER_ACTIONS (the batch plan), VISUAL_STATUS stages and Final Master. Each
   shows its own date ("1 d ago", "4 d ago"), but none of them updates live. Making them live
   needs a DB-backed writer, which is out of scope here.
3. **Missing per-card timestamps (FU-6).** These have none: Money "Headline", "Source health" and
   "Period"; Home "Since you last looked"; each Approvals card and each Notifications alert; the
   Laura cards; Account "Phase"/"Authentication"; Emergency. These show "as of: unknown": Learn
   "Improvement loops" and "Visual R&D"; Insights/Store "Search & SEO"; Store "Launch verdict".
4. **"provider gave no reason" (FU-7)** still appears on DEGRADED cards for store_foundation,
   autonomy, search_evidence and Operations departments. It is honest but not actionable.
5. **Laura's "Needs you" count** is still a separate number (10 in CC_VERIFY). F4 reconciles
   only Home and Company.
6. **No production-data check.** All of the above ran on SQLite with one product. The deployed
   service was not exercised, and nothing here was verified on Railway.
7. **Other pypdfium2 users.** There are none today. The new static test fails if one is added
   without `PDFIUM_LOCK`.

## 5. Verified where

| Feature / fix | In c131f07 | Only on `claude/w4-CCGAP` |
|---|---|---|
| Matrix rows 1–17 render with real or dated-snapshot data, honest UNKNOWN and per-card freshness (with the FU-6 exceptions above) | **yes** (driven at 1280 and 390 px) | |
| PDFium serialization (F1) | no: the process crashes under concurrency | yes |
| SLO honesty (F2), agent never-run/overdue/next work (F3), owner-count reconcile (F4), dev-lane labels (F5), Approvals phone wrap (F6) | no | yes |
