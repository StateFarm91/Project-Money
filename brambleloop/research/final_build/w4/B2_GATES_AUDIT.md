# W4-B2GATES: audit of the 102 gated Build 2 rows (54 owner-gated, 41 data-gated, 7 external)

Date: 2026-10-11 (UTC). Branch `claude/w4-B2GATES`, from `origin/claude/w4-NEXTREL` b34c968.

**Ledger used.** The authoritative copy is `research/final_build/w4/BUILD2_LEDGER.json`. It was
last written by 846dbcb (W4-B2VERIFY, 2026-10-10T03:26Z), and every lineage carries that same
commit (B2CLOSE, B2VERIFY, PACKETREL, NEXTREL). That JSON is older than the B2CLOSE code fixes, so
I recomputed the ledger from the current registry and code with `build2.closure.ledger(db)`. The
gate states came from a fresh local database, so every gate was closed. The result was the same
215 / 54 / 41 / 7 / 3 / OPEN-DEFECT 0, before and after this lane's changes. The per-row machine
output is in `B2_GATES_AUDIT.json`.

**No row was reclassified, and no requirement was created.**

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

## Remaining (reported, not changed here)

- **R1. Stale executor gate-table entries, #94 and #140.** The registry says both rows are
  data-gated, needing traffic and a sale for #94 and listings accumulating over time for #140.
  The ledger agrees. But `executor._GATE_FOR_REQUIREMENT` still lists #94 under `model_provider`
  and #140 under `culture_feed`, and `approval_inbox` uses that table to compute what a card
  unblocks. As a result, the **model_provider owner card claims to unblock #94, which no model
  can unblock**. culture_feed is already listed as company-opened, so it is not an owner ask.
  - Not fixed here. Removing #94 suppresses the model_provider card, and
    `tests/test_cert_dashboard.py::test_a_legacy_row_for_a_closed_gate_merges_into_its_card_rather_than_duplicating`
    uses that card as its fixture.
  - Owner-queue lane: drop #94 and #140 from the gate tuples. The fund_model decision stays
    genuine through `image_vision`. Then re-point that test at `image_vision`.
- **R2. The remaining 6 unnamed data gates, #23 #82 #89 #98 #296 #298 (8 counting #94 and #140
  from R1).** These are registry `data_gated` rows, and the ledger shows them with gate `—` and a
  generic "customers, orders or traffic". The precise data need is in each registry note and in
  the table below, but nothing machine-readable records it. The registry forbids `parked_on` on
  data-gated rows, so naming these gates in code needs a registry or closure schema change, for
  example a `data_need` field. Each gate is genuine and the machinery exists and is reached.
- **R3. #35 and #39 are classed EXTERNAL-GATED, but the gate now also opens on a person's
  reading.** That path was fixed in B2CLOSE: `rendered_pages` opens on `POST /api/policy/snapshot`
  by a named person. In practice the remedy is a human task, the OWNER_ACTIONS
  `policy_page_reading` decision (about 15 minutes every 30 days), not an external provider. The
  classification is left as it is: reclassifying needs the closure lane's ruling.
