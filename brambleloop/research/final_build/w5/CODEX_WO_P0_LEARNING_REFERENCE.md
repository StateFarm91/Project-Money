# Codex work order: P0-LEARNING-REFERENCE

| Field | Value |
|---|---|
| Issued by | Main Opus, lead integrator |
| Date | 2026-10-31 |
| Claim | `P0-LEARNING-REFERENCE` in `COORDINATION.json`, reserved for Codex |
| Branch | `codex/p0-learning-reference`, created from `origin/claude/w4-INTEG8-next` |
| Background | `brambleloop/research/final_build/w5/LEARNING_MAP.md`. Read it first. |

## 0. Ground rules (not negotiable)

- **Work only on `codex/p0-learning-reference`.** Never push to `claude/*`, `opus2/*` or `claude/repository-setup-nc9x6o`. Never merge, deploy, publish to Etsy, touch Railway, buy anything, or call paid providers (Anthropic, image or vision APIs).
- **Claim the work before you write code.** Commit one change to `COORDINATION.json` on your branch: set the `P0-LEARNING-REFERENCE` claim's `operator` to `codex` and `state` to `in_progress`. The integrator reconciles it on `INTEG8-next`.
- **Extend; do not duplicate.** The internal learning system is `improve/` plus `teardown/`. Do not create a second lesson store, a second learning department, or a parallel intake. `learn/` is customer tutorials, so do not touch it.
- **Deterministic validation wins.** Nothing you build may relax a gate, the originality checks, Product Truth, licence checks or the CA$100 spend ceiling. UNKNOWN never counts as PASS. Never weaken an existing test.
- **No protected content leaves the library.** Analysis stores only closed vocabulary and numbers. Reuse `teardown/library.check_derived` on every free-text field. Never commit purchased PDFs; `benchmark_library/` is gitignored.
- **Do not edit files owned by others.** Leave these alone:
  - `publish/pdf.py` (W-PDF).
  - `quality/physical.py` and `physical_upgrade` (W-PHYSFIX).
  - `radar/intake.py` and the concept path (W-CONCEPT).
  - `improve/commercial_lessons.py` (opus2).
  - `products/production_inventory.py` (W-INVENTORY).

  If you need a hook in one of them, write the one-line hook into your handoff instead.
- **Never store secrets.** All dates are UTC, ISO 8601.

## 1. WO-1: teardown analyst job and independent review of findings

**Problem.** `teardown/intake.receive` stores an upload, but no job ever analyses it: `teardown_state` stays `queued`. `teardown/reader.analysis()` is never persisted, and no findings are reviewed.

**Build:**
1. Create `runtime/teardown_ops.py` with handler `teardown.analyse(job)`. Register it in the runtime handler registry, the same way existing handlers in `runtime/*_ops.py` are registered. Add a daily cadence `teardown_analyse_sweep` in `runtime/worker.py` CADENCES, and regenerate `autonomy/autonomy_map.json` with `cd brambleloop && PYTHONPATH=src python -m brambleloop.autonomy.map`; `test_v11_autonomy_timeline` enforces this.
2. Make `teardown/intake.receive` enqueue `teardown.analyse` with an idempotency key `teardown:<benchmark_id>:<file_sha256>`. The sweep enqueues any `BenchmarkProduct` whose `teardown_state == "queued"`.
3. The handler runs `reader.read`, then `analysis`, `architecture_answers`, `construction_correspondence` and `size_family.all_size_parse` / `schematic_cross_check`.
   - Persist to a new `BenchmarkAnalysis` table (add it to `core/models.py` and `core/db.create_all`). Store only closed vocabulary, numbers, element-presence booleans and file hashes.
   - Prefill audit presence through `teardown/lab.record_audit`.
   - Set `teardown_state` to `analysed`, or to `needs_analyst` when confidence is below `enforce.MIN_BINDING_CONFIDENCE`.
