# Independent security review: CODEX2 (P0-LEARNING-REFERENCE, delta)

- Subject: `origin/codex/p0-learning-reference`, delta after the last reviewed SHA 623fc26c.
- **Exact SHA reviewed and verdicted: 6f0fe7aa058dc315f5cf3fa0be10d695df0bb0b3.**
  - The original target was 26533977 (commits bd215b08, f4feaaa0, d0e80fe3, fe392b0c, 40292ecd, dbd1e14f, 26533977; confirmed with `git log`).
  - At the integrator's request, the review was extended to 2f55f22b and 6f0fe7aa.
- Newer head not reviewed: after a container restart the branch had moved to 25c7e802, which adds 8 more commits (7436b3aa..25c7e802). None of this report covers them, except one spot-check noted under CODEX2-2.
- Reviewer: independent, adversarial, read-only. 2026-11-02 (UTC). No push, no commit to shared branches, no deploy, no Railway, no vendor network.
- Prior report: `origin/claude/w5-SECREVIEW-CODEX1:brambleloop/research/final_build/w4/INDEPENDENT_SECREVIEW_CODEX1.md`.

## Verdict for 6f0fe7aa: DO NOT SHIP (not even as a partial integration)

CODEX1-1, CODEX1-2, CODEX1-3, CODEX1-6 and CODEX1-9 are fixed and verified. Two new blockers remain:

1. **CODEX2-1 (HIGH): a publish-gate regression with no exit, measured against the rollback target 0967c3ee.** A legacy teardown finding has no `recorded_by`, which is every finding in a deployed database after the additive migration. Such a finding now produces a permanent "requires independent review" release hold, even when our product **meets** the requirement. Review of such a row is refused ("recorder is unknown"), and no other path clears it. At 0967c3ee the same data does not block.
2. **CODEX2-2 (HIGH): an existing suite regresses.** `test_w4_fmbatch1_retention_guard` fails at 6f0fe7aa (`unresolved:improve/design_knowledge.py::_lesson_roots`). It passes at 26533977 and at 0967c3ee. The cause is that the new lesson verifier reads `audit_log` by a computed action name. Retention could prune the very `cir.compiled` rows it relies on, so the guard correctly fails closed. The gap is still present at 25c7e802 (spot-check).

On IP isolation the branch is clean. Nothing reads `DesignRule`, `BenchmarkAnalysis`, `design_eval` or `purchase_provenance` on any CIR, PDF, listing or image-prompt path. The schema changes are additive and safe to roll back to 0967c3ee (see the DB section).

## Prior-finding status

| ID | Prior sev | Status at 6f0fe7aa | Evidence |
|---|---|---|---|
| CODEX1-1 | HIGH | **FIXED** | `DEFAULT_LIBRARY = /var/lib/brambleloop/benchmark_library`, outside the app tree. From cwd `brambleloop/` with the env unset, `refuse_benchmark_references(['/tmp/x.png'])` passes. An unsafe root becomes the named `ReferenceRefused`/`ImagesRefused`, never an uncaught `LibraryRefused`. Intake maps `LibraryRefused` to 503 and `ValueError` to 400. `test_image_reference_hash_failclosed` (4/4) and `test_originality` pass. Ops caveat (UNKNOWN): production needs `/var/lib/brambleloop` writable and persistent, but Railway volume config was not inspected. A library at the old `/app/benchmark_library` would be orphaned; it was ephemeral anyway. |
| CODEX1-2 | HIGH | **FIXED** | `teardown.analyse` and `teardown.analyse_sweep` are in `JOB_CLASS` as `_B`. `test_w3_k11_authority` passes. |
| CODEX1-3 | MED | **FIXED at 6f0fe7aa** (only partial at 26533977) | At 26533977 the forward path was narrowed, because enforce lessons now come only from reviewed, binding findings. `propose(kind=lesson)` still accepted any lesson, including legacy teardown lessons. At 6f0fe7aa, `_lesson_roots` requires `source_findings`; the evidence_ref roots digest must match; each root must pass `_finding_source` (independently reviewed, confidence in [0.5,1], purchase manifest present, private_analysis licence). Legacy NULL-provenance lessons, rootless teardown publishes, forged lessons on unreviewed roots, and unverifiable defect lessons are all refused (probe P4). |
| CODEX1-4 | MED (scope) | IN PROGRESS | Review actions, `propose_from_analysis`, frozen eval cases and written-output measurement now exist. There is still no approve/activate path and no `DesignRule` consumer. Not a safety issue. |
| CODEX1-5 | LOW | OPEN at 6f0fe7aa | The sweep output still has no `work_done`/`WORK_KEYS`; `queued` and `knowledge_proposed` are not generic counters. 7436b3aa (newer, unreviewed) claims a fix. |
| CODEX1-6 | LOW | **FIXED** | `enqueue_purchase` returns `reason: licence_refused` instead of raising after files are stored. |
| CODEX1-7 | LOW | OPEN | `analyse_file` still retrieves and parses before the existing-row check. a0b53d28 (newer, unreviewed) touches this. |
| CODEX1-8 | LOW | UNKNOWN | Mutations not re-run. |
| CODEX1-9 | LOW | **FIXED** | Roots that contain the tree are refused. Probe P1: `/`, the app, app/src, the app's parent, the checkout, a symlink to app/src, a symlink to `/`, a relative root from inside the tree and a `..` traversal are all REFUSED. The default, `/tmp/x` and `/home` (which does not contain this checkout) are accepted. An empty env falls back to the default. |
| CODEX1-10 | INFO | not re-checked | |

