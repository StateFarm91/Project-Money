# CURRENT_PRIORITIES

_Updated 2026-09-16T08:40Z (Day 1, heartbeat)_

1. ~~Validate workbook v1~~ done; ~~listing 2, 3, 4 generators~~ all done. Listing 4 (`build_listing4.py`) required fresh 2026 tax research (federal brackets confirmed against CRA's own page; 13 provincial/territorial brackets and CPP/CPP2 rates cross-checked; sources in TAX_REFERENCE.md), validated 0 formula errors across 3 hand-checked income/province scenarios (incl. Quebec abatement and CPP2). Next build item: listing 5, the bundle (1+2+3+4, CA$44) — package the four existing files together with combined copy; no new tax logic needed.
2. **Etsy API client** (`products/etsy-templates/etsy_api.py`): PKCE auth URL + token exchange/refresh, `findAllListingsActive` competitor pull, create draft listing, upload file/images, publish, daily stats pull. Unit-tested against recorded fixtures (no live calls until credentials exist).
3. **Listing copy + images** for listing 1 and 2 (titles from competitor keyword neighbourhoods; 13 tags; 6 images rendered from the workbook; AI-assistance disclosure).
4. **Waiting on owner:** `OWNER_ACTIONS.md` Block 1 → then run EXP-001 immediately.
5. **Heartbeat Routine** live (`AUTOMATIONS.md`) so the mission continues without this session.
6. ~~Listings 2-4 generators~~ all done. Listing 5 (bundle) still open.
7. **POD line (D-008):** Printify API client (`products/pod/`), 3-5 Canadian-gift designs rendered programmatically, product mockups, listing copy; publish when `PRINTIFY_TOKEN` exists. Zero cost until an order.
8. ~~Track B product research~~ done (D-011). Open follow-ups: trademark/business search for "Pine and Nook" before domain purchase; CJ verification of the three SKUs once the API key exists.
9. **Track B build (after Block 2A):** Shopify store via Admin API (theme, policies with honest delivery times, products, markets CA/US), CJ product import; Meta creatives (Pillow images; fal.ai + ffmpeg videos) once `FAL_KEY` exists; support agent Worker once Cloudflare + Anthropic exist; ads launch only when all three parts are done and the lifetime caps are set.
10. **Product-intelligence pipeline (D-012, SPEC §8):** build `products/store/intel/` (Ad Library probe, Trends, competitor catalogues, scorer, queue builder) with fixtures; produce the first `PRODUCT_QUEUE.md` from ≥ 100 discovered candidates before any ad spend; re-run each heartbeat. Track A effort ≤ 20% of heartbeat time once listings are live.
