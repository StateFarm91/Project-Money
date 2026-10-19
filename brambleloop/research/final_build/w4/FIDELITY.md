# W-FIDELITY: independent product-fidelity verifier for generated images (OWNERIMG E3)

- **Branch:** `claude/w4-FIDELITY`, from `origin/claude/w4-VISAUTO` 56691f84.
- **Production:** 1b21e81 (SHADOW). Nothing was deployed, nothing was spent, no provider was
  called, no credential was changed, and nothing was written to production.
- **Not touched:** `visual/outfits.py`, `visual/styling.py`, `creative/flux_prompt.py` and
  `creative/failure_codes.py` (W-VISAUTO's files).
- **Why:** without E3, every real autonomous run blocked at stage 4 with "no qualified
  verifier for generated product images". The verifier now exists. A run with real judges
  still blocks at stage 4 until the vision judge is funded, because craft texture is a vision
  question; the block message now names that check.

## 1. What was built

`src/brambleloop/visual/fidelity.py` (`product-fidelity/1.0.0`).

- It reads only the image bytes and the certified CIR.
- It never reads the prompt, the references, the generator's receipt or any verdict the
  generator wrote (`reads_generator_claims: False`).
- Every check returns PASS, FAIL, UNKNOWN or NOT_APPLICABLE, together with the values it
  measured.
- The verdict is the worst check. UNKNOWN is never PASS, and a PASS never carries a code.

### 1.1 Expected values, all derived from the certified CIR (`expectation`)

| Fact | Source |
|---|---|
| Palette | `cir.colors`, converted to CIE Lab |
| Pieces, `make`, finished cm | `pattern_refs._components` (compiler and digital twin) |
| Appearance: colour per position | `charts.render_fabric` / `render_round_fabric`, the same renderer behind the `layout` reference. Each row is resampled to its stitch-weighted compiled height (`render_verification.expected_model`, PT-08), so a band of sc rows is as short as the yarn makes it. |
| End bands, edging and ribbing declared, cable columns | `pattern_refs.fabric_facts` |
| Motif repeat | `pattern_refs.technical_rules` `repeat`: stitches across ÷ repeat stitches, e.g. Cloudline 99/9 = 11 |

### 1.2 Anchor checks on the product-only unfolded flat lay (`verify_anchor`)

| Check | Method | Fails with |
|---|---|---|
| `isolation` | A plane is fitted robustly to the border ring (outer 2 %). The background must be plain: p90 ≤ 10 dE76, with ≥ 70 % of the ring as inliers. Every yarn colour must be ≥ 12 dE76 from the background. Foreground is > 0.45 × that separation. Contact shadows (the background darkened, same chroma, off every yarn colour) are removed. A piece touching the frame edge is treated as cropped. | UNKNOWN (cluttered, low-contrast or cropped) |
| `piece_count` | Connected components ≥ 0.2 % of the image, compared with the sum of `make`. Touching pieces (one blob > 1.6 × median) or an extra small object read UNKNOWN. | `WRONG_PIECE_COUNT` |
| `<piece>:flat` | The piece's area must be ≥ 93 % of its minimum-area rectangle (rotating calipers on the hull). Round pieces need solidity ≥ 0.93. Below that the piece is folded, turned, curled or occluded, and it is not measured through. | UNKNOWN + `UNVERIFIABLE_COUNT` |
| `<piece>:aspect` | Rectified long/short against the twin's cm, ±10 % (round pieces ±15 %). | `WRONG_ASPECT_RATIO` |
| `<piece>:palette` | K-means in Lab seeded from the declared colours. Then a per-channel gain in linear RGB, bounded to [0.6, 1.6] (illumination). Each cluster centre must be ≤ 15 dE76 from its hex. A pixel is off-palette when it is > 22 dE76 from every colour and every two-colour mix. A row or column ≥ 50 % off is a stripe, which FAILs. Unstructured off-palette > 3 % is UNKNOWN (occlusion, prop or invented motif). | `OFF_PALETTE_COLOUR` |
| `<piece>:colour_layout` | Per-row palette shares compared with the CIR render (total-variation distance), with ±2 % alignment, over the 4 dihedral orientations that keep the rows axis. Mean TV must be ≤ 0.20 and ≤ 8 % of rows may have TV > 0.5. A declared colour below 25 % of its expected share is missing. | `WRONG_COLOUR_LAYOUT` |
| `<piece>:end_band_top/bottom` | Applies to every declared plain band of ≥ 3 rows. Each interior band row must be ≥ 75 % band colour. The band width is measured the same way on the CIR render and must be within ×0.6–1.5 of it. | `INVENTED_END_BAND_TREATMENT` |
| `<piece>:edges` | Applies when the CIR declares no edging. The outer 4 % row-end strip (after a 1.5 % inset) is compared with the same strip of the CIR render, using colour shares plus normalised L* per column. It FAILs when the mismatch is > 0.30 and > 2 × the interior mismatch + 0.1. | `INVENTED_EDGING` |
| `<piece>:repeat_count` | Column signal over body rows (the declared colour with the most column variance, or L* for relief-only fabric such as cables). Autocorrelation is searched over ±60 % of the expected period. The check needs autocorrelation ≥ 0.40, \|count − round\| ≤ 0.30 and ≥ 1.5 px per stitch. The estimator is first run on the CIR's own render, and it must recover the declared count there; otherwise it is not qualified for that product. | `WRONG_REPEAT_COUNT`; low confidence is UNKNOWN + `UNVERIFIABLE_COUNT` |
| Round pieces | A radial colour profile (20 bins) against the round render. A mismatch only in the outer bins is an edging. | `INVENTED_EDGING` / `WRONG_COLOUR_LAYOUT` |
| `craft_texture` | Vision (§1.3). | `WRONG_CRAFT_TEXTURE` (or `INVENTED_EDGING`) |

**Tolerance reasons:**

- 22 dE76 for off-palette pixels and 15 dE76 for cluster centres are both under half of the
  smallest within-product palette distance in the catalogue. That distance is cream/forest at
  70.8; cream/ink is 82.2 and cream/wine is 80.7. A cluster therefore cannot match two
  declared colours.
- The 22 dE76 threshold sits above the ±10–15 dE76 that yarn shading spans under soft light.
- ±10 % aspect: blocking variation is about ±5 % and a 10° camera tilt is about ±3 %. A
  square drawn instead of 4:5 is −18 %.
- None of these was tuned to make a frame pass. The calibration perturbations pass with
  margin.

### 1.3 Vision second

Craft texture (crochet vs knitting, ribbing, knitted rope cables) is asked **blind**:

- `craft_prompt` names no product fact.
- `compare_craft` compares the reading with `fabric_facts` deterministically, which is the
  `visual.inspect` "compared, not asked" rule.
- `GatewayVisionJudge` is gated on `image_vision`. It is budgeted exactly as `inspect`
  (`check_budget`, reservation, `_bill` to `quality_director`/`asset_inspection`).
- With the gate closed it calls nothing and reads UNKNOWN. A test asserts no provider call.

### 1.4 Lifestyle images (`verify_lifestyle`)

All three of the following are required, and anything missing is UNKNOWN:

1. **Anchor:** a PASS anchor for the same release, read from the learning rows (`_best`).
2. **Region palette:** a palette check inside a declared `product_region`.
3. **Consistency:** a vision consistency reading against the anchor bytes.

Geometry is never claimed from a lifestyle image.

### 1.5 Wiring (no gate relaxed)

- **`candidate_gates.RealJudges.product_truth`:**
  - The verifier's verdict replaces `structural_floor`'s UNKNOWN ("no qualified producer for
    generated frames"). That replacement is the purpose of E3.
  - A floor FAIL (for example F-753, the wrong stitch scale) stays FAIL.
  - For LIFESTYLE, `lifestyle_evidence` still applies on top. Pattern-derived references
    still FAIL Product Truth there (a test asserts it).
  - The fidelity codes are reported in `codes`, which feeds the existing repair router and
    `UNVERIFIABLE_COUNT` handling.
- **`publication_verdict`** is unchanged. F-852 refuses every generated frame however
  faithful it is. A test asserts this for lifestyle, detail and colour_context frames with a
  PASS anchor.
- **`image_production`:**
  - The anchor's learning row now carries the fidelity codes.
  - Regeneration after a fidelity FAIL sends the targeted repair when every code has a route
    (`repair_routes`). It stays within `MAX_ATTEMPTS_PER_ROLE`.
  - The stage-4 UNKNOWN block names the unknown checks and what they need (for example
    "craft_texture needs a vision judge").
  - `_best` exposes a `fidelity` summary.

## 2. New failure codes (owned here until W-VISAUTO folds them in)

`fidelity.LOCAL_CODES`, all in category `product_fidelity`:

- `WRONG_ASPECT_RATIO`
- `OFF_PALETTE_COLOUR`
- `WRONG_COLOUR_LAYOUT`
- `WRONG_REPEAT_COUNT`
- `WRONG_PIECE_COUNT`

`fidelity.ALL_CODES` is the shared set plus these five, and nothing is redefined (a test
asserts it).

**Routing:**

- They have no repair route yet, so `_repair_for` returns None for them. Regeneration is
  then a plain retry within the cap, which is the existing behaviour.
- To route them, W-VISAUTO should add them to `creative/failure_codes.PRODUCT_TRUTH_CODES`
  and `repair_routes.ROUTES`, each as a prompt negative.
- Until they are in `failure_codes.ALL_CODES`, `image_stages.fidelity_verdict` refuses them.
  The orchestrator does not call it with these codes today.

## 3. Calibration (tests/test_w4_fidelity.py, offline)

**Positives** are synthetic flat lays rendered from the certified CIR:

- Products: Cloudline, the reading-nook wrap and the hexagon coaster set.
- Every row is at its compiled height, with yarn texture and a contact shadow, on a plain
  taupe surface.
- Each is checked under six perturbation sets: none; blur 2 px; a 30 % lighting gradient; a
  6° rotation; JPEG q60; and rotate −3° + blur 1.5 + gradient 0.2 + JPEG q75.
- Result: **all PASS.** Measured, for example: Cloudline repeat 11.0 (confidence ~1.0), wrap
  cable columns 8, coasters 4 pieces.

**Negatives:** each one FAILs with its own code.

| Defect | Code |
|---|---|
| Ink stripe inside Cloudline's 6-row cream end band; forest stripe inside the wrap's 4-row cream band | `INVENTED_END_BAND_TREATMENT` |
| 3 % cream border on Cloudline's row ends; 6 % ribbed forest border on the wrap (same colour, texture only) | `INVENTED_EDGING` |
| 10 motif repeats instead of 11 (Cloudline) | `WRONG_REPEAT_COUNT` (measured 10) |
| Mustard rows in the body | `OFF_PALETTE_COLOUR` |
| Cloudline squashed to 1:1 | `WRONG_ASPECT_RATIO` (1.00 vs 1.217) |
| 3 of 4 coasters | `WRONG_PIECE_COUNT` |

**UNKNOWN cases:**

- Wrap with its cable relief flattened: UNKNOWN `UNVERIFIABLE_COUNT`.
- A turned-under corner: `flat` reads UNKNOWN.
- A brown object over the body: `palette` reads UNKNOWN.
- A background within 12 dE76 of cream: isolation reads UNKNOWN.
- A cropped piece: UNKNOWN.

**Vision:**

- With no judge, or a closed `image_vision` gate: `craft_texture` reads UNKNOWN, so the
  verdict is UNKNOWN, and no call is made.
- A "knitting / ribbing / knitted_rope" reading gives FAIL `WRONG_CRAFT_TEXTURE`.

**The owner's wrap image** (`flux_experiments/2026-10-19_reading_nook_cable_wrap/output_image.png`):

- As an anchor: isolation reads UNKNOWN, because it is not a plain-background flat lay.
- As a lifestyle image: UNKNOWN with no anchor, with a non-PASS anchor, and even with a PASS
  anchor and a product region but no vision reading.
- With a judge that reports what the owner saw: FAIL with `WRONG_CRAFT_TEXTURE` and
  `INVENTED_EDGING`.
- It is never PASS.

**Wiring:**

- A faithful anchor plus a vision reading passes stage 4, and the run moves on to
  `load_laura_references`.
- Without a vision judge, stage 4 blocks. The block names craft_texture and the vision judge,
  after 1 call and with no exhaustion.
- A striped anchor is regenerated with a targeted `INVENTED_END_BAND_TREATMENT` repair, then
  blocks exhausted after 3 attempts. Learning counts the code 3 times.
- Publication stays refused by F-852.

## 4. False-pass risk: what this checker cannot see

1. **Stitch identity.** Knitted, woven or printed fabric in the right colours and layout
   passes every deterministic check. Only the vision judge stands between such an image and
   a PASS, and its reading is itself a model judgement. The question is asked blind and
   compared deterministically, but a judge that misreads crochet as crochet is a false pass.
2. **Same-colour texture inventions.**
   - Ribbing, bobbles or a different stitch inside an end band of the right colour.
   - An edging in the body colour whose texture does not change the row-end luminance
     profile.

   The ribbed-border test passes because ribbing modulates L* per column. A subtler texture
   may not.
3. **Narrow edgings,** under the 1.5 % inset (about 1.2 cm on Cloudline).
4. **Rows are not counted.** The row-direction check is a colour profile.
   - A wrong number of rows in a single-colour body is invisible, beyond the ±10 % aspect.
   - A wrong number of thin stripes is caught only when the stripes drift out of phase by
     more than the TV tolerance.
5. **Counts on other axes and on round pieces.**
   - Counts are checked only along the axis where the CIR declares a repeat.
   - On round pieces, only the number of pieces is counted (no ring or round count).
   - Products with no horizontal repeat (ornaments; the wrap's body rows) get no count.
6. **Colours between palette colours.** A colour on the line between two declared colours
   reads as a mix of them, so a grey stripe on cream/ink is not flagged as extra. The layout
   and end-band checks catch it only where it lands in a band or shifts the row profile.
7. **Illumination absorbs uniform shifts.** A product rendered uniformly in a slightly
   different shade (within the [0.6, 1.6] per-channel gain) is accepted as lighting.
8. **Lifestyle geometry.** A lifestyle image is never rectified or counted. Its fidelity
   rests on the anchor plus one vision consistency reading.
9. **Calibration is synthetic.** The positives come from the same renderer the expectation
   uses, perturbed. No real FLUX flat lay exists yet (no paid call was made). The first paid
   product-only render must be run through `verify_anchor` and recorded before any threshold
   is trusted on real output. A real image that FAILs a good product is a cost (a
   regeneration), not a false pass. A real image that PASSes a bad product is the risk, and
   §4.1–4.7 are where it would come from.
10. **Back of the piece.** Only the face that is shown is measured.

## 5. Findings for other owners (not changed here)

1. **`pattern_refs` layout reference row heights (W-FLUXAPI/W-VISAUTO).** The layout reference
   (`_render_layout`) stretches uniform chart rows to the twin's height. The physical piece
   has stitch-weighted rows. The reference therefore draws end bands too tall:
   - Cloudline's 6 sc rows are 6.0 % of the height in the reference and 4.5 % physically
     (×1.33).
   - The wrap's 4 sc rows are 2.6 % in the reference and 1.7 % physically (×1.47).

   A generator that copies the reference faithfully will draw bands close to this verifier's
   ×1.5 limit. The fix is to render the layout reference with compiled row heights, as
   `tests/test_w4_fidelity._weighted_rows` does.
2. **Flat-lay background (`image_stages.FLAT_LAY_SCENE` / `flux_prompt`).** The brief asks for
   "a plain, matte, neutral surface". A light neutral such as #D9D4CC is 11.9 dE76 from cream,
   so isolation reads UNKNOWN for every cream-bearing product. The brief should name a
   mid-tone surface (L* about 45–60) at least 25 dE76 from every palette colour, chosen from
   the CIR palette. For example, the taupe #7A746C is ≥ 28 dE76 from cream, ink, wine and
   forest.
3. **`candidate_gates.binding` `cir.fingerprint()`.** `CIR.fingerprint` is a property, so the
   call raised, was swallowed, and `cir_fingerprint` was always None.
   `campaign_consistency`'s CIR comparison was therefore vacuous. This is fixed here
   (§6, F-FID-1).

## 6. Closures

- **E3** (OWNERIMG §9): an independent fidelity verifier for generated product images.
  - Deterministic anchor checks: `fidelity.verify_anchor`.
  - Vision craft texture: `fidelity.craft_texture` / `GatewayVisionJudge`.
  - Lifestyle evidence: `fidelity.verify_lifestyle`.
  - Wired as Product Truth: `candidate_gates.RealJudges.product_truth` / `fidelity_reading`.
  - Wired as the stage-4 gate: `image_production` `fidelity_gate` via the anchor's
    `product_truth`.
  - Tests: `tests/test_w4_fidelity.py`.
- **F-FID-1:** `binding` now records the real `cir_fingerprint`.

## 7. Still needs a vision judge (blocks until `image_vision` is funded)

- `craft_texture` on every anchor. Every real stage 4 therefore reads UNKNOWN today, and the
  run blocks with a named reason, no spend beyond the one generation, and no notification.
- `anchor_consistency` on every non-anchor generated frame.
- A `product_region` detector for lifestyle frames. Today it is declared by the caller, and
  none is declared by the generator, so `region_palette` reads UNKNOWN.

## 8. Tests

See the commit that records the results.
