# ENG-BENCHBUY: review request (benchmark shopping list across the nine watchlist shops)

- Branch: `eng/benchbuy`, created from `origin/claude/w6-INTEG2` @ `809107b5` (no earlier `eng/benchbuy` existed).
- The final SHA is the commit that adds this file; it is given in the issue #28 comment, tagged `[ENG-BENCHBUY]`.
- Not deployed. Not merged. Nothing touches Railway, production, secrets, Etsy writes, spend, `BRAMBLELOOP_PHASE` or `STAGE_A_ENABLED`. `claude/repository-setup-nc9x6o` was not pushed to.
- `sw.js` is untouched, so `VERSION` stays as it was (`cc-shell-v33` on this base). The panel lives in the existing `insights.js`, which is already in the shell list.

The owner's ask: benchmark patterns to buy, with variety from each of the nine shops scanned daily; MadelineMaeCo, baby products, stuffed animals/amigurumi and pillows are "huge hits".

## What was built

1. **Selection** (`intel/purchase_selection.py`, `shopping_list`). `select()` and the MJs approved set are unchanged.
   - Same design: greedy facet coverage, a computed reason per pick, and no pick without a new facet.
   - Catalogue: the scanned `BenchmarkListing` rows of all nine watchlist shops, pattern digital downloads only.
     - Digital means the API's own `options.listing_type == "download"`.
     - An unobserved type is `digital_status_unknown` and excluded. It is never assumed to be a download.
     - A pattern word (pattern, pdf, tutorial, ebook, chart) is also required in the title or tags.
   - Quota: 3 per shop, 5 for MadelineMaeCo.
   - Rank order:
     1. Capability-gap facet (in-the-round, colourwork chart, mosaic/tapestry, granny/motif, garment grading, amigurumi, flat). Covered once for the whole company.
     2. Owner-demand facet (baby, stuffed animal/amigurumi, pillow/cushion). Covered once per shop.
     3. The shop with the fewest picks so far.
     4. The old facets, then observable depth.
     5. Bestseller and favourites, as a tie-break only.
2. **Budget, in code.**
   - Remaining ceiling = `intake.SET_BUDGET_CAD` (300) minus recorded `BenchmarkProduct.paid_cad`.
   - Every price is checked at ×1.158 and shown beside the listed price. The list total is the contingency total.
   - Money is held back so every shop with an eligible listing gets a first pick before the ceiling is spent. If that cannot be honoured, the plain ceiling check applies.
   - A BenchmarkProduct row with no recorded price is reported as `unknown_price_for`, never counted as CA$0.
   - Owned items are excluded:
     - both MJ benchmarks, matched by title;
     - every BenchmarkProduct row, matched by listing reference or title.
   - Picks already bought stay on the list as `bought`, or `intake done` once files exist. They still count toward the quota and the coverage, but are not charged again.
3. **Daily refresh** (`benchmark_refresh.refresh_shopping`, job `intel.benchmark_shopping`).
   - Cadence 24 h, in `FREE_JOB_TYPES`, upstream inputs `intel.watchlist_scan` and `mjs.scan`, so it runs after the scans.
   - `work_done` is 1 only when the to-buy set changed. An unchanged day therefore backs off through the existing thrash/backoff; a real scan lifts it.
   - Wired in: worker cadence, handler (`runtime/intel_ops.py`), pipeline outcome keys, authority class, agent registry, priority family. `autonomy_map.json` regenerated (143→144 cadences, 175→176 handlers).
4. **Mission Control.**
   - Insights tab gets a "Benchmark shopping list" panel grouped by shop. It sits right after the marketing & customers view (F-622 is preserved).
   - Each pick shows the title, the Etsy URL (`https`, `noopener`), the CA$ price and the ×1.158 figure, what it teaches, why, and its status.
   - Every shop is shown with a status:
     - PICKED;
     - EMPTY, with a counted reason;
     - UNKNOWN, when no scanned listings exist.
   - ONE consolidated owner card, "Buy N benchmark patterns, ≤ CA$X". The key is `benchmark_shopping:set`. It is restated in place, and closed when nothing is left to buy or the scan data is missing.
