# W4-SAMPLE: physical-sample packages for the owner's review

**Status: prepared, nothing sent.** Nobody was commissioned, contacted or paid, and nothing was bought. No database was written and no `src/` behaviour was changed. Both tester calls are drafts waiting for the owner.

- **Branch:** `claude/w4-SAMPLE`, cut from `origin/claude/w4-INTEG8-next` at `b0133916`. Today is 2026-10-27 (UTC).
- **How every figure was produced:** by the repo's own deterministic code, run at `nice 19`. No test suites were run. The code paths are:
  - `products.launch0.cir_for`
  - `cir.compiler.compile_cir`
  - `cir.twin.build_twin`
  - `gates.certificate._release_hash` (the content hash, through `quality.tester_kit.content_hash`) and `gates.certificate.certify`, run in memory with no database
  - `gates.risk_matrix.matrix_for`, `first_customer_requirement` and `owner_action_spec`
  - `quality.physical.assess`, used only for the simulations in §3.3, which are labelled as simulations
  - `quality.tester_kit.build`
  - `publish.pdf.build_pattern_pdf`
- **To regenerate:** `cd brambleloop && nice -n 19 python3 research/final_build/w4/tester_kit_coaster.py [--refresh-basket]`. This needs `reportlab`; the repo venv has 5.0.1. The script writes the coaster kit and re-checks the basket kit. With the flag, it also rebuilds a stale basket kit in place.

**Labels:**
- **COMPUTED**: produced by repo code today.
- **FROM REPO**: stated in a committed file.
- **ESTIMATED**: not sourced, or the code itself calls it an assumption.
- **PENDING**: waiting on another worker's conclusion.

---

## 0. What changed since the earlier record, and three things the owner should know first

1. **The basket kit's test PDF was stale. It is rebuilt here; the content hash is unchanged.**
   - The content hash `1ddde587…3991` still equals the computed hash (COMPUTED), as `LAUNCH_PATH.md` found.
   - The test PDF's bytes did not match a rebuild. The committed file was `5d4578d2…` and a rebuild today gives `a724cbae…`.
   - A text diff shows that the pattern instructions are identical. Only the renderer's boilerplate changed after the kit was cut on `bb0f43d0` (W4-COPY "store copy v3" and the support-scope block). The old PDF still printed superseded wording, for example "corrections and revisions are free forever".
   - A tester must work the text a customer will receive, so the kit was rebuilt in place by `tester_kit.build`. In `KIT_MANIFEST.json`, only the TEST.pdf digest changed. The record sheet is byte-identical (`335fd7aa…`).
   - The rebuild is deterministic: a second run reproduces every digest.
2. **The code accepts a physical test only for a whole object, never for a swatch.**
   - `runtime.release.handle_physical_record` calls `quality.physical.assess`. That function divides the measured yarn by the twin's yarn figure for the **whole pattern**, and `cir.twin._yardage` multiplies that figure by `Component.make`.
   - A swatch, or one coaster out of four, therefore gives a factor below `FACTOR_FLOOR` 0.4. The result is `SAMPLE_FACTOR_IMPLAUSIBLE` (ERROR), which means `passed=False`.
   - A half set does worse. It passes with a false factor of 0.50, which would then halve the yardage figures for every `dk cotton:sc` pattern (simulated in §3.3).
   - So "a swatch may be enough" is not true under the current code, even though the risk matrix asks only for `partial_physical`. **Both kits are full makes, with scope `full_make`.** A full make satisfies `partial_physical` (`risk_matrix.satisfies`).
   - `owner_action_spec`'s CA$32.40 swatch price buys evidence the intake would reject (engineering gap G1, §6).
3. **The coaster set is not the quicker or cheaper sample.**
   - It is the smallest *piece*, but the set is 4 pieces, 672 stitches and 3.46 h (COMPUTED by `seasonal.leadtime` via `launch0.make_hours`).
   - The basket is 1 piece, 1,050 stitches and 2.15 h, because the coasters have more ends and joins per stitch.
   - At the code's own rates, the coaster ceiling is **CA$92.03** against the basket's **CA$59.65**.

---

## 1. Package A: `market-basket-small@1.2.0`, Crochet Hexagonal Bread Basket

### 1.1 Identity and digests (COMPUTED)

