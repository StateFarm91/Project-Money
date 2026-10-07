# W4-SEO handoff: Etsy search packages for every product

Branch `claude/w4-SEO` (base `claude/visual-investigation` fee1cfe). Latest pushed SHA: see `git log -1 origin/claude/w4-SEO`.

## Owned / touched
- NEW `src/brambleloop/seo/packages.py`: assemble, record, refresh, current, history.
- `src/brambleloop/seo/models.py`: new table `SeoSearchPackage` (`seo_search_packages`). `core.db.create_all` already imports `seo.models`.
- `src/brambleloop/seo/jobs.py` and `seo/handler.py`: `run_cycle` calls `packages.refresh`, which is the post-launch update loop.
- `src/brambleloop/commerce/search_evidence.py`: the summary carries `search_package`. The `truthful_query_coverage` rung is never PASS without a current package bound to the listing. This change only tightens the rung.
- `src/brambleloop/runtime/release.py`: one additive try-block in `listing.seo` (producer) that calls `seo.packages.record_from_release`. It never blocks. **PIPE lane note:** a surgical additive edit near `_judge_search_hero`.
- NEW `tests/test_w4_seo_packages.py`.
- NEW `research/final_build/w4/seo_packages_build.py` → `SEO_PACKAGES.json` / `SEO_PACKAGES.md`.

## Status
See the final report and `SEO_PACKAGES.md` for counts.

## Next deterministic action (if resuming)
1. `PYTHONPATH=src python tests/test_w4_seo_packages.py`
2. `PYTHONPATH=src python research/final_build/w4/seo_packages_build.py`
3. Run the focused tests: test_v11_seo_cycle, test_w3_k1_search, test_search_truth, test_launch0_listing_truth, test_vacuity, test_secret_scan, test_reachability, test_w3_tmp_hygiene.
4. Commit and push.

## Gates (not executable by the company)
- EXTERNAL-GATED: Etsy seller-taxonomy read needs the app keystring (`ETSY_KEYSTRING`). Until that read happens, every category is UNKNOWN and the certificate's category and attributes checks fail.
- DATA-GATED: no listing is live, so all learning signals are UNKNOWN. The loop is proven with fixture data only.
