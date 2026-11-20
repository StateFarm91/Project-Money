# ENG-IMPROVE: review request, slice 1 (the automatic self-improvement team)

- Branch: `eng/improve`.
- Base: `origin/claude/w6-INTEG3` @ `39b92619`.
- The final SHA is the commit that adds this file; it is given in the issue #28 comment.
- Not deployed. Not merged.
- Nothing touches Railway, production data, secrets, Etsy, spend, `BRAMBLELOOP_PHASE` or
  `STAGE_A_ENABLED`. Production deploy logs were read once, read-only. They hold HTTP lines
  only, so no job state was read from them.
- `eng/learn` (ENG-LEARN) had not landed on origin when this slice was cut. Nothing here
  duplicates its image or pattern loops. The lesson reads in this slice use the existing bus
  (`core.models.Lesson`, `bus.acted_on`) and `learn_decisions`. When ENG-LEARN's lesson
  interface lands, `department_loops.lessons` / `_fired` switch to it; that is the only seam.

Owner directive (2026-11-20): every department gets better with experience, learning counts
only when it changes behaviour, and a team turns lessons into fixes.

## 1. Map of what existed

- **Lessons.** `improve.bus` / `core.models.Lesson` (`lessons`).
  - `consume.matching` / `consume.act` / `score_adjustment` / `rank_adjustments`.
  - Live consumers:
    - `market_radar`: radar.score and the watchlist;
    - `pattern_engineering`: cir draft;
    - `seo_search`: listing.seo;
    - `customer_experience`: support;
    - `growth`: content;
    - `portfolio`: seasonal.
- **Offline champion/challenger.**
  - `policy_loops`: 5 loops, replay/holdout, bounded params, guarded by `invariants`.
  - `league`: `config_versions`, with promote and rollback.
  - `visual.rnd.loop`: the only real significance test, a two-proportion z.
- **Roles.** `improve.roles`: 8 roles, which write `improvements` proposals.
- **Autonomy.** `autonomy.departments` / `charters` / `kpis`. Every charter's KPIs are the
  same three generic job-level numbers.
- **What was missing:**
  - live (online) champion/challenger with share and spend caps;
  - an allowlist of tunable keys covering prompts, choices and schedules;
  - engineering change requests of any kind;
  - a per-department check that a lesson reached a consumer.

## 2. Diagnosis: parked improve.* loops (improve.monitor)

These job types read rows that other code writes, and none of them reports `work_done`:

| Job type | Reads |
|---|---|
| `improve.monitor` | promotions |
| `improve.sandbox` | proposals |
| `improve.league` | configuration versions |

**Why they are parked**
- With nothing promoted, `improve.monitor` returns identical outputs every night, for example
  `promoted: 0, judged: 0, waiting: 0`.
- So `_free_poll_backoff` parks it at 2x, then 4x, up to 32x a daily period.
- For an idle watcher that backoff is correct.

**The defect**
- Nothing lifted the backoff when the input arrived.
- `UPSTREAM_INPUTS` and `made_progress` see only job outputs, and the monitor's input is a
  row (`improvements.promoted_at`, `capability_history`).
- So a promotion made after the monitor parked waited up to 32 days for the only job that
  can roll it back. That leaves a rollback path that exists on paper only.

**Fix** (`swarm/orchestrate.py` `INPUT_PROBES`)
- Each of the three job types has a probe that reads its real input rows:
  - **monitor:** a promotion, a non-monitor reading of a promoted cell, or a self-tune
    promotion;
  - **sandbox:** a new proposal;
  - **league:** a new configuration version.
- A backoff now lifts on the sweep after new input appears. No backoff was simply removed,
  and spending loops are unchanged.
- Tests: `test_g_*`.

**Limits of the evidence**
- This session could not read the production suspension list: no readback token, and the
  logs hold HTTP only. ENG-RECOVERY's reading says "every listed suspension in production is
  `kind: backoff`".
- The cause above is derived from the code and reproduced in a fixture.
- Any improve.* loop still parked at 32x after this deploys becomes a `failing_loop` ECR,
  filed automatically. That is how a different cause would surface.

## 3. What was built

### Self-improvement modules (`src/brambleloop/improve/`)

| Module | What it does |
|---|---|
| `stats.py` | Two-proportion z-test with a floor of ≥50 units per arm. Promotion is judged only at fixed looks (50·2^k units), with a per-look threshold of z ≥ 2.807 (one-sided α 0.0025, Bonferroni over 6 looks) and a gain of ≥ 3 points. Harm stops at z ≤ −1.96. The trend is UNKNOWN below 20 runs per window. |
| `tuning.py` | Live champion/challenger over a hard-coded allowlist of 13 keys, details below. |
| `ecr.py` | `EngineeringChangeRequest` rows, details below. |
| `department_loops.py` | The department × KPI × lesson-consumer table for 11 departments, details below. |
| `self_improve.py` | The `improve.self_tune` daily job, and the panel (`panel`). |
| `self_models.py` | Four tables, created at boot through `core.db.register_models`. |

**`tuning.py`**
- **The allowlist.** 13 keys covering numbers within bounds and choices: prompt template,
  title template, price-test arm, schedule factors, research focus weights and lesson weights.
- **Guarding.** Every key and value also passes `improve.invariants`. Certified gates, safety
  rules, spend ceilings, evidence floors and owner keys are refused, and an undeclared key is
  refused. The module refuses to import if a protected key is ever added.
- **Share cap.** A challenger gets at most 20% of units, by a stable hash.
- **Spend cap.** At most CA$5 of recorded arm cost. A cap of 0 means no recorded cost at all.
- **Watching.** A promotion is WATCHED against a 20% holdback of the replaced value, and rolls
  back automatically when z ≤ −1.96.
