# Launch-0: the assortment plan

_Written 2026-09-25 by Catalogue / Product Planning, in shadow mode, in an isolated worktree.
No Etsy API call, no model API call, no image generation, CA$0 spent. Nothing published._

Every claim carries a label:

| label | meaning |
|---|---|
| **SOURCED** | read from a cited source, or measured from this repository's own code by running it |
| **DERIVED** | arithmetic performed here on sourced numbers, shown |
| **ESTIMATED** | a judgement with no measurement behind it, said so |
| **UNKNOWN** | genuinely not established. Not filled in with a plausible number |

The governing rule for this document is the owner's:

> **Do not manufacture catalogue completion ahead of Product Truth.**

A product is not in this catalogue because it would sell. It is in it when a CIR exists,
compiles clean, measures the object its name promises, and the deliverable is makeable. Code
deliverable: `src/brambleloop/products/launch0.py`, with `tests/test_launch0.py` (43 checks,
green). Nothing in that module declares a product ready — every readiness statement in this
document is **computed by compiling the CIR**, so this plan goes stale visibly rather than
quietly.

---

## 0. The one-paragraph version

Launch-0 is **three listings**: a nesting basket in three sizes, one baby blanket, and a set of
four coasters. Two of the three are the children's sub-categories the landed research puts
first on obligation and verifiability — nursery decor and baby blankets — and the third is the
floor of the price ladder and the cheapest honest way to exercise the Etsy path end to end.
Three is not modesty. Building the gates that this plan runs on found that **eleven of the
eighteen CIRs in the repository claim something their pattern does not make**, and the largest
finding is structural: `Row.color` is one value per row and `Op` has no colour field, so **the
CIR cannot put two colours in one row**. Every "mosaic", "overlay mosaic" and "graphghan"
product in the catalogue — including all three sizes of the hand-engineered Nordic Forest, which
was going to be the headline of this plan — is a one-row stripe with a raised sc/dc relief. It
compiles clean, it certifies, and it is not the fabric the name describes. Launch-0 is three
products because three is what survived.

---

## 1. The assortment

Small is the feature. Nine finished pieces, three genuinely different constructions, and no
product whose name outruns its CIR.

### 1.1 Nesting Baskets, three sizes

