# Independent security and visual-truth review: W4-PDF1 delta 38c16035..363a467a

- **Reviewer:** an independent Claude Code session on `claude/w4-SECREVIEW-RENDER-363a467`. It did not author the change.
- **Subject:** `git diff 38c16035..363a467a` on `claude/w4-PDF1`. Release `market-basket-small@1.3.0`, `c4aa14a0…`.
- **Prior reviews:** SECREVIEW-RENDER-38c1603 (F1 to F7) and DESIGNREVIEW-basket-1.3.0 (D1 to D4).
- **Date:** 2026-10-31 (UTC).
- **Method:**
  - Detached worktrees at 363a467a (`/tmp/new`), at 38c16035 (`/tmp/old`), and a mutant copy (`/tmp/mut`).
  - scipy and sqlalchemy were installed first (F7 of the prior review).
  - Every number below was measured in this session from rendered bytes or committed PDFs.
  - The probe scripts are reproduced inline.

## Verdicts

| | Verdict |
|---|---|
| **CODE** | **DO NOT SHIP (as is).** Two small, contained fixes are needed (R1 and R2). The verifier is sound and was not loosened, and the drawing is now right. The block is that the guard which makes the label travel with the picture can be bypassed, and no test covers it. |
| **PRODUCT** | **FIT FOR CUSTOMER**, as far as visual truth goes, for the artefacts built at 363a467a. This is conditional on the physical-sample gate, which Etsy requires anyway and which is still pending. Every customer-facing place that shows the rounded rim is labelled as an estimate (hero, scale and angle alt text, listing description, PDF cover, about box, schematic and gallery), or is covered by the listing-level disclosure (CONTENTS preview, R4). Nothing I found shows the buyer an unlabelled shape the product does not have. |

The two verdicts differ because the *current* artefacts are honest, but the code would let a frame without the note reach export. That is a guardrail defect, not a defect in what is on file today. Fix R1 and R2 before the upload path runs for this listing.

## Findings

| # | Severity | Finding | Status of prior item |
|---|---|---|---|
| R1 | **HIGH (blocking code)** | `export_check` takes the "this frame needs the estimate note" requirement from the frame's own manifest field `estimated`. That field is not bound to the bytes, nor re-derived from the CIR. Remove it and the frame exports with no note. The new check is untested: deleting it survives every suite. | F1: partly fixed |
| R2 | **MEDIUM (blocking code)** | `disclosed-render/3.0.0` is still qualified for `market-basket-small`. The 38c16035 *scale* frame (stamped 3.0.0, the widened-rim model, no `estimated`) passes `structural_floor` **and** `export_check` under 363a467a with no note. | F4: partly fixed |
| R3 | LOW | `rim_flats_cm` runs only on oblique views. On the elevation (scale) view no check is emitted at all, although the code comment says "reports UNKNOWN rather than passing". So the scale view cannot catch a rim widened across the flats (this is how R2 gets through). | F2: fixed for hero/angle |
| R4 | LOW | The CONTENTS supplement shows the PDF cover with the rounded rim. Its alt text has no estimate note, and the in-PDF note is illegible at preview size. It is covered by the listing description's "About the shape" line, which is shown on the same page. | F1: residual |
| R5 | LOW | The owner photo shot list (LISTING_PACKAGE §images, shot 3) still asks for "walls standing straight". These are photographs, so they are true by construction, but the brief contradicts the soft-corner model. Reword it to "the wall as it stands; do not straighten it", so a sample is not posed to look like the old prism. | new |
| R6 | INFO | A comment in `disclosed_render.RENDERER_VERSION` is garbled: two `#` comments are concatenated on one line. | new |
| — | — | F3 (limits documented), F5 (source cited with branch and path), F6 ("rise straight up" → "turn up at a defined edge", in all three editions), D3 ("about 0.7 cm tall") | **fixed, verified** |
| — | — | D2 and D4 deferred to W-PHYSFIX | not reviewed (out of delta) |

### R1: HIGH. The estimate note is self-attested by the frame

`disclosed_listing.export_check` (363a467a):

```python
for note in ((frame.get("disclosed_render") or {}).get("estimated") or []):
    if note not in frame.get("alt_text", ""): problems.append(...)
    if note not in (description or ""): problems.append(...)
```

- The list of notes required comes from the manifest that the frame record carries.
- `structural_floor` binds only `image_sha256`, `slug`, `version`, `view`, `role` and `cir_fingerprint`. It then re-verifies pixels against the CIR. Nothing checks that `estimated` is present when `render_contract.rim_softening(cir)` is non-zero for a wall view.
- `platform_policy.release_assets` reads the same field to decide whether the copy disclosure is added, so dropping it also removes the description line.

