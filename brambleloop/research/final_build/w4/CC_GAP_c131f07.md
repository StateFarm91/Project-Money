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
| F7 | **Phone (second case, found on Postgres-seeded data):** Approvals was 465 px at 390 px. A long token in a flex card title (`` `commerce.shop_package.policies()` ``) pushed the status pill off screen. | `.card-head > :first-child { min-width: 0 }` and `.card-title { overflow-wrap: anywhere }` | The cc_mock card title now carries such a token. check.mjs fails before the fix (122/1, "scrollWidth 465 > 390") and passes 123/0 after. Also test_w4_ccgap_views. |
| F8 | **Missing per-card timestamps (FU-6).** | Every data card now renders `freshness()`: a `<time>` element, or "as of: unknown" when the source has no time. This covers Money Headline/Period/Source health (order source last read, "never read"); Home "Since you last looked"; each Approvals card ("Inbox read"), the batch plan and Not yet askable; each Notification (last seen); the Laura header, presence and each answer; Account signed-in devices; Emergency phase, publishing and departments (`emergency.status` now returns `as_of`); Completion lanes; Ask answers (`answered_at`). | test_w4_ccgap_views (2 tests) |

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

1. **Build 2 closure warm-up (FU-8).** It takes 67–101 s after boot and the launch packet about
   2 min (see §6). Both run off the request path, show honest UNKNOWN until ready, and never delay
   `/health`. Not a deploy risk; left as is.
2. **Snapshot-backed sections.** Fixed where the runtime records the data (F9). The rest are
   labelled as release artefacts (§7).
3. **Timestamps.** Fixed (F8). After F8 the only cards without a timestamp are forms, controls
   and static policy: Ask box, Laura Ask/Private, Store preview link and observation form,
   Account Authentication/Appearance/Sign out/Emergency link, Emergency "Never paused", More,
   drill reference and the Money legend. Account "Phase" sits inside "Live authorities & grants",
   which is timestamped. "As of: unknown" stays, honestly, where the source never ran: Learn
   "Improvement loops" and "Visual R&D", Insights/Store "Search & SEO", Store "Launch verdict".
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
| SLO honesty (F2), agent never-run/overdue/next work (F3), owner-count reconcile (F4), dev-lane labels (F5), Approvals phone wrap (F6, F7), per-card timestamps (F8), live sourcing + release labels (F9) | no | yes |

## 6. Cold start: measured (follow-up task)

Method: `uvicorn` in a fresh process via the same harness (`serve.py` marks; the timer starts
the moment the process is spawned).
- Health: `/health` polled every 0.1 s.
- Owner pages: TEST login, then `GET /cc/`, `/api/cc/home` and `/api/cc/company`.
- Build 2 readiness: `/api/cc/company` polled until `build2_closure` is no longer UNKNOWN, timing
  `/health` on each poll.
- Database: a throwaway local **PostgreSQL 16**.
- Hosting: `RAILWAY_ENVIRONMENT` was set, so the hosted boot guard is enforced and forces shadow,
  and the SQLite refusal applies.
- Worker: embedded worker on, the production default.
- Load: the host was also running another lane's full suite (load average 5–6 on 4 cores), so
  these are pessimistic.

| Scenario | Build | App import (incl. boot-guard tree digest) | Startup hooks done (create_all, seeds, boot enqueues) | **First 200 /health** | /cc/ shell | First CC page (`/api/cc/home`) | `/api/cc/company` | Build 2 closure ready | Max /health latency while it computes |
|---|---|---|---|---|---|---|---|---|---|
| SQLite, fresh, worker off | c131f07 | 1.60 s | 4.19 s | **4.45 s** | 4.46 s | 6.8 s | 10.2 s | 66.9 s | — |
| PG fresh DB, hosted, worker on | c131f07 (run 1) | 1.37 s | 4.84 s | **5.03 s** | 5.04 s | 7.1 s | 13.1 s | 96.4 s | — |
| PG fresh DB, hosted, worker on | c131f07 (run 2) | 1.30 s | 2.97 s | **3.09 s** | 3.10 s | 5.1 s | 12.1 s | 101.2 s | 0.13 s |
| PG fresh DB, hosted, worker on | CCGAP branch | 1.34 s | 4.78 s | **5.00 s** | 5.01 s | 7.4 s | 14.9 s | 97.4 s | 0.23 s |
| PG restart (populated DB) | c131f07 | 1.21 s | 1.79 s | **1.95 s** | 1.96 s | 4.3 s | 9.2 s | 90.4 s | 0.19 s |
| PG restart (populated DB) | CCGAP branch | 1.14 s | 1.83 s | **2.02 s** | 2.02 s | 4.0 s | 7.9 s | 94.3 s | 0.14 s |