5. **Safety.**
   - Nothing buys. The module makes no request and has no purchase path.
   - The panel has no control: no button, form or POST.
   - Metadata only. No competitor content is read or stored.
   - Purchased PDFs go only through `teardown.intake.receive`, into the quarantined library (B-117).
     - That function now accepts a listing from any watchlist shop.
     - The folder is `<shop key>-<listing id>` and the seller is recorded. Mrs J keeps `mjs-<id>`.

## Tests

- New `tests/test_benchbuy.py`: 17 tests, all passing.
- New check in `tests/fixtures/cc_mock/check.mjs`, with a `benchmark_shopping` fixture section: the panel groups by shop, shows the URL, price, contingency, teaches, why and status, shows an empty shop's reason, and has no buy control.
- Covered:
  - variety from all nine shops and the quotas (3, and 5 for MadelineMaeCo);
  - the quota binding with 30 listings in one shop;
  - no pick without a new facet;
  - gap before demand before favourites;
  - digital and pattern eligibility;
  - the budget never exceeded at ceilings 300, 120, 40, 7 and 0;
  - recorded spend coming off the ceiling;
  - owned exclusion and the bought / intake-done statuses;
  - an empty shop's visible reason;
  - UNKNOWN with no scan data and no card raised;
  - one owner card, quiet on a second day;
  - the card closing;
  - the loop registered daily, free, after the scans;
  - no purchase path, with the network switched off;
  - a purchase from another shop entering only through the quarantined intake;
  - the Insights read model.
- Mutants killed (7 of 7): quota off, budget check off, owned filter off, new-facet rule off, digital filter off, contingency 1.0, favourites-first ranking.
- The tests found and I fixed one real bug before commit: `tabs.benchmark_shopping` used the wrong relative import, which the panel's `guard` would have turned into a silent UNKNOWN in production.
- Required suites, run on this branch:
  - `test_v11_pwa_static`: 84 passed, 0 failed.
  - `test_v11_pwa_browser`: 234 passes, 0 failures.
  - `test_s4_p0_board`: 0 failed.
  - `test_route_auth_default_deny`: 8/8.
  - `test_w4_resume_runner`: passes.
  - `test_v11_autonomy_timeline`: 0 failing, committed map matches the generator.
  - `test_purchase_selection` and `test_intake`: pass.
- Regression runs of the wider wiring suites are listed in the issue comment. A full, uninterrupted certification run was NOT done here.

## What is UNKNOWN (not claimed)

- This checkout has no production database, so how many picks, which shops, and what total the real list yields are UNKNOWN until `intel.benchmark_shopping` runs on production after the next scans.
- Whether every shop's stored listings carry `options.listing_type` is UNKNOWN. Listings scanned before that field was stored are excluded and counted `digital_status_unknown`, so a shop could read EMPTY until its listings are re-read.
- The gap and demand keyword sets are metadata heuristics over title, tags and pod. They are not a judgement of the PDF. Reviewers should read `GAPS` and `OWNER_DEMAND`.
- The one open design choice: a BenchmarkProduct row with no recorded price is not charged against the budget (the owner's ask was "recorded spend"). It is disclosed as `unknown_price_for`.

## Where to look

- `intel/purchase_selection.py`: from the "ENG-BENCHBUY" banner to the end.
- `intel/benchmark_refresh.py`: `refresh_shopping`.
- `runtime/intel_ops.py`: `handle_benchmark_shopping`.
- `app/command_center/tabs.py`: `benchmark_shopping`.
- `app/command_center/static/js/views/insights.js`: `shoppingPanel`.
- `teardown/intake.py`: `_catalogue_row` and `receive`.
- `DECISION_LOG.md`: D-OWNER-BENCHBUY.
