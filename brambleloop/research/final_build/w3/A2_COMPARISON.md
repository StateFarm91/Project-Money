# Brambleloop identity: comparison for the owner's decision (wave 3, lane A2)

Date: 2026-10-06 (UTC). Status: **OWNER TO DECIDE.** This page records observations only and
makes no recommendation. No mark is locked, nothing has been uploaded to Etsy, and nothing was
spent.

## Candidates

| # | Candidate | What it is |
|---|---|---|
| 1 | **D1 Briar Monogram** | `brand.identity_system`: a vector rebuild of the owner's concept, made from outlined OFL type and geometry |
| 2 | **Owner concept (raster, as supplied)** | The owner's PNG, 1536×1024, sha256 `28f301b2…`. It has only been cropped (to the monogram for icon sizes, to the lockup for the banner and header) and resampled. It has not been traced, redrawn, recoloured or cleaned. |
| 3 | **D2 Chain Link** | `brand.directions`, ranked 2nd by lane A's judge (total 73.3) |
| 4 | **D3 Drupelet** | `brand.directions`, ranked 3rd by lane A's judge (total 73.3, tied with D2) |

The full 2.3 MB original is not in the repository. Only a downscaled reference
(`A2_0_owner_concept_as_supplied.png`, 691×461) is committed.

## Evidence

All images are in `evidence/`. Each is 300 KB or smaller.

- `A2_0_owner_concept_as_supplied.png`: the owner raster, downscaled, for reference
- `A2_1_icon_small_sizes.png`: the shop icon at 40 px and 70 px, in a circle crop, and magnified 4×
- `A2_2_header_scale.png`: the seller/store header on a phone (390 px) and on desktop (1280 px), plus a 280×40 header lockup
- `A2_3_mobile_fold.png`: the mobile storefront first screen at 390×844
- `A2_4_banner_1600x400.png`: the banner at Etsy's recommended 1600×400
- `A2_5_desktop_1280.png`: the desktop storefront first screen at 1280×800
- `A2_6_monochrome.png`: one ink, black on cream and cream on forest, at 160 px and 40 px
- `A2_measurements.json`: every number below, with its basis

Rebuild everything with
`PYTHONPATH=src python research/final_build/w3/A2_build_comparison.py <scratch>`. The rebuild
needs the owner raster and the preinstalled Chromium, and it blocks network access.

## Method

The same procedure is applied to every candidate:

- **Sizes.** Etsy's verified constraints come from `integrations.etsy_constraints`: the logo
  must be at least 500×500 and square, and the recommended banner is 1600×400. Each icon is
  made as a 500 px square and then resampled with Lanczos to 160, 70 and 40 px, which is how a
  browser shows an upload.
- **Storefront.** The storefront and banner are lane B's v2 renderer (`store_foundation.preview_v2`),
  with the candidate's icon and banner lockup injected into its render context. The layout,
  lane C's copy, the page palette (D1's tokens) and the type are the same for every candidate.
  This means D2 and D3 marks sit on a D1-coloured page, and their own palettes are not shown in
  the page chrome.
- **Owner concept placement.** Its banner lockup is the supplied crop on its own paper colour,
  and it includes its own script tagline and category line. The vector candidates use lane C's
  tagline instead.
- **Laura.** Every Laura image is the canonical portrait and is labelled internal, not
  publication-approved. This applies to all four candidates.

## Measured at small sizes

| | D1 | Owner concept | D2 | D3 |
|---|---|---|---|---|
| Ink pixels at ≥ 3:1 against the ground, 40 px | 64% | 42% | 75% | 76% |
| Median-ink contrast, 40 px | 3.83:1 | 2.44:1 | 4.33:1 | 7.14:1 |
| Darkest-ink contrast, 40 px | 12.09:1 | 7.61:1 | 13.97:1 | 13.79:1 |
| Detail retained, 40 px vs 160 px (edge correlation) | 0.670 | 0.534 | 0.669 | 0.626 |
| Stroke survival at 40 px (0.5 px erosion) | 0.652 | 0.452 | 0.688 | 0.660 |
| Ink outside the inscribed circle | 0.2% | 1.7% | 0.0% | 1.5% |
| Header lockup fitted in 280×40: wordmark letter height | 16.5 px | 5.1 px (stacked crop) | 8.9 px | 8.2 px |
| One-ink version: colour ink still inked | 93% | 83% (derived) | 95% | 93% |
| One-ink edge correlation with colour, 70 px | 0.984 | 0.969 (derived) | 0.988 | 0.994 |

## Observations

These are factual and are not ranked.

- **40 px icon.**
  - D1: the serif B, ring and ball stay distinct. The leaf pair remains only as a small accent.
  - Owner concept: the B stays recognisable. The sprig, blossoms and yarn figure-of-eight
    merge into soft mid-tones, and its median ink is the lowest contrast of the four (2.44:1).
  - D2: reads as two linked rings.
  - D3: reads as a berry or grape cluster, and the looped stem is barely visible.
- **Header.**
  - D1, D2 and D3 each have a horizontal lockup.
  - The owner concept is stacked only, so it cannot fill a 280×40 header slot. Fitted there,
    its wordmark letters are 5.1 px tall.
  - In lane B's phone header, every candidate's icon sits beside the shop name, which is set
    as live text.
- **Banner (1600×400) and storefront.**
  - All four lockups fit the banner's centre area.
  - The owner concept appears as a lighter paper rectangle because it is supplied on its own
    background.
  - Its script tagline ("Patterns for a More Handmade Life") and category line are
    legible at 1600 px. At the phone crop they are very small (see `A2_3`); this was not
    measured in pixels.
- **Monochrome.**
  - D1, D2 and D3 each have a designed one-colour variant, and every element survives in both
    black on cream and cream on forest.
  - The owner raster has no one-ink version. A luminance threshold keeps the B, the leaves,
    the yarn and the ball, but its cream blossoms and soft shading do not carry through to a
    single ink. Producing a one-ink version would require redrawing it.
- **Production facts.**
  - The owner concept's monogram crop is a 590×529 px raster. It is above Etsy's 500×500
    minimum but not square, so it is padded with its own paper colour to make the square icon.
  - It has no vector source for print, embossing or large sizes.
  - D1, D2 and D3 are vector, with no size limit.

## What was not verified

- How Etsy's current shop page actually crops and masks the icon and banner on each device.
  The circle crop shown is only a design margin.
- Any buyer response to any candidate.
- How the D2 and D3 palettes look across a full page.
