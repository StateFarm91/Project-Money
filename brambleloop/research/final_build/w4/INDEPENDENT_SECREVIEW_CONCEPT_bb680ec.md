# Independent security & integrity review — W5-CONCEPT delta 933bf742..bb680ec5

- **Subject:** `claude/w5-CONCEPT` @ `bb680ec5`, diffed against `933bf742` (10 files, +567/−47).
- **Prior review:** `INDEPENDENT_SECREVIEW_CONCEPT_933bf74.md` (findings F1–F7).
- **Reviewer:** an independent reviewer that did not write the change. It judged the code, not `CONCEPT_INTAKE.md`.
- **Date:** 2026-10-31 (UTC)
- **Method:**
  - I read the diff.
  - I reproduced findings with scratch scripts that import the subject's own test helpers. They are inlined below.
  - I ran 30 single-point mutants in a separate worktree (`/tmp/mut`), restoring the file after each one. The worktree was clean afterwards.
  - I ran the requested suites one at a time with `nice -n 19`.
  - The container had no `sqlalchemy`, so I installed `requirements.lock` and `requirements-test.lock` with `--require-hashes`.

## Verdict: **DO NOT SHIP**

All six prior findings are fixed at the root (table below), and all 12 mutants that survived last time are now killed. One defect remains, and it fails brief item 4 directly:

- **G1 (HIGH):** a `cir.draft` job that was already queued for a concept that is then **withdrawn** still drafts the CIR and enqueues `cir.compile`. It runs with **no pre-engineering gate at all**.

The fix is small. Until it lands, a withdrawal does not stop work that is already in flight.

## Test runs (one at a time, `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

| suite | result |
|---|---|
| test_w5_concept_intake | pass, 0 failures (39 s) |
| test_w4_intelrec_watchlist | pass (18 s) |
| test_radar | pass (2 s) |
| test_shadow | still running at commit time; result appended below when done |
| test_w4_fmbatch1_retention_guard | pass (30 s) |
| test_cost_governance_wave2 | pass (21 s) |
| test_vacuity | pass (9 s) |
| test_v11_autonomy_timeline | pass, 0 failing (82 s) |
| test_cert_wiring | pass, 16/16 (797 s) |

## Prior findings: status

| prior | status | evidence |
|---|---|---|
| F1 HIGH: stale approval never withdrawn; rows churn | **Fixed, with one gap (G1)** | Three changes. (1) `withdraw_unsupported` runs at the start of every `run` and re-checks every APPROVED row against its source. (2) `approved_rows` excludes research rows whose task is no longer ANSWERED, is unresolved or is expired (`_unsupported_research`, read at the moment of use). (3) The fingerprint now carries `answered` instead of the quality score, which changes from day to day, so decay no longer creates a new row each day. A refused revision withdraws the earlier approval. N1–N6 are killed. Retention was added for the table. |
| F2 MEDIUM: taste fields taken from the job in `radar.score` | **Fixed** | `c = intake.gate_inputs(db, slug, c)` now drops the job's own concept, brief, taste, strength, `key`, `make_lane` and `provenance` fields. `cir.draft` applies the same filter when `seed.origin` is set. M19 and N12 are killed. |
| F3 MEDIUM: judged strength fields ride in on a proposal | **Fixed** | `_JUDGED_BRIEF_FIELDS` is stripped in `_clean` (N11 killed) and again in `gate_inputs` (N18 survives; see G3). |
| F4 MEDIUM: surviving mutants | **Fixed** | M3, M4, M5, M10, M12, M13, M14, M15, M19, M22, M23 and W1 are all killed now. W1 is killed because `summary(now=...)` is now passed through. |
| F5 LOW: prefix match in `release._seed_for` | **Fixed** | Release now matches exactly. Intake also refuses a slug that a POOL slug prefixes (`<pool>-…`). N13 and N14 are killed. |
| F6 LOW: callers not given `db` | **Fixed** | `db` is now passed in storefront, readiness, `product_seed`, pricing peers, `_collection_siblings` (which now uses `pool_with_intake`), member collections, `collection.assemble` and the teardown in certify. N15 and N16 are killed. |

## Findings

