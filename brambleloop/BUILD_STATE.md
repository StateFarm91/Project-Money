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
Verified by `./run_tests.sh` — **371 tests passing, 0 failing**, including 23 that
assert the owner's acceptance gates line by line.

Suites: CIR engine, platform, release gates, market radar, model gateway, brand and
storefront, commerce (pricing, search, thumbnail, paid media), departments (support, content,
portfolio), quality (confidence, regression), finance, shadow pipeline, real-process
persistence, chaos, deployment surface, flagship run and adversarial attacks, generated
catalogue, and the acceptance gates.
- The full release chain runs end to end with no human in the loop, and correctly *refuses*
  to publish in shadow mode. A single `plan.cycle` now carries an entire 11-SKU portfolio
  from market scan to eleven release certificates without intervention.
- Persistence is **proven, not assumed**: a worker is SIGKILLed mid-job against a file-backed
  database and a fresh process recovers and completes the work, inputs intact, with no
  duplicate side effects.
- Cloud deployment: **live and verified.** See "Deployment" below for the exact
  configuration, the twelve production checks that pass, and the measured cost.
- Catalogue: **17 engineered designs** (16 generated from the motif library plus the
  hand-placed flagship). Every one compiles, reverse-compiles and certifies. Ten of the eleven
  release candidates ship an engineered design; the eleventh is the collection bundle, which
  correctly has no pattern of its own.
- Storefront, listings, imagery and content: **drafted and held.** 11 listings, 70 listing
  images, ~97 content pieces and a collection, none of it published. Nothing in this system
  can publish: there is no Etsy, Pinterest, email, video or messaging integration at all.
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
Master Plan v1.2's commercial departments, built on the proven infrastructure rather than
alongside it. Sections 6, 7, 8, 9, 10, 11, 12 and 16 now have running code and tests:

- **Brand system and Storefront Director (§6).** Palette, type, crop and lighting rules, a
  two-word collection naming grammar, the brand model's character bible with three enforced
  refusals, grid-coherence measurement, and the whole shop drafted — announcement, About, five
  policies, sections, banner and icon briefs.
- **Listing imagery (§7).** Seven ordered frames rendered from the twin, each declaring its
  asset class and claims, checked by Asset Truth, with the hero judged at Etsy's real
  search-grid size.
- **Search Domination (§8).** A query model that distinguishes reachable phrases from head
  terms a shop with no history cannot place for, thirteen tag slots spent under a word budget,
  coverage scored against reachable demand, and structured attributes from pattern data.
- **Pricing Intelligence (§9).** Market price scanner, contribution-per-visitor optimiser,
  bundle economist with a breakeven attach rate, price experiments whose stopping rule is
  fixed before they run, and promotion checks that refuse a permanent sale.
- **AI Customer Experience (§10).** Triage across seven desks with escalation ordered first,
  replies drafted and recorded as unsent, review solicitation refused, and repeated questions
  about one row surfaced as candidate defects.
- **Marketing (§11).** A full content ecosystem per product — article, four distinct pins,
  tutorial outline, email with a CASL unsubscribe, validated free teaser, cross-sell and a
  crochet-along where the make time warrants one — scheduled backwards from launch.
- **Portfolio (§12).** Section 12's diagnostic table as code, with intervention ladders, and a
  classifier that refuses to classify a SKU nobody has seen.
- **Confidence (§3) and regression capture (Gate B).** Seven dimensions tracked separately with
  no overall score, and confirmed defects frozen as permanent fixtures.
- **Paid media guard rails (§11).** Every ceiling section 11 names, and every auto-pause
  condition: tracking failure, unavailable listing, CAC breach, refund anomaly and the
  test-loss cap. Built while no campaign exists and no money can be spent — `authorise_spend`
  refuses on phase and on missing owner authority before it looks at any budget, because a cap
  is not permission.
- **Finance (§1, §15, §34).** The full P&L section 15 lists, read from observed entries only;
  a tax reserve that is never counted as ours; cost-per-validated-pattern computable without
  revenue; a CFO/Skeptic that reports concerns when everything is nominally fine and blocks on
  infrastructure above the owner's ceiling or advertising with no attributable orders; and a
  CA$100K trajectory that refuses to forecast from zero orders.
- **The catalogue (§16).** A motif library and a builder; sixteen designs generated, every one
  compiling and reverse-compiling clean. Ten of eleven release candidates now ship an
  engineered design rather than the striped template; the eleventh is the bundle, which
  correctly has no pattern of its own.

## Last completed milestone (previous)
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

## Acceptance gates

Every line of `spec/03_Acceptance_Tests_and_Autonomy_Gates.pdf` now has a named test in
`tests/test_acceptance_gates.py`, so "Gate B passes" is a claim backed by a test rather than
inferred from a scattering of others.

