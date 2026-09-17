# BUILD_STATE

_Updated 2026-09-17 by the Brambleloop build session. Maintained continuously so any future
session resumes without rediscovery (Execution Directive step 1, Master Plan section 35)._

## Current phase
PHASE 1 — SHADOW MODE, **deployed and running 24/7**. Nothing is connected to live customers,
live listings or live spend. The system runs unattended on Railway whether or not any Claude
session is open.

Live: https://brambleloop-os-production.up.railway.app — dashboard `/`, health `/health`,
status `/api/status`, **verification `/api/verify`**.

## Canonical specification
`brambleloop/spec/01_Brambleloop_Master_Plan_v1.2.pdf` (vendored copy of the owner's handoff).
Treat v1.2 as canonical. Improvements become v1.3+ with a preserved changelog — do not
scatter canonical strategy across chat.

## Honest status — what actually exists
Verified by `./run_tests.sh` — **188 tests passing, 0 failing**:

- CIR engine (27), platform layer (14), release gates (27), market radar (31), model gateway
  (21), shadow pipeline (8), real-process persistence (5), chaos/resilience (21), deployment
  surface (8), flagship product run and adversarial attacks (26).
- The full release chain runs end to end with no human in the loop, and correctly *refuses*
  to publish in shadow mode. A single `plan.cycle` now carries an entire 11-SKU portfolio
  from market scan to eleven release certificates without intervention.
- Persistence is **proven, not assumed**: a worker is SIGKILLed mid-job against a file-backed
  database and a fresh process recovers and completes the work, inputs intact, with no
  duplicate side effects.
- Cloud deployment: **live and verified.** See "Deployment" below for the exact
  configuration, the twelve production checks that pass, and the measured cost.
- Model providers: **none configured.** The Model Gateway is built and tested, but no API
  key exists in this environment, so `available_providers()` returns an empty list and the
  dashboard says "none". Nothing in the pipeline currently calls a model: every load-bearing
  step is deterministic code.
- Object storage: **none.** Rendered PDFs and charts are written to local disk, which is
  ephemeral in a container. The system knows this: artifact *hashes* are stored in Postgres
  and survive, the bytes may not, and `assets.storage_not_durable` is audited on every run.
- Etsy shop, listings, customers, revenue, ad spend: **none, CA$0, zero.**
- Market Radar now runs on **real observed competitor intelligence** (five seeded shops,
  dated 2026-09-17, with price bands, discount patterns, format signals and named gaps) and a
  **34-concept opportunity pool across 23 categories**. No live scraping integration exists;
  observations are point-in-time and carry their observation date so they cannot silently rot.

## Last completed milestone
The complete shadow release chain on a real product. One unattended `plan.cycle` now runs
market scan → portfolio selection → engineered CIR → compile → digital twin → reverse compile
→ certificate → PDF and charts → pricing → listing and SEO → launch plan → refused publish,
for all eleven release candidates, with 101 jobs completed and no unexpected failures. The
flagship's actual output — the 8-page PDF, the chart, the price net of Etsy fees, the listing
copy, the launch dates and a support transcript — is written to
`reports/shadow_release_nordic_forest.md` so it can be inspected rather than taken on trust.
The chain was then deliberately attacked: 16 attack tests covering a single wrong stitch in a
motif, a stale chart from another size, drifted customer text, unsupported size claims,
invented motifs, a fake was-price, a bundle that is not cheaper, an unsupportable listing
claim, an agent reaching outside its permissions, support trying to amend a pattern, and a
corrupted or missing artifact. All are rejected by construction.

## Architecture decisions
See `DECISION_LOG.md` for reasoning. Summary:
- Python 3.11. Core value is deterministic arithmetic, PDF/chart generation and image work.
- Postgres in production; SQLite for hermetic tests. Durable queue via `SELECT ... FOR UPDATE
  SKIP LOCKED` (Postgres) with a portable fallback — no Redis, fewer moving parts to die
  unattended.
- FastAPI + server-rendered Jinja admin. No separate frontend build step.
- Railway as the deploy target (owner account `statefarm91` verified present, personal
  workspace, 3 existing projects). **Not provisioned** — paid infrastructure is an owner gate.
- Lives at `brambleloop/` inside the Project-Money repo for now, purely because push
  credentials are scoped to that repo. Migrating to a dedicated repo is a tracked follow-up,
  not a blocker.

## Completed capabilities
- `core/db.py`, `core/models.py` — warehouse: jobs, agents, audit log, cost entries, ledger,
  spend limits, products, pattern versions, incidents, owner-action queue.
- `queue/durable.py` — leased jobs, idempotency keys, backoff with jitter, dead-letter.
- `agents/registry.py` — per-agent job-type permissions, daily cost ceilings, structurally
  forbidden combinations, audit trail, and a SpendGuard that pauses a scope on breach.
- `core/backup.py` — backup plus a restore drill that reloads and compares row counts.
- `gates/asset_truth.py` — imagery/claims checked against the digital twin.
- `gates/policy.py` — unsupported claims, IP tripwires, deceptive pricing, Etsy limits.
- `gates/certificate.py` — the full release chain and an immutable release hash.
- `gates/incidents.py` — defect correlation, P1 escalation, publication halt.
- `runtime/worker.py` — worker loop (authorize → dispatch → complete/fail) and scheduler.
- `runtime/pipeline.py` — the shadow release pipeline and its job handlers. `radar.scan` now
  scores the real pool and emits the selected portfolio; `radar.score` re-scores each
  candidate at the moment it would consume engineering effort, because a job can sit in the
  queue while a seasonal window closes underneath it.
- `radar/market.py` — dated competitor profiles, category observations, and the SHOPPING DATE
  vs MAKING DATE window arithmetic (section 5).
- `radar/opportunity.py` — the 34-concept pool, the six-component score, and the section 33
  portfolio constraints.
- `radar/report.py` — renders the whole decision as reviewable markdown.
- `gateway/prompts.py` — immutable, content-hashed, version-pinned prompts.
- `gateway/model_gateway.py` — provider-agnostic routing, per-provider circuit breakers,
  strict JSON parsing, per-agent cost recording, and `require_deterministic()` which refuses
  to let a model verdict stand where the compiler has one.
- `gateway/evals.py` — property-based eval fixtures that block a prompt version change if the
  model starts inventing or dropping factual claims.
- `products/nordic_forest.py` — the first engineered design: a motif grid, three generated
  sizes.
- `publish/charts.py`, `publish/pdf.py` — charts and the customer PDF, rendered from the twin.
- `commerce/pricing.py`, `commerce/seo.py`, `commerce/launch.py` — fee-aware pricing that
  refuses deceptive discounts, listing copy assembled only from computed facts, and a launch
  plan anchored on the buying window.
- `support/concierge.py` — answers from the exact released version and cannot amend it.
- `core/artifacts.py` — content-addressed artifacts; hashes durable, bytes not.
- `core/resilience.py` — transient/permanent classification, Retry-After honouring, circuit
  breaker, artifact hash integrity, strict model-output parsing.
- `app/main.py`, `app/worker_entry.py`, `app/scheduler_entry.py`, `Dockerfile`,
  `railway.json` — the deployable surface. Written and exercised locally; not provisioned.
- `cir/stitches.py` — canonical stitch taxonomy (consumes/produces/height per stitch). US
  canonical, UK rendered downstream.
- `cir/model.py` — CIR dataclasses, JSON round-trip, components/rows/repeats/gauge/materials.
- `cir/compiler.py` — deterministic compiler. Validates per row: stitch availability, over/
  under-run, repeat divisibility, declared-vs-computed count, unknown colour, row ordering,
  empty rows. Warns on missing turning chains for tall stitches.
- `cir/writer.py` — CIR → customer-facing pattern text, US/UK terminology, magic-ring aware.
- `cir/reverse.py` — independent parser of customer-facing text + structural diff against
  canonical CIR. Shares no parsing code with the writer by design.
- `cir/twin.py` — digital twin: cell-level fabric model, chart/colour grids, finished
  dimensions from gauge, per-colour yardage estimate with an explicit ±20% tolerance until a
  physical test calibrates it.

## Acceptance gates passed
- **Gate A (Infrastructure): passing.** Worker death does not strand jobs (lease reclaim);
  duplicate publish/spend refused by DB-enforced idempotency keys; backoff then dead-letter;
  backup + restore drill comparing row counts; audit log identifies actor/action/artifact.
- **Gate B (Pattern Safety): passing except regression automation.** Known-good compiles;
  broken stitch count, bad repeat, overrun, underrun, unknown colour rejected; text mutations
  (repeat count, stitch substitution, run length, declared count, turning chain, dropped row,
  unparseable text) caught by reverse compilation. Outstanding: "a corrected bug creates a
  regression test" — the incident → regression-fixture automation is not built.
- **Gate C (Asset Truth): passing.** Absent motif/colour/component rejected; unsupported
  size, size-label, material and difficulty claims blocked; provenance mandatory; a render
  cannot masquerade as a photograph; an undisclosed AI concept cannot be the hero.
- **Gate D (Commercial Safety): passing.** Agent permissions and structural prohibitions;
  per-agent daily cost ceilings; ad budget breach prevented *and* the scope auto-paused.
  Outstanding: contribution accounting reconciles against real transactions (no real ones yet).
- **Gate E (Customer Experience): passing.** Repeated defects correlate into one incident;
  P1 halts the publication chain; support has no path to the canonical pattern.
  Outstanding: answering from the correct pattern version needs the support agent.
- **Gate F (Shadow Graduation): passing.** Full simulated product completes the chain without
  intervention. Model-provider failover is untested (no Model Gateway yet).

## Deployment (verified 2026-09-17)

| | |
|---|---|
| Railway project | `brambleloop` (`0d61d9ec-76ca-42e3-aa69-918728845b29`), workspace "Jacob McKenna's Projects" |
| Environment | `production` (`d618b2fe-70ec-4541-852f-0b656c2eedaf`) |
| App service | `brambleloop-os` (`c14774b3-0df2-409e-9721-fd7045099c53`) |
| Source | `StateFarm91/Project-Money`, branch `claude/repository-setup-nc9x6o`, root `brambleloop` |
| Build | Dockerfile (`brambleloop/Dockerfile`), region us-west2, 1 replica |
| Domain | `brambleloop-os-production.up.railway.app` |
| Health check | `/health`, 300 s timeout |
| Database | `Postgres` service (`c40c71a5-…`), Postgres 18, 5 GB volume |
| Variables | `BRAMBLELOOP_REQUIRE_POSTGRES=1`, `BRAMBLELOOP_PHASE=shadow`, `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `BRAMBLELOOP_EMBEDDED_WORKER=1`, `BRAMBLELOOP_SCHEDULER_INTERVAL=60`, `BRAMBLELOOP_RUNNER_START_DELAY=25`, `BRAMBLELOOP_ARTIFACT_DIR=/app/artifacts`, `PORT=8000` |

### Measured cost, not guessed

From 61 samples of Railway's own metrics over the first hour of operation:

| | vCPU (avg) | RAM (avg) | Disk |
|---|---|---|---|
| `brambleloop-os` | 0.0053 | 0.074 GB | 0 |
| `Postgres` | 0.0011 | 0.082 GB | 0.157 GB |

At Railway's rates (~US$20/vCPU-month, ~US$10/GB-month RAM, US$0.15/GB-month volume) that is
**about US$1.70 / CA$2.40 per month of usage**, inside the Hobby plan's included US$5 credit.
Recurring infrastructure is therefore the **US$5 / ~CA$7 per month plan fee**, against the
owner's CA$20 ceiling. This is an estimate from observed utilisation, not a bill; the first
real invoice replaces it here.

Workload is bursty and tiny — a full 11-SKU planning cycle is about 40 seconds of CPU — so
this should hold. If it stops holding, splitting the worker into its own service is the first
thing that would push it up, and is not being done.

### What was actually verified in production

`GET /api/verify` returns **all twelve checks passing**. Each carries its evidence:

- `phase_is_shadow`, `nothing_published` (0 published / 15 refused),
  `publication_was_actually_attempted_and_refused` — publication is blocked *and* the block
  was exercised rather than merely configured.
- `no_paid_advertising` (CA$0), `no_revenue_claimed` (CA$0, 0 ledger entries),
  `every_agent_has_a_cost_ceiling` (15/15), `spend_limits_not_breached`.
- `no_model_provider_configured` — no API key exists, and the system says so.
- `state_is_in_a_durable_database` — engine `postgresql`, with certified releases and audit
  records that could not have come from a container that started empty.
- `worker_is_alive`, `scheduler_has_ticked`, `no_unexpected_dead_letters_in_24h`.

Beyond the endpoint:

- **Real unattended cycles ran in production.** `POST /api/plan-cycle` for several dates;
  267 jobs, **zero non-publish failures**, 15 products and 15 certified releases. A cycle for
  a different date correctly produced a *different* portfolio and added only the new products.
- **Restart recovery, twice.** Container restarted with work queued; state identical
  afterwards (same products, same certified releases, no duplicates), new process confirmed by
  a changed worker start time. Six concurrent cycles (79 jobs) drained across a restart with
  no failures and no duplicated products.
- **Scheduler and heartbeat run in the deployed environment** — `ops.heartbeat` records real
  queue state on its cadence.
- **Honest gap:** no production job needed a second attempt, because every cycle drained
  faster than a Railway restart takes effect. So in-flight *lease reclaim* is not proven on
  Railway specifically. It is proven locally in `tests/test_persistence.py`, which SIGKILLs a
  real worker subprocess mid-job — a harder case than Railway's graceful restart.

## Integrations connected
- None. Railway account exists but no project is provisioned.

## Owner actions required

**1. Delete the stray Railway service `Project-Money` (housekeeping, ~1 minute).**
- *Exact action:* in the Railway project `brambleloop` → `production`, delete the service
  named `Project-Money` (`4dff24df-2186-4278-b01f-c11ec39a766f`).
- *Why:* it was created by accident — a deploy call spawned a second service instead of
  deploying to `brambleloop-os`. Its build failed and it is not running, so it costs nothing
  measurable, but it is not part of the system and should not sit in the project pretending
  to be. Deletion was declined when attempted from this session.
- *Maximum cost:* CA$0. Leaving it costs nothing either; this is tidiness, not spend.
- *Consequence of waiting:* none beyond confusion for whoever opens the project next.

Deferred until the system actually reaches them (Master Plan section 35), in order:
object storage for artifact durability → brand/trademark clearance for "Brambleloop Studio"
→ Etsy account/KYC → banking. **Do not ask for these yet.**

## Financial state
Exact and verified. Nothing here is projected.

- **Recurring infrastructure:** Railway Hobby plan, US$5 / ~CA$7 per month, which includes
  US$5 of usage. Measured usage is ~US$1.70/month, so no overage is expected. Owner ceiling
  is CA$20/month; nothing may exceed it without the owner's approval.
- **Spend to date:** CA$0 invoiced. No bill has been issued yet.
- **Agent/model spend:** CA$0 — no model provider is configured and no model call has been
  made.
- **Advertising spend:** CA$0 — paid media is not enabled.
- **Revenue:** CA$0. **Customers:** 0. **Orders:** 0. **Listings live:** 0.

## Current blockers
- None blocking. All remaining work in the execution order is unblocked.

## Known refinements (tracked, not urgent)
- Yardage constants are uncalibrated heuristics with a stated tolerance; physical tests
  replace them per yarn/hook. Never present an uncalibrated estimate as precise.
- Reverse compiler handles the writer's grammar plus common variants; widen coverage as real
  pattern styles appear.
- Brand model imagery (Master Plan section 6) raises a disclosure question — AI-generated
  lifestyle imagery of a fictional model wearing an item that has not been physically made
  must not imply a photograph of a real finished object. Asset Truth + Policy Gate own this;
  flagged so it is decided deliberately, not by default.

## Next highest-value unblocked actions
1. Incident → regression-fixture automation to close Gate B.
2. Storefront Director and the brand/model system (section 6): collection naming, crop and
   lighting rules, visual QA, and the disclosure question around AI lifestyle imagery.
3. Search Domination and Thumbnail Warfare (sections 10, 7): keyword coverage modelling and
   listing-image variant scoring.
4. Engineer the remaining ten release candidates rather than letting them ship the templated
   striped panel. Only the flagship has a real design so far.
5. Row-level repeats in the CIR ("repeat rows 2-25 four more times"). The flagship's written
   instructions currently spell out all 120 rows where a real pattern would collapse them.
6. Brand/trademark clearance screening for "Brambleloop Studio" before any commercial launch.

## Changelog
- 2026-09-17: Initial build. Competition retired. CIR engine complete (27 tests).
- 2026-09-17: Platform layer — durable queue, agent governance, audit, spend caps, backup
  drill (14 tests). Gate D test caught a real bug: the spend guard raised inside its session,
  so the rollback discarded the `paused` flag and a breach would have refused one spend then
  accepted the next. Fixed: the pause commits before the raise.
- 2026-09-17: Release gates — asset truth, policy, certificate, incidents (27 tests).
- 2026-09-17: Shadow pipeline + worker/scheduler (8 tests). Two ordering bugs found and fixed:
  permission was checked *after* handler lookup (so an agent reaching for forbidden work that
  had no handler was recorded as "no handler" instead of denied), and a shadow-mode refusal
  was being retried with backoff against a mode that cannot change between attempts.
- 2026-09-17: Deployable surface (FastAPI admin/API, container, entrypoints), real-process
  persistence proof (5 tests) and the chaos suite (21 tests). Persistence testing exposed a
  race in its own harness — a three-second lease could expire during subprocess spawn — fixed
  by expiring leases deterministically in the database instead of sleeping on the wall clock.
- 2026-09-17: Market Radar (30 tests). Replaced the placeholder concept stubs with dated
  competitor intelligence and a 34-concept scored pool, and wired the section 33 portfolio
  selector into `radar.scan`. Three real bugs found while building it: the buy-window buffer
  was flat rather than proportional, so a 60-hour Christmas throw was scored as "too early"
  in September against direct evidence to the contrary; the constraint-repair loop could
  evict a quick low-price make to make room for a quick low-price make and spin forever; and
  the bundle was outranking everything in the pool while its members went unbuilt.
- 2026-09-17: Full shadow release chain on the flagship (26 tests) plus the deployment
  surface (8). Four real defects found and fixed while building it: the digital twin was using
  turning-chain units as physical row heights, overstating a blanket's finished length by
  half — a size claim, therefore a refund; the yardage constants were set by feel and came out
  at less than half of a checkable reference, which would have told a customer a throw needed
  190 m of yarn; support indexed row counts by row number into a zero-based list, so it
  confidently answered the wrong row; and the flagship's written instructions flattened every
  repeat across the full 144 stitches, producing a row instruction eleven lines long that no
  maker could follow.
- 2026-09-17: Model Gateway (21 tests). Prompts are immutable and content-hashed, output is
  parsed strictly, cost is recorded per agent so a runaway loop hits the daily ceiling rather
  than the bill, and a dead provider's circuit opens instead of absorbing doomed calls. Two
  standing constraints are now asserted rather than documented: no registered prompt may ask
  a model for pattern content, and `require_deterministic()` raises if a model verdict is
  offered where the compiler has one.
- 2026-09-17: **Deployed to Railway and verified in production.** Four real defects surfaced
  only by watching the deployed service, none of which any local test could have caught:
  the container hardcoded port 8000 so the health check probed nowhere; the embedded worker
  started a full planning cycle the instant the app came up and starved the health endpoint
  until the platform failed a working deployment; the operational heartbeat had been
  dead-lettering every fifteen minutes since the first boot because it was scheduled against
  an agent with no permission for it; and the fix for that never reached production, because
  agent seeding was insert-if-absent and the row already existed. A fifth appeared when a
  dated planning cycle ran two jobs instead of sixty: `plan.cycle` dropped `as_of`, so the
  run scored against today and collapsed into the morning's idempotency keys.
  Each fix carries a test: every cadence must be runnable by its agent, permissions reconcile
  on deploy, and a cycle's date must reach the radar.
- Totals: 200 tests passing, 0 failing. Gates A, C, D, E, F passing; B passing except
  regression automation.
