# IMAGE_REMEDIATION: Launch-0 and proposed product images (W4-IMAGES, 2026-10-11)

Branch `claude/w4-IMAGES`, from `origin/claude/w4-INTEG2` (68224ac).

Constraints this work kept to:
- Shadow only. CA$0 spent, with no provider, model or network call.
- No photograph of a physical object was fabricated.
- The image safety gate is unchanged and not weakened. Disclosure rules are unchanged.

The CATALOG lane's `CATALOG_RECONCILIATION.md` does not exist yet: no branch `claude/w4-CATALOG`
was on origin when this was written. "Other proposed launch products" are therefore
`products.launch0.PROPOSED_CANDIDATES`; these await the owner's catalogue-floor decision.

## The question each image was asked

Each image was assessed from four angles at once: Visual, Product Truth, Quality and Creative.
For every image the review asks:
1. Does an image exist, and what is its sha256?
2. Does it depict the pattern (geometry and colour against the CIR)?
3. How was it made?
4. Is the disclosure satisfied?
5. Does it represent the finished object truthfully?
6. Is it approved for customer use?
7. What is the verified alternative?

`src/brambleloop/store_foundation/image_review.py` computes all of this live from the current
CIR, and the owner page shows it.

## Per-image findings (measured on this branch, renderer host Pillow 12.3.0 / FreeType 2.14.3 / DejaVuSans)

The shared readings for all 10 images:
- **How made:** a deterministic disclosed render (`disclosed-render/2.0.0`) of the certified CIR.
  It is not a photograph and not generated.
- **Disclosure:** present in the pixels and at the start of the alt text, for all 10.
- **Product Truth gates:** PASS for all 10 (`launch0.product_truth`).
- **Verifier (`render-verification/2.1.0`):** PASS on the exact bytes for all 10.
- **Customer approved:** **no**, for all 10 (reasons below).

| Product | Build (group) | CIR | Hero sha256 (prefix) | Review status |
|---|---|---|---|---|
| Nesting Baskets: S | basket_small (launch0) | market-basket-small@1.2.0 | a16ae6095d757310 | VERIFIED, NOT APPROVED |
| Nesting Baskets: M | basket_medium (launch0, **preview**) | market-basket-medium@1.2.0 | 2853edb459191a8d | VERIFIED, NOT APPROVED |
| Nesting Baskets: L | basket_large (launch0) | market-basket-large@1.2.0 | e4de773ba6b2401e | VERIFIED, NOT APPROVED |
| Cloudline Baby Blanket | cloudline_blanket (launch0, **preview**) | cloudline-baby-blanket@1.2.0 | bf30686b90bff8e0 | VERIFIED, NOT APPROVED |
| Hexagon Coaster Set (4) | hexagon_coasters (launch0, **preview**) | hexagon-coaster-set@1.2.0 | dde60f6bbe780d18 | VERIFIED, NOT APPROVED. All 4 pieces drawn |
| Nordic Snowflake Ornament Set (6) | snowflake_ornaments (launch0, **preview**) | nordic-star-ornaments@1.4.0 | 4680c878f28768d5 | **MISLEADING HERO, DO NOT USE.** It shows 1 of the 6 pieces, and the alt text says "the whole piece" |
| Winter Snowfall Relief Throw | snowfall_throw (launch0, **preview**) | winter-village-graphghan@1.3.0 | c7c15427340597e4 | VERIFIED, NOT APPROVED |
| Nordic Forest Relief Baby Blanket | nordic_forest_baby (proposed) | nordic-forest-mosaic-throw-baby@1.3.0 | ed92367e49358e56 | VERIFIED, NOT APPROVED |
| Diamond Lattice Placemat Pair | placemat_pair (proposed) | mosaic-placemat-pair@1.3.0 | 60a8aecb36b5d19e | **MISLEADING HERO, DO NOT USE.** It shows 1 of the 2 pieces |
| Housewarming Key Basket | key_basket (proposed) | housewarming-key-basket@0.1.0 | 75855b9f3ee03e47 | VERIFIED, NOT APPROVED |

**How truthfully each image represents the finished object.** Each image is accurate to the
CIR's geometry, row colours and stitch layout. The sizes are arithmetic from the stated gauge.
No sample has been made (`twin.calibrated` is False), so drape, real texture and true yarn colour
are not shown. Nothing is generated in place of a sample.

**Creative and Quality observations** (owner judgement, not gate failures):
- The 86–92 cm throws and the blanket read as fine stripes at thumbnail size, and the relief is
  barely visible.
- The snowflake ornament reads as a striped square, not as a snowflake.