4. Independent review of findings. Add `review_state` to `TeardownFinding` with values `proposed`, `reviewed` and `rejected`, plus `reviewed_by` and `reviewed_at`.
   - The reviewer must be a different role or actor from the one that recorded the finding. Refuse self-review.
   - `teardown/enforce.requirements` binds only `reviewed` findings. `proposed` findings stay provisional.
   - Add an owner-session Command Center action `teardown.review_finding` on the existing step-up path in `app/command_center/approvals.py`: a reason is required, the action is audited, and it never writes outside the teardown tables.
5. Retention: every new audit action you read gets an entry in `ops/retention.py` `KNOWN_READ_ACTIONS`. `test_w4_fmbatch1_retention_guard` fails otherwise.
6. Hardening:
   - Add a `brambleloop/.dockerignore` that excludes `benchmark_library/`.
   - Make `teardown/library.library_root()` refuse any root that resolves inside the repository or the image's source tree.

**Acceptance tests,** in the new file `tests/test_codex_teardown_analyse.py`:
- An upload of the existing proof-run fixture leads to an enqueued job, a persisted analysis and `teardown_state == "analysed"`.
- Uploading the same file twice gives one job.
- Every free-text field passes `check_derived`. A planted sentence copied from the fixture is refused.
- A finding recorded and reviewed by the same actor is refused. Unreviewed findings never bind in `enforce.requirements`.
- A low-confidence result goes to `needs_analyst` and binds nothing.
- `library_root()` inside the repository is refused.
- The new Command Center action needs the owner session plus step-up, and is refused with only the ops token.

## 2. WO-2: a versioned, approved design-knowledge store read by pattern development

**Problem.** Lessons have provenance but no version and no approval. Neither the CIR drafting/revision logic nor `cir/writer.py` reads any learned knowledge, so learning does not change the patterns produced.

**Build:**
1. Create `improve/design_knowledge.py` and a `DesignRule` table with these columns:
   - `key`
   - `version` (int)
   - `statement` (closed-vocabulary rule id plus parameters, not prose copied from any source)
   - `scope` (construction family / category / writer section)
   - `state` (`proposed`, `approved` or `retired`)
   - `provenance` (JSON list of lesson ids, teardown finding ids and incident ids)
   - `approved_by` and `approved_at`
   - `supersedes`

   Approval must come from a different actor than the producer. An approval that cites no WO-3 evaluation is refused.
2. **Producers.** Each producer *proposes* rules and never approves them:
   - mined `defect` lessons;
   - `teardown/enforce.requirements`, using reviewed findings only;
   - `improve/readings_bus` customer lessons.

   Extend `improve/mine.py` so that compile failures (`cir.compiled` with `ok: False`) and UNREPAIRABLE revisions from `runtime/engineering_ops.py` are mined. Wire the orphaned `support/community.py` and `support/lesson_trigger.py` into the existing `improve.mine` run.
3. **Readers.** These are the point of this work order:
   - the `cir.draft` / `cir.revise` content logic in `runtime/engineering_ops.py`;
   - `cir/writer.py`.

   Each reads only `approved` rules, through a single function `design_knowledge.applicable(scope)`, and records every read with `improve/consume.act`. If the store cannot be read, behaviour stays exactly as it is today (no rule applied) and the failure is recorded. It must never apply an unapproved rule.
4. List `publish/pdf.py` and `visual/*` as planned readers in your handoff, as the hooks the integrator will add. Do not edit them.

**Acceptance tests,** in the new file `tests/test_codex_design_knowledge.py`:
- A proposed rule never affects drafting.
- An approved rule demonstrably changes the writer's output for a fixture CIR. Assert on the output, not just that the function was called.
- Self-approval is refused.
- Approval without a passing WO-3 evaluation is refused.
- When the store crashes, the output is byte-identical to the no-rule baseline.
- A compile failure becomes a mined `defect` lesson.
- The orphaned support producers now emit lessons.
- The existing suites `test_cir*`, `test_writer*`, `test_compiler`, `test_twin`, `test_reverse` and `test_k9_*` pass unchanged.