| Item | Value |
|---|---|
| CIR | `products.vessels.build_basket("small")` via `launch0.cir_for("basket_small")`, slug `market-basket-small`, version **1.2.0** |
| Product / listing | candidate `nursery-nesting-baskets` (small variant); plan price CA$6.50 |
| Content hash (`_release_hash` of the US written pattern, which certification binds evidence to) | `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991` |
| In-memory certification (`gates.certificate.certify`, no db) | granted; `release_hash` = content hash; only finding `ORIGINALITY_DURABLE_EVIDENCE_UNCHECKED` (no db) |
| Product Truth (`launch0.product_truth`) | `passes_gates=True` |
| Test PDF `market-basket-small-1.2.0-TEST.pdf` (9 pages, released_on 2026-10-07) | sha256 `a724cbae5d58ff469a991668d257f54dce57c7e0d0437bcb323ecca2bfb72b0c` (was `5d4578d2…` before the rebuild) |
| Record sheet `market-basket-small-1.2.0-RECORD-SHEET.pdf` | sha256 `335fd7aa9c65a0b1ab52119db02fd644e327206b76a4dc80a3769f29c7bfcf76` |
| Risk class (`risk_matrix.matrix_for`) | declared B, derived B (`dimensional_form`, twin shape `vessel`), **effective B**; `required_physical = partial_physical`; automated threshold unmet (`effective_class_a`) |
| First-customer requirement (`first_customer_requirement`) | `partial_physical` of this content; held: none |

The test PDF comes from the customer PDF renderer (`publish.pdf.build_pattern_pdf`) for this release, with `released_on` fixed at 2026-10-07. It was not byte-compared against a production `assets.built` PDF, because that needs a production readback. The **content hash** is what binds the evidence, and it is what the record sheet prints.

### 1.2 Tester instructions

Files are in `tester_kit/`. The protocol is printed on the record sheet:

1. Weigh each full ball and record the ball band (grams and metres).
2. Work a 10 × 10 cm sc swatch. Record stitches and rounds per 10 cm, and the hook. **Add at send time: weigh each ball again after the swatch and use that as the start weight.** The printed sheet does not say this. If it is not done, about 8.6 m of swatch yarn (172.5 swatch stitches × 0.0496 m per stitch, both COMPUTED) is counted as basket yarn. That inflates the calibration factor by about 16.5% (8.6 ÷ 52.1); see gap G2.
3. Make the basket exactly as written. Note every guess, re-read or rip-back, with the round number. **The printed sheet truncates this step at 118 characters ("…with th").** The full text is in `KIT_MANIFEST.json`.
4. Weigh what is left of each ball. Grams used = start minus end, per colour.
5. Measure the base across the points and across the flats, and the wall height, in cm, without stretching.
6. Record the total hours, and whether you followed the instructions exactly.
7. Photograph the basket on a plain surface, top and side, in daylight.
8. Return the sheet and photos. The operator enters them through `POST /api/physical-test` with `scope: full_make` and `content_hash: 1ddde587…`, and through `POST /api/physical-photo`. The payload is built by `tester_kit.intake_payload`.

The person: one independent adult crocheter who is **not the owner** (F-071). They should be confident with sc in joined rounds, six-point increases and turning a base into walls, should read US terms, and need a 1 g scale. Time: 2–3 h plus about 15 min.

### 1.3 Yarn and materials (from the CIR and twin, COMPUTED)