- **Read guard.** A stored champion outside its bounds is never used; the default applies.
- **Audit.** Every state change goes to `history` and to `audit_log`
  (`improve.self_tune`), with its evidence.

**`ecr.py`**
- **Fingerprint.** Each request is identified by (defect_class, department, module).
- **Dedupe.** Filing again into an open request merges the evidence and the count.
- **Related.** Prior or closed requests on the same fingerprint, or the same department and
  module, are listed in `related`.
- **Lifecycle.** FILED → BUILDING → REVIEWED → DEPLOYED (the commit is required) →
  VERIFIED. REVIEWED can return to BUILDING. DEPLOYED → REOPENED → BUILDING.
- **Close.** A request closes only through `verify`, when the KPI after the deploy beats the
  filed baseline. A worse KPI, or no gain after 21 days, REOPENS it with the evidence.
- **Readback.** `readback()` projects counts, ids and generated text only.

**`department_loops.py`**
- **KPI.** Useful yield: DONE runs with `made_progress`, over DONE+DEAD runs. Gated no-ops are
  excluded.
- **Lessons.** Learned, VERIFIED (confidence measured or confirmed, plus an evidence_ref) and
  APPLIED.
- **Consumers.** Checked statically (the call site is still in the module source) and live
  (it acted on a lesson, or wrote `learn_decisions`, in the last 30 days).
- **Verdicts.** No consumer, or no ACTIVE consumer, is a FINDING, never a pass, and the job
  files an ECR for it.

### Other changes

- **Readback.** `GET /api/readback/ecrs` was added to `security.READBACK_ROUTES`. It accepts
  the readback token only (the operator token is refused), GET/HEAD only, and sends
  `Cache-Control: no-store`.
- **Panel.** Mission Control → Autonomy now has a "Self-improvement (per department)" section
  (`tabs.self_improvement_section`). For each department it shows:
  - the KPI and its trend (UNKNOWN below the floor);
  - lessons learned, verified and applied;
  - consumer states;
  - active challengers, promotions and rollbacks;
  - ECRs open, shipped and verified;
  - an `improving` flag, which is YES only on an UP trend or a VERIFIED ECR. A no-op is
    never improvement.
- **Service worker** bumped to `cc-shell-v41`.
- **Registrations** for the new job:
  - `CADENCES` (`self_tune`, orchestrator, daily);
  - `FREE_JOB_TYPES`;
  - `authority.classes` (BUILD);
  - `departments.WORK_CLASS` (IMPROVE);
  - the orchestrator's `allowed_job_types`;
  - `autonomy_map.json`, regenerated through the module.

## 4. Department × KPI × lesson-consumer table

The table is in `research/final_build/w6/self_improvement_table.md`.

**Structural findings**
- **Pricing and Ops have no consumer.** These are FINDINGS with ECRs. They are not passes.
- **QA, Visual and Finance consume through policy loops.** Their thresholds feed `next_work`
  but do not yet gate the release, render or cost paths (W-B3/W-B4).
- **No tunable has a wired reader yet.** The engine is complete and tested, but no live
  challenger can run until a reader calls `tuning.value()`. The panel shows "not wired".

## 5. Tests

- `tests/test_eng_improve.py`: 24 tests.
  - A: a truly better variant is promoted, and 0 of 40 null streams promote under peeking.
    Small samples decide nothing, a worse challenger stops, and a unit is counted once.
  - B: a regression rolls back automatically, and a holding promotion settles.
  - C: non-tunable keys are refused, and a mutation test kills 4 of 4 mutants (allow-all,
    no bounds check, widened bounds, protected key allowlisted). The import-time refusal
    is also tested.
  - D: share and spend caps; the tampered-value read guard; a no-op trial is refused.
  - E: ECR dedupe and related requests; the lifecycle; close only on a verified KPI;
    REOPENED on no gain or a worse KPI; the projection carries no free text.
  - F: the table:
    - a missing consumer is a FINDING with an ECR, deduplicated on refiling;
    - a vanished call site reads MISSING;
    - the KPI is UNKNOWN on a small sample;
    - a no-op is never improvement.
  - G: parked monitor, sandbox and league lift on new input.
  - H: the job is registered and idempotent, and a parked improve.* loop becomes a
    `failing_loop` ECR.
- `tests/test_eng_improve_readback.py`: 5 tests.
  - 503 when no token is set, and 401 for no token, a wrong token or the operator token.
  - 200 with the readback token, with no private text.
  - Every mutating method is refused and the DB is unchanged.
  - The readback token opens no operator route.

Suites run: see the issue #28 comment for the exact list and the pass counts.

## 6. Honest status and slice 2

**Honest status**
- Not deployed. No production row has been read, and no live KPI value is claimed.
- No challenger has run in production, and none can until a reader is wired.
- The ECR lifecycle has no write route. BUILDING, REVIEWED and DEPLOYED are moved by
  `ecr.advance` only; the integrator has no HTTP path for them yet.

**Slice 2**
1. Wire the first live readers through `tuning.value(db, key, unit)`, recording outcomes into
   `si_observations`:
   - `concept.lesson_nudge_step` in radar.score;
   - `listing.title_template` in listing.seo.
2. Add an operator-gated ECR transition route, with `ecr.advance` and deploy detection from
   `release.boot_verdict`.
3. Build Pricing and Ops consumers. Their ECRs close only on a verified KPI.
4. File `recurring_defect` ECRs from `improve.mine` lesson groups above a count threshold.
5. Switch to ENG-LEARN's lesson interface when it lands.
