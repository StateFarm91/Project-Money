# ENG-SEO-PRICE slice 1 — review request

Branch `eng/seo-price`, cut from `origin/claude/w6-INTEG2` @ `64146306`. The final SHA is the
commit that adds this file (see the `[ENG-SEO-PRICE]` comment on #28). Builder only: nothing
merged, deployed, published or spent. Production was read only through Railway deploy logs
(one filtered query; nothing useful in it). No production database, token or secret was
touched.

Slice 1 covers all four parts of the brief at the level of engine plus chain wiring. Slice 2
items are listed at the end.

## 1. The taxonomy snapshot path (production "search: FAIL, category UNKNOWN")

**Root cause, from the code.** I could not read production's audit rows: they need the ops
token, and the readback token is unset. The diagnosis below is therefore from the code. It is
consistent with the 2026-10-21 refresh evidence (one snapshot, `new_snapshot: false` every
day):

1. `taxonomy_drift.after_refresh` runs **only when a refresh stores a new snapshot**. The
   snapshot that first carried the Patterns & Blueprints schema was diffed once. Every later
   daily refresh confirms the same hash and never looks at the profiles again.
2. On that one run the re-queue switch (`BRAMBLELOOP_TAXONOMY_DRIFT_REQUEUE`) is off by
   default. That run held an **UNKNOWN** profile (never certified, never publishable) for the
   owner, exactly as it holds a CHOSEN listing whose certified node drifted. Nothing
   re-decided it.

So a profile computed before the schema was read stays UNKNOWN permanently, even though the
stored snapshot would now CHOOSE a node for it.

**Fix: `integrations/taxonomy_drift.backfill_unknown`**, called from
`handle_taxonomy_refresh` on every refresh that ran, whether or not it stored a new snapshot.
It selects each newest profile that:

- is not CHOSEN,
- is not bound to the newest snapshot, and
- has a category the newest snapshot now CHOOSES.

Each such profile gets one `listing.seo` with **`fix_only: True`**, once per snapshot (token
`catfill<id>`).

- The W6 FIX-ONLY primitive ends at the listing. It never reaches `launch.plan` or
  `store.publish`, and it never alters a live listing. That is why it needs no owner switch:
  review F-1's concern (an Etsy-side change driving an Etsy write) cannot arise.
- A CHOSEN profile is never touched here; drift still owns it.
- The refresh's job output and audit report the result as `category_backfill`
  (`queued` / `skipped` with reasons).
- The autonomy map is regenerated through its module and gains one edge:
  `taxonomy_drift.py:backfill_unknown -> listing.seo`.

**What this does not prove:** that production's stored Patterns & Blueprints schema offers
"Crochet". If it does not, `choose` still returns UNKNOWN with that reason, which is correct.
The backfill then reports it in `skipped`, and the next production refresh row says which
case holds.

## 2. SEO from the research shelf (`commerce/market_fit.py`)

- **Evidence.** `research_listings` reads `BenchmarkListing` rows of the nine
  `scan_evidence.OWNER_SHOPS` only: title, tags, price, pod and size range. It never reads a
  description, chart or photo. Shops outside the nine are excluded (tested).
  `keyword_evidence` ranks tag phrases by the number of **shops** using them.
- **Originality.** `originality` / `overlap` refuse any of three things:
  - a verbatim title, after normalisation;
  - a shared run of more than 4 tokens that contains 2 or more non-generic words;
  - a word-trigram Jaccard of 0.5 or more, counting only trigrams that carry a non-generic
    word.

  Generic category vocabulary ("crochet pattern pdf digital download") is never treated as a
  copy.
- **Etsy rules.**
  - Titles: 140 characters; `% : & +` at most once each; at most 3 all-caps words; must
    contain "pattern" (B-409).
  - Tags: exactly 13, each 20 characters or fewer, no duplicates, plus
    `listing_schema.tag_problems`.
  - Materials: an attribute in Etsy-legal characters.
  - Taxonomy: the node comes from `category.choose`; UNKNOWN is a problem.
- **Tags.** `choose_tags` fills to 13 in this order:
  1. the chain's own tags;
  2. shelf phrases that are **true of this product**, meaning every content word is in its own
     facts vocabulary, with no finished-item phrasing;
  3. fact phrases.

  In `listing.seo`, a short tag set is completed this way, and each added tag still passes
  `search.tag_truth` and the diversity check.
- **Above the fold (B-409).** `build_description(fold_facts=...)` adds this sentence to the
  first line: "Skill level: X. Size: Y (or N sizes (...)). Included: two PDFs, one in US terms
  and one in UK terms." `fold_problems` checks that the first 420 characters say what it is,
  that it is a pattern and not a finished item, the size(s), the skill level, and US+UK PDFs.
- **Gate integration.**
  - `listing.seo` runs `seo_package`. Any `TITLE_*` or `FOLD_*` problem, including
    `TITLE_COPIES_COMPETITOR`, blocks the draft.
  - The search certificate gains a `market_fit` check. `release_gates.search_gate` already
    refuses on any failed check, so the readback "search" section fails on a copied title or a
    bad fold.

## 3. Price from the competitor band

- **The band.** `price_band` gives the quartiles (inclusive method), median, low and high of
  the research listings in the same pod. Graded pods (garments, hats) narrow to the same size
  range when 5 or more listings from 2 or more shops still qualify, and otherwise widen and
  say so. Below 5 listings or 2 shops the band is UNKNOWN, and no price is invented.
- **The price.**
  - `complexity` scores 0..1 from rows, sizes and colourwork, with weights 0.4, 0.35 and 0.25.
  - The target is `Q1 + score x (Q3 - Q1)`, then charm-priced to the nearest x.99 inside the
    band.
  - `pricing.decide_price` then applies its net-contribution floor and measured price points
    (B-201).
  - The result is checked to lie inside [Q1, Q3], and is refused otherwise.
- **The chain.** In `pricing.position` (non-Launch-0), a MEASURED band replaces the static
  `CATEGORY_BANDS_CAD` band.
  - A price outside it is refused with `OUTSIDE_EVIDENCE_BAND`.
  - `pricing.positioned` carries `market_fit`: the band, its listing refs, the complexity, the
    charm reason and `was_price: None`.
  - An UNKNOWN band keeps the static band, and the record says "static category band (no
    research-shelf evidence)".
  - Launch-0 prices stay on the owner-reviewed plan. The research band is recorded beside the
    plan price (`within_research_band`) but not applied.
