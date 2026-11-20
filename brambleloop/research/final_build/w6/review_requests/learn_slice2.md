# ENG-LEARN slice 2: the pattern learning loop (`eng/learn`)

**Status:** builder branch. NOT reviewed, NOT integrated, NOT deployed.

## Connected, not rebuilt
- **Source.** Every engineering outcome already exists as a finished job that holds the CIR it
  judged:
  - `cir.draft` refusals;
  - `cir.compile`, with the compiler findings;
  - `gate.certify`, with the certificate's blocking findings. These cover the twin, reverse,
    Product Truth, size truth, originality, policy and the written deliverable.
  The loop reads those jobs. It adds no new hooks to the chain.
- **Construction family.** Taken from the newest `cir.drafted` audit row: the route family
  (vessel, tote, panel_pair, …) or the creative form. If there is none, the CIR construction
  is used. That action is already a protected lifetime read in `ops.retention`.
- **Draft and design-time consumption, through the existing machinery.**
  - "Prefer" lessons are published as `construction_preference`. They are already a favouring
    subject, routed to Market Radar, Pattern Engineering and Creativity. `radar.score` reads
    them as a score nudge (Market Radar) and as a draft-order heuristic (Pattern Engineering,
    `consume.matching`). Both record `bus.acted_on`.
  - "Avoid" lessons are published as a new subject, `engineering_risk`. It routes to Market
    Radar, Pattern Engineering and Creativity, and is added to `consume.DISFAVOURS`. So a
    concept in a known-failing region scores lower. The old `defect` subject does not route
    to Market Radar, so it could not do this.
- **`cir.draft`** (fallback and creative paths) records `learning_advice`, the measured regions
  the new CIR falls in, in the `cir.drafted` audit and the job result. This is advice only and
  never a refusal: deterministic validation still decides certification.

## Built: `learning/pattern_lessons.py`
- **`harvest`.** One observation per job, idempotent by job id. It records:
  - the family, the category and the binned parameters (rows, foundation, colours,
    components, yarn weight, risk class, assembly, stitch count);
  - each defect code, with the stage that owns it: compiler, twin, reverse, product_truth,
    size_truth, deliverable, construction or certify.
  - Halts, duplicates, older-than-newest refusals and version conflicts are excluded, because
    they say nothing about the design.
- **`designs` / `first_pass_by_family`.** A design (`slug@version`) is first-pass when its
  first compile passed and its first certificate was granted with no revision. A design still
  in the chain is pending and not counted. The rate is reported per family in 14-day rolling
  windows:
  - a window with fewer than 10 designs is UNKNOWN;
  - the trend is UNKNOWN without two measured windows;
  - "improving" needs one-sided p < 0.05.
- **`derive_lessons`.** A parameter region against the rest of its family, using a one-sided
  Fisher exact test (samples are small). It needs 6+ designs per side, alpha 0.01 and
  Bonferroni over the family's comparisons. Lessons whose evidence weakens are deactivated.
- **`advise(cir, family)`** and **`lessons_applied`.** `lessons_applied` counts bus `acted_on`
  only, never lessons that were merely published.
- **`record(...)`.** A direct recording entry point for deliverable QA. It is not yet called by
  the PDF QA path: see "Not done".

## Tests: `tests/test_eng_learn_patterns.py` (6/6)
- A truly failing region (100+ rows: 15% vs 90%) becomes `pattern:tote:rows:100+:-`. Its
  statement names the recurring REVERSE/SIZE codes. `advise` names it for a new long tote and
  not for a short one. It reaches `consume.matching("market_radar")` with direction -1.
- A noise region (60% vs 60%) yields no lesson.
- Compile failures count as not first-pass. Pending designs are excluded, and halted
  certifications are ignored.
- Trend:
  - 4 designs gives UNKNOWN;
  - 30% → 90% across windows is "improving";
  - 60% → 60% is `no_significant_change`.
- The Fisher test is exact (5/5 vs 0/5 gives 1/252).

## Not done
- **Deliverable QA outside `gate.certify`.** PDF build QA in `assets.build` is not harvested
  yet. `record()` is its entry point.
- **Draft-time advice does not change geometry.** Changing parameters automatically would put
  a lesson in front of a construction rule. The ranking path is the consumer.
- **No production readings.** Not run against production, so the real first-pass rate per
  family is UNKNOWN here.