## New findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| CODEX2-1 | **HIGH** | **Permanent release hold for legacy findings, including met requirements.** `enforce.check` adds `teardown finding for <key> requires independent review` for every unreviewed requirement row with confidence None or ≥0.5, **whatever its verdict** (including `met`); not_applicable rows are skipped. `release_gates` (`publish/release_gates.py:1653`) blocks publishing on those reasons. After `core/migrate.apply` adds the columns, every existing `teardown_findings` row has `recorded_by = NULL`. `review.review_finding` refuses such rows ("recorder is unknown; independent review cannot be established"), and no backfill, attestation or other route sets `recorded_by` on a legacy row. Rows written by a rolled-back 0967c3ee release get `review_state = NULL`, which also cannot be reviewed. Any product with a publish-consumer requirement derived from a legacy non-self finding is therefore blocked until someone edits the database by hand. `test_cert_improve_wave` had to be changed to review findings first (fixtures were added; no assertions were removed), which confirms the behaviour change. Production impact depends on whether the deployed `teardown_findings` table holds non-`brambleloop:` rows, which is UNKNOWN. A gate with no way to open is still a defect. | Scratch SQLite. Finding A: `TeardownFinding(benchmark_ref='mjs-1', dimension='instruction_clarity', score=9, confidence=0.9, recorded_by=None)`. Self-audit B: `brambleloop:demo`, same dimension, score 10. `enforce.check(db,'demo',consumers=PUBLISH_CONSUMERS)` at **0967c3ee** gives `exceed / met / binding=True`, `blocks=False`. At **6f0fe7aa** it gives `exceed / met / binding=False / proposed`, `blocks=True`, reason "teardown finding for dimension:instruction_clarity requires independent review". `review_finding(A, reviewer='owner:jacob', decision='reviewed' or 'rejected')` gives ReviewRefused "recorder is unknown". **Fix options:** (a) only hold when the verdict is not `met`; (b) add a step-up owner action that attests a legacy recorder or reviews/rejects a legacy row, with its own audit; (c) treat legacy rows (`recorded_by IS NULL`) as before (binding per confidence) until they are reviewed. Add a test with a migrated legacy row. |
| CODEX2-2 | **HIGH** | **Retention-guard regression (existing suite).** 2f55f22b's `_lesson_roots` verifies defect lessons with `select(AuditLog).where(AuditLog.action == action)`, where `action` comes from a dict lookup. The AST scanner cannot resolve this, so `retention.unknown_read_actions()` returns `['unresolved:improve/design_knowledge.py::_lesson_roots']`. The concern is real, not only a scanner limit: if retention prunes old `cir.compiled` rows, a lesson that verified yesterday is refused today. That fails closed, but provenance then decays silently. | `PYTHONPATH=src:tests python tests/test_w4_fmbatch1_retention_guard.py` gives AssertionError at line 83 (`unknown_read_actions() == []`). The direct call returns `[]` at 0967c3ee and 26533977, and `['unresolved:…_lesson_roots']` at 6f0fe7aa and at 25c7e802. **Fix:** use literal action constants (two explicit selects) and add `cir.compiled` / `cir.revise_unrepairable` to `KNOWN_READ_ACTIONS` with a retention decision. Better still, record the root audit id in the lesson's `source_findings` or `evidence_ref`, so verification does not depend on unrelated, prunable audit rows. |
| CODEX2-3 | MED | **The frozen held-out manifest goes stale on merge with INTEG1.** `design_eval_cases.json` pins `cir_sha256` for launch0 `hexagonal-bread-basket`, and INTEG1 changes `products/launch0.py`. In a scratch merge of INTEG1 7c42e706 with 6f0fe7aa (conflicts resolved trivially), `test_codex_design_eval_cases` fails: `DesignEvaluationRefused: held-out cases differ from the frozen manifest`, with drift only in `hexagonal-bread-basket.cir_sha256`. The design fails closed, which is correct, but the integrator must re-freeze deliberately and record who did it and why, rather than regenerating to green. Separately, `research/bench2/out/product_truth.json` is not copied into the Docker image (it COPYs only src, release, tests and run_tests.sh), so `load_cases()` always refuses in production. That fails closed, and `test_codex_design_eval_cases` would fail if run inside the image. | `cd <merge>/brambleloop && PYTHONPATH=src:tests python tests/test_codex_design_eval_cases.py` gives 1 error. A diff of `materialize_cases()` against the manifest yields `hexagonal-bread-basket ['cir_sha256']`. |
| CODEX2-4 | MED | **"Independent" review is checked by string only, and the recorder is hard-coded.** `scorecard.record` and `audits.record` default `recorded_by="teardown_analyst"`. The operator routes `/api/teardown/audit` and `/api/teardown/finding` never pass the real actor. The owner action records `reviewed_by="owner:<actor>"`, so a finding the owner entered through the operator route can be "independently" reviewed by the same owner. The same holds for analyses (`recorded_by` default `teardown_analyst`), although those are machine-produced, so owner review of them is genuinely independent. | Probe P5: `scorecard.record(...)` stores `recorded_by == 'teardown_analyst'`. `review_finding(fid, reviewer='owner:operator')` then returns `reviewed`. **Fix:** stamp `recorded_by` from the authenticated principal on the routes (for example `operator:<token-id>` or `owner:<session>`), and refuse review when principals match. |
| CODEX2-5 | LOW | **Weak defect and support lesson verification.** A `quality/defect` lesson with `evidence_ref="cir.compiled:compile_failed"` is accepted whenever *any* `cir.compiled ok:false` audit exists anywhere; it is not bound to the lesson's members. A support lesson needs only one `SupportCase` with a matching slug and id. No IP path is involved, and both must still pass a future approval. Related: `_finding_source` rejects confidence None while `enforce` treats None as binding, so a binding requirement with a None-confidence root cannot become a proposal. That inconsistency fails closed. | Code read: `design_knowledge._lesson_roots`. Probe P4: with no compile-failure audit present, the defect lesson is refused, which is correct. |
| CODEX2-6 | LOW | **Requirement row multiplication and lesson churn.** `requirements()` now groups by (key, review_state, sufficient), so one key can yield up to 4 rows. Consumers that key by `r['key']` (the `provisional`/`unmet` lists and the lesson subjects) can double-count. The teardown lesson `evidence_ref` now includes a digest of the roots, so each change in group membership publishes a new lesson, while old lessons are neither withdrawn nor superseded and remain proposable. | Code read: `teardown/enforce.py`, `runtime/release.py:6986`. |
| CODEX2-7 | INFO | `reconcile_state` can move `awaiting_analyst` to `queued`. `intel/purchase_selection.taught_nothing_yet` counts `analysed` and `needs_analyst` as taught. `with_for_update()` is a no-op on SQLite, so the lock-based races are reasoned on Postgres but not executed (UNKNOWN). The owner-recorded purchase path trusts the operator-route caller for licence terms, exactly as the pre-existing `licence_terms` field did; publishing uses are always stripped. | Code read. |

