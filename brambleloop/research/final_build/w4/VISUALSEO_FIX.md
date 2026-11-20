# VISUALSEO_FIX — Launch-0 visual / creative / SEO blockers (W4-VISUALSEO, 2026-10-11)

Branch `claude/w4-VISUALSEO`, based on production 0417f35. Shadow only: no Etsy or Railway write,
no paid provider call, CA$0 spent. No gate, threshold or existing test assertion changed. The
Laura identity (laura-r2-a42aeac7) and owner branding and shop fields were not touched.

## How this was measured

`research/final_build/w4/visualseo_launch0_proof.py` runs the real release chain: gate.certify →
listing.draft → assets.build → pricing.position → listing.seo. It runs in a shadow worker on
scratch SQLite, with outbound sockets refused and no Etsy taxonomy snapshot. It covers the five
Launch-0 releases that pass Product Truth:
- market-basket-small, market-basket-medium and market-basket-large (the nursery-nesting-baskets
  listing);
- cloudline-baby-blanket;
- hexagon-coaster-set.

For each release it then reads what the publish path reads:
- the listing-set certificate;
- the stored F-004 search certificate;
- the #75 parity verdict, classified the way `launch.readiness` classifies it;
- the search-evidence gallery;
- the F-060 search rungs;
- the SEO package readiness.

The output is in `VISUALSEO_LAUNCH0_PROOF.json`. The latest run took 432 s, and every chain job
finished.

nordic-star-ornaments and winter-village-graphghan are still in `LAUNCH0_SLUGS`, but they fail
Product Truth: the title promises 6 pieces or village imagery that the CIR does not make. That
work belongs to the PRODUCT lane, not this one.

## Measured state: identical for all 5 releases after the fixes

| Check | Result |
|---|---|
| Listing-set certificate | **valid**. Frames served: 6 for blanket and coasters, 8–9 for the baskets (disclosed hero, scale and detail, plus the verified supplements) |
| Parity (8 dimensions) | identity, product_truth, mobile_grid, lifestyle_quality (D-FB-9 presentation standard, all 7 checks True), gallery and brand **PASS**. hero and competitive_blind_review **UNJUDGED** |
| 340 px thumbnail legibility / hero thumbnail / mobile contexts | **PASS** on every frame |
| F-004 search certificate | **REFUSED**. Failed checks: `category` and `attributes`. The `copy`, `tags`, `description` and `hero` checks pass |
| Search rungs (F-060) | competitive_thumbnail **PASS**. truthful_query_coverage **FAIL** (the certificate is REFUSED; match rate 0.80–0.90). conversion_readiness **FAIL**. no_unresolved_first_party_warning **UNMEASURED** |
| Search-evidence gallery | every job covered except **LIFESTYLE** |
| SEO package readiness | EXTERNAL_GATED |

## Each remaining blocker, classified

| # | Blocker (Launch-0) | Class | Exact gate / who clears it |
|---|---|---|---|
| 1 | Parity **HERO** unjudged: "the hero frame was never described" | **Provider limitation, held by an owner gate** | Gate `image_vision` is closed. The blind description needs a vision model call. Anthropic credit is too low, so the owner action is `fund_model` (≈CA$25, 5 min) in OWNER_ACTIONS. D-FB-9 rules that this is not company work; it is not asserted from the brief. |
| 2 | Parity **COMPETITIVE** (blind review) unjudged | **Missing data + provider** | Needs `benchmark_observation` (observed benchmark galleries, a physical or owner observation; `benchmark_purchase`, up to CA$300) **and** `image_vision`. It is never assumed to be favourable. |
| 3 | Search certificate `category` / `attributes` REFUSED, so truthful_query_coverage FAILs | **External / owner gate (credential)** | No Etsy seller-taxonomy snapshot exists. A read needs `ETSY_KEYSTRING`, or a production `listing.taxonomy_refresh` after OA-A1 re-authorisation. No taxonomy id is assumed. The ETSYCOMM lane owns the fetch code. |
| 4 | Gallery **LIFESTYLE** missing, so conversion_readiness FAILs | **Owner gate** | Needs VB-1 P2 lifestyle composites (CA$2.00 inside the CA$4.76 VB-1 ceiling) or physical sample photographs. Photorealism and identity gates are unchanged (B-657 stands). |
| 5 | first_customer **flawless_downloads**, so conversion_readiness FAILs | **Owner gate (phase)** | The delivery path is never exercised until a real `store.publish` attaches every terminology's certified file. Shadow mode refuses that, so it needs `live_listings` / Etsy authority. |
| 6 | no_unresolved_first_party_warning UNMEASURED | **Missing data** | Needs a live shop's Search Visibility reading (owner intake `POST /api/search-visibility`). |
| 7 | first_customer **post_purchase_clarity** failed for every listing | **Company-side defect: FIXED** (76d63ef) | See fix B. |
| 8 | Certified gallery supplements were exported without a mobile-context reading or a label-in-pixels reading | **Company-side defect: FIXED** (90a631b) | See fix A. |
| 9 | Parity's frame set is the 3 disclosed frames, not the 6–9 frames the certificate exports. GALLERY reads "3 frames" | **Company-side gap: OPEN, mitigated** | Each supplement is now measured by the certificate path for truth, layout, mobile and label (fix A). Giving parity the full set needs `product_authority.structural_floor` to accept a supplement's on-bytes verification (`launch_imagery.check_supplement`). That is an image-truth edit, kept for a dedicated change with the full visual suites. Next step: have `listing_asset.frames_for` append the valid certificate's supplements, with a structural reading from `check_supplement`. |
| — | `catalogue_depth`: 8 listable needed, Launch-0 has 5 renderable slugs | Owner decision (D-FB-9, recorded) | The threshold is not lowered. |