**Why none is approved for customers.** None of these is satisfied in this environment:
- a valid listing-set certificate for the exact release (#70);
- parity HERO and COMPETITIVE, which are unjudged: `image_vision` is closed and the benchmark
  galleries have not been observed (D-FB-9);
- an owner publication grant (D-FB-10).

## Why production's preview shows all five WITHHELD

At the same code, both production's commit (0417f35) and INTEG2 verify **all five** preview
heroes locally (`preview.hero_frame`: VERIFIED, verifier PASS, caption PASS). The code does not
withhold them. The production cause is therefore **UNKNOWN from here**: the preview is an
owner-session page, and production was not read.

Candidate causes, in order of likelihood:
1. A host difference, such as a missing font or a different rasteriser. The renderer and
   verifier are byte-exact and font-bound, and `render_contract.font` refuses any fallback.
2. An exception in `hero_frame`, which records verifier `NOT_RUN`.

The new review page prints the host's Pillow, FreeType and contract-font readings, together
with each frame's verifier status, failed checks and error. **Owner action, ≈2 min, CA$0:** open
`/cc/image-review` in production. The page names the cause, and the matching remediation step
applies:
- missing font: redeploy the Docker image, which installs `fonts-dejavu-core`;
- verifier FAIL: company re-engineering, as in the remediation path below.

## Image material that is NOT a candidate (never to be used as product images)

- AI-generated R&D images in `research/e1, e3, e4, e5, bench1, bench2, v1grad (out/gen*)`. These
  come from flux-2-pro, gpt-image, Gemini and BFL. They are pictures of objects nobody made, so
  they fail Product Truth by construction (F-852).
- The Laura canonical pack. It holds brand references, none of them publication-approved, and
  B-657 stands.
- `waves/h2_samples/*_hero_640_downscaled.png`. These are historical copies; the live candidate
  is always the frame re-rendered and re-verified from the current CIR.

## Remediation path per image

1. **The 8 verified heroes** (baskets S/M/L, cloudline, coasters, snowfall throw, nordic forest
   baby, key basket). Steps, in order:
   - Diagnose production's WITHHELD on `/cc/image-review` (above).
   - Run the release chain in production (gate.certify → assets.build → listing.seo) so a valid
     listing-set certificate exists.
   - Owner `fund_model`, which opens `image_vision` for the HERO description.
   - `benchmark_purchase` / `benchmark_observation` for the COMPETITIVE blind review.
   - An owner publication grant per release (D-FB-10).
   - Optional, for LIFESTYLE: VB-1 P2, or photographs of a sample that has actually been made.
2. **Snowflake ornaments (set of 6) and placemat pair (2): company-side defect, OPEN (VISUAL
   lane).** The flat renderer draws one piece where the rounds form draws `make` copies, and the
   alt text calls it "the whole piece". The verifier checks only the one piece it is given, so it
   passes. Fix:
   - `disclosed_render._flat_view` draws `make` copies on the hero (rounds already does this at
     L632);
   - `render_verification`'s flat hero counts and verifies every copy;
   - the alt text names the set.

   The customer preview currently still shows the ornament hero as VERIFIED. Withholding it there
   would change the preview's tested contract (`test_v11_store_preview` asserts all five are
   VERIFIED), and existing assertions are not edited in this lane. The finding now travels on
   the frame record (`hero_frame(...)["pieces_finding"]`).

   **Integrator/owner decision:** withhold that tile now, or wait for the renderer fix.

## The owner-only internal review: `/cc/image-review`

- **Access:** an owner session is required (`security.OWNER_SESSION_PAGES`; anonymous requests
  get 401). Responses are `no-store` and `noindex`, carry a CSP, and contain no script.
- **Content:** the actual images, at 640 px, as `data:` URIs. Each carries a stamped status
  banner such as "INTERNAL · …", along with:
  - its limitations, prominently at the top of the card;
  - provenance, verifier status, disclosure readings and Product Truth;
  - a remediation path and the verifier checks, in collapsible sections.
- **Layout:** works on a phone (1 column) up to desktop (3 columns), and in light and dark mode.
- **What it never does:** it shows a withheld or failed frame only on this owner page, never on
  the customer preview. It grants no publication, and its "customer-approved" count is
  computed (0).
- **Where it is linked:** the store summary's `image_review_path`.
- **Speed:** renders are cached per (build, CIR fingerprint), so the cold first load is about
  40 s for 10 frames.

## Tests

- `tests/test_w4_images.py`: 7/7.
- Existing suites that pass: test_v11_store_preview, test_v11_wiring_cc, test_w3_store_ux_mobile,
  test_w3_store_ux_structure, test_canon_store_brand_face, test_w3_laura_cc_access,
  test_w3_priv_leak, test_w3_k7_ops_truth, test_w3_laura_memory_isolation,
  test_w3_b2_canonical_assets, test_vacuity, test_secret_scan, test_reachability.
- test_w3_tmp_hygiene has 2 failures. Both are in files this lane did not touch
  (`scripts/w4_learn_loops_proof.py`, `tests/test_w4_fmgate_catalogue_filters.py`), so they are
  pre-existing on INTEG2.
