# Brambleloop identity system — O1 "Bramble B" (the owner's concept, production build)

Lane A3, 2026-10-06. Owner decision **D-FB-16** item 1: the owner's own concept
(`owner_logo_concept.png` sha256 28f301b2…, banner variant `owner_banner_concept.png` sha256
048a1991…) is the PRIMARY identity. D1 Briar Monogram and D2–D4 remain design research only.

**Status: OWNER_DIRECTED_PRIMARY, final drawings not yet owner-approved.** Nothing is
uploaded to Etsy. The owner's rasters are not embedded or traced; every mark is original vector
geometry plus outlined open-licence type, built by code (`brand/owner_identity.py`).

## What was kept from the concept, and what was professionalised

| Concept element | Production form |
|---|---|
| High-contrast serif B | Playfair Display B (Didone/transitional, OFL), outlined. Its hairline waist slit (cut into the stem) is closed: it read as a print fault large and as a break at 40 px. |
| Bramble growth | One stem climbing the left of the B from its foot to above the top serif: 9 leaves with veins, 2 five-petal blossoms, a lower-right sprig with a third blossom; berry clusters from the banner variant (left, lower right, tip). |
| Yarn loop + small ball | One strand as a figure-of-eight with a real interlace: behind the stem, a small lobe left of the letter, over the stem and lower bowl, a large right lobe, ending in a wound ball. Gaps are SVG masks, so the marks stay transparent-ready. |
| Spaced serif BRAMBLELOOP | Cormorant Garamond SemiBold (OFL), caps +0.17 em, optical kerning (LO, AM, OP). |
| CROCHET PATTERNS between hairlines | Work Sans (OFL), caps +0.32 em, concept taupe, hairlines to the wordmark's width. |
| Script tagline | "Patterns for a More Handmade Life" in **Allison** (OFL, signature script), outlined; sized to the wordmark's width. |
| Small heart between hairlines | Dusty-rose heart, as in both concept images. |
| Category line, mugs, signs | Merchandising/copy (lane C), not identity. |

## Deliverables (all from `brambleloop.brand.identity_system`)

| Piece | Function | Master files (`src/brambleloop/brand/masters/`) |
|---|---|---|
| Full hero lockup | `hero_lockup_svg()` = `lockup_stacked_svg()` | `brambleloop-hero-lockup-{colour,mono,reversed,colour-transparent}.svg` |
| Horizontal wordmark lockup | `lockup_horizontal_svg()` | `brambleloop-horizontal-lockup-*.svg` |
| Full B / bramble / yarn monogram | `monogram_svg()` = `emblem_svg()` | `brambleloop-monogram-*.svg` |
| Simplified micro-mark (shop icon) | `micro_mark_svg()` = `icon_svg()`, `icon_png(500)` | `brambleloop-micro-mark-*.svg` |
| Wordmark | `wordmark_svg()` | `brambleloop-wordmark-*.svg` |
| Bramble motif tile | `motif_svg()` | (code only) |

Variants: `colour` (forest on cream), `mono` (one ink: forest + paper only), `reversed` (cream on
forest); `transparent=True` drops the ground. `export_masters()` regenerates the 20 masters; a
test fails if the committed files drift from the code.

## The micro-mark: same B, simplified

The A2 board measured the raw concept at 40 px: **42% of ink at ≥ 3:1, median 2.44:1**. The
micro-mark keeps the identity and simplifies it: the same Playfair B in its heaviest cut
(900; same contours, more ink — tested), two large bramble leaves instead of the sprig, one bold
loop of yarn (behind the stem, around the left, over the stem foot and lower bowl) ending in the
ball; every stroke ≥ 2.4 px at 40 px; every colour ≥ 3:1 on cream and on forest; knockout gaps
so the one-ink version keeps its shapes; nothing outside the circular crop.

Measured with the existing `brand.comparison` procedure (500 px → Lanczos; ink = RGB distance
> 0.18; WCAG per ink pixel), `research/final_build/w3/evidence/A3_measurements.json`:

| px | micro-mark ink ≥ 3:1 | median | raw concept ink ≥ 3:1 | median |
|---|---|---|---|---|
| 40 | **65.5%** | **4.91:1** | 42.2% | 2.44:1 |
| 48 | 71.9% | 5.91:1 | 43.5% | 2.67:1 |
| 70 | 83.4% | 8.11:1 | 49.8% | 2.99:1 |

