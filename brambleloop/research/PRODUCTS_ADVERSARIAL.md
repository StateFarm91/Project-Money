# Adversarial audit: the four product modules

**Date:** 2026-09-25 (UTC)
**Scope:** `src/brambleloop/products/personalisation.py`, `motifs.py`, `texture.py`, `vessels.py`
**Tests:** `tests/test_products_adversarial.py` (15 tests)
**Run by:** a cloud pilot session, working only inside the four modules above, their three
existing test files, this document and the new test file. Everything else in the tree was
read and not touched.

These four are pure computation with no I/O, and they generate customer-facing pattern text
and construction. There is nobody downstream of them: what they put in a `finished_size_note`
is what a buyer reads, and what `personalisation.check` says a custom design needs is what a
shop will make it pass. A defect here reaches the buyer directly.

The hunt was for this codebase's five recurring defect shapes:

1. a verdict computed from the **absence of evidence** (no data silently reads as "fine");
2. a check that **cannot see** the thing it exists to measure;
3. **one value living in two places** that can drift apart;
4. a proof measured on a **sample that cannot contain the broken case**;
5. a **docstring asserting a property the code does not have**.

All five were present. Nine defects were found: seven fixed inside the boundary, two left and
documented below.

## Baseline

A full `bash run_tests.sh` was run before any edit.

```
TOTAL PASSING: 2963 ; suites failing: 2
```

**The baseline was not green**, and the two failures were nothing to do with this audit.
`tests/test_deploy.py` and `tests/test_health.py` both died importing
`fastapi.testclient` → `starlette.testclient`, which needs an HTTP client package that
`requirements.txt` does not pin (starlette 1.7.0 wants `httpx2`, and accepts `httpx` with a
deprecation warning; `requirements.txt` lists neither, and `uvicorn[standard]` does not bring
one). Installing `httpx2` into the gitignored `.venv` fixed both suites with no repository
file touched. See **Left in place** — the missing pin is a one-line change to
`requirements.txt`, which is outside this audit's boundary.

## Final

```
TOTAL PASSING: 3014 ; suites failing: 0
```

**3014 against a baseline of 2963, and zero failures.** The +51 is accounted for exactly,
suite by suite, against the baseline log:

| suite | baseline | final | why |
|---|---:|---:|---|
| `tests/test_deploy.py` | 0 | 32 | died at import; the whole suite now runs |
| `tests/test_health.py` | 26 | 30 | 26 already passed; 4 needed the HTTP client |
| `tests/test_products_adversarial.py` | 0 | 15 | this audit |
| **total** | **2963** | **3014** | **+51** |

**No other suite changed by a single test, in either direction.** Comparing per-suite pass
counts across the two logs, `test_health.py` is the only pre-existing suite whose count moved
at all. Nothing was weakened, skipped or deleted to get there: all three existing test files
inside the boundary — `test_personalisation.py` (12), `test_texture.py` (21) and
`test_motif_fidelity.py` — pass unmodified, as do `test_products.py` (16) and
`test_geometry.py` (44), the two suites outside the boundary that exercise these modules
hardest.

---

## Fixed

### F1 — `personalisation.NEEDS_THE_CHAIN` was a stale second copy of the chain

*Shapes 3, 5 and 4 stacked on one another.* **`personalisation.py:83`** (original).

```python
# What a construction-level option must do before it may be sold. The chain's own stages,
# named rather than restated: this module routes, it does not certify.
NEEDS_THE_CHAIN = ("compile", "twin", "geometry", "write", "reverse", "certificate")
```

The comment says the stages are "named rather than restated". The line underneath restates
them, and the copy had gone stale. `gates.certificate.CANONICAL_STAGES` is ten stages:

```
compile, twin, geometry, write, reverse, originality, asset_truth, policy,
physical_test, confidence
```

Five were missing: **`originality`, `asset_truth`, `policy`, `physical_test`, `confidence`**.

