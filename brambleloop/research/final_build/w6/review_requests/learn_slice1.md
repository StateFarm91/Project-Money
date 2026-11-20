# ENG-LEARN slice 1: the image learning loop (`eng/learn`)

**Status:** builder branch. NOT reviewed, NOT integrated, NOT deployed. Production unchanged.

## What was found and connected (not rebuilt)
- `image_candidates` (`visual.image_records`) already records every judged frame. Each row has:
  - prompt, prompt_version and references;
  - role, attempt and cost;
  - each gate check and its failure categories.
- Nothing turned these rows into measured lessons or a champion/challenger.
  - `visual.image_learning.propose_brief_challenger` registers a league challenger.
  - `improve.league.cycle` then waits forever for a recorded run on the shared task set. A run
    is model calls, and `challenger_runs` turns it into an owner spend card. So no image prompt
    challenger has ever been measured.
- The lesson bus (`improve.bus`) gains one subject, `image_production`. It routes from quality
  to creative_assets and product_creativity, and its lessons are published as `measured`.
  This is the `verified_lesson` stage.

## What was built
- **`learning/stats.py`.** Deterministic statistics: Wilson interval, one-sided
  two-proportion z test, a Welch test for cost, and `rate()`. `rate()` returns UNKNOWN below
  its minimum sample.
- **`learning/store.py`.** Five additive `learning_*` tables: observations (image and pattern),
  arms, decisions and derived lessons.
- **`learning/image_lessons.py`:**
  - **`harvest`.** Each candidate frame becomes one observation, idempotently by candidate id.
    Provider errors are skipped because nothing was judged. An observation holds:
    - closed-vocabulary features read from the prompt text and the recorded scene: camera,
      lighting, pose, room, Laura or product-only, reference set and role;
    - each gate's verdict: identity, outfit, product_fidelity, anatomy, realism, dimensions,
      quality and accepted;
    - the failure reasons, cost and attempt.
  - **`derive_lessons`.** Lessons are derived per `family:role`:
    - 20 frames per side, alpha 0.01, Bonferroni over every comparison in the scope;
    - lessons are published to the bus;
    - a lesson whose evidence weakens is deactivated.
  - **`propose_challengers`.** A "prefer" camera or lighting lesson becomes a challenger
    template: the champion plus that one change. It still has to win its own trial.
  - **`prompt_for` and the champion/challenger:**
    - assignment is deterministic, by a hash of the assignment key;
    - the challenger share is 15%, hard-capped at 20%, with at most 2 challengers per scope;
    - an assignment replaces the champion for that generation. It never adds a generation, so
      spend is unchanged and the existing generation-gate ceilings still apply.
  - **`evaluate`.** Challengers are compared with the champion only on frames from the same
    period.
    - **Promotion** needs 40+ first-pass frames per arm, p < 0.002 and a lift of at least
      +8pt. Or, on cost: 15+ galleries per arm, at least 15% cheaper per completed gallery,
      p < 0.002, with first-pass not worse by more than 3pt.
    - **Early stop:** a challenger that is measurably worse (p < 0.05, n ≥ 15) is retired.
    - **Futility:** a challenger still undecided at 400 frames is retired.
    - **Demotion:** a champion whose later frames are measurably worse than the evidence
      that promoted it is rolled back.
    - Every seed, registration, promotion, retirement and demotion is a `learning_decisions`
      row with its counts.
- **`visual.image_production.record_candidate`** now keeps the producer's `scene` dict as
  `checks._scene`. No gate reads it.

## Proof on synthetic streams (`tests/test_eng_learn.py`, 13/13)
These are measured with the shipped constants, using pure counts and 40 sequential looks per
trial:

| Stream | Trials | Promoted | Notes |
|---|---|---|---|
| Identical arms (noise) | 1000 | 9 (0.9%) | 785 retired as futile, 206 harm-stopped |
| +30pt challenger | 500 | 500 | |
| +15pt challenger | 500 | 497 | |

The database-backed tests check the following:
- the better arm is promoted;
- noise is not promoted;
- a worse arm is retired early;
- a contradicted promotion is demoted back to the old champion;
- a three-quarter-camera product-fidelity effect becomes a published lesson and then a
  challenger;
- scene noise yields no lesson;
- a diluted effect is deactivated;
- the share cap holds;
- assignment is stable.

## Suites run (all exit 0)
`test_eng_learn`, `test_compiler`, `test_reverse`, `test_twin`, `test_mine`, `test_w4_visnext`,
`test_learning`, `test_improve`.

## Not yet done (later slices)
- **Production frames.** The live producers do not yet call `prompt_for`, so no production
  frame is attributed to an arm. The scene lessons can still be derived from production
  frames. Champion/challenger evidence starts when ENG-VIS-GALLERY and ENG-VIS-FLUX adopt the
  contract.
- **Real data is UNKNOWN.** No production observation has been harvested, so every real
  trend is UNKNOWN.
- **Later slices:** a scheduled `learning.cycle` job, the pattern loop, the suspended-job
  fixes, readback and Mission Control, and commerce readings.