- **B-376.** `discount_problems` refuses each of these:
  - a was-price never charged;
  - a was-price at or below the current price;
  - any flagship discount;
  - discounting on more than a third of live days.

  Charm pricing is allowed.

## 4. Learning hook

`eng/learn` has not landed (no such branch on origin), so this uses the interface that is
already live: `improve.bus` and `improve.consume`.

- `record_choice` writes every SEO and price choice as a `market_fit.choice` audit row: tags
  with provenance, originality verdict, band evidence.
- `learn(db, slug)` reads `ListingOutcome` rows with provenance **`real`** only.
  - It needs 100 or more real visits per price point.
  - It publishes a `pricing_response` lesson (the best contribution per visitor) and a
    `search_language` lesson (tags kept by favourites). Both are idempotent on evidence.
  - `listing.seo` already reads `seo_search` lessons through `consume.matching`.
  - `outcome_points` gives `decide_price` its contribution-per-visitor price points.
  - Synthetic rows teach nothing (tested).
- `price_arms` allows at most 2 arms. The variant stays inside the band, is at least 8% and at
  most 10% from the control, and is omitted when the band cannot hold one.

## Tests

`tests/test_eng_seoprice.py`: 23/23.

Covered:
- no competitor title copied (verbatim, run, rearranged), and generic overlap allowed;
- 13 true tags, ranked by evidence;
- finished-item phrases refused;
- title, materials and fold rules;
- certificate `market_fit` check;
- band quartiles; thin shelf UNKNOWN and no price invented;
- price inside the band with evidence, reasons and charm;
- graded size range;
- B-376 cases;
- learning: synthetic ignored, real lessons, bounded arms;
- **the taxonomy path end to end.** The real chain drafts the coaster UNKNOWN. A refresh under
  the pre-fix code stores the deciding snapshot, and the profile stays UNKNOWN. The next
  refresh stores no new snapshot, yet the profile is backfilled fix-only (no `launch.plan` or
  `store.publish`) to CHOSEN, and a third refresh queues nothing.

