# Independent security and visual-truth review: W4-PDF1 delta 363a467a..115464fc

- **Reviewer:** an independent Claude Code session on `claude/w4-SECREVIEW-RENDER-115464f`. It did not author the change.
- **Subject:** `git diff 363a467a..115464fc` on `claude/w4-PDF1`. The fix commit is 39ac0dfe; 115464fc refreshes evidence, the listing package and the audit.
- **Prior review:** SECREVIEW-RENDER-363a467 (R1 HIGH, R2 MED, R3 to R6 lower).
- **Date:** 2026-10-31 (UTC).
- **Method:**
  - Detached worktrees at 115464fc (`/tmp/new`), at 38c16035 (`/tmp/old`, to render the old widened-rim frames) and a mutant copy (`/tmp/mut`).
  - scipy and sqlalchemy were installed first.
  - Every value below was measured in this session. Probe scripts were kept outside the repository.

## Verdicts

| | Verdict |
|---|---|
| **CODE** | **SHIP.** R1 and R2 are fixed and fail closed on every path I tried. R3 is fixed, and the elevation check catches the real 38c16035 scale frame even when that frame is restamped 3.1.0. Nothing at Medium or above remains. There are two LOW findings (one test gap, one fragile truncation) and three INFO items. |
| **PRODUCT** | **FIT FOR CUSTOMER** on visual truth, still **conditional on the physical-sample gate**, which is pending. Every customer-facing frame that shows the rim now carries the estimate note: hero, scale, angle and CONTENTS alt text, plus the listing copy. The only frame without the note is the base plan (detail), which does not show the rim. |

## Findings

| # | Severity | Finding | Prior item |
|---|---|---|---|
| — | — | R1: the note requirement is now derived from slug and view (`render_contract.estimate_notes`). It is used by `export_check`, `alt_text` and `platform_policy._owes_estimate`. | **R1 fixed, verified** |
| — | — | R2: a pre-3.1.0 stamp, or any stamp other than 3.1.0, is UNKNOWN for `market-basket-small` at `structural_floor`. Other products are unchanged. | **R2 fixed, verified** |
| — | — | R3: the elevation now emits `rim_flats_cm` from the top round's central stitch pitch. It fails the widened rim and passes the true one. | **R3 fixed, verified** |
| — | — | R4: CONTENTS alt text carries the note. R5: shot 3 reworded to "the wall as it stands; do not straighten it". R6: comment repaired. | **fixed, verified** |
| N1 | LOW | Reverting `platform_policy.release_assets` to read the manifest's `estimated` field (mutant M5) **survives** the new test. No test exercises `_owes_estimate`. The effect fails closed: copy built without the "About the shape" line is refused by `export_check`. So this is a coverage gap, not a truth gap. | new |
| N2 | LOW | `contents_frame.alt_text` and `launch_imagery.supplement_alt_text` add the note and then silently truncate to `ALT_TEXT_MAX`. With a long enough title the note would be cut off. The upload path compares against the same truncated `expected_alt_text`, so nothing would catch it. The disclosed-render `alt_text` raises `DisclosureMissing` in this case. Supplements should do the same. Today's basket alt texts are 180 (CONTENTS) and 202 (ANGLE) characters, so no harm on file. | new |
| N3 | INFO | `SOFT_CORNER_MIN_RENDERER` is enforced as an exact match (`!=`), not as a minimum. A future 3.2.0 renderer would read UNKNOWN for the basket until the constant is updated. This fails closed; the name is misleading. | new |
| N4 | INFO | The `detail` exemption is keyed on the view name. It is correct today: the vessel `detail` view draws `_draw_plan(..., rings=base)` with `part="base"`, so no wall and no rim. A hero frame relabelled `detail` fails the floor (stitch_count). If a future vessel's detail ever draws the wall, key the exemption on the drawn part instead. | new |
| N5 | INFO | The ANGLE and CONTENTS alt texts decide the note with their own `slug in SOFT_CORNER_SLUGS` test rather than `estimate_notes`. The result is the same today and there is no stored-trust path (see below), but the logic is duplicated. | new |
| N6 | INFO | Sensitivity of the elevation flats check. Its tolerance is max(2 %, 1 px) on the central pitch. The true frame reads +0.65 % (0.8052 against 0.80 cm) and the 38c16035 model reads +5.5 % (0.8437). A widening under about 2 % (about 0.28 cm across the flats) would pass on the scale view. This is the same 2 % envelope the oblique `rim_flats_cm` uses (`EXTENT_REL`), so it is consistent, not loosened. | new |

## 1. R1: can a soft-cornered frame reach export, upload or the listing without the note?

**No, on every path tried.** Product basket_small, the record from `disclosed_listing.build`, and the description containing only the render disclosure (no estimate line).

| Probe | Result |
|---|---|
| hero / scale, `estimated` removed, note stripped from alt text, `cir` given | export **refused** |
| same, `cir=None` (slug taken from the frame or manifest) | export **refused** |
| hero / scale as filed, copy without the note | export **refused** |
| hero / scale as filed, copy with the note | export ok |
| hero relabelled `detail` (role changed to match) | floor **FAIL** (stitch_count), export refused |
| scale relabelled `detail` | floor **FAIL** (extent_cm, …), export refused |
| view renamed `angle`, `None`, `Hero`, `top` | floor **FAIL** (role does not match view), export refused |
| frame `slug` removed | floor FAIL |
| `release_assets` on stripped frames | `estimated_shape` True for hero and scale, False for detail |

`estimate_notes` fails closed: any view other than `detail`, including a missing or new one, owes the note.

