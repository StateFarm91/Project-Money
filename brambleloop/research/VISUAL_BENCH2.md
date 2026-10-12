# Commercial benchmark 2 — Mini Star Stitch Cardigan: Product Truth, star-stitch identity, deterministic reference, gated heroes

**Verdict: no certified hero.** Seven draws were made and gated; none passed. The pipeline
itself is complete and recorded end to end (all-size Product Truth, a self-tested star-stitch
identity instrument, a frozen size, a deterministic full-product reference that passes its own
gate, an automatic certification gate), and it did its job: it rejected every draw for stated,
measured reasons. The benchmark closed early because **both external providers ran out of
credit** during phase 5 (OpenAI first, then Google), which is an OWNER ACTION REQUIRED item, not
a pipeline failure. Bench1 (`e4af6f1`) was not reopened; nothing in it changed.

Branch `claude/visual-investigation`; phases 1–2 at `73cb144`, the rest in the closing commit.
Everything measurable is in `research/bench2/out/`; the designer's PDF, its text and photographs
stay outside the repository (asserted by `test_bench2.py`). External spend **US$1.83** of the
US$5.00 ceiling (generation US$1.68, reads and judgements US$0.15).

## 1. PDF identity

"Mini Star Stitch Cardigan" by MJ's Off The Hook Designs Inc., 17 pages, intermediate; a
children's hooded, buttoned cardigan in star stitch with sc-blo ribbed bands and cuffs, worked
flat in one piece bottom-up with the sleeves built in. Ten sizes 0-3m … 12. Licence: personal
use; the pattern's photographs, images and text may not be used to sell finished items (so
they are evidence here, never assets).

## 2. All-size Product Truth (`research/bench2/product_truth.py`, `out/product_truth.json`)

Parsed from the PDF text at run time (the letter-spaced pages are squeezed and matched
space-free), every fact cited to its page: identity, construction, yarn (DK acrylic, 273 yd /
100 g), hooks (5.5 mm body, 5 mm ribbing), gauge (18 sts = 9 stars × 10 rows = 4 in; ribbing
10 sts × 10 rows = 2 in), buttons 4–6 × 18–20 mm, the size chart, the schematic, the star-stitch
definitions, and every per-size vector: back band (chain, sts, rows), back body sts and rows,
sleeve chains (left and right), yoke stars and return sts, rows before the neck, neck marking
and opening sts, right/left front rows and ending sts, sleeve marks, front panels (stars, sts,
rows, final row, band rows), hood (join row, rows 1–5, height rows, shaping), seams, edging,
buttonholes, collar band, cuff.

