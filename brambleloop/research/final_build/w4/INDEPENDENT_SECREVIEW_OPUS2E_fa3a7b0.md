# Independent security review OPUS2E: `opus2/p0-revenue-workforce` @ fa3a7b09 (delta from fb52cb9e)

Reviewer: independent Claude Code session, 2026-11-01. Read-only review: nothing was pushed to
`opus2/*` or `claude/repository-setup-nc9x6o`.

**Scope.** These are the non-merge commits in `fb52cb9e..fa3a7b09`, excluding merges of
`claude/w4-INTEG8-next`:

| Commit | Subject |
|---|---|
| 768f2b35 | Tote: a vessel with two measured, sewn straps, plus the `cir.assembly` round span |
| 30a9eb7d | Egg cosy: one-piece cups worked from the crown down |
| 9caf0e0b | CYC head-circumference chart sourced; a hat is refused |
| 129dc17a | Seven completion states recorded per cluster (records only, handoff §28) |
| fa3a7b09 | Fixes for the OPUS2D LOW items R1–R5 and the INFO wiring test |

## Verdicts

| Part | Verdict | Findings |
|---|---|---|
| Tote (768f2b35) | **CHANGES REQUIRED** | E1 MEDIUM, E5 INFO |
| Egg cosy (30a9eb7d) | **ACCEPT** (fix E3 before any cosy can pass name truth) | E3 LOW, E4 LOW (latent) |
| Hat refusal and CYC chart (9caf0e0b) | **ACCEPT** | none |
| Records (129dc17a) | **ACCEPT** | none |
| R1 anchor state from the latest finished attempt | **ACCEPT** | mutation killed |
| R2 shared purchase-request cap | **ACCEPT** | mutation killed |
| R3 behavioural `gate.quality` enqueue test | **ACCEPT** | mutation killed |
| R4 SHA-256 swap test | **ACCEPT** | mutation killed |
| R5 size-claim false positives | **CHANGES REQUIRED** | E2 MEDIUM: the fix fails open |
| INFO: handler wiring for `slug=` and `rationale=` | **ACCEPT** | mutation killed |
| Digest-scoped versus product-wide size halts | **ACCEPT** | nothing here depends on digest scope |

## Findings

### E1 MEDIUM: any "bag" title drafts as an open strapped tote, and the straps count as the pieces the title promises

`FC.plan` sends **every** `category="bag"` concept to `TOTE`. It also sends every title matching
`\b(?:tote|bag|market bag|shopper)s?\b` in any category, unless the rest of the title is shaped.
`"bag"` was removed from `NEEDS` and `_SHAPED_WORDS`, so nothing refuses a bag that is not a tote.

There are two consequences, and `eligibility.name_truth` returns `[]` for every probe below:

1. **Wrong form.** All of these draft as an open large basket with two 50 cm straps:
   - "Drawstring Bag"
   - "Plastic Bag Holder"
   - "Backpack" (category bag)
   - "Clutch"
   - "Crossbody Phone Bag"
   - "Bean Bag Toss"
   - "Lavender Sachet Bag" (category `home_decor`)
   - "Small Tote" (always drafted at size **large**)
   - "Baby Diaper Tote"
2. **Multiplicity backed by straps.** `launch0.title_promise` sums `Component.make`. A tote
   is 1 body plus `make=2` straps, so it reports **3 pieces**.

   | Title | `plan` | `title_promise` | Result |
   |---|---|---|---|
   | "3 Tote Bags" | tote | "the title claims 3 pieces and the CIR makes 3" | `backed=True`, but the pattern is **one** bag |
   | "Tote Bags x2" | tote | claims 2, makes 3 | backed |
   | "Gift Bag Set" | tote | "'set' … the CIR makes 3" | backed |
   | "Two Market Bags" | tote | no multiplicity seen | passes |

   E2 makes this worse: at fb52cb9e, "3 tote bags" and "Two Market Bags" were size or count
   claims (`vessel_count`) and `FC.plan` refused them. At fa3a7b09 they are not.

