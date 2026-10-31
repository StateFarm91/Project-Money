# Independent design review: `market-basket-small@1.3.0` (D-W4-OWNER-BASKET-1.3.0)

- **Date:** 2026-10-31 (UTC)
- **Reviewer:** independent crochet construction and product review (W4-DESIGNREVIEW). No source
  was changed, and no PR was opened. Only this report is pushed, to
  `claude/w4-DESIGNREVIEW-basket-1.3.0`.
- **Subject:** `claude/w4-PDF1` at `4fb6252d`. The design commit is `69516b8f`; the editions,
  kit and listing are from `a4ddfb61`, `6846fe8`, `e3bb63f` and `4fb6252`.
- **Release hash:** `c4aa14a000e5439b0dfb32812039178b5efed6b4ba840efef7e7c64a6b7c659c`.
  I recomputed it through `launch0.cir_for("basket_small")` → `write_pattern(…, "US")` →
  `gates.certificate._release_hash`. **It matches.**
- **Method:**
  - I re-ran the prior review's probe (`construction_review_probes/probe_basket_small.py`),
    retargeted to 1.3.0, with extra checks for the loop on each row and for medium and large.
  - I checked out the parent commit (`69516b8^`) and compared medium and large there.
  - I extracted the text of the US, UK, proof and kit PDFs (`pdftotext -layout`) and diffed them.
  - I looked at the cover (p1), schematic (p3) and gallery (p12) pages as images.
  - I read the listing package, the chain evidence, both manifests and the diff of `69516b8f`.

## Verdicts

| | Verdict |
|---|---|
| **Design** | **SOUND.** The one approved change is implemented exactly, it is correct crochet, and every count and number is unchanged and traces to the twin. |
| **Product** | **FIX BEFORE SALE.** The renders still draw a faceted hexagonal prism with hard vertical corners up to the rim. The listing frames carry this to Etsy with no "idealised" statement. The minimal fix is in the **renderer** (soften the wall corners toward the rim). It is **not** a further design change. Sale is separately blocked by the physical sample, Etsy O-1 and the provisional kit, all already recorded in the listing package §9. |

## 1. Construction

### 1.1 The change, and nothing else

`products/vessels.build_basket`: for `size in DEFINED_EDGE_SIZES = ("small",)`, wall round 1
(Rnd 11) is `Op("sc", 60, loop="back")`, with the row note "back loop only: the unworked front
loops make the edge the base folds up along". Every other wall round is still `Op("sc", 60)`
(both loops).

Probe output:
- twin loops on Rnd 11 = `{'back'}`; on Rnds 12–22 = `{'both'}`;
- `geometry.corners()` = 6;
- compile OK, with no errors and no warnings;
- `reverse.compare` = `[]`.

**Nothing in the construction is invented beyond the approved change:**
- The base (Rnds 1–10), the colour bands (15–16, 18–19), the join and the finishing text are
  byte-identical in content.
- The added text is consequential copy only:
  - the row note;
  - a "Back loop only" technique entry (`publish/abbreviations.py`);
  - a rewritten base-to-wall tip (`publish/tips.py`);
  - a reworded render caption (`publish/pdf.py::_render_gap`).
- The row note is inside the hashed pattern text. That is correct, because it is an instruction.

### 1.2 Does a back-loop-only Rnd 11 make a defined fold, with the six-sided base kept?

**Yes.**
- Working the first even round into the back loops leaves the front loops of Rnd 10 as a free
  ridge on the right side. The fabric hinges at that line. This is the standard basket and
  slipper technique for a crisp base edge.
- Because the rounds are joined and not turned, the right side faces the maker throughout.
  The ridge therefore lands on the outside of the basket, as the technique note and the tip say.
  The wall folds away from the maker, so the right side ends up outside.
- The base is unchanged. It has 6 stacked increase columns, and the flat-hexagon check from the
  prior review still applies (apothem growth 0.693 cm against a row height of 0.725 cm, ratio 0.96).
- The fold follows the outline of the Rnd 10 hexagon. The base edge is therefore a **defined
  hexagonal fold**, which is what the twin's instantaneous 90° turn at ring 11 assumes
  (`radius_delta` 0.000, `rise` 0.725).

**The wall corners are unchanged from 1.2.x.** No round above Rnd 10 has a stitch at the corner
columns.
- The crisp hexagonal fold helps the lower wall hold the hexagon for the first few rounds.
- Towards the rim the tube relaxes towards a rounded hexagon. Rim across-points tends from
  16.0 cm towards the 15.3 cm circle figure; across-flats stays about 13.9 cm.
