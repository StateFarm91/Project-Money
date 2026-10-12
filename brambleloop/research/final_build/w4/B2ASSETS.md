# W4-B2ASSETS: Final Master F-527 Brand Asset Health

Branch `claude/w4-B2ASSETS`, from `origin/claude/w4-INTEG2` 16e36ae.

**Status: PARTIAL**, checkpointed at the controlled pause. F-527 is advanced, not yet closed.

## Built

`brand/asset_health.py` compares the live shop's icon and banner, as getShop returns them,
with the owner's canonical files (D-FB-17). It reports four findings:
- **missing**: getShop returned no URL.
- **low resolution**: the icon is under 500 x 500 px, Etsy's recommended logo size (help
  article 115015663347). The banner's resolution is reported UNKNOWN, because the API returns
  only a 760 x 100 rendition.
- **stale**: the brand's colours, but not the current artwork (difference-hash and
  mean-colour readings).
- **off-brand**: neither of the above.

Each problem opens one P2 incident, `brand.asset_health:<surface>:<problem>`. The incident
routes the upload to Brand/Visual and closes when a fresh reading is clean.

The check is wired into `etsy.shop_snapshot` behind `policy_reader.enabled()`, so a test
process makes no network read.

## Tests

- `tests/test_w4_b2assets.py`: 3/3.
- Required regression set: **not run** (paused before it).

## Known gaps

- Listing-image colour and typography consistency rests on the existing
  `brand.bible` BRAND_PALETTE_DRIFT check. It is not re-tested here.

## Next executable step

Run the required regression set plus test_etsy_ops or test_storefront_gate through
testslot, then record F-527 evidence for the integrator.
