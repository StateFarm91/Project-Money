# Independent security review: CODEX3 (P0-LEARNING-REFERENCE, delta)

- Subject: `origin/codex/p0-learning-reference`, delta after the last reviewed SHA 6f0fe7aa058dc315f5cf3fa0be10d695df0bb0b3.
- **Exact SHA reviewed and verdicted: 20e0b3a7106d55fa3f94b858a48926d4911f6caa** (confirmed with `git rev-parse` after `git fetch`).
- Commits in the delta (18, oldest first):
  - 7436b3aa Report actual work for reference analysis jobs
  - 8a8c00b8 Freeze the full current launch catalogue for learning evaluation
  - a0b53d28 Recheck analysis licence before persisting observations
  - 493221e4 Persist fail-closed evaluation previews over frozen cases
  - 96bbdd6a Measure twin, claim and originality evidence in evaluation previews
  - 6c8aa061 Record individual benchmark and stitch gate states in previews
  - 1d311d12 Add independent rejection for proposed design rules
  - 25c7e802 Exercise frozen benchmark truth cases and detect replaced findings
  - 8f2a5c7c Bind independent reference reviews to their evidence
  - ae2b7079 Evaluate and verify frozen learning knowledge before writer use
  - 5e652f42 Recover dead learning jobs when their inputs return
  - bb6c558a Read frozen benchmark evidence through private licensed storage
  - eb84f326 Track reference knowledge gaps through the incident lifecycle
  - 2b6688a1 Preserve unmeasured audit elements for analyst review
  - 24b70df0 Compare successor knowledge against the verified incumbent
  - c7bda4e1 Keep instruction writer independent with verified frozen directives
  - 32dc9635 Keep unknown knowledge gaps open and document integration status
  - 20e0b3a7 Avoid unreviewable legacy teardown release holds
- Reviewer: independent, adversarial, read-only. 2026-11-02 (UTC). No push, no commit, no deploy, no Railway, no vendor network. Scratch worktrees only (all removed afterwards).
- Prior report: `origin/claude/w5-SECREVIEW-CODEX2:brambleloop/research/final_build/w4/INDEPENDENT_SECREVIEW_CODEX2.md`.
- Codex's own framing: this is not a completion or integration request (`CODEX_P0_LEARNING_HANDOFF.md` says "not ready for integration"). CODEX2-3 and CODEX2-4 are acknowledged as open.

## Verdict for 20e0b3a7: DO NOT SHIP (not even as an inert partial), because of one new HIGH: CODEX3-1

CODEX2-2 is fixed. CODEX2-1's unclearable hold is gone, but the fix overshoots. It turns a release gate that blocks at the rollback target 0967c3ee into a non-blocking one, for every pre-migration finding. Those findings have no path to become binding again, and a new test asserts the weakened behaviour. Because `enforce.check` feeds `publish/release_gates.py` today, integrating this branch is **not inert**: the live publish gate changes. Everything else in the delta is either inert in production (no producer of pinned CIRs, no consumer of `DesignRule` on release paths) or fails closed.

**What would flip this to SHIP-AS-PARTIAL (inert):** either option is enough.

- (a) Main or the owner records an explicit decision that pre-migration (legacy) teardown findings become advisory. The decision must be backed by evidence that the production `teardown_findings` table holds no non-`brambleloop:` rows that would be relaxed.
- (b) Add a step-up owner path that makes a legacy row binding again: attest a recorder, or review or reject the legacy row. Until it is reviewed, keep a legacy *unmet/unmeasured* row blocking (binding per confidence, as at 0967c3ee); let a legacy *met* row produce no hold.

Option (b) is what CODEX2-1 fix (c) proposed.

The other conditions in this report are integration preconditions, not blockers for an inert merge: CODEX2-3 re-freeze, CODEX3-2 for A6, and the merge resolution.

## Prior-finding status

