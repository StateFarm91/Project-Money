# LEARNING-APPLY — why benchmark lessons ran thousands of times and never applied

Branch `eng/learning-apply`, from `origin/claude/w6-release-19h17`. Not merged, not deployed. Production is unchanged.

## Evidence (production, 00:00Z 2026-11-22, `learning.benchmark_lessons`)

All 14 of 14 lessons are ingested and wired.

| Department | Applied | Hook runs |
|---|---|---|
| seo_search | 0 | 2536 |
| pattern_engineering | 0 | 1690 |
| creative_assets | 0 | 1268 |
| customer_experience | 0 | 2 |
| pricing | UNKNOWN ("hook has not run since ingestion") | none |

## Root causes (verified in code, and against the real catalogue locally)

The note → flush → `record` mechanism works. The quality department's 22 MM-L7 applications are 11 Launch-0 products × 2 terminologies, all coming through the same buffered PDF path. Applications are recorded correctly when they happen. The zeros have three separate causes.

1. **pattern_engineering: the applicability predicate is never true for the real products.** The four lessons need one of these:
   - an amigurumi family (HC-L4 component grouping, MM-L4 eye options);
   - chunky or chenille yarn (MM-L3);
   - a slip-stitch or pick-up join at a stated round (MM-L2);
   - more than one component (HC-L4).

   I built each of the 11 Launch-0 CIRs (baskets, blankets, coasters, runner, ornaments, placemats). Every one is single-component, has no assembly seams and no chunky yarn, and is family basket, blanket or small_home_goods. No product builder makes amigurumi. So 0 is a true measurement. It was just indistinguishable from a broken hook. `test_no_launch0_product_is_relevant_to_the_pattern_engineering_lessons` pins this down.

2. **seo_search and creative_assets: the hooks sit only on validators downstream of generators that never read the lessons.**
   - MM-L6 (`seo_check`) recorded applied only when a listing made a sew claim, and `build_title` / `choose_tags` never make one. Before this fix, a *true* claim also counted as applied.
   - HC-L7 (`front_load_findings`) applies only to a title that fails the check. But `commerce.seo.build_title` already front-loads "Object | Crochet Pattern PDF" as a base rule (F-021/F-022), so a generated title can never fail.
   - HC-L3 applies only when copy promises photos, which our copy never does.
   - MM-L5 (`scale_brief`) applies only to toy categories, and the catalogue has none.

   So the hooks run on every validation and the lessons are relevant to none of the products.

3. **pricing: the hook sits on a path that does not run.** HC-L1 (`effective_price`) is called only from `intel.serp.capture`, the live SERP capture. That capture is blocked in production by the Etsy read credential (`serp.capture_blocked`), so the hook never runs. Meanwhile the department's real price-research read, `release._outcome_price` (every `pricing.decide` job), took the median of `BenchmarkListing.price_cad`. For a listing observed on sale, that is the strike price.

## Fixes

- **Pricing on its real cadence.**
  - New `benchmark_lessons.anchor_prices`, called by `release._outcome_price` on every pricing job.
  - With HC-L1 stored, an on-sale benchmark row is read at the effective price observed beside it (`detail.effective_price_cad`). If no effective price was observed, the row is left out, because its listed price is a strike price.
  - It records one run per pricing read. It records an application only when a strike price was replaced or dropped, which changes the anchor's inputs.
  - `intel.observe.scan` now stores the payload's effective price when the payload states one below the listed price (`observed_effective_price`, a fact stored whatever lessons are active).
- **SEO MM-L6 on the generator.**
  - `seo.proposals.propose` now asks `earned_sew_tags`. A multi-piece amigurumi whose certified construction really is no-sew or low-sew earns "no sew amigurumi" / "low sew amigurumi", which still has to pass `truth.check_term`.
  - `note_sew_tags` records an application only when the earned tag is in the final tag set.
  - The validator `seo_check` now counts an application only when it *refuses* a claim. A true claim is relevant but changes nothing.
- **Relevance measured separately from application.**
  - `note` / `record` take `relevant` (it defaults to `applied`) and write a `relevant:<hook>:<dept>` count.
  - The readback adds `relevant_runs`. For a measured zero it adds `why_zero`: either "no relevant product" or "relevant, already satisfied, no output changed".
  - A run is never counted as an application. UNKNOWN stays UNKNOWN when the hook has not run.

## Expected production change after deploy

- **Pricing** moves from UNKNOWN to measured on the next `pricing.decide`. It applies only if a benchmark pod holds on-sale rows. Historical rows have no effective price, so on-sale rows are dropped from the anchor rather than read at their strike price.
- **seo_search, pattern_engineering, creative_assets** stay at applied 0 for the current catalogue, and that is correct. `why_zero` will say "no relevant product" until an amigurumi, chunky or multi-piece product exists. Relevance rows start counting only from deploy, so earlier runs have none.
- **Not fixed here:** HC-L7 can only apply to titles that `build_title` did not generate (current or legacy drafts). Its check is weaker than the lesson: it does not check "crochet" or "PDF" within the first 60 characters. I did not strengthen it, because a stricter soft finding would still change no output.

## Tests

`brambleloop/tests/test_learning_apply.py` has 12 tests, each pairing a relevant subject with an irrelevant one:

- **Pricing:**
  - the effective price is read and the run applies;
  - with no sale listing, the hook runs and does not apply;
  - with no lesson stored, prices are read as before;
  - `_outcome_price` runs the hook on the pricing cadence;
  - the observation keeps the effective price beside the listed one.
- **SEO:**
  - a no-sew amigurumi earns the modifier tag and the application is recorded;
  - a sewn amigurumi and a catalogue basket earn nothing;
  - a true claim is relevant but not an application.
- **PDF:** an amigurumi applies MM-L4; a catalogue blanket does not ("no relevant product"); no Launch-0 product is relevant.
- **Creative assets:** hand scale applies to a toy campaign and not to a blanket.

## Suite results (commit a6c01f7, clean tree)

**Run 20261122T002403Z-1082: 26 related suites, including `test_vacuity.py`, `test_learn_proof.py` and `test_learning_apply.py`.** Result: 370 passing, 4 suites failing.

- **Three of the failures came from my local environment:** the venv had an unpinned starlette that wants `httpx2`. These were `test_cert_mjs`, `test_cert_wiring` and `test_fb4_lc`.
- **Rerun with the lockfile's pinned versions** (`test_cert_mjs`, `test_cert_wiring`, `test_eng_daily`, `test_fb4_lc`, `test_ws2_r1_competitor_scans`): 91 passing, 1 suite failing.
- **The one remaining failure is pre-existing:** `test_eng_daily::test_the_job_is_wired_free_and_records_the_ledger` asserts `retention.unknown_read_actions() == []`. It returns the same five entries on the base `origin/claude/w6-release-19h17`, checked in a separate worktree. This change adds no audit action. It is not fixed here.

The full suite was not run.
