# W4-B2GATES: audit of the 102 gated Build 2 rows (54 owner-gated, 41 data-gated, 7 external)

Date: 2026-10-11 (UTC). Branch `claude/w4-B2GATES`, from `origin/claude/w4-NEXTREL` b34c968.

**Ledger used.** The authoritative copy is `research/final_build/w4/BUILD2_LEDGER.json`. It was
last written by 846dbcb (W4-B2VERIFY, 2026-10-10T03:26Z), and every lineage carries that same
commit (B2CLOSE, B2VERIFY, PACKETREL, NEXTREL). That JSON is older than the B2CLOSE code fixes, so
I recomputed the ledger from the current registry and code with `build2.closure.ledger(db)`. The
gate states came from a fresh local database, so every gate was closed. The result was the same
215 / 54 / 41 / 7 / 3 / OPEN-DEFECT 0, before and after this lane's changes. The per-row machine
output is in `B2_GATES_AUDIT.json`.

**No requirement was created.** The only reclassification is #35 and #39, EXTERNAL → OWNER, made in the follow-up (G2).

## Method

**(a) Is the gate genuine, and is it named precisely?** For each row I checked three things:
- The row's gate key exists in `executor.GATES` with a `what` and an `opens_when`.
- An owner gate has an owner decision (`ops.owner_queue.DECISION_BY_GATE`) that says who acts and
  what they do.
- The executor gate table agrees with the registry.