This is the same class as OPUS2C N3.1 ("trio drafted as one basket", MEDIUM): a title that
promises more than the CIR contains passes product truth.

**Reproduce** (`PYTHONPATH=src:tests`, after `import _tmp; _tmp.install()`):
```python
from brambleloop.runtime import pipeline
from brambleloop.creative import fallback_constructions as F
from brambleloop.publish import eligibility as E
from brambleloop.products import launch0
seed = pipeline._seed_for("everyday-market-tote"); g = pipeline.concept_geometry(seed)
c = pipeline.Concept(slug="x", title="3 Tote Bags", category="bag",
        stitch_repeat=[tuple(x) for x in g["stitch_repeat"]], width_stitches=10, rows=4,
        colors=g["colors"], risk_class=seed.risk_class)
F.plan(category="bag", title=c.title, slug="x")["family"]   # 'tote'
cir = F.tote(c)
E.name_truth(cir, None)                                     # []
launch0.title_promise(cir)                                  # claimed 3, makes 3, backed True
```

**Fix:**
- Route to `TOTE` only when the title names a tote, market bag or shopper. Refuse other bag
  forms with a `NEEDS` entry: drawstring, holder, backpack, clutch, crossbody, pouch, sachet,
  bean bag and similar.
- Honour size words (small or medium) or refuse them, rather than always drafting large.
- Make `title_promise` count finished objects, not pieces. Exclude parts joined into another
  piece by `cir.assembly`, such as straps, so a strap never backs "set" or a numeral.
- Add tests for "3 Tote Bags", "Gift Bag Set" and "Drawstring Bag".

### E2 MEDIUM: the R5 fix for over-refusal now lets real claims through (fail-open regression)

R5 asked to stop false positives on hooks, "bags of yarn" and "2x to 4x". The fix did this, and
each new exclusion is pinned: removing the tool exclusion or the vessel narrowing each fails
`test_review_opus2d_r5_…`. But it went further than R5 asked:

- `vessel_count` was narrowed from `_VESSEL` to baskets, bowls, bins, boxes and trays only.
- A blanket `(?!\s+of\b)` was added.
- `_TOK` in `named_range` was made case-sensitive.

As a result, phrases that fb52cb9e refused are now passed. `size_claims.claims_in` results:

| Phrase | fb52cb9e | fa3a7b09 |
|---|---|---|
| "3 plant pots" | `vessel_count` | **[]** |
| "2-piece pot set" | `vessel_count` | **[]** |
| "3 planters set" | `vessel_count` | **[]** |
| "3 tote bags" / "Two Market Bags" | `vessel_count` | **[]** |
| "Two baskets of different sizes" | `vessel_count` | **[]** (blocked by `(?!\s+of)`) |
| "Sizes s to xl" (lower case) | `named_range` | **[]** |
| "3 baskets of yarn" (true negative) | `vessel_count` | [] (intended) |

The gate is meant to fail closed, so over-refusal was the safe direction. "Two baskets of
different sizes" is an explicit multi-size promise and now passes.

**Reproduce:**
```bash
cd brambleloop
PYTHONPATH=src python -c "from brambleloop.gates import size_claims as S; \
  print([S.claims_in(t) for t in ['3 plant pots','Two baskets of different sizes','Sizes s to xl']])"
```

**Fix:**
- Keep `_VESSEL` in `vessel_count`.
- Exclude only the contents phrases (`of yarn`, `of wool`, `of stuffing`) and the
  `holds/stores/fits` lookbehinds.
- Keep `_TOK` case-insensitive, but require a size context, or that the token is not followed
  by `x` plus a digit, so "2x to 4x" is still excluded.
- Add every row of the table above to the R5 test as a "still refused" case.

### E3 LOW: the egg cosy is smaller than the egg at four of eight yarn weights, and the test checks one