| | |
|---|---|
| **What it is** | One pattern, three baskets worked in the round from a flat disc base into straight walls. 15 cm × 9 cm, 20 cm × 16 cm, 25 cm × 23 cm. |
| **CIR** | `products/vessels.build_basket("small"/"medium"/"large")`. Three CIRs from one design. |
| **Why at launch** | The children's research puts **nursery decor first** — on obligation and verifiability, not on demand — and `intel.childrens.SUBCATEGORIES["nursery_decor"]` names baskets explicitly with a `LEAD` verdict. It is the only nursery-decor object in this repository a compiled CIR already makes. The child does not handle it, nothing is applied to it, and the geometry is the kind `cir.geometry` measures exactly: the base disc sets the width, the wall rounds set the height. |
| **Price** | CA$6.50. Band CA$4–12 (**SOURCED**, `radar/market.py: OBSERVATIONS["price_band"]`). A basket-specific observed competitor price is **UNKNOWN** — no profiled shop's basket price was captured — so this sits mid-band rather than pretending to a comparable. Cleared `commerce.pricing.decide_price`: net CA$5.61 after Etsy's fee stack, take rate 13.7%. `decide_price` recorded one reason of its own: *"3 finished sizes from one chart, which no profiled competitor offers"*. |
| **Make time** | 3.7 h / 7.5 h / 12.7 h per size (**ESTIMATED**, derived from the twin's stitch count at an assumed 700 st/h; `leadtime` reports that rate as *assumed*, not measured). |

**Certified** — compiles with 0 errors and 0 warnings in all three sizes; the twin resolves each
as a `vessel` and computes the width, height and circumference above; `Component.make` is 1 and
the title claims one basket per size, so the name matches the object.

**Aspiration** — every measurement is arithmetic from the stated gauge. `twin.calibrated` is
**False**: no basket has been crocheted. The firm cotton gauge that makes a basket stand up
rather than slump is asserted by the CIR and unverified in fabric.

**What would disqualify it** — a worked sample whose walls slump at the stated gauge, which
would make the stated height a number rather than a basket; a base disc that does not lie flat,
which the increase arithmetic predicts and only a sample confirms; any decision to add an
applied trim, which turns a nursery object the child does not handle into one that can shed a
part.

### 1.2 Cloudline Baby Blanket

| | |
|---|---|
| **What it is** | A 78.8 × 97.2 cm baby blanket in two colours, worked flat. The colour changes every row and a raised diamond lattice is worked in double crochet against a single-crochet ground, so the fabric is **a one-row stripe with a relief** — not a two-colour picture. |
| **CIR** | `products/builder.for_slug("cloudline-baby-blanket")`. |
| **Why at launch** | Keepsake and baby blankets are the research's other first-entry sub-category (`baby_blanket`, `BUILD` verdict). This is the **only blanket in the catalogue whose name does not claim a colourwork fabric the CIR cannot express** — see §4. Class A geometry, no fitted sizing, no applied parts, and the largest single make in Launch-0, which is what carries the price. |
| **Price** | CA$7.50. Band CA$8.47–11.65 (**SOURCED**, `radar/market.py`: HanJanCrochet CA$8.47–11.65, MJsOffTheHookDesigns CA$8.47–11.64, observed 2026-09-17). Priced **below** the band floor on purpose: those listings advertise PATTERN + VIDEO, which the same file records as table stakes rather than a premium, and we have neither a video nor a review history. `decide_price` recorded it as *"priced below the band floor of CA$8.47 deliberately, to buy early reviews rather than early margin"*. Net CA$6.52, take rate 13.1%. |
| **Make time** | 17.5 h (**ESTIMATED**, same basis). |

**Certified** — compiles with 0 errors and 0 warnings; the twin computes 78.8 × 97.2 cm and a
`rectangle` outline over 11,088 stitches; the title makes no multiplicity claim and no
technique claim, so nothing in the name outruns the pattern.

**Aspiration** — the dimensions are arithmetic from the stated gauge; `twin.calibrated` is
**False**. And the material one: **none of the five statements this product must carry is
rendered by the deliverable chain**. `required_statements("baby_blanket", "under_3")` returns
`age_suitability`, `fibre_and_care`, `not_legal_advice`, `safe_sleep`,
`selling_finished_items`; a search of `publish/*.py`, `cir/*.py` and `commerce/*.py` for any of
"safe sleep", "supervised", "choking" finds **zero files** (measured by
`launch0.statement_rendering_gap()`). `intel.childrens.assess()` on the product as built returns
the subject as allowed and **not ready to ship**, with every statement listed as missing. That
is the gap, and it is the one thing standing between this product and a publishable deliverable.

**What would disqualify it** — listing copy or imagery showing a two-colour lattice *picture*,
which is the motif-fidelity failure `publish/motif_fidelity.py` exists to block; the design's own
note claiming *"no long floats for small fingers to catch"* — true, and still a description of
stranded colourwork this pattern does not make, offered as reassurance about a child's safety for
a hazard the product does not have. **Corrected 2026-09-25**: the note now reads "The lattice is a
relief rather than colourwork: double crochet standing above a single-crochet ground, one colour
per row", and `gates.asset_truth` refuses any float claim on a fabric no row of which works two
colours — in the designer notes as well as the title, which is where this one lived and why no
gate saw it. It survives above as a listing-copy risk rather than a pattern one; a worked sample whose drape at the stated gauge is stiff enough that the object is not
a baby blanket.

### 1.3 Hexagon Coaster Set (4)

| | |
|---|---|
| **What it is** | Four hexagonal coasters, about 9.6 cm across the points, worked in joined rounds with the increases stacked at six corners and a contrast round one in from the edge. |
| **CIR** | `products/vessels.build_hexagon_coaster()`. |
| **Why at launch** | Not a children's product, and it is here for two jobs neither children's entry can do. It is the **floor of the price ladder**, and it is the cheapest honest way to **exercise the whole Etsy listing path end to end** — a four-piece make with `Component.make` set correctly, a geometry the twin resolves as a `disc`, and no safety statement set in the way. Its merchandising value is review velocity and price structure, not distinctiveness, and saying so is more useful than dressing it up. |
| **Price** | CA$4.00, the floor of the CA$4–12 cluster (**SOURCED**, as above). Net CA$3.35, take rate 16.3% — the highest of the three, which is the honest arithmetic of a cheap digital product and the reason this listing earns its place through reviews and cross-sell rather than margin. |
| **Make time** | 1.1 h per coaster, **4.4 h for the set** (**ESTIMATED**). |

**Certified** — compiles with 0 errors and 0 warnings; `Component.make` is 4 and the title says
"Set (4)", so the count is backed; the twin resolves a `disc` 9.6 cm across over 330 stitches per
piece.

**Aspiration** — 9.6 cm is arithmetic from the stated gauge; `twin.calibrated` is **False**.
Flatness is *predicted* by the increase rate and unverified in fabric.

**What would disqualify it** — a worked sample that does not lie flat, which is the one thing a
coaster must do and the one thing the increase-per-round arithmetic cannot prove; a price that
has to rise above the cluster floor to clear fees, since the whole point of this listing is the
bottom of the ladder.

### 1.4 First reserve, named so that "why only three" has an answer

**Harvest Table Runner** (30 × 124 cm, `harvest-table-runner`) passes every gate. It is held
back on **assortment grounds rather than truth grounds**: it repeats the blanket's construction,
it is not a children's product, and small is the feature. `Pet Snuggle Mat` is in the same
position. `launch0.excluded_from_launch0()` marks both as *held back on assortment, not truth*,
so the distinction between "we cannot" and "we chose not to" survives into next month.

### 1.5 One caveat on the make-time figures, because it bites the coaster set

`seasonal.leadtime.estimate_make_hours` sums the stitches in a twin, and a twin holds **one**
instance of a component however many the pattern says to make. It reports 1.1 hours for a set of
four coasters that takes about four and a half. `launch0.make_time()` corrects for
`Component.make` and a test pins the correction. The uncorrected figure must never reach a
listing: a make-time a quarter of the real one is the kind of small wrongness that earns a
one-star review about honesty. Reported rather than fixed in `seasonal/**`, which another
department owns.

---

## 2. Baby and children's: what the plan owes the research

The research's entry order is **obligation- and verifiability-weighted, not demand-weighted**,
and Launch-0 follows it exactly: nursery decor and baby blankets now, amigurumi second with an
embroidered-face default, children's fitted garments last.

Every constraint below is consulted through `intel.childrens.assess()` and
`required_statements()` rather than restated here. What this plan adds is the per-product
answer.

| product | sub-category | verdict | audience | statements required | as built |
|---|---|---|---|---|---|
| Nesting Baskets | `nursery_decor` | `LEAD` | under 3 years | age_suitability, fibre_and_care, not_legal_advice, safe_sleep, selling_finished_items | subject allowed; **not ready to ship** — all five statements missing |
| Cloudline Baby Blanket | `baby_blanket` | `BUILD` | under 3 years | the same five | subject allowed; **not ready to ship** — all five statements missing |
| Hexagon Coaster Set | — | — | — | — | **not a children's product**, stated rather than left as an omission |

Four things this plan commits to, each of which is enforced in code rather than remembered:

**No applied parts anywhere in Launch-0.** Under 36 months a detachable applied part is
*refused*, not warned about — `assess` returns `REFUSE` and `publishable()` returns False, with
no severity downgrade available. So the Brambleloop default is an integral surface: nothing on
any Launch-0 product is held on by friction, a washer or glue. A test asserts the applied-part
tuple is empty for every children's item and that a lovey with `safety_eyes` at `under_3` is
refused.

**Embroidered faces are the default for the amigurumi that is coming, not a caveat on it.**
`embroidered_eyes` is in `INTEGRAL_FEATURES`; `safety_eyes` is in `DETACHABLE_APPLIED_PARTS`.
Safety eyes become a clearly-labelled 3+ variant and never the hero image. The research is
right that this is a real merchandising cost against the genre's visual signature, and it is
the one we are choosing.

**Etsy's policy reaches the pattern, so the refusals are refusals.**
`launch0.never_published()` enumerates them from the constraint module rather than restating
them: infant sleep accessories, baby carriers and slings, children's loose-fitting sleepwear
(all `NEVER`), and rattles and teethers (`AVOID`). A test constructs
`"Nursery Crib Bumper Pattern"` dressed as nursery decor and asserts `assess` refuses it on
`PROHIBITED_SUBJECT` — the gate that matters most is the one no current product trips.

**Drawstrings and baby-blanket supervised use are handled where they belong.** No Launch-0
product is children's upper outerwear, so the 16 CFR 1120 / ASTM F1816-97 rule does not bite
yet; `assess` already enforces it for the garments in wave 4. The baby blanket's `safe_sleep`
statement is required by `intel.childrens` and computed, not chosen.

**The blocker, stated plainly.** `required_statements()` computes the obligation and **nothing
consumes it**. Until the deliverable renders the statement block, these two children's products
are not publishable however clean their arithmetic is. `publish/pdf.py` is owned by the
deliverable department; this is a measurement for them, not an edit by this department.

---

## 3. Seasonal pipeline

### 3.1 The counter-seasonal pairing, re-derived rather than believed

The research measured the two series; this plan does the arithmetic, in
`launch0.seasonality()`. Wikimedia pageviews, en.wikipedia, `user` agent class, monthly,
2025-09 → 2026-08 (**SOURCED**, `wikimedia.org/api/rest_v1/...`, pulled 2026-09-24).

| series | mean | peak / trough | peak | trough |
|---|---|---|---|---|
| `Amigurumi` | 5,340 | **1.92×** | 2025-12 | 2026-06 |
| `Baby_shower` | 8,686 | **1.60×** | 2025-09 | **2025-12** |
| 50/50 blend, each series normalised to its own mean | 1.00 | **1.48×** | 2025-09 | 2026-08 |

**DERIVED.** Amigurumi's annual maximum falls in the month of baby-occasion's annual minimum, so
a portfolio holding both swings **1.48×, flatter than either category alone**. Normalising each
series to its own mean before blending is the point: a raw sum weights baby-shower 1.6× simply
for being the more-read article, which is not a portfolio decision anybody made. A test also
sweeps the mix weight from 30% to 60% amigurumi and asserts the blend stays flatter than
baby-occasion alone at every weight — **a finding that only held at exactly 50/50 would be a
coincidence, not a portfolio argument**.

Caveats, stated because they matter: pageviews are a proxy for interest and not for purchase
intent; en.wikipedia, so the population is closest to `GLOBAL`/`US` rather than `CA`; one year,
n=12, and no confidence interval is claimed.

### 3.2 The sequence

`launch0.pipeline_plan()` holds this as data, in a **separate type from the catalogue** — a
`PipelineEntry` has no CIR and a test asserts the two populations never intersect, because the
easiest way to grow a catalogue on paper is to add an aspiration to the product list "so it is
not forgotten".

| wave | item | why this position | blocked on | owner |
|---|---|---|---|---|
| 1 | **Retire or rename the eleven over-claiming CIRs** | Before any new product: they are the reason the catalogue looks larger than it is | a merchandising decision — rename to what the fabric does, or hold until the CIR can express it | product planning, with visual on the renders |
| 1 | **Per-stitch colour in the CIR** | The highest-value unbuilt capability in the product, measured by what it unblocks | `cir/**` is another department's | whoever owns `cir/model.py`, `compiler.py`, `twin.py`, `writer.py` |
| 2 | **Lovey with an embroidered face** (`lovey`, `BUILD`) | The counter-seasonal half of the portfolio, aimed at amigurumi's December peak. **Genuinely buildable**: `vessels.py` already works discs from a magic ring and `cir.stitches` carries `inc`/`dec`/`dc_inc`/`dc_dec`, so sphere shaping needs no new primitive, and an embroidered face needs none at all | a stuffing-containment check (nothing measures whether the stated gauge is tight enough that stuffing cannot migrate); the statement block | product planning can build the CIR; `publish/**` owns the statements |
| 2 | **Milestone / keepsake baby blanket** (`keepsake_blanket`, `LEAD`) | The audience's highest price tolerance, and second rather than first only because it needs two things that do not exist | per-stitch colour; an alphabet and numeral motif set validated at blanket gauge (`motifs.LIBRARY` holds eight motifs and no glyphs); and a decision on the economics, since `personalisation.py` correctly routes a construction-level customisation to its own compile and certificate — which means a named blanket is a product **per name** | `cir/**` for the colour primitive; product planning for the glyphs |
| 3 | **Baby and child hats, booties, mittens** (`baby_wearables`, `BUILD`) | The fastest review accumulator available, behind the lovey only because grading needs a table we do not carry | the CYC head-circumference table, read and landed as data with its source (`intel.childrens` holds chest only) | product planning |
| 4 | **Children's fitted garments** (`childrens_garment`, `CAREFUL`) | Last, where the research and the repository's own Class C model both put it | physical samples, which `twin.calibrated` being False makes a prerequisite; the drawstring rule, which `assess` already enforces | `quality/physical.py` plus an owner action to crochet samples |

**The December date is computed, not chosen.** `seasonal.leadtime.compile_launch` for the lovey
against a 2026-12-15 gifting date, at 5 assumed make-hours: **latest effective launch
2026-11-06, preferred launch 2026-10-13, work must start by 2026-09-22.** Status at
2026-09-25: `on_track`, 42 days of runway. Every assumption in that chain is reported as
*assumed* rather than measured, and `fully_measured` is False — which is the honest reading of a
date derived from a stitch rate nobody has timed.

**What the sequence buys.** Launch-0 is entirely baby/nursery and home, which is the flat half
of the pair. The lovey lands in November for amigurumi's December peak, which is baby-occasion's
trough. That is the pairing working as designed rather than as asserted.

---

## 4. The hard rule, applied: what we found looking for Product Truth

`launch0.py` runs three gates over every CIR in the repository. They exist because the
generated catalogue fails each of them, and each is also tested against an **injected** defect,
so a gate does not stop being tested the moment the catalogue is fixed.

**Eleven of eighteen CIRs fail a gate** (measured 2026-09-25 by `excluded_from_launch0()`):

| CIR | gate failed | what was measured |
|---|---|---|
| `winter-village-graphghan` | fabric claim | claims "graphghan"; at most **1 colour in any one row** |
| `autumn-oak-mosaic-throw` | fabric claim | claims "mosaic"; 1 colour per row |
| `mosaic-placemat-pair` | fabric claim **and** title promise | claims "mosaic"; and the title claims 2 pieces, the CIR makes 1 |
| `nordic-forest-baby` / `-throw` / `-large` | fabric claim | claims "overlay mosaic"; 1 colour per row |
| `nordic-star-ornaments` | title promise | title claims **6** pieces; CIR makes **1** (a single 7.5 × 11.7 cm rectangle) |
| `pressed-flower-motifs` | title promise | title claims **12**; CIR makes **1** |
| `spooky-garland` | assembly | title names "garland"; 0 seams, 1 piece |
| `valentine-heart-garland` | assembly | title names "garland"; 0 seams, 1 piece |
| `cottage-wall-hanging` | assembly | title names "wall hanging"; 0 seams, 1 piece |

### 4.1 The root cause, and it is one line of the data model

`Row.color` is a single value and `Op` has no colour field. **The CIR cannot express more than
one colour in a row.** Every colourwork product above is therefore a fabric where each row is
one solid colour and the motif appears as a **height difference between single and double
crochet inside that colour band** — and because the colour alternates every row, a 24-row fir
tree is drawn across twelve alternating cream and forest stripes. A two-colour picture of a fir
tree cannot appear, because no row contains two colours.

The gate measures the colours actually present per row rather than arguing about what overlay
mosaic means, because the measurement is decidable and the argument is not. Two related
capabilities are measured the same way, by inspecting the dataclass rather than asserting a
fact in prose, so that **when somebody adds `Op.color` the gate re-opens by itself**:

- `per_stitch_colour_expressible()` → False today
- `per_stitch_reach_down_expressible()` → False today (`Row.into` retargets a whole row, which
  is not the per-stitch reach-down that defines overlay mosaic)

These products all compile clean and would all certify. That is precisely why a name-versus-
fabric gate had to exist: **the arithmetic being right is not the same as the object being what
it is called.**

### 4.2 The multiplicity defect is the one `vessels.py` already fixed once

`Component.make` exists and `vessels.build_hexagon_coaster` uses it correctly. `builder.Design`
has no `make` field, so the generic builder always makes one piece, and three titles promise
counts nothing checks. This is the same defect as the old "Market Basket Trio" — one flat panel
sold as three baskets — recurring in the layer above the one that was fixed. The gate is
generic rather than a list of those three, because the next product generated from the same
builder will fail it the same way.

### 4.3 Calibration: the honest headline

`twin.calibrated` is **False catalogue-wide**. Nothing in the deliverable has been checked
against a physically worked sample. Every finished measurement in this document — 78.8 × 97.2
cm, 20 cm across, 9.6 cm across the points — is arithmetic from a gauge the CIR states and
nobody has crocheted. `product_truth()` reports that in the same dict as the numbers rather
than in a footnote, and `report()["calibration"]["any_product_calibrated"]` is False.

### 4.4 Two defects found in other departments' files, reported rather than edited

- **`publish/motif_fidelity.chart_colours(twin)` counts stitch codes, not colours.** It reads
  `twin.chart_grid()`, which is the *stitch* grid; the colour grid is `twin.color_grid()`. For
  every current product the stitch vocabulary happens to be `{sc, dc}` and the colour count
  happens to be 2, so it returns the right answer by the wrong measurement — and it would report
  "2 colours" for a single-colour textured pattern. The motif-fidelity gate is the check that
  would otherwise have caught §4.1 in an image.
- **`seasonal.leadtime.estimate_make_hours` ignores `Component.make`** (§1.5).

Neither is edited here. Both are measurements for the departments that own those files.

---

## 5. What is genuinely blocked

| # | blocked thing | blocked on | what would unblock it |
|---|---|---|---|
| 1 | Publishing either children's product | the children's statement block does not exist in the deliverable chain — measured: zero files in `publish/`, `cir/` or `commerce/` mention any of the statement set | `publish/**` consuming `intel.childrens.required_statements()`. Owned by the deliverable department |
| 2 | Every colourwork, mosaic, graphghan and lettered-keepsake product | `Op` has no colour field, so two colours in one row is not expressible | a per-stitch colour primitive in `cir/**`. Not this department's file |
| 3 | Any claim that a finished measurement is real | `twin.calibrated` is False catalogue-wide | the owner's Visual Stage 0 physical swatch, already batched in BUILD_STATE, plus one worked sample per Launch-0 product |
| 4 | Keepsake / milestone blankets | no alphabet or numeral motifs exist in `motifs.LIBRARY`; and `personalisation.py` correctly makes a named blanket a product per name | a validated glyph set, and a decision on the per-name economics before it is built |
| 5 | Baby wearables grading | `intel.childrens` carries the CYC chest tables and not head circumference | reading and landing the published CYC head-circumference chart with its source |
| 6 | Any listing-attribute claim for the children's audience | the attribute schema for Etsy taxonomy node 66 is **UNKNOWN**; one `getPropertiesByTaxonomyId(66)` call would establish it, and this department made no Etsy API call | another department spending that one call. Unchanged from the research's §6 |

**No OWNER ACTION REQUIRED item arises from this plan** that is not already batched in
BUILD_STATE. Blocker 3 is the existing Visual Stage 0 item; nothing here needs money, KYC,
legal acceptance or a new physical act beyond crocheting the three Launch-0 products, which is
the same request already outstanding.

---

## 6. Code deliverable

`src/brambleloop/products/launch0.py`, `tests/test_launch0.py` — 43 checks, green.

It earns its place on one argument: **every readiness claim in this document is decidable by
compiling a CIR, and a planning document that states readiness in prose is a document that
disagrees with the code the first time a design changes.** So the module carries the assortment
as data with the safety constraints wired in through `intel.childrens`, and computes the rest:

- `product_truth()` — compiles every variant and reports errors, warnings, the twin's finished
  measurements, and `calibrated`, with the "this is arithmetic, not a sample" caveat in the same
  dict;
- `title_promise()`, `assembly_promise()`, `fabric_truth()` — the three gates, each measuring
  one thing and saying what and why;
- `per_stitch_colour_expressible()`, `per_stitch_reach_down_expressible()` — the CIR capability
  the gates depend on, **measured from the dataclass** so the finding cannot go stale;
- `childrens_view()` — `assess()` run twice, as-built and as-planned, because "may we publish
  this" and "what must it say" are different questions;
- `statement_rendering_gap()` — whether the deliverable can print the statement set at all;
- `seasonality()` — the measured series, and the blend arithmetic that justifies the pipeline
  order;
- `price_plan()`, `make_time()` — both routed through the modules that own the arithmetic;
- `excluded_from_launch0()` — every CIR not in Launch-0 with the measured reason, distinguishing
  *gate-failing* from *held back on assortment grounds*;
- `PIPELINE` and `pipeline_plan()` — the aspirations, in a separate type, each naming a blocker
  and its owner.

What it deliberately does **not** carry: any demand, velocity, competition or conversion score
for a product. `intel.childrens` refuses those for the same reason and asserts the refusal in a
test; this module does too. A plan is where an invented 0.8 is most tempting and most damaging,
because it sits beside compiled measurements and borrows their authority.

And it does not fix the eleven over-claiming products. The root cause is in `cir/**`, which
another department owns, and a title edited to match a weaker fabric is a merchandising decision
somebody should make on purpose rather than a side effect of a planning module.
