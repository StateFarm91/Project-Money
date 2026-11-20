# ENG-NINTH-SHOP — review request

Branch: `eng/ninth-shop`, from `origin/claude/w6-INTEG2` @ `a35ad302`. The final SHA is the
commit that adds this file (see the GitHub comment on #28). Builder only: nothing merged,
deployed, published or spent; no Railway, production or secrets touched.

## The directive

Owner directive 2026-11-19 adds a ninth mandatory research shop. It is **ArtLoveDesing**,
spelled "Desing" exactly as the shop is named.

- Owner-supplied URL, kept verbatim:
  `https://www.etsy.com/ca/shop/ArtLoveDesing?ref=shop_profile&listing_id=4427559824`
- Canonical URL: `https://www.etsy.com/ca/shop/ArtLoveDesing`

The shop is a permanent research source and never a report mention. The decision is
`D-OWNER-NINTH-SHOP` in `DECISION_LOG.md`.

## What changed

| Registry | Change |
|---|---|
| `intel/benchmarks.py` | `ARTLOVE` spec (mandatory, both URLs, `D-OWNER-NINTH-SHOP` reason) in a new `OWNER_ADDED_SHOPS`, appended to `REGISTRY`. No categories or pods are declared: nobody has observed the catalogue, so a pod would be an assumption. |
| `intel/watchlist.py` | A `Member` with role `permanent` is generated from `OWNER_ADDED_SHOPS`. It is scanned by the same `scan_member` (official Etsy Open API v3 public reads) on the `intel.watchlist_scan` cadence. |
| `intel/scan_evidence.py` | The ninth row of `OWNER_SHOPS`, with the owner URL verbatim and role `permanent`. |
| `radar/market.py` | A `COMPETITORS` profile in the IvyLoop shape: band (0, 0), no formats, "Not yet observed". Nothing is claimed about the shop. |

**Monitoring of listings, prices, amigurumi, PDF languages and quality, reviews and trends.**
`watchlist.MONITORING_FOCUS[artlove_desing]` maps each part to the `compare` figures that
answer it, and the comparison carries that map per shop as `monitoring_focus`. Three figures
are new, and they are read for every shop:

- `amigurumi_listings` (DERIVED): pod routing, the count in the amigurumi pod.
- `listing_languages` (MEASURED): findShops `languages`. Language codes only are kept, at
  store time and again at compare time; anything else in the payload is dropped. The PDF is
  never bought, downloaded or opened.
- `pdf_quality` (**UNMEASURED**, value UNKNOWN, with its reason): no compliant source exists.
  Review average and recurring complaint themes stay separate figures and are never relabelled
  as PDF quality.

The other parts are answered by existing figures: listings_observed and new_listings_7d,
price_median_cad and on_sale_share, review_count, review_average and
recurring_complaint_themes, category_mix and public_sales. `SCOPE` gains `amigurumi`,
`pdf_languages` and `pdf_quality`.

**Unreachable shop.** The existing `D-W4-OWNER-SEEDSHOPS` path is reused unchanged:
`_record_not_accessible` records `not_accessible` with a dated limitation, keeps the
monitoring and backs off. The other shops still scan, and `scan_evidence` never lists the shop
as scanned. One honesty fix: `alternative_evidence` and `scan_evidence._seed_observation` now
say "owner-named profile, not yet observed" for a COMPETITORS profile with no band and no
formats. Before, an unobserved profile was cited as a dated "public-profile seed
observation". This also changes how IvyLoop reads, and the IvyLoop test still passes
(`COMPETITORS[IvyLoop]` is still cited). For the same reason, `radar/report.py` prints "No
price band observed yet" for such a profile instead of "Observed <date> at CA$0.00-0.00".

**Counts are now nine, and computed where possible.**
- `ops/readback.py`: `RESEARCH_SHOPS = 9`. The script is stdlib-only, so the number is stated
  there and a test pins it to `len(OWNER_SHOPS)`.
- The readback label is computed from that number: "competitor shops scanned (nine-shop
  research network)".
- New: a server that reports a different number of shops WARNs ("expected 9") and never PASSes.
- `app/command_center/p0_board.MANDATORY_SHOPS = len(OWNER_SHOPS)`. It was a literal 8, and
  missing it would have kept the board at PRODUCTION-VERIFIED with only eight shops.
- The board's JS title no longer hardcodes "8". The Required tile shows the count.
- `production_evidence.competitor_scans` needed no code change. It iterates `OWNER_SHOPS`, so
  it now returns nine.

## Tests

- New suite `tests/test_ninth_shop.py`, listed in `scripts/suite_final_segment.txt` before
  `test_product_run`. It covers:
  - every registry, with the exact URLs and spelling;
  - the scan and compare covering each monitoring part;
  - `pdf_quality` reading UNMEASURED;
  - language codes only;
  - an unreachable shop as a limitation that blocks none of the others and is not scanned;
  - no content or name in the comparison;
  - the readback count.
- Existing suites that hardcoded eight now assert the **exact nine**, either by name or by
  alias in owner order: `test_w4_intelrec_watchlist`, `test_opus2_scan_evidence`,
  `test_ws2_r1_competitor_scans`, `test_w4_readback_evidence` (label) and `test_s4_p0_board`
  (counts, plus a pin `MANDATORY_SHOPS == len(OWNER_SHOPS) == 9`).
- The no-competitor-content-in-proposals test (`test_ws2_r5_proposal_writer`) is unchanged
  and green.

**Mutation.** Each check removes the shop from one registry in a scratch copy and runs the
five suites above. The baseline was green.

| Mutation | Failing suites |
|---|---|
| `benchmarks.REGISTRY` without it | ninth_shop, intelrec_watchlist |
| `watchlist.WATCHLIST` without it | ninth_shop, intelrec_watchlist, opus2_scan_evidence, ws2_r1 |
| `scan_evidence.OWNER_SHOPS` without it | ninth_shop, opus2_scan_evidence, ws2_r1, s4_p0_board |
| `radar.market.COMPETITORS` without it | ninth_shop |
| `ops/readback` count back to 8 | ninth_shop, ws2_r1 |

**Suite run.** The command was
`JOBS=4 SUITE_REGISTRY=0 SUITES=<list> PY=<venv> bash run_tests.sh`, with no PYTHONPATH and
the venv built from both lock files. The list is every suite that grep shows naming
FireflyCrochets, watchlist, scan_evidence, benchmarks or competitor_scans. Added to it:
`test_w4_readback_evidence`, `test_watchlist_cadence`, `test_vacuity`, `test_w3_tmp_hygiene`,
`test_w4_resume_runner`, `test_w4_fmbatch1_retention_guard`, `test_ninth_shop`,
`test_radar`, `test_commerce`, `test_ws2_r5_proposal_writer`, `test_s4_p0_board`,
`test_leadtime`, `test_serp`, `test_r2_product_seo_unicode`, `test_acceptance_gates`,
`test_v11_seo_truth`, `test_v11_pwa_browser` and `test_w4_ccux`. The result is in the #28
comment.

## For the reviewer to weigh

1. **The new `languages` shop field.** It is stored in `shop` / `shop_history` for every
   watched shop. It is a list of codes, where the other fields are numbers.
   `production_evidence` reads only `listing_active_count` from `shop`.
2. **The readback count mismatch is advisory.** It WARNs and never FAILs, the same as the rest
   of the row.
3. **BUILD_STATE is not edited.** Main integrates. The DECISION_LOG entry carries the record.
