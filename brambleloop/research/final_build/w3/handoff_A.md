# Handoff: wave 3, lane A (brand strategy, logo and wordmark, visual identity system)

Branch `claude/w3-A`, based on `claude/v11-CANON` @ f0c2d12. The branch is committed locally and
has not been pushed.

## Requirements addressed

| requirement (directive §2, §5, §7) | status | notes |
|---|---|---|
| 3–5 genuinely distinct directions | COMPLETE | D1 briar-monogram, D2 chain-link, D3 drupelet, D4 tapestry-b (`brand/directions.py`) |
| One direction rebuilt faithfully from the owner's concept | COMPLETE | D1. The B monogram, bramble sprig with blossoms and berries, yarn figure-of-eight to a ball, spaced serif wordmark, CROCHET PATTERNS between hairlines and the sage/cream/rose palette are all original vector work. The owner's PNGs are not embedded or traced. Props with slogans are excluded (usage rule). |
| Solve the 40 px problem | COMPLETE | Separate simplified icon (B in a yarn loop from a ball, leaf pair), iterated 3 times (`brand/iterations.py`, evidence A_5) |
| Icon/monogram, wordmark, palette, type, motif, usage rules as one system | COMPLETE | `identity_system` (13 usage rules, colour/mono/reversed variants) |
| Legal fonts only, no CDN | COMPLETE | All fonts SIL OFL 1.1 with licence files in `brand/fonts/`. Marks are outlined (`data/glyphs.json`), so no `<text>`. Four Latin `.woff` subsets are bundled for page text. |
| Recognisable without text; mono and restrained colour | COMPLETE (measured) | `test_mono_variant_is_one_ink`, mono edge correlation 0.99 |
| Distinctive at 40/70 px, premium at banner scale | COMPLETE (measured) / judged | raster checks plus rubric (`brand/judge.py`) |
| Independent judging with explicit criteria | PARTIAL | The measured criteria are automated. The rubric is the builder's labelled opinion. An independent judge (lane J or the owner) is still required. |
| Blind comparison with premium brands, structural only | COMPLETE | `judge.BENCHMARKS` holds descriptions only and nothing was fetched. A_2 shows the icons under blind labels P–S. |
| Complement Laura | COMPLETE (composition check) | A_4 shows the banner and phone fold with the canonical portrait labelled INTERNAL. Laura usage rules are written. No new Laura images. |
| Winner chosen with reasoning; runners-up kept | COMPLETE | `A_brand_decision.md`; `identity_system.alternatives()` |
| Contact sheets via Playwright/Chromium, ≤6 PNG, ≤300 KB | COMPLETE | 5 PNGs, 72–213 KB each, plus `A_judge_verdict.json` |

## Interface: `brambleloop.brand.identity_system` (exported in the first commit, 72f6538)

- `DIRECTION_ID` is `"D1-briar-monogram"`. `STATUS.state` is
  `RECOMMENDED_PENDING_OWNER_APPROVAL`.
- `PALETTE` holds the named hex colours: forest, sage, sage_mist, rose, rose_deep, rose_light,
  petal, paper, berry, gold.
- `ROLES` holds the semantic web colours: background, surface, text, text_muted, accent,
  accent_text, leaf, rule, berry, inverse_*, focus. Every text pair is at least 4.5:1, and this is
  tested.
- `TYPOGRAPHY` maps display/body/italic/ui to family, CSS stack and bundled file. Related:
  `font_face_css(base_url)` and `css_variables()`.
- The SVG functions are `icon_svg`, `emblem_svg`, `wordmark_svg`, `lockup_horizontal_svg`,
  `lockup_stacked_svg(tagline=...)` and `motif_svg`. Each takes the variant `colour|mono|reversed`,
  plus `transparent=` and `width=`. The general form is
  `mark_svg(kind, variant, direction_id=...)`.
