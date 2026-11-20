# products/

Product code lives here, one directory per product. If a product needs its own repository, link it from this file with its deploy target and status.

## etsy-templates — MapleSheets (Track A, D-005)
Canadian small-business bookkeeping/tax spreadsheets, sold as Etsy digital downloads.
- **Deploy target:** Etsy (shop not yet open; owner Block 1 in `OWNER_ACTIONS.md`).
- **Status:** all five listings (1-4 + bundle) built, formula-validated, and packaged (copy + images) in `dist/` (gitignored; rebuild with the `build_*.py` / `package*.py` scripts). Etsy API client written and unit-tested. Nothing published yet.
- **Run tests:** `.venv/bin/python products/etsy-templates/test_workbook.py` (listing 1), `test_listing3.py`, `test_listing4.py` (formula validation via the `formulas` engine — see `LESSONS_LEARNED.md` LL-002/LL-009 before adding new lookup formulas), `test_etsy_api.py` (offline, no network).
- **Build:** `.venv/bin/python products/etsy-templates/build_templates.py && package.py` (repeat with `build_listing2.py`/`package2.py` etc. through `build_listing4.py`/`package4.py`, then `package5.py` for the bundle — `.venv` from `.venv-requirements.txt` if it doesn't exist).

## store — Track B e-commerce store (D-009, spec in `store/SPEC.md`)
Capped, staged paid-social dropshipping store (Shopify + CJ + Meta), owner-authorized swing bet.
- **Deploy target:** Shopify (not yet created; owner Block 2 in `OWNER_ACTIONS.md`).
- **Status:** spec and product research only (`SPEC.md`, `PRODUCT_RESEARCH.md`); the Meta Ad Library probe (`intel/adlibrary_probe.mjs`) has run live under an owner-approved permission rule (D-013). No Shopify/CJ/Meta client code built yet — blocked on Block 2A/2B/2C credentials for live calls, but SPEC modules 0-3 can be built offline with fixtures per the spec's own instructions.
- **Run tests:** none yet (no client code).

## pod — print-on-demand line (D-008, candidate detail in `research/candidates/CANDIDATES.md` C19)
Personalized Canadian-gift products (mugs, prints, totes) via Printify, sold through the same Etsy shop as Track A. Design spec and architecture notes: `pod/DESIGN_SPEC.md`.
- **Deploy target:** Etsy, via a Printify-connected shop (optional step in owner Block 1; needs `PRINTIFY_TOKEN`).
- **Status:** Printify API v1 client written and unit-tested (shops, catalog/blueprints, print providers with a Canadian-provider filter, variants, image upload, product create/publish, orders). No live calls made — waiting on `PRINTIFY_TOKEN`. 3 of 5 target designs built and rendered (`build_designs.py`: mug, art print, tote); personalization itself is handled by Printify's own Personalization Studio once configured (not done yet — needs the live connection). Pixel dimensions and listing copy still need the real blueprint spec.
- **Run tests:** `.venv/bin/python products/pod/test_printify_api.py` and `test_build_designs.py` (both offline, no network).
