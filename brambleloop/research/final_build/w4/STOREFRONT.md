# W4-STOREFRONT: customer storefront preview and owner Store area

Branch `claude/w4-STOREFRONT`, from `claude/w4-INTEG2` @ 68224ac. Nothing here is published, written to Etsy or spent. Auth, CSRF and step-up are unchanged. Brand assets and Laura's identity are untouched; Laura does not appear in the customer view.

## Update after merging w4-INTEG2 @ a5b889b (CAP-1, ETSYREL, OWNERHOME, IMAGES, ONDEMAND)

CAP-1 is merged. The owner approved the cap change from 5 to 8 products as **configuration
only** (`launch0.CATALOGUE_FLOOR_APPROVED=True`), which brings the 3 prepared products into
Launch-0 scope. The products themselves are **not approved, drafted or published**.

- **How the 3 products are labelled.** The Command Center now labels them **"In Launch-0 scope (CAP-1); not approved: gates pending"** (status `CAP1_SCOPE`). The earlier "awaiting decision D-FB-9" label is gone. The owner decision card reads "CAP-1: products in Launch-0 scope — NOT APPROVED: GATES PENDING".
- **Customer page.** They stay off the customer page unless every gate passes (`storefront.customer_gates_pass`): W4-IMAGES' computed customer approval (listing-set certificate for the exact release, parity fully judged, an owner publication grant) **and** a verified, complete hero image. None of the 3 passes today. The browser checks and `test_w4_storefront` assert both points.
- **Incomplete hero images (W4-IMAGES).** A hero that shows fewer pieces than the pattern makes (`pieces_finding`) is never shown to customers. The customer page shows the placeholder instead. The owner still sees the image, tagged "incomplete hero", and gets a readiness blocker.
- **Prices.** They come from what the store grid reports (`content.launch0_products`). The placemat shows its plan price, CA$5.00.
- **Store overview.** The ETSYREL "Etsy connection" card (re-check / connect, with step-up) is kept on the Store overview as its own section, next to the live-shop observation. Each overview section is a separate, commented function, so the SHOPSYNC "Live shop settings" card can be added cleanly.
- **First load never blocks the phone.** On a cold server process, rendering and checking eight pictures takes about 20–30 s. That was enough to time out the real-backend check on the Store tab. The full catalogue is now computed once in a background thread and cached for 120 s. A request waits at most 4 s for it, then gets the quick catalogue: the same products, prices and listings, with pictures marked NOT_CHECKED and quality UNKNOWN (never a pass), plus a "Still checking" note. The phone also stops waiting on the catalogue after 8 s and shows a "PREPARING" card. With this, the real-backend check passes cold (44 OK).
- **Pre-existing failure fixed.** `test_w4_images::test_candidates_cover_the_preview_products_and_the_proposals` was already failing on a5b889b, because the opening grid grew to 8 under CAP-1. `image_review.candidates()` now marks as customer-shown exactly the storefront view's set, so the test passes with its assertion unchanged.
- **Merge conflicts.** In app.css, api.js and cc_mock/data.mjs I kept both sides. In store.js I kept this branch's layout and added the ETSYREL card.

## A. Customer storefront preview

New variant `storefront` (`store_foundation/storefront.py`). It is now what the Command Center opens by default: `/cc/store-preview` with no `variant` parameter. `preview.render_preview()` keeps its own default of `standard`, so existing callers are unaffected. The v1, brand-face, v2 and compare variants all still render, so nothing is deleted.

### Customer view (mobile-first)

The page has these parts, in order:

