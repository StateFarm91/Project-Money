# SEO / keywords / taxonomy / search intelligence — audit (v1.1 lane G)

Date: 2026-10-06 (UTC). Base: `claude/visual-investigation` @ 0694fb7. Scope: directive v1.1 §11
("SEO / keywords / search — operate it continuously"), Master §F-001..F-026, F-248/F-280,
#237/#293, F-918 (KPI anti-gaming), F-929 (no hallucinated action).

Method: read every module that decides or measures search (listed below), traced each decision
to the evidence it reads, and checked the scheduler (`runtime/worker.py` CADENCES) for what
re-runs it. Nothing below is claimed from a docstring alone; the "re-runs" column is what the
scheduler actually enqueues.

## 1. What exists (pre-lane), and whether it is continuous

| Decision / reading | Code | Evidence it reads | Basis | Re-runs? |
|---|---|---|---|---|
| Listing title | `commerce/seo.py build_title` (called by `runtime/release.py listing.seo`) | CIR title, category, identity qualifiers | product facts | **One-shot** per release; `chain.rebuild` (hourly) re-drafts only on a chain-version/release-hash change, never on new search evidence |
| 13 tags | `commerce/search.py build_query_set` + `choose_tags`, `release._diversify_tags`, `release._drop_vanity_tags` | `_TEMPLATES` hand-set demand/competition; `intent.listing_language` (benchmark titles, keywords table, SERP density); lesson inbox; latest Stats export (`operating_readings` kind `attribution.stats`) | template = **modelled** (labelled `assumed`, F-020); observed phrases labelled `observed:`; Stats export = **measured** (owner-exported, shop-level) | **One-shot** at draft time. New Stats/Insights evidence does not re-open an existing draft |
| Tag truth | `search.tag_truth` / `tags_truth` (difficulty, finished-item phrasing); `first_customer.product_type_findings` / `colourwork_findings` (PT-01); `portfolio.stuffing`; `seo.check_search_copy` | printed difficulty, CIR | deterministic | At draft time only. **No traceability rule**: a tag word unrelated to any product fact (e.g. a competitor shop name, "knitting") passed unless it hit one of the specific patterns |
| Category (deepest truthful node, F-005/F-006) | `commerce/category.py choose` over `integrations/etsy_taxonomy.latest` | Etsy taxonomy snapshot | **measured** when a snapshot exists; **UNKNOWN** otherwise (no default 66) | Snapshot refresh is **continuous** (`listing.taxonomy_refresh`, daily) but **gated on `etsy_api`** (no successful `etsy.probe` recorded) → never ran; no snapshot exists in any real database |
| Attributes / properties (F-007/F-008) | `search.listing_attributes`, `attribute_truth`; `category.properties_for` | twin colours, difficulty, season | product facts; properties need the snapshot | One-shot at draft |
| Coverage matrix / "search share" | `search.score_coverage` → `Listing.seo_score`, `ListingSearchProfile.coverage_matrix` | template query set | **proxy** (the audit row says `"search_share_basis": "assumed+observed (planning proxy)"`) | One-shot |
| Search certificate (F-004) | `search.search_certificate`, `release_gates.search_gate` | all of the above + hero judgement | deterministic | Re-checked at publish (staleness via fingerprint) |
| Search Visibility (F-248/F-280) | `commerce/search_visibility.py`, `runtime/storefront_watch.py` | owner readings | first-party, owner-recorded | Daily watch cadence; intake refuses while `live_listings` is closed |
| Marketplace Insights (#236/#37) | `intel/insights.py` | owner-recorded Shop Manager figures | measured-by-Etsy, owner-read | On owner entry only |
| SERP laboratory (#15) | `intel/serp.py` → `serp_snapshots` | API `findAllListingsActive` sorted by score | measured *supply in the API index*; rank is directional | When a reader/credential exists (none demonstrated) |
| Keyword outcome / vanity terms (#237) | `commerce/attribution.py parse_stats_csv`/`join_stats`; `POST /api/attribution/stats` | owner Stats CSV | measured, **shop-level** (a term is not split by listing) | On owner upload only; no upload has happened (shop not live) |
| Listing outcomes | `listing_outcomes` table (written by commerce readers once live) | Etsy Stats/API per listing per period | measured | No rows: no live listing |
| `keywords` table | `core/models.Keyword`; read by `intent.observed_phrases`, `improve/measure.measure_seo_search` | `est_demand`/`est_competition` | **no recorded provenance** → treat as modelled | No writer found in `src/` |
| Etsy surfaces registry | `intel/etsy_surfaces.py` | Etsy OpenAPI absence probes | sourced | Static: there is **no** Etsy API for shop Stats, Marketplace Insights or Search Visibility (counted absences: "stats" 0, "insight" 0, "seo" 0) |

Taxonomy ids: `2112` (Blankets & Afghans), `2114` (Coasters), `2115` (Baskets & Storage) appear
only in `tests/fixtures_etsy_taxonomy.py`, whose docstring says "The ids and names are
illustrative, not Etsy's". No Launch-0 category id has ever been read from Etsy.

Etsy field limits as the repo records them: `commerce/seo.py` TITLE_MAX=140, TAG_MAX_CHARS=20,
TAG_MAX_COUNT=13; `commerce/search.py` TAG_SLOTS=13, TAG_MAX_CHARS=20, TITLE_MAX=140;
`publish/listing_schema.py` (SOURCED from Etsy's OpenAPI document, read 2026-09-24) "140-character
title, 13 tags of 20 characters" plus title/tag character-set rules.

## 2. Gaps against §11 (before this lane)

1. **Not continuous.** No scheduled job re-evaluates titles/tags/attributes when evidence
   changes. Evidence intake paths exist (Stats CSV, Insights, SERP) but nothing closes the loop
   back to existing drafts.
2. **No keyword evidence store with provenance.** Evidence is spread over five tables with
   different basis conventions; the template phrases' constants are labelled `assumed` only
   inside the in-memory `Query` objects.
3. **No traceability guardrail (F-918).** Truth checks were pattern-specific; a tag word with no
   product fact behind it, or a competitor shop name, was not rejected as such.
4. **No taxonomy readiness view.** Category status was only visible per release, inside
   `ListingSearchProfile`.
5. **No per-keyword attribution** with stated confidence; vanity-term logic existed only inside
   the release handler.
6. **No SEO provider** for the Owner Command Center / orchestrator.

## 3. What lane G built (`src/brambleloop/seo/`)

| Requirement | Module | Status |
|---|---|---|
| Keyword evidence store with provenance + basis (measured / observed / modelled / unknown; `use` says when a measured count is used as a proxy) | `seo/evidence.py`, `seo/models.py` (`seo_keyword_evidence`) | Built; idempotent by content fingerprint |
| Truthful-tag validator (traceable to CIR / verified facts; rejects stuffing, competitor names, third-party brands, protected IP, misleading claims; Etsy limits) | `seo/facts.py`, `seo/truth.py` | Built; reuses `search.tag_truth`, `seo._UNSUPPORTABLE`, `gates.policy`, `first_customer`, `portfolio.stuffing`, `listing_schema` |
| Title/tag/attribute proposals for Launch-0 drafts (never written to Etsy) | `seo/proposals.py` | Built; diff + audit vs the current `listings` row when one exists |
| Taxonomy readiness (CONFIRMED vs GATED(etsy_api) / PENDING_REFRESH / UNRESOLVED) | `seo/taxonomy.py` | Built; CONFIRMED requires an Etsy-read snapshot (`source=etsy_open_api_v3` and `confirmed_at`, which only `refresh` sets) |
| Continuous job, idempotent | `seo/jobs.py run_cycle`, `seo/handler.py` (`seo.cycle`) | Built; scheduling needs WIRING (handoff_G.md) |
| Measurement hook (per-keyword attribution, honest confidence, UNKNOWN when none) | `seo/measure.py` | Built; confidence capped at `moderate`; listing outcomes never split across tags |
| Provider `summary(db)` + `next_work(db)` | `seo/status.py` | Built; contract documented in module docstring |

## 4. Measured vs proxied, after this lane (current real state)

- Every Launch-0 tag's demand basis is **modelled** (template constants). The runtime proof
  (`evidence/G_seo_cycle_proof.json`) shows 42 phrases, all `modelled`, 0 measured, 0 observed.
- Every Launch-0 category is **GATED(etsy_api)** (5 of 5 variants).
- Keyword outcomes are **UNKNOWN**: no Stats export ingested, no `listing_outcomes` rows.
- The coverage "search share" remains a **planning proxy** and is not reported by this package
  as a KPI.
- What would turn modelled into measured: an `etsy.probe` success (opens `etsy_api` → taxonomy
  refresh → CONFIRMED categories, SERP supply counts); owner Marketplace Insights entries
  (measured demand, owner-read); and, once the shop is live, the owner's Stats CSV
  (measured shop-level term outcomes). `run_cycle` picks each up on its next run with no code
  change, and re-issues only the proposals whose inputs changed.
