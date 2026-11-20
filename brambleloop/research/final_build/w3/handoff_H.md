# Wave 3, lane H: Visual permanent self-improving R&D and Visual Learn data

Branch `claude/w3-H` (base `claude/v11-CANON` f0c2d12). Shadow phase. No network, no provider call,
no spend.

## Interface (exported in the first commit, 06ade5b)

- `brambleloop.visual.rnd.status.summary(db) -> dict`. Accepts a `Database` or a bare `Session`
  and never raises. It always returns `status`, `as_of`, `basis`, `items` and `sources`, plus
  `totals`, `loop`, `gates`, `tunables`, `lessons` and `spend`. There is one `items[]` entry per
  product class (8). Each entry has:
  - `pipeline` {version_id, label, generation, params, since}
  - `versions_total`, `promotions_total`, `experiments_by_state`
  - `promoted`, `rejected`, `rolled_back`, `overturned`, `refused` (the technique lists)
  - `structural_rejection_trend` (per version), `photorealism_trend`
  - `laura_identity_consistency`, `accepted_image_yield`
  - `cost_per_accepted_image` (CAD, with its basis), `latency_s_median`, `task_score_mean`
  - `benchmark_gap`, `hero_ctr`, `listing_conversion`, `refund_rate`
  - `paid_challengers_gated`

  Every metric is `{value, reading: MEASURED|UNKNOWN, basis|why}`. UNKNOWN is never 0.
- `brambleloop.visual.rnd.status.next_work(db) -> list`. It returns internal GREEN items only,
  with kinds monitor 75, calibrate 70, judge_production 60, experiment 50 and bootstrap 40. Every
  item has `job_type="visual.rnd.cycle"` and `green=True`. Paid work never appears here.
- `brambleloop.visual.rnd.loop.cycle(db, builds=None, classes=None)` runs one full repeat of the loop.

## Requirements (directive §9–12, 18)

| Requirement | Status |
|---|---|
| Loop GENERATE→…→AFFECT FUTURE GENERATION | COMPLETE for the deterministic path (`loop.py` maps each step) |
| Gates: product truth, structure (`render_verification.verify` on bytes), Laura identity (`canonical.laura_verdict`), anatomy, photorealism (N/A for disclosed renders per D-FB-9), composition and 170 px thumbnail (`layout_qa`), disclosure, gallery contract (hero = DESIRE first), blind benchmark (advisory, UNKNOWN) | COMPLETE. UNKNOWN blocks. |
| Fast loop: yield, failure taxonomy, latency, cost, thumbnail prominence | COMPLETE (measured) |
| Slow loop: impressions/CTR/favourites/carts/purchases/conversion/refunds, which can overturn | COMPLETE as code. GATED on data: no live listings. The comparison is sequential before/after (z ≥ 1.96, with volume floors), not a randomised test, and is labelled that way. |
| Overturn changes future behaviour | COMPLETE: rollback, an `overturned` lesson, and the parameter struck from the class's internal search for 180 days |
| Product-class strategies (8 classes) | COMPLETE: each class has its own lineage and search space. Only 3 classes have free producers. |
| Pipeline versioning and traceability | COMPLETE: every judgement row carries `pipeline_id` and the label `class/gN-digest` |
| Whole-pipeline challengers | PARTIAL: renderer layout, post-processing and encode run locally; provider/model, lighting, camera, composition, crop, control and Laura reproduction are planned as GATED_SPEND with an estimated cost |
| Never weaken gates | COMPLETE: `improve.invariants` plus `VISUAL_PROTECTED`. Gates are code (`pipeline.GATES`), not params. |
| Laura is a hard independent gate | COMPLETE: computed from per-dimension readings, so a caller-supplied PASS is overridden. Reproduction choices are all `frozen_v15*`. |
| Paid execution gated | COMPLETE (closed): `paid_execution_gate()` always denies; there is no executor |
| 3-month evolution visible in CC | COMPLETE as data (generation, promotions, trends) |

## Measured findings (real runs, hexagon coasters, deterministic)

- Baseline hero thumbnail score: 0.6256, yield 1.0.
- **Promoted** `hero_gap_ratio` 0.18→0.06: score 0.7238 (+0.098), all gates PASS.
- **Rejected:**
  - Gap 0.0: the pieces merge and the verifier's `object_count` FAILs.
  - Gaps 0.12 and 0.24: worse scores.
  - Grain σ=3: `contract_palette` FAIL.
  - Grain σ=1.5: passed the verifier but made the images 57× larger (15.6 MB) for no gain.
- Blanket hero vs detail at 170 px: 0.276 vs 0.544 ink share. The detail view would win on
  thumbnail prominence, but frame one must be DESIRE, so it is not a tunable. This is recorded
  here for Creative.

## Files

- New: `src/brambleloop/visual/rnd/{__init__,models,pipeline,gates,loop,status}.py`.
- Modified: `visual/disclosed_render.py`. It gains an opt-in `layout={"hero_gap_ratio"}` parameter
  that is bounded and refuses unknown keys. Omitted, the output is byte-identical (verified by sha).
  `layout_params` is added to the manifest only when the parameter is given.

## Tests

- `tests/test_w3_visual_rnd_loop.py`: 8/8 OK.
- `tests/test_w3_visual_rnd_guard.py`: 6/6 OK.
- Existing re-run, all passing (OK lines = test count): test_disclosed_render 27/27, test_disclosed_render_runtime 3/3, test_canon_manifest 21/21, test_final_visual_authority 10/10, test_fb4_lc 16/16, test_vacuity 7/7, test_secret_scan 6/6.

## WIRING REQUESTS

1. **Lane D**, `core/db.py create_all`: add
   `from ..visual.rnd import models as visual_rnd_models  # noqa: F401; Visual R&D (H, w3)`.
   The tables are also created lazily, so this is not blocking.
2. **Lane D**, `runtime/worker.py` CADENCES / registry: add a job handler `visual.rnd.cycle` that
   calls `brambleloop.visual.rnd.loop.cycle(db)`. Suggested cadence is every 6 h. A first full
   cycle takes roughly 2–3 min of CPU: 5 Launch-0 builds, cached per process.
3. **Lane F**: render `visual.rnd.status.summary(db)` as Visual Learn. Show the `reading`/`why`
   for UNKNOWN; never show 0.

## Open defects / could NOT verify

- No marketplace data, so the slow loop has only been exercised by tests.
- Photorealism, anatomy and benchmark readings need `image_vision` and paid generation (owner
  gated). The Laura-on-model, garments, accessories and seasonal classes have no judged
  production image.
- Latency is wall-clock on a shared machine. It blocks only beyond a 5 s per-task noise floor.
- The census margin (flat `QUALITY_MARGIN` when the task set is the whole class catalogue)
  promoted on a single coaster product. Future coaster products are covered only by MONITOR.