- **Preview label and header.** A "Preview — not live" ribbon says plainly that this is not the real Etsy storefront. Below it: banner, shop icon, name and tagline, then the line "New shop, no reviews yet".
- **Announcement and category chips.** Chips appear only for populated categories (`navigation.public_nav`, D-FB-18 item 3). Hidden categories are listed in the owner panel.
- **"All patterns" grid.** Two columns on a phone, four on desktop. Each card shows the verified rendering, its category, a short name, the price and **"Digital download (PDF pattern)"**, plus a concise one-sentence description.
- **Images.** Only `preview.hero_frame` frames that verify on their exact bytes are shown. Anything else gets a neutral yarn placeholder labelled "Picture coming soon"; the unverified asset is never embedded. Each verified image is embedded once, as a stylesheet rule shared by its card and its sheet.
- **Product sheets.** Each has the image, name, price, digital and US/UK terms label, description, sizes and an inactive "Add to basket" button.
- **Customer disclosures stay in place.** Each sheet carries its listing-level disclosures: digital item, AI-assisted design, and "rendering, not a photograph". The full store disclosure appears under "About these patterns". Etsy requires AI disclosure (`etsy_constraints.ai_disclosure`, VERIFIED).
- **Closing sections.** "Made to be followed" trust lines, About, policies (returns open by default), licence, FAQ, support.

### Owner evidence panel

This is a folded `<details>` at the foot of the page, labelled "not part of the shop page". Everything internal moved here:

- the readiness table and its findings;
- owner actions, the settings checklist, image verification with sha256, and where titles and prices come from;
- the evidence behind each trust line (quality mechanics);
- hidden categories;
- the customer-copy source;
- what Etsy lets the shop control.

Tests confirm the customer part contains no jargon (`preview_v2.JARGON`), no `copy_v2.BANNED_TECHNICAL_TERMS`, no sha/verifier/gate/basis words and no unfilled copy placeholder.

### Copy (COPY lane)

The `claude/w4-COPY` branch does not exist yet. Every customer string goes through `storefront.copy_text(key)`, which tries sources in this order:

