# W4-CCVERIFY: Command Center end-to-end verification of release candidate 7421ef6

Date: 2026-10-11 (UTC). Lane: W4-CCVERIFY. Branch `claude/w4-CCVERIFY`, based on 7421ef6. This lane
only verifies; it changes no code.

**Verdict: NOT READY. There is 1 RELEASE-BLOCKING defect.** The Store tab crashes on every load
(RB-1). Every other page loads with no JS errors, and the data it shows matches the provider JSON
behind it. There are 10 FOLLOW-UP defects.

## 1. What was run

| Item | Setup |
|---|---|
| App | The real FastAPI app (`brambleloop.app.main:app`) at 7421ef6, served by uvicorn on `http://localhost:8899`. Only loopback sockets are allowed (`harness/env.py`), so there is no outbound network. |
| Database | A throwaway local **PostgreSQL 16** cluster (`initdb` under /var/tmp, port 55432), reached through `BRAMBLELOOP_DATABASE_URL`. SQLite was not used. |
| Phase | `BRAMBLELOOP_PHASE=shadow`, embedded worker off. No Etsy, model or image credentials. |
| Owner credentials | **TEST only.** A random passphrase was hashed locally with `auth.hash_passphrase`, and a random base32 TOTP secret was generated. Both live in a scratchpad file outside the repo and were never printed. No real credentials were used. |
| Seed data | The real offline release chain was run into that Postgres (`harness/seed.py`, which mirrors `pipe_chain_run.py`). It used 3 Launch-0 products: hexagon-coaster-set 1.2.0, nordic-star-ornaments 1.4.0 and cloudline-baby-blanket 1.2.0. Each ran gate.certify → listing.draft → assets.build → pricing.position → listing.seo → launch.plan → store.publish, and store.publish was refused in shadow as designed (3 dead letters). The registry was seeded and an MJS findings reading added (`seed_result.json`). For the Money checks, 25 **test** cost rows were added (`harness/seed_money.py`). 22 LLM calls this month are estimated at CA$0.010 and recorded at CA$0.016 each, so drift should read DEGRADED. 3 calls in 2026-09 total CA$0.75. |
| Browser | Playwright 1.56.1 with Chromium from /opt/pw-browsers (`cc_verify_drive.mjs`). Pages were checked at 1280×900, and 5 core pages again at 390×844 (phone). |
| Evidence | `evidence_CCVERIFY/`: `screens/` (JPEG, 0.75 scale, long pages split into `_pN`); `api_drive/` (every `/api/cc` response the browser received, in order); `api_cold/` (a direct authenticated read of each tab right after boot); `dom/` (what each page rendered); `drive_result.json`; `harness/`. CSRF tokens are redacted. |

Not covered: the deployed Railway service, real Etsy/model integrations and any mutating owner
action other than login, logout, Ask and Laura's Ask. Emergency pause/kill, approvals and grants
were not executed. The local build identity reads `unknown` because `RAILWAY_GIT_COMMIT_SHA` is
unset; this is expected locally.

## 2. Auth and session (passphrase + TOTP)

| Check | Result |
|---|---|
| All 33 GET and 31 POST `/api/cc/*` routes without a session | **401** for every one except `GET /auth/status` (200, by design) |
| `/cc/` CSP | `script-src 'self'`, `default-src 'none'`, `frame-ancestors 'none'`: strict |
| Login form asks for TOTP when the secret is set | yes (`#login-totp`) |
| Passphrase only / wrong TOTP / wrong passphrase | 401 for each. The UI shows "passphrase or code not accepted" and stays on sign-in (`screens/00_login_wrong_totp.jpg`). |
| Throttle | Hit by accident during setup. After 5 failed logins from one client within 15 min, a correct login got 429 "too many failed logins; wait 15 minutes". It worked as specified. |
| Cookies | `__Host-bl_cc` and `__Host-bl_dev`: HttpOnly, Secure, SameSite=Strict |
| Logout | 200; the old cookie then gets 401 on `/api/cc/company` |
| Cross-origin POST (`Origin: https://evil.example`) | 403 |
| POST without CSRF header | 403 |

