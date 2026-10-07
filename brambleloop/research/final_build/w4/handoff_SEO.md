# W4-SEO handoff: Etsy search packages for every product

Branch `claude/w4-SEO`. Base: `claude/visual-investigation` fee1cfe, merged with `origin/claude/w4-INTEG` 7631026 (MJS findings). Latest pushed SHA: see `git log -1 origin/claude/w4-SEO`.

## Owned / touched
- NEW `src/brambleloop/seo/packages.py`. It assembles, records, refreshes and reads packages (`current`, `history`). It also provides:
  - `competitive_findings`, which reads the MJS benchmark findings from the stored `mjs.findings` reading.
  - `sync_keywords`, which writes `Keyword` rows (W4L-1).
- `src/brambleloop/seo/models.py`: table `seo_search_packages`.
- `seo/jobs.py` and `seo/handler.py`: `run_cycle` calls `packages.refresh`. This is the post-launch update loop.
- `commerce/search_evidence.py`: the `truthful_query_coverage` rung needs a CURRENT package that is still bound to the listing.
- `runtime/release.py`: `listing.seo` calls `record_from_release`. The edit is additive and never blocks.
- W4L-1 reader guards. These are surgical one-line filters on `Keyword.intent` starting with `package:`:
  - `seo/evidence.py`: no `est_demand` for package rows.
  - `commerce/intent.py`: `package:modelled` phrases are not counted as observed market language.
  - `intel/insights_budget.py`: package rows are not counted as query snapshots on file.
- Tests: `tests/test_w4_seo_packages.py`, 6 tests: producer→consumer, certified fixture branch plus staleness, MJS findings, W4L-1 measurable cell, search evidence, and the Stats update loop (FIXTURE).
- `research/final_build/w4/seo_packages_build.py` writes `SEO_PACKAGES.json` and `SEO_PACKAGES.md`. It runs the real chain over 21 CIR products, with the MJS reading seeded and PIPE inventory statuses alongside.

## Status (SEO_PACKAGES.md)
- 21 products have a CIR. 7 are viable (Product Truth clean).
- 17 packages exist. Certificate: 0 PASS, 17 REFUSED.
- 5 are EXTERNAL_GATED: cloudline-baby-blanket, hexagon-coaster-set and market-basket-small, -medium and -large. For these the taxonomy read is the only failing input.
- 2 viable products are BLOCKED on the hero image (company imagery work): harvest-table-runner and pet-snuggle-mat.
- Every packaged price is below the benchmark seller's observed p25. This is evidence for pricing; nothing was changed here.

## Gates
- EXTERNAL-GATED: the Etsy seller-taxonomy read needs `ETSY_KEYSTRING`. The `category` and `attributes` certificate checks fail until it happens.
- DATA-GATED: no listing is live, so all learning signals are UNKNOWN. The update loop is proven with fixture data only.

## Wiring requests
- PIPE / imagery: hero imagery for harvest-table-runner and pet-snuggle-mat.
- Product Truth renames or re-engineering for the 11 not-viable products. This is PIPE's work.

## Resume
`PYTHONPATH=src python tests/test_w4_seo_packages.py`, then `python research/final_build/w4/seo_packages_build.py`, then commit and push.