Judge gates on the micro-mark: stroke survival 0.67, thinnest stroke 2.4 px, 0% ink outside
the circle, one-ink edge correlation 0.997, header letter 14 px. The remaining share under 3:1
is anti-aliased edge pixels, which every mark has at 40 px.

## Palette (sampled from the owner's files; re-sampled by the test)

| Name | Hex | Source / use | On paper |
|---|---|---|---|
| paper | #F3EEE7 | concept paper (exact) — ground | — |
| forest | #2F3E33 | banner wordmark #303F38 (ΔE 2.7) — B, wordmark, text | 9.8:1 |
| taupe | #7F6851 | descriptor (exact) — CROCHET PATTERNS, small caps | 4.55:1 |
| rose | #A67372 | heart (exact) — decoration only | 3.4:1 |
| rose_deep | #8E5A59 | rose for small text | 4.8:1 |
| yarn | #9E8170 | strand #987D6C (ΔE 1.9) — monogram yarn | 3.1:1 |
| yarn_deep | #7E6253 | ball shadow, deepened — micro-mark loop, wraps | 4.8:1 |
| leaf | #4B503F | concept leaves (exact) | 7.2:1 |
| sage | #7A7B68 | banner B (exact) — soft accents | 3.7:1 |
| berry | #86413D | banner berries (exact) | 6.4:1 |
| petal / pollen | #FBF8F3 / #A48B5A | blossoms | decorative |
| sage_mist, yarn_light, rose_light, surface | #CFD0C3, #D2B9A9, #DDB0AA, #FBF8F3 | veins/rules; reversed yarn/heart; page surface | — |

Text roles (`ROLES`) all pass 4.5:1 on background and surface (tested).

## Type system

| Role | Family (OFL) | Use |
|---|---|---|
| Monogram B | Playfair Display 700 / 900 | outlined artwork only — Playfair has a Reserved Font Name, so it is never shipped as a (modified) web font |
| Wordmark / display | Cormorant Garamond SemiBold | wordmark outlined; `fonts/CormorantGaramond-SemiBold.subset.woff` for headings (22 px+ on phones) |
| Descriptor / UI | Work Sans | caps +0.2–0.32 em, nav, prices, buttons |
| Tagline | Allison | outlined in the hero lockup; `fonts/Allison-Regular.subset.woff` via `font_face_css(extra=("script",))`; 32 px minimum, tagline only |
| Body | Lora (+ italic) | long-form, 16 px minimum |

Script licence: Allison is SIL OFL 1.1 (licence in `brand/fonts/Allison-OFL.txt`), obtained
from the google/fonts repository and outlined at build time (`fontbuild.main_owner`); nothing
is hot-linked. Interim alternative considered: Sacramento (more retro capitals).

## Clear space and minimum sizes (`CLEAR_SPACE`, `MIN_SIZE`)

* Hero lockup: 0.5 × the monogram B's cap height on all sides; at least 320 px / 50 mm wide.
* Horizontal lockup: 1 × wordmark cap height; at least 28 px / 6 mm tall.
* Monogram: 0.25 × its B; at least 160 px / 25 mm wide.
* Micro-mark: 1/8 of its square (built into the 500 px icon); 40 px / 6 mm minimum; the only
  mark used from 40 to 96 px.

## Usage and Laura

`USAGE_RULES` (15 rules) in the module. Laura is the face, the mark is the signature: in a
banner Laura sits to one side and the hero lockup takes the centre, as in the owner's banner
concept; the micro-mark may be a small corner seal, never on her face or body; previews with
the canonical portrait stay labelled INTERNAL.

## Evidence

`research/final_build/w3/evidence/`: `A3_micro_vs_concept.png`, `A3_lockups_cream_forest.png`,
`A3_horizontal_wordmark.png`, `A3_marks_variants.png`, `A3_palette_type.png`,
`A3_clearspace_minsize.png`, `A3_measurements.json`. Rebuild:
`PYTHONPATH=src python -m brambleloop.brand.owner_proofs research/final_build/w3/evidence`.

## Not verified / open

* The owner has not seen or approved these drawings; the B, leaves and loop are this lane's
  reading of the concept.
* No browser/print proof at physical sizes; no Etsy upload (the shop-icon PNG is `icon_png(500)`).
* `banner_png` (a 1600×400 raster banner exporter) is still absent; lane B's storefront gate
  reports it.