**The failing case.** `check(Offer("throw", "motif_arrangement", price_cad=8.0))` returns
`needs` — the list a shop follows to make a buyer's own motif arrangement sellable. It
omitted `originality`, which is the one stage that exists to stop a customer-supplied design
shipping under our name. A buyer's arrangement, or a name worked into the fabric, was routed
to a chain that never checked whether the design was ours to sell. `CLAUDE.md` names that as
a non-negotiable.

Worse, the guard that should have caught the drift could not. `test_personalisation.py:50`
asserts:

```python
assert set(out["needs"]) <= set(CANONICAL_STAGES) | {"certificate"}
```

A **subset** assertion holds for every omission there is. The check meant to keep the two
lists together passed cleanly all the way through the drift — shape 4, an assertion whose
shape cannot contain the broken case.

**Fix.** `NEEDS_THE_CHAIN = CANONICAL_STAGES + ("certificate",)`. The module docstring no
longer lists the stages either; it points at `CANONICAL_STAGES`. `gates/` imports nothing
from `products/`, so there is no cycle.

**Tests.** `test_a_custom_design_is_routed_to_the_whole_chain_and_not_to_half_of_it`,
`test_a_subset_assertion_cannot_see_a_stage_that_went_missing` (which pins the direction the
old assertion could not look in, by showing the stale tuple satisfying the old shape).

### F2 — an unclassified customisation read as a cleared one

*Shape 1.* **`personalisation.py:106, 114, 122, 127, 146-147`** (original).

Every verdict in the module was reached by two equality tests — `level == CONSTRUCTION` gates
the certificate rule, `level == PRESENTATION` gates the pricing rule — and `ok` was computed
as `not reasons`. An option whose level is neither answers *no* to both, collects no reasons,
and comes back `ok: True`. Not because it was checked and passed: because nothing could see
it.

**The failing case.** An `OPTIONS` entry with `"level": "Presentation"` (a capital letter — a
plausible typo) is cleared for sale by `check`, and appears in **neither** list returned by
`catalogue`, which built its two lists with the same two equalities. The shop could not sell
it and could not see that it was not selling it.

**Fix.** One `_level_of(option)` used everywhere, which refuses a level that is not one of
the two constants; `_check_options()` runs at import so an unclassified option cannot wait
for a caller to find it; `catalogue`'s two lists are asserted to be a partition of `OPTIONS`.

**Tests.** `test_an_option_on_neither_side_of_the_line_is_refused_rather_than_cleared`,
`test_the_catalogue_is_a_partition_and_not_two_filters_that_happen_to_cover_it`.

### F3 — the bobble pillow's size sentence stated the opposite of its own arithmetic

*Shape 5, and it was customer-facing.* **`texture.py:133-134`** (original).

```python
finished_size_note=("Sized for a 45 cm floor cushion pad. Bobble fabric draws in, so "
                    "the panel is worked slightly wider than the pad."),
```

The panel is 70 stitches at 16 sts/10cm = **43.8 cm**. The pad is **45 cm**. It is 1.2 cm
*narrower*, and bobble fabric then draws it in further. The twin agrees: 43.80 × 43.90 cm.
The compensation was stated backwards, and a buyer sizing a cover by that sentence was
reading the opposite of the arithmetic three lines above it.

**Which half was wrong.** The arithmetic. A cushion cover wants to be a little smaller than
its pad so the pad fills it out taut rather than swimming in it — 43.8 cm for a 45 cm pad is
the right design, and the sentence describing it was simply backwards. So the sentence was
made to follow the arithmetic rather than the panel being rebuilt to follow the sentence.

**Why nothing caught it.** Nothing reads `finished_size_note`. It is set by every product,
serialised in `CIR.to_dict`, and consumed by no module in the tree: `publish/pdf.py:437`
takes the finished size from `twin.width_cm` / `twin.height_cm` instead. It is a customer-
facing claim with no reader and therefore no check — shape 2.

**Fix.** The number and the direction word are both derived: `across_cm(width, WORSTED)`
computes the panel, `PAD_CM` is named once, and the sentence says "narrower" or "wider"
according to the sign of the difference. The sentence cannot be backwards again.