The 340 px thumbnail legibility, hero thumbnail, mobile grid, D-FB-9 lifestyle presentation and
search hero checks are no longer blockers for any Launch-0 release. They are measured PASS on
the bytes.

## Fixes

**A. Supplement frames are measured where a shopper sees them** (`publish/release_gates.py`
`supplement_presentation`, wired in `disclosed_supplements`; `publish/listing_set.py`
`disclosed_gate_results`).

Supplements are the ANGLE, CONSTRUCTION, COLOUR_CONTEXT, SIZING, MATERIALS and CONTENTS frames.
Before this fix, they were certified with only a layout-QA reading and a frame-set reading. The
`full_gallery` mobile context counted only the 3 disclosed frames. No pixel measurement checked
their title-safe band or their honesty label; the producer's word stood in for both.

Each supplement is now measured for three things:
- **Ink in the title-safe band** at phone-gallery size (390 px) and full-gallery size (2000 px).
  The threshold is 0, the same as for the disclosed set.
- **The label in the pixels.** A drawn frame must carry the render disclosure caption
  (`caption_in_image`). The CONTENTS frame must carry `PREVIEW_LABEL`, because it is a document
  preview and not a render.
- **The alt text** must open with the frame's label and stay within 500 characters.

A frame that fails any of these is left out with the reason (fail closed). The readings are
ANDed into COMMERCIAL_QA and POLICY_PROVENANCE; this only adds checks and replaces none.

Runtime: every Launch-0 supplement measured 0.0 ink with its label present, so the certificates
and frame bytes are unchanged.

**B. post_purchase_clarity read a complete disclosure check as "silent"**
(`commerce/first_hundred.py`). The expression `missing or [{"disclosure": "support"}]` treated an
empty `missing` list as silent. As a result, a listing whose copy carried every owed disclosure,
including how to ask a question, always failed. Unchecked listings and listings that are
genuinely missing "support" still fail.

Runtime: post_purchase_clarity now clears for all 5 releases. conversion_readiness now names only
flawless_downloads and LIFESTYLE, both gated.

## SEO path

The search package and certificate are already produced for every Launch-0 release through
`listing.seo` (W4-SEO). Copy, tags, description and hero pass on the merits. Match rates are
0.80–0.90. All 13 tags are `modelled`; no search volume has been measured, and none is claimed.
The only failing certificate inputs are the taxonomy-dependent ones (#3 above). Owner-configured
live shop fields are never written; drift remains proposal-only (W4-STORE).

## Tests

All run one at a time, with a private TMPDIR that has been removed.
- `tests/test_w4_visualseo.py`: 8/8 (new).
- test_w4_visual_certified_gallery: 7/7.
- test_launch0_listing_truth: 14 OK.
- test_first_hundred: 0 FAIL.
- test_cohorts, test_w4_spenda_k5a, test_cert_growth_ops, test_k8_listing_estate: 0 FAIL.
- test_vacuity, test_secret_scan, test_w3_tmp_hygiene, test_reachability: pass.
