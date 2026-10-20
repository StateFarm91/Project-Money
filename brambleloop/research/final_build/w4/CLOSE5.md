# W4-CLOSE5

Branch `claude/w4-CLOSE5`, based on `origin/claude/w4-INTEG3` at 364ade0. Production is b931d17
(SHADOW). This branch makes no deploys, no production writes and no spend.

## 1. Security review of 324927f, R1 (LOW): FIXED, dev-proven

**Finding:** an unauthenticated refusal flood on `/api/etsy/webhook` could take the shared
AnyIO threadpool tokens (40 per process, shared with about 187 sync routes) and the DB pool
(5 + 10 overflow).

**Fix:**
- `integrations/etsy_webhooks.py`: `WebhookGate` / `GATE` gives the webhook its own
  `anyio.CapacityLimiter` with `WEBHOOK_SLOTS = 4`, so it never uses the default limiter.
  Admission is non-blocking (`threading.BoundedSemaphore.acquire(blocking=False)`). When the
  gate is saturated, the route returns `None` at once and runs no thread and no DB work.
  `busy()` returns a static 503 with `Retry-After: 5`. Etsy retries a 5xx, so a real delivery
  that is shed is not lost. `summary()["gate"]` exposes in-process counters
  (`slots`, `in_flight`, `admitted`, `shed_busy`) without a DB read.
- `app/main.py` `api_etsy_webhook`: `refuse` and `receive` run through `gate.run(...)`. A
  slot is taken only after the capped async body read, so a slow client cannot hold one.

