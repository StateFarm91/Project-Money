# Wave 3 lane B handoff: store UX / art direction (Owner Store Preview v2) and K2 trust gate

Branch `claude/w3-B` (base `claude/v11-CANON` f0c2d12). It merges lane C (`claude/w3-C`,
copy_v2), lane I (`claude/w3-I`, etsy_constraints) and lane A (`claude/w3-A`,
identity_system) as they stood when merged. No peer file was edited. Nothing was pushed or
published, and no paid call was made.

## What was built

| Requirement | Status | Notes |
|---|---|---|
| Owner Store Preview v2 (F-926 / K16): `render_preview(db, vp, variant="v2")` | COMPLETE (preview), NOT CERTIFIED | Mobile-first at 390 px and excellent at 1280 px. Order of the page: banner, shop header, announcement, sections and product cards in the top fold. Below it: a trust band, About anchored on Laura, then FAQ, policies and support. Lane J must judge whether it is actually premium. |
| Storefront top fold | COMPLETE | `<div class="fold" data-fold="first-screen">`. No implementation vocabulary (tested and measured). |
| Logo/icon at real tiny sizes | COMPLETE | Lane A's `icon_svg()` at 16, 32, 40, 48 and 70 px, shown on light and on dark. |
| Laura seller portrait | COMPLETE (internal only) | Byte-verified canonical portrait via `brand_face.image_for(..., for_customers=False)`. Every Laura element has the label "Internal preview — canonical reference, not publication-approved" in its aria-label. The banner caption strip and the About portrait carry the visible label. |
| Desktop and mobile-safe banner | COMPLETE (preview) | One canvas, seen whole on desktop and as a centre crop on a phone. Laura and lane A's stacked lockup (lane C's banner line) sit inside the phone window. Disclosed product renders sit in the desktop-only wings. Owner board shows desktop, 390 and 320 px crops. Canvas is 1600x400 (lane I: VERIFIED_HELP_CENTER). The phone crop is UNKNOWN at Etsy, so the 2:1 used here is ASSUMED and labelled. |
| Announcement/tagline | COMPLETE | Taken from lane C: TAGLINE → shop title; BANNER["line"] → banner; ANNOUNCEMENT. |
| Sections | COMPLETE | Only sections with listings are shown, named by lane C's slugs. Planned sections are not shown, because that would imply products that do not exist. |
| Listing cards | COMPLETE | Product-first. Uses only the Launch-0 disclosed renders that pass verification on their exact bytes. A frame that fails is withheld. Every card says "Digital rendering, not a photograph". |
| About / story anchored on Laura | COMPLETE | Lane C's ABOUT_PARAGRAPHS beside the large Laura portrait, plus a promise box built from lane C's trust signals. |
| FAQ / policy / trust presentation | COMPLETE | Accordions with 48 px rows, plus a 2x2 (phone) / 4-up (desktop) trust band. |
| Seasonal extension | COMPLETE (preview) | Winter banner (desktop and phone crop) with lane C's seasonal heading. Labelled "No seasonal patterns are listed yet". |
| Dark / awkward crop checks | COMPLETE | Icon and cards on a dark surround. Banner at 320 px. Listing image at square, landscape and portrait (Etsy publishes these shapes but not their ratios; labelled UNKNOWN). Portrait at 120 px square and 72 and 40 px circles. |
| Side-by-side comparison vs rejected v1 | COMPLETE | `variant="compare"` shows both first screens at 390x844, with scoped CSS so neither page restyles the other. It shows static metrics computed live, plus measured metrics from the committed evidence (see below). |
| K2 storefront trust gate (F-233/234/235/237/263/279) | BUILT; WIRING REQUEST to lane A | `store_foundation/storefront_gate.py` checks the rendered assets, not briefs (per-row table below). |

### K2 per-row status (`storefront_gate.evaluate()`, with A, C and I merged)

| Row | Status | Why |
|---|---|---|
| F-233 Storefront completion | FAIL (honest) | `STORE_BANNER_NOT_EXPORTED`: no 1600x400 raster banner exists for upload. Icon passes at 40 and 70 px on lane A's raster: contrast 3.58 and 4.16, coverage about 0.3, stroke at least 16 px. Lockup measures about 141 px tall on a 390 px phone. Copy is from lane C. |
| F-234 Shop trust architecture | PASS | Every one of these is present: what is sold, the PDF, delivery, skill, the support path and returns. The render disclosure is present and the copy states no social-proof figures. |
| F-235 About / process | PASS | 400 characters or more, truth-lint clean, and Laura is disclosed as an AI. |
| F-237 Section architecture | PASS | Buyer-facing names. No empty section is shown. |
| F-263 Ads readiness | FAIL | Inherits every storefront finding: traffic may not be bought to an unfinished shop. |
| F-279 Storefront-to-listing continuity | PASS | Every product the announcement names is in the grid. The banner line is the shop's own copy. The seasonal banner stays preview-only until seasonal listings exist. |