**(b) Is the company-side work behind the gate done and wired?** For each row I checked that:
- the machinery the row names exists, is tested, and is reached from a runtime root (the
  closure's `proof_of`);
- the cited tests exist;
- something in the running system writes the durable state the gate's checker reads. Without
  that, the gate can never open, however much the owner, buyer or provider does.

I checked that last point against every checker in `executor.GATES`.

## What I built: the defects found

| ID | Rows | Defect | Fix | Test |
|---|---|---|---|---|
| **F1** | #4 #10 #246 #247 #248 #251 #255 (owned_surfaces) | The gate reads the latest `owned_surface.probe` audit row, and **nothing in the codebase wrote one**. The owner could open a site or a Pinterest account and all 7 rows would have stayed parked. | New `growth/owned_surface.py`, run six-hourly by `ops.capability_probes`. Every check is a read; nothing is published or spent. **Site:** ok when `BRAMBLELOOP_SITE_URL` serves `/.well-known/brambleloop-surface.txt` containing `brambleloop-owned-surface`, a file the owner published. **Pinterest:** ok when `PINTEREST_ACCESS_TOKEN` reads at least one board through `GET /v5/boards`; no pin is created. The token is never recorded. The gate's `opens_when` now names these exact steps. | `test_w4_b2gates`: probe ×2, wiring |
| **F2** | #189 #221 #222 #320 (acceptance_ruling) | The gate reads a done OwnerAction under `decision.api_vision_equivalence`, and **nothing created that row**. There was no door to record the ruling. | New Command Center action `acceptance.rule`. It needs step-up and a reason. The gate card offers two rulings, "API+vision satisfies" and "browser required"; either one opens the gate. The action records a SATISFIED OwnerAction with an audit row. | `test_w4_b2gates` |
| **F3** | #294 #295 (ad_authority) | The gate reads `SpendLimit('ads')`. The only writer is `SpendGuard.set_limit`, which **had no caller**, while the owner step said "set SpendLimit … (owner credential)". | New Command Center action `ads.set_limit` on the ad_authority card. It needs step-up and a reason, and refuses anything above `paid_media.CONSERVATIVE_CAPS` (CA$3/day, CA$25 lifetime). It sets authority only: nothing is spent, and SpendGuard still enforces the cap. The card appears only once the decision is askable (W4-GATESB precondition). | `test_w4_b2gates` |
| **F4** | #9 #43 #250 (tester_roster) | The gate reads a CreatorProfile agreement. `quality.tester_programme.record_agreement` is documented as "the one intake" and **had no caller**. | New `POST /api/tester/agreement`. It needs the operator credential and is default-deny. It requires express consent and a named consent source (CASL), records only, and sends nothing. | `test_w4_b2gates` (401 / 400 / 200 → gate opens) |
| **F5** | #244 #245 (customers) | The registry `proof` cited only a test, so the closure reported **no machinery and no runtime consumer**. The machinery exists and runs daily. | Registry `proof` now names `commerce/paid_media.py` and `runtime/growth_ops.py`, with a note. State and parking are unchanged. The closure now shows the machinery as existing, tested and reached. | `test_w4_b2gates` |

The 16 rows behind F1–F4 were all genuine gates. For each one, the company side that turns the
owner's act into an open gate was missing; it is now built.

## Follow-up (same lane): data gates named, #35/#39 reclassified, and the #94 decision for the coordinator

The recomputed ledger is now **PROVEN 215 / OWNER-GATED 56 / DATA-GATED 41 / EXTERNAL-GATED 5 /
NOT-APPLICABLE 3 / OPEN-DEFECT 0**. It was regenerated with the official generator
(`build2_ledger.py`) from the same production gate reading as before
(`evidence_B2/prod_gates_2026-10-10.json`, fcb982d). The new data gates have no production
reading, so they show `unchecked`. The only row-state changes are #35 and #39, from EXTERNAL to
OWNER.

### G1. The eight prose-only data gates now have keys the ledger reads

All eight are registry `data_gated` rows, and the registry forbids `parked_on` on them. So:
- each gate is an `executor.GATES` entry with an empty requirement tuple;
- `executor.DATA_GATE_FOR` maps each row to its gate;
- `closure.classify` reads the mapping for registry data_gated rows.

A closed gate keeps the row DATA-GATED. An opened gate moves it to OPEN ("the measured reading
is now owed"), the same rule every parked row follows. `approval_inbox` lists each gate under
`waiting_on_data` with the row it holds, never as an owner card.

| Row | Gate | Opens when (the runtime record the row's own machinery reads, at its own minimum) |
|---|---|---|
| #23 Numeric Scale/Kill | `listing_traffic` | a ListingOutcome with visits > 0 (commerce.kill_table's input) |
| #82 Creative Performance Learning | `style_outcomes` | one hero_style on ≥3 listings with ≥200 impressions (style_learning MIN_LISTINGS / MIN_IMPRESSIONS) |
| #89 Creativity Outcome Learning | `concept_outcomes` | ≥200 ListingOutcome visits and ≥20 countable Orders (outcome_learning MIN_VISITS / MIN_ORDERS) |
| #94 Creativity Capability Scorecard | `market_outcomes` | listing traffic AND ≥1 countable Order (CTR / conversion / winner rate) |
| #98 External Learning Radar | `learning_sources` | LearningObservation rows in both `techniques` (a craft source) and `customer_pain` |
| #140 Cultural Demand Lead-Lag | `lead_lag_series` | `culture.radar.lead_lag(signal)` is measurable for one CultureObservation signal |
| #296 Seasonal Revenue War Room | `seasonal_orders` | a countable Order whose season (order detail, else the concept seed) is a SEASONAL_EVENT |
| #298 Post-Season Learning Harvest | `season_harvest` | a SeasonHarvest with status `measured` (≥20 orders in a passed occurrence) |

Tests in `test_w4_b2gates`:
- every registry data_gated row has a mapped, classified and described gate;
- the ledger names each gate;
- each gate is closed on an empty DB and opens exactly at its record's threshold;
- below-threshold records, unpaid orders and unassigned seasons do not open it;
- an opened gate un-parks its row.

Note for production: the culture feed already writes readings, so `lead_lag_series` may already
be open there. If it is, #140 will read OPEN-DEFECT on its next live read. That is an evidence
change, not a reclassification.

### G2. #35 and #39 are classified by who opens their gate

The `rendered_pages` gate opens on a recorded browser.probe, which etsy.com/legal refuses with a
403. It also opens on `platform_policy.page_readings_status`. That condition is met when:
- all 5 etsy.com/legal pages (seller_policy, creativity_standards, advertising_rules,
  shilling_and_reviews, children_and_baby) each have a reading;
- each reading was recorded by a named person (`read_by`) through `POST /api/policy/snapshot`
  and audited;
- each is no more than 30 days old, with no unreviewed change.

The person is **the owner**, through the owner_queue decision `policy_page_reading` ("open the 5
pages in your own browser … every 30 days", 15 minutes, CA$0). So the rows are OWNER-GATED:
- `closure.PERSON_OPENED_GATES` names who opens it;
- the ledger row carries `gate.kind = OWNER-GATED`, `gate.opened_by` and `gate.gate_kind_of =
  EXTERNAL-BLOCKED`.

`kind_of('rendered_pages')` is unchanged, because tests/test_w4_b2close.py and
tests/test_cert_dashboard.py pin it. As a result the owner queue still lists `rendered_pages`
under "external capability unavailable" and does not ask the owner live. The ask exists only in
the release packet, where the live-first Approvals view shows it under "not tracked live".
**Proposed fix (needs your decision, since it changes those two pinned tests):** in
`approval_inbox`, raise a card for a PERSON_OPENED gate instead of listing it as external.

### D1. #94 and the model_provider owner card (for your decision; nothing changed)

**What the live card says** (`approval_inbox`, fresh DB at this head):

> gate `model_provider`: "a model provider that can actually serve a request". Action: "Set ONE
> Railway variable … ANTHROPIC_API_KEY". **unblocks: [94]**, unblocks_count 1, max CA$25,
> 10 min.

The `fund_model` decision batch item lists unblocks `[15, 44, 61, 67, 86, 88, 116, 126, 218, 277,
281, 304, 308, 309, 94]`, and its consequence_of_yes ends "…, #94".

**What #94 actually waits on.** The registry status is `data_gated`. The note says "What remains
needs data no engineering here supplies: market CTR, conversion and winner rate need live traffic
and a sale". The ledger agrees: DATA-GATED, now on gate `market_outcomes`. No model call
produces a CTR or a sale. The blinded half of #94 (`creative/blinded.py`) already runs without
the gate, and per its note "cannot currently return a number … a fact about the catalogue".

**Why they disagree.** The hand-written gate table still holds `Gate("model_provider", …,
(94, 277, 281), …)`. #277 and #281 have since moved to `image_vision` by registry `parked_on`,
and the registry wins for them. #94 has no `parked_on`, because data_gated rows may not carry
one. So the old table entry survives, and `gated_requirements()` reports #94 as parked on
model_provider.

**Effect.**
- The model_provider card exists only because of #94. Without it, the gate unblocks nothing and
  would be listed under `suppressed_unblocks_nothing`.
- The owner is told that adding an API key unblocks a scorecard that actually needs a sale.
- fund_model is still a genuine ask through `image_vision`, which holds 14 rows.

**Proposed fix** (one line, plus re-pointing one test fixture):
1. Remove 94 from the `model_provider` tuple, giving `(277, 281)`. The registry already wins
   for those two, so nothing else moves. Optionally make `gated_requirements()` skip table
   entries for rows whose registry status is data_gated or covered, so drift like this cannot
   recur.
2. Drop "#94" from fund_model's `consequence_of_yes`.
3. `tests/test_cert_dashboard.py::test_a_legacy_row_for_a_closed_gate_merges_into_its_card_rather_than_duplicating`
   uses model_provider as its example closed gate with a legacy `model_credits` row. Re-point it
   at `image_vision` (same fund_model decision, 14 rows) or add a test-local parked row.
   **Not done here, by instruction.**

#140 has the same table drift: `culture_feed` holds `(140, 147)`. It is already listed as
`company_opened_not_owner`, so it is never shown to the owner as an ask. The same one-line
cleanup applies.

## Per-row table (102 rows)

Columns: **Who unblocks** is who or what clears the gate. **Gate producer** is what writes the
state the gate's checker reads (**NEW** means built in this lane). **Company side** is whether
the machinery exists and is reached, with the reached modules and the number of test references.

| # | Title | Kind | Gate | Who unblocks | Gate producer | Company side | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Etsy Marketplace Insights as First-Party Demand  | OWNER | insights_access | owner (reads Shop Manager Insights) | POST /api/insights/snapshot → intel.insights.record → InsightsSnapshot | yes (insights.py, executor.py; 3 test refs) | genuine; company side wired |
| 4 | Pre-Production Demand Validation | OWNER | owned_surfaces | owner (opens a site / Pinterest) | **NEW** ops.capability_probes → growth.owned_surface.probe → `owned_surface.probe` row | yes (preproduction.py, registry.py; 9 test refs) | gate could never open → fixed F1 |
| 8 | Proof Stack | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (proof.py; 1 test refs) | genuine; company side wired |
| 9 | Creator and Tester Distribution | OWNER | tester_roster | a tester agrees (owner confirms outreach) | **NEW** POST /api/tester/agreement → tester_programme.record_agreement → CreatorProfile | yes (creators.py, owned.py; 4 test refs) | gate could never open → fixed F4 |
| 10 | Free-to-Paid Acquisition Engine | OWNER | owned_surfaces | owner (opens a site / Pinterest) | **NEW** ops.capability_probes → growth.owned_surface.probe → `owned_surface.probe` row | yes (free_to_paid.py, owned.py; 6 test refs) | gate could never open → fixed F1 |
| 11 | First 100 Customers Program | OWNER | transactions_r | owner (re-authorise Etsy app with transactions_r) | Etsy OAuth grant (runtime.etsy_ops) + etsy.probe → orders_ingest.gate | yes (cohorts.py; 2 test refs) | genuine; company side wired |
| 12 | Customer LTV and Cohorts | OWNER | transactions_r | owner (re-authorise Etsy app with transactions_r) | Etsy OAuth grant (runtime.etsy_ops) + etsy.probe → orders_ingest.gate | yes (cohorts.py, ladder.py; 3 test refs) | genuine; company side wired |
| 14 | Conversion Benchmark Engine | OWNER | live_listings | owner (leave shadow + per-listing publication grant) | store.publish (runtime.pipeline) sets Listing.etsy_listing_id under a grant | yes (benchmarks.py; 2 test refs) | genuine; company side wired |
| 15 | First-Page SERP Laboratory | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (serp.py, etsy_public.py; 5 test refs) | genuine; company side wired |
| 16 | Listing Experiment Discipline | OWNER | live_listings | owner (leave shadow + per-listing publication grant) | store.publish (runtime.pipeline) sets Listing.etsy_listing_id under a grant | yes (listing_tests.py, experiments.py; 3 test refs) | genuine; company side wired |
| 18 | Customer-Service Conversion Advantage | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (service.py; 2 test refs) | genuine; company side wired |
| 19 | Promotional Science | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (promotion.py; 2 test refs) | genuine; company side wired |
| 20 | Owned-Audience Compounding | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (owned.py, content.py; 3 test refs) | genuine; company side wired |
| 21 | Creator Micro-Seeding | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (creators.py; 1 test refs) | genuine; company side wired |
| 23 | Numeric Scale/Kill Framework | DATA | listing_traffic | buyers / time (data) | **NEW** data gate `listing_traffic`: per-listing traffic (ListingOutcome visits > 0) | yes (kill_table.py; 1 test refs) | genuine data gate, now named and checked (G1) |
| 25 | $3K Run-Rate Decomposition | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (runrate.py, weekly.py; 5 test refs) | genuine; company side wired |
| 28 | Conditional Scale Rules | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (runrate.py, readiness.py; 5 test refs) | genuine; company side wired |
| 31 | Cost-to-Create and Profitable Throughput | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (unit_cost.py, governor.py; 3 test refs) | genuine; company side wired |
| 33 | Replace the narrow Christmas Strike Team with a  | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (engine.py, daily.py; 7 test refs) | genuine; company side wired |
| 35 | Etsy Creativity / AI Disclosure Gate | OWNER (was EXTERNAL) | rendered_pages | the owner: reads the 5 etsy.com/legal pages every 30 days | POST /api/policy/snapshot / intel.browser.probe | yes (platform_policy.py; 4 test refs) | reclassified to who opens it (G2) |
| 37 | Marketplace Insights Query Budgeter | OWNER | insights_access | owner (reads Shop Manager Insights) | POST /api/insights/snapshot → intel.insights.record → InsightsSnapshot | yes (insights_budget.py, executor.py; 3 test refs) | genuine; company side wired |
| 39 | Policy Freshness Watch | OWNER (was EXTERNAL) | rendered_pages | the owner: reads the 5 etsy.com/legal pages every 30 days | POST /api/policy/snapshot / intel.browser.probe | yes (platform_policy.py; 3 test refs) | reclassified to who opens it (G2) |
| 41 | Refund / Chargeback / Case Prevention | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (buyer_trust.py, department.py; 8 test refs) | genuine; company side wired |
| 43 | Tester Capacity Marketplace | OWNER | tester_roster | a tester agrees (owner confirms outreach) | **NEW** POST /api/tester/agreement → tester_programme.record_agreement → CreatorProfile | yes (testers.py; 3 test refs) | gate could never open → fixed F4 |
| 44 | Brand Moat Beyond the Model | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (moat.py; 2 test refs) | genuine; company side wired |
| 45 | Product Cannibalization / Bundle Attribution | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (attribution.py, bundles.py; 4 test refs) | genuine; company side wired |
| 46 | Price Elasticity Memory | OWNER | live_listings | owner (leave shadow + per-listing publication grant) | store.publish (runtime.pipeline) sets Listing.etsy_listing_id under a grant | yes (elasticity.py; 3 test refs) | genuine; company side wired |
| 48 | Launch Cohort Holdout | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (elasticity.py, weekly.py; 4 test refs) | genuine; company side wired |
| 51 | Business Continuity Export | OWNER | offsite_storage | owner (bucket + credential) | ops.offsite_archive cadence / POST /api/offsite/archive → core.offsite.archive | yes (continuity.py; 2 test refs) | genuine; company side wired |
| 54 | Pre-Etsy Launch Readiness Gate | OWNER | insights_access | owner (reads Shop Manager Insights) | POST /api/insights/snapshot → intel.insights.record → InsightsSnapshot | yes (readiness.py; 3 test refs) | genuine; company side wired |
| 61 | Visual Semantic QA | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (layout_qa.py, eligibility.py; 5 test refs) | genuine; company side wired |
| 64 | Physical Proof Upgrade Path | OWNER | physical_proof | a tester (physical make) | POST /api/physical-test → physical.record → PhysicalTest.completed_at | yes (eligibility.py, listing_set.py; 4 test refs) | genuine; company side wired |
| 67 | Competitive Creative Benchmark | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (benchmark_set.py, blind_review.py; 5 test refs) | genuine; company side wired |
| 72 | Mandatory Brambleloop Model for Applicable Produ | EXTERNAL | model_bearing_render | external (provider must render a certified structure) | daily assets.model_photography handler → audit rows | yes (identity.py, model_photography.py; 4 test refs) | genuine; company side wired |
| 82 | Creative Performance Learning | DATA | style_outcomes | buyers / time (data) | **NEW** data gate `style_outcomes`: one hero style on ≥3 listings with ≥200 impressions | yes (style_learning.py; 3 test refs) | genuine data gate, now named and checked (G1) |
| 86 | Creativity Benchmark Memory | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (vision.py, mechanisms.py; 4 test refs) | genuine; company side wired |
| 88 | Idea-to-Thumbnail Test | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (concept.py, preengineering.py; 4 test refs) | genuine; company side wired |
| 89 | Creativity Outcome Learning | DATA | concept_outcomes | buyers / time (data) | **NEW** data gate `concept_outcomes`: ≥200 visits and ≥20 countable orders | yes (outcome_learning.py; 3 test refs) | genuine data gate, now named and checked (G1) |
| 94 | Creativity Capability Scorecard | DATA | market_outcomes | buyers / time (data) | **NEW** data gate `market_outcomes`: listing traffic AND a countable sale | yes (blinded.py; 1 test refs) | genuine data gate, now named and checked (G1); owner card mismatch → D1 |
| 98 | External Learning Radar | DATA | learning_sources | buyers / time (data) | **NEW** data gate `learning_sources`: LearningObservation in 'techniques' and 'customer_pain' | yes (learning.py, serp.py; 4 test refs) | genuine data gate, now named and checked (G1) |
| 116 | Creative Reference Decomposition | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (reference.py; 2 test refs) | genuine; company side wired |
| 120 | Holiday-to-Holiday Learning Transfer | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (discovery.py, ideation.py; 4 test refs) | genuine; company side wired |
| 126 | Search-Grid Blind Tournament | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (board.py, blinded.py; 6 test refs) | genuine; company side wired |
| 130 | Model-Led Brand Storytelling | EXTERNAL | model_bearing_render | external (provider must render a certified structure) | daily assets.model_photography handler → audit rows | yes (identity.py, model_photography.py; 4 test refs) | genuine; company side wired |
| 140 | Cultural Demand Lead-Lag Model | DATA | lead_lag_series | buyers / time (data) | **NEW** data gate `lead_lag_series`: culture.radar.lead_lag measurable for one signal | yes (feeds.py, demand.py; 2 test refs) | genuine data gate, now named and checked (G1) |
| 147 | Culture Radar Feeds Continuous Improvement | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (daily.py, content.py; 5 test refs) | genuine; company side wired |
| 163 | Brambleloop Must Add Unique Value | OWNER | benchmark_purchases | owner (CA$300 purchase) | POST /api/teardown/intake → teardown.library.register → BenchmarkProduct | yes (certificate.py, lab.py; 7 test refs) | genuine; company side wired |
| 165 | Benchmark Refresh Cadence | OWNER | benchmark_purchases | owner (CA$300 purchase) | POST /api/teardown/intake → teardown.library.register → BenchmarkProduct | yes (benchmark_refresh.py; 2 test refs) | genuine; company side wired |
| 168 | Pre-Launch Benchmark Challenge | OWNER | benchmark_purchases | owner (CA$300 purchase) | POST /api/teardown/intake → teardown.library.register → BenchmarkProduct | yes (readiness.py, pipeline.py; 3 test refs) | genuine; company side wired |
| 169 | Post-Purchase Delight Metric | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (lab.py, scorecard.py; 4 test refs) | genuine; company side wired |
| 189 | Cloud Browser/Vision Worker Pool | OWNER | acceptance_ruling | owner (ruling, free, ~2 min) | **NEW** CC action `acceptance.rule` (step-up) → done OwnerAction `decision.api_vision_equivalence` | yes (browser.py, executor.py; 3 test refs) | gate could never open → fixed F2 |
| 195 | Proof of Off-Device Autonomy | OWNER | production_window | owner (authorise the unattended window) | computed: build2.autonomy.launch_item == PROVEN | yes (autonomy.py, executor.py; 4 test refs) | genuine; company side wired |
| 202 | Appropriate Product-First Styling | EXTERNAL | model_bearing_render | external (provider must render a certified structure) | daily assets.model_photography handler → audit rows | yes (brief.py; 2 test refs) | genuine; company side wired |
| 203 | Model Merchandising Shot System | EXTERNAL | model_bearing_render | external (provider must render a certified structure) | daily assets.model_photography handler → audit rows | yes (executor.py, model_photography.py; 5 test refs) | genuine; company side wired |
| 218 | MJs Challenge Gate | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (blind_review.py; 3 test refs) | genuine; company side wired |
| 221 | Mandatory Cloud Browser + Vision Capability | OWNER | acceptance_ruling | owner (ruling, free, ~2 min) | **NEW** CC action `acceptance.rule` (step-up) → done OwnerAction `decision.api_vision_equivalence` | yes (browser.py, executor.py; 3 test refs) | gate could never open → fixed F2 |
| 222 | Browser/Vision Acceptance Test | OWNER | acceptance_ruling | owner (ruling, free, ~2 min) | **NEW** CC action `acceptance.rule` (step-up) → done OwnerAction `decision.api_vision_equivalence` | yes (acceptance.py, executor.py; 3 test refs) | gate could never open → fixed F2 |
| 226 | Specialist Pod Continuous Learning | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (pod_learning.py, mission_runtime.py; 5 test refs) | genuine; company side wired |
| 229 | CA$5K/Month Becomes the Primary Commercial Scale | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (target.py, weekly.py; 5 test refs) | genuine; company side wired |
| 235 | Etsy Targeted-Offer Optimizer | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (promotion.py; 2 test refs) | genuine; company side wired |
| 236 | Marketplace Insights Portfolio Allocator | OWNER | insights_access | owner (reads Shop Manager Insights) | POST /api/insights/snapshot → intel.insights.record → InsightsSnapshot | yes (insights.py, insights_budget.py; 5 test refs) | genuine; company side wired |
| 237 | Search-Term-to-P&L; Attribution | OWNER | insights_access | owner (reads Shop Manager Insights) | POST /api/insights/snapshot → intel.insights.record → InsightsSnapshot | yes (attribution.py, leading.py; 3 test refs) | genuine; company side wired |
| 238 | Conversion Cohort Benchmarks | OWNER | live_listings | owner (leave shadow + per-listing publication grant) | store.publish (runtime.pipeline) sets Listing.etsy_listing_id under a grant | yes (benchmarks.py; 3 test refs) | genuine; company side wired |
| 239 | Search Share-of-Opportunity Dashboard | OWNER | live_listings | owner (leave shadow + per-listing publication grant) | store.publish (runtime.pipeline) sets Listing.etsy_listing_id under a grant | yes (benchmarks.py, arbitrage.py; 3 test refs) | genuine; company side wired |
| 241 | Listing Launch Experiment Pack | OWNER | live_listings | owner (leave shadow + per-listing publication grant) | store.publish (runtime.pipeline) sets Listing.etsy_listing_id under a grant | yes (experiments.py; 5 test refs) | genuine; company side wired |
| 242 | Organic-First Proof Before Heavy Ads | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (paid_media.py; 2 test refs) | genuine; company side wired |
| 243 | Paid Acquisition Allowable CAC | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (runrate.py; 2 test refs) | genuine; company side wired |
| 244 | Offsite Ads Economics Guard | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (paid_media.py, growth_ops.py; 3 test refs) | evidence mapping fixed (F5) |
| 245 | Share-and-Save / Direct-Link Economics | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (paid_media.py, growth_ops.py; 3 test refs) | evidence mapping fixed (F5) |
| 246 | Pinterest Search Factory | OWNER | owned_surfaces | owner (opens a site / Pinterest) | **NEW** ops.capability_probes → growth.owned_surface.probe → `owned_surface.probe` row | yes (pins.py, calendar.py; 3 test refs) | gate could never open → fixed F1 |
| 247 | Google / SEO Topic Cluster Engine | OWNER | owned_surfaces | owner (opens a site / Pinterest) | **NEW** ops.capability_probes → growth.owned_surface.probe → `owned_surface.probe` row | yes (clusters.py, observe.py; 4 test refs) | gate could never open → fixed F1 |
| 248 | Video Distribution Flywheel | OWNER | owned_surfaces | owner (opens a site / Pinterest) | **NEW** ops.capability_probes → growth.owned_surface.probe → `owned_surface.probe` row | yes (video.py, artefacts.py; 4 test refs) | gate could never open → fixed F1 |
| 250 | Tester-to-Ambassador Path | OWNER | tester_roster | a tester agrees (owner confirms outreach) | **NEW** POST /api/tester/agreement → tester_programme.record_agreement → CreatorProfile | yes (creators.py; 4 test refs) | gate could never open → fixed F4 |
| 251 | Email / Owned Audience Lifecycle | OWNER | owned_surfaces | owner (opens a site / Pinterest) | **NEW** ops.capability_probes → growth.owned_surface.probe → `owned_surface.probe` row | yes (tools.py, experiments.py; 4 test refs) | gate could never open → fixed F1 |
| 252 | Repeat Purchase Engine | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (repeat.py; 2 test refs) | genuine; company side wired |
| 253 | Collection Subscription / Club Research Lane | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (club.py; 2 test refs) | genuine; company side wired |
| 254 | Personalization / Customization Layer | OWNER | live_listings | owner (leave shadow + per-listing publication grant) | store.publish (runtime.pipeline) sets Listing.etsy_listing_id under a grant | yes (personalisation.py; 2 test refs) | genuine; company side wired |
| 255 | Free Tool Acquisition Layer | OWNER | owned_surfaces | owner (opens a site / Pinterest) | **NEW** ops.capability_probes → growth.owned_surface.probe → `owned_surface.probe` row | yes (tools.py, substitution.py; 3 test refs) | gate could never open → fixed F1 |
| 256 | Product-Led Referral Research | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (referral.py, reviews.py; 5 test refs) | genuine; company side wired |
| 257 | Review-to-Conversion Learning | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (reviews.py, observe.py; 4 test refs) | genuine; company side wired |
| 258 | Customer Project Gallery | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (buyer_trust.py, experiments.py; 3 test refs) | genuine; company side wired |
| 260 | First-100-Customer Interview Sampling | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (interviews.py; 2 test refs) | genuine; company side wired |
| 263 | Leading Indicator Dashboard | OWNER | live_listings | owner (leave shadow + per-listing publication grant) | store.publish (runtime.pipeline) sets Listing.etsy_listing_id under a grant | yes (leading.py; 2 test refs) | genuine; company side wired |
| 265 | Growth Experiment Portfolio | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (experiments.py; 4 test refs) | genuine; company side wired |
| 266 | Incrementality Discipline | OWNER | live_listings | owner (leave shadow + per-listing publication grant) | store.publish (runtime.pipeline) sets Listing.etsy_listing_id under a grant | yes (experiments.py; 4 test refs) | genuine; company side wired |
| 270 | Revenue Concentration Stress Test | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (mix.py, confidence.py; 4 test refs) | genuine; company side wired |
| 272 | Scale Readiness Gate | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (readiness.py, weekly.py; 3 test refs) | genuine; company side wired |
| 277 | NON-NEGOTIABLE: Proven-Trend Seasonal Capture | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (intake.py; 4 test refs) | genuine; company side wired |
| 280 | Colour-Forecast Layer | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (colour.py, feeds.py; 4 test refs) | genuine; company side wired |
| 281 | MJs-to-Brambleloop Seasonal Response Pipeline | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (intake.py; 4 test refs) | genuine; company side wired |
| 292 | Evergreen-to-Seasonal Multiplier | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (remerchandising.py; 1 test refs) | genuine; company side wired |
| 294 | Pre-Season Ad Learning Window | OWNER | ad_authority | owner (ads budget; not askable until a listing is ready to sell) | **NEW** CC action `ads.set_limit` (step-up, ≤ CONSERVATIVE_CAPS) → SpendLimit('ads') | yes (growth_ops.py; 2 test refs) | gate could never open → fixed F3 |
| 295 | Aggressive Winner Scaling | OWNER | ad_authority | owner (ads budget; not askable until a listing is ready to sell) | **NEW** CC action `ads.set_limit` (step-up, ≤ CONSERVATIVE_CAPS) → SpendLimit('ads') | yes (growth_ops.py; 2 test refs) | gate could never open → fixed F3 |
| 296 | Seasonal Revenue War Room | DATA | seasonal_orders | buyers / time (data) | **NEW** data gate `seasonal_orders`: a countable order attributed to a seasonal event | yes (leadtime.py; 3 test refs) | genuine data gate, now named and checked (G1) |
| 298 | Post-Season Learning Harvest | DATA | season_harvest | buyers / time (data) | **NEW** data gate `season_harvest`: a measured SeasonHarvest | yes (harvest.py, leadtime.py; 4 test refs) | genuine data gate, now named and checked (G1) |
| 300 | Seasonal System Acceptance Test | EXTERNAL | model_bearing_render | external (provider must render a certified structure) | daily assets.model_photography handler → audit rows | yes (cycle.py, executor.py; 3 test refs) | genuine; company side wired |
| 304 | MJs Listing Photos Must Be Visually Studied | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (vision.py, observe.py; 3 test refs) | genuine; company side wired |
| 308 | Owner Example - Christmas Cardigan Response | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (family.py, response.py; 7 test refs) | genuine; company side wired |
| 309 | MJs Trend-to-Season Mission Pipeline | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (response.py, mission_runtime.py; 4 test refs) | genuine; company side wired |
| 315 | MJs Quality Challenge Is Release-Blocking | OWNER | benchmark_purchases | owner (CA$300 purchase) | POST /api/teardown/intake → teardown.library.register → BenchmarkProduct | yes (audits.py; 2 test refs) | genuine; company side wired |
| 317 | Ten-Pattern Benchmark Laboratory | OWNER | benchmark_purchases | owner (CA$300 purchase) | POST /api/teardown/intake → teardown.library.register → BenchmarkProduct | yes (purchase_selection.py, lab.py; 3 test refs) | genuine; company side wired |
| 320 | MJs Mission End-to-End Acceptance Test | OWNER | acceptance_ruling | owner (ruling, free, ~2 min) | **NEW** CC action `acceptance.rule` (step-up) → done OwnerAction `decision.api_vision_equivalence` | yes (acceptance.py, executor.py; 3 test refs) | gate could never open → fixed F2 |

## Tests run

All runs were focused, one at a time, with a private TMPDIR. The full suite was not run because
CPU is shared with the NEXTREL full suite.

- New: `test_w4_b2gates` 11/11.
- Existing, all passing (exit 0):
  - test_w4_b2_build2_ledger (ALL OK)
  - test_w4_b2close 18/0
  - test_closure 27/0
  - test_w4_gatesb 10/0
  - test_w4_owner_actions 6/0
  - test_capability_gates
  - test_policy_intake 9/0
  - test_build2
  - test_cert_dashboard 18/18
  - test_executor
  - test_w4_cc_company 23/23
  - and, from the first pass: test_v11_cc_actions 7/7, test_route_auth_default_deny 7/7,
    test_cc_h_attributes, test_v11_pwa_static 81/0, cc_mock check.mjs 123/0

**Not verified here:** live production gate states. The ledger uses the 2026-10-10 production
reading of the gates that existed then; the new data gates are `unchecked`.