- **Gate A (Infrastructure): passing.** Worker restart loses no durable jobs; a replayed cycle
  duplicates no products; backup and a tested restore succeed; dead-letter and backoff work;
  the audit log identifies actor, action and artifact.
- **Gate B (Pattern Safety): passing — now complete.** Known-good compiles; a broken stitch
  count fails; a bad repeat fails; a construction-changing mutation of the customer text is
  caught by reverse compilation; **and a corrected bug creates a regression test**, which was
  the one line that kept this gate open. The repository carries a regression corpus of
  defective patterns that must keep failing.
- **Gate C (Asset Truth): passing.** An absent motif is rejected; unsupported size, material
  and difficulty claims are blocked; provenance is stored for every listing asset.
- **Gate D (Commercial Safety): passing — now complete.** Price and promotion changes pass
  policy; an ad budget breach is prevented and the scope auto-pauses with no refused spend
  leaking through; **contribution accounting reconciles against test transactions**, which was
  the outstanding line; per-agent cost ceilings hold.
- **Gate E (Customer Experience): passing — now complete.** Routine support is answered from
  the correct pattern version and recorded as unsent; repeated defect reports correlate into
  one incident; support cannot patch a CIR by any path; a P1 halts the publication workflow.
- **Gate F (Shadow Graduation): passing.** A full product completes Market Radar → Opportunity
  → CIR → QA → PDF/assets → pricing → listing draft → launch plan → simulated support with no
  intervention, and a second test asserts that **nothing graduated**: no publication, no
  ledger entry, no message sent.

Passing these is permission to graduate SHADOW → STAGING, not graduation. Nothing has
graduated, and nothing will without the owner.

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
- The test suite now takes roughly twenty minutes, because several files each run the full
  eleven-product pipeline including 2000px image rendering. Slow and representative beats fast
  and unrepresentative, but a lighter pipeline fixture for the tests that do not care about
  image content would pay for itself.
- Yardage constants are uncalibrated heuristics with a stated tolerance; physical tests
  replace them per yarn/hook. Never present an uncalibrated estimate as precise.
- Reverse compiler handles the writer's grammar plus common variants; widen coverage as real
  pattern styles appear.
- Brand model imagery (Master Plan section 6) raises a disclosure question — AI-generated
  lifestyle imagery of a fictional model wearing an item that has not been physically made
  must not imply a photograph of a real finished object. Asset Truth + Policy Gate own this;
  flagged so it is decided deliberately, not by default.

## Next highest-value unblocked actions
1. Row-level repeats in the CIR ("repeat rows 2-25 four more times"). Written instructions
   currently spell out every row where a real pattern would collapse them. This is the largest
   remaining *product-quality* gap and it is a CIR schema change, so it touches the compiler,
   the writer, the reverse compiler and the twin together.
2. Construction beyond flat rows: worked-in-the-round shaping, seaming and assembly. Until the
   CIR can model them, amigurumi, bags and garments cannot be engineered honestly, which is
   why they are absent from the catalogue rather than approximated.
3. Physical test coordination (section 3): the PHYSICAL_TESTS table exists and nothing writes
   to it. Yardage stays uncalibrated and Class B/C products stay unshippable until a real
   person crochets a real sample. This is the next genuine owner-adjacent gate.
4. Brand/trademark clearance screening for "Brambleloop Studio" before any commercial launch.
5. Live-data halves of Pricing Intelligence, Thumbnail Warfare and Portfolio, which are built
   and correctly refuse to act without observations that do not exist yet.

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
- 2026-09-17: **Master Plan v1.2's commercial departments** (sections 6-12, 15, 16, 34).
  Brand system and Storefront Director; listing imagery as part of the release; Search
  Domination; Pricing Intelligence; AI Customer Experience; the content ecosystem; portfolio
  classification; separate confidence dimensions; regression capture closing Gate B; a motif
  library and sixteen generated designs; and the full P&L with a CFO challenge.
  Four real defects found while building: the thumbnail check counted non-background pixels,
  so a two-colour crochet fabric — half cream against a cream background — scored 9% and
  blocked six products for a problem none of them had; the fabric renderer coloured cells by
  their row's yarn, which in overlay mosaic is flat stripes and no motif at all; tag selection
  spent six of thirteen slots on the word "mosaic"; and the pipeline had been certifying a
  "Collection Bundle" whose PDF was a twelve-row striped panel — a product sold as three
  patterns and delivered as one invented swatch.
- Totals: 371 tests passing, 0 failing. All six acceptance gates pass, each line with its own
  named test. Gates A, C, D, E, F passing; B passing except
  regression automation.