### G1 — HIGH — a withdrawn concept's queued `cir.draft` is drafted with no gate
`handle_cir_draft` resolves `seed = _seed_for(slug, ctx.db)`. For a withdrawn concept this is `None`, because `approved_concept` only returns APPROVED rows. The gate only runs when `seed is not None or isinstance(inputs["concept"], dict)`. The `radar.score` → `cir.draft` payload spreads the concept fields at the top level and has no `"concept"` dict. So for a withdrawn slug:

1. the gate is skipped;
2. `creative` is false, and `_engineered_cir` returns `None`;
3. the `concept_to_cir` fallback drafts the CIR from the queued job's geometry and enqueues `cir.compile`.

The withdrawal is real (row `withdrawn`, audited), but it does not reach work already in the queue. It also bypasses the very gate (and the vision-judge record) that let the job be queued.

**Reproduction** (`cd brambleloop && PYTHONPATH=src:tests python r1.py nojudge`, where `r1.py` is):
```python
import sys
from test_w5_concept_intake import *
from test_w5_concept_intake import _db,_benchmarks,_answered_task,_proposal,_run,_jobs,_fixture_judgement,_set_task,_actions,_rows
db=_db(); _benchmarks(db); tid,_=_answered_task(db); intake.attach_proposal(db,tid,_proposal())
_run(db,"radar.concept_intake",{})
restore=_fixture_judgement()
_run(db,"radar.concept_intake",{"as_of":(TODAY+timedelta(days=2)).isoformat()},key="j")
print("promoted",_run(db,"radar.score",None)["promoted"])        # queues cir.draft
if sys.argv[1]=="nojudge": restore()                             # judgement gone too
_set_task(db,tid,expires_on=datetime.now(timezone.utc)-timedelta(minutes=1))
out=_run(db,"radar.concept_intake",{},key="w")
print("withdrawn",out["withdrawn"], [r.state for r in _rows(db)])
print("cir.draft ->",_run(db,"cir.draft",None))
print("compile jobs",[j.inputs["cir"]["slug"] for j in _jobs(db,"cir.compile")])
```
Observed:
- `withdrawn [...expired on 2026-10-31 (F-433)...] ['withdrawn']`
- then `cir.draft -> {'artifact': 'tide-line-table-runner@1.0.0', 'drafted': True, 'rows': 16}`
- then `compile jobs ['tide-line-table-runner']`
- The only audit is `cir.drafted`, from the "concept_to_cir fallback". The result is the same with or without the judgement on record.

**Live exposure:** an intake `cir.draft` is only queued once the gate has passed, which needs a recorded vision judgement. `image_vision` is CLOSED today, so this cannot happen in production yet. It becomes reachable as soon as a judgement is recorded and the evidence then expires, goes unresolved or is revised before the draft job runs.

**Fix:**
- In `handle_cir_draft`, refuse and audit (`cir.draft_refused`, gate `radar.intake`) when `seed is None` and either:
  - the inputs carry `provenance` starting `radar.intake:`, or
  - any `RadarConcept` row exists for the slug.
- Add a test for a withdrawal that happens between `radar.score` and `cir.draft`.

### G2 — LOW — prune can delete a row whose fingerprint prevents re-evaluation
`prune` keeps only the newest row per `(source_ref, slug)`. An older row can still hold the fingerprint of the *current* proposal. Example: proposal A is approved, revision B is refused (A withdrawn), then the proposal reverts to A. The revert is "unchanged" and stays withdrawn, because the withdrawn A row holds its fingerprint. After 90 days that row is pruned, and the next pass re-evaluates A and approves it.

The result is not unsafe: A passes every check against current evidence. But it contradicts both the brief and `prune`'s own docstring ("its fingerprint is what keeps an unchanged … proposal from being re-evaluated").

**Reproduction** (`r2.py`, same imports): attach A, run; attach B, run; attach A, run (output `unchanged 1 ['withdrawn','refused']`). Then `retention.apply(db, now=now+200d)` removes 1 row, leaving `['refused']`. The next run prints `approved ['tide-line-table-runner']`.

**Fix:** also keep any row whose fingerprint equals the one the current candidate for that `(source_ref, slug)` would produce. Or decide that re-evaluation after the retention horizon is intended, and say so in the docstring and in `CONCEPT_INTAKE.md`.