Mutation checks:
- overlap thresholds disabled: copy accepted;
- `GENERIC` emptied: generic overlap becomes a copy;
- band minimum of 1 observation: thin shelf accepted;
- 1 shop allowed: single-shop band accepted;
- band clamp: complexity 3.0 is still inside Q3;
- forged sub-floor band: refused.

Each mutant is killed by the assertion next to it.

Wider suites: see the results section below.

## Results

Run on this branch with `run_tests.sh` (`SUITES=` list below, `JOBS=4`), 2026-11-20T04:21Z to
04:46Z, run record `artifacts/suite_runs/20261120T042106Z-2677.json`. **587 passing, 2 suites
failing, 0 environment failures.** The run is not release-eligible: the tree was dirty, and
HEAD moved to cb8faaf partway through.

| Suite | Result | Note |
|---|---|---|
| `test_eng_seoprice` | 22/23 in the wide run; **23/23 after the fix** | The wide run caught a real reporting defect. A backfill re-run that was still pending was re-reported as `queued` on the next refresh. The enqueue was deduped, but the report was wrong. Fixed: a re-run already queued or done for this snapshot is reported under `skipped`. A fourth refresh in the test now pins this. |
| `test_w6_listing_chain_e2e` | 3/6 | **Pre-existing.** Identical 3 failures on untouched base 64146306 (run in a separate worktree): the test expects one `cir.draft`/`gate.certify`/`store.publish` job, and the chain now drafts 8. |
| `test_w4_fmbatch1_drift` (run separately; not in the name filter) | 6/10 | **Pre-existing.** Identical 4 failures on base 64146306: its `_profile` helper expects one search profile, and the chain now drafts 6. |
| every other suite in the list | green | Includes `test_w4_listready`, `test_first_listing_doors`, `test_w4_resume_runner`, `test_v11_autonomy_timeline` (map regenerated with `python -m brambleloop.autonomy.map --write`), `test_vacuity`, `test_w4_firstsale_taxonomy` 7/7, every `seo`/`search`/`taxonomy`/`price`/`listing` suite, and compiler/reverse/twin. |

Suites run (58):
`test_cert_listing_frames test_codex_a1_listing_child test_eng_seoprice test_first_listing_doors test_k3_listing_outcomes test_k8_listing_estate test_launch0_listing_truth test_listing_parity_gate test_listing_schema test_listing_set test_listing_tests test_opus2_listing_package test_r2_product_listing_writes test_r2_product_seo_unicode test_r5_research_2 test_r5_research_3 test_r5_research_4 test_search_certificate_integrity test_search_hero_publish test_search_truth test_search_visibility test_v11_seo_cycle test_v11_seo_proposals test_v11_seo_taxonomy test_v11_seo_truth test_w3_k1_search test_w3_seo_constraints test_w3_seo_learning test_w3_seo_strategy test_w4_adopt_manual_listing test_w4_c09_seo test_w4_c12_search_visibility test_w4_cap1_placemat_price test_w4_firstsale_taxonomy test_w4_fmbatch1_pricing_trial test_w4_fmbatch1_research test_w4_fmbatch1_research_run test_w4_fmbatch1_search_strategy test_w4_fmbatch2_research_docs_absent test_w4_fmgate_taxonomy_refusal test_w4_listing_memory test_w4_placemat_reprice test_w4_prodready_taxonomy test_w4_research test_w4_research_agent test_w4_research_to_product_stall test_w4_seo_packages test_w4_visualseo test_w5_a4a_research_to_concept test_w6_listing_chain_e2e test_ws2_research_m2 test_w4_listready test_w4_resume_runner test_v11_autonomy_timeline test_vacuity test_compiler test_reverse test_twin`

## Slice 2 (not in this slice)

- Make `market_fit` a *required* search-certificate check. Today it is checked whenever
  present; legacy profiles without it are not refused on its account.
- Bundle structure in the band: bundles keep `decide_price`'s member-total rule. A band built
  from shelf bundles is not yet separated from singles.
- A cadence that runs `market_fit.learn` per live listing when real outcomes land.
- A Command Center panel for the `market_fit.choice` evidence.
