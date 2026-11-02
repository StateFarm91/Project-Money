# Independent security review: CODEX1 (P0-LEARNING-REFERENCE, first push)

- Subject: `origin/codex/p0-learning-reference` at 623fc26c (base merge 88982f20; commits 99805eb7..623fc26c)
- Reviewer: independent, adversarial, read-only. 2026-11-02 (UTC). No deploy, no spend, no Railway, no network to vendors.
- Scope: `git diff 88982f20 623fc26c` (21 files, +631/-9)

## Verdict: DO NOT SHIP

There are two HIGH regressions, both reproduced against the base commit. Base 88982f20 passes all three affected suites; 623fc26c fails them.

1. The new `library_root()` guard refuses the default library location. With `WORKDIR /app` in the Docker image, it now raises `LibraryRefused` on the image-gateway reference path, on intake and on manifest writes, unless `BRAMBLELOOP_BENCHMARK_LIBRARY` is set. Nothing in the repository sets it or documents it.
2. The two new job types have no authority class, so `test_w3_k11_authority` fails.

On copyright and IP the increment is sound. Analysis rows hold only closed vocabulary, counts, page numbers and hashes. Nothing reads `BenchmarkAnalysis` or `DesignRule` yet, so no reference content can reach a CIR, PDF, listing or image prompt. The "proposal only" approval path cannot produce active knowledge, because no approve function and no reader exist.

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| CODEX1-1 | **HIGH** | `teardown/library.library_root()` (be92bfe1) refuses any root inside `Path(__file__).parents[3]`. In the image that is `/app` (Dockerfile `WORKDIR /app`, code at `/app/src/brambleloop/...`). The default root `benchmark_library` resolves against cwd `/app`, so it is now refused. Callers are `gates/originality.refuse_benchmark_reference`, called by `gateway/images.refuse_benchmark_references` for every reference image, `teardown/intake.receive` and `teardown/lab.write_manifest`. `refuse_benchmark_references` catches only `ReferenceRefused`, so the uncaught `LibraryRefused` crashes every reference-conditioned image request (#200 identity lock). Intake (`POST /api/teardown/intake` catches only `IntakeRefused`) returns 500. `originality.benchmark_images` swallows `LibraryRefused`, so presentation similarity silently reports nothing compared once purchases exist. The repo neither sets nor documents `BRAMBLELOOP_BENCHMARK_LIBRARY`. Production config is UNKNOWN (Railway not inspected). Existing suites regress: `test_image_reference_hash_failclosed` (3 ERRORs: LibraryRefused) and `test_originality` (`test_a_renamed_copy_of_a_purchased_file_is_refused_by_its_bytes`), both green at base. | From `brambleloop/` with the env var unset: `PYTHONPATH=src python -c "from brambleloop.gateway.images import refuse_benchmark_references; refuse_benchmark_references(['/tmp/ok.png'])"` raises `LibraryRefused`. From cwd `/tmp` it passes. Suites: see Commands. **Fix:** move the default to an external path (for example `/var/lib/brambleloop/benchmark_library`), or require the variable with a documented OWNER/ops config item, and keep the existing tests unchanged. Never weaken them. |
| CODEX1-2 | **HIGH** | `teardown.analyse` and `teardown.analyse_sweep` are registered (handlers, CADENCES, agent registry) but absent from `authority/classes.JOB_CLASS`, so they classify as UNCLASSIFIED. The F-669 coverage test fails: `job types with no explicit authority class: ['teardown.analyse', 'teardown.analyse_sweep']`. W5-INTEG1's `classes.py` does not add them either. | `PYTHONPATH=src:tests python tests/test_w3_k11_authority.py` gives 1 failing (base: 0 failing). Fix: add both to `JOB_CLASS` (`_B` like `teardown.enforce`, or `_R`). |
| CODEX1-3 | MED | The independent-review gate on findings can be laundered through a lesson. `design_knowledge.propose` refuses a `finding` that is not `reviewed`, but accepts any `lesson` id. `teardown.enforce` (runtime/release.py ~6985) publishes every *binding* teardown requirement, derived from unreviewed findings, as a `Lesson` (`evidence_ref=teardown_requirement:...`). A proposal that cites that lesson is accepted. This is not exploitable today, because there is no approve path or reader, but it will be once WO-2 approval lands. | Scratch DB: create an unreviewed `TeardownFinding`. `propose(... finding)` is refused. Then `bus.publish(..., evidence_ref="teardown_requirement:x:y")` and `propose(... lesson)` returns `{'state': 'proposed'}`. Fix: refuse lessons whose `evidence_ref` starts with `teardown_requirement:` or `teardown`, or whose origin chain contains an unreviewed finding. |
| CODEX1-4 | MED | Incomplete against the work order and owner requirements; this is not a safety issue. The push has no `review_state`/`reviewed_by` on `TeardownFinding`, no review action, and no approve function. It has no WO-3 evaluation (`quality/design_eval.py`), no `applicable(scope)` reader and no `consume.act` recording. `teardown_state` is never moved to `analysed` or `needs_analyst`, and there is no `lab.record_audit` prefill. Non-MJ intake is missing, as are knowledge-gap detection and purchase recommendations. The consumer interface for opus2's A6 does not exist yet: `design_knowledge` exposes only `propose()`, and `improve/consume.act` consumes `Lesson` rows, not `DesignRule`. The WO test files `test_codex_teardown_analyse.py`, `test_codex_design_knowledge.py` and `test_codex_design_eval.py` are absent. | `git grep -n "DesignRule\|BenchmarkAnalysis" 623fc26c -- brambleloop/src` shows only the writer side. |
| CODEX1-5 | LOW | The `teardown.analyse_sweep` output (`purchases/queued/existing/licence_refused`) has no `work_done` and no `WORK_KEYS` entry, so `pipeline.did_no_work` is always True, even when it queued jobs. `ops.queue_check` will re-drive it on every deploy, and it reads as a permanent no-op cadence. | `did_no_work({'purchases':1,'queued':1,...}, 'teardown.analyse_sweep')` returns True. |
| CODEX1-6 | LOW | `intake.receive` now calls `enqueue_purchase` after the files are stored, the audit is written and the manifest is regenerated. If the owner-recorded terms omit `private_analysis` from `allowed_uses`, `LicenceRefused` (a `PermissionError`) escapes `receive`. The route catches only `IntakeRefused`, so the upload half-succeeds and returns a 500. | Code read: `teardown/intake.py` (end of `receive`) and `app/main.py` (~6884). |
| CODEX1-7 | LOW | `analyse_file` retrieves and parses the quarantined PDF before checking for an existing analysis, so a retry or re-run re-reads the file every time. Idempotency is still correct (unique `(benchmark_id, file_sha256)`, IntegrityError fallback). Dedup is permanent per `teardown:<id>:<sha>`, so a dead-lettered analysis is never retried by the sweep; it needs `ops.queue_check`/requeue. | Code read. |
| CODEX1-8 | LOW | Test gaps (surviving mutations): M3 (`check_derived(producer)` removed), M6 (manifest recheck under `FOR UPDATE` removed), M8 (`refuse_unless_permitted` in `enqueue_purchase` removed; still covered by `library.retrieve`'s licence check in depth), and M13 (supersedes-must-share-key check removed). | See Mutations. |
| CODEX1-9 | LOW | The guard rejects roots inside the app tree but not roots that *contain* it (for example `BRAMBLELOOP_BENCHMARK_LIBRARY=/` or `/home/user`). Such a root makes source files readable as "library" paths and lets intake write purchase folders beside the code. | Code read of `library_root`. |
| CODEX1-10 | INFO | `design_rules` (approval records) is not listed in `core/continuity.NON_REDERIVABLE`, although continuity exports it anyway. `mine.py` will mine every `cir.compiled ok:false`, including expected intermediate failures inside a revise loop, which may add noise lessons. | Code read. |

## Adversarial checks

1. **Copyright/IP: PASS for this increment.** `BenchmarkAnalysis.observations` contains page counts, booleans, dimension verdicts, architecture presence plus page numbers, construction verdict, `pieces_named` (from the closed `PIECE_VOCABULARY`), and the `size_family.numeric_summary` numbers. There is no document text, and a test asserts that "Row 1" is absent. Only hashes and ids go to the audit. `DesignRule.statement` is restricted to the registered rule id `include_finishing_checklist` with empty parameters; scope is a closed vocabulary; producer goes through `check_derived`. Nothing reads either table, so no route to a CIR, PDF, listing or image prompt exists. `benchmark_library/` is gitignored (brambleloop/.gitignore:16). The `.dockerignore` is effective: `brambleloop/railway.json` builds `brambleloop/Dockerfile`, so the context is `brambleloop/`. The Dockerfile only COPYs src, release, tests and run_tests.sh. No new `check_derived` covers the analysis observations, but they are closed vocabulary by construction.
2. **Approval: fail-closed today.** There is no approve or activate path, and rows are written `state="proposed"`. Unreviewed findings are refused (a missing `review_state` is treated as not reviewed, so UNKNOWN does not count as reviewed). This is weakened by CODEX1-3 (lesson laundering). Independent approval and audit do not exist yet (CODEX1-4).
3. **Durability: partially consistent.** Handlers registered (pipeline import), CADENCES `teardown_analyse_sweep` daily, agents registry, `JOB_BANDS` (`benchmark_change`), `autonomy_map.json` regenerated (identical to a fresh `--write` except timestamp; counts 132/165/34/82), `retention.unknown_read_actions() == []`. **Missing:** `authority/classes.JOB_CLASS` (CODEX1-2) and `WORK_KEYS` (CODEX1-5). Retries are idempotent: enqueue key `teardown:<id>:<sha256>`, a unique DB constraint, a re-check under `with_for_update`, and the IntegrityError fallback. The worker restart test passes.
4. **Database:** see the statement below.
5. **No spend and no vendor network.** No gateway or provider call is added; analysis is local PDF parsing.
6. **Ownership: no duplication.** None of the WO's protected files is touched (`publish/pdf.py`, `quality/physical.py`, `radar/intake.py`, `improve/commercial_lessons.py`, `products/production_inventory.py`). opus2's `learning.knowledge_gaps`, `commercial_lessons` and `consume.py` changes on INTEG1 are not duplicated, and no opus2 branch defines `DesignRule` or `design_knowledge`. A6 has nothing to consume yet (CODEX1-4).
7. **Removed or weakened assertions: none.** The test diff is +301/-0, and the `mine.py` edits keep the existing gate, asset and release branches intact. However, the change breaks three existing suites (CODEX1-1 and CODEX1-2).

## DB-compatibility statement

The push adds two **new tables** and no column changes to existing tables:

- `design_rules`: unique `(key, version)`, self-FK `supersedes`, and indexes on `key` and `state`.
- `benchmark_analyses`: FK to `benchmark_products.id`, and unique `(benchmark_id, file_sha256)`.

`core/db.create_all` and `core/migrate` create missing tables on boot through `Base.metadata.create_all`. This is the same path every earlier table used, and it never alters existing tables, so it is additive on the deployed Postgres. `test_w4_auditfix_migrate` passes on SQLite.

Rolling back to the previous release is safe: old code ignores the extra tables, and nothing old has an FK into them. Continuity exports made by the new release would include the two extra tables. Whether an *old-release restore* tolerates unknown tables was not verified.

Not executed on Postgres: live Postgres boot-migration is **UNKNOWN**, reasoned compatible but not run.

## Merge-tree result

`git merge-tree --write-tree origin/claude/w5-INTEG1 origin/codex/p0-learning-reference` exits 1 with tree 422a81bc and 3 conflicts:

- `COORDINATION.json`: textual, in an unrelated photo-approval entry.
- `brambleloop/src/brambleloop/autonomy/autonomy_map.json`: regenerate after the merge.
- `brambleloop/src/brambleloop/runtime/pipeline.py`: the late-import block. INTEG1 adds `commercial_ops`, `learning_gaps_ops` and `evidence_ops`; Codex adds `teardown_ops`. Keep all four.

These auto-merge cleanly: `agents/registry.py`, `core/models.py` (INTEG1 adds the `OwnerAction` partial unique index and a `text` import; no overlap), `ops/retention.py`, `runtime/worker.py` and `swarm/orchestrate.py` (INTEG1 added `JOB_BANDS` for `chain.successors`, `listing.package`, `intel.scan_evidence`, `improve.commercial_lessons`, `learning.knowledge_gaps` and `radar.concept_intake`; no clash).

INTEG1 also changed `teardown/reader.py` (assembly cue exclusions), which changes what `analysis_store` records for joined-round documents; this is benign. INTEG1's `authority/classes.py` changes do not fix CODEX1-2. After resolving the conflicts, regenerate the autonomy map and rerun `test_v11_autonomy_timeline` and `test_w3_k11_authority`.

## Tests run (one at a time; venv-integ4; `BRAMBLELOOP_BENCHMARK_LIBRARY` unset)

| Suite | 623fc26c | Base 88982f20 |
|---|---|---|
| test_codex_analysis_store | PASS (1) | n/a |
| test_codex_analysis_worker | PASS (3) | n/a |
| test_codex_design_proposals | PASS (1) | n/a |
| test_codex_failure_mining | PASS (1) | n/a |
| test_codex_library_boundary | PASS (2) | n/a |
| test_swarm_runtime | PASS | not run |
| test_teardown | PASS | not run |
| test_teardown_reader | PASS | not run |
| test_improve | PASS | not run |
| test_w4_auditfix_migrate | PASS | not run |
| test_vacuity | PASS | not run |
| test_w4_fmbatch1_retention_guard | PASS | not run |
| **test_w3_k11_authority** | **FAIL** (F-669 unclassified types) | PASS |
| **test_image_reference_hash_failclosed** | **FAIL** (3 ERROR, LibraryRefused) | PASS |
| **test_originality** | **FAIL** (27/28; LibraryRefused) | PASS (28/28) |

Not run: `test_v11_autonomy_timeline`, `test_w4_wraptest` and `test_w3_k12_model_photography`. The last two exercise reference images and are likely also affected by CODEX1-1, but this is UNKNOWN.

## Mutations (scratch worktree, reverted)

| Mutation | Suite | Result |
|---|---|---|
| M1 finding review_state check off | design_proposals | killed |
| M2 evidence-exists check off | design_proposals | killed |
| M3 `check_derived(producer)` removed | design_proposals | **survived** |
| M4 library_root guard off | library_boundary | killed |
| M5 post-read sha256 recheck off | analysis_store | killed |
| M6 locked manifest recheck off | analysis_store | **survived** |
| M7 licence-recorded check off | analysis_worker | killed |
| M8 enqueue `refuse_unless_permitted` off | analysis_worker | **survived** (defence in depth via retrieve) |
| M9 idempotency key removed | analysis_worker | killed |
| M10 compile-failure mining off | failure_mining | killed |
| M11 unrepairable mining off | failure_mining | killed |
| M12 `ok is False` filter off | failure_mining | killed |
| M13 supersedes-same-key check off | design_proposals | **survived** |
| M14 parameter vocabulary check off | design_proposals | killed |

## Commands

```
git -C /home/user/Project-Money fetch origin
git worktree add --detach <scratch>/codexrev-1 623fc26c ; git worktree add --detach <scratch>/codexrev-base 88982f20
git diff 88982f20 623fc26c
cd <wt>/brambleloop && env -u BRAMBLELOOP_BENCHMARK_LIBRARY PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/<suite>.py   # one at a time
PYTHONPATH=. python -m brambleloop.autonomy.map --write <scratch>/amap.json   # compared to committed map, identical bar timestamp
python -c "from brambleloop.ops import retention; print(retention.unknown_read_actions())"   # []
git merge-tree --write-tree --name-only origin/claude/w5-INTEG1 origin/codex/p0-learning-reference
git worktree remove --force <scratch>/codexrev-1 <scratch>/codexrev-base
```