**Upload path** (`runtime/etsy_ops`, the single exporter):
- Disclosed renders are re-run through `export_check` with `cir = authoritative_cir(slug, version)`, against the listing copy on file.
- Gallery supplements (ANGLE, CONTENTS and the rest) must carry alt text equal to `expected_alt_text(slug, job)`, which is recomputed from code today. Their bytes are re-verified by `check_supplement`, which redraws ANGLE with the current renderer and requires a byte match.
- So a certificate filed before 39ac0dfe with a CONTENTS alt text lacking the note is now refused at upload, not uploaded on trust.
- Certification itself (`release_gates.disclosed_supplements`) always redraws the supplements and generates their alt text in code; nothing stored is trusted.

| Supplement alt text (basket) | Length | Note |
|---|---|---|
| ANGLE | 202 | yes |
| CONTENTS | 180 | yes |
| CONSTRUCTION / COLOUR_CONTEXT / MATERIALS / SIZING | 169–176 | no (charts and counts; no rim shown) |

**Mutants** run against the new test `test_the_rim_estimate_is_owed_by_the_product_not_by_the_frames_word`:

| Mutant | Result |
|---|---|
| M1: `export_check` loop → `for note in []` | **killed** |
| M2: `export_check` back to the manifest's `estimated` | **killed** |
| M3: R2 block disabled (`and False`) | **killed** |
| M4: elevation flats branch disabled | **killed** |
| M5: `release_assets` back to the manifest's `estimated` | **survives** (N1) |

## 2. R2: can a pre-3.1.0 stamp pass for the basket?

**No.**

`structural_floor` for basket frames as filed, re-stamped:

| Stamp | hero | scale | detail |
|---|---|---|---|
| disclosed-render/3.1.0 | PASS | PASS | PASS |
| disclosed-render/3.0.0 | UNKNOWN | UNKNOWN | UNKNOWN |
| disclosed-render/2.0.0 | UNKNOWN | UNKNOWN | UNKNOWN |
| disclosed-render-assembled/2.0.0 | UNKNOWN | UNKNOWN | UNKNOWN |

`export_check`, `certify_disclosed` (by way of the exporter) and the upload path all require floor PASS, so UNKNOWN blocks every gate.

**Defence in depth.** The stamp is not bound to the bytes, so I re-rendered the real 38c16035 frames and verified them under the 115464fc verifier, as though restamped 3.1.0:

| 38c16035 frame | sha256 | verify | rim_flats_cm |
|---|---|---|---|
| hero | f5ff019b | **FAIL** | 14.37 vs 13.86 |
| scale | 3189554b | **FAIL** (`rim_flats_cm`) | 14.61 vs 13.86 (pitch 0.8437 vs 0.80) |
| angle | d62a93d9 | **FAIL** | 14.16 vs 13.86 |

The scale frame that passed in the prior review is now refused on two independent counts.

**Other products** are unchanged under 3.0.0. For each, floor as filed and floor restamped 3.0.0:

| Product | hero | scale | detail |
|---|---|---|---|
| basket_medium | PASS / PASS | PASS / PASS | PASS / PASS |
| hexagon_coasters | PASS / PASS | PASS / PASS | PASS / PASS |
| cloudline_blanket | PASS / PASS | PASS / PASS | PASS / PASS |

None of them owe a note.

## 3. R3: the elevation flats check

| Frame (115464fc) | rim_flats_cm |
|---|---|
| basket_small hero | PASS 13.85 / 13.86 |
| basket_small **scale** | **PASS 13.95 / 13.86** (pitch 0.8052 / 0.80) |
| basket_small angle | PASS 13.86 / 13.86 |
| basket_medium hero / scale / angle | PASS (18.03, 18.01, 18.03 / 18.01) |
| basket_large hero / scale / angle | PASS (22.19, 22.02, 22.17 / 22.17) |
| 38c16035 widened scale | **FAIL** 14.61 |
| test mutant (`soft_radius` reverted to the widening formula) | **FAIL** |

The new check emits on the other hexagonal vessels too, and it passes there, so their floors are unchanged. Round vessels (key basket) use `_verify_round_vessel` and have no flats.

**UNKNOWN is not-PASS everywhere.**
- `verify` aggregates with `FAIL if any FAIL, else UNKNOWN if any UNKNOWN (or no checks), else PASS`.
- `export_check`, `listing_asset`, `final_image_gate`, `model_photography` and the upload path all test `== "PASS"` or `!= "PASS"`.
- The new branch emits UNKNOWN, never a silent skip, when fewer than three central stitches are found.

## 4. Author's claims

| Claim | Result |
|---|---|
| `estimate_notes` decides, and is used by `export_check`, `alt_text` and `_owes_estimate` | **true** (diff and probes) |
| `SOFT_CORNER_MIN_RENDERER` = 3.1.0 | **true** (exact match; see N3) |
| Scale view emits `rim_flats_cm` or UNKNOWN | **true** |
| PDFs and frames are byte-identical | **true**. No PDF or PNG changed in the diff. The MANIFEST change is `engine_commit` only. Fresh renders hash to 71f6b955 (hero), 5a68eb6f (scale) and 4a1f866f (angle), matching the committed chain-run evidence. |

## Tests (115464fc, run one at a time, `PYTHONPATH=src:tests nice -n 19`)

TESTS_PLACEHOLDER

## Recommended follow-ups (non-blocking)

1. N1: add an assertion that `release_assets` on a frame with `estimated` removed still yields `estimated_shape=True`. This kills M5.
2. N2: in the supplement and CONTENTS alt text, raise rather than truncate when the note would not fit.
3. N3: rename the constant to `SOFT_CORNER_RENDERER`, or compare versions properly.