**Test.** `test_the_bobble_panel_sits_the_way_round_its_own_sentence_says_it_does`.

### F4 — the other two size sentences were typed, not computed

*Shape 3.* **`texture.py:51, 75-76, 178-180`** (original). "21.8 cm" beside `width = 24`,
"about 22 cm across" in the note, "About 90 cm wide" beside `width = 144`. Each was a second
copy of a number computed two lines away. All three happen to be right today; all three go
wrong silently the first time anyone changes a width, and F3 is the proof that happens.

**Fix.** `texture.across_cm(stitches, gauge)`, used by all three notes.

**Test.** `test_every_texture_width_sentence_is_the_width_the_twin_measures` — every note's
figure is now checked against the twin that measures the piece.

### F5 — "Eighteen cable columns" was prose beside a computed number

*Shape 3.* **`texture.py:175`** (original). `across = _check(width, 8, ...)` computes 18; the
designer note spelled it out. Correct today, and a second copy.

**Fix.** The note interpolates `across`. **Test.**
`test_the_cable_column_count_is_counted_rather_than_spelled_out`.

### F6 — the coaster listing stated the size asked for, not the size made

*Shape 5 against the module's own docstring, with shape 4 explaining the silence.*
**`vessels.py:164`** (original).

`vessels.py`'s module docstring says, in terms:

> a target circumference becomes a stitch count the motif and the gauge both allow, **and the
> stitch count becomes the diameter that goes on the listing**.

It did not. The note printed `across_cm` — the size *requested*. `base_stitches_for` rounds
the count to a whole multiple of `wedges` **and floors it at `wedges * 2`** (`vessels.py:60`),
so the size asked for and the size made are two different numbers.

**The failing cases.**

| asked | stitches | actually made | listing said |
|------:|---------:|--------------:|-------------:|
| 10.0 cm (the default) | 60 | **9.55 cm** | "About 10 cm" |
| 7.0 cm | 42 | **6.68 cm** | "About 7 cm" |
| 1.0 cm | 12 *(the floor)* | **1.91 cm** | "About 1 cm" |

Below the floor the request is discarded outright and the note is independent of every number
underneath it — `build_hexagon_coaster(across_cm=1.0)` makes a 1.9 cm coaster and told the
buyer it was 1 cm. `across_cm` is a public keyword argument with no validation.

**Why nothing caught it.** `test_geometry.py:267` measures round pieces against their stated
size — but only for the three curated `BASKET_SIZES`, whose rounding error happens to be
under half a centimetre (−0.15, +0.16, +0.46). The coaster is measured for its corner count
and its chart aspect ratio, never for its size. A proof measured on a sample that cannot
contain the broken case.

**Fix.** `vessels.diameter_cm(stitches, gauge)` — the inverse of `base_stitches_for` — and
both listings are built from it. The coaster now reads "About 9.5 cm across the points". The
floor's behaviour is documented in `base_stitches_for`'s docstring.

**Tests.** `test_the_coaster_listing_states_the_size_the_stitch_count_makes`,
`test_the_basket_listing_states_the_size_the_stitch_count_makes`,
`test_the_size_asked_for_is_not_the_size_made_and_the_gap_is_reachable`.

### F7 — the motif library was a hand-maintained copy of the module's own contents

*Shapes 3 and 1.* **`motifs.py:146-149` and `156-169`** (original).

```python
LIBRARY: dict[str, Motif] = {
    m.slug: m for m in (FIR_AND_STAR, SNOWFALL, DIAMOND_LATTICE, CHEVRON_BAND,
                        BASKETWEAVE, HEART_ROW, PUMPKIN_ROW, CABLE_TWIST)
}
```

A tuple of the eight names defined above it: a second copy of the set of motifs the file
defines. **This had not drifted** — eight defined, eight registered, and the audit says so
rather than inventing a break. What makes it worth closing is what happens when it does.