- The PDF now states this honestly (§3).

### 1.3 Counts

| Check | Recomputed | Twin / PDF | OK |
|---|---|---|---|
| Base | 6, 12 … 60 (+6 a round, Rnds 1–10) | same | ✅ |
| Wall | 60 on every round of Rnds 11–22 (12 rounds), Rnd 11 included | `(60 sts)` on each | ✅ |
| Total | 330 + 12 × 60 = **1,050** | 1,050 twin cells | ✅ |
| Back-loop stitches | 60, all on Rnd 11 | twin `loop=back` × 60 | ✅ |

### 1.4 Wording for a confident beginner

- **US, p7:** "Rnd 11 (cream): sc in back loop of next 60 sts. (60 sts) -- back loop only: the
  unworked front loops make the edge the base folds up along." This is correct and unambiguous.
- **UK, p7:** "dc in back loop of next 60 sts". This is the correct UK term. A US→UK diff of the
  full text shows only terminology differences (sc→dc, inc→dc inc); the technique note and the
  tip are identical.
- **Technique note, p6:** it defines front and back loop relative to the maker ("front loop,
  nearer you"), says to work the stitch "as usual", and says the front loop "stays on the outside
  as a ridge". This is correct and sufficient for a confident beginner.
- **Tip, p9 ("Turning the base into the wall"):** it is accurate. It replaces the 1.2.x
  gradual-turn tip, which would now be wrong.
- **"Rise straight up" (p2 and p3):** this was F2 in the prior review. It is now accurate for a
  back-loop fold.
- **p5 checkpoint "Round 11 … 1 cm tall":** this is now physically reachable (one sc row, about
  0.7 cm, standing). "1 cm" rounds 0.72 up by about 40 %, under a header that says "If it does not,
  the difference is gauge". See finding D3 (minor): "about 0.7 cm" or "the first wall round is
  standing" would be safer.

### 1.5 Medium and large are truly unchanged

At `69516b8^` and at `4fb6252` I got the same results:

| Size | Version | US release hash | US text sha256[:16] | UK text sha256[:16] | Loops |
|---|---|---|---|---|---|
| medium | 1.2.1 | `db568b84…53efea0` | `803a4c848522f54f` | `459fdba334c9d4e3` | `{both}` |
| large | 1.2.1 | `0400b906…d881d18` | `96b04114fdff29a7` | `1ba74eb219be9ca0` | `{both}` |

They have no row notes. The new tip branch only fires when the first wall round's loops are
`{"back"}`, and the old soft-fold branch is kept for them. **Unchanged.**

## 2. Numbers

The independent recomputation starts from `COTTON_GAUGE`: 12.5 sts and 13.8 rows per 10 cm,
stitch width 0.80 cm, row height 0.725 cm.

| Quantity | Independent | Twin 1.3.0 | PDF / listing / kit | OK |
|---|---|---|---|---|
| Perimeter | 60 × 0.80 = 48.0 cm | 48.0 | n/a | ✅ |
| Across points | side 8.0 × 2 = **16.0** | 16.0 | 16.0 everywhere | ✅ |
| Across flats | 8.0 × √3 = 13.86 → **13.9** | 13.9 | 13.9 | ✅ |
| Height | 12 × 0.725 = **8.70** | 8.7 | 8.7; "about 9 cm" in the size note and p5 | ✅ |
| Cream | (222 × 6.2 + 54 × 12.4 + 480 × 6.2) × 0.8 cm = **40.2 m** | 40.2 | 32–48 m (±20 %); kit 40.2 | ✅ |
| Wine | 240 × 6.2 × 0.8 cm = **11.9 m** | 11.9 | 10–14 m; kit 11.9 | ✅ |
| Total | 52.1 m (42–63 m) | 52.1 | 42–63 m; DK about 60 m | ✅ |

**Is 8.7 cm now honest? Yes. It is now a central estimate, not just an upper bound.**
- In the prior review the rounded fold cost about 0.5–0.8 cm (F4). The back-loop crease removes
  most of that loss, so the real fabric now matches the twin's sharp-fold model.
- What remains is measurement definition, not error:
  - table to rim on the outside reads slightly **more** than 8.7 cm, by about the base thickness
    (≈ 0.3–0.5 cm);
  - inside depth reads slightly **less**.
- Both are well inside `physical.SIZE_DISAGREEMENT` (12 %).
- The figure is still labelled "computed, not yet measured on a worked sample", which is correct.

**Traceability.** Every printed number traces to the 1.3.0 twin and CIR: points, flats, height,
yarn by colour, round counts, colour rounds and gauge. The yardage model ignores the loop, which
is correct, because a back-loop sc uses essentially the same yarn. Known untraced constants carry
over from 1.2.0 and are not new: hook 5.0 mm (constant across yarn weights), 2.15 make-hours, and
the joining sl st and ch 1 not counted in yardage (prior review F5 and F6).

## 3. Truth in the visuals

**What the renders draw** (cover p1, schematic p3, gallery p12; `visual.disclosed_render._draw_vessel`):
- a faceted hexagonal **prism**;
- 6 flat wall panels with hard vertical corner edges running full height;
- the rim the same 16.0 cm hexagon as the base;
- a square base edge.

**Against 1.3.0:**
- **The base edge is now true.** The back-loop fold makes the defined edge drawn.
- **The base outline is true** (p3 "the base, from above" and the p12 close view are exact).
- **The wall corners are still not true.** No wall round keeps them, and the rim relaxes towards a
  rounded hexagon. The front view and the cover both show a crisp hexagon at the rim and 6 sharp
  vertical arrises. **That is a shape the product does not have.**

**In the PDF this is disclosed adequately:**
- the cover second caption line: "the base edge is defined as drawn; the wall's corners soften
  toward the rim";
- the long statement on p2, p3 and p12: "idealised in one respect …".

The PDF passes.

**On Etsy it is not disclosed:**
- The chain's certified listing set (`evidence_PDF1_basket_1.3.0_chain_run.json`) puts a
  `DIGITAL_TWIN_RENDER` at **position 1, role `hero`**. The chart render is at position 6.
- Their in-pixel label and the alt text (package §8, frames 7–10) say only "Digital rendering of
  the pattern's finished design, not a photograph … About 16 x 8.7 cm".
- The description's image bullet adds "Every stitch in it is drawn from the pattern itself", which
  implies the shape is exact.
- Nowhere in the listing does it say "idealised" or "corners soften toward the rim".
- A buyer sees a sharp hexagonal prism, and will make a basket that is hexagonal at the base and
  rounder at the top.
- This is a **moderate** truth-in-advertising gap. It is not a gross one: size, colours, base and
  proportions are right.

**Does this still block sale? Yes, as currently packaged.**
- The listing package's own rule (photos first, an unedited real photo at #1, renders never first)
  would reduce the risk once a photo exists.
- But the certified set the system would upload still leads with the render, and its frames are
  uncaptioned about the gap.
- The project's non-negotiable "never claim … until verified" makes an undisclosed idealised hero
  a blocker.

**The minimal fix is the renderer.**
- In `_draw_vessel`, when the wall rounds carry no corner stitches (for this CIR, `corners()`
  counts only the base increases), interpolate each wall ring from the base polygon towards a
  rounded polygon or circle at the rim.
- This is a regeneration of the listing and PDF images. The pattern does not change, the release
  hash does not change (the renders are not in the hashed text), and the stitch arithmetic does
  not change.
- Once it is done, the "idealised in one respect" captions can be retired, and `_render_gap`
  would return None.
- **Interim acceptable alternative (cheaper):** carry the short idealised statement into the
  listing frames' in-pixel label and alt text, and into the description's image bullet. Do this
  only if the renderer change slips, and note that it still leaves an uncaptioned-looking hero.
- **A further design change is not recommended.** Keeping corners up the wall needs corner
  stitches or a surface slip-stitch column on every wall round. That changes the counts, the
  yardage, the difficulty and the hash, for little gain in a bread basket. The prior review §4
  said the same.

## 4. Version linkage

| Item | Version | Hash | OK |
|---|---|---|---|
| US, UK and proof PDFs | 1.3.0 on every page footer (`market-basket-small@1.3.0`), the release block and the cover | MANIFEST `release_hash` = `c4aa14a0…`; file sha256 values match the MANIFEST (`5ac0375a…`, `b49cebde…`, `496316be…`) | ✅ |
| Listing chain evidence | `pattern_version` 1.3.0; all 6 `listing_assets` `version: 1.3.0`; `listing_set_certificate` 1.3.0 | `c4aa14a0…` (×3) | ✅ |
| `LISTING_PACKAGE.md` | 1.3.0 throughout; 1.2.0 and 1.2.1 appear only as labelled history | `c4aa14a0…` in the identity table and the photo brief | ✅ |
| Kit: TEST PDF, RECORD SHEET, KIT_MANIFEST, BASKET_KIT_FOR_OWNER_APPROVAL | 1.3.0 | `c4aa14a0…`; TEST `edc25c5a…` and SHEET `f8072169…` match the manifest | ✅, with D4 below |

- **D4 (minor):** the kit TEST PDF prints **"RELEASED 2026-10-07 · version 1.3.0"** (p2 and the
  release block). The cause is `quality/tester_kit.py:406`, which hard-codes
  `released_on=date(2026, 10, 7)`. The customer editions say 2026-10-31.
  - 1.3.0 did not exist on 2026-10-07.
  - Otherwise the TEST PDF text equals the customer US edition (a diff shows only those two date
    lines).
- **Info:** the stale 1.2.1 kit PDFs are still in `tester_kit/`. They are labelled and superseded,
  but they could be picked up by mistake.

## 5. Tester kit

**What the record sheet measures for 1.3.0:**
- base across the points and the flats;
- "wall height (cm)";
- base sits flat;
- "holds its shape";
- grams, hours and photos (shots 2 and 3 are top-down and side at table level).

**What 1.3.0 claims that it does not measure:**
- **Base edge.** There is no field for whether the fold is crisp at Rnd 11, the one property the
  design change exists to deliver. A rounded edge would still be marked "holds its shape: yes".
- **Corners at the rim.** There is no `corners_at_rim` or rim across-points field. That measurement
  is exactly what would confirm or retire the "corners soften toward the rim" caption, and calibrate
  the renderer fix in §3.
- **Wall-height method.** It is still undefined: outside or inside, table to rim or fold to rim. As
  §2 explains, with a crisp fold the outside and inside readings differ by the base thickness.

The kit is labelled **PROVISIONAL**. `BASKET_KIT_FOR_OWNER_APPROVAL.md` line 3 says it lacks the
W-PHYSFIX fields (wall-height method and the rest). That is honest, but **the kit does not yet
measure what 1.3.0 claims.**

Add before commissioning the make:
1. `base_edge`: crisp / rounded, plus the round at which the wall is vertical.
2. `corners_at_rim`: yes / no, plus `rim_across_points_cm`.
3. A fixed wall-height method: outside, flat table to top of rim, at the middle of a flat side.
   Optionally add `inside_depth_cm`.

This is prior-review F7, still open.

## 6. Tests

Run one at a time on `claude/w4-PDF1` at `4fb6252d` with
`cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`:

_Partial: test results pending (run in progress)._

## Findings

| ID | Severity | Finding |
|---|---|---|
| D1 | **Moderate (blocks sale as packaged)** | The listing renders (certified hero at position 1, plus frames 7–10) draw hard vertical wall corners and a 16.0 cm hexagonal rim. The product's corners soften toward the rim. On Etsy there is no "idealised" disclosure, and the description says every stitch is "drawn from the pattern itself". Fix: renderer wall-corner softening in `_draw_vessel`; no design change. |
| D2 | **Moderate (test coverage)** | The provisional kit has no base-edge field, no rim-corner field and no defined wall-height method, so it cannot confirm the property 1.3.0 was made for (prior F7, open). |
| D3 | Minor (copy) | p5 "Round 11 … 1 cm tall", under "the difference is gauge", rounds 0.72 cm up by about 40 %. Prefer "about 0.7 cm" or "the first wall round stands up". |
| D4 | Minor (version linkage) | The kit TEST PDF prints "RELEASED 2026-10-07 · version 1.3.0". The date is hard-coded at `quality/tester_kit.py:406`. |
| D5 | Info | The superseded 1.2.1 kit PDFs remain beside the 1.3.0 kit in `tester_kit/`. |
| D6 | Info (carried) | Carried from 1.2.0: hook 5.0 mm is a constant for every weight; the yardage omits the join sl st and ch 1 (about 0.85 m, runs low, inside ±20 %); make-hours 2.15 is untraced (prior F5, F6). |
| — | Resolved from the 1.2.0 review | F1 (soft fold) is resolved by the back-loop Rnd 11. F2 ("rise straight up", the contradictory tip) is resolved. F3 is half resolved: the base edge is now true, and the wall corners remain (D1). F4 (8.7 cm only an upper bound) is resolved: 8.7 cm is now a central estimate. |