## 3. WO-3: held-out evaluation of design quality before and after a change

**Problem.** Nothing proves that a knowledge change improves designs. The owner requires measurable before-and-after evidence, and "saving information is not learning".

**Build:**
1. Create `quality/design_eval.py`. Build a fixed held-out set, frozen and hashed, from:
   - the Launch-0 CIRs and briefs;
   - the bench1/bench2 Product Truth in `quality/benchmark_e2e.py`;
   - `quality/stitch_benchmarks.FAMILIES`.

   A challenger rule may not bring its own cases; follow the rule in `improve/league.py`.
2. Use deterministic metrics only:
   - compile, twin and reverse pass rate;
   - writer section coverage and clarity self-audit, in the style of `teardown/reader.self_test`;
   - originality findings, which must not increase;
   - Product Truth contradictions, which must be zero.

   Compare the incumbent knowledge version with the candidate. Record the result as a `design_eval.completed` audit row containing both scores, the case-set hash, and the rule key and version.
3. A `DesignRule` may move to `approved` only with a recorded evaluation that shows no regression on any metric and an improvement on at least one. Add a daily cadence `design_eval`. This also wires the two benchmark modules that currently have no callers.
4. Never fabricate an improvement. If there are too few cases, the result is `insufficient_evidence` and blocks approval.

**Acceptance tests,** in the new file `tests/test_codex_design_eval.py`:
- A rule that worsens a metric cannot be approved.
- A rule with no improvement cannot be approved.
- A case set the challenger supplied is refused.
- The case-set hash is stable.
- The evaluation is deterministic: the same inputs give the same score.
- `insufficient_evidence` blocks approval.

## 4. How to run

Requirements: Python 3.11, `pip install -r brambleloop/requirements.txt`, and SQLite only. No network, no paid APIs.

```
cd brambleloop
PYTHONPATH=src:tests python tests/test_codex_teardown_analyse.py
PYTHONPATH=src:tests python tests/test_codex_design_knowledge.py
PYTHONPATH=src:tests python tests/test_codex_design_eval.py
# Required regression set. Every one must pass:
for t in test_vacuity test_shadow test_route_auth_default_deny test_w4_fmbatch1_route_audit \
         test_w4_fmbatch1_retention_guard test_w4_fmbatch1_contracts test_v11_autonomy_timeline \
         test_gates test_compiler test_twin test_reverse test_originality test_teardown_reader \
         test_cert_culture_teardown test_cost_governance_wave2; do
  [ -f tests/$t.py ] && PYTHONPATH=src:tests python tests/$t.py || echo "MISSING $t"
done
```

Run the suites one at a time. Do not run the full `run_tests.sh`; the integrator runs the certification suite.

If you add or change a route, add a row to `ops/CONTRACT_CHANGES.md` and update the route pin the way existing rows describe.

## 5. Handoff (definition of done)

1. Push `codex/p0-learning-reference` with clear commits, one per work order. Do not squash other people's history.
2. Write `brambleloop/research/final_build/w5/CODEX_P0_LEARNING_HANDOFF.md`. It must contain:
   - the head SHA;
   - files changed per work order;
   - test results, with pass and fail counts per suite;
   - each acceptance criterion and the test that proves it;
   - the integrator hooks needed in files you did not own (`publish/pdf.py`, `visual/*`, `radar/intake.py`);
   - anything you could not do, and why.
3. Update your claim in `COORDINATION.json` on your branch to `state: "handoff"`.
4. Open a PR from `codex/p0-learning-reference` into `claude/w4-INTEG8-next`, titled `CODEX P0-LEARNING-REFERENCE`, with the handoff as its body. **Do not merge it.**

The integrator then runs an independent review. The possible verdicts are ACCEPT, CHANGES_REQUIRED, BLOCKED and REJECTED. Accepted work is integrated into Batch 5 and certified.
