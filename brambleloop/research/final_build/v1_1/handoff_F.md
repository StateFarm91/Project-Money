# Handoff — v1.1 lane F (Store Foundation / Owner Store Preview)

Branch `claude/v11-F`, based on `claude/visual-investigation` @ 0694fb7. Nothing was pushed,
published, sent to Etsy or spent. The phase stayed shadow throughout.

## Requirements

| ID | Status | Notes |
|---|---|---|
| Directive §10 Store Foundation | PARTIAL (content COMPLETE; owner-gated items open) | All 21 store surfaces are modelled, checked and previewed. What remains needs an owner decision or owner login. See STORE_FOUNDATION_REVIEW.md. |
| F-926 Store Preview Mode | COMPLETE (pending route wiring) | `render_preview(db, viewport)` covers the shop, listings, images, titles, descriptions (via policies and About), prices, disclosures, and phone and desktop layouts. It is not mounted yet; see the wiring request below. |
| F-233 Storefront completion gate | PARTIAL | Every surface has content and a verdict. "Complete on Etsy" needs owner entry, and its live state is UNKNOWN. |
| F-234 Shop trust architecture | COMPLETE (content) | What is sold, what the buyer receives, delivery, skill-level FAQ, support path, policies. |
| F-235 About / process | COMPLETE | The truth lint passes. ABOUT was made paste-ready. |
| F-236 Shop SEO surface | COMPLETE (prepared) | Reuses `brand.storefront.check_shop_seo`. |
| F-237 Section architecture | COMPLETE | The basket's placement is an owner decision. |
| F-239 / F-293 Mobile and visual inspection | PARTIAL | Pre-launch mock-up at 390 px and 1280 px with no overflow. Live inspection is GATED (`rendered_pages`). |
| F-240 Public identity | Reused | `seller_identity.check_identity`; the shop name still needs owner confirmation. |
| F-515 Shop completeness | PARTIAL | As F-233. |
| F-527 Brand asset health | PARTIAL | The SVG assets are checked for palette, absence of text, crop and contrast. A raster export is pending. |

## Files

Created:
- `src/brambleloop/store_foundation/{__init__,limits,lint,assets,content,readiness,preview}.py`
- `tests/test_v11_store_foundation.py` (20 tests) and `tests/test_v11_store_preview.py` (13 tests)
- `research/final_build/v1_1/STORE_FOUNDATION_REVIEW.md`, this file
- `research/final_build/v1_1/evidence/F_preview_mobile_390_shop.png`, `F_preview_mobile_390_about_policies.png`, `F_preview_desktop_1280_shop.png`, `F_preview_desktop_1280_owner_panel.png`

Modified:
- `src/brambleloop/brand/storefront.py`: added `unwrap_paragraphs()` and made `ABOUT` paste-ready (one line per paragraph). Same words; the existing brand, storefront and shop-package tests pass.

## Provider contract

`brambleloop.store_foundation.preview.summary(db, *, verify_images=False, now=None) -> dict`
- It returns `status` (OK, DEGRADED, BLOCKED or UNKNOWN), `as_of`, `basis` ("measured"), `items` (one per surface plus `listing_images`), and `sources`. It also returns `counts`, `owner_actions`, `preview_path` ("/cc/store-preview"), `products` (3; sizes are not counted), `live`/`published` (both False), and a note.
- It never raises. A broken database gives a degraded but valid answer; an internal error gives UNKNOWN with a reason.
- It accepts a `core.db.Database` or a bare SQLAlchemy `Session`, and works with `db=None`.
- By default the `listing_images` item is `UNKNOWN`, because images are not verified on a summary call (about 10 s). Use `verify_images=True` to render and verify them.
- Current result: **DEGRADED** (FAIL 0, NEEDS_OWNER 9, GATED 2, UNVERIFIED 7, READY 3).

`render_preview(db, viewport="mobile"|"desktop", *, now=None) -> str`
- Escaped HTML (via `app.security.esc`), no `<script>`, no inline handlers, no external URL. Images are `data:` URIs, which the CSP's `img-src 'self' data:` allows; there is an inline `<style>`, which `style-src 'unsafe-inline'` allows.
- An unknown viewport falls back to mobile.
- The first call renders and verifies three 2000 px hero frames (about 10 s). They are cached per process, keyed by CIR fingerprint.

## WIRING REQUEST (lane C / integrator)

Add to `src/brambleloop/app/storefront_api.py`, inside `make_router(db)`, after the `/api/storefront/preview` route. Add `from fastapi.responses import HTMLResponse` to that file's imports.

```python
    @router.get("/cc/store-preview")
    def owner_store_preview(viewport: str = "mobile"):
        """F-926 Owner Store Preview: a not-live mock-up of the whole shop (lane F)."""
        from ..store_foundation import preview as store_preview

        return HTMLResponse(store_preview.render_preview(db, viewport),
                            headers={"Cache-Control": "no-store",
                                     "X-Robots-Tag": "noindex, nofollow"})
```

Also mount it inside the Command Center's own router, if lane C prefers that location. The page links to `?viewport=mobile` and `?viewport=desktop` relative to itself.

**Auth:** the page has no customer data, but it is owner-facing. Gate it like the rest of `/cc/*`, or add `"/cc/store-preview"` to `OPERATOR_GET_ROUTES` in `app/security.py`. The global security headers already apply.

**Command Center tile:** call `brambleloop.store_foundation.preview.summary(db)`. Its `preview_path` links to the route above.

## Tests and runtime proof

The machine has no single interpreter with every locked dependency: the `.venv` has numpy but no sqlalchemy, and `python3` has the reverse. The runs below used
`PYTHONPATH=src:/home/user/Project-Money/.venv/lib/python3.11/site-packages python3`.

- `tests/test_v11_store_foundation.py`: 20 OK, 0 FAIL.
- `tests/test_v11_store_preview.py`: 13 OK, 0 FAIL. Without numpy, the image test asserts the fail-closed WITHHELD path instead of VERIFIED.
- Existing tests for touched modules: see the integrator report (test_brand, test_shop_package, test_storefront_fb4, test_bible, test_cert_takeover, test_deliverable_qa, test_launch).
- `tests/test_vacuity.py`: the v11 files are clean. Three pre-existing findings elsewhere were there before this lane: test_launch0_listing_truth, test_pattern_truth, test_web_security. `tests/test_secret_scan.py` has one pre-existing finding, in test_rc1_ord2.py.
- Runtime: I rendered both viewports. All three Launch-0 hero frames were rendered from the current CIRs and returned **verifier PASS with caption PASS**: market-basket-medium, cloudline-baby-blanket and hexagon-coaster-set. I screenshotted the pages with the preinstalled Chromium, through Node Playwright at `/opt/node22/lib/node_modules/playwright` with `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`; nothing was installed. scrollWidth equals clientWidth at both 390 px and 1280 px.

## Open defects and gaps

- Owner decisions (8) and gated settings (16): see the review.
- Not fixed, because the files belong to other lanes: " -- " typewriter hyphens in `commerce.shop_package`; "its photographs" in `commerce.terms`; the off-palette sage hero background (`visual.render_contract.BACKGROUND`); the weak Cloudline blanket thumbnail.
- No verification here of how Etsy delivers a corrected file to past buyers. The corrections promise is a decided policy, not a verified mechanism.
- The SVG-to-PNG raster export for Etsy upload is not built.
- Etsy field limits other than listing title and alt text are UNKNOWN. They are labelled so and never invented.
