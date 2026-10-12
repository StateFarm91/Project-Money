# W4-SIZEINTENT: F-056 Size/Scale Intent

Branch `claude/w4-SIZEINTENT`, from `origin/claude/w4-INTEG2` (9fd62cc).

## The board row

Row **F-056** (labelled post_launch; under the owner's 2026-10-12 decision it is required
before launch):

- **Missing:** "Size count in title and finished size in description; no size/shape query
  family".
- **Remaining:** "Add a size/shape query family from twin dimensions".

## What was built

**A measured shape.** `commerce.search.shape_of(twin)` returns the shape the twin measured:

- the polygon for a stacked-increase round piece (`twin.sides`): hexagon for the coasters and
  the nesting baskets;
- `round` for a piece worked in the round with no corners (the key basket);
- `None` for flat pieces, which make no shape claim.

**Two new query families in `build_query_set`, labelled `assumed` like every template:**

- **`shape`:** `{shape} {category} pattern` and `{shape} crochet {category}`. Added only when a
  shape was measured.
- **`sizes`:** `{category} pattern in {n} sizes` and `multi size {category} pattern`. Added only
  when the pattern is graded into more than one size.

**No size words are generated.** Small, large, mini and oversized are never produced: nothing
here measures a size class against what a buyer expects.

**Shape truth.** `tag_truth` and `tags_truth` take the measured shape. A shape word that
contradicts it is refused as `TAG_SHAPE_UNTRUE`, wherever the phrase came from: a template, an
observed buyer phrase, a must-have tag or the final tag set. An unmeasured shape neither
supports nor refutes a phrase.

**Wired into the release path.** `listing.seo` passes the twin's shape and the graded size count
into the query set, the observed-phrase filter, the must-have truth check and the final tag
truth check.

## Evidence

`tests/test_w4_size_shape_intent.py`, 5 of 5 passing:

- the shape is read from the twin (coasters and baskets are hexagon, the key basket is round,
  flat pieces have none);
- the family adds only shape phrases and graded-size phrases, never a size class, and each
  phrase is labelled assumed;
- there is no shape family without a measured shape;
- a contradicting shape word is refused;
- every Launch-0 curated tag set agrees with its twin.

Regression runs through `testslot`: test_commerce, test_search_truth, test_w3_k1_search,
test_launch0_listing_truth, test_w3_seo_strategy, test_product_run and test_vacuity. Their
results are recorded below.

**Row status:** F-056 is advanced to *implemented and tested*. It is not closed: closing
needs the deploy and the release record.

## Checkpoint (owner controlled pause, 2026-10-12)

**Status: DONE for code and its own tests. The required regression set has not been run on
the merged head.**

Tests on base 9fd62cc, all through testslot:

| test | result |
|---|---|
| `test_w4_size_shape_intent` | 5 of 5 OK |
| `test_commerce` | rc=0 |
| `test_search_truth` | rc=0 |
| `test_w3_k1_search` | rc=0 |
| `test_launch0_listing_truth` | rc=0 |
| `test_w3_seo_strategy` | rc=0 |
| `test_vacuity` | rc=0, after guarding one loop |
| `test_product_run` | not run |

After merging INTEG2 16e36ae (c8ddf2b), the required set (test_vacuity, test_launch,
test_cost_governance_wave2, test_search_hero_publish, test_cert_listing_frames,
test_v11_autonomy_timeline) was queued but **not run**: it was stopped at the pause.

`test_search_hero_publish` will fail on this branch with `LISTING_PRICE_NOT_PLAN` until
W4-PRICEFIX is merged, because the same failure exists on clean INTEG2.

**Row:** F-056 is advanced to implemented and tested. It is not closed.

**Next executable step:** run the required set and `test_product_run` through testslot, then
hand the branch to the integrator.