If a peer is missing, the gate fails closed (`STORE_ICON_NOT_RENDERED`, `STORE_BANNER_NOT_RENDERED`, `STORE_COPY_INTERIM`).

## Measured improvement (Chromium/Playwright, `research/final_build/w3/evidence/B_metrics.json`)

See the table in "Runtime proof" below. Every number comes from the committed JSON.

## Files

New (lane B):
- `src/brambleloop/store_foundation/preview_v2.py`
- `src/brambleloop/store_foundation/preview_sources.py` (adapters for A, C and I, with fallbacks)
- `src/brambleloop/store_foundation/storefront_gate.py`
- `scripts/w3_store_preview_measure.mjs`, `scripts/w3_store_preview_evidence.py`
- `tests/test_w3_store_ux_structure.py`, `tests/test_w3_store_ux_mobile.py`, `tests/test_w3_store_ux_gate.py`
- `research/final_build/w3/evidence/B_*` (8 JPEGs, each 300 KB or less, plus B_metrics.json)

Modified (lane B owned): `src/brambleloop/store_foundation/preview.py`. It adds the `v2` and `compare` variants and a dispatch. The v1 `standard` and `brand_face` output is unchanged and still the default.

## WIRING REQUESTS

1. **Lane A, `brand/storefront.py::check_storefront`** (K2). Before the final `return problems`, add:
   ```python
       # K2 (F-233..F-279): judge the rendered icon/banner and the real copy, not the briefs.
       from ..store_foundation import storefront_gate
       problems.extend(storefront_gate.problems())
   ```
   Expect `shop_complete` / launch readiness to FAIL on `STORE_BANNER_NOT_EXPORTED` until item 2 lands. That failure is intended.
2. **Lane A, `brand/identity_system.py`**: add `banner_png(width=1600, height=400, tagline=None) -> bytes`. It should be the stacked lockup on paper with motif wings and no Laura (Laura is not publication-approved). The gate already looks for `identity_system.banner_png`.
3. **Lane F, `app/command_center/api.py::store_preview_handler`**: pass the variant through:
   ```python
   def owner_store_preview(request: Request, viewport: str = "mobile", variant: str = "v2"):
       ...
       return HTMLResponse(store_preview_mod.render_preview(db, viewport, variant=variant), ...)
   ```
   `render_preview` falls back to `standard` for unknown values, so the value is safe to pass. I recommend `v2` as the route default. The function default stays `standard` so the v1 tests hold.
4. Optional, lane F: serve `brand/fonts/*.woff` under `/cc/` (CSP `font-src 'self'` blocks `data:` fonts). Once served, `preview_v2._css` can prepend `identity_system.font_face_css(base_url)`. Until then the preview uses lane A's CSS stacks with Georgia/system fallbacks.

## Open defects / for the certifier (lane J)

- The listing cards are the diagrammatic disclosed renders. They are truthful but not beautiful, and they are the weakest part of the page. This is a Visual (lane H) quality gap, not a layout one.
- Laura's banner and About images are internal-only. A publishable banner today means no Laura.
- Lane I found that Etsy's profile photo belongs to the account holder (`profile_is_account_level`). The desktop "Laura" card is therefore presented as a brand-face card, not as Etsy's owner photo. Where Laura may appear on Etsy is an owner decision (lane I checklist B3).
- The owner's concept tagline "Patterns for a More Handmade Life" trips `TRUTH_PHYSICAL_MAKING` in the store lint. Lane C chose "For a life you make by hand" instead.
- The owner's concept image is not embedded: the woman in it is unverified as Laura.

## What I could NOT verify

- How Etsy actually crops the banner on phones and in the app. It is UNKNOWN at Etsy, so 2:1 is assumed. Check the real crop after upload.
- How the design looks with lane A's real web fonts. Screenshots use fallback fonts (DejaVu/Liberation in this container).
- Whether it is premium. That judgement belongs to lane J and the owner, not to the builder.