- `icon_png(px)` gives the PNG for the Etsy icon upload. `data_uri(svg)` is also available.
- `USAGE_RULES`, `alternatives()` and `to_dict()` (JSON-serialisable) complete the interface.
- The tagline is a parameter. Lane C owns that copy, and nothing is hard-coded.

## Files

New:
- `src/brambleloop/brand/`: `vector.py`, `typeset.py`, `fontbuild.py`, `directions.py`,
  `iterations.py`, `judge.py`, `identity_system.py`, `data/glyphs.json` (239 KB),
  `fonts/*.woff` (4 files, 12–22 KB each), `fonts/*-OFL.txt` (7 files)
- `tests/test_w3_brand_identity.py`
- `research/final_build/w3/`: `A_build_sheets.py`, `A_shoot.mjs`, `A_brand_decision.md`,
  `handoff_A.md`, `evidence/A_1..A_5*.png`, `evidence/A_judge_verdict.json`

No existing file was modified.

## Tests

- `tests/test_w3_brand_identity.py`: 15/15 OK (about 5 s).
- Existing suites, all with no FAIL lines: test_brand 23 OK, test_bible 13 OK,
  test_storefront_fb4 17 OK, test_v11_store_foundation 20 OK, test_v11_store_preview 13 OK.
  For test_canon_store_brand_face, test_vacuity and test_secret_scan, see the final report.

## Runtime proof

- `A_build_sheets.py` ran: Chromium rendered the shipped SVGs through data-URI `<img>` at 1×, and
  produced 5 sheets. The renders match the Pillow rasters that the tests measure.
- `judge.verdict()` ranks D1 94.8, D2 73.3, D3 73.3, D4 70.9. On measured score alone, D1 (92.9)
  and D2 (93.3) tie; see the sensitivity note in the decision doc.

## Wiring requests (lane B owns `store_foundation/assets.py` and `preview.py`)

1. Replace the rejected mark. In `store_foundation/assets.py`, make `icon_svg()` return
   `identity_system.icon_svg(width=ICON_W)` and build the banner around
   `identity_system.lockup_stacked_svg(transparent=True, tagline=<copy_v2 tagline>)`.
   - `check_icon` and `check_banner` compare against `bible.PALETTE`. Extend the allowed set to
     `bible.PALETTE ∪ identity_system.PALETTE`, or check against `identity_system.PALETTE`.
   - `test_v11_store_foundation` line 184 replaces `#244A3A` to provoke `ASSET_OFF_PALETTE`. Swap
     it to replace `identity_system.PALETTE['forest']` (`#2F3E33`). The intent stays the same.
2. Page CSS: serve `src/brambleloop/brand/fonts/` (for example under `/static/brand/fonts/`). Then
   inline `identity_system.font_face_css('/static/brand/')` and `css_variables()`. This needs an
   owner (lane F) entry in `app/main.py` if a static mount is required.
3. `bible.PALETTE` (PDF and charts) was deliberately left alone. Moving the pattern-PDF palette to
   the new identity is a later, separate change because it affects customer PDFs.
4. Proposed DECISION_LOG entry (the integrator writes it): "D-W3-A1: Brand identity direction
   D1-briar-monogram recommended (pending owner approval); runners-up D2–D4 kept; basis
   research/final_build/w3/A_brand_decision.md".

## Open defects and risks

- At 40 px the icon's silhouette overlaps a plain serif B at 0.483 IoU, so recognition leans on the
  letterform.
- The script tagline from the concept was replaced by Lora Italic, because no OFL script is
  available offline and script fails legibility at phone sizes.
- `mono_edge_correlation` saturates near 0.95–0.99 for every direction, so it discriminates
  weakly. It is kept as a floor check only.
- The motif is functional but simple. It could be refined if the owner wants richer packaging.

## Not verified

- Owner approval.
- An independent (lane J) judgement.
- Any customer or marketplace evidence.
- Etsy's current icon and banner pixel sizes and crop shape (lane I owns these).
- Trademark clearance.
- How the marks look on real phone hardware (only Chromium at 1× was checked).