`check_library()` iterates `LIBRARY`. A motif written in this file but left out of the tuple
is in no library, reaches no product, and — this is the part that bites — **is validated by
nothing**. `check_library()` would return `[]`, which reads as "the library is sound" and
means "the broken motif was not in the sample I looked at". The same disappearance is
reachable a second way: `{m.slug: m}` silently keeps the last of two motifs sharing a slug,
and the first is gone from the library and past no check.

This is the defect `run_tests.sh` already names in its own comments — a hand-maintained list
is wrong exactly when new work lands — in a second file.

**Fix.** `motifs.collect(namespace)` discovers every `Motif` in the module namespace, calls
`validate()` on each, and **refuses** a slug collision rather than resolving it.
`check_library()` now reports `MOTIF_UNREGISTERED` for any motif the module defines that is
not in `LIBRARY`, so an empty result means "everything this file defines was looked at".

**Tests.** `test_a_motif_left_out_of_the_library_is_reported_rather_than_unseen` (injects a
motif that is both ragged and far outside the density band, and shows the old check saw
neither), `test_two_motifs_sharing_a_slug_are_refused_rather_than_one_replacing_the_other`,
`test_the_library_holds_every_motif_this_module_defines`.

---

## Left in place

### L1 — the written cable pattern never says which way the cable crosses

**Not fixed: the fix is outside the boundary.**

`texture.build_cable_throw`'s docstring claims:

> which pair crosses in front is a property of the stitch instead of prose nobody checked

It is not a property of the stitch. `cir/stitches.py:97` defines `cable2x2` with a code, two
names, `consumes`, `produces` and two heights — **nothing about direction**. A 2-over-2
crossing worked front-to-back and one worked back-to-front are mirrored fabrics.