| ID | Prior sev | Status at 20e0b3a7 | Evidence |
|---|---|---|---|
| CODEX2-1 | HIGH | **Hold FIXED, but superseded by CODEX3-1** | `enforce.check` now emits "requires independent review" only for `verdict in (unmet, unmeasured)` and `review_state == "proposed"`. A met provisional requirement no longer blocks. Legacy rows (`recorded_by` NULL, or `review_state` NULL from rollback-window writes) get `review_state = "legacy"` and `binding = False`, and produce no reason. `test_codex_legacy_findings` passes 2/2. The migrated-DB probe (DB created by 0967c3ee code, migrated by head, written again by 0967c3ee code) shows no unclearable hold. New attributable findings (`scorecard.record`/`audits.record` default `recorded_by = "teardown_analyst"`) are `proposed`, and unmet ones hold until reviewed; that hold is clearable. **However**, legacy unmet and unmeasured requirements now block nothing (CODEX3-1). |
| CODEX2-2 | HIGH | **FIXED** | `_lesson_roots` uses literal `AuditLog.action == "cir.compiled"` / `"cir.revise_unrepairable"` selects. `cir.revise_unrepairable`, `design_eval.completed` and `design_knowledge.rule_approved` are in `KNOWN_READ_ACTIONS` as `lifetime_total`. `test_w4_fmbatch1_retention_guard`: 5/5 OK. |
| CODEX2-3 | MED | **OPEN, and it has grown** | The frozen manifest now pins 8 launch cases. In a scratch merge with INTEG1 7c42e706, the drift is `hexagonal-bread-basket.cir_sha256` **and** `hexagon-coaster-set.cir_sha256`, against 1 case before. INTEG1 also changes `cir/writer.py`, `compiler.py`, `model.py`, `twin.py`, `reverse.py` and `teardown/reader.py`. All of these feed `implementation_digest`, so after the merge every evaluation and pin is stale by design. The bench2 inputs are still not in the image; they now come from the private library (`OA-BENCH-LIBRARY-VOLUME`), which Main must provision. Missing inputs fail closed. |
| CODEX2-4 | MED | **OPEN** (acknowledged) | `scorecard.record` and `audits.record` still default `recorded_by = "teardown_analyst"`, and the operator routes do not pass the authenticated principal. Rule review uses `producer` (`"teardown_analyst"` for auto-proposals) against `owner:<actor>`, which is genuinely independent for machine proposals. |
| CODEX2-5 | LOW | OPEN | Defect-lesson verification still accepts any `cir.compiled ok:false` audit, without binding it to the lesson's members. The query is now literal. |
| CODEX2-6 | LOW | OPEN, slightly wider | Grouping is now (key, review_state ∈ {reviewed, proposed, legacy}, sufficient), so up to 6 rows per key. |
| CODEX2-7 | INFO | unchanged | `with_for_update()` is still a no-op on SQLite. Postgres race behaviour is UNKNOWN. |
| CODEX1-5 | LOW | **FIXED** | `teardown.analyse`, `teardown.analyse_sweep`, `design_eval.sweep` and `design_eval.evaluate` return `work_done` and are declared in `WORK_KEYS`. |
| CODEX1-7 | LOW | OPEN | `analyse_file` still retrieves and parses the PDF before the existing-row check. This costs efficiency only. a0b53d28 adds a licence re-check under lock before persisting, which is good. |
| CODEX1-8 | LOW | UNKNOWN | Mutations were not re-run. |

## New findings