**Probe** (basket_small, `_frame_record` helper from `test_disclosed_render`; description = `COPY_DISCLOSURE` only, without the estimate line):

| view | manifest as rendered | `estimated` key removed, alt text regenerated |
|---|---|---|
| hero | export **refused** ("estimate note missing from the listing copy") | export **ok=True**, floor PASS; alt text has no note |
| scale | refused | **ok=True**, floor PASS |
| angle | refused | **ok=True**, floor PASS |

**Mutation.** I replaced the loop with `for note in []:`, which disables the check entirely. The mutant **survives**:
- `test_disclosed_render`: 27/27 passing.
- `test_pdf_premium`: all OK.
- `test_disclosed_certified_upload`: 7/7 passing.

No test calls `export_check` on the basket. `test_pdf_premium` asserts only that `alt_text()` *produces* the note, not that export *refuses* without it. The requested check, "mutate `export_check` and confirm a test fails", therefore **fails**.

**Fix (small):**
1. In `export_check`, derive the required notes from the authoritative CIR and the view, for example `required = [K.ESTIMATED_SHAPE] if K.rim_softening(cir) and view in WALL_VIEWS else []`. Union this with the manifest's notes, so a missing key fails closed.
2. Do the same in `release_assets`, or have it read the requirement from the CIR.
3. Add a test that exports a basket hero with (a) the key stripped and (b) the description line removed. Assert that both are refused. Then confirm the loop-deletion mutant is killed.

### R2: MEDIUM. 3.0.0 is still qualified for the basket, and an unlabelled 38c16035 frame passes

`product_authority.QUALIFIED_RENDERERS` keeps `disclosed-render/3.0.0` on the grounds that 3.1.0 is "byte-identical to 3.0.0 for every other product". That is true for the other products. But for `market-basket-small`, "3.0.0" names **two** different drawings: the original prism (4fb6252d) and the widened soft-corner model (38c16035). Neither of them carries `estimated`.

I rendered hero, scale and angle at 38c16035 and ran them through 363a467a's `structural_floor` and `export_check`:

| 38c16035 frame (stamped 3.0.0) | floor under the 3.1.0 verifier | export_check (no note in copy) |
|---|---|---|
| hero | FAIL (rim_flats_cm, stitch_counts) | refused |
| scale | **PASS** | **ok=True, no estimate note anywhere** |
| angle | FAIL (rim_flats_cm, stitch_counts, colour_placement) | refused |

The old scale frame (sha256 `3189554b…`, compared with the current `5a68eb6f…`) visibly draws the wall bowing outward across the faces. That is the widened model F2 rejected, and it would be listed with no estimate label. Any database or store that holds a chain run from 38c16035 (the evidence JSON for that run was rewritten in this delta) can serve it.

On F4's question, "can an old verifier version PASS a 1.3.0 render it should fail?": **no**. Only one verifier exists in code (3.1.0). `structural_floor` always re-verifies live, and stored `verifier_version` values are only recorded (`store_foundation/preview.py`, `image_review.py`), never trusted. The cache key includes `VERIFIER_VERSION`. The exposure is on the *renderer*-qualification side, not the verifier side.

**Fix:** qualify `disclosed-render/3.0.0` only for slugs not in `K.SOFT_CORNER_SLUGS`. With R1's CIR-derived requirement in place, any stale frame is then refused on two counts.

### R3: LOW. `rim_flats_cm` is silent on the elevation view

`_verify_vessel` adds `rim_flats_cm` only `if sa > 0.2:` and has no `else`. The scale view emits `rim_corners_cm` only. The comment ("an elevation sees no depth and reports UNKNOWN rather than passing") does not match the code.

Emitting UNKNOWN on elevation would make the scale floor UNKNOWN, which blocks export, so a different approach is needed:
- either measure the flats on the elevation from the side-face silhouette at rim height; or
- correct the comment and rely on R1 and R2.

Measured at 363a467a:

| view | rim_corners_cm (measured / expected) | rim_flats_cm (measured / expected) |
|---|---|---|
| hero | 15.47 / 15.48 PASS | 13.85 / 13.86 PASS |
| scale | 15.46 / 15.48 PASS | *(not emitted)* |
| angle | 15.47 / 15.48 PASS | 13.86 / 13.86 PASS |

### R4: LOW. The CONTENTS preview shows the rim without its note in the alt text

