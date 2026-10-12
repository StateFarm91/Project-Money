# W4-AESTHETIC: F-055 Style/Aesthetic Intent

**Status: PARTIAL.** This is a work-in-progress commit made at the owner's controlled pause on
2026-10-12.

Branch `claude/w4-AESTHETIC`, from `origin/claude/w4-INTEG2` (16e36ae).

## Row

F-055 is **advanced, not closed**. The row says the aesthetic facet exists in `map_product`,
but the fallback facets that `listing_language` uses omit it. The required change: include an
evidence-backed aesthetic facet in the fallback path.

## Code

**`commerce.intent.aesthetic_of(*texts)`** returns the first aesthetic word found in the
product's own record: its listing qualifiers, then its title. A word counts only if it is in
the classifier's aesthetic vocabulary, and words from our own vocabulary or from the
empty-for-search list are excluded. If the record names no aesthetic, it returns "".

**`listing_language(..., motifs=, title=)`** now adds that aesthetic to its fallback facets.
`listing.seo` passes `motifs` and `cir.title`.

## Last test results (through testslot)

| test | result |
|---|---|
| `test_w4_aesthetic_intent` | 1 FAIL, `test_the_fallback_facet_map_carries_it_and_still_maps` |
| `test_search_truth` | rc=0 |
| `test_w3_k1_search` | rc=0 |
| `test_vacuity` | rc=0 |
| `test_launch` | rc=1 (see below) |
| `test_cost_governance_wave2` | not run (paused) |
| `test_search_hero_publish` | not run (paused) |
| `test_cert_listing_frames` | not run (paused) |
| `test_v11_autonomy_timeline` | not run (paused) |

**Why `test_w4_aesthetic_intent` failed.** The failure was in the test fixture, not the code.
The fixture called `listing_language` for the ornaments with `season=None`, and `map_product`
refused it because a seasonal product must supply its `season_event` facet. The fixture now
passes `season="Christmas"`. **That fix has not been re-run.**

**Why `test_launch` failed.** Its failures read `hero: 340 px legibility ['2 piece(s) read at
340 px where the pattern makes 1']`. That is an image-gate result and is unrelated to this
diff, but it has not been checked on clean 16e36ae. Name it in the handback.

## Next executable step

1. Run `test_w4_aesthetic_intent` through testslot.
2. Run the required regression set.
3. Run `test_launch` on clean INTEG2 to classify the hero-legibility failure.