| ID | Sev | Finding | Repro / fix |
|---|---|---|---|
| CODEX3-1 | **HIGH** | **Fail-open regression in a live publish gate.** `enforce.requirements` classifies every finding with `recorded_by IS NULL` or `review_state IS NULL` as `legacy`, with `binding = False`. `enforce.check` adds no reason for legacy rows, whatever the verdict. After `core/migrate.apply`, **every** pre-existing `teardown_findings` row is legacy, and so is every row written by 0967c3ee code during a rollback window. `review.review_finding` still refuses those rows ("recorder is unknown"), so a legacy requirement can never become binding again. Adopted floors (`adopt_floor`, #164) on legacy findings are therefore also no longer enforced. At 0967c3ee the same data **blocks** publishing through `release_gates.py:1653`. `test_codex_legacy_findings::test_unmet_legacy_without_attribution_is_nonbinding` asserts the relaxed behaviour (unmeasured legacy, `blocks == False`). No DECISION_LOG entry records the change. Production impact depends on whether production holds non-self teardown findings, which is UNKNOWN (not inspected). | Probe `scratchpad/probes/probe_cx3_gate.py`: benchmark finding `mjs-1` instruction_clarity 9 (conf 0.9), our self-audit 3. At **0967c3ee**: `exceed/unmet/binding=True`, `blocks=True`. At **20e0b3a7**: `exceed/unmet/binding=False/legacy`, `blocks=False`, `reasons=[]`. The unmeasured variant behaves the same way (True → False). **Fix:** keep legacy unmet/unmeasured rows blocking (binding per confidence, as before) and only drop the hold for met rows. Also add a step-up owner action that attests or reviews a legacy row, with its own audit record. Alternatively, record an explicit owner decision with production evidence. |
| CODEX3-2 | MED (A6 integration precondition; inert at this SHA) | **The pure writer honours unverified knowledge markers, and no release, certificate or PDF path verifies them yet.** `cir.writer.write_pattern` turns any well-formed `learning_rule:include_finishing_checklist:…` primitive into checklist output without verification. This is by design: the writer is pure, and the F-792 originality suite passes. `verify_cir_pins` has **no caller** on release, certificate, quality or PDF paths in this branch. The contract assigns that work to Secondary's A6. This is safe today only because nothing outside `design_eval` produces pinned CIRs: `freeze_pins` is called only for the in-memory incumbent in the preview, and the result is not persisted. A malformed `learning_rule:` primitive makes `write_pattern` raise `ValueError`, which is a fail-closed availability risk. | Probe `probe_cx3_writer.py`: a forged marker (`rule_id 7`, fake digests) **changes** pure-writer output. `verify_cir_pins` and `freeze_pins` refuse it ("not an approved rule version"). `write_with_verified_knowledge` returns the byte-identical baseline. The CIR fingerprint changes with the marker, so certificates bind to it. **For A6:** before any pinned CIR can exist, call `verify_cir_pins` and refuse at the draft, revision, certificate, release, quality and PDF boundaries, exactly as `I-A6-FROZEN-KNOWLEDGE-CONTRACT` requires. `write_with_verified_knowledge` must never be wired onto those paths; today it has no caller. Add a test showing that a release path refuses a forged or stale pinned CIR. |
| CODEX3-3 | LOW | **Knowledge validity is coupled to the whole implementation and to the private volume.** `verify_pins` re-runs `implementation_digest`. That digest covers the source of ~23 modules (writer, compiler, twin, reverse, gates, etc.), the numpy and scipy versions, and the three bench2 files read under a live licence check. Any deploy that touches one of those modules, a dependency bump, a missing library volume, or a bench2 licence change therefore invalidates every approved rule. Once A6 enforces refusal, that also makes every pinned CIR unreleasable until it is re-evaluated and re-approved with owner step-up. This fails closed, which is correct. It is an operational trap rather than a security issue. | Code read: `design_knowledge._assert_evaluation` and `design_eval.implementation_digest`. **Suggest:** A6 should define a re-evaluation workflow and an alert (incident) for knowledge that went stale after a deploy, before going live. |
| CODEX3-4 | LOW | **Dead-job re-drive is bounded per sweep but not over time.** On `DuplicateJob`, `enqueue_purchase` and `design_eval.sweep` call `requeue_dead(ids=[existing_id])` with `reset_attempts=True`. The call is scoped to a single id: an `existing_id` of -1 matches nothing, and `redrivable` and `retry_allowed` are honoured. However, a job that dies deterministically is re-driven with attempts reset on every daily sweep, forever, and each re-drive counts as `work_done`. That masks the no-work signal. | Code read: `runtime/teardown_ops.py:99-103`, `teardown/jobs.py:41-44`. **Fix:** pass `reset_attempts=False`, or cap re-drives per input digest; do not count a re-drive as work. |
| CODEX3-5 | LOW | **Partial bench2 stages are ignored at approval.** `classify_evaluation` requires bench2 `pattern` and `cir` to be PASS, but `reference`, `ad_image` and `comparison` are always `UNKNOWN` and never consulted. That is acceptable for the only supported rule, a finishing-section formatting change. It must not be inherited by a rule that changes construction or imagery, because UNKNOWN must never count as PASS. | Code read: `design_eval._bench2_stages` and `classify_evaluation`. |
| CODEX3-6 | INFO | **The bench2 builder is not a sandbox; Codex says so too.** Confirmed: from restricted `exec` globals, `CIR.__init__.__globals__["__builtins__"]` reaches `open` and `__import__`. `_bench2_stages` catches only `(KeyError, TypeError, ValueError, SyntaxError)`, so any other exception from the pinned builder would crash the evaluate job instead of becoming a refusal. With the current pinned source that cannot happen (see below). | Inline probe (scratch). |
| CODEX3-7 | INFO | Naming overlap after the merge: INTEG1's `intel/knowledge_gaps` (`learning.knowledge_gaps` job) and this branch's `improve/knowledge_gaps` (incident signature `learning.knowledge_gap:analysis:<id>`) are different systems. They do not collide, but they will confuse operators. | grep on the merge tree. |

## Executor security assessment (bb6c558a, bench2 evaluator)

**Pin integrity.**

| File | Pinned SHA-256 | Repo file SHA-256 | Match |
|---|---|---|---|
| `research/bench2/product_truth.py` | `dec34b0b5cea211ef31399835952d2bc34679cdaa5bfe32a3b4a7330260f6a83` | `dec34b0b…6a83` | Yes |
| `out/product_truth.json` | `5167e32b…2aa1` | `5167e32b…2aa1` | Yes |
| `out/bench2_manifest.json` | `bf5f8c68…01ed` | `bf5f8c68…01ed` | Yes |

The builder's only history is bb0f43d0 (the W4-K9 merge); it is unchanged in this delta.

**Source review of the pinned builder.**

- Only `build_cir` (lines 213-288) executes; it was reviewed line by line:
  - No decorators and no default arguments, so nothing runs at definition time.
  - No `import`, `global`/`nonlocal`, lambda, yield or await.
  - No dunder names. The only attribute accesses are `.append` and `.index`.
  - No I/O, `eval`/`exec`, `open`, environment or network access.
  - Free names: the injected `CIR, Component, Gauge, Material, Op, Row, Seam, SIZES`, the builtins `int, range, round`, and locals.
  - The single `while k < (after or 6)` loop is bounded by pinned truth data.
  - f-strings format pinned JSON scalars only.
- The rest of the file (module-level `mkdir`, `sys.path` insert, `os.environ` default, parsers, `main`) is **never executed**: only the `build_cir` FunctionDef node is compiled into a fresh `ast.Module`.
- The file contains a scratchpad default path for `BENCH2_PATTERN_TXT`. It is used only by `parse`/`main`, which are not executed (INFO).

**Hashed buffer, not a re-read.**

- `_bench2_files` reads each file exactly once into `bytes` and hashes those bytes.
- `_bench2_stages` receives the same `builder_bytes` object and runs `ast.parse(builder_bytes)` on it. Nothing re-opens the file between hashing and compiling.
- TOCTOU on the file therefore does not matter. Even a symlink swap between `library.retrieve`'s `resolve()` check and `read_bytes()` could only yield bytes that must still match the SHA-256.

**Only `build_cir` runs.** Exactly one top-level `FunctionDef` named `build_cir` is required, otherwise `ValueError`. Restricted `__builtins__` is hygiene, not containment (CODEX3-6).

**No challenger-supplied builder.**

- `_bench2_files()` takes only `db`.
- Paths are constants: the repo path when present, else `$BRAMBLELOOP_BENCHMARK_LIBRARY/benchmark-2-mini-star-stitch-cardigan/evaluation/*`.
- `load_cases(challenger_cases=…)` is still refused.
- No API, job input or DB field reaches the builder bytes or the pins.

**Licence handling.**

- `refuse_unless_permitted(db, ref, "private_analysis")` runs before any read.
- Each `library.retrieve(..., db=db)` re-checks the recorded licence per file. A licence revoked between the three reads therefore raises `LibraryRefused`, which becomes `DesignEvaluationRefused`.
- A revocation after the reads completes cannot retroactively undo that one evaluation. However, `verify_pins` re-runs `_bench2_files` at every use, so revocation immediately withholds all approved knowledge (fail-closed).
- `retrieve` keeps the role guard (`teardown_analyst` is an analyst role) and the root-containment guard (CODEX1-9).

**Threat model.**

- A malicious buffer with the right hash requires a SHA-256 second preimage, which is infeasible.
- A malicious *pinned* update requires all of the following:
  - a commit to `research/bench2/product_truth.py` (or a library-volume file);
  - a matching new `_BENCH2_BUILDER_SHA` constant in `quality/design_eval.py`, which is code under review;
  - a deploy.
- Anyone able to do that can already change any Python in the image, so the pin adds no new trust root.
- **Requirement for Main:** treat any change to `_BENCH2_*_SHA` or to `research/bench2/product_truth.py` as security-sensitive code review. The builder runs in-process in the worker, which holds DB credentials.

**Fallback path.** When `research/bench2/out/product_truth.json` exists (repo checkouts and tests), the files are read directly from the repo tree, not through the quarantine reader, but under the same licence pre-check and SHA pins. This is acceptable: those bytes are already in git.

**Assessment:** acceptable for this exact pinned source. It is not a sandbox, and it must never be generalised to evaluate any builder that is not pinned and reviewed.

## A6 contract checks (c7bda4e1 and later)

- **`verify_pins`:**
  - Strict shape: exactly 4 keys, `int` ids (bool rejected), versions > 0, lowercase 64-hex digests, no duplicates.
  - Requires `state == "approved"`, `active_slot == 1`, matching version, `approved_by` and `approved_at` set, `approved_by ≠ producer`, `rule_digest` match, and an approval audit by the approver with matching `rule_digest` and `evaluation_digest`.
  - Re-validates provenance at use time: reviewed sources, digests, the manifest and licences.
  - Re-asserts the evaluation: `design_eval.completed` by `design_evaluator`, bound to a `DesignEvaluationRun`, `state == passed`, `approval_evidence_complete`, and rule, lineage, implementation, corpus and case-set digests all current. `classify_evaluation` must still give `passed`.
  - Probe: forged, uppercase, extra-key, bool-id and non-list pins are all refused.
- **`freeze_pins`:** verifies first, refuses to replace existing different pins, and requires provenance. Forged pins are refused.
- **`verify_cir_pins`:** also checks the rule-name-to-statement mapping.
- **`applicable`:** logs and returns `[]` on any failure. Its only callers are `design_eval._incumbent_pins` and `knowledge_gaps`; it is not on release paths.
- **Pure writer:** `write_pattern` reads only the CIR, with no DB, library or reference context. `test_originality` passes.
- **`write_with_verified_knowledge`:** no caller in `src` (grep), so it is not reachable on release or PDF paths at this SHA. See CODEX3-2 for the A6 obligation.
- **Approval:** `design_knowledge.review_rule` is in `approvals.ACTIONS` with step-up `True`. `test_codex_finding_review_cc` (4/4) shows that an operator token and an un-stepped session are refused, and that the owner can approve only a completed evaluation.
  - Self-review is refused: `producer` against the reviewer, casefolded.
  - A `no_improvement` or repeated successor cannot be approved (`test_codex_knowledge_contract`, 3/3).
  - Only one active slot exists, enforced by a unique index on `active_slot`; a successor must supersede the incumbent.
- **Evidence digest binding (8f2a5c7c):**
  - `independent_decision` now also requires `reviewed_sha256 == evidence_digest(row)`, so changed evidence becomes unreviewed.
  - `_reviewable` allows re-review of `proposed` rows and of digest-less or changed `reviewed`/`rejected` rows. The CAS update matches on the prior state and digest (`== None` compiles to `IS NULL`).
  - This does **not** reintroduce an unclearable block for rows that have a recorder. Digest-less reviews existed only on unmerged branch code. A previously *rejected* digest-less row reappears as `proposed` and, if unmet, holds until it is re-rejected; that hold is clearable.
  - The adopted floor (`detail.adopted`) is deliberately outside the digest; it is a later owner/system action, not evidence.
- **Job registration:** `design_eval.sweep` and `design_eval.evaluate` are in `JOB_CLASS` (`_B`), `JOB_BANDS` (`benchmark_change`), `WORK_KEYS` and the orchestrator agent registry; the daily cadence is registered. `test_w3_k11_authority` passes.

## IP isolation and held-out leakage

- **PASS.** No `DesignRule`, `BenchmarkAnalysis`, `design_eval` or bench2 read occurs on any CIR, PDF, listing or image path.
  - `design_eval` is imported only by `runtime/teardown_ops.py` and `improve/design_knowledge.py`.
  - The rule vocabulary is closed (`include_finishing_checklist`, no parameters) and only reformats our own finishing lines.
- Evaluation records hold hashes, counts and closed codes. Shingles are compared, not stored.
- The manifest is ids and hashes only.
- **Held-out caveat (INFO, unchanged):** the "held-out" set is our own launch catalogue, which is a fixed regression set.

## DB compatibility (rollback target 0967c3ee)

- **Schema changes are additive:**
  - `teardown_findings.reviewed_sha256` and `benchmark_analyses.reviewed_sha256` (nullable);
  - `design_rules.active_slot` (nullable) with the unique index `uq_design_rule_active_slot`;
  - new table `design_evaluation_runs` (FKs to `design_rules` and `audit_log`; the audit actions it references are `lifetime_total` in retention).
- **Round trip on SQLite** (`probe_cx3_mig.py`):
  1. 0967c3ee code creates the DB and writes a finding.
  2. Head code runs create_all and `migrate.apply`, which is idempotent (a second run makes no changes). `review_state` is backfilled to `proposed`. The new table and index are present, and head writes an attributable finding.
  3. **0967c3ee code writes and reads again successfully.**
  4. Head reads again: the rollback-window row has `review_state NULL` and is classed `legacy`, which feeds CODEX3-1.
- **Rollback is safe at the schema level.** Live Postgres was not exercised (UNKNOWN).

## Suites (20e0b3a7; one at a time; venv-integ4; `BRAMBLELOOP_BENCHMARK_LIBRARY` unset)

| Suite | Result |
|---|---|
| test_w4_fmbatch1_retention_guard | PASS (5/5); CODEX2-2 fixed |
| test_codex_legacy_findings | PASS (2/2); note that test 2 asserts the CODEX3-1 relaxation |
| test_codex_analysis_store | PASS (1) |
| test_codex_analysis_worker | PASS (7) |
| test_codex_design_eval_cases | PASS (7) at the branch head; on the INTEG1 merge, UNKNOWN (not run; manifest drift shown directly) |
| test_codex_design_proposals | PASS (3) |
| test_codex_failure_mining | PASS (1) |
| test_codex_finding_review | PASS (1) |
| test_codex_finding_review_cc | PASS (4) |
| test_codex_knowledge_contract | PASS (3) |
| test_codex_lesson_provenance | PASS (4) |
| test_codex_library_boundary | PASS (5) |
| test_codex_purchase_intake | PASS (3) |
| test_codex_purchase_intake_api | PASS (1) |
| test_cert_improve_wave | PASS (0 failures) |
| test_originality | PASS (28/28) |
| test_image_reference_hash_failclosed | PASS (4) |
| test_w3_k11_authority | PASS (0 failing) |
| test_swarm_runtime | PASS |
| test_teardown | PASS |
| test_cert_culture_teardown | PASS (0 failed) |
| test_w4_auditfix_migrate | PASS (0 failing) |
| test_shadow | PASS (rc 0, 1510 s) |

The full suite was not run (per instructions); all other suites are UNKNOWN. No assertion removals were found in the delta's test diffs: the removed lines are fixture setup and imports moved into helpers.

## Merge with origin/claude/w5-INTEG1 (7c42e706)

`git merge-tree --write-tree --name-only origin/claude/w5-INTEG1 20e0b3a7` exits 1 with the same three textual conflicts as before:

- `COORDINATION.json`
- `brambleloop/src/brambleloop/autonomy/autonomy_map.json`: regenerate after the merge.
- `brambleloop/src/brambleloop/runtime/pipeline.py`: the late-import block. Keep INTEG1's `commercial_ops`, `learning_gaps_ops` and `evidence_ops` and Codex's `teardown_ops`.

Auto-merged: `registry.py`, `approvals.py`, `classes.py`, `cir/writer.py`, `models.py`, `improve/bus.py`, `retention.py`, `release.py`, `worker.py`, `orchestrate.py` and `ops/CONTRACT_CHANGES.md`.

**Semantic drift (CODEX2-3):** after the merge, `materialize_cases()` differs from the frozen manifest on `hexagonal-bread-basket` and `hexagon-coaster-set` (`cir_sha256`). INTEG1's writer and compiler changes also change `implementation_digest`, so any evaluation or pin would need re-running.

After the merge:

1. Re-freeze `design_eval_cases.json` deliberately, recording who did it and why.
2. Regenerate the autonomy map.
3. Rerun `test_codex_design_eval_cases`, `test_codex_knowledge_contract`, `test_v11_autonomy_timeline`, `test_w3_k11_authority` and `test_w4_fmbatch1_retention_guard`.

The merged tree's suites were not run (UNKNOWN).

## Commands

```
git -C /home/user/Project-Money fetch origin codex/p0-learning-reference claude/w5-INTEG1 claude/w5-SECREVIEW-CODEX2
git worktree add --detach <scratch>/cx3rev 20e0b3a7 ; <scratch>/cx3base 0967c3ee ; <scratch>/cx3merge origin/claude/w5-INTEG1 (+ merge --no-commit 20e0b3a7)
sha256sum brambleloop/research/bench2/product_truth.py brambleloop/research/bench2/out/{product_truth,bench2_manifest}.json
cd <wt>/brambleloop && env -u BRAMBLELOOP_BENCHMARK_LIBRARY PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/<suite>.py   # one at a time
probes: scratchpad/probes/probe_cx3_gate.py (both SHAs), probe_cx3_writer.py, probe_cx3_mig.py (base -> head -> base -> head on one SQLite file)
git merge-tree --write-tree --name-only origin/claude/w5-INTEG1 20e0b3a7
git worktree remove --force <scratch>/cx3rev <scratch>/cx3base <scratch>/cx3merge
```