`count = round(EGG_AROUND_CM × st/10cm / 10 / 6) × 6` rounds to the **nearest** whole wedge, so it
can round down below the design girth. The 13.8 cm egg girth is stated as an assumption.

| Weight | sts | Around | Versus 13.8 cm | `certify` |
|---|---|---|---|---|
| lace | 54 | 14.6 | +6% | passes |
| fingering | 36 | 13.6 | **−1%** | passes |
| sport | 24 | 13.3 | **−3%** | passes |
| dk | 18 | 12.4 | **−10%** | `TWIN_DIMENSION_IMPLAUSIBLE` |
| worsted | 18 | 14.4 | +4% | passes |
| bulky | 12 | 12.6 | **−9%** | passes |
| super_bulky | 12 | 17.1 | +24% (loose) | `TWIN_DIMENSION_IMPLAUSIBLE` |

The test's "snug, between the girth and 15% over it" invariant holds only for the weight the
fixture uses. `certify` catches DK and super-bulky only because it parses the egg's 13.8 cm
from the note as the claimed size.

This is non-blocking today: name truth refuses every cosy (handoff §28, "until the W-LISTING
rule recognises a one-piece cup"). Fix it before that rule lands:
- Use a ceiling to the next wedge multiple.
- Refuse weights where one wedge is more than about 15% of the girth.
- Run the snugness assertion over every `gauge_for` weight.

**Reproduce:** loop `F.cosy(Concept(..., yarn_weight=w))` over the weights above and read
`finished_size_note`.

### E4 LOW (latent): cosy titles naming a character or a second object draft as a plain cup

`plan` returns `COSY` for:
- "Easter Bunny Egg Cosy"
- "Chick Egg Cosies"
- "Bobble Egg Cosy"
- "Easter Egg Cosy and Basket" (the basket is dropped)

These are refused today only by the same name-truth assembly rule as in E3. When the
one-piece-cup rule lands, add `_SHAPED_WORDS` or `NEEDS` coverage for:
- character words (bunny, chick, owl, face and similar), which need appliqué pieces;
- "and <object>";
- texture stitches the plain-sc cup does not contain.

The children's-product question: an egg cosy is tableware, not a toy, and toy, nursery and
amigurumi categories already refuse. Character cosies are the children-adjacent case. Keep
them refused rather than drafting them, so the children's gate never has to judge a plain cup
sold as a "bunny".

### E5 INFO: strap attachment

The craft arithmetic is correct:
- Chain 7, then 6 sc per row with a ch-1 turn, gives a 6-stitch strap.
- Each strap end is whipstitched across 6 stitches of the top round at the same gauge, so the
  join lengths match. `_placed_on_round_cm` measures 2 × `stitches_from_centre`, and an over-wide
  strap raises `ASSEMBLY_MISMATCH` (tested).
- Placement at n/8 and 3n/8, mirrored at +n/2, is a conventional tote handle spacing.

For a load-bearing bag, sewing only to the rim round is weak. Common practice is to overlap the
strap 2–3 cm onto the inside wall and sew around the overlap. This is design guidance, not a
defect.

## Checks with no finding

**Deterministic validation; reuse of families.** Tote and cosy reuse existing families:
- the tote is the existing `vessel()` at size large;
- the cosy uses `products.vessels._disc_rounds`;
- the strap is a plain `flat_rows` component with a `Seam`.

No new technique is introduced. Both constructions pass `compile_cir`, `build_twin` and
`reverse.compare(...) == []` in tests, and both are wired through `handle_cir_draft` with lineage
provenance. `ValueError` and `KeyError` still become an audited `cir.draft_refused`. The crown-down
cosy (magic ring, +6 per round to a flat crown, then straight rounds) is standard crochet.

**Hat and CYC chart.** I fetched `https://www.craftyarncouncil.com/standards/head-circumference-chart`
on 2026-11-01. Every figure in `HEAD_CIRCUMFERENCE_CM` matches the page's cm column exactly:
- preemie 23–30.5
- baby 35.5–40.5
- toddler 40.5–46
- child 45.5–51
- tween 51–56
- woman 53–58.5
- man 56–61

The page publishes no hat height and no negative-ease figure, so the refusal text ("publishes
circumference only") is true. The source URL and retrieval date are recorded. Only factual
measurements are transcribed, with no page text or layout, so there is no copyright concern.
The hat stays refused rather than guessed.

**Gates.** The new families are drafted before every downstream gate. `certify` (originality,
truth and assembly) and `name_truth` run on them in tests. `test_originality` (28),
`test_childrens` (40) and `test_opus2_size_claims` (12) all pass. E1 and E4 are gaps in what
those gates are asked, not bypasses.

**Size halts.** A disagreeing sample opens a defect with `product_slug=slug` and
`component=None` (`runtime/release.py:2999`), so the halt is product-wide. Nothing in this delta
scopes a size halt by digest or component. The tote (assembled) and the cosy rely only on the
product-wide behaviour, which is consistent with the Batch 4 decision.

**R1–R5 and INFO.** Each fix was reverted in turn, and its new test failed:

| Mutation | Test that failed |
|---|---|
| R1 condition back to `fail is attempted` | `test_review_opus2d_r1_a_queued_retry_never_hides_the_anchors_failure` |
| R2 shared-cap check → `if False` | `test_review_opus2d_r2_benchmark_refresh_honours_the_shared_cap_too` |
| R3 `gate.quality` enqueue disabled | `test_review_opus2d_r3_recertification_queues_exactly_one_gate_quality` |
| R4 SHA-256 comparison removed (`release_gates.py:748`) | `test_review_opus2d_r4_bytes_that_are_not_the_attested_photo_never_lead` |
| R5 tool exclusion disabled; `vessel_count` restored to `_VESSEL` | `test_review_opus2d_r5_…` (both) |
| INFO handler passes `slug=""`, `rationale=""` | `test_review_opus2d_the_handler_passes_slug_and_rationale_to_the_route` |

R1–R4 are fixed at the root with discriminating tests. R5 discriminates for what it excludes,
but over-reaches (E2).

**Records (handoff §28).** These are honest:
- Integrated, certified, deployed, production-verified and end-to-end are "no" for every
  cluster.
- The tote, cosy, cushion and triangle are marked "not yet reviewed". This is accurate: OPUS2D
  explicitly excluded 3232862 and 9b8f842.
- Known blocks are disclosed, including the cosy name-truth refusal and a `test_risk_matrix`
  failure on the integration base.

Nothing claims a deployment or production evidence.

## Suites run (fa3a7b09, `PYTHONPATH=src:tests nice -n 19 python tests/<f>`, one at a time)

`sqlalchemy` and `requirements.txt` were installed first; the container lacked them.

| Suite | Result |
|---|---|
| test_opus2_draft_constructions | 13 passing, 0 failing |
| test_compiler | all OK |
| test_twin | all OK |
| test_reverse | all OK |
| test_originality | 28 passing, 0 failing |
| test_childrens | 40 OK |
| test_opus2_size_claims | 12 passing, 0 failing |
| test_vacuity | all OK |
| test_radar | all OK |
| test_opus2_knowledge_gaps | 9 OK |
| test_opus2_photo_led_gallery | 9 OK |
| test_opus2_reverify_withhold | 6 OK |
| test_opus2_scan_evidence | 9 OK |

Probes and mutations were run from `/tmp`, outside the repository. The source tree was restored
after each mutation.

## Required before integration

1. **E1:** narrow the tote route, and stop straps backing multiplicity in `title_promise`.
2. **E2:** restore the recall of `vessel_count` and `named_range`, keeping only the targeted
   R5 exclusions.

Before the cosy name-truth rule opens: **E3** (ceiling and every weight tested) and **E4**
(character and compound cosy titles refused).