`railway.json` has `healthcheckPath: /health` and `healthcheckTimeout: 300`. The worst `/health`
was 5.0 s, about 60× inside the timeout.
- What runs before `/health` can answer: the boot guard's tree digest at import, about 1.3 s.
  Then the synchronous startup hook: `create_all` (migration), the release incident record,
  registry/benchmark seeding and the boot enqueues, 0.5–3.5 s.
- None of these is skipped or deferred.
- Nothing heavy is on the health path. The Build 2 closure (67–101 s) and the launch packet are
  already computed in background threads. `/health` stayed at or under 0.23 s while they ran,
  and every poll returned 200.
- The ">1 min" in CC_VERIFY is that background warm-up, not boot.
- Conclusion: **no root-cause fix is needed**, so none was made.
- Not measured: production-scale Postgres, where the audit log holds thousands of rows a day.
  `create_all` there is schema introspection, not data-proportional, but the real Railway boot
  time was not observed here.

## 7. Live sources vs release artefacts (F9, follow-up task)

The four snapshot-only sections were checked against what the running system records.

| Section | c131f07 | Now on `claude/w4-CCGAP` | Live source | Release artefact kept (labelled) |
|---|---|---|---|---|
| Decision batch plan (Approvals) | The OWNER_ACTIONS.json packet (26 decisions, generated 2026-10-10). **Bug:** the live fallback compared `approval_inbox()["batches"]` (a dict from `owner_queue.batch_cards`) against `list`, so live batches were never used. | **Live first.** On the seeded app this is 11 decisions in 8 batches, "live owner queue", read every request. The 16 decisions only the packet lists are a separate group, "Also in the release packet, not tracked live", labelled and **never added to the live count**. | `approval_inbox()` (gate states + `owner_actions` rows) | OWNER_ACTIONS.json, for release-only decisions (Etsy account screens and off-platform steps the runtime cannot see; they may already be done) |
| Visual pipeline (Company) | VISUAL_STATUS.json stages A–E only | **New live card**, "Visual pipeline (live: listing frames & certificates)". For each product release it shows frames planned, approved and blocked, the certificate state, certified jobs and the last change. With no rows it is UNKNOWN with the reason. | `listing_assets`, `listing_set_certificates` | Stages A–E, retitled "Visual R&D milestones A-E (release artefact)". These are offline simulation milestones and the runtime has no record of them. |
| Completion (Completion tab) | COMPLETION_BOARD.json only | **New live card**, "Company work now (live, from jobs)": running, queued, completed and failed in 24 h, plus the running jobs. | `jobs` | The Claude development-lane board. Development lanes are not runtime state. It is labelled unless an operator supplies the board through `BRAMBLELOOP_COMPLETION_BOARD`. |
| Final Master (Company) | The snapshot, with "read just now" and an `as_of_basis` note | The same numbers. The card now says "Release artefact, not live … mapped at commit 019ebf0, 2f36fe0, 6f9a2f7, 8b67414, fee1cfe; generation time UNKNOWN". | none; the runtime keeps no closure matrix | `build2/final_master_closure.json` |

**Label format** (`company.release_artefact`):

> "Release artefact, not live: <what> as of release <sha12> (recorded <recorded_at>); generated <time>. It changes only when a new release ships."

- The release sha and recorded_at come from the release record that the boot guard matched for
  this exact tree.
- With no matching record, the label names the build commit, or UNKNOWN. That is the case
  locally, where it reads "build UNKNOWN (no release record matched this build)".
- An artefact with no generation time says "generation time UNKNOWN".

**Tests:**
- `tests/test_w4_ccgap_live.py` 6/6. It covers the labels; the live-first batches including the
  real dict shape that c131f07 missed; release-only decisions kept apart; the visual live rows
  and UNKNOWN when there are none; the live work counts from `jobs`; and the PWA wiring.
- Still passing: w4_cc_company 23/23, cc_snapshots, ccgap_views 10/10, pwa_static 81/0,
  h_attributes 6/0, v11_cc_views 13/13, v11_cc_actions 7/7, ccfin 9/9, ccpacket 5/5, and
  cc_mock check.mjs 123/0.
- A drive of the real app (SQLite, one seeded product chain) found no JS errors, and every phone
  page fits at 390 px.
