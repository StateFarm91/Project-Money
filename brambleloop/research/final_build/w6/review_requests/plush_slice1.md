# [ENG-PLUSH] Slice 1 review request: amigurumi as a core family, under a child-safety content gate

- **Branch:** `eng/plush` (from `claude/w6-INTEG2` 809107b5, plus `eng/families` 777a66f3, which
  is independent-review SHIP and already in INTEG3). Not merged, not deployed.
- **Directive:** D-OWNER-CORE-FAMILIES, Track 2.
- **Ported:** `opus2/p0-amigurumi` 98d216b, 1,089 lines.

Slices 1 to 3 were built and are pushed together. Many files carry changes for more than one
slice. Each slice has its own review document, which lists the files and tests that are its
own. Suite and mutation results are at the end of this document.

## What this slice delivers

### 1. Port, and every open finding fixed

**OPUS2T-4 (HIGH, child safety): fixed.** INTEG2's A1-R gate already makes the construction the
primary trigger (`launch0.closed_stuffed_form`, `ChildrensDecisionRequired`), and it supersedes
opus2's `stuffed_figure` trigger. The conflicts were resolved toward INTEG2.
- `stuffed_figure` is kept as a helper.
- It now also recognises a body that states a stuffing point.
- Every look-alike-letter and neutral-title case is still refused by the renderer (tests in
  `test_opus2_amigurumi` and `test_opus2_a1_children`).

**OPUS2T-5: fixed.** There is now one definition of a small part: `gates.small_parts.blocking`,
in which FITS and UNKNOWN both block.
- The engine refuses any yarn weight at which an ear fits or may fit the cylinder.
- Sport weight is refused. DK, worsted and bulky are clear.
- opus2's own geometry copy is removed.

**OPUS2P P-1 (HIGH): fixed.**
- plush, softie and teddy are added to the infant-product nouns.
- bear, bunny and rabbit are deliberately NOT added. `_PET_TOY` already reads bunny and rabbit
  as pets, and the construction catches every toy anyway.

**P-2 to P-9: carried over, and their tests pass.** Two needed changes:
- **P-2 (counted joins):** there is no base disc any more. The ear join is still measured by
  stitch count, and the mismatch test now uses a 30-st ear.
- **P-7 (sewing tail):** the tail is now 30 cm (`AMI_SEWING_TAIL_CM`).

**A defect the new gate found in the port.** The opus2 ear was 9 sts flattened, sewn across an
8-st span: an 11% mismatch, so it did not assemble. The ears are now 20-st discs (5 wedges)
that flatten to 10 sts, sewn across exactly 10 sts.

### 2. CIR model: closed spiral rounds, stuffing points, placed joins

**New Component fields:** `stuff_at_round` and `closes`.
- `to_dict` omits them at their defaults, and `from_dict` reads them.
- No existing digest moves (`test_cir_roundtrip`).

**The body** is one closed piece in `spiral_rounds`:
- a magic ring of 6;
- staggered increases to 36;
- 7 even rounds;
- staggered decreases to 6;
- a gathered closure.

It is stuffed after the 18-st round. Two placed ears are whipstitched across round 6, mirrored.

**`cir/closed_forms.py`** is called by `compile_cir` and is all ERROR. Its findings:
- STUFFING_POINT_UNKNOWN_ROUND, STUFFING_POINT_TOO_EARLY, STUFFING_OPENING_TOO_SMALL (under 12
  sts), STUFFING_AFTER_CLOSE;
- CLOSED_FORM_OPEN (over 8 sts), CLOSED_FORM_UNSTUFFED, CLOSED_FORM_NOT_ROUNDS;
- PART_GEOMETRY_GATHERED, PART_GEOMETRY_TOO_SHALLOW (the meridian is shorter than the widest
  diameter), PART_GEOMETRY_NO_GAUGE.

The geometry is `cir.geometry.measure`, the same one the twin carries. The twin still refuses a
height for a closed shape and states only the circumference.

**Writer and reverse compiler.**
- The writer prints `Stuff after Rnd N:` and `Close after Rnd N:` in place.
- The PDF keeps these lines in order among the rounds instead of lifting them out as notes.
- The reverse compiler reads both back independently. REVERSE_CLOSED_FORM catches a dropped or
  moved line in US and UK.

### 3. The child-safety pattern-content gate (`gates/child_safety.py`)

Each check is PASS, FAIL or UNKNOWN. The verdict is PASS only when every check passes, FAIL if
any fails, and HELD when only UNKNOWNs remain.

