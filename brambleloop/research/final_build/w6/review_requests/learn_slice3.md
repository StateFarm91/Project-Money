# ENG-LEARN slices 3 and 4: the suspended learners, proof of improvement, real sales (`eng/learn`)

**Status:** builder branch. NOT reviewed, NOT integrated, NOT deployed.

## Why the five jobs were suspended (diagnosed from the code)
All five were parked by the **backoff** half of the thrash breaker (`swarm.orchestrate._progress`
/ `_free_poll_backoff`): three identical output states in a row lead to backoff, up to 32x.
The failure/spend breaker was not involved.
- Four of them (`creative.*`, `visual.*`) can never get the per-release re-arm probe, because
  `SPENDING_PREFIXES` overrides the allow-list.
- None had an `UPSTREAM_INPUTS` entry. So when the evidence they exist to read changed, nothing
  lifted the backoff. The only exit was the deadline, after which the next unchanged run
  parked them again.

| Job | Why parked | Fix (none is a plain unsuspend) |
|---|---|---|
| `creative.image_benchmark` | Superseded by the FLUX 3 ruling; returned the same record hourly | Its superseded branch now runs the image learning loop (`image_lessons.cycle`): harvest, lessons, challengers, evaluation. DB only. Its state changes when judged frames arrive. Upstream: `visual.image_production`, `visual.controlled_experiment` |
| `creative.outcome_learning` | UNMEASURED daily (no real outcomes) | Upstream: `listing.outcomes`, `commerce.orders_ingest`, `commerce.readings`. New real outcomes lift it |
| `creative.reference_reading` | Vision gate closed, or every judged listing already read: identical state | Upstream: `intel.gallery_analysis`, `intel.benchmark_refresh`. Newly judged gallery images lift it. It stays paid (vision) and spending-classified |
| `visual.rnd.cycle` | Hero merchandising R&D (evaluated, promoted, calibration overturned) was invisible to `work_done` and the state | Counted in `work_done`. Upstream: `gate.certify`, `chain.rebuild` (a new catalogue fingerprint) |
| `improve.monitor` | `promoted` (a standing count) was a WORK_KEY, and there was no lift on a new reading | `promoted` dropped from WORK_KEYS; `trial_monitoring.judged` added. Upstream: `improve.measure`, `improve.sandbox` |

**Upstream progress is judged by declared work.** `made_progress(outputs, job_type)` judges a
type that declares WORK_KEYS with the same judge as every no-op report (`did_no_work`). So
`{"ran": true, "measured": 0}` does not lift anything. Undeclared types keep the old reading.

**Spend.** No spend classification changed. The four prefixed jobs are still spending and
still get no release probe.

## New free job: `learning.loops`
- Runs daily: the pattern loop (harvest and lessons), then commerce.
- Registered on the `improve.commercial_lessons` pattern, owned by the analyst agent (GREEN,
  CA$0). It is listed in `FREE_JOB_TYPES`, allocated as exploration, and placed in the Learn
  charter.
- Upstream: `cir.compile`, `gate.certify`, `cir.draft`, `listing.outcomes`,
  `commerce.orders_ingest`.
- `autonomy_map.json` is regenerated with `python -m brambleloop.autonomy.map --write`.

## Proof of improvement (`learning/progress.py`)
`summary()` is shown in Mission Control (AUTONOMY / LEARN tab, `learning` section). It shows,
per loop:
- the metric over six 14-day windows;
- the trend between the earliest and latest measured window;
- active and inactive lessons;
- lessons acted on (bus `acted_on`), never lessons merely published;
- before/after per promotion or demotion, from the decision's own evidence.

It also feeds the readback. `/api/readback/evidence` gains a `learning` section holding
`progress.readback()`: rates, counts and statuses only.

The rules:
- A window under 10 observations is UNKNOWN.
- A trend needs two measured windows, and "improving" needs p < 0.05.
- Retries never count as first-pass frames.

The service worker is bumped to `cc-shell-v40` for the `learn.js` change.

## Slice 4: real sales (`learning/commerce_lessons.py`)
- Real `ListingOutcome` and `Order` rows (`evidence_provenance.learnable`) are joined to each
  listing's image arm (the prompt_version of most of its accepted frames) and its pattern
  family.
- Conversion lessons need 200+ visits per side, 5+ orders and p < 0.01. They are published as
  `commercial_demand` / `commercial_underperformance`, under the existing separate buyer cap.
- With no real rows the result is UNMEASURED and nothing is written. Fixtures and synthetic
  rows are never learned from. No sales are created.

## Tests: `tests/test_eng_learn_wiring.py` (9/9)
- Every suspended learner has an upstream input that is a registered job.
- A bare `ran` does not count as progress, and real work lifts a parked learner end to end
  (`suspended_job_types`).
- `learning.loops` is free and registered, and `improve.monitor` no longer counts a standing
  `promoted` as work.
- Hero work is counted in `visual.rnd.cycle`.
- An empty company reads UNKNOWN in summary, readback and `/api/readback/evidence`.
- A real 40% → 85% image first-pass rise reads "improving", and retries do not move it.
- Commerce ignores synthetic rows, and learns from real rows into Market Radar's inbox.

## Honest status
- No production observation exists yet. Every real metric is UNKNOWN until this is deployed
  and the loops have read production rows.
- No consumer (ENG-VIS-GALLERY / ENG-VIS-FLUX) calls `prompt_for` yet, so no arm has
  production evidence. Promotions happen only after they adopt the contract.
- **`creative.reference_reading` still needs the owner's vision activation to do paid work.**
  The upstream lift only makes sure it runs again once newly judged images exist.
