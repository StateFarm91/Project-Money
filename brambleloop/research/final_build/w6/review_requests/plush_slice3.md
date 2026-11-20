# [ENG-PLUSH] Slice 3 review request: baby items under the child-safety gate

- **Branch:** `eng/plush`. Not merged, not deployed. Suite and mutation results: `plush_results.md`.
- **Files that are this slice's own:**
  - `creative/baby.py` (new);
  - the lovey route in `fallback_constructions._plan` and the pipeline;
  - the `lovey` family;
  - `radar.intake`'s engine-sized exemption;
  - `size_truth` (the lovey `NO_TEMPLATE` entry removed).

## What it covers

### Baby blankets

These are the existing **verified** flat-panel family. Their construction is unchanged.
- They are inside `gates.child_safety` because of their child words. Their profile is base plus
  sleep.
- Every baby blanket PDF now carries the child-safety section with the safe-sleep statement
  ("Keep this out of a baby's crib, cot or bassinet"), citing CPSC "Bare is Best" and Health
  Canada safe sleep, both accessed 2026-11-20.
- `cloudline-baby-blanket` renders, and the gate PASSES on its finished PDF. A flat, unstuffed,
  one-piece blanket needs no physical evidence.
- **The catalogue's baby blanket PDFs change** (a new section). This is intentional.

### Simple flat baby garments: HELD

They are held as `construction_unsupported:garment`. The radar path has no sourced baby body
measurements or ease, so grading is not supported there. This is the honest answer to "where
grading supports them".

### Loveys: `creative.baby.lovey`

The head is the slice 1 closed spiral ball: 36 sts, stuffed after the 18-st round, closed at 6,
with two placed ears. It is sewn by a **surface join** to the centre of a plain sc square:
- the square is 30 x 30 cm (`LOVEY_SQUARE_CM`, a stated design size);
- it has no picots, loops or tassels.

Only a bear or bunny head is drafted.

**Routing.**
- A concept declaring the amigurumi construction names a lovey honestly.
- `size_truth`'s "the fallback makes neither the toy nor the join" was true until now and has
  been removed.
- `radar.intake` no longer applies flat-panel size bands to engine-sized families (lovey,
  amigurumi).

**Family status: physical_gate.** The proof is
`tests/test_eng_plush.py::test_a_research_lovey_is_physical_gated_end_to_end`:
- the real handlers run;
- certification is withheld only for `PHYSICAL_TEST_REQUIRED` and
  `CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN`;
- the US and UK PDFs carry every round and row count, the part diagram and the safety section,
  including the safe-sleep statement;
- the gate verdict is HELD.

**The renderer is given a TEST `("lovey", "under_3")` assignment.** With no decision, it is
refused.

## Not done in this slice (stated, not hidden)

- **No content-bound physical-evidence authority exists.** Every toy and lovey stays HELD;
  UNKNOWN is never PASS. Commissioning a tester sample is an owner spend decision and is not
  requested here.
- **Baby garments are held,** as above.
