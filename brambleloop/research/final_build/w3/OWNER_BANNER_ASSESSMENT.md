# Owner canonical banner — publication assessment (lane B2, D-FB-17)

Generated 2026-10-06 (UTC) by `brambleloop.store_foundation.owner_banner.assess()`.
Machine-readable record: `research/final_build/w3/owner_banner_candidates/owner_banner_assessment.json`
(regenerate with `owner_banner.write_evidence(Path("."))`; `tests/test_w3_b2_canonical_assets.py`
fails if this file and the code disagree).

**File:** `src/brambleloop/brand/owner_source/brambleloop_owner_banner_canonical.png`,
sha256 `048a199133f7589cc243cb876a7ee5b0f68b5d6530929a922c79de9eda64eb98`, 1983×793 RGB PNG
(2.50:1), byte-identical to what the owner supplied (re-hashed on every read; immutable).

**Verdict: BLOCKED.** The exact file cannot be published today. 4 gates pass, 5 fail, 6 are
UNKNOWN (UNKNOWN blocks like FAIL and is never counted as a pass). The failures are **not only
dimensional**, so no reframe alone makes it publishable. The banner stays the canonical target;
nothing has been substituted, and no correction is adopted.

## What the code can and cannot know

- **Measured from pixels:** size, aspect, format, opacity, embedded metadata, and the centred
  identity block's extent (ink rows in the central 40–60 % band: rows 44–636, 593 px tall;
  wordmark columns 630–1431).
- **Measured from the file's own metadata:** the PNG carries a C2PA (Content Credentials)
  manifest in a `caBX` chunk. Parsed, it declares `digitalSourceType = trainedAlgorithmicMedia`,
  action `c2pa.created` / `c2pa.converted`, generator "ChatGPT" / "gpt-image", signed by
  "OpenAI Media Service", 2026-10-06T14:07:05Z. **The signature has not been cryptographically
  verified** (no C2PA library is installed); this is the file's own declaration. The logo
  carries the same kind of manifest (2026-10-06T14:05:20Z).
- **Measured from the repo:** Etsy's published numbers (`integrations.etsy_constraints`, quoted
  from Etsy's Help Center on 2026-10-06; what Etsy *publishes*, not observed enforced — no upload
  has been made), the catalogue and sections, Laura's canon and publication status, and the store
  disclosure text.
