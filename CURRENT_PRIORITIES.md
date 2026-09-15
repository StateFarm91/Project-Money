# CURRENT_PRIORITIES

_Updated 2026-09-15 (Day 1, evening)_

1. ~~Validate workbook v1~~ done; ~~listing 2 generator~~ done (`build_listing2.py`, validated). Next build item: listing 2 images + package; listing 3 (home-office + vehicle) and listing 4 (instalment planner; verify 2026 brackets first).
2. **Etsy API client** (`products/etsy-templates/etsy_api.py`): PKCE auth URL + token exchange/refresh, `findAllListingsActive` competitor pull, create draft listing, upload file/images, publish, daily stats pull. Unit-tested against recorded fixtures (no live calls until credentials exist).
3. **Listing copy + images** for listing 1 and 2 (titles from competitor keyword neighbourhoods; 13 tags; 6 images rendered from the workbook; AI-assistance disclosure).
4. **Waiting on owner:** `OWNER_ACTIONS.md` Block 1 → then run EXP-001 immediately.
5. **Heartbeat Routine** live (`AUTOMATIONS.md`) so the mission continues without this session.
6. Listings 2-4 generators (quick-method calculator; home-office/vehicle workbook; instalment planner) after listing 1 is published.
7. **POD line (D-008):** Printify API client (`products/pod/`), 3-5 Canadian-gift designs rendered programmatically, product mockups, listing copy; publish when `PRINTIFY_TOKEN` exists. Zero cost until an order.