## Adversarial checks

- **Library root guard:** PASS (see CODEX1-1 and CODEX1-9). The env override is honoured; symlinks are resolved before comparison.
- **LibraryRefused/ReferenceRefused handling:**
  - `originality.refuse_benchmark_reference` converts `LibraryRefused` to `ReferenceRefused`, and `gateway/images` raises `ImagesRefused`; both are named refusals.
  - `originality.benchmark_images` and `reader` catch it as before.
  - Intake returns 503.
  - `lab.write_manifest` (lab.py:581) does not catch `LibraryRefused`. This is reached only with an unsafe env, and after intake has already validated the root in the same request.
  - PASS.
- **JOB_CLASS/JOB_BANDS:** both job types are classified. No new job types appear in the 26533977..6f0fe7aa delta. `test_w3_k11_authority` and `test_v11_autonomy_timeline` pass. PASS.
- **CODEX1-3 provenance:** PASS at 6f0fe7aa (probe P4). The finding, analysis, lesson and incident kinds all trace to reviewed roots, or fail closed.
- **IP isolation:** PASS.
  - The only reader of `DesignRule` is its own writer, and `design_eval` is not called from `src` outside tests.
  - `measure_written_case`/`compare_written_case` store counts only, and return `approval_evidence_complete: False`.
  - Purchase provenance fields pass through `check_derived`.
  - Analysis observations remain closed vocabulary.
