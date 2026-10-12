# Handoff — lane A3 (owner-concept production identity, D-FB-16 item 1)

Branch `claude/w3-A3` (from `claude/visual-investigation`). Full system doc:
`research/final_build/w3/A3_IDENTITY_SYSTEM.md`.

## Requirements
| Requirement | Status |
|---|---|
| Owner concept = PRIMARY (`DIRECTION_ID = "O1-owner-bramble-b"`), D1 kept as research | DONE |
| Hero lockup, horizontal lockup, full monogram, micro-mark, wordmark; colour/mono/reversed | DONE (20 SVG masters in `src/brambleloop/brand/masters/`) |
| Micro-mark from the same B, tested at 40/48/70 px vs raw concept | DONE — 40 px: 65.5% ink ≥ 3:1, median 4.91:1 (raw: 42.2%, 2.44:1) |
| Palette sampled from the concept, fidelity tested | DONE (re-sampled from the sha-verified owner files) |
| Script tagline, open licence, offline | DONE — Allison (OFL), outlined; woff subset bundled |
| Clear space / minimum sizes / palette / type docs | DONE |
| Proof sheets ≤ 6 PNG ≤ 300 KB | DONE (6, 33–88 KB) |

## Files
`src/brambleloop/brand/owner_identity.py` (new), `owner_proofs.py` (new), `identity_system.py`
(primary switched; `get_direction`, `ALL_DIRECTIONS`, `RESEARCH_DIRECTION_ID`, `CLEAR_SPACE`,
`MIN_SIZE`, `monogram_svg`/`micro_mark_svg`/`hero_lockup_svg`, `master_svgs`/`export_masters`,
`font_face_css(extra=)`), `vector.py` (nonzero fill rule), `typeset.py` (merges
`data/glyphs_owner.json`), `fontbuild.py` (owner font build), `directions.py` (`_moved` keeps
fill rule), `comparison.py` (looks directions up via `get_direction`), fonts + OFL texts.

## Tests
`tests/test_w3_brand_owner_identity.py` — 14 tests, all OK. `tests/test_w3_brand_identity.py`
updated for D-FB-16 (status state, judge winner = research D1; the primary now gets the same
small-size gates via `judge.measure_direction`) — 14 OK. Also run green: test_w3_brand_comparison,
test_v11_store_foundation, test_v11_store_preview, test_w3_store_ux_gate,
test_w3_store_ux_structure, test_canon_store_brand_face, test_storefront_fb4,
test_w3_store_copy_routing, test_brand, test_vacuity, test_secret_scan.

## Interface changes for lane B
Compatible: `icon_svg()`, `lockup_stacked_svg(tagline=, transparent=)`, `PALETTE` (same keys
plus new ones), `ROLES` (+`descriptor`, `yarn`, `sage`), `font_face_css()` (still 4 faces),
`css_variables()` (+`--bl-font-script`). The stacked lockup now always carries a script tagline:
lane C's text if the outlined script can set it, else the owner's tagline.

## Open / not verified
Owner has not approved the drawings. No Etsy upload. `banner_png` exporter still absent.
test_w3_store_ux_mobile (browser) not run.