### G3 — MEDIUM — new code with surviving mutants
| mutant | suites run | why it survives |
|---|---|---|
| N8: `prune` may delete APPROVED rows | intake + retention_guard | The only approved fixture row is also the newest for its slug, so the newest-row rule protects it anyway. The state filter is the only guard for an approved row that is not the newest, for example after an evaluation crashed after inserting a PROPOSED row. |
| N9: `prune` ignores the 90-day age | intake + retention_guard | Every fixture row is old. No young refused row is asserted to survive. |
| N10: `ops.retention.apply` does not call `intake.prune` | intake + retention_guard | The test checks `retention.plan` (dry-run) and calls `intake.prune` directly. The real `apply` path is never asserted. |
| N17: withdrawal when a family loses proven demand (`amplification`) | intake | No family-withdrawal test. |
| N18: `gate_inputs` stops stripping judged brief fields from the stored row | intake | It overlaps with `_clean`. It still matters for rows approved under 933bf74, before `_clean` stripped those fields: those rows can still hold `strength_score` in the database. |

**Fix:** add one targeted test for each.

### G4 — INFO
- **Retention never refuses to run.** At bb680ec5, `ops.retention.unknown_read_actions()` returns `[]`. `concept.intake_withdrawn` is written but never read by name in `src/`, so it adds no unclassified action, and `apply` does not raise `RetentionRefused`.
- **Withdrawal is audited** (`concept.intake_withdrawn`, with row, source_ref, reasons and as_of), both in `withdraw_unsupported` and in the refused-revision path. N6 is killed.
- **Queued `radar.score` jobs are safe.** For a withdrawn concept they return `radar.unknown_concept` / "not in the pool", and `rescore_judged` iterates `approved_rows`. Only `cir.draft` leaks (G1).
- **The use-time check covers only part of the evidence.** `_unsupported_research` checks state, unresolved status and expiry, but not freshness decay below the 0.40 floor. Decay is withdrawn on the next `run`, which runs every 6 h (`CADENCES`). A decayed concept can therefore stay in the pool for up to 6 h.
- **Withdrawn family variations can be proposed again.** `_decided_slugs` leaves out WITHDRAWN, so a withdrawn family variation becomes a candidate again. It is only re-evaluated when its evidence fingerprint changes, which is acceptable.
- **A malformed source reference fails closed.** A malformed `source_ref` (no `:<int>`) makes `approved_rows` raise. Only intake writes these rows, so this cannot happen today.
- **M3 is killed by a crash, not by its assertion.** It is killed (the handler raises a `TypeError` downstream rather than failing the targeted assertion). It is still detected.

## Answers to the brief

1. **Root fixes:** F1–F6 are all fixed at the root (table above). F1 has a residual gap for queued drafts (G1).
2. **Mutants:** all 12 prior survivors are killed. Of 18 mutants of the new fixes, 13 are killed. N8, N9, N10, N17 and N18 survive (G3).
3. **Retention:** `prune` is wired into both `ops.retention.plan` and `apply`.
   - Approved rows are never pruned in code. The state filter excludes them, and the newest row per `(source_ref, slug)` is also kept.
   - However, a non-newest row that holds the current proposal's fingerprint can be pruned (G2).
   - Retention does not refuse to run, because there are no unclassified read actions.
4. **Withdrawal:** it is audited, and it reaches the pool, the queued `radar.score` jobs and `rescore_judged`. It does **not** reach a `cir.draft` that is already queued (G1, HIGH).
5. **No new fail-open path, no gate relaxed:** no gate was relaxed. `gate_inputs` is stricter, and the evidence time check now uses the actual time of day, so an expiry earlier today counts. The one fail-open path is the pre-existing "raw geometry" fallback in `cir.draft`, which a withdrawn concept now falls into (G1).
6. **Alias:** `nordic-forest-mosaic-throw-baby` resolves through `launch0.SIZE_OF_RADAR_CONCEPT`, an exact map, to `nordic-forest-mosaic-throw` (`mosaic_blanket`, CAD 12.50). `release._seed_for` and `pipeline.product_seed` agree. I scanned every hyphenated string literal in `src/`, and this is the only slug that relied on the old prefix match. It is handled correctly.

## Required before SHIP
1. G1: block `cir.draft` for a slug that has a `RadarConcept` row (or `radar.intake:` provenance) but no current approval. Add a test.
2. G3: add tests that kill N8, N9, N10, N17 and N18.
3. G2: fix the prune rule, or document the intended behaviour.