- **Held-out leakage (dbd1e14f):** PASS. The manifest is hashes and ids only. `load_cases(challenger_cases=…)` is refused. No proposal or training path reads `materialize_cases`/`load_cases`. Note: the "held-out" set is our own launch catalogue, which is also what future rules target. That is a fixed regression set rather than a statistically held-out sample. INFO.
- **Idempotency (40292ecd):** PASS (code read plus `test_codex_analysis_worker` 5/5, including restart and reopened-DB sweeps). `propose_from_analysis` has key uniqueness, an existing-row check and an IntegrityError fallback; `reconcile_state` recomputes from durable rows.
- **Tests weakened:** none found.
  - The 623fc26c..6f0fe7aa test diff removes no assertions.
  - Changes to existing tests add review steps and fixture fields (`test_cert_improve_wave`, `test_codex_finding_review`, `test_codex_design_proposals`).
  - Note that `test_cert_improve_wave` needed review steps because of the CODEX2-1 behaviour change.

## DB compatibility (rollback target 0967c3ee)

The changes go beyond new tables. Additive columns on **existing** tables:

- `teardown_findings`: `recorded_by`, `review_state` (indexed, literal default `proposed` backfilled by migrate), `reviewed_by`, `reviewed_at`
- `benchmark_products`: `purchase_provenance`
- `lessons`: `source_findings`

New tables: `benchmark_analyses` (now with 4 review columns) and `design_rules`.

`core/migrate.apply` adds the nullable columns, backfills the literal defaults and creates the indexes. On SQLite this was verified: an old 0967c3ee DB was migrated forward by 6f0fe7aa (`review_state` backfilled to `proposed`), then 0967c3ee code wrote again successfully. **Rollback is safe**, because old ORM code ignores the extra columns and nothing old has an FK into the new tables. Rows written during a rollback have `review_state = NULL` and `recorded_by = NULL`; on roll-forward they are unreviewable, which compounds CODEX2-1. Live Postgres migration was not executed (UNKNOWN). `test_w4_auditfix_migrate` passes.

## Suites (6f0fe7aa unless noted; one at a time; venv-integ4; `BRAMBLELOOP_BENCHMARK_LIBRARY` unset)