**Tests:**
- `tests/test_w4_close5_r1.py`, 4 tests:
  - a private limiter is used (the default limiter's borrowed tokens do not change);
  - the 4th call is shed in under 50 ms, and its work never runs;
  - a slot is released when the work raises;
  - `slots < QueuePool pool_size (5)`;
  - the route answers 503 + Retry-After with `refuse`/`receive` never called and the refusal
    counters unchanged, then recovers (401 counted, 202 accepted).
- `tests/test_w4_integ3_secfixes.py::test_m1_...threadpool` is now **strengthened**: it
  requires `gate.run` and forbids `run_in_threadpool` in the route.

Production evidence is still needed, so this is dev-proven and awaiting deploy.

## 2. Spend: weekly `creative.grid_tournament`, input tokens cut, dev-proven

**Measured run:** about CA$13, 84 judge calls, 2.89M input tokens. That is about 34,400
tokens a call, or about 4,300 an image at 8 images a call. Full-size images dominate:
`IMAGE_TOKENS_ESTIMATE`'s measured mean is about 5,000 per `il_fullxfull` image.

**Unchanged:**
- models (`provider_for("gallery_observation")`);
- the 3 judges and their personas;
- `MAX_IMAGES_PER_CALL` (8);
- the median rule, `GRID_THRESHOLD` and the F-278 / #218 readers;
- the spend ceiling and the per-call reservation (`IMAGE_TOKENS_ESTIMATE` per image is still
  reserved, so the budget check stays conservative).

**Downscale** (`creative/blinded.py`, `judge_view`). The judges are asked to score
*thumbnails on a simulated Etsy search page*; the browsing judge looks "on a phone ... for
about a second". On a search results card, Etsy serves `il_340x270` (1x) and `il_570xN`
(2x srcset). 570 px wide is therefore the largest picture a real search page shows, and the
smallest that loses nothing the simulated page would show. The same rule applies on both
sides, so the comparison stays fair:
- benchmark: `il_fullxfull.<id>` becomes `il_570xN.<id>`, the same Etsy image resized by Etsy
  itself. It is still a URL and nothing is downloaded. Checked by a read-only GET
  (2026-10-20): the variant exists, 1200x1400 becomes 570x665;
- ours: resized locally to 570 px wide, aspect kept, never enlarged, same format and
  basename. The copy is in a content-addressed cache bounded to 256 entries.

**Reuse** (`grid_fingerprint`, `cached_panel`, `store_panel`):
- The fingerprint hashes:
  - the content address of every cell on the page (URL, or sha256 of the bytes sent);
  - pod, provider, model, judge personas, prompt template, fields, max_tokens and the batch
    limit;
  - the view width and version.
- A complete panel is stored as an `AuditLog` row `creative.grid_panel`. A panel is complete
  only when every judge answered every cell on every field, nothing was stopped and nothing
  failed.
- An identical grid is reused within `PANEL_REUSE_DAYS` (56), with cell-by-cell mapping
  through content addresses. A reused panel costs 0 and makes no call. It is revalidated
  before use, so a tampered or partial stored row is refused.
- The panel is not reused when:
  - any picture or the benchmark set changes (scores are relative to the page);
  - the model changes;
  - two cells share one picture.
- Registered in `ops/retention.KNOWN_READ_ACTIONS` as `windowed`.

**Estimated saving** (`tests/test_w4_close5_grid_spend.py::test_estimated_saving_on_the_measured_production_run`,
using the provider's (w x h)/750 rule):

| | per image | per call (8 images) | run (84 calls) | CA$ |
|---|---|---|---|---|
| before (measured) | ~4,300 | ~34,400 | 2.89M | ~13.0 |
| after, square 570x570 | 434 | ~3,700 | ~0.31M | ~1.4 |
| after, worst 2:3 portrait 570x855 | 650 | ~5,450 | ~0.46M | ~2.1 |

That is **at least 84% fewer input tokens, about CA$11 or more saved a run**, before reuse.
Reuse then makes every week whose page is unchanged (same benchmark set, same heroes)
cost **CA$0** for that pod. The reuse rate is not measured yet, so no number is claimed for it.

**Tests:**
- `tests/test_w4_close5_grid_spend.py` (10): Etsy variant rewrite; resize, aspect, name,
  format and no-enlarge; judges receive only 570-wide images; the saving estimate; identical
  grid reused with no call and 0 spend; changed hero, changed benchmark set or changed model
  re-judged; incomplete panel never stored or reused; stale or tampered panel refused;
  duplicate pictures not reused; retention registration.
- Existing suites unchanged and green: `test_blinded` (46), `test_w4_herotourney` (4),
  `test_w4_b2vision` (7), `test_cert_preengineering` (19), `test_cert_intel_wave2` (15).

This is dev-proven and awaiting deploy. The production saving is read from the first weekly
run after deploy: `spend_report` rows with purpose `search_grid_tournament`.

## 3. Build 2 / Final Master closures

### 3.0 Method

- **Board re-read on production b931d17.** I took read-only GETs at 2026-10-20T04:16Z
  (`evidence_BOARD/*_20261020T0416Z.json`) and regenerated the ledgers, board and scope with
  the existing generators. That re-read alone moved:
  - Build 2 verified from 116 to 198;
  - FM launch-critical from 333 to 358.

  These moves come from the deploy, not from this lane, so they are not counted as closures
  below.
- **Closing a row whose code is already deployed** uses these mechanisms:
  - the mapping-row corrections are applied by `w4/close5.py`
    (`mapping/remap_b931d17/`, and `aggregate.py` REMAP_SHAS `b931d17`, a closure-only
    remap);
  - a `BOARD_CLOSURES.json` row whose health file names b931d17;
  - evidence:
    - the production GET;
    - `evidence_CLOSE5/deployed_tree_tests_b931d17.json`. Every cited test file was run
      unchanged, through testslot, on a clean detached worktree of b931d17. The CLOSE5 test
      files were copied in, and src was untouched.
- **A row whose module this branch edits** gets the mapping correction only. The board then
  counts it as dev-proven, awaiting deploy.
- **`module_reachability.json` regenerated on b931d17**
  (`evidence_CLOSE5/module_reachability_b931d17.json`; 697 modules, 604 reached, **none lost**
  against 0417f35).
  - The previous file dated from 0417f35. Every module added since then was absent from it,
    so `aggregate.cap()` held the W4-FMCLOSE rows at TESTED. That is why they never closed.
  - Regenerating it changed the class of no row other than those listed here. I diffed the
    board before and after.

### 3.1 Batch 1: launch-critical class-A engineering rows (closed on b931d17)

| row | criterion (quoted) | tests | evidence |
|---|---|---|---|
| **F-152** Scratch Non-Authority | "Recovery/audit evidence cannot exist only in ephemeral scratch." | `test_w4_close5_rows.py::test_f152_*` (4). All 31 scratch sites in src/ are classified with their durable home and checked; a new site fails until classified. The continuity proof and the offsite archive are restored from the DB or remote store after the scratch directory is deleted | `prod_api_offsite_20261020T0416Z.json` (last_archive ok); `prod_api_build_…` (offsite_storage OPEN); deployed-tree run |
| **F-299** Controlled Phase Change | "Shadow -> staging -> live publication/ads is explicit owner-approved transition with rollback." | `test_fb4_launch.py` (4 phase tests), `test_rc1_auth.py::test_A1_…`, `test_w3_k4_launch_verdict.py::test_F300_rollback…`, plus new `test_f299_ad_spend_follows_the_recorded_owner_transition_not_the_environment` (the ads half was unasserted) and `test_f299_the_staging_step_cannot_be_skipped_and_needs_the_owner` | `prod_api_verify_…` phase_is_shadow: env == recorded, agree; 186 publication refusals; ad spend 0.0. The mapping's "add a PhaseTransition record" was stale: `core/phase.py` is deployed |
| **F-718** No Chat as Source of Truth | "...No critical state may exist only in a Claude, GPT or Fable conversation." | `test_w4_provenance.py` (2), new `test_f718_*` (2): the approval record matches or mismatches the DB; no runtime module reads dev-lane or session state | `prod_api_model_identity_…` approval_record **MATCH** (audit 5693); `prod_api_audit_model_frozen_…`. **Judgment call for the owner:** `ops/registry.py` (`ops/JOBS.json`) is build-session tooling outside the deployed tree. The runtime never reads it (test), and each lane's outcome is committed (branch + `w4/<NAME>.md`). I treat that as not "critical state only in a conversation" |
| **F-283** First-Sale Attribution | "Record first-sale source honestly (organic Etsy, Etsy Ads, Offsite Ads, owned/direct, unknown). One sale proves possibility, not scale." | `test_w4_fmclose_etsy.py::test_f283_…`, `test_money_truth.py` (3) | the route (built by W4-FMCLOSE) is deployed; transactions_r OPEN; deployed-tree run |

### 3.2 Batch 2: the W4-FMCLOSE Etsy rows

| row | scope | criterion (quoted) | tests | status |
|---|---|---|---|---|
| **F-682** Accountant Activity | LC | "show last reconciliation, discrepancies, close status, tax/threshold alerts and evidence; never silently force mismatches to zero." | `test_w4_fmclose_etsy.py::test_f682_*` (2) | **closed on b931d17** (deployed-tree run, module reached) |
| **F-558** Order Operations Ledger | LC | "For every order, reconcile payment, item/version, digital delivery state, buyer issue, refund/cancellation/case state and downstream accounting evidence." | `test_f558_every_order_reconciles_six_parts…`, plus new `test_w4_close5_rows2.py` (2): item/version with its basis, the cancellation path, and unknown version is a problem | **closed on b931d17** |
| **F-570** Offsite Ads Economics | post | "Track Offsite Ads attribution, fee rate, 30-day attribution behavior and the shop's 365-day revenue threshold/participation status. Recompute contribution margin on attributed orders." | `test_f570_*` (3) | **closed on b931d17**. The recorded defect (unread read as 0%) is fixed and tested |
| **F-574** Marketing Channel Attribution | post | "Compare organic Etsy search, Etsy Ads, Offsite Ads, social and Share & Save at listing/product-family level. One order cannot be double-credited to multiple channels internally." | `test_f574_*`, `test_money_truth.py::test_ingest_writes_unknown_source…` | **closed on b931d17**. The recorded defect (organic-looking defaults) is fixed: ingest writes `unknown` |
| **F-657** Event Wakeups | post | "orders, messages, reviews, refunds, Etsy events, policy changes, incidents, spend anomalies, research signals, schedules and owner decisions wake the appropriate team." | `test_f657_*` (2) | **closed on b931d17** |
| **F-512** Webhook Reliability | post | "Webhook/event handling includes validation, idempotency, duplicate protection, retries, storage and observability." | `test_f512_*` (5) + `test_w4_close5_r1.py` | **dev-proven, awaiting deploy** (`etsy_webhooks.py` edited by R1) |
| **F-501** Etsy Event Feedback | LC | "Supported Etsy events feed a durable, idempotent business-event layer after authenticated integration is proven." | `test_f501_*` | **dev-proven, awaiting deploy** (same module) |

I did not close **F-590**. W4-FMCLOSE's own note says it is met only for channels that can be
observed on receipts: the SELL_ON_FACEBOOK listing flag is not read from the live shop.

### 3.3 Spot audit: 20 more verified rows (`BOARD_AUDIT.json`, sample `close5_random`)

`random.seed(20261020)` over the verified rows not already audited. Result: **16 PASS and
4 DOWNGRADE (20%)**. All four are **re-closed** with tests. Each downgraded row's behaviour was
already in b931d17; only the assertion was missing.

| row | verdict | finding | re-closed by |
|---|---|---|---|
| F-251 Search Language Integrity | DOWNGRADE | only TAGS were tested; the criterion's "Titles" clause was unasserted | `test_w4_close5_audit.py::test_f251_a_foreign_language_title_is_refused_unless_a_deliberate_translation` |
| F-073 Risk-Class Validation Matrix | DOWNGRADE | "novel assemblies" and "new construction primitives" never asserted as raising the class | `test_f073_a_novel_assembly_raises_the_class…`, `test_f073_a_new_construction_primitive_raises_the_class_until_calibrated` |
| B2#219 Elite Panel Beyond One Seller | DOWNGRADE | "purchased Benchmark Library products" on the panel unasserted | `test_b2_219_a_purchased_library_product_puts_its_seller_on_the_panel` |
| F-057 Materials/Technique Intent | DOWNGRADE | only technique truth tested; material truth unasserted | `test_f057_a_material_the_pattern_does_not_use_is_refused_and_the_strategy_blocks_it` |

PASS rows:
- F-784, F-835, B2#194, F-860, B2#57, B2#139, F-277, F-891, B2#200, F-133, F-700, B2#233,
  F-101, F-918, F-074, B2#63.

Nine of the PASS rows have a citation finding: the ledger names tests that miss the clause, and
other existing tests assert it. These are recorded as `citation_finding`:
- F-784, B2#57, B2#139, F-891, B2#200, B2#233, F-101, F-918, B2#63.

Across this sample and W4-BOARD's, the pattern is the same: a multi-clause criterion where only
some clauses are tested.

### 3.4 Batch 3: rows built by W4 lanes that never wrote their mapping back, plus F-535, F-542 and F-878

Six W4 lanes merged into production (FAILMEM, RESEARCH, IMPROVEMETRICS, SWARMCONTROL,
SWARMMETRICS, MJSCOUNT) without updating the mapping. Their rows stayed `engineering_open`.
For each row I re-audited the lane's tests against the quoted criterion before closing it.

| row | criterion (quoted, abridged where long) | tests | status |
|---|---|---|---|
| **F-378** Failure Memory | "Known failed methods/providers/prompts/architectures are fingerprinted with the evidence that rejected them. They are not retried without a materially changed premise or new evidence." | `test_w4_failmem.py` (4). The recorded defect "stop_doing advisory" is fixed by the propose guard | closed on b931d17 |
| **F-427** Negative Evidence | "Record well-designed failed experiments and authoritative negative findings as durable knowledge; absence of success is not proof of impossibility…" | `test_w4_failmem.py` (4) | closed on b931d17 |
| **F-428** Scope Discipline | "A failed implementation rejects only the tested method/class at the supported scope…" | `test_w4_failmem.py` (2) | closed on b931d17 |
| **F-706** Learning Ledger | "…Failed approaches remain institutional knowledge so Brambleloop does not unknowingly repeat known failures." | `test_w4_failmem.py` (2). The recorded defect "no repeat guard" is fixed | closed on b931d17 |
| **F-403** Unknown Detection | "Agents must explicitly identify uncertainty, missing evidence, stale knowledge, …" | `test_w4_research.py` (3) | closed on b931d17 |
| **F-409** Fact / Claim / Inference Separation | "…distinguish directly observed facts, source claims, Brambleloop inference, hypothesis and unresolved uncertainty…" | `test_w4_research.py` (3) | closed on b931d17 |
| **F-424** Research Reproducibility | "Record queries/terms, source identifiers/URLs …, versions/dates, key evidence, extracted constraints and resulting decisions…" | `test_w4_research.py` (2) | closed on b931d17 |
| **F-433** Research Freshness | "Durable research carries freshness/expiry semantics appropriate to the domain…" | `test_w4_research.py` (1) | closed on b931d17 |
| **F-399** Learning Health Metrics | "Expose … adoption/rejection rate, regressions caught, repeated-failure avoidance, cost per adopted improvement…" | `test_w4_improvemetrics.py` (2) | closed on b931d17 |
| **F-605** Company Learning Memory | "Persist experiments, failures, reversals, evidence, confidence and withdrawn claims…" | `test_w4_improvemetrics.py` (1) | closed on b931d17 |
| **F-535** Refund/Cancellation Root Cause (LC) | "Every refund, cancellation, case or complaint receives a reason code and owner. Repeated causes trigger … investigation." | `test_k8_shop_cx.py` (2) | closed on b931d17 (transactions_r OPEN) |
| **F-542** Remote Write Readback (LC) | "Every Etsy mutation that can affect customers must be followed by authoritative remote readback… A 2xx response is insufficient proof…" | new `test_w4_close5_rows3.py` (3): a rule over every Etsy mutation call site in src/ (draft-only sites listed with reasons); an activation Etsy accepted but did not apply is not recorded live; a rollback whose read-back still differs is not recorded restored. Plus existing publish read-back tests. The mapping's "publish path performs no read-back" was stale | closed on b931d17 |
| **F-878** Launch Packet (LC) | "Owner receives candidate SHA, tests/audit, Visual status, listings/products, policy state, owner actions, spend limits, economics, rollback and activation steps." | `test_fb4_launch.py` (2), `test_w4_packetrel.py` (2) | closed on b931d17. Evidence: `evidence_CLOSE5/launch_packet_b931d17a738d_20261020T053641Z.json`, generated by the deployed tree's own script; `recorded_suite` is PASS, bound to `release/RELEASE_324927f1…` by tree digest plus ancestor. The owner can confirm by reading `/api/cc/launch/packet` with the owner credential, which I do not hold |

Left open after the audit:
- **F-394.** The criterion names "risk reduction, confidence". `roi.prioritise` has neither
  term.
- **F-398.** I did not assert per-improvement "old/new version, tests, quality-floor verdicts" as
  one record.
- **F-431.** W4-RESEARCH itself says it is partial: the `research.run` job and the fetch step
  are missing.
- **F-457.** The producer is operator tooling (`ops/registry.py`), so INTEGRATED is unreachable.
  It needs the integrator's structural-target decision.
- **F-470.** Storage and Railway capacity are not measured.
- **F-489.** Wall-clock compression and conflict rate are not measured.
- **F-590.** Not closed; see §3.2.

### 3.5 Batch 4: SWARM / MJs rows and a production 500

**Production defect found and fixed: `GET /api/departments` returns HTTP 500 on b931d17.**
- Evidence: `evidence_BOARD/prod_api_departments_20261020T0540Z.json`.
- Cause: `swarm.metrics.agents_view` indexed `parked[t]["why"]`. A job type in *backoff* (an
  unchanged poll) carries `until`/`factor` and no `why`, so the KeyError fires as soon as any
  agent holds a backed-off job type.
- Why tests missed it: W4-SWARMMETRICS's route test only checked that the route string exists.
- Fixed in `swarm/metrics.py` (`_parked_why`). The view now also carries each agent's
  `last_output` (its newest finished job), which covers the criterion's "output/evidence" clause.
- Tests: `test_w4_close5_rows4.py` (2) execute the route against a database holding a backoff
  and a suspension.

| row | status |
|---|---|
| **F-473** Priority Preemption | closed on b931d17 (`test_w4_swarmcontrol.py` (3), `swarm/preempt.py` reached) |
| **F-191** MJs Scan Consistency | closed on b931d17 (`test_w4_mjscount.py` (3)) |
| **F-193** Gallery Cost Forecast | closed on b931d17 (`test_w4_mjscount.py` (2)) |
| **F-192** Scan Health Semantics | dev-proven, awaiting deploy (the display is in `app/main.py`, which R1 edits) |
| **F-487** Department Health | dev-proven, awaiting deploy (the 500 fix) |
| **F-655** 24/7 Valuable Work | dev-proven, awaiting deploy (`swarm/metrics.py` edited). The production reading already holds: `prod_api_swarm_runtime_20261020T0540Z.json` shows `starved_ready` starved 0, capacity idle |
| **F-730** No Lost Opportunity | dev-proven, awaiting deploy. Production shows `untouched_opportunities` 0 of 20 gaps |

## 4. Findings for the integrator

1. **Production `/api/departments` returns 500 on b931d17.** The fix is on this branch (§3.5).
2. **The production dead letter that blocks the 24 h off-device proof on b931d17:**
   `intel.gallery_analysis` failed at 2026-10-20T04:05:50Z with "TimeoutError: The read
   operation timed out".
   - What the code shows: a socket read timeout inside `gateway/anthropic._send` is not one of
     the errors that become `TransientError`. `_classify_failure` reads it as UNCERTAIN, since
     the call may have billed. `paid_calls.guarded` then refuses to resend an unresolved
     request, so the job's retries cannot succeed.
   - I did not change it. It is the billing-safety policy of a hot module, and that is a
     decision for the gateway owner. It is why `no_unexpected_dead_letters_in_24h` fails on
     b931d17.
3. **`module_reachability.json` was stale (0417f35).** Every module added since then was capped
   at TESTED, which is why the W4-FMCLOSE and W4 lane rows never closed. It is regenerated on
   b931d17 (§3.0). It should be regenerated at every deploy.
4. **Lanes that build rows should run `close_*.py` and write the mapping back.** Six merged
   lanes did not, so about 30 rows looked unbuilt.

### 3.6 Batch 5: deployed rows whose gap was a test, a consumer name or a stale maturity cap

| row | criterion (quoted) | tests | status |
|---|---|---|---|
| **F-491** Failure Isolation | "A failed department task does not roll back unrelated validated work. Contain failures to their dependency branch and preserve successful independent outputs." | new `test_w4_close5_rows5.py`. The cited tests only covered the failing job itself; this one shows a dead letter leaves a completed job's status, outputs and audit untouched, and work queued beside it completes | closed on b931d17 |
| **F-586** Delivery Settings Applicability | "Audit delivery/shipping settings even for a digital-first shop; mark physical-only controls explicitly not applicable rather than silently ignoring them." | `test_etsy_surfaces.py::test_unsupported_and_not_applicable_are_never_the_same_verdict`, `test_w4_etsysurf.py` route | closed on b931d17. The registry is reached at runtime, so TESTED becomes INTEGRATED |
| **F-591** Pattern / External Channel Boundary | "If Etsy surfaces Pattern or other owned-site channels, evaluate them separately from Etsy marketplace sales…" | registry invariants, plus `test_f590_inventory_names_effects…` (a Pattern sale is its own channel and opens an incident) | closed on b931d17 |
| **F-793** Functional Technique Reuse | "Standard crochet methods … may be used … rather than preserve a competitor's distinctive overall expression by default." | `test_specification.py` (3) | closed on b931d17. It is reached through certification |
| **F-498** Finite Parallel Launch | "…Launch blockers remain explicitly bounded." | `test_w4_etsysurf.py` (3). W4-ETSYSURF put the bounded first-sale list into readiness | closed on b931d17 |

Not closed, with reasons:
- **F-546.** Seller Handbook, Etsy Plus and Shop Manager capability changes are not watched;
  only the OpenAPI document is.
- **F-599.** Its owner-review task is not built, and it needs a ruling.
- **F-600.** Most surfaces have no collector.
- **F-478.** No test yet shows research and engineering running independently.
- **F-148.** The producer is test infrastructure, so INTEGRATED is unreachable.

### 3.7 Batch 6: Command Center, growth, search and funding rows built by merged lanes, plus F-240

| row | criterion (quoted) | tests | status |
|---|---|---|---|
| **F-619** Brambleloop Command Center | "…web app with Today, Month, Finance, Products, Listings, Marketing, Customers, Experiments, Departments, Agent Activity, Owner Actions and System Health…" | `test_w4_ccfm1.py::test_every_named_owner_area_has_a_route_and_an_api` | closed on b931d17 |
| **F-651** Unified Studio | "one Brambleloop Studio app contains Command Center, Products, Visual, Etsy, Marketing, Finance, Customers, QA, Research, Reliability, Agents and Owner Inbox." | same test | closed on b931d17 |
| **F-504** Experiment Attribution | "Record what changed, why, evidence, expected effect, measured effect, owner/department and retain/rollback decision." | `test_w4_ccgrow.py` (2) | closed on b931d17 |
| **F-660** Elastic Capacity | "…normal multi-agent operation continues when promotional/paid cloud credit is zero." | `test_w4_f660_zero_credit.py` (2) | closed on b931d17 |
| **F-056** Size/Scale Intent | "Capture size/shape intent where meaningful." | `test_w4_size_shape_intent.py` (3) | closed on b931d17 |
| **F-871** Provider Funding Is Authority (LC) | "Model/vision credit is owner financial authority; bounded experiment and max spend are prepared first." | `test_w4_funding.py` (4) | closed on b931d17 on the production readback W4-FUNDING named: `prod_api_funding_packets_20261020T0612Z.json` serves the credit packet (30-day spend by purpose, CA$100 ceiling, CA$35.28 headroom, run rate, outage evidence, `approves_itself` false) |
| **F-240** Public Seller Identity Integrity (LC) | "Approved public shop identity may differ from legal/tax presentation only where Etsy permits; legal, payout and tax identity remain truthful." | `test_storefront_fb4.py` (3) | closed on b931d17. The mapping's "MISSING" was stale: `brand/seller_identity.py` (FB-4) enforces the rule and is reached via `launch.plan`. The legal values stay UNKNOWN until the owner confirms them at KYC, and readiness blocks until then |

Not closed:
- **F-621, F-661, F-668, F-729.** The CC views carry most of what each criterion names, but not
  all of it:
  - F-621: no charter-KPI trend;
  - F-661: conversion, active departments and owner decisions are not on the executive block;
  - F-668: no org chart, heartbeat or learning;
  - F-729: no restarts, experiments or improvements on the autonomy-health block.
- **F-652, F-653, F-670.** Design-quality criteria. W4-CCFM1/2 recorded these as evidence or
  partial.
- **F-126.** W4-CCGROW says it is partial: visual benchmark rows are not superseded.
- **F-100.** W4-FUNDING left the approved-provider refusal for an owner ruling.

Production observation from the same readback: `/api/funding/packets` reports model probes
failing 156 of 223 (0.70) and 86 parked model jobs over 30 days. That is outage evidence for the
owner's diversification decision, F-100.

### 3.8 Batch 7: F-019 and F-046 (post-launch class-A engineering; no code change needed)

| row | criterion (quoted) | tests | status |
|---|---|---|---|
| **F-019** Plural/Root Waste Detector | "Do not burn tag slots on singular/plural variants Etsy already root-matches." | `test_w4_close5_rows6.py` (3) | closed on b931d17. The mapping's "MISSING" was stale. `commerce/search.intent_key` folds plurals (`_stem_word`: -s and -ies to -y, but never -ss), word order and synonyms. `_acceptable_tag` refuses a phrase whose folded key an already-chosen tag carries, in both the must-include pass and the value pass. A surviving pair becomes a blocking `TAG_SEMANTIC_DUPLICATE` in the release gate (`runtime/release.py`, `seo/packages.py`). Until now, no test asserted the singular/plural case |
| **F-046** No Paid-Rank Myth | "Never model Etsy Ads or Etsy Plus as organic ranking boosts." | `test_w4_close5_rows6.py` (2) + `test_ranking_readiness.py` | closed on b931d17. Before this batch there was no guard; the guard is now a test over deployed code. An AST scan of the organic ranking modules (`commerce/search.py`, `commerce/seo.py`, `commerce/ranking_readiness.py`, `seo/*.py`) finds no paid-media import, no Etsy Ads, Offsite Ads, Etsy Plus or ROAS name or string, and no use of `search_policy`'s ads thresholds. The scan is self-checked against a planted line. Recording CA$353 of ads, offsite-ads and Etsy Plus cost leaves every ranking dimension, the certificate and the summary identical |

`close5.py` is now idempotent on re-run: the `searched` tag is no longer appended again on each
regeneration, and the repeats from earlier runs are collapsed.
