VERDICT: DO NOT SHIP d62208d331a3c56f670f896c95ad9827de69c884

# Independent review: origin/eng/learn @ d62208d3 (ENG-LEARN slices 1–4)

Base: origin/claude/w6-INTEG3 @ 39b926194fac895948d66b85261ff1965453cf04 (the merge-base, so the merge is a fast-forward).
Reviewed 2026-11-20. The suites ran on a venv with requirements.lock versions (starlette 1.6.0, fastapi 0.141.1).

## Suite results (`JOBS=4 SUITE_REGISTRY=0 SUITES=… bash run_tests.sh`)
These are the same 52 named suites plus each tree's own new ones: every suite naming lesson, learn, improve, consume, department, charter or kpi, plus test_model_spend_paths, test_cost_governance_wave2, test_route_auth_default_deny, test_w4_readback_evidence, test_w4_resume_runner, test_v11_autonomy_timeline, test_w4_fmbatch1_retention_guard, test_etsy_oauth_callback and test_vacuity.

| Tree | Passing | Failing suites |
|---|---|---|
| base 39b92619 | 618 | **0** |
| base + learn (d62208d3) | 644 | **2** |
| base + learn + improve | 672 | 3 (the union of both units' failures; no new interaction failure) |

The unit's own suites are green: test_eng_learn, test_eng_learn_patterns and test_eng_learn_wiring.

### Blocking regressions. Both are introduced by this unit, and the base is green.
1. **`test_vacuity` fails.** The failing test is `test_no_new_vacuous_risk_loop_anywhere_in_the_suite`. The cause is `tests/test_eng_learn_wiring.py:46`, which loops `for jt in SUSPENDED + ("learning.loops",)` with no non-emptiness assertion.
   **Fix:** add `assert SUSPENDED` (or a `# vacuity-ok:` reason).
2. **`test_w4_readback_evidence` fails.** The failing test is `test_readback_evidence_names_the_checks_the_server_serves`, at `assert {s for _i, s, _k in readback.EVIDENCE_ITEMS} == set(pe.SECTIONS)`.
   - The unit adds a `learning` section to `ops.production_evidence.SECTIONS` but does not add it to the readback client's `EVIDENCE_ITEMS` (`ops/readback.py`).
   - So the operator's readback CLI does not read the new section, and the contract test catches the drift.
   - **Fix:** add the item to `ops/readback.py`.

## Requirement checks

### No fabricated learning
- **Lessons need evidence thresholds.** PASS in code:
  - image lessons: n ≥ 20 per side, α 0.01 with Bonferroni across the scope;
  - pattern lessons: one-sided Fisher exact test, n ≥ 6 per side, α 0.01 with Bonferroni;
  - commerce lessons: ≥ 200 visits per side, ≥ 5 orders, p < 0.01.

  My probe against the shipped code:
  - 12 vs 12 frames at 100% vs 0% gives 0 lessons (below the floor);
  - 40 seeds of 200-frame 50/50 noise give 0 of 40 with any lesson.
- **Champion/challenger promotion.** PASS. My synthetic test used `compare()` with an 85/15 split, a look every 20 frames, and futility after 400 challenger frames.

  | Stream | Trials | Promoted | Notes |
  |---|---|---|---|
  | Identical arms, p = 0.2 | 400 | 6 | |
  | Identical arms, p = 0.5 | 400 | 4 | |
  | Identical arms, p = 0.8 | 400 | 5 | |
  | Identical arms, p = 0.95 | 400 | 0 | |
  | Identical arms, with the cost path | 400 | 2–10 | |
  | +10pt challenger | 200 | 168 | |
  | +15pt challenger | 200 | 198 | |

  - Across the noise streams the false-promotion rate is about 1–2.5%.
  - A demotion path rolls back a promotion that its later frames contradict.

  This is a statistically meaningful gate. It cannot be "never" literally, and the builder's own 0.9% figure is consistent with what I measured.
- **UNKNOWN on small samples.** PASS:
  - `stats.rate` returns UNKNOWN below n = 10;
  - a trend needs two measured windows;
  - the empty-company summary and readback read UNKNOWN (tested).
- **A no-op never counts.** PASS:
  - `made_progress(outputs, job_type)` now judges declared WORK_KEYS through `did_no_work`;
  - `improve.monitor` no longer counts the standing `promoted`;
  - `lessons_applied` counts only `bus.acted_on`;
  - `compare` on identical or zero-variance arms returns `continue`.

### Suspended learners
PASS. They were fixed at the root cause, not just unsuspended:
- they got `UPSTREAM_INPUTS` entries, gated by real declared work;
- `visual.rnd.cycle` now counts its hero work;
- `creative.image_benchmark`'s superseded branch now does DB-only learning work.

No backoff was removed. `SPENDING_PREFIXES` is unchanged, so `creative.*` and `visual.*` (including the paid vision job `creative.reference_reading`) stay spending-classified and get no release re-arm probe. `learning.loops` is GREEN, CA$0 and in FREE_JOB_TYPES.

### Spend
PASS:
- assignment *replaces* the champion's generation and never adds one;
- `share()` = min(0.15, 0.20);
- ≤ 2 challengers per scope;
- the new loops are DB-only.

### Consumers
- **Pattern lessons:** PASS. They are consumed by `cir.draft`, which records `learning_advice` (advice only, never a refusal), and by `radar.score` and `consume.matching` through `construction_preference` and the new `engineering_risk` DISFAVOURS subject (tested to direction −1).
- **Image lessons:** PARTIAL. The image-prompt interface `image_lessons.prompt_for` exists and is tested. It returns champion or challenger templates derived from lessons, plus `scene_lessons`. But **no producer calls it yet** (grep: 0 callers), and nothing consumes the `image_production` bus subject for creative_assets or quality. This is honestly disclosed in BUILD_STATE and the review request. It is not blocking for this slice, but no image lesson changes behaviour in production until ENG-VIS-GALLERY or ENG-VIS-FLUX adopts the contract.

### Mutation testing
Each mutant was run against its own suite.

**Killed:**
- `ALPHA 0.002→0.5`
- `MIN_N 40→2`
- promotion condition → `True`
- `CHALLENGER_SHARE 0.15→0.6`
- `PATTERN_ALPHA 0.01→0.9`

**Survived (test-coverage gap on the evidence thresholds; required fix alongside the two regressions):**
- `stats.LESSON_MIN_N 20→1`
- `stats.LESSON_ALPHA 0.01→0.9`
- the Bonferroni division removed in `image_lessons.derive_lessons`
- `pattern_lessons.PATTERN_MIN_N 6→1`
- `commerce_lessons.MIN_VISITS 200→1`
- `commerce_lessons.MIN_ORDERS 5→0`
- `commerce_lessons.ALPHA 0.01→0.99`
- `stats.TREND_MIN_N 10→1`
- `stats.MIN_LIFT 0.08→0.0` (minor: the α still guards)
- `CHALLENGER_SHARE_CAP 0.20→0.9` (equivalent mutant while the share is 0.15; acceptable)

The shipped code applies all of these correctly (verified by my probes above). But nothing in the suite would catch a later weakening of the "lessons need evidence" guarantee.

**Required:** boundary tests just above and just below each floor, and a near-threshold noise stream that fails with alpha 0.9 or without Bonferroni.

## Fit with eng/improve
- Merging the two needs four mechanical resolutions:
  - BUILD_STATE.md and DECISION_LOG.md: keep both sides;
  - `sw.js`: both bumped from v39 (learn v40, improve v41), so the integrated tree needs **v42**;
  - `autonomy_map.json`: regenerate it with `python -m brambleloop.autonomy.map --write`.
- After resolution, no extra failures.
- Shared lesson store: improve reads `core.models.Lesson`, `bus.acted_on` and `learn_decisions`. Learn publishes its lessons to that same bus (`bus.publish`, confidence `measured`) and keeps its own `learning_*` tables. They interoperate through the bus. Improve's declared seam (`department_loops.lessons`/`_fired`) is not yet switched to the `learning_*` store; that is a follow-up, not a conflict.

## To ship
Fix regressions 1 and 2, add the threshold boundary tests, and re-run the named suites to 0 failing.