| Suite | Result |
|---|---|
| test_w3_k11_authority | PASS |
| test_image_reference_hash_failclosed | PASS (4) |
| test_originality | PASS |
| test_codex_library_boundary | PASS (5) |
| test_codex_analysis_store | PASS (1) |
| test_codex_analysis_worker | PASS (5) |
| test_codex_design_eval_cases | PASS (4) at 6f0fe7aa; **FAIL (1 error) on the INTEG1 merge** (CODEX2-3) |
| test_codex_design_proposals | PASS (2), matching Codex's 2/2 |
| test_codex_failure_mining | PASS (1), matching Codex's 1/1 |
| test_codex_finding_review | PASS (1), matching Codex's 1/1 |
| test_codex_finding_review_cc | PASS (2) |
| test_codex_lesson_provenance | PASS (4), matching Codex's 4/4 |
| test_codex_purchase_intake | PASS (3) |
| test_codex_purchase_intake_api | PASS (1) |
| test_cert_improve_wave | PASS (0 failures), matching Codex's 24/24 |
| test_mine | PASS (rc 0), matching Codex's 7/7 |
| test_w4_fmbatch1_readings_bus | PASS (rc 0), matching Codex's 3/3 |
| test_cert_culture_teardown | PASS |
| test_w4_listready | PASS |
| test_teardown | PASS |
| test_teardown_audits | PASS |
| **test_w4_fmbatch1_retention_guard** | **FAIL** (CODEX2-2); not in Codex's reported list |
| test_w4_auditfix_migrate | PASS |
| test_v11_autonomy_timeline | PASS |
| test_swarm_runtime | PASS |
| test_shadow | PASS (rc 0, 1352s) |

Codex did not report `test_w4_fmbatch1_retention_guard`; it fails at the SHA it reported on. The full suite was not run (per instructions), so other suites are UNKNOWN.

## Merge with origin/claude/w5-INTEG1 (7c42e706)

`git merge-tree --write-tree --name-only origin/claude/w5-INTEG1 6f0fe7aa` exits 1 with three textual conflicts, the same set as at 26533977 and at CODEX1:

- `COORDINATION.json`: textual.
- `brambleloop/src/brambleloop/autonomy/autonomy_map.json`: regenerate after the merge.
- `brambleloop/src/brambleloop/runtime/pipeline.py`: the late-import block. Keep INTEG1's `commercial_ops`, `learning_gaps_ops` and `evidence_ops` together with Codex's `teardown_ops`.

`approvals.py`, `authority/classes.py`, `core/models.py`, `agents/registry.py`, `ops/retention.py`, `runtime/worker.py`, `swarm/orchestrate.py` and `ops/CONTRACT_CHANGES.md` auto-merge.

**Semantic conflict:** the frozen eval manifest drifts after the merge (CODEX2-3). After merging, regenerate the autonomy map, deliberately re-freeze `design_eval_cases.json`, and rerun `test_v11_autonomy_timeline`, `test_w3_k11_authority`, `test_codex_design_eval_cases` and `test_w4_fmbatch1_retention_guard`.

## Probes (scratch, reverted; script at scratchpad/probes/probe_cx2.py)

- P1: library_root matrix (above).
- P2: the image gateway with the env unset passes; env `/` or env app both raise `ImagesRefused` (named).
- P3: CODEX2-1 repro.
- P4: CODEX1-3 laundering attempts, all refused.
- P5: CODEX2-4.
- A forward and rollback migration on SQLite.
- A base comparison at 0967c3ee.

## Commands

```
git -C /home/user/Project-Money fetch -q origin codex/p0-learning-reference claude/w5-INTEG1
git worktree add --detach <scratch>/cx2rev 6f0fe7aa ; <scratch>/cx2base 0967c3ee ; <scratch>/cx2merge origin/claude/w5-INTEG1 (+ merge --no-commit 6f0fe7aa)
cd <wt>/brambleloop && env -u BRAMBLELOOP_BENCHMARK_LIBRARY PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/<suite>.py   # one at a time
python -c "from brambleloop.ops import retention; print(retention.unknown_read_actions())"   # per SHA
git merge-tree --write-tree --name-only origin/claude/w5-INTEG1 6f0fe7aa
git worktree remove --force <scratch>/cx2rev <scratch>/cx2base <scratch>/cx2merge
```