**Auth: PASS. No auth hole found.**

## 3. Page results

The criteria: **Loads** = no JS error, no error card, no NaN/undefined/[object Object].
**Data** = the rendered numbers and statuses match the provider JSON or the DB. **UNKNOWN** =
missing evidence shows Unknown, never 0 or OK. **Time** = every card shows an as-of.
**Agents vs Claude** = production agents are kept apart from Claude development workers.

| # | Page / view | Loads | Data matches provider JSON / DB | UNKNOWN when no evidence | Timestamp | Result |
|---|---|---|---|---|---|---|
| 1 | Login (passphrase + TOTP) | yes | n/a | n/a | n/a | **PASS** (FU-10 cosmetic) |
| 2 | Home | yes | Decisions for you 16 = `headline.owner_decisions`; Products 3 = DB; Jobs (24 h) 18 = `jobs_completed_24h`; Open incidents 0 = DB | Revenue and Profit read **Unknown**, not CA$0 | Cards yes; "Since you last looked" has none | **PASS** (FU-6) |
| 3 | Laura (Phase 1 text) + Talk to Laura | yes | Ask returned ANSWERED with 11 evidence links and the method "deterministic retrieval … (no model call)". Phase 2 voice and Phase 3 live show as **Gated**. The portrait is labelled internal, not publication-approved. | yes | answer stamped 2026-10-11 00:30:03 UTC | **PASS** (FU-4 count) |
| 4 | Approvals / owner decision batches | yes | "26 decisions in 9 batches". The served snapshot equals `research/final_build/w4/OWNER_ACTIONS.json` byte for byte (`generated_at` 2026-10-10T04:30:36Z). There are 16 cards (3 of them publication cards from this chain run). | max cost UNKNOWN where not costed | yes (20 h ago, shown) | **PASS** (FU-4) |
| 5 | Money (default, month, last_month, ytd, all) | yes | With period=month, Operating spend reads CA$0.35 (22 × 0.016 = 0.352); with last_month it reads CA$0.75. Both match the seeded rows. "Showing: booking period 2026-09" echoes the server. | Revenue, refunds, fees, cash, profit and the safe budget all read **Unknown**. The legend says Unknown is not zero. | Accounting yes; Headline, Source health and Period cards have none | **PASS with defects** (FU-2, FU-6) |
| 5a | Money: estimated vs actual | yes | DEGRADED: "22 calls estimated CA$0.2200 and recorded CA$0.3520 (ratio 1.6) … under-estimated". This matches `estimate_drift` exactly. Settlement against provider billing is labelled **OWNER-GATED**. On the empty DB (`api_cold`) it read UNKNOWN, not "healthy". | yes | yes | **PASS** |
| 5b | Money drill (recorded_spend) | yes | lists the source rows | yes | yes | **PASS** |
| 5c | Money period=7d | error card "period '7d': use month, last_month, 30d, ytd, all or YYYY-MM" (400 BAD_PERIOD, by design per handoff_CC) | n/a | n/a | n/a | **PASS (by design)** |
| 6 | **Store / launch readiness** (store foundation, live drift, readiness, SEO W3, search evidence, publication candidates, competitor intel) | **NO. It crashes on every load:** "Could not load: h(): attribute maxlength is not allowed". | The API is fine (`api_drive/024_store.json`: 11 sections, products 3 = DB), but nothing renders. | n/a | n/a | **FAIL: RB-1** |
| 7 | Company | yes | The status tiles match `company_status.items[0]`: 7 sleeping and 4 Unknown departments, 16 decisions, 0 incidents, Final Master OPEN 9, lanes running 0. The pipeline reads 3 products / 3 certified / 3 drafted / 0 on Etsy, matching the DB. | Departments with no jobs read **UNKNOWN** (4), and agents with no job read **UNKNOWN** (21). | yes on every card ("as of 4 d ago" for the visual snapshot and competitor findings) | **PASS** (FU-3, FU-9) |
| 7a | Build 2 ledger (Company) | yes | PROVEN 215, OWNER-GATED 54, DATA-GATED 41, EXTERNAL 7, N/A 3, OPEN-DEFECT 0, total 320 all equal `build2_closure.headline`. On a cold process it shows **UNKNOWN "computing … refresh shortly"** (`api_cold/api_cc_company.json`), not 0. | yes | yes | **PASS** |
| 7b | Final Master (Company) | yes | 490 launch-critical: 355 complete, 126 gated (83 owner, 17 data, 26 external), 9 OPEN, Launch ready No. This equals `final_master_closure`. | n/a | `read_at` shown, and as_of_basis explains why `as_of` is null | **PASS** |
| 8 | Completion board | yes | 31 lanes: 1 BLOCKED (VALIDATE), 29 MERGED, 1 DONE. This equals `board.counts`. "1 lane(s) have not reported rows closed; they are not counted as 0." | yes | board as_of 2026-10-10T04:00Z shown as "20 h ago" | **PASS** |
| 8a | Launch packet (Completion tab) | yes | First read: UNKNOWN "being generated … reload in a minute". Later: UNKNOWN verdict "7 of 7 product(s) not publishable now; 7 … sections never read; 8 open owner action(s)". Not passing; honest. | yes | yes | **PASS** (FU-8) |
| 9 | Operations (incidents, health, providers) | yes | Incidents 0 = DB; queue "3 dead-lettered jobs" = the 3 shadow store.publish refusals; Truth is DEGRADED (security_controls, rollback_baseline, as expected locally) | SLO card was **OK** right after boot with 5 of 7 objectives UNKNOWN and no scheduler ever run, then turned DEGRADED | yes | **PASS with defect** (FU-5, FU-3) |
| 10 | Autonomy & Learn: **Rule #1** | yes | 6 defects, 11 of 11 departments evaluated; per-department DEFECT/OK equals `rule1.items`. (The PRODUCTION_CATCHUP "Rule #1 MISSING" finding is now **closed** in 7421ef6.) | "Hours since you last acted" reads **Unknown** | yes | **PASS** |
| 10a | Autonomy & Learn: **agents card** | yes | 29 agents (28 sleeping, 1 unhealthy) equals the `agents` provider (`autonomy.status.agents`; the PROVIDER-ONLY finding is closed) | agents that have never run read "SLEEPING" here but UNKNOWN on Company | yes | **PASS with defect** (FU-3) |
| 10b | Learn: improvement loops and outcomes | yes | 5 of 5 loops UNMEASURED; pre-sale outcomes 7/9 | yes | "as of: unknown" on Improvement loops and Visual R&D | **PASS** (FU-6) |
| 11 | Visual | yes (Company, Learn) | Visual pipeline stages come from the snapshot (A PASS, B PARTIAL …, as of 2026-10-07T12:00Z, shown "4 d ago"). Visual R&D reads UNKNOWN "no image has been judged". | yes | yes / "unknown" for R&D | **PASS** |
| 12 | SEO | Insights yes; the Store-tab SEO sections are blocked by RB-1 | Insights "Search & keywords" reads UNKNOWN "no SEO proposal exists yet" (true for this DB: no seo cycle ran) | yes | "as of: unknown" | **PASS** (Store part: RB-1) |
| 13 | MJs / competitor intel | yes (Company "Competitor findings") | 10 findings from MJS_FINDINGS (e.g. 441 observed listings), as of 2026-10-07 | n/a | yes | **PASS** (Store copy: RB-1) |
| 14 | Insights (ads) | yes | **Ads card always reads UNKNOWN "ads readiness unreadable: AttributeError('Session' object has no attribute 'engine')"**. The provider works when called directly. | shows UNKNOWN (fails safe) | yes | **PASS with defect** (FU-1) |
| 15 | Notifications | yes | 18 unacked, matching the nav badge; "37 refused owner-auth attempts in the last hour" is real (this lane's unauthenticated route probes) | n/a | yes | **PASS** |
| 16 | Timeline | yes | events from audit_log, with sources | n/a | yes | **PASS** |
| 17 | Ask Company | yes | "What is blocking launch?" → ANSWERED: shadow + 16 owner decisions | n/a | yes | **PASS** |
| 18 | Account (sessions, authority policy/DAG) | yes | authority_policy OK; authority_dag UNKNOWN "no work items recorded yet" | yes | yes | **PASS** |
| 19 | Emergency, More, Source drill | yes | phase shadow; publishing and spend refused | n/a | yes | **PASS** |
| 20 | Phone width (home, company, money, learn, completion) | yes | n/a | n/a | n/a | **PASS**: scrollWidth = clientWidth = 390 on all 5 |

**Production agents vs Claude development workers: PARTIAL.**
- The Completion board marks every lane "Worker: Claude worker (W4-…)", 31 of 31.
- Company/Learn/Operations "Agents" are the 29 registry agents (coo, laura, listing …).
- Nothing on screen says in words that these are two different kinds of worker. The Company
  status hero shows "Lanes running" among the department tiles without saying they are Claude
  development lanes (FU-9).

## 4. Defects

### RELEASE-BLOCKING

**RB-1: the Store tab crashes on every load (core page).**
- **Evidence:** `screens/05_store.jpg`; `drive_result.json` page `05_store`, error_text "h():
  attribute maxlength is not allowed".
- **Cause:** `src/brambleloop/app/command_center/static/js/views/store.js:37-38` (from c4003ee,
  W4-CC) builds the live-shop observation form with
  `h("textarea", { …, maxlength: 6000 })` and `h("input", { …, maxlength: 500, … })`. `dom.js`
  allows only the camel-case property `maxLength` (`ALLOWED_PROPS`). For any other key it
  throws, and the view's render rejects.
- **When it fires:** the observation card renders whenever `sections.live_drift.items` is
  non-empty. The 14 storefront fields are always listed, so this is every real backend,
  including the production one. The API itself is fine (`api_drive/024_store.json`).
- **What the owner loses:** the Store tab is one of the 5 phone bottom-bar tabs. It carries store
  foundation, live drift, the live-shop observation form, store readiness, SEO W3, search
  evidence, publication candidates, competitor intel and the store preview link. All of it
  becomes unreachable.
- **Why tests missed it:** the mock fixture `tests/fixtures/cc_mock/data.mjs` has no
  `live_drift`, so the Playwright mock check never renders this card.
- **Fix (not applied in this lane):** change `maxlength` to `maxLength` on those two lines, then
  add `live_drift` items to the mock.

### FOLLOW-UP

| ID | Defect | Evidence | Why not blocking |
|---|---|---|---|
| FU-1 | The Insights "Ads readiness & economics" card is always UNKNOWN with an internal error. `providers._invoke` first calls a provider with a `Session` and retries with the `Database` only when the error text mentions `'session'`. `growth.ads_readiness.summary` catches its own exception and reports `'Session' object has no attribute 'engine'`, so the retry never happens. | `dom/10_insights.json`; `api_drive/031_insights.json`. Called directly with a `Database`, `ensure_tables/state/readiness/proposals/kpis` all succeed. | It fails safe (UNKNOWN, never wrong numbers), and ads are owner-gated. Still, this card can never show data. |
| FU-2 | Money "Headline: Recorded spend (all kinds)" shows CA$1.10 (all time) whichever period is selected. With "Last month" selected the page says "Showing: booking period 2026-09" and the headline still reads CA$1.10, while the period's operating spend is CA$0.75. The API scopes the filter (`period_applies_to: ["accounting"]`), but the UI does not label the headline as all-time. | `dom/04_money_last_month.json`; `api_drive/019_money_period_last_month.json` | The correct per-period figure is on the same page and the headline total is true. It is mislabelled scope, not a false number. **Arguably should block if the owner reads the headline as the period total.** |
| FU-3 | Agent status disagrees across tabs. For the same 29 agents, Company shows 7 sleeping, 1 unhealthy and **21 UNKNOWN** ("no recorded job"), while Autonomy & Learn shows **28 SLEEPING** and 1 unhealthy. Learn shows never-run agents as "sleeping" even when their next wake is already past and no scheduler has ever run (e.g. orchestrator, "next wake 19 min ago"). Operations has a third card titled "Agents" with status OK; it only lists registry config. | `api_drive/044_company.json` vs `046_autonomy.json`; `dom/08_operations.json` | The Company tab is honest. Learn's overall card status is DEGRADED. |
| FU-4 | Owner-decision counts differ by surface: 16 (Home, Company tile, Ask), 13 (Company "Your actions" reason), 10 (Laura "Needs you"), and 26 decisions in 9 batches (Approvals). | api_drive home/company/laura/approvals | Each count is internally sourced, but the owner sees 4 different numbers for "what needs me". |
| FU-5 | Right after boot, the SLO card read **OK** "every judged objective is met" with 5 of 7 objectives UNKNOWN, `scheduler_liveness` "no evidence either way" and no scheduler ever run. Later reads turned DEGRADED ("scheduler is stale"). | `api_cold/api_cc_operations.json` (OK) vs `dom/08_operations.json` (DEGRADED) | It self-corrects within minutes, and every UNKNOWN objective is listed. Still, a headline of OK on thin evidence. |
| FU-6 | Some cards have no timestamp or show "as of: unknown". No timestamp: Money "Headline", "Source health", "Period"; Home "Since you last looked". "as of: unknown": Learn "Improvement loops", "Visual R&D", Insights "Search & keywords", "Hours since you last acted". | `drive_result.json` `cards_without_time`; dom files | Page meta shows generation time; the values themselves are UNKNOWN or derived. |
| FU-7 | DEGRADED/BLOCKED cards whose provider gave no reason show "provider gave no reason": store_foundation, autonomy, agents (Learn), search_evidence, Operations departments, Laura departments. | dom/api files | Honest, but not actionable for the owner. |
| FU-8 | Cold-start latency. The first `GET /api/cc/company` took **64.5 s** on a fresh process (Build 2 closure computing); later reads take 5–18 s. The launch packet reads "being generated … reload in a minute" on its first read. | `api_cold` timings (fetch log); `api_drive/028_launch_packet.json` | It shows UNKNOWN "computing", not wrong data. 64 s is near typical proxy timeouts. |
| FU-9 | Production agents vs Claude development workers are not labelled as such. The Company hero "Lanes running" tile and the Completion "Parallel lanes" subtitle never say the lanes are Claude development workers, not company agents. Each lane row does say "Claude worker (W4-…)". | `dom/06_company_warm.json`, `dom/07_completion_warm.json` | Each lane row is labelled, so a reader can tell them apart. |
| FU-10 | The login card is squeezed to about 190 px wide on a 1280 px desktop viewport. | `screens/00_login.jpg` | Cosmetic. |

## 5. Notes for the integrator

- The PRODUCTION_CATCHUP §5 findings for "Rule #1 MISSING" and "`agents` PROVIDER-ONLY" are
  closed at 7421ef6: `rule1` and `agents` are read by `/api/cc/autonomy` and rendered on
  Autonomy & Learn. `authority_dag` and `authority_policy` now render on Account.
- The completion board is still the 2026-10-10T04:00Z content. That is shown honestly
  ("20 h ago", no lane RUNNING, so nothing reads STALE).
- The environment needed `uvicorn`, `psycopg2-binary`, `numpy` and the rest of
  `requirements.txt` installed before `assets.build` could run. Without numpy, assets.build
  dead-letters (`ModuleNotFoundError`). This is an environment gap, not a product defect; the
  Dockerfile installs requirements.
- To reproduce:
  1. Start a throwaway Postgres on 55432.
  2. Write a TEST credentials file in the format `harness/env.py` reads.
  3. Run `python3 harness/seed.py <slugs>`, then `python3 harness/seed_money.py`, then
     `python3 harness/serve.py`.
  4. Run `CC_BASE=http://localhost:8899 CC_SECRET_FILE=… OUT=… node cc_verify_drive.mjs`.
