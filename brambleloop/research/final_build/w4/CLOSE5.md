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