1. `store_foundation.copy_w4.CUSTOMER_COPY[key]` (the COPY lane's module, once it exists);
2. lane C's `copy_v2.customer_copy()[key]`;
3. otherwise a visible `[copy: key]` placeholder.

Elements carry `data-copy="<key>"`. The keys in use are `tagline`, `announcement`, `section:<slug>`, `trust_headline`, `trust:<key>`, `about`, `delivery`, `returns`, `privacy`, `store_disclosure`, `support_contact`, `faq_q:/faq_a:<key>`, and the new per-product keys `product_name:<slug>` and `product_summary:<slug>`. Until the COPY lane supplies the per-product keys, they fall back to the plan title and the first sentence of the description.

### What Etsy actually lets a shop control

`storefront.etsy_controls()` is built from `integrations.etsy_constraints`, retrieved 2026-10-06. Rows marked VERIFIED quote an Etsy help-centre or Open API sentence; rows marked UNKNOWN carry no number. Highlights:

- **Shop page:** shop name (4–20 characters), shop title (55), About (5,000), up to 5 About photos and a video.
- **Banner and logo:** big banner (1600×400 recommended, 1200×300 minimum), logo (500×500).
- **Sections and featured listings:** 20 sections of 24 characters each, with empty sections hidden; 4 featured listings.
- **Listings:** title (140), 13 tags of 20 characters each, 20 photos and 2 videos per listing.
- **Digital files:** up to 5 per listing, 20 MB each, filename 70 characters and not editable after upload.
- **Disclosure:** AI disclosure is required.
- **Limits not on file (UNKNOWN):** announcement length, FAQ limits, description length.

**Drawn by Etsy, approximated here (UNVERIFIED, since no Etsy source grants control):** page layout, colours, fonts, card design, navigation and filters, card text (Etsy shows the listing title; the preview shows short names), and listing pages.

## B. Command Center Store area (phone)

Routes are in `views/store.js`. Everything is read-only except the existing live-shop observation.

- **`#/store` (Overview).** It contains:
  - sub-navigation;
  - **Launch readiness**: collection 8, Launch-0 5 / proposed 3, pictures verified, pattern quality OK and Etsy connection, plus the launch verdict;
  - **Your store decisions**: D-FB-9 catalogue floor, and publication approvals with a link to Approvals;
  - the **visual catalogue**;
  - **Storefront review**: opens the customer view, with earlier designs folded;
  - the **live-shop observation form**, kept;
  - **Technical evidence**: all 12 earlier sections, folded.
- **`#/store/collection`.** The dedicated **8-product launch collection**: 5 Launch-0 products plus the 3 CAP-1 products, labelled "In Launch-0 scope (CAP-1); not approved: gates pending". Before CAP-1 these were "Proposed". They are off the customer page until every gate passes.
- **`#/store/product/<slug>`.** Product page with the verified image, price, digital label, description and sizes.
  - **US/UK pattern PDF previews**, rendered now from the CIR; the sold file is the released, hashed PDF.
  - Readiness blockers, each with who clears it.
  - Listing and price, read-only, with "on Etsy: UNKNOWN".
  - Folded technical evidence: compile/certify, release hash, picture check and sha, title and price sources, CIR fingerprint.
- **`#/store/listings`.** Every title and price with its character count and its source.
- **`#/store/storefront`.** The preview plus "What Etsy lets the shop control".

**API (owner session through the `/api/cc/` gate):**

- `GET /api/cc/store/catalogue`: data from `store_foundation.owner_store`, cached for 120 s. It reports the Etsy connection from `oauth_credentials`; with no database it reads UNKNOWN, never "connected".
- `GET /api/cc/store/image/{build}`: returns PNG only for a collection build whose frame verified. Anything else gets a 404, never a substitute.
- `GET /api/cc/store/pdf/{slug}?terms=US|UK`: returns an inline `application/pdf`. An unknown product or terminology gets a 404, and a refusal gets a 409.

## Tests

| Test | Result |
|---|---|
| `tests/test_w4_storefront.py` (new): variant/default; self-contained and labelled; no internal material in the customer view; owner panel folded and complete; verified-only images with placeholder; populated categories; disclosures; copy keys; Etsy controls; 8-product catalogue; image/PDF refusals; API needs a session, image/PDF served, preview default | 11/11 |
| `tests/fixtures/cc_mock/check.mjs` at 390 px | 181/0 (23 new storefront checks) |
| `real_backend_check.mjs` against this branch through `real_backend_bridge.py` | no FAIL |
| Existing tests, one at a time with a private TMPDIR: `test_v11_store_preview`, `test_w3_store_ux_structure`, `test_w3_store_ux_mobile`, `test_canon_store_brand_face`, `test_w3_laura_cc_access`, `test_v11_wiring_cc`, `test_w3_priv_leak`, `test_w3_laura_memory_isolation`, `test_route_auth_default_deny`, `test_customer_data_auth`, `test_w4_ccux`, `test_v11_pwa_static` | all pass |

New browser checks at 390 px:

- store sub-navigation; readiness tiles; D-FB-9 shown;
- verified pictures load through the owner session; a withheld picture shows a placeholder and is **never requested**;
- the preview opens the storefront variant; evidence is folded and the observation form is kept;
- the collection shows 5 + 3; an unknown price reads Unknown, never CA$0.00;
- the product page shows the image, the digital label and US/UK PDF links, and the PDF is served as `application/pdf`;
- listing views are read-only; listings for all 8;
- Etsy controls show UNKNOWN, never a number;
- no horizontal scroll; tap-size floor met.

## Screenshots (390 px), in `research/final_build/w4/storefront_screens/`

| View | Before (68224ac) | After |
|---|---|---|
| Customer preview | `before/customer_preview_390_top.png`, `before/customer_preview_390_full.png` (v1 "standard", the previous owner default) | `after/customer_preview_390_top.png`, `after/customer_preview_390_full.png`, `after/customer_preview_owner_evidence_open_390.png` |
| CC Store (mock API) | `before/cc_store_390_top.png`, `before/cc_store_390_full.png` | `after/cc_store_390_top.png`, `after/cc_store_390_full.png` |
| CC Store, real backend with real renders | — | `after/real_cc_store_*_390_{top,full}.png`: overview, collection, product, listings, storefront |

The mock serves a 1×1 stand-in PNG. The `real_cc_*` shots come from the actual app through the bridge, with the 2000 px verified renderings.