| | Value | Source |
|---|---|---|
| Yarn | "worsted cotton", weight `worsted` (gauge `yarn_weight: medium`, CYC 4), 2 colours: cream and wine | `cir.materials`, `cir.gauge` |
| Fibre | **cotton, from the yarn name only.** `Material.fibre_content` is empty in the CIR. The kit's "100% cotton" is the kit's wording, not a CIR field. | CIR |
| Yardage | cream **40.2 m**, wine **11.9 m**, total **52.1 m**, ±20% (`twin.yardage_tolerance` 0.2) | `build_twin` |
| Hook | **5.0 mm** (`gauge.hook_mm`); the PDF allows "whatever hook gets you the gauge" | CIR |
| Notions | tapestry needle, 4 stitch markers, scissors; 1 g kitchen scale and a cm tape (tester's own) | `tester_kit.MATERIALS` |

### 1.4 Required measurements and tolerances

The tolerance is `quality.physical.SIZE_DISAGREEMENT` = 12% of the twin figure. Anything outside it is a `SAMPLE_SIZE_DISAGREES` ERROR.

| Measurement | Twin (COMPUTED) | PASS band (±12%) | Payload field | Checked by code? |
|---|---|---|---|---|
| Base across the points | 16.0 cm | 14.08–17.92 cm | `measured_width_cm` | yes |
| Wall height | 8.7 cm | 7.66–9.74 cm | `measured_height_cm` | yes |
| Base across the flats | 13.9 cm | 12.23–15.57 cm (package rule, same 12%) | `notes` | **no**; the operator reads it |
| Circumference | 48.0 cm | 42.24–53.76 cm | `measured_around_cm` | yes if given; the kit does not ask for it |
| Yarn factor (measured m ÷ 52.1) | 1.0 | **code:** 0.4–2.5 (`FACTOR_FLOOR/CEILING`), i.e. 20.8–130.3 m; **stated claim:** ±20%, i.e. 41.7–62.5 m | `grams_by_color` + ball band | factor bounds yes; ±20% no |

A factor that is plausible but outside ±20% still passes. It then becomes a calibration that rewrites `worsted cotton:sc` yardage (§1.8).

### 1.5 Gauge and construction checks

- **Gauge:** CIR gauge is **12.5 sts × 13.8 rows = 10 cm in sc**, 5.0 mm hook. Record the swatch on the sheet.
- **Progress checkpoints**, printed in the PDF's "Checking your progress":
  - R1: 6 sts, about 2 cm across, flat.
  - R5: 30 sts, about 8 cm across, flat.
  - R11: 60 sts, about 16 cm across, 1 cm tall.
  - R16: 60 sts, about 4 cm tall.
  - R22: 60 sts, about 9 cm tall.
- **Construction:** the increases stack into six corners, so the base is a hexagon, not a circle, and lies flat through round 11. The walls rise straight, with no flare and no pull-in, at 60 sts for rounds 12–22. The contrast (wine) rounds sit where the PDF says. A deviation goes in the notes, with the round number.

### 1.6 Photographs

**The protocol's photo evidence** (#64, `publish.physical_upgrade`):
- the finished basket, top and side, on a plain surface in daylight;
- intake by `POST /api/physical-photo {slug, sha256, source: "tester", rights_basis}`. With `rights_basis: tester_agreement`, which is the tester's separate photo choice in the consent text, a photo becomes a `PHYSICAL_PRODUCT_PHOTO` frame in the PROOF job. Without a rights basis it is received and held, never used.

**Likely listing shots: pending image-policy conclusion.** The role names come from `visual.shot_plans.ORDER`. Etsy's size and format needs are being settled by another worker.
- **hero:** the basket styled with bread or rolls;
- **proof:** the physical photo itself;
- **scale:** the basket beside a hand or a standard loaf;
- **detail:** close-up of a stacked-corner increase and the colour change;
- **angle:** three-quarter view showing wall height;
- **construction:** base from below, showing the hexagon;
- **colour_context:** cream and wine together.

LIFESTYLE is "not drawable" by disclosed renders, and PROOF/FIT are photograph-only (`shot_plans`). A real photo is the only way to fill those slots.

### 1.7 Acceptance criteria

**What the code decides.** `PhysicalTest.passed` is binary (`quality.physical.record`). It is true only when all of these hold:
- the factor is within 0.4–2.5;
- there is no ERROR finding: no `SAMPLE_UNKNOWN_COLOUR`, no `SAMPLE_NO_COMPARISON`, and no `SAMPLE_DEVIATED` (instructions not followed);
- `size_agrees` is not False, meaning every measured dimension is within 12%.

**There is no PARTIAL state in the code.** The three levels below are this package's reading of the code for the owner:

| Level | Meaning | Code result | Gate effect |
|---|---|---|---|
| **PASS** | `passed=True`, scope `full_make`, content hash `1ddde587…`; the across-the-flats figure is within 12%; tester notes report no pattern error | row binds (`bind_physical_evidence`) | first-customer `gauge_and_size_claims` → **PASS**; readiness `physical_calibration` met (≥1 passed test); `risk_based_physical_evidence` met **for this release only** |
| **PARTIAL** (package label) | `passed=True`, but one of: the notes report an unclear or wrong round; the across-the-flats figure is outside 12%; or a dimension is within 12% but beyond the 10% stated-dimension tolerance (`risk_matrix.DIMENSION_TOLERANCE`, F-117) | row binds; a `SAMPLE_TESTER_NOTES` WARNING is recorded | the gate reads PASS. **Owner review decides** whether to list as is, or fix the text first. A fix is a new release with a new hash, so it needs a re-test. |
| **FAIL** | `passed=False`: a size outside 12%, an implausible factor, a deviation, or an unknown colour | row stored, binds nothing ("did not pass") | `gauge_and_size_claims` stays **UNRESOLVED** → `first_customer.blocking` non-empty → `store.publish` refuses (A9) |

**The level the first-customer gate needs.** For class B, `first_customer_requirement` needs **`partial_physical`** of this exact content, at code-PASS (`passed=True` and bound). The full make held here satisfies that.

Even with nine areas at PASS, `first_customer.NEVER_AUTHORISES` applies: PASS is "evidence for an owner review, not a substitute". The `etsy_remote_state` deadlock D1 in `LAUNCH_PATH.md` still blocks independently.

### 1.8 Cost in CAD (ESTIMATED: no tester rate has ever been paid)

**The code's ceiling** is `gates.risk_matrix.owner_action_spec` at `TESTER_FEE_CAD_PER_HOUR` 20.0 and `YARN_CAD_PER_METRE` 0.06. The code itself labels both as estimates.

```
tester time  2.15 h (launch0.make_hours) x 1.3 = 2.795 h x CA$20/h = CA$55.90
yarn         52.1 m (twin) x 1.2 = 62.52 m x CA$0.06/m           = CA$ 3.75
ceiling                                                            CA$59.65   (= owner_queue tester_outreach, = KIT_MANIFEST)
```

**Reimbursing whole balls**, using `tester_kit.MATERIALS` estimated retail of CA$5.00 per ball, CA$6.00 for the hook and CA$4.00 for notions:

```
fee CA$55.90 + 2 balls CA$10.00                      = CA$65.90   (exceeds the CA$59.65 ceiling by CA$6.25)
fee CA$55.90 + full materials list CA$20.00           = CA$75.90   (tester owns no tools)
```

The approved ceiling covers yarn at a per-metre rate, not at the price of whole balls. **Recommendation:** ask the owner to approve **CA$66.00**: the fee plus two balls, with the tester's own tools. Alternatively, keep CA$59.65 and reimburse yarn per metre, but say so in the call.

Owner time: `owner_queue` lists 25 minutes, and `risk_matrix.OWNER_MINUTES` is 5.

### 1.9 Expected turnaround (ESTIMATED; there is no recruitment data in the repo)

| Step | Time |
|---|---|
| Owner decision `tester_outreach` | 25 min (FROM REPO) |
| Post the call and recruit an applicant (Ravelry) | 2–7 days (ESTIMATED) |
| Tester window | ≤ 14 days (the call's term); the make itself is 2.15 h computed, "2–3 h" in the kit |
| Operator intake (`physical.record` is a queued job) | same day |
| **Total** | **about 1–3 weeks** from the owner's yes |

### 1.10 If the sample fails

- **Recording:**
  - The row is stored with `passed=False`.
  - A size disagreement also writes `physical.size_disagreement` and files a `DefectReport`. That opens a **P2** incident. One report does **not** halt publication: `IncidentTracker` sets `halts_publication` only at 3 reports. This contradicts the `handle_physical_record` docstring ("halts its publication"); see gap G4.
  - **The listing is still blocked**, because `gauge_and_size_claims` stays UNRESOLVED and the first-customer gate refuses publication.
- **Fix path** (patterns are software releases):
  1. Correct the generator (`products/vessels.py` `build_basket`: gauge, counts or size note), or the renderer if the text was unclear. Never patch the PDF or the listing.
  2. Bump to a new version (1.2.1 or 1.3.0), which changes the content hash.
  3. Re-certify with `gate.certify` (compile, reverse compile, twin, risk matrix) and rebuild assets. The listing-set certificate, search certificate and PDF hashes rebind to the new release.
  4. The failed or earlier row now reads "invalidated: worked against 1ddde587…, a material change needs a re-test".
  5. Rebuild the kit (`tester_kit.build`; the hash is taken from the CIR) and run a **new test of the new hash**. That is a second owner approval and a second ceiling.
- **Tester deviation** (`instructions_followed = no`): this is not a pattern defect. Re-test the same version, with no re-release.
- **Implausible factor:** check the ball band and the grams for a transcription error before anything else.
- **Calibration on a PASS:** if the factor is not 1.0, `calibration_from_db` applies it to every `worsted cotton:sc` pattern: the small, medium and large market baskets and `housewarming-key-basket`. For a certified release, `assets.build` is re-enqueued, so PDF hashes change and the listing set re-certifies. This is intended.

---

## 2. Package B: `hexagon-coaster-set@1.2.0`, Hexagon Coaster Set (4)

### 2.1 Identity and digests (COMPUTED)

| Item | Value |
|---|---|
| CIR | `products.vessels.build_hexagon_coaster()` via `launch0.cir_for("hexagon_coasters")`, version **1.2.0**; one component `coaster`, `make=4`, 7 rounds |
| Product / listing | candidate `hexagon-coaster-set`, one variant `set_of_four`; plan price CA$4.00 |
| Content hash | `3754ed17a63b790dc2c04b0f744de3fad34e5893ca69c0ff9f0c7cb41090937b` (matches `LAUNCH_PATH` `3754ed17a63b790d`) |
| In-memory certification | granted; release_hash = content hash; only finding `ORIGINALITY_DURABLE_EVIDENCE_UNCHECKED` (no db) |
| Product Truth | `passes_gates=True` |
| Test PDF `hexagon-coaster-set-1.2.0-TEST.pdf` (7 pages) | sha256 `7d10fc229525b650a3a2d77171c36842a9c46abab4213157a04cedafb4739909` |
| Record sheet `hexagon-coaster-set-1.2.0-RECORD-SHEET.pdf` | sha256 `892484a895fd55e33dbcd95d5b50c52bdb4efe6fc72d07e22ae88f931c77107e` |
| Manifest | `tester_kit/KIT_MANIFEST_hexagon-coaster-set.json`; outreach draft `tester_kit/OUTREACH_hexagon-coaster-set.md` (NOT SENT) |
| Risk class | declared A, derived A (no section-8 feature; twin shape `disc`), **effective A**; `required_physical = None`; **automated threshold qualifies** (`certify`'s matrix: no unmet criteria) |
| First-customer requirement | **`partial_physical`** (the first-customer floor: `need = required_physical or PARTIAL_PHYSICAL`); held: none |

The kit was built by `tester_kit_coaster.py`. That script swaps `quality.tester_kit`'s product constants for the coaster's and calls the same `tester_kit.build`, so it uses the same compile, twin, hash, PDF and record-sheet code. It then restores the constants.

`build()` labels the twin's height `wall_height`. For a coaster that figure is the across-the-flats span, so the manifest's `finished_size_cm` was corrected to `across_points` / `across_flats`.

### 2.2 Tester instructions

These are printed on the record sheet. Every line is under the sheet's 118-character limit.

1. Weigh each full ball and record the ball band.
2. Work a 10 × 10 cm sc swatch. Record stitches and rounds and the hook, **then re-weigh each ball**. This keeps the swatch yarn out of the set's grams.
3. Make **all four** coasters exactly as written. Note every guess, re-read or rip-back by round.
4. Grams used = re-weighed start minus end, per colour, for all four.
5. Measure each coaster across the points and across the flats, lying flat and unstretched.
6. Say for each coaster whether it lies flat, cups (the edges lift) or ruffles (a wavy edge).
7. Record hours for all four (excluding the swatch), and whether you followed the pattern exactly.
8. Photograph in daylight on a plain surface: all four top-down, and one side-on at table level.
9. Return the sheet and photos. The operator enters them with `scope: full_make` and `content_hash: 3754ed17…`.

**Operator rule.** Enter the coaster whose across-the-points figure is **furthest from 9.7 cm** as `measured_width_cm`, and its across-the-flats figure as `measured_height_cm`. The other three go in `notes`. This makes the 12% size check apply to the worst coaster.

**Never enter fewer than four coasters' grams**: see §3.3.

The person: an independent adult who is not the owner. They should be confident with sc in joined rounds from a magic ring and with six stacked corner increases, should read US terms, and need a 1 g scale. Time: 3.5–4.5 h plus about 20 min.

### 2.3 Yarn and materials (COMPUTED)

| | Value |
|---|---|
| Yarn | "dk cotton", weight `dk` (gauge `yarn_weight: light`, CYC 3), cream and wine |
| Fibre | cotton, **from the yarn name only**; `fibre_content` is empty |
| Yardage, whole set of 4 | cream **22.6 m**, wine **6.2 m**, total **28.8 m** (±20%). Per coaster that is about 7.2 m. The PDF prints "about 18–27 m" and "about 5–7 m". |
| Hook | **5.0 mm** |
| Notions | tapestry needle, 1 marker, scissors; scale and tape (tester's own) |
| Construction | magic ring, 7 joined rounds to 42 sts; contrast (wine) on round 6 (`rows[-2]`); make 4 |

### 2.4 Required measurements and tolerances (12%, `SIZE_DISAGREEMENT`)

| Measurement | Twin | PASS band | Field | Checked by code? |
|---|---|---|---|---|
| Across the points (worst coaster) | 9.7 cm | 8.54–10.86 cm | `measured_width_cm` | yes |
| Across the flats (same coaster) | 8.4 cm | 7.39–9.41 cm | `measured_height_cm` (the twin's `height_cm` is the flats span) | yes |
| Other three coasters | same | same (package rule) | `notes` | no |
| Lies flat | flat (`finished_size_note`: "Lies flat") | all four flat (package rule; launch0 lists "does not lie flat" as a **disqualifier**) | `notes` | **no** (gap G3) |
| Yarn factor (measured ÷ 28.8 m) | 1.0 | code: 0.4–2.5 (11.5–72.0 m); stated: ±20% (23.0–34.6 m) | grams + band | bounds only |

### 2.5 Gauge and construction checks

- **Gauge:** **14.5 sts × 16.0 rows = 10 cm in sc**, 5.0 mm.
- **PDF checkpoints:**
  - R1: 6 sts, about 1 cm across.
  - R3: 18 sts, about 4 cm.
  - R5: 30 sts, about 7 cm.
  - R7: 42 sts, about 10 cm, still flat.
- **Construction:** the increases go into the second stitch of the previous round's increase, so they stack into six corners. The result is a hexagon, not a circle. The contrast round is one in from the edge, and the work is flat after every round.

### 2.6 Photographs

**The protocol's evidence:**
- all four, top-down;
- one side-on at table level, which is the flatness proof and the coaster's one physical claim;
- intake is as in §1.6.

**Likely listing shots: pending image-policy conclusion.**
- **hero:** the four coasters stacked or fanned, with a mug;
- **proof:** the physical photo;
- **scale:** under a standard mug;
- **detail:** the corner increase and the contrast round;
- **whats_included:** all four laid out (the CONTENTS job, "Set (4)");
- **colour_context:** cream and wine.

### 2.7 Acceptance criteria

The code verdict is the same binary `passed` as in §1.7. The package levels:

| Level | Meaning | Gate effect |
|---|---|---|
| **PASS** | `passed=True`, `full_make`, hash `3754ed17…`; all four coasters within 12% on both spans; all four lie flat; no pattern error in the notes | `gauge_and_size_claims` → PASS; `physical_calibration` met. `risk_based_physical_evidence` is **already met** for this release (class A, automated threshold). |
| **PARTIAL** (package label) | `passed=True`, but a non-worst coaster is outside the band, or the notes report an unclear round | binds and the gate reads PASS; the owner reviews. A text fix means a new hash and a re-test. |
| **FAIL** | `passed=False`, **or any coaster cups or ruffles**. A coaster that does not lie flat is a FAIL by this package's rule and by launch0's disqualifier, but the code cannot see it (G3). | `passed=False` keeps the gate UNRESOLVED and the listing blocked. **Not-flat with `passed=True` would read PASS in the gate**, so the owner must hold the listing: the `standards_gate` owner veto (#228, per LAUNCH_PATH A8; the mechanics are not re-verified here). The fix path follows. |

**The level the first-customer gate needs:** **`partial_physical`** of this content, at code-PASS. This is the class A first-customer floor. The full make here satisfies it.

### 2.8 Cost in CAD (ESTIMATED)

```
code ceiling (owner_action_spec, full make):
tester time  3.46 h x 1.3 = 4.498 h x CA$20/h        = CA$89.96
yarn         28.8 m x 1.2 = 34.56 m x CA$0.06/m      = CA$ 2.07
ceiling                                                CA$92.03

fee CA$89.96 + 2 balls CA$10.00                      = CA$99.96
fee CA$89.96 + full materials list CA$20.00          = CA$109.96

(swatch spec CA$32.40 = 1.5 h x CA$20 + 40 m x CA$0.06: NOT usable. A swatch or a partial set
 is refused, or worse mis-calibrates, at intake; see 3.3)
```

The materials figures are the same `tester_kit.MATERIALS`-style estimated retail as the basket: CA$5 per ball, CA$6 hook, CA$4 notions. **Recommendation, if the coaster is chosen:** approve **CA$100.00** (fee plus two balls).

### 2.9 Expected turnaround (ESTIMATED)

| Step | Time |
|---|---|
| Owner decision | about 25 min |
| Recruit | 2–7 days |
| Make window | ≤ 14 days; the make itself is 3.46 h computed |
| Intake | same day |
| **Total** | **about 1–3 weeks**, the same calendar as the basket. The window, not the hours, dominates. |

### 2.10 If the sample fails

The path is the same as §1.10:
- `passed=False` blocks the listing through the first-customer gate. A size disagreement opens a P2 incident, which does not halt publication on one report.
- The fix is in `build_hexagon_coaster`. For example, if a coaster cups or ruffles, change the increase rate or the gauge, or the `_disc_rounds` arithmetic.
- Then a new version, a new hash, re-certification, a kit rebuild with `tester_kit_coaster.py`, and a re-test with a new owner approval.
- On a PASS with a factor that is not 1.0, the calibration key `dk cotton:sc` applies **only to this product**: no other Launch-0 release uses DK cotton.

---

## 3. Shared notes

### 3.1 Gate coverage by one PASS sample

| Gate / requirement | Basket small PASS | Coaster set PASS |
|---|---|---|
| first-customer `gauge_and_size_claims` | clears it for `market-basket-small@1.2.0` **only**. Medium and large need their own samples, because `physical.record` cannot declare `compatible_variants`. A three-size `nursery-nesting-baskets` listing therefore needs 3 samples: CA$59.65 + CA$108.96 + CA$175.08 (COMPUTED by `owner_action_spec`). | clears it for the **whole product**, which has one variant |
| readiness `physical_calibration` (≥ 1 passed test) | met | met |
| readiness `risk_based_physical_evidence` (every certified class B/C release) | discharges **one** of the B releases (small basket) | discharges **none**; the coaster is class A and already met |
| yardage calibration | `worsted cotton:sc`: 4 releases (3 baskets + key basket) | `dk cotton:sc`: 1 release |
| `tester_outreach` owner card | is exactly this kit (CA$59.65) | needs a new card or an amended one |

Neither sample clears D1 (`etsy_remote_state`) or D2 (`listing_fees` / `brand_clearance` constants) from `LAUNCH_PATH.md`. Both are engineering blockers that sit ahead of any physical result.

### 3.2 Determinism

Both kits were rebuilt twice and gave identical digests. The basket's content hash, record sheet and computed figures (16.0 / 13.9 / 8.7 cm; 40.2 + 11.9 m; 9 pages) match the committed manifest. Only the TEST.pdf bytes changed, as described in §0.1.

### 3.3 Simulations of intake (labelled SIMULATION, not evidence)

These use `quality.physical.assess` on the real twin, with a fabricated ball band of 50 g / 77 m and exact-size measurements. **This is not physical evidence and was not recorded anywhere.**

| Sample | Basket factor → passed | Coaster factor → passed |
|---|---|---|
| whole object, exact yardage | 1.0 → True | 1.0 → True |
| one quarter (one coaster; a swatch is similar) | `SAMPLE_FACTOR_IMPLAUSIBLE` → **False** | `SAMPLE_FACTOR_IMPLAUSIBLE` → **False** |
| half (two coasters) | 0.501 → **True** (a false calibration) | 0.50 → **True** (a false calibration that would halve DK-cotton yardage) |

---

## 4. One-page comparison: basket versus coaster

| | **Basket small @1.2.0** | **Coaster set @1.2.0** |
|---|---|---|
| Content hash | `1ddde587…3991` | `3754ed17…937b` |
| Kit | exists; TEST.pdf refreshed today | built today, mirroring the basket's |
| Make (COMPUTED) | 1 piece, 1,050 sts, **2.15 h**, 52.1 m worsted cotton | 4 pieces, 672 sts, **3.46 h**, 28.8 m DK cotton |
| Cost ceiling (code) | **CA$59.65** | **CA$92.03** |
| Realistic (fee + 2 balls, ESTIMATED) | CA$65.90 | CA$99.96 |
| Turnaround (ESTIMATED) | 1–3 weeks | 1–3 weeks (about 1.3 h more making) |
| Risk class | **B** (`dimensional_form`) | **A** (automated threshold met) |
| What the sample proves that code cannot | a closed 3-D form's size: wall height and base, which is the risk class B exists for | flatness, the one thing launch0 says arithmetic cannot prove; but the code does not read it |
| Gate coverage | first-customer for the small basket; `physical_calibration`; 1 B release's `risk_based_physical_evidence`; calibrates 4 releases | first-customer for the whole product; `physical_calibration`; adds nothing to `risk_based_physical_evidence`; calibrates 1 release |
| Launch value | CA$6.50, net CA$5.60 at a 13.8% take rate (`launch_price`); the anchor of a three-size family, but the three-size listing needs 2 more samples | CA$4.00, net CA$3.34 at 16.4%; price-ladder floor; one sample clears the whole listing |
| Image value | high: a real photo of a 3-D vessel fills PROOF and LIFESTYLE, which renders cannot honestly fill, and shows wall height and scale | moderate: a flat disc is the shape renders draw best; the photo's unique value is the side-on "lies flat" proof and the four-piece contents shot |
| Owner card | `tester_outreach` already says this, at CA$59.65 | new decision required |

**Recommendation: commission the basket first.**
- It is cheaper by CA$32.38 at the code's ceiling and by about CA$34 in realistic cost, and it takes about 1.3 fewer hours to make.
- It is the only one of the two whose class actually requires physical evidence.
- It calibrates four releases instead of one, and its photograph is worth more.
- The owner card already exists.

**Before sending it:**
- add the "re-weigh after the swatch" line (G2);
- raise or restate the ceiling to **CA$66.00** (fee plus whole balls) so that the reimbursement promise in the call is covered.

**Choose the coaster instead only if** the first listing must be one complete product cleared by a single sample. In that case approve about CA$100, and the owner must hold the listing manually if any coaster fails to lie flat.

---

## 5. OWNER ACTION REQUIRED (not asked here; for the owner's batch)

| Action | Why | Max cost | Minutes | Consequence of waiting |
|---|---|---|---|---|
| Approve `tester_outreach` for **market-basket-small@1.2.0**, at CA$66.00 (fee plus two balls) or at CA$59.65 with per-metre yarn; and confirm `tester_kit/OUTREACH.md` | recruiting is outreach to real people; the spend is consequential | CA$66.00 (ESTIMATED) | 25 | no `PhysicalTest` exists, so `physical_calibration` and every first-customer `gauge_and_size_claims` stay blocked |
| *(Alternative)* approve the coaster call `tester_kit/OUTREACH_hexagon-coaster-set.md` | same | CA$100.00 (ESTIMATED) | 25 | same |

## 6. Engineering gaps found (not fixed: this lane changes no `src/`)

> **Update 2026-10-27 (W-PHYSFIX, `claude/w4-PHYSFIX`):** G1-G5 are fixed at the root; see `PHYSFIX.md`. The intake now records what was made, a swatch is accepted as gauge evidence only, flatness/shape/problem notes route to the owner as PARTIAL, a size mismatch halts that release, both kits are rebuilt by `quality.tester_kit.build` with the re-weigh step and unwrapped protocol lines, and a sample covers exactly one size. The record-sheet digests in §1.1 and §2.1 are superseded by `PHYSFIX.md` §5; the TEST.pdf digests and content hashes are unchanged.

- **G1.** `physical.record` / `quality.physical.assess` compares any sample against the whole-pattern twin yardage. A `swatch` or `component` scope therefore fails with an implausible factor, or (between 0.4 and 1.0) passes with a false calibration. `risk_matrix.owner_action_spec` still prices a CA$32.40 swatch for the `partial_physical` requirement. The fix is to scale the estimate by the reported scope, or to refuse `calibration_from_db` for non-full scopes.
- **G2.** The `quality.tester_kit.PROTOCOL_STEPS` swatch step does not tell the tester to re-weigh, so about 16% of swatch yarn is counted in the basket's grams. Step 3 is also truncated on the printed record sheet, because `_record_sheet_pdf` cuts lines at 118 characters.
- **G3.** There is no record field for flatness or shape. A coaster that cups would be recorded `passed=True` if its spans fit.
- **G4.** The `handle_physical_record` docstring says a size disagreement "halts its publication". In fact `IncidentTracker` opens a P2 incident that halts only at 3 reports. The block comes from the first-customer gate instead.
- **G5.** `physical.record` cannot set `compatible_variants`, so one basket sample never covers medium or large.
