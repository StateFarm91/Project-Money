# POD line — design specification (v1, Day 2)

Candidate: C19 (`research/candidates/CANDIDATES.md`), decision D-008. Personalized Canadian-gift
products sold through the same Etsy shop as MapleSheets, fulfilled via Printify with a
Canadian print provider (4-8 day domestic delivery, no cross-border duties).

## Personalization architecture (confirmed 2026-09-17)

Printify has a native **Personalization Studio**: a product variant can be configured with a
text layer, the buyer enters their own text at checkout (on Etsy, via Etsy's personalization
field, or on Printify's own storefront), and Printify renders the final artwork and generates
mockups automatically (async preview-generation endpoint, confirmed against Printify's API
docs). **This means no custom per-order rendering pipeline is needed** — `build_designs.py`
renders the *base template art* (background, icons, static text) with the personalizable area
left visually balanced for a range of text lengths; Printify's own system handles the buyer's
actual words once the product's personalization strategy is configured through the API or
dashboard. That configuration step needs a live shop connection (`PRINTIFY_TOKEN`) and is not
done yet — it is the next step once Block 1 (optional Printify sub-step) lands, not before.

## The three initial designs (`build_designs.py`)

| Design | Function | Product | Personalizable fields | Occasion |
|---|---|---|---|---|
| Welcome to \<Town\> | `mug_welcome(town, province, established=None)` | 11oz mug wrap | town, province, established year (optional) | new-home, moving-away, cottage-country pride |
| The \<Family\> Cottage | `print_cottage(family, established)` | 8×10 art print | family surname, established year | cottage, housewarming |
| Proud Hockey \<Role\> of \<Name\> #\<Number\> | `tote_hockey(name, number, role)` | canvas tote | player name, jersey number, role (mom/dad/grandma/...) | hockey-family gifting |

Palette: navy `#1A2B3C`, pine `#244A3A`, cream `#FAF6EB`, gold `#C49545` — distinct from the
MapleSheets Etsy-template brand (navy/cream/gold there too, but this is a different product
line in the same shop; no shared trademark claim either way, both are generic).

## Robustness: auto-fit text (LL-010 candidate if this recurs elsewhere)

Every personalizable string is rendered through `fit_font()`, which shrinks the font size until
the text fits a safe width, rather than a fixed size that can run text off the canvas. This
was **not** the case in the first draft: a first pass fixed-size mug design put a divider line
through the middle of the town name (spacing bug), and separately, long realistic inputs
("Sault Ste. Marie", "Papineau-Beauchamp", "grandmother") ran off both edges of the canvas at
a fixed font size — caught by rendering stress-test inputs before considering the designs
done, not by the happy-path sample data. `test_build_designs.py` checks this automatically
(renders long and short sample text, asserts no ink reaches the outer safety margin) so a
future edit can't silently reintroduce the overflow.

## Open, not yet done

- **Pixel dimensions are placeholders**, sized generously (mug wrap 3600×1600, print 2400×3000
  @300dpi-equivalent for 8×10, tote 4200×4800) but not yet checked against a real Printify
  blueprint's exact print-area spec. Once `PRINTIFY_TOKEN` exists: `printify_api.py blueprints`
  to find the mug/print/tote blueprint ids, `providers <blueprint_id>` filtered to a Canadian
  print provider (`printify_api.py locations`), then `variants <blueprint_id> <provider_id>`
  for the exact print-area pixel dimensions per variant; resize/crop the base art to match
  before upload.
- **Personalization Studio configuration** (the text-layer definition itself, font choice
  inside Printify's own renderer, preview generation) is not done — needs the live API
  connection. Until then these are static base-art files only.
- **Listing copy, pricing, images** for these three products are not written yet (unlike the
  Etsy-template listings, which have full `listings.json` entries) — do after the blueprint
  dimensions are confirmed, since final mockup images should come from Printify's own mockup
  generator (photorealistic) rather than the flat design files here.
- **2 more designs** to reach the "3-5" target in `CURRENT_PRIORITIES.md` (e.g. a "New Home in
  \<Province\>" moving mug, a personalized pet-owner tote) — same pattern, add functions to
  `DESIGNS` in `build_designs.py`.