- **Not measured (no OCR, face detector or face-embedding model is installed):** what the picture
  shows. The visible words are a transcription (lane B2 brief + DECISION_LOG D-FB-17), and the
  people/objects are as declared in D-FB-17 ("Laura left, warm cozy setting, centred identity,
  crochet/yarn right, tagline"). Those gates are UNKNOWN for human review.

## Gates on the exact file

| Gate | Status | Evidence | Basis |
|---|---|---|---|
| `canonical_integrity` | **PASS** | byte-identical to what the owner supplied | sha256 of the repository copy |
| `etsy_banner_minimum_and_format` | **PASS** | 1983×793 opaque PNG ≥ Etsy's published minimum 1200×300 and recommended 1600×400; PNG supported | file vs Etsy Help Center figures (published, not enforcement-observed) |
| `f233_banner_canvas_4to1` | **FAIL** | file is 2.50:1; the storefront canvas is 4.00:1 (1600×400). Etsy must crop or fit it; how Etsy fits a non-4:1 upload is **not published (UNVERIFIED)** | measured |
| `f233_identity_block_survives_4to1` | **FAIL** | identity block 593 px tall (rows 44–636); a full-width 4:1 crop is 496 px tall, so **no** 4:1 crop keeps all of it; a centre crop (rows 148–643) cuts 104 px off the top of the monogram | measured ink rows; centre crop is an assumption about Etsy |
| `f233_identity_block_in_phone_window` | **UNKNOWN** | horizontally inside an assumed 2:1 centre window (cols 496–1487 ⊃ 630–1431), but Etsy publishes no phone crop | measured block vs ASSUMED window |
| `laura_identity` | **UNKNOWN** | a person is declared (D-FB-17). Whether she is Laura (`laura-r2-a42aeac7`) cannot be measured: biometric floor UNMEASURED (no qualified face-embedding model), no judge readings, no conditioning receipt from her reference bytes (the manifest names an outside generator). Human identity-review queue (`owner_banner.identity_review_request(db)`) | identity gate run on the file |
| `laura_publication_status` | **FAIL** | `visual.canonical.asset_status` = `not_for_publication`; no Laura image is publication_approved. A banner presenting a woman as the brand's face is Laura imagery (if she is Laura) or an unverified woman as the brand face (if not) | measured on the file's sha256 |
| `laura_photorealism_anatomy` | **UNKNOWN** | no vision-judge reading exists; none invented | — |
| `ai_generated_imagery_disclosure` | **FAIL** | the file's own C2PA manifest declares it AI-generated; the store disclosure (`copy_v2.store_disclosure`) carries Laura's AI line but **not** `platform_policy.DISCLOSURES["generated_imagery"]`, so the generated scene and crochet would reach shoppers undisclosed. Also: the shop's image note says "Images are digital renderings … not photographs", which does not describe this generated image | C2PA manifest + store disclosure text |
| `laura_never_claims_human_in_text` | **PASS** | `TRUTH_LAURA_HUMAN_CLAIM` fires on no transcribed word (scope: the transcription only) | lint |
| `laura_ai_disclosure_at_banner` | **UNKNOWN** | no in-image AI disclosure; store-level disclosure says Laura is an AI; whether that is adequate for a shopper who sees only the banner is an unmade policy reading | transcription + disclosure text |
| `product_truth` | **UNKNOWN** | `final_image_gate` = UNKNOWN (no verified source render — the file declares itself generated). The shop has 3 patterns: Hexagonal Storage Basket, Cloudline Textured Baby Blanket, Hexagon Coaster Set. Any crochet item (garment, basket, granny-square pieces, the book spines) that reads as a Brambleloop product but is not one of these fails Product Truth — a reviewer must list what is shown | final_image_gate + catalogue |
| `nav_categories_truth` | **FAIL** | banner nav HOME \| BABY \| WEARABLES \| GIFTS \| SEASONAL: **Wearables, Gifts, Seasonal hold no pattern** (sections `wear`, `collections`, `seasonal` have 0 listings; only Home 2 and Baby 1) | transcription vs measured sections |
| `public_copy_truth_lint` | **PASS** | no truth rule fires on: BRAMBLELOOP, CROCHET PATTERNS, "Patterns for a More Handmade Life", the nav, "Good Things Take Time", "SAME YARN MORE HAPPY", "Crochet a Brighter Everyday", spines "CROCHET / A CALMER HOME / A BRIGHTER YOU". All-caps voice advisories only (artwork typography) | lint over the transcription |
| `visible_text_complete` | **UNKNOWN** | no OCR: nobody has machine-checked the transcription is every word | — |

**Related logo finding (not a banner gate):** the canonical logo's footer reads
HOME · BABY · GIFTS · SEASONAL — **Gifts and Seasonal hold no pattern today.** These are the
owner's pixels; this lane does not edit them. Owner options: list patterns in those sections
before the artwork is shown publicly, or decide on the wording.

## Minimal correction candidates — OWNER_REVIEW_REQUIRED, none adopted

Deterministic and non-generative; **no owner pixel is altered** in either (tests prove pixel
equality against the original). They address only the dimensional gates. Review copies are
resampled; the full-size candidate is regenerated exactly by `owner_banner.candidates()`.
Adoption would need a new owner decision naming the file's bytes
(`canonical_assets.AUTHORISED_BRAND_CHANGES`).

| Candidate | What changes (measured) | Fixes | Does not fix |
|---|---|---|---|
| `A_crop_4x1_top_anchored.png` (review 800×200) | full-width crop to 1983×496 (3.998:1), rows 44–539. Removes the top 44 rows and the bottom 253 rows. Of the identity block, the monogram, wordmark and descriptor are kept; the last row of the script tagline (row 540), the heart (550–594) and the category line (619–636) are cut. Whether the person's face stays whole is **not measured** (no face detector) — owner to look | `f233_banner_canvas_4to1` | identity block (heart + nav cut), all non-dimensional gates |
| `B_pad_4x1_edge_colour.png` (review 1000×250) | every owner pixel kept at its own size; 594 px added left, 595 px right (3172×793, exactly 4:1) as a soft vertical gradient of each edge's own colours (per-row mean of the 4 outermost columns, 201-row box smoothing; no new imagery). The artwork fills the centre 63 % of the width; under the assumed 2:1 phone window owner columns 199–1784 show | `f233_banner_canvas_4to1`, `f233_identity_block_survives_4to1` | all non-dimensional gates |
| `simulation_centre_crop_4x1.png` (review 800×200) | **not a candidate**: what a plain 4:1 centre crop of the exact file would show (one possible Etsy behaviour) | — | — |

## What the owner needs to decide (no action taken by this lane)

1. **Laura in the banner** — the woman is not verified as Laura and no Laura image is
   publication-approved. Either the human identity review confirms her and the Laura
   customer-facing gates are passed, or the composition is reproduced from Laura's canonical
   references (Visual), or the owner decides otherwise. Any visible change comes back to the owner.
2. **Generated-imagery disclosure** — the file declares itself AI-generated. Lane C must add the
   generated-imagery sentence to the store disclosure (and adjust "Images are digital
   renderings…") before this banner can be published.
3. **Product Truth review** — a human lists the crochet shown and whether any reads as a
   Brambleloop pattern that does not exist.
4. **Nav categories** — Wearables / Gifts / Seasonal (banner) and Gifts / Seasonal (logo footer)
   have no products.
5. **Aspect** — choose A, B, neither, or a Visual reproduction at 4:1 of the same composition.