Derived per size: counts (stars = sts / 2 everywhere), cm dimensions from counts × gauge, and
**25 deterministic cross-checks, all passing** on all ten sizes (yoke = back + both sleeve
chains; wingspan, back width, front width, sleeve width, sleeve length, hood width and height,
neck opening and hem band against the schematic within tolerance; the fronts + band closing to
the back width; the cuff round matching the sleeve rows; buttonhole band = collar band; etc.).
**Four ambiguities recorded, not hidden:** the later-size sleeve-row-range line is one value
short (read consistently as "rows after the neck = rows before it"); whether the hood's 3
shaping rows follow or replace the last pattern rows (follow: matches the schematic on all ten
sizes); 4–6 buttons "by preference" (5 declared for the benchmark); no colour RGB in the text
(Oat Milk sampled from the designer's photograph, declared).

The CIR vocabulary was extended (reusable): `beg_star_st` 3→1, `star_st` 2→1, `end_star_st` 1→2,
`hdc_inc` 1→2, `hdc3` 1→3, with UK terms; the size 2-3T CIR (back band, back body, yoke with
sleeves, fronts with sleeve halves and neck increases, front panels, hood with its increases and
decreases, collar band, cuff) **compiles** (fingerprint `962acf0ad919` as frozen; `ee8a670f3154` after the codes were renamed `*_st` post-suite, see the manifest note).

## 3. Star-stitch identity and gauge instrument (`research/bench2/star_identity.py`)

Built and self-tested **before any paid generation**, as the brief requires.

**What it measures.** From the pattern's own stitch definitions: every star closes into one
eye and spans two stitches; the return row puts two hdc in every eye; the next star row is
worked into those two hdc, so each new eye forms over the eye below shifted by about a quarter
star, alternating with the working direction. The visible signature is the **lattice of eyes**.
The instrument builds an isotropic-dark-blob map (Hessian; posts, bars and valleys are
rejected), autocorrelates it, and finds the along-row fundamental (star pitch) and the
across-row basis; then tests, with a priori bars named in `BARS`/`WHY`:

| test | bar | why |
|---|---|---|
| row peak, next-row peak | ≥ 0.10 | the lattice exists |
| column offset (shortest lattice vector) | ≤ 0.30 star | derived: eyes stack in columns; a checker (seed, waffle, bobble) is half a star over |
| star pitch / row pair | 0.39–0.72 | derived from gauge (0.556) ± 30 % |
| blob isotropy | ≥ 0.55 | holes, not bars |
| diagonal gradient fraction | ≥ 0.30 | the legs fan into the eye; hdc rows and grids sit at 0°/90° |
| return-row contrast | ≥ 1.25 | the thin hdc row between star rows; bump lattices have none |
| gauge: measured pitch and pair vs expected | ± 35 % | Bench1's generator-fuzz tolerance |

**Self-test (`out/star_identity_selftest.json`).** Deterministic truth: PASS identity and gauge
at two phases; at 2× scale PASS identity, FAIL gauge (as it must). Controls, all FAIL: the
half-offset fabric of the first model, plain hdc rows (diagonal fraction 0.15), a seed checker
(offset 0.5), knit (isotropy 0.43), Bench1's waffle reference (offset 0.5, ratio 1.0), Bench1's
certified hero (seed-like: ratio 1.2, no return row). Designer photographs (private, crops of
the flat lay and the worn gallery shots, upscaled ×2): **five of six PASS** identity with
pitch/pair 0.48–0.57 and column offset 0.03–0.20; the sixth is a ~5-star crop of the worn baby
cardigan, below the stated envelope, and reads FAIL (never PASS by accident).

**What was learned, recorded in the module.** Two earlier designs (row-frequency alternation,
then energy alternation between half-bands) passed the deterministic truth and failed every
photograph. The first truth fabric also stacked star rows half a star apart; the mechanics and
the photographs (offset 0.03–0.20) say the eyes stack in columns, so the model was corrected
and the half-offset fabric became a control. Bars were never moved.

**Known limit (found in phase 6).** A cluster texture with the same eye lattice, pair ratio
and return row (draw 3) passes the instrument; the reader's material `texture` answer caught
it. The instrument certifies the star stitch's lattice and gauge, not the five-leg loop
structure; a leg-convergence measure around each eye is the recorded next improvement.

## 4. Frozen size and reference (`out/bench2_manifest.json`, `research/bench2/reference.py`)

**Size 2-3T**, because every shaping element exists at that size (neck increases, hood
increases and shaping rows, sleeve rows before and after the neck), the designer photographs it
worn (private comparison possible), and at the frame that fits its 73.8 cm wingspan a star is
18 px across, inside the instrument's envelope. Frozen with the Product Truth digest and the
CIR fingerprint before any draw.

**Reference:** 1536×1024 flat lay, front up, buttoned, hood spread flat above the shoulders,
sleeves 32° down (Bench1's convention), on a dark slate surface so the cream garment segments by
lightness. Geometry is Product Truth's: back 32.7 cm; fronts 14.7 cm each with the closed
centre strip 3.3 cm (declared: BW − 2·FW, the pattern's 7-st band is 3.6 cm); hem band 3.6;
front panel 18 rows + front yoke half 12 rows = 34.1 cm hem to shoulder; the front neck sloping
from the 12.4 cm opening at the shoulder to the band at the underarm (the neck increases);
sleeves 16.9 cm + 3.6 cm gathered cuffs, 12.2 cm face; hood 31.6 × 22.4 cm with a face-edge
band whose rib rows run perpendicular to the edge and a centre seam line; five 19 mm buttons
evenly spaced on the band (declared). Star fabric at 1.13 × 2.03 cm from the same deterministic
model the instrument was self-tested on, rows horizontal on body and hood and along the
sleeves; sc-blo ridges perpendicular to each band's edge. **Validation:** every region present;
the instrument reads the reference's own fronts as star stitch at gauge (pitch 18.0 px vs 18.44
expected, pair 33.0 vs 33.1, ratio 0.545); the reference passes its own deterministic gate
(silhouette IoU 1.0, 5 buttons); the substitute reader reads it as a buttoned star-stitch
cardigan with attached hood, five buttons, ribbed bands, on every property.

## 5. Generation (`research/bench2/run_bench2.py`)

**Blocker 1.** At the first paid call the OpenAI account answered HTTP 429
`insufficient_quota` / `credit_balance_exhausted`. That blocks gpt-image-1.5 high-input-fidelity
(the brief's primary route), the pinned gpt-5 reader and the pinned gpt-5 D judge together.
Route taken, all recorded per call with provider/model/substitute_for: gemini-3-pro-image (the
brief's named alternative) at 2K on a 3:2 frame, prompt v1 = Bench1's round-2 presentation
wording with the dark cloth and DK yarn; gemini-3.1-pro-preview as a **declared substitute** for
the reader and the judge with the pinned prompts unchanged.

**Blocker 2.** After draw 7, Google answered HTTP 402 `RESOURCE_EXHAUSTED` (prepaid credit
depleted); draw 8 failed, and the substitute reader and judge stopped with it. Draws 5–7 are
gated deterministically only and stay UNKNOWN on the reader and judge (never PASS).

| draw | prompt | silhouette IoU | aspect drift | buttons | star identity / gauge | reader texture | material failures | verdict |
|---|---|---|---|---|---|---|---|---|
| g3pro_1 | v1 | 0.752 | 0.105 | 5 | FAIL (col. offset, ratio) / PASS | other | front_band, texture, silhouette, proportions, star_identity | FAIL |
| g3pro_2 | v1 | 0.622 | 0.118 | 0 found | FAIL / FAIL | smooth | + sleeve_span, buttons, star_gauge | FAIL |
| g3pro_3 | v1 | 0.912 | 0.009 | 6 | PASS / PASS | ribbed_all_over | texture, buttons | FAIL |
| g3pro_4 | v1 | 0.845 | 0.202 | 6 | PASS / PASS | star_stitch | proportions, buttons | FAIL |
| g3pro_5 | v2 | 0.839 | 0.101 | 5 | FAIL / FAIL | (blocked) | proportions, sleeve_span, star_identity, star_gauge | FAIL |
| g3pro_6 | v2 | 0.875 | 0.014 | 6 | FAIL (return row, isotropy) / PASS | (blocked) | buttons, star_identity | FAIL |
| g3pro_7 | v2 | 0.898 | 0.013 | 5 | FAIL (return row) / FAIL | (blocked) | star_identity, star_gauge | FAIL |

The substitute judge passed all seven realism items on draws 1–4 with no notes and 103 output
tokens each; it discriminated nothing and its verdicts carry no weight. The pinned D judge has
not seen any Bench2 draw.

Prompt v2 (D-B2-4) added two fidelity sentences naming parts the reference already contains
(hood open and spread as drawn; exactly the buttons drawn, none added or removed); it never
names a count, a stitch or a construction detail. It fixed the button count on two of three
draws and did nothing for the hood.

## 6. Discrepancies and root causes

- **Texture.** Gemini replaced the drawn star fabric with plain hdc rows on four of seven draws
  and with cluster textures on three; only draw 4 reads as star stitch to the reader and passes
  the instrument. Root cause: the provider, with no structure lock (E5's finding) — it keeps the
  silhouette and rewrites the surface. gpt-image-1.5 with `input_fidelity=high`, which kept
  Bench1's texture cells, was blocked.
- **Hood posture.** Every draw folds the spread hood into a pointed hood, which costs silhouette
  IoU (0.62–0.91) and, on draw 4, aspect. Root cause: the provider's prior; the fidelity
  sentence did not move it. Reference option not taken: draw the hood folded (as the gallery
  photos wear it) — a presentation choice the owner may prefer, recorded as D-B2-5.
- **Button count.** 4 or 6 for the 5 drawn on four of seven draws; caught by the deterministic
  button counter (added when calibration withdrew the reader's closure count).
- **Reader calibration (private).** On the designer's photographs the substitute reader read
  closure count 4 twice (the photographs show four buttons; Product Truth declared five), so
  closure count was withdrawn from materiality by the recorded rule and replaced by code;
  texture read `other` on the small flat lay and `star_stitch` on the worn shot (stays
  material); the baby-worn photograph returned nothing (UNKNOWN throughout).

## 7. Private comparison

No certified hero, so `out/private_comparison.json` is empty by construction. The designer's
readings are in `out/designer_photos.json` (evidence only).

## 8. Reusable improvements recorded

1. CIR star-stitch vocabulary (`beg_star_st`, `star_st`, `end_star_st`, `hdc_inc`, `hdc3`).
2. Space-free parsing for letter-spaced PDF text; the size-chart quadruple parser.
3. The eye-lattice identity instrument with a stated operating envelope, self-test record and
   the first-design note (lattice geometry and mechanics, not row-frequency reasoning).
4. The stitch-model correction rule: a truth fabric may be corrected by the stitch mechanics
   and photographs of the real stitch; bars may not.
5. Deterministic button counting on the reference's band region.
6. Reader calibration on private ground truth with a recorded withdrawal rule (E3 rule, now
   code: `gate.calibrate`).
7. Provider fallback that never silently changes the model: pinned first, declared substitute
   on `insufficient_quota`, every call labelled; offline gating that leaves verdicts UNKNOWN.
8. Cost/yield: gemini-3-pro-image 2K US$0.24 per draw, 0 of 7 certified; the material failures
   are texture (6/7), hood posture (7/7), button count (4/7).

## 9. Blockers — OWNER ACTION REQUIRED

Batched in `out/bench2_manifest.json` → `blockers`:

1. **Add prepaid credit to the OpenAI API organisation** (Settings → Organization → Billing).
   Why: the pinned reader, the pinned D judge and gpt-image-1.5 cannot run. Max cost: owner's
   choice; US$10 covers re-running this benchmark's reads and judgements and ~25 gpt-image-1.5
   draws at the recorded rates. Minutes: 3. Consequence of waiting: no Bench2 hero can be
   certified; the substitute judge is not a substitute for certification.
2. **Or add prepaid credit to the Google AI Studio project** (ai.studio/projects → billing) —
   restores gemini-3-pro-image and the substitute reader/judge only. Max cost: US$5 to finish
   this benchmark. Minutes: 3.

## 10. Tests

`research/bench2/test_bench2.py`: 42 checks, all passing (vocabulary, Product Truth, instrument
record and live re-run, reference validation and self-gate, gate rules, calibration rule,
manifest bookkeeping, nothing of the designer's tracked). Full suite: see BUILD_STATE.

## 11. Confidence statement

High confidence that the recorded pipeline is deterministic, honest and reproducible, that the
instrument recognises the real stitch on flat photographs and rejects the six controls, and
that every rejection above is for the stated reason. No confidence claim about a hero: none
exists. The single provider that kept texture cells in Bench1 was never reached, so the
yield of this pipeline with its intended provider is unmeasured.