| Check | What it enforces |
|---|---|
| FEATURES_EMBROIDERED | No safety eye, button, bead, bell, pellet, wire, magnet, glue, snap or zip in any material, note or instruction. A face must be embroidered with yarn. |
| FEATURES_INSTRUCTED | The printed instructions (not only the CIR's notes) tell the maker to embroider the face. |
| JOINS_VALIDATED | Every sewn-on piece is joined by a sewing method, at a stated position, measured by `cir.assembly` (does_not_assemble is FAIL, anything unmeasured is UNKNOWN), and sewn through both loops with the tail buried. |
| NO_CORDS_OR_LOOPS | No threaded cord, no chain-only piece, no chain run over 6 inside a row, and no cord, ribbon, string, strap, tie or loop words. |
| STUFFING_GUIDANCE | New polyester toy stuffing is named. Every stuffed piece states both its stuffing point and its closure, and `closed_forms` is clean. |
| SMALL_PARTS | `gates.small_parts.blocking` is empty. |
| PHYSICAL_EVIDENCE | Required for anything stuffed or with sewn-on pieces. No content-bound authority exists, so this is always UNKNOWN today, and the item is HELD. |
| SAFETY_SECTION, CITATIONS, NO_CERTIFICATION_CLAIM, NO_HARD_PARTS_IN_TEXT | Checked on the rendered PDF text: every required statement is present, every source is printed with its URL and "accessed 2026-11-20", and no "tested", "certified", "meets ASTM", "CE", "safe for babies" or "non-toxic" claim appears. |

**Where the gate is wired in:**
- **`gates.certificate.certify`, step 6e.** A FAIL becomes `CHILD_SAFETY_<CODE>` and an UNKNOWN
  becomes `CHILD_SAFETY_<CODE>_UNKNOWN`. Both are ERROR.
- **`publish.pdf`.** It renders the section "Child safety: read before you make this", reads the
  finished bytes back, and refuses on any FAIL.

**Scope.**
- The gate applies to: a children's assignment; child words; a stuffed figure (whatever any
  decision says); any stuffed or closed piece in rounds; and a closed stuffed form decided FOR
  a child.
- An undecided stuffed panel-pair cushion is not in scope. The A1-R decision gate already holds
  it.
- Of the 26 engineered catalogue CIRs, only the two baby blankets are in scope, and both PASS.

**Citations.** Each was read on a primary page on 2026-11-20: 16 CFR 1501, 16 CFR 1500.19(b)(1),
SOR/2011-17 (s.7, s.29, s.31), Health Canada toy safety tips, CPSC Publication 5100, CPSC safe
sleep, and Health Canada safe sleep.
- **NOT stated, because none was confirmed:** a Canadian cord-length rule (SOR/2011-17 has
  none), an age in months on CPSC's safe-sleep page, and ASTM F963's 12-inch cord limit (found
  only in a 2010 CPSC staff memo).
- **Re-read word for word before any live listing:** the canada.ca and cpsc.gov quotes, which a
  summariser extracted.

**We sell patterns.** The section says so, and claims no testing or certification. The existing
A1-R children's statements (supervision, construction integrity, selling finished items) still
render alongside it.

### 4. PDF deliverable

- **Every round** is printed with its count, and the stuffing and closing steps are in place.
- **Part diagram** (`publish/part_diagram.py`):
  - every piece is drawn at one scale from the twin;
  - every join is drawn at its stated round and stitch span;
  - stuffing and closure are marked;
  - it is labelled "not a photograph".
- **Child-safety section.**
- **US and UK** both render.
- **Children's age statement:** for a closed shape it now states the circumference ("about 29 cm
  around its widest round, its height set by the stuffing") instead of being unrenderable.
- **Fibre:** a stuffing material is not read as a yarn fibre.

### 5. Routing (`creative/construction_families.py`)

`amigurumi` moves from UNBUILT to **physical_gate**, pinned by
`tests/test_eng_plush.py::test_a_research_amigurumi_is_physical_gated_end_to_end`.
- **Admitted:** a plain ball-body bear or bunny.
- **Held, with a `construction_unsupported:amigurumi` reason, for:**
  - any other animal or character ("Meadow Hare");
  - an unmodelled texture ("fluffy", "brushed", "faux fur", "fur", "chenille", "boucle"), with
    the reason naming the missing loop-stitch or brushed engine;
  - more than one toy;
  - an accessory or rattle.
- **H1 named features:** `amigurumi_features` and the new `embroidery` feature are honest only
  for the amigurumi and lovey families (embroidery also for appliqué covers). Every other family
  is held on them exactly as before.

### 6. Shared fixes the tests found

- **`gates.asset_truth`:** colours are read from every piece, as the stitch check already was.
  Contrast-colour ears were refused as ASSET_COLOR_ABSENT.
- **`gates.risk_matrix`:** `closed_3d_form` is now also raised by `stuff_at_round` or `closes`.
  Without this, a stuffed body declaring class A would not be raised to class C.
- **`cir.writer.finishing_lines`:** a piece with a stuffing point gets "stuffed and closed, so it
  is not blocked". It had been told to damp-finish standing up.

## End-to-end proof

`test_a_research_amigurumi_is_physical_gated_end_to_end` runs the real handlers on SQLite:
`radar.concept_intake` → `radar.score` → `cir.draft` → `cir.compile` → `gate.certify`.

- **Certification is withheld for exactly two reasons:** `PHYSICAL_TEST_REQUIRED` and
  `CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN`.
- **The US and UK PDFs carry:**
  - every round's count;
  - the Stuff and Close lines;
  - the part diagram figure;
  - the full safety section;
  - the gate verdict HELD, with only PHYSICAL_EVIDENCE not PASS.
- **The renderer is given a TEST assignment** (`build_pattern_pdf(childrens=...)`). With no
  decision, the same CIR is refused (`ChildrensDecisionRequired`).

## Mutation run

`scripts/mutate_plush.py` weakens each new rule in a scratch copy of the tree; `test_eng_plush`
must kill it.
- **First run:** 31 of 34 killed. The three survivors (thread as a cord, a stuffed piece that
  never closes, the engine's own small-parts refusal sitting behind the size floor) each got a
  direct test.
- **Final run:** see "Results" below.

## Results

See `plush_results.md`, which holds the suite list and counts at the pushed commit.