The only place the direction appears is `designer_notes` ("two held to the front, two worked
behind them, then the held pair") — and `designer_notes` reaches neither the buyer's document
nor any check. It is read by `publish/motif_fidelity.py:144` to extract a motif name and by
`gates/certificate.py:168` for a language check, and by nothing else. It is exactly the prose
nobody checked that the docstring says it is not. Shape 5.

**The failing case.** `write_pattern(build_cable_throw(), ...)` — the document the buyer
receives — contains:

```
Row 5: Ch 2, turn. [bpdc in next 2 sts, cable2x2 over next 4 sts, bpdc in next 2 sts] x 18. (144 sts)
```

The words `front`, `behind`, `held` and `cross` appear nowhere in any row line. `cable2x2` is
an abbreviation this system invented and the document never expands — there is no
abbreviation list or special-stitch section in `publish/pdf.py`. The buyer is told to work a
manoeuvre that is never defined, in a direction that is never given.

**Minimal proposed patch** (for whoever owns `cir/`):

1. `cir/stitches.py` — add a field to `Stitch`, e.g. `crossing: str = ""`, and set
   `crossing="front"` on `CABLE_2X2` and `CABLE_1X1` (the held pair passes in front).
2. `cir/writer.py` — where the crossing is rendered as `{code} over next {consumes} sts`,
   emit the direction too, e.g. `cable2x2 over next 4 sts (hold 2 to the front)`; and add a
   special-stitch definition block for any stitch in `twin.stitch_types_used` whose code is
   not standard crochet shorthand.
3. `cir/reverse.py` — `compare` must read the direction back, or step 2 makes the document
   and the CIR disagree and `REVERSE_PARSE` will fire.

**Test.** `test_the_written_cable_pattern_never_says_which_way_the_cable_crosses` pins the
gap so it stays visible. It asserts the current state deliberately, and its docstring says
that when the fix lands the test should fail and the right change is to assert the direction
*is* in the written pattern.

### L2 — `requirements.txt` does not pin an HTTP client for `starlette.testclient`

**Not fixed: `requirements.txt` is outside the boundary.**

`tests/test_deploy.py` and `tests/test_health.py` (62 tests) cannot run from a clean install
of `requirements.txt`. `fastapi.testclient` → `starlette.testclient` raises at import:

```
RuntimeError: The starlette.testclient module requires the httpx2 package to be installed.
```

starlette 1.7.0 imports `httpx2`, falling back to `httpx` with a deprecation warning.
`requirements.txt` pins neither, and `uvicorn[standard]` does not bring one. The suite was
therefore two suites short of green on any freshly built environment, and `run_tests.sh`
exited 2 rather than 0 — a red suite whose cause is a missing line, which is the kind of
persistent red that trains people to read "2 failing" as normal.

**Minimal proposed patch:** add `httpx2>=2.13` to `requirements.txt` (or `httpx>=0.27` to
stay on the deprecated path). For this session it was installed into the gitignored `.venv`,
which touches no repository file.

---

## Clean: what was looked for and not found

A clean area is a result. These were checked and are sound; nothing was changed on their
account and no finding was manufactured from them.

- **`motifs.Motif.validate()` is complete for what it claims.** `MalformedMotif` says "not
  rectangular, or not made of ones and zeros" and `validate` checks exactly those two, with
  row indices in the message. Every library motif is validated at module import via `_m`.
- **The motif notes' checkable claims are true.** `snowfall` says "twelve-stitch repeat" and
  is 12 wide; `heart-row` says "ten-stitch repeat" and is 10 wide. `diamond-lattice` says
  "every raised stitch touches another" — computed over all 8×9 cells, both standalone and
  tiled, and it holds. Pinned by `test_the_diamond_lattice_really_is_continuous`.
- **No duplicate motifs.** `check_library()`'s sha256 comparison is correct and all eight
  grids are distinct.
- **All motif densities are inside the 8%–72% band** (0.174 to 0.500).
- **Every motif width divides the width of every design that uses it.** `builder.build`
  refuses otherwise, and all eleven catalogue designs divide exactly.
- **`texture`'s technique claims are honoured.** The ribbed scarf works `fpdc`/`bpdc` in the
  same columns on all 100 ribbing rows; the bobble pillow's bobbles alternate position every
  second bobble row, which is a grid and not columns; the cable throw crosses every fourth
  row for 30 blocks. `gates.asset_truth.check_technique_claims` passes all three, and
  `test_texture.py` already covers this thoroughly.
- **The ribbed scarf's "about 147 cm" comment is right.** It looked wrong — 101 rows at 13
  rows/10cm is 78 cm — but `fpdc`/`bpdc` carry `row_height=1.9`, and the twin measures
  146.9 cm. The comment is correct and the gauge is not being misapplied.
- **`texture`'s repeat arithmetic divides exactly** in all three designs (24/4, 70/5, 144/8),
  and `_check` refuses otherwise with a message naming both numbers.
- **`vessels._disc_rounds` stacks its increases correctly.** `geometry.corners` reads 6 out of
  the coaster's stitch positions, and the increase-per-round rate (6) is within 7% of the
  geometric ideal at both gauges (6.1% over 5.655 cotton, 5.0% over 5.712 coaster), so the
  disc lies flat.
- **The basket's wall height is exact**, not rounded: all three sizes divide by the 0.5 cm row
  height with no remainder, and the three `BASKET_SIZES` diameters were within 0.5 cm even
  before F6 — which is precisely why F6 survived.
- **`personalisation`'s classification of the six options is right.** Letters and rearranged
  motifs really do change the chart, the counts and the fabric at the edges; colour, size
  selection from a graded range and print layout really do not.

### Looked at and deliberately not changed

- **`motifs` density is a whole-grid average**, so a motif of alternating all-raised and
  all-blank rows would average 0.5 and pass a band that exists to prevent exactly that
  fabric — shape 2 in principle. It is not reported as a defect because no motif in the
  library is anywhere near that shape, and any per-row rule tight enough to catch it would
  have to be loosened to let `basketweave` (rows of 0.5) and `fir-and-star` (rows of 0.0 and
  0.83) through. A threshold tuned until the current library passes is not a check; it is the
  eyeballing the comment says it replaced. Naming it here is the honest outcome.
- **`fir-and-star` has two isolated raised stitches** (no neighbour, even tiled). Its note
  makes no connectivity claim — unlike `diamond-lattice`, which does and honours it — and a
  single contrast stitch is legitimate in overlay mosaic. No claim is violated, so this is an
  observation, not a finding.
- **`personalisation.Offer.own_certificate` is a bare boolean the caller asserts**, and
  `check` cannot see whether a certificate exists or whether it covers the option — shape 2.
  It is not reported as a defect because the module's stated job is to *route*, not to
  certify ("this module routes, it does not certify"), and verifying the certificate would
  mean this module deciding what `gates.certificate` already decides. It is noted so that
  whoever wires `check` into a live listing flow knows the flag is an input, not a finding.

---

## Test inventory

`tests/test_products_adversarial.py`, 15 tests, all passing. Each was run against the
original modules (via `git stash`) to establish what it proves.

**Reproducing tests — fail against the original code, pass against the fix (10):**

| test | what it saw on the original |
|---|---|
| `test_a_custom_design_is_routed_to_the_whole_chain_and_not_to_half_of_it` | `originality is in the chain and was not in what this module asks` |
| `test_a_subset_assertion_cannot_see_a_stage_that_went_missing` | the stale tuple satisfying the old `<=` guard |
| `test_an_option_on_neither_side_of_the_line_is_refused_rather_than_cleared` | `an unclassified customisation was cleared for sale: ok=True` |
| `test_the_catalogue_is_a_partition_and_not_two_filters_that_happen_to_cover_it` | the unclassified option vanishing from both lists |
| `test_the_bobble_panel_sits_the_way_round_its_own_sentence_says_it_does` | `the panel is 1.2 cm NARROWER than the pad` |
| `test_every_texture_width_sentence_is_the_width_the_twin_measures` | `the sentence names [45.0] and the piece is 43.8 cm` |
| `test_the_cable_column_count_is_counted_rather_than_spelled_out` | `Eighteen cable columns…` |
| `test_the_coaster_listing_states_the_size_the_stitch_count_makes` | `asked 10.0, made 9.55 cm, listing says [10.0]` |
| `test_a_motif_left_out_of_the_library_is_reported_rather_than_unseen` | `check_library()` returning `[]` with a ragged, out-of-band motif present |
| `test_two_motifs_sharing_a_slug_are_refused_rather_than_one_replacing_the_other` | no mechanism existed to refuse a collision |

The size tests recompute the expected figures from the gauge locally rather than importing
the new helpers, so they fail on the number the buyer reads and not on a missing name.

**Guards and pins — pass against the original too, and say so (5):**

- `test_the_library_holds_every_motif_this_module_defines` — the drift in F7 is latent, not
  present. This is a regression guard, not a reproduction.
- `test_the_basket_listing_states_the_size_the_stitch_count_makes` — the basket's three
  curated sizes were already within tolerance. A regression guard; the coaster was the
  broken one.
- `test_the_size_asked_for_is_not_the_size_made_and_the_gap_is_reachable` — demonstrates the
  mechanism behind F6 (`base_stitches_for` is unchanged), so the finding cannot be dismissed
  as a rounding quibble.
- `test_the_diamond_lattice_really_is_continuous` — a clean result, pinned because it is a
  claim shipped in a note.
- `test_the_written_cable_pattern_never_says_which_way_the_cable_crosses` — pins L1, which
  was deliberately not fixed.

## Boundary

Files created or modified:

```
src/brambleloop/products/personalisation.py
src/brambleloop/products/motifs.py
src/brambleloop/products/texture.py
src/brambleloop/products/vessels.py
tests/test_products_adversarial.py        (new)
research/PRODUCTS_ADVERSARIAL.md          (new)
```

No file outside that list was modified, created or deleted. `tests/test_personalisation.py`,
`tests/test_motif_fidelity.py` and `tests/test_texture.py` were within the boundary but did
not need changing: every existing test still passes unmodified, and none was weakened,
skipped or deleted. No `git merge`, `rebase` or `pull` was run. Mitsuba was not installed and
nothing needing it was touched.