The CONTENTS frame rasterises PDF pages 1 to 4. The cover render shows the rim. The cover's second caption line, "Rim shape estimated until a sample is made.", is present in the PDF text but is about 4 px tall in the 2000 px frame. The alt text ("Preview of the pattern document. … shown at reduced size.") has no note.

Etsy shows the description on the same listing, and it carries the "About the shape" disclosure, so the buyer is told. For consistency with the rule "every frame showing the rim", append `K.ESTIMATED_SHAPE` to `contents_frame.alt_text` for `SOFT_CORNER_SLUGS`.

## Verification of the author's claims

### F1. Labelled everywhere?

| Place | Note present | How verified |
|---|---|---|
| PDF (US, UK, TEST kit) | yes, 4 times each (cover, about box, schematic, gallery) | pypdfium2 text extraction of the committed PDFs; `idealised` absent; "straight up" absent |
| RECORD-SHEET PDF | 0 (shows no render) | same |
| Listing description | yes: "About the shape: … Rim shape estimated until a sample is made." | LISTING_PACKAGE.md line 128, and `DISCLOSURES["estimated_shape"]` |
| Alt text: hero, scale, angle disclosed renders | yes, the note ends each one (≤ 250 characters) | regenerated with `alt_text()`; LISTING_PACKAGE rows 7, 8, 10 |
| Alt text: detail (base only) | no, correctly (it shows no rim) | `"estimated" not in manifest` |
| Alt text: CONSTRUCTION, COLOUR_CONTEXT, MATERIALS | no; these frames show charts and counts, not the rim | LISTING_PACKAGE rows 11 to 13 |
| Alt text: CONTENTS | **no** (R4) | rendered the frame |
| Can a frame reach export without the note? | **yes** (R1, R2) | probes above; the mutant survives |

### F2. Are the flats held?

- **Model.** `K.soft_radius` moves only points outside the same-perimeter circle Rc, so mid-faces never move. The renderer (`wall_outline`, the top-of-frame bound) and the verifier (`k_at`) both use it.
- **Twin value held.** `rim_flats_cm` measures 13.85 and 13.86 against the twin's 13.86 (2a) on hero and angle.
- **The old widening model fails.** `test_pdf_premium` swaps `soft_radius` back to the 38c16035 formula and asserts `rim_flats_cm` in the failures for hero and angle. Independently, my 38c16035 hero and angle frames fail `rim_flats_cm` under 3.1.0.
- **Tolerances are not loosened.** `EXTENT_REL/PX` and `HEIGHT_REL/PX` are untouched in the diff. The wall-height pixel floor now uses `k_at(top_c.cx)`, which equals cos(camera) at a mid-face, the same as before for the central column.
- The visual comparison (old hero on the left, new on the right) shows the rim is now a rounded hexagon over a hexagonal foot, not a flared near-circle.

### F4. Versions

- Renderer is 3.1.0, contract 3.1, verifier 3.1.0. The test pins were updated.
- Other products' bytes: `test_w4_multipiece.test_single_piece_heroes_are_byte_identical_to_before` pins basket_medium, cloudline, coasters and snowfall: **5/5 passing, unchanged**.
- Gap: R2.

### F3, F5, F6, D3

- F3: the limits are written into the `render_verification` docstring and are accurate against my prior sweep.
- F5: the source is now cited with its file and branch.
- F6: "turn up at a defined edge" is in all three editions.
- D3: "about 0.7 cm tall" is present.

## Tests (363a467a, run one at a time, `PYTHONPATH=src:tests nice -n 19`)

| Test | Result |
|---|---|
| test_pdf_premium | PASS (rc 0, 124 s) |
| test_disclosed_render | 27/27 (115 s) |
| test_w4_fidelity | 22 passed, 0 failed (145 s) |
| test_w4_prodready_contract3 | 6/6 (24 s) |
| test_cert_listing_frames | PASS, 0 failing (99 s) |
| test_search_hero_publish | 4/4 (161 s) |
| test_launch0_listing_truth | PASS, rc 0, all OK (457 s) |
| test_w4_visual_certified_gallery | 7/7 (41 s) |
| test_w4_multipiece (extra, F4 bytes) | 5/5 (13 s) |

Green tests do not clear R1: the mutant that deletes the new check passes every suite above that touches it.

## What would flip CODE to SHIP

1. R1: derive the required note from the CIR and view in `export_check` and `release_assets`, and add a test that kills the loop-deletion mutant.
2. R2: stop qualifying `disclosed-render/3.0.0` for `SOFT_CORNER_SLUGS`, and add a test that a 38c16035-style scale frame is refused.
3. Optionally, R3 (fix the comment or add an elevation flats check) and R4 (CONTENTS alt text).
