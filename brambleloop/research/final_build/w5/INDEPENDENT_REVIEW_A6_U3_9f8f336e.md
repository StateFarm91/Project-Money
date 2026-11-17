# Independent review: U3 "A6 Learning certification/delivery safety" at 9f8f336e

- Head: `codex/a6-learning-consumer` @ `9f8f336e94a10d6ea8aa435f392501cef2ea070f` (PR #32). It contains
  `opus2/a6-codex-contract` 594d5e38, `opus2/a6-learning-to-design` 8c131f10 and
  `codex/p0-learning-reference` 1ae00eb3.
- Target: `claude/w6-INTEG1` @ `5913931f`. Merge base `7c42e706` (w5-INTEG1). The diff is 80 files,
  +8685/-90.
- Method: read-only. A trial merge was made in the throwaway worktree `/home/user/bl-runs/wt-rv-a6`
  (detached, `--no-commit`). Mutants ran in a plain copy, `/home/user/bl-runs/mut-a6`. Nothing was
  committed, pushed or deployed, and no paid provider was called. Both trees were removed at the
  end (`git worktree remove --force`, `rm -rf mut-a6`).
- Python: `/home/user/bl-runs/venv-integ4/bin/python`, from `brambleloop/`, with `PYTHONPATH=src:tests`.
  The host was shared, with load average 12–16 on 4 cores for most of the run.

## Verdict: DO NOT SHIP 9f8f336e (no subset is shippable as reviewed)

1. **The branch says it must not be integrated.** `research/final_build/w5/CODEX_A6_CONTINUATION_HANDOFF.md`
   section "Independent review: do not integrate" records two HIGH findings that are still open: pin
   absence inferred from a caller-supplied CIR, and certify-vs-retire TOCTOU. It also says "do not
   merge or deploy from this branch". My code reading confirms both defects exist at 9f8f336e
   (F1, F2).
2. **One of its own acceptance suites fails.** `test_w5_a6_learning_to_design` FAILS 2/6 on the
   trial merge. The author records this as an expected, deliberate failure. It is still a red suite,
   and the A6 acceptance criterion it encodes ("a lesson changes a drafted construction") is unmet.
   UNKNOWN or deliberately failing never counts as PASS.
3. **Prior A6-1 and A6-2 are closed only by disabling the path.** The root cause of A6-1 (a fixed
   5.0 mm hook with no hook-band check at certification) is still present, and **no test protects
   the disablement**: mutant M15 re-enables the legacy yarn path, and the only tests it touches were
   already failing.

4. **Five live guards have no test.** Mutants M3 (read-side approver independence), M8 (a visual
   stage with the release missing), M9 (publication re-verification), M14 (a frozen record
   replaced) and M15 survive.

Required before re-review:
1. Fix F1 and F2: trusted lineage for pin presence, and a transactional fence between retire and
   certify/publish.
2. Rewrite or remove the legacy positive-effect tests and code paths (F3).
3. Add tests that kill M3, M8, M9, M14 and M15.
4. Either derive the hook from the yarn and add a certification hook-band check, or delete the
   `yarn_weight` lever (F4).
5. Record the pin-invalidation outage cliff (F5) in BUILD_STATE.

The new DesignRule / frozen-pin mechanism is otherwise solid on the paths it covers. Most gate-boundary
mutants were killed (see the mutant table). Its authority is owner step-up
only, and it makes no paid or LLM calls. It never copies source text. No support text or customer
data flows into it.

**Subsets.** `codex/p0-learning-reference` 1ae00eb3 alone is not a clean subset:
- It adds `writer.write_pattern` marker rendering without the certify, PDF and publish
  re-verification that 594d5e38 adds.
- It conflicts with w6 on `autonomy_map.json` and `pipeline.py`.
- It was not reviewed as a standalone unit.

The opus2 legacy-consumer commits (8c131f10) must not ship; see A6-1 and A6-2.

## Prior findings on 8c131f10

| ID | Status at 9f8f336e | Evidence |
|---|---|---|
| **A6-1 HIGH** (approved yarn lesson certifies with fixed 5.0 mm hook) | **NEUTRALISED, root cause open, unprotected.** | `runtime/pipeline.py:1097-1102`: `_design_learning` now returns `{"summary", "changes": [], "applied": False}` and never returns `yarn_weight` or `construction`, so `handle_cir_draft:852-853` and `_draft_creative` (`yarn_weight=learning.get("yarn_weight") or DEFAULT_WEIGHT`) always use the default weight. Confirmed by run: the yarn acceptance test now fails because the gauge stays `medium`. **Still present:** `creative/prototype.py:131` hard-codes `hook_mm=5.0` for every weight, and nothing in `gates/`, `cir/` or `quality/` checks the hook against the yarn's band (grep: only `certificate.py:669` compares hook *equality* to a stored gauge). The dead code that consumes `learning["yarn_weight"]` is still wired. **Mutant M15** (re-enable the yarn value) is not killed by any passing test, so a one-line regression would silently reopen A6-1. |
| **A6-2 MED** (`lesson.acted_on` records a change that did not happen) | **CLOSED for preferences by disablement; holds are truthful.** | No construction or yarn change is recorded (`changes: []`). The only remaining `record_application` caller is the hold branch (`pipeline.py:1088-1091`), and there the draft really is refused, so the record is true. The underlying same-ENGINE_ROUTE comparison bug in `_preferred_construction` (`want != current` on concept vocabulary) is still in the source and becomes live again if preferences are re-enabled. |
| A6-3 MED (unauthenticated AuditLog approval) | **Partly resolved.** | Design-changing authority moved to `DesignRule` + owner step-up (`approvals.py` `design_knowledge.review_rule`, `requires_step_up`). **Holds** still honour any `AuditLog(action="lesson.design_approved", actor in {owner, evaluator})` row, with no re-check of independence (`consume._design_approval`, `consume.py:237`). Today this can only refuse a draft, so it is fail-closed (LOW). |
| A6-4 MED (cir.revise hold vs A5 named hold, vocabulary mismatch) | **OPEN.** | `engineering_ops.py:121-128` (the hold check is at 125-128): the hold returns `learning.hold` with no `record_hold`/incident and is checked against `cir.construction` (flat_rows/joined_rounds/spiral_rounds). A5 is not in w6, so this is deferred to the U10 merge. It must be resolved there. |
| A6-5 (8 of 12 guard mutants survived) | **Superseded.** | The guards being mutated are new. See the mutant table below. |
| A6-6 LOW, A6-7 LOW | A6-6 is open for holds. A6-7 is moot, because the pins replace the provenance marker. | |

## Findings at 9f8f336e

### F1 HIGH (author-declared, confirmed by reading): pin absence is inferred from the caller-supplied CIR
- `improve/knowledge_gate.py:23-29` `has_pins(cir)` and `refusal()` (`:49-60`) return None
  ("no pins, nothing to verify") for any CIR whose `primitives_used` lack a `learning_rule:` marker.
- `engineering_ops.handle_cir_revise:110` and `gate.certify` (`pipeline.py:1370`) both judge the CIR
  from the job inputs.
- **Scenario.** A pinned design reaches `cir.revise` or `gate.certify` after its marker was stripped
  (a bug, a replayed job, or a hand-written job). It is then treated as never pinned. After the rule
  is retired, the design still goes through repair, compile and certify as an unpinned baseline
  under the same slug@version lineage.
- The visual boundaries now bind to the stored release hash (`stored_visual_refusal`). The
  revise and certify path does not.
- The fix the author names (bind pin presence to trusted immutable lineage, such as the drafted CIR
  fingerprint or the `design_knowledge.frozen` audit) is not implemented.
- Impact is bounded: an unpinned CIR is the pre-A6 baseline design, and it still passes every
  deterministic gate. The concern is knowledge-lineage integrity, not a pattern-truth regression.
  I would grade it MEDIUM, but the author and the earlier reviewer hold it at HIGH and it is
  declared integration-blocking.

### F2 HIGH (author-declared, confirmed by reading): retire/certify TOCTOU
- `pipeline.py:1366-1375`: the pin check runs in its own read session.
- The certificate is computed and persisted later (`certify(...)` at about line 1417, and the
  PatternVersion write further down) with no shared lock on `DesignRule` and no re-check in the
  write transaction.
- `review_rule(decision="retire")` (`design_knowledge.py`, with update+audit in its own session)
  can commit in between, and a certificate is then granted for a retired pin.
- The same pattern (check, then act, in different transactions) exists at `assets.build`
  (`release.py:328`), `for_publish` (`release_gates.py:1634`) and the visual stages.
- Mitigation: `quality reverify`, `for_publish` and the visual stages re-check later, so the stale
  certificate is caught downstream on the next pass. It is not atomic.

### F3 MEDIUM: an acceptance suite in the unit fails; the A6 acceptance criterion is unmet
`tests/test_w5_a6_learning_to_design.py` fails 2/6 on the trial merge:
- `test_an_approved_construction_preference_changes_the_drafted_construction` (joined_rounds →
  joined_rounds);
- `test_an_approved_yarn_weight_lesson_changes_a_radar_fallback_draft` (gauge unchanged).

The handoff acknowledges this. The suite is unchanged since ebead3dd and was not rewritten to assert
the new held behaviour. As a result, it now protects neither the old contract nor the new one (see
M15). Required:
- rewrite the two tests to assert `design_changes_held is True` and an unchanged CIR fingerprint
  for both construction and yarn;
- or delete the legacy preference code paths outright.

### F4 MEDIUM: the A6-1 root cause remains (hook not derived from yarn, no certification band check)
`creative/prototype.py:131`. It is unreachable at 9f8f336e only because every draft path uses the
default weight. The A5 `GAUGE_FROM_YARN_BAND` repair (U10) inherits it. Fix it before any yarn
lever is re-enabled, by any route, including a future DesignRule.

### F5 MEDIUM (availability, fail-closed): every routine code change invalidates every pin
`quality/design_eval.py:85-110` `implementation_digest` hashes the source of 24 modules, including
the compiler, writer, certificate, originality, policy, risk_matrix and design_knowledge, plus the
numpy and scipy versions and the private bench2 files. `_assert_evaluation`
(`design_knowledge.py:527-529`) requires the current digest at every `verify_pins`.

**Scenario.** Any deploy that edits `cir/compiler.py`, or a new benchmark purchase (which changes
`corpus_digest`), makes *every* pinned release fail at once:
- certify, the PDF and `for_publish` refuse;
- `quality reverify` opens a P2 incident and withholds publication;
- the visual stages refuse.

This lasts until `design_eval.sweep` re-evaluates (daily cadence) and the owner step-up re-approves
each rule (`reapprove`). It is safe, but it is an outage cliff tied to ordinary engineering work.
`verify_pins` also recomputes the digest (24 × `inspect.getsource` plus library retrieval) on every
call, including every visual stage. Neither cost is acknowledged in BUILD_STATE or the handoff.

### F6 LOW: the customer delivery re-render does not re-verify pins
`commerce/deliverables.py:80-110` `render_certified_pdfs` re-renders the certified CIR, including any
`learning_rule:` markers (writer `cir/writer.py:488-491` applies them **without** authority checks),
and never calls `knowledge_gate.refusal`. The contract text (`contracts.py` CHANGELOG v3, and the
`knowledge_gate` docstring "every boundary") says the PDF refuses.

The delivered bytes equal the certified bytes, so this does not affect Product Truth. The claim is
still overstated. Either gate delivery explicitly or narrow the claim. The same applies to the other
`write_pattern` callers (`learn/swatch.py`, `learn/beginner_sim.py`, `gates/first_customer.py`,
`products/reengineer.py`). The writer trusts markers, and only the release boundaries verify them.

### F7 LOW: fail-to-baseline reads
- `knowledge_gate.freeze_applicable:38-45` returns the CIR unchanged on any exception.
- `design_knowledge.applicable:156-185` returns `[]` on any exception.

An unreadable store silently drafts the baseline. That is not a safety fail-open: the baseline is
the pre-A6 certified-safe design and nothing is approved by it. But a store outage silently stops
applying approved knowledge, and it is logged only at WARNING/exception level. The draft should
carry an UNKNOWN marker, not "no knowledge applies".

### F8 LOW: new production cadences, not fixture-only
- `runtime/worker.py:937-938` adds daily `teardown_analyse_sweep` and `design_eval_sweep`.
- `agents/registry.py` grants the orchestrator four new job types.
- `authority/classes.py` gives them class B.

They are deterministic and make no paid or network calls (checked `quality/design_eval.py`,
`design_revalidation.py`, `runtime/teardown_ops.py`, `teardown/analysis_store.py` and
`teardown/jobs.py`: no gateway, LLM or HTTP imports). They do read the private benchmark library in
production (the `DEFAULT_LIBRARY` change below). The map lists only U4, not U3, as fixture-only, so
this is in scope. Note it for the deploy:
- `teardown/library.py:37` changes `DEFAULT_LIBRARY` to `/var/lib/brambleloop/benchmark_library`.
- `library_root` now raises `LibraryRefused` for any path inside the repository or application tree.
- `gates/originality.refuse_benchmark_reference` converts that to `ReferenceRefused`, which is
  fail-closed.

A production host with `BRAMBLELOOP_BENCHMARK_LIBRARY` unset or set to an in-tree path will start
refusing reference checks. That is correct, but it must be configured before the deploy.

### F9 LOW: `teardown/licence.py` default semantics changed
`terms.get("allowed_uses", DEFAULT)` replaces `terms.get(...) or DEFAULT`, for both allowed and
prohibited uses. An explicit `[]` now means "none" instead of "default":
- for `allowed_uses` this is stricter;
- for `prohibited_uses: []` it removes the default publishing prohibitions.

This is not a relaxation in practice, because `Licence.permits` also requires the use to be in
`allowed_uses`, which still defaults to private research uses. It should be documented, and the
owner-supplied terms on intake still need to be read carefully.

### Checked and found sound
- **Authority.**
  - Rule approval, reapproval and retirement go only through `command_center.execute`
    (`design_knowledge.review_rule`) with `reviewer="owner"` and `requires_step_up: True`.
  - Producer independence is enforced, and the mutant (M6) is killed.
  - `verify_pins` binds the rule digest, approval audit (actor equals `approved_by`), evaluation
    digest, lineage digest, licence and manifest at use time.
  - No LLM, agent or unapproved lesson can change a design, price, listing or publication through
    this unit.
  - The rule vocabulary is closed: two parameterless finishing-checklist rules. No parameter
    carries source text.
- **Consent.**
  - No support text or customer data enters Learning. `readings_bus._customer` publishes counts
    only (`source_findings=[]`).
  - `_lesson_roots` accepts a `support_cases:` lesson only as a reference id, and the lineage
    digest stores `evidence_ref` only.
  - A rule cannot be supported by support lessons alone: it needs a reviewed analysis.
  - `analysis_store` stores vocabulary keys, flags, page numbers and counts, never document text.
- **Spend.** Nothing in the unit touches `gateway/` or a paid provider. Teardown intake records a
  purchase the owner already made, and buys nothing.
- **Thresholds.**
  - No existing threshold constant changed.
  - `teardown/enforce.py` makes only independently reviewed findings *binding*, but `check()`
    still blocks release on unreviewed concerns that meet confidence ("requires independent
    review"), so release protection is preserved.
  - New constant: `MAX_AUTOMATIC_REDRIVES = 2`.
- **Laura canonical assets.** No `laura` path is in the diff (`git diff --name-only 7c42e706
  9f8f336e | grep -i laura` is empty). `laura-r2-a42aeac7` is untouched.
- **pytest.** None of the 23 changed or added test files imports pytest. All have a `__main__`
  runner.
- **Retention.** `lesson.design_approved`, `lesson.acted_on`, `design_knowledge.rule_approved`,
  `design_eval.completed`, `teardown.audit_prefilled` and `cir.revise_unrepairable` are classified
  `lifetime_total`. `test_w4_fmbatch1_retention_guard` passes.
- **durable.py atomicity.**
  - `requeue_dead(max_automatic_redrives=...)` validates the limit.
  - It does a compare-and-set update (`status == DEAD AND automatic_redrives == previous`), which
    SQLAlchemy renders as `IS NULL` when the value is None, in one session.
  - A lost race is reported as skipped, never as moved.
  - All new enqueue sites (`teardown/jobs.py`, `teardown_ops.py`) use standalone
    `JobQueue(db).enqueue`, not a caller session, so the missing ee32f68f savepoint does not affect
    them.
  - The new `Job.automatic_redrives` column is nullable with no default, and `core/migrate.apply`
    adds it.

## Trial merge and conflict resolution

`git merge --no-commit 9f8f336e` onto `origin/claude/w6-INTEG1` 5913931f has **1 conflict, and it
is `COORDINATION.json`, not `durable.py`.** The map's "1 (durable.py)" is wrong for this target:
- `queue/durable.py` auto-merges, because 9f8f336e only touches `requeue_dead` and w6 lacks
  ee32f68f.
- `git merge-tree 9f8f336e ee32f68f` also merges `durable.py` cleanly (only `COORDINATION.json`
  conflicts), so a later U1 merge does not conflict textually there.
- The `pipeline.py`, `release.py`, `quality_ops.py`, `main.py`, `registry.py`,
  `incident_lifecycle.py` and `image_production.py` hunks all auto-merge.

Recipe for COORDINATION.json: keep both claim objects in the `claims` array, in order:
1. w6's `CODEX-A7-FRESHNESS-FIX` entry, closed with its own `"files": [... flow_health.py,
   test_w5_a7_supply_stall.py], "claimed_at": "2026-11-03" }`;
2. then 9f8f336e's `CODEX-A6-CONTINUATION` entry (with its own files list and
   `"claimed_at": "2026-11-03"`).

After resolving, `python3 -c "import json; json.load(open('COORDINATION.json'))"` must succeed. It
did on the trial merge.

On w6-INTEG1 there is no semantic conflict in `durable.py`. If U1 (ee32f68f) lands first, re-run
`test_codex_analysis_worker` and `test_codex_technique_supplement`, the redrive users.

## Test table (trial merge, plain scripts)

Suites in the unit's diff (23 files) plus the requested cross-unit and durable.py suites:

| Suite | Result | Time (s) |
|---|---|---|
| test_codex_design_eval_cases | PASS | 14 |
| test_codex_design_proposals | PASS | 4 |
| test_codex_analysis_store | PASS | 20 |
| test_codex_analysis_worker (requeue_dead / redrive user) | PASS | 62 |
| test_codex_failure_mining | PASS | 2 |
| test_codex_finding_review | PASS | 2 |
| test_codex_finding_review_cc | PASS | 21 |
| test_codex_integ1_freeze | PASS | 0 |
| test_codex_knowledge_contract | PASS | 25 |
| test_codex_learning_http_e2e | PASS | 10 |
| test_codex_legacy_findings | PASS | 3 |
| test_codex_lesson_provenance | PASS | 6 |
| test_codex_library_boundary | PASS | 0 |
| test_codex_purchase_intake | PASS | 4 |
| test_codex_purchase_intake_api | PASS | 3 |
| test_codex_revalidation | PASS | 25 |
| test_codex_scoped_knowledge | PASS | 52 |
| test_codex_technique_supplement (redrive user) | PASS | 8 |
| test_cert_improve_wave | PASS 24 | 33 |
| test_w4_fml_checkpoint_adoption | PASS 3 | 6 |
| test_w4_visnext2 | PASS 12/12 | 232 |
| test_w5_a6_frozen_knowledge | PASS 6/6 | 149 |
| **test_w5_a6_learning_to_design** | **FAIL 4/6**: construction preference (joined_rounds -> joined_rounds) and yarn lesson (gauge unchanged) | 21 |
| test_w5_v0_paid_provider_gate | PASS 52 | 101 |
| test_w6_fix_only_rebuild | PASS 14 | 893 |
| test_w6_support_defect_incident | PASS 27 | 308 |
| test_w6_secret_leak_escalate | PASS 8 | 167 |
| test_persistence (durable) | PASS 11 | 45 |
| test_health (durable) | PASS 39 | 272 |
| test_cert_thrash (durable) | PASS 6 | 15 |
| test_cert_orchestration (durable) | PASS 20 | 57 |
| test_chaos (durable) | first run TIMEOUT at 1500 s (32/38 OK, 0 FAIL, under load 13+); **rerun PASS 38/38** | 2508 |
| test_cert_design_pipeline | first run TIMEOUT at 1500 s (9 OK, 0 FAIL); **rerun PASS 17 passing, 0 failing** | 1971 |
| test_compiler / test_reverse / test_twin | PASS 9 / 18 / 8 | 0 |
| test_launch0 | PASS 52 | 76 |
| test_w4_fmbatch1_retention_guard | PASS 5 | 60 |
| test_w3_k11_authority | PASS 19 | 31 |

These suites were not run, so their status is UNKNOWN: test_shadow, the full suite, and the author's
other suites (test_w4_agents, test_w4_visnext, test_w4_wraptest, parity). Also not run:
- **PostgreSQL**: every run used SQLite. The DesignRule `with_for_update` and unique-slot races
  were not exercised on PostgreSQL, so UNKNOWN.
- **Merge with U1 ee32f68f**: it merges cleanly textually, but no suite was run on the combination,
  so UNKNOWN.

## Mutant table (applied to the trial-merge copy; killed means a test result differs from the M0 baseline)

| Mutant (guard) | Result | Killed by |
|---|---|---|
| M1 `knowledge_gate.refusal` never refuses a pinned CIR | KILLED | test_w5_a6_frozen_knowledge |
| M2 `has_pins` always False | KILLED | test_w5_a6_frozen_knowledge |
| M3 `verify_pins`: approver == producer accepted (read-side independence) | **SURVIVED** | - |
| M4 evaluation corpus freshness ignored | KILLED | knowledge_contract, scoped_knowledge, revalidation |
| M5 `verify_cir_pins` scope check removed | KILLED | test_codex_scoped_knowledge |
| M6 `review_rule` independence removed (write side) | KILLED | knowledge_contract, revalidation |
| M7 `stored_visual_refusal` release-hash check removed | KILLED | test_w5_a6_frozen_knowledge |
| M8 `image_production.run_stage` missing-release refusal removed | **SURVIVED** | - (also ran test_w4_visnext2) |
| M9 `for_publish` knowledge reasons dropped (publication boundary) | **SURVIVED** | - |
| M10 `assets.build` (PDF) pin check removed | KILLED | test_w5_a6_frozen_knowledge |
| M11 `gate.certify` pin check removed | KILLED | test_w5_a6_frozen_knowledge |
| M12 quality reverify pin check removed | KILLED | test_w5_a6_frozen_knowledge |
| M13 `requeue_dead` redrive limit `>=` to `>` (durable.py) | KILLED | test_codex_analysis_worker |
| M14 `freeze_pins` allows replacing an existing frozen record | **SURVIVED** | - |
| M15 legacy yarn preference re-enabled in `_design_learning` (the A6-1 path) | **SURVIVED** | No green test changes. The red legacy test moves from an "unchanged gauge" assertion to `KeyError('learning')`: the yarn changes **silently, with no acted_on record and with the 5.0 mm hook** |
| M16 `cir.knowledge.markers` duplicate-pin check removed | **SURVIVED** | - (`verify_pins` has its own duplicate check, so this one is defence in depth) |

11 of 16 killed, 5 survived (M3, M8, M9, M14, M15); M16 is partly redundant. The surviving guards
that matter:
- **M9**: publication's re-verification is untested.
- **M3**: read-side approver independence. Only the write side, M6, is tested.
- **M14**: a frozen record can be replaced.
- **M8**: a resumed visual stage with no release is not tested.
- **M15**: nothing locks the A6-1/A6-2 disablement.

Each needs a test before integration.

Mutant script: `scratchpad/a6u3/a6u3_mutants.py`. Logs are under `scratchpad/a6u3/mutlogs/<Mn>/`.
Tests run per mutant: frozen_knowledge, knowledge_contract, scoped_knowledge, revalidation,
learning_http_e2e, learning_to_design, fml_checkpoint, plus visnext2 for M7/M8, analysis_worker and
technique_supplement for M13, and finding_review_cc for M6. The baseline M0 ran all 11 and matched
the main run exactly.

## Process note (shared scratchpad collision)

The scratchpad directory is shared with a concurrently running A3 reviewer.
- My first mutant script (`scratchpad/mutants.py`) was overwritten by the A3 reviewer's script
  before I launched it, so from about 12:15 to 12:25 UTC one extra copy of **the A3 mutant script**
  ran under my process (PID 21652, cwd `mut-a6`).
- That copy recreated `/home/user/bl-runs/mut-a3/m0..m5` and appended to `scratchpad/mutants.jsonl`.
  `mutants.jsonl` now holds duplicate rows for A3 M1–M3.
- I killed that process tree by PID once I found it. The A3 reviewer should treat its M1–M6
  results as possibly contaminated and re-run them.
- My own mutants then ran from `scratchpad/a6u3/` against `/home/user/bl-runs/mut-a6` only.