- **Not verified here:** production gate states. Every gate was read as closed on a fresh local
  DB. Production `/api/build` was not read in this lane.

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
| 23 | Numeric Scale/Kill Framework | DATA | — | buyers/time (registry data_gated) | data accrues: per-listing traffic, CTR, conversion and support load (live listings + orders) | yes (kill_table.py; 1 test refs) | genuine; named in registry note only → R2 |
| 25 | $3K Run-Rate Decomposition | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (runrate.py, weekly.py; 5 test refs) | genuine; company side wired |
| 28 | Conditional Scale Rules | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (runrate.py, readiness.py; 5 test refs) | genuine; company side wired |
| 31 | Cost-to-Create and Profitable Throughput | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (unit_cost.py, governor.py; 3 test refs) | genuine; company side wired |
| 33 | Replace the narrow Christmas Strike Team with a  | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (engine.py, daily.py; 7 test refs) | genuine; company side wired |
| 35 | Etsy Creativity / AI Disclosure Gate | EXTERNAL | rendered_pages | a named person reads etsy.com/legal (or a working browser) | POST /api/policy/snapshot / intel.browser.probe | yes (platform_policy.py; 4 test refs) | genuine; company side wired |
| 37 | Marketplace Insights Query Budgeter | OWNER | insights_access | owner (reads Shop Manager Insights) | POST /api/insights/snapshot → intel.insights.record → InsightsSnapshot | yes (insights_budget.py, executor.py; 3 test refs) | genuine; company side wired |
| 39 | Policy Freshness Watch | EXTERNAL | rendered_pages | a named person reads etsy.com/legal (or a working browser) | POST /api/policy/snapshot / intel.browser.probe | yes (platform_policy.py; 3 test refs) | genuine; company side wired |
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
| 82 | Creative Performance Learning | DATA | — | buyers/time (registry data_gated) | data accrues: ≥200 impressions per style and ≥3 listings with sourced outcomes | yes (style_learning.py; 3 test refs) | genuine; named in registry note only → R2 |
| 86 | Creativity Benchmark Memory | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (vision.py, mechanisms.py; 4 test refs) | genuine; company side wired |
| 88 | Idea-to-Thumbnail Test | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (concept.py, preengineering.py; 4 test refs) | genuine; company side wired |
| 89 | Creativity Outcome Learning | DATA | — | buyers/time (registry data_gated) | data accrues: ≥3 concepts per attribute value, 200 visits, 20 orders | yes (outcome_learning.py; 3 test refs) | genuine; named in registry note only → R2 |
| 94 | Creativity Capability Scorecard | DATA | — | buyers/time (registry data_gated) | data accrues: market CTR, conversion and winner rate (live traffic + a sale) | yes (blinded.py; 1 test refs) | genuine data gate; stale gate-table entry (model_provider) → R1 |
| 98 | External Learning Radar | DATA | — | buyers/time (registry data_gated) | data accrues: a craft-technique source and customer-pain data (search half already fed) | yes (learning.py, serp.py; 4 test refs) | genuine; named in registry note only → R2 |
| 116 | Creative Reference Decomposition | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (reference.py; 2 test refs) | genuine; company side wired |
| 120 | Holiday-to-Holiday Learning Transfer | DATA | customers | a buyer (real orders) | orders ingest (commerce.orders_ingest) → LedgerEntry with evidence_ref | yes (discovery.py, ideation.py; 4 test refs) | genuine; company side wired |
| 126 | Search-Grid Blind Tournament | OWNER | image_vision | owner (fund a vision-capable model) | ops.capability_probes → gateway.anthropic.vision_probe | yes (board.py, blinded.py; 6 test refs) | genuine; company side wired |
| 130 | Model-Led Brand Storytelling | EXTERNAL | model_bearing_render | external (provider must render a certified structure) | daily assets.model_photography handler → audit rows | yes (identity.py, model_photography.py; 4 test refs) | genuine; company side wired |
| 140 | Cultural Demand Lead-Lag Model | DATA | — | buyers/time (registry data_gated) | data accrues: listings discovered over time by the scanner (≥4 matched; accumulates by itself) | yes (feeds.py, demand.py; 2 test refs) | genuine data gate; stale gate-table entry (culture_feed) → R1 |
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
| 296 | Seasonal Revenue War Room | DATA | — | buyers/time (registry data_gated) | data accrues: seasonal revenue, run rate and ad learning (orders during a season) | yes (leadtime.py; 3 test refs) | genuine; named in registry note only → R2 |
| 298 | Post-Season Learning Harvest | DATA | — | buyers/time (registry data_gated) | data accrues: a passed seasonal event with ≥20 orders | yes (harvest.py, leadtime.py; 4 test refs) | genuine; named in registry note only → R2 |
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

- New: `test_w4_b2gates` 7/7.
- Existing, all passing:
  - test_v11_cc_actions 7/7
  - test_w4_owner_actions 6/0
  - test_route_auth_default_deny 7/7
  - test_w4_gatesb 10/0
  - test_closure 27/0
  - test_cc_h_attributes 6/0
  - test_v11_pwa_static 81/0
  - test_cert_dashboard 18/18
  - test_build2 (pass)
  - cc_mock check.mjs 123/0
